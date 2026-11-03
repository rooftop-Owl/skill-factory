#!/usr/bin/env python3
"""With/without-skill eval for Claude Code (headless `claude -p`).

Runs each task N times per arm in a fresh copy of the target project and scores
each run with that task's deterministic oracle. Arms:

  with     the skill present at .claude/skills/<name>/
  without  .claude/skills/<name>/ removed
  control  (--control) same name + description; SKILL.md body and every other file in
           the skill directory replaced by filler of equal byte length: separates "the
           skill's content helped" from "any skill-shaped text in context helped"

Run tree: the project's working tree (git: tracked plus untracked-not-ignored files)
is copied without .git, the arm is applied, and for a git project a new repository
is created with one commit. The run tree has no remote and no history holding the
skill, so `git log -p`, `git diff` or `git checkout` cannot recover it. The without
and control trees also lose every other copy of the skill: any directory whose
SKILL.md declares the same name (a plugin mirror such as skills/<name>/) and any file
byte-identical to the skill's SKILL.md. The run is refused if any remaining file
(up to SCAN_MAX_BYTES) still contains the SKILL.md body.

Stopping the worker: the script makes itself a child subreaper
(prctl PR_SET_CHILD_SUBREAPER), so every descendant the worker orphans is reparented to
the script however it detaches (setsid, chdir, closed descriptors). The worker runs in
its own process group. When it exits or times out, that group is killed, then every
remaining descendant of the script is killed and reaped. A descendant outside the
worker's own group (Claude Code starts Bash-tool commands with setsid) is a stray.
Finally /proc is swept for processes that are not descendants but whose cwd or an
open file is inside the run tree (a command started through a long-running server);
each is killed and counted as a stray. A run with any stray is `stray-process` (not
scored), and the count is in the receipt. Linux only: without /proc, or if prctl
fails, the script refuses to run.
The sweep kills any of your processes rooted in a run tree; do not cd a shell into
the work root while it runs.

Model and effort are always passed explicitly; the header prints the union of the
models reported in modelUsage across runs, or "model unknown (requested <model>)".

Per run directory: stream.jsonl, stderr.txt and result.txt for every run; oracle.txt
for runs that reached the oracle.

Adherence (was the skill invoked) and effect (oracle pass rate) are reported
separately: an outcome alone cannot say whether a skill failed because it was not
followed or because following it did not help.

Isolation: every run passes `--setting-sources project,local`, which drops
~/.claude/skills and installed plugins, so the run tree's own .claude/skills is the
only non-builtin skill source. Each run's stream-json `system/init` event lists the
loaded skills; a run whose arm disagrees with that list is excluded as invalid.

Not a sandbox: the worker runs as you with --dangerously-skip-permissions and full
access to your files, network and credentials. The run tree is only where it
starts; nothing stops it reading or changing anything else you can, including the
tasks directory and the original project. The tasks directory is refused if it is
inside the project (it would be copied into every run tree), but outside it the
oracle is protected only by the worker not being told its path.

Task layout: <tasks>/<id>/prompt.txt and <tasks>/<id>/oracle.sh. The oracle runs
after the worker's group and the swept processes have been killed, as
`bash oracle.sh <run_tree> <result_text_file>`. Exit 0 is a pass and 1-124 a fail;
a timeout, exit >= 125 (126/127: cannot execute / not found) or a signal makes the
run invalid (oracle-error), never a fail.

Exit codes: 0 report written; 1 report written but some runs were invalid;
2 refused (precondition unmet, CLI absent, 3 consecutive runs unavailable; a
receipt with the completed runs is still written in the last case).
"""
from __future__ import annotations

import argparse
import ctypes
import json
import math
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ARMS = ("with", "without")
CONTROL_ARM = "control"
SMOKE_N = 10
UNAVAILABLE_MAX_CONSECUTIVE = 3
# A result event with is_error set is a real run only when the turn budget ran out;
# every other error result (API error, overload, usage limit) means no measured work.
REAL_RUN_ERROR_SUBTYPES = ("error_max_turns",)
ORACLE_ERROR_MIN_RC = 125
PROC = Path("/proc")
PR_SET_CHILD_SUBREAPER = 36
SCAN_MAX_BYTES = 20 * 1024 * 1024
PIPE_DRAIN_SECONDS = 10
FILLER_LINE = "This line is filler text of matched length and carries no instructions.\n"
PARENT_CONTEXT_FILES = ("CLAUDE.md", "CLAUDE.local.md", ".claude/skills",
                        ".claude/settings.json", ".claude/settings.local.json")


class Refusal(Exception):
    pass


def norm_skill(name: str) -> str:
    """Strip a leading slash. A namespaced `plugin:skill` stays namespaced: it names a
    plugin's skill, never the project skill of the same bare name."""
    return name.strip().lstrip("/")


# ---------------------------------------------------------------- stream-json parsing

def parse_stream(stdout: str, skill: str) -> dict:
    """Extract the facts one run contributes from `--output-format stream-json`."""
    loaded = None
    invocations = 0
    result = None
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        typ = ev.get("type")
        if typ == "system" and ev.get("subtype") == "init":
            loaded = [norm_skill(s) for s in ev.get("skills") or []]
        elif typ == "assistant":
            for block in (ev.get("message") or {}).get("content") or []:
                if (isinstance(block, dict) and block.get("type") == "tool_use"
                        and block.get("name") == "Skill"
                        and norm_skill(str((block.get("input") or {}).get("skill", ""))) == skill):
                    invocations += 1
        elif typ == "result":
            result = ev
    models = sorted((result or {}).get("modelUsage") or {})
    return {
        "init_seen": loaded is not None,
        "skill_loaded": loaded is not None and skill in loaded,
        "invocations": invocations,
        "result_seen": result is not None,
        "result_subtype": (result or {}).get("subtype"),
        "is_error": bool((result or {}).get("is_error")),
        "terminal_reason": (result or {}).get("terminal_reason"),
        "result_text": (result or {}).get("result") or "",
        "models": models,
    }


def classify(arm: str, facts: dict, rc: int) -> str:
    """valid | unavailable | contaminated | not-loaded, from structured events only.

    Never matches text: assistant and tool output can contain any words.
    """
    if not facts["init_seen"]:
        return "unavailable"
    if rc == 124:
        pass  # timed out: the worker started, so the oracle still decides the run
    elif not facts["result_seen"]:
        return "unavailable"
    elif facts["is_error"] and facts["result_subtype"] not in REAL_RUN_ERROR_SUBTYPES:
        return "unavailable"
    if arm == "without" and facts["skill_loaded"]:
        return "contaminated"
    if arm != "without" and not facts["skill_loaded"]:
        return "not-loaded"
    return "valid"


# ---------------------------------------------------------------- statistics

def fisher_exact(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher exact p for [[a, b], [c, d]] (rows = arms, cols = pass/fail)."""
    r1, r2, c1, n = a + b, c + d, a + c, a + b + c + d
    if n == 0:
        return 1.0
    denom = math.comb(n, c1)

    def p(x: int) -> float:
        return math.comb(r1, x) * math.comb(r2, c1 - x) / denom

    observed = p(a)
    lo, hi = max(0, c1 - r2), min(r1, c1)
    total = sum(p(x) for x in range(lo, hi + 1) if p(x) <= observed * (1 + 1e-9))
    return min(1.0, total)


def summarize(runs: list, arms: list) -> dict:
    out = {}
    for arm in arms:
        rs = [r for r in runs if r["arm"] == arm and r["status"] == "valid"]
        invoked = [r for r in rs if r["invocations"] > 0]
        out[arm] = {
            "n_valid": len(rs),
            "n_invalid": sum(1 for r in runs if r["arm"] == arm and r["status"] != "valid"),
            "invoked": len(invoked),
            "passed": sum(1 for r in rs if r["passed"]),
            "pass_rate": (sum(1 for r in rs if r["passed"]) / len(rs)) if rs else None,
            "passed_when_invoked": sum(1 for r in invoked if r["passed"]),
        }
    comparisons = {}
    for other in [a for a in arms if a != "with"]:
        w, o = out["with"], out[other]
        delta = (None if w["pass_rate"] is None or o["pass_rate"] is None
                 else w["pass_rate"] - o["pass_rate"])
        comparisons[f"with_vs_{other}"] = {
            "delta": delta,
            "fisher_p": fisher_exact(w["passed"], w["n_valid"] - w["passed"],
                                     o["passed"], o["n_valid"] - o["passed"]),
        }
    min_n = min((out[a]["n_valid"] for a in arms), default=0)
    return {"arms": out, "comparisons": comparisons, "min_n_valid": min_n,
            "label": "smoke, not evidence" if min_n < SMOKE_N else "measured"}


def render(summary: dict, meta: dict) -> str:
    lines = [
        f"Skill A/B: {meta['skill']}  ({len(meta['tasks'])} task(s), N={meta['n']} per arm per task)",
        f"Effect measured on "
        f"{'/'.join(meta['models_used']) or 'model unknown (requested ' + meta['model'] + ')'}"
        f"/{meta['effort']}  [{summary['label']}]",
        "",
        "Adherence (Skill tool invoked, valid runs)",
    ]
    for arm, s in summary["arms"].items():
        lines.append(f"  {arm:<8} invoked {s['invoked']}/{s['n_valid']}"
                     + (f"   ({s['n_invalid']} invalid run(s) excluded)" if s["n_invalid"] else ""))
    lines += ["", "Effect (oracle pass, valid runs)"]
    for arm, s in summary["arms"].items():
        rate = "n/a" if s["pass_rate"] is None else f"{s['pass_rate']:.0%}"
        lines.append(f"  {arm:<8} {s['passed']}/{s['n_valid']} ({rate})"
                     + (f"   passed when invoked: {s['passed_when_invoked']}/{s['invoked']}"
                        if arm != "without" else ""))
    for key, c in summary["comparisons"].items():
        d = "n/a" if c["delta"] is None else f"{c['delta']:+.0%}"
        lines.append(f"  {key}: delta {d}, Fisher exact p = {c['fisher_p']:.3g}")
    return "\n".join(lines)


# ---------------------------------------------------------------- workspace

def check_work_root(work_root: Path, project: Path) -> None:
    """Refuse a work root that would leak context into the run trees.

    CLAUDE.md is discovered by walking up from cwd, so a parent of the run tree that
    holds one (or a skills/settings dir) would be read by every arm. Works on a path
    that does not exist yet, so nothing is created before the check.
    """
    wr = work_root.resolve()
    if wr == project or project in wr.parents:
        raise Refusal(f"work root {wr} is inside the project; use a directory outside it")
    for parent in [wr, *wr.parents]:
        for rel in PARENT_CONTEXT_FILES:
            if (parent / rel).exists():
                raise Refusal(f"{parent / rel} would be discovered by every run; "
                              "choose a --work-root with no Claude context above it")


def is_git_project(project: Path) -> bool:
    return (project / ".git").exists()


def tree_files(project: Path) -> list:
    """Relative paths the run tree copies (git: tracked + untracked-not-ignored)."""
    if not is_git_project(project):
        out = []
        for d, dirs, files in os.walk(project):
            if Path(d) == project and ".git" in dirs:
                dirs.remove(".git")
            out += [Path(d, f).relative_to(project) for f in files]
            out += [Path(d, x).relative_to(project) for x in dirs if Path(d, x).is_symlink()]
        return sorted(out)
    listed = subprocess.run(["git", "-C", str(project), "ls-files", "-z", "--cached", "--others",
                             "--exclude-standard"], capture_output=True, check=True).stdout
    return sorted({Path(r) for r in listed.decode("utf-8", "surrogateescape").split("\0") if r})


def copy_working_tree(project: Path, dest: Path) -> None:
    """Copy the working tree without .git."""
    if not is_git_project(project):
        shutil.copytree(project, dest, symlinks=True,
                        ignore=lambda d, names: [".git"] if Path(d) == project else [])
        return
    dest.mkdir(parents=True)
    for rel in tree_files(project):
        s, d = project / rel, dest / rel
        if not (s.exists() or s.is_symlink()):
            continue  # tracked but deleted in the working tree
        d.parent.mkdir(parents=True, exist_ok=True)
        if s.is_symlink():
            os.symlink(os.readlink(s), d)
        elif s.is_dir():  # a submodule's gitlink
            shutil.copytree(s, d, symlinks=True, ignore=shutil.ignore_patterns(".git"))
        else:
            shutil.copy2(s, d)


FRONTMATTER_RE = re.compile(rb"\A---\r?\n(.*?)\r?\n---\r?\n?", re.S)
NAME_RE = re.compile(rb"^name:[ \t]*['\"]?([^'\"\r\n]*?)['\"]?[ \t]*$", re.M)


def frontmatter_name(data: bytes):
    m = FRONTMATTER_RE.match(data)
    n = NAME_RE.search(m.group(1)) if m else None
    return n.group(1).decode("utf-8", "replace") if n else None


def skill_body(data: bytes) -> bytes:
    m = FRONTMATTER_RE.match(data)
    return (data[m.end():] if m else data).strip()


def _under(rel: Path, roots) -> bool:
    return any(rel == r or r in rel.parents for r in roots)


def plan_removals(project: Path, files: list, skill: str, skill_src: Path, src_rel) -> list:
    """Every copy of the skill the without/control trees must not hold."""
    removals = {Path(".claude") / "skills" / skill}
    if src_rel is not None:
        removals.add(src_rel)
    md = (skill_src / "SKILL.md").read_bytes()
    for rel in files:
        p = project / rel
        if p.is_symlink() or not p.is_file():
            continue
        size = p.stat().st_size
        if rel.name == "SKILL.md" and size <= SCAN_MAX_BYTES and frontmatter_name(p.read_bytes()) == skill:
            removals.add(rel.parent)
        elif size == len(md) and p.read_bytes() == md:
            removals.add(rel)
    return sorted(removals)


def check_no_leftover_copy(project: Path, files: list, removals: list, skill_src: Path) -> None:
    body = skill_body((skill_src / "SKILL.md").read_bytes())
    if not body:
        return
    for rel in files:
        p = project / rel
        if _under(rel, removals) or p.is_symlink() or not p.is_file():
            continue
        if p.stat().st_size <= SCAN_MAX_BYTES and body in p.read_bytes():
            raise Refusal(f"{rel} contains the skill's SKILL.md body, so the without and control "
                          "arms would still see it; remove or move that copy first")


def init_run_repo(tree: Path) -> None:
    """A fresh repository with one commit of the arm's tree: no remote, no skill history."""
    g = ["git", "-C", str(tree), "-c", "user.name=skill-ab", "-c", "user.email=skill-ab@localhost",
         "-c", "commit.gpgsign=false", "-c", "gc.auto=0", "-c", "maintenance.auto=false"]
    subprocess.run(g + ["init", "-q"], check=True)
    subprocess.run(g + ["add", "-A"], check=True)
    subprocess.run(g + ["commit", "-q", "--no-verify", "--allow-empty", "-m", "skill-ab run tree"],
                   check=True)


def control_skill_md(text: str) -> str:
    """Same frontmatter, body replaced by neutral filler of equal byte length."""
    m = re.match(r"(?s)\A(---\n.*?\n---\n)(.*)\Z", text)
    if not m:
        raise Refusal("SKILL.md has no frontmatter block; cannot build a control")
    head, body = m.group(1), m.group(2)
    return head + filler(len(body.encode("utf-8"))).decode("ascii")


def filler(size: int) -> bytes:
    line = FILLER_LINE.encode("ascii")
    return (line * (size // len(line) + 1))[:size]


def remove_path(p: Path) -> None:
    if p.is_symlink() or p.is_file():
        p.unlink()
    elif p.exists():
        shutil.rmtree(p)


def prepare_arm(tree: Path, arm: str, skill: str, skill_src: Path, removals: list) -> None:
    """Apply the arm. without/control drop every planned copy of the skill (see
    plan_removals); with only replaces .claude/skills/<name>/ by the source."""
    target = tree / ".claude" / "skills" / skill
    remove_path(target)
    if arm == "with":
        shutil.copytree(skill_src, target)
        return
    for rel in removals:
        remove_path(tree / rel)
    if arm == CONTROL_ARM:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(skill_src, target)
        for f in sorted(p for p in target.rglob("*") if p.is_file()):
            if f == target / "SKILL.md":
                f.write_text(control_skill_md(f.read_text(encoding="utf-8")), encoding="utf-8")
            else:
                f.write_bytes(filler(f.stat().st_size))


def build_run_tree(project: Path, dest: Path, arm: str, skill: str, skill_src: Path,
                   removals: list) -> None:
    copy_working_tree(project, dest)
    prepare_arm(dest, arm, skill, skill_src, removals)
    if is_git_project(project):
        init_run_repo(dest)


def load_tasks(tasks_dir: Path) -> list:
    tasks = []
    for d in sorted(p for p in tasks_dir.iterdir() if p.is_dir()):
        prompt, oracle = d / "prompt.txt", d / "oracle.sh"
        if not prompt.is_file() or not oracle.is_file():
            raise Refusal(f"task {d.name} needs prompt.txt and oracle.sh")
        tasks.append({"id": d.name, "prompt": prompt.read_text(encoding="utf-8"),
                      "oracle": oracle.resolve()})
    if not tasks:
        raise Refusal(f"no tasks under {tasks_dir}")
    return tasks


def worker_argv(claude: str, args, prompt: str) -> list:
    # --setting-sources project,local: drop ~/.claude/skills and installed plugins.
    # --no-session-persistence: no transcript is written, so adherence is read from
    #   this stream. --max-turns is accepted but not listed in `claude --help`.
    # --dangerously-skip-permissions: headless has no one to approve a write. The
    #   worker then runs with the user's full file access and no sandbox.
    return [claude, "-p", "--verbose", "--output-format", "stream-json",
            "--no-session-persistence", "--setting-sources", "project,local",
            "--dangerously-skip-permissions",
            "--model", args.model, "--effort", args.effort,
            "--max-turns", str(args.max_turns), prompt]


def _drain(pipe, chunks: list) -> None:
    while True:
        b = os.read(pipe.fileno(), 65536)
        if not b:
            return
        chunks.append(b)


def processes_rooted_in(tree: Path) -> list:
    """PIDs (other than this one) whose cwd or an open file is inside `tree`."""
    root = str(tree.resolve())
    me, hits = os.getpid(), []
    for d in PROC.iterdir():
        if not d.name.isdigit() or int(d.name) == me:
            continue
        try:
            paths = [os.readlink(d / "cwd")]
        except OSError:
            continue  # gone, a zombie, or not ours
        try:
            for fd in (d / "fd").iterdir():
                try:
                    paths.append(os.readlink(fd))
                except OSError:
                    pass
        except OSError:
            pass
        if any(p == root or p.startswith(root + os.sep) for p in paths):
            hits.append(int(d.name))
    return hits


def set_subreaper() -> None:
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        ok = libc.prctl(PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0) == 0
        err = ctypes.get_errno()
    except (OSError, AttributeError) as e:
        ok, err = False, str(e)
    if not ok:
        raise Refusal(f"cannot become a child subreaper (prctl PR_SET_CHILD_SUBREAPER: {err}); "
                      "it is needed to stop worker children that detach (Linux only)")


def descendants(root: int) -> dict:
    """pid -> (ppid, pgrp, state) for every process descended from `root`."""
    table = {}
    for d in PROC.iterdir():
        if not d.name.isdigit():
            continue
        try:
            stat = (d / "stat").read_text()
        except OSError:
            continue
        rest = stat[stat.rindex(")") + 2:].split()
        table[int(d.name)] = (int(rest[1]), int(rest[2]), rest[0])
    kids = {}
    for pid, (ppid, _, _) in table.items():
        kids.setdefault(ppid, []).append(pid)
    out, stack = {}, [root]
    while stack:
        for c in kids.get(stack.pop(), []):
            out[c] = table[c]
            stack.append(c)
    return out


def kill_descendants(worker_pgid: int) -> int:
    """Kill and reap every descendant of this process; return how many were alive and
    outside the worker's own (already killed) process group."""
    me, strays = os.getpid(), set()
    for _ in range(100):
        desc = descendants(me)
        if not desc:
            break
        for pid, (ppid, pgrp, state) in desc.items():
            if state != "Z" and pgrp != worker_pgid:
                strays.add(pid)
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            if ppid == me:
                try:
                    os.waitpid(pid, os.WNOHANG)
                except ChildProcessError:
                    pass
        time.sleep(0.02)
    return len(strays)


def kill_rooted(tree: Path) -> int:
    """Kill every process rooted in the run tree; return how many were found."""
    found = set()
    for _ in range(20):
        pids = processes_rooted_in(tree)
        if not pids:
            break
        for pid in pids:
            try:
                os.kill(pid, signal.SIGKILL)
                found.add(pid)
            except ProcessLookupError:
                pass
        time.sleep(0.1)
    return len(found)


def run_group(argv: list, cwd: Path, timeout: int) -> tuple:
    """Run argv in its own session; when it exits or times out kill its process group,
    then every other descendant (see kill_descendants), then any non-descendant still
    rooted in `cwd`.

    Returns (rc or None on timeout, stdout, stderr, strays). Output is read by threads
    and joined with a bound, so a child that keeps a pipe open cannot hang the run.
    """
    proc = subprocess.Popen(argv, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            start_new_session=True)
    bufs = ([], [])
    readers = [threading.Thread(target=_drain, args=(pipe, buf), daemon=True)
               for pipe, buf in zip((proc.stdout, proc.stderr), bufs)]
    for t in readers:
        t.start()
    try:
        rc = proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        rc = None
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    if rc is None:
        proc.wait()
    strays = kill_descendants(proc.pid) + kill_rooted(cwd)
    for t in readers:
        t.join(timeout=PIPE_DRAIN_SECONDS)
    out, err = (b"".join(b).decode("utf-8", "replace") for b in bufs)
    return rc, out, err, strays


def run_worker(argv: list, cwd: Path, timeout: int) -> tuple:
    """(rc, stdout, stderr, strays); rc 124 on timeout."""
    rc, out, err, strays = run_group(argv, cwd, timeout)
    return (124 if rc is None else rc), out, err, strays


def run_oracle(oracle: Path, tree: Path, result_file: Path, timeout: int) -> tuple:
    """(rc, output); rc is None on timeout."""
    rc, out, err, _ = run_group(["bash", str(oracle), str(tree), str(result_file)], tree, timeout)
    return rc, out + err + ("oracle timed out\n" if rc is None else "")


def oracle_ok(rc) -> bool:
    """False when the oracle could not run: timeout, exit >= 125, or a signal."""
    return rc is not None and 0 <= rc < ORACLE_ERROR_MIN_RC


def positive_int(text: str) -> int:
    n = int(text)
    if n < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return n


def write_receipt(out_dir: Path, payload: dict) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    receipt = out_dir / "skill-ab-receipt.json"
    fd, tmp = tempfile.mkstemp(dir=str(out_dir), prefix=".skill-ab-receipt.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        os.replace(tmp, receipt)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return receipt


# ---------------------------------------------------------------- main

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--skill", required=True,
                    help="skill name in <project>/.claude/skills/, or a path to a skill directory")
    ap.add_argument("--tasks", required=True, type=Path)
    ap.add_argument("--project", default=".", type=Path)
    ap.add_argument("--n", type=positive_int, default=1, help="runs per arm per task (default 1)")
    ap.add_argument("--control", action="store_true", help="add the length-matched control arm")
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--max-turns", type=positive_int, default=20)
    ap.add_argument("--timeout", type=positive_int, default=900, help="seconds per worker run")
    ap.add_argument("--oracle-timeout", type=positive_int, default=120)
    ap.add_argument("--work-root", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None, help="receipt directory")
    ap.add_argument("--claude", default="claude", help="claude CLI to invoke")
    ap.add_argument("--dry-run", action="store_true", help="check preconditions and print the plan")
    args = ap.parse_args(argv)

    try:
        claude = shutil.which(args.claude)
        if not claude:
            raise Refusal(f"`{args.claude}` CLI not found: the with/without mode is Claude Code only")
        project = args.project.resolve()
        src = Path(args.skill)
        if not (src / "SKILL.md").is_file():
            src = project / ".claude" / "skills" / args.skill
        if not (src / "SKILL.md").is_file():
            raise Refusal(f"no SKILL.md for {args.skill!r} (looked in {src})")
        src = src.resolve()
        skill = src.name
        src_rel = src.relative_to(project) if project in src.parents else None
        if not (PROC / "self" / "cwd").exists():
            raise Refusal(f"/proc is not available (looked at {PROC}): it is needed to find and "
                          "stop worker children that leave the process group (Linux only)")
        set_subreaper()
        files = tree_files(project)
        removals = plan_removals(project, files, skill, src, src_rel)
        check_no_leftover_copy(project, files, removals, src)
        tasks_dir = args.tasks.resolve()
        if tasks_dir == project or project in tasks_dir.parents:
            raise Refusal(f"tasks dir {tasks_dir} is inside the project, so every run tree would "
                          "hold its oracles; move it outside the project")
        tasks = load_tasks(tasks_dir)
        arms = list(ARMS) + ([CONTROL_ARM] if args.control else [])
        if args.control:
            control_skill_md((src / "SKILL.md").read_text(encoding="utf-8"))
        # check before creating anything; mkdtemp's dir has the same parents
        work_root = args.work_root or Path(tempfile.gettempdir()) / "skill-ab-check"
        check_work_root(work_root, project)
        if args.work_root and work_root.exists() and any(work_root.iterdir()):
            raise Refusal(f"work root {work_root} is not empty (an earlier run?); "
                          "pass a new --work-root")
    except Refusal as e:
        print(f"skill-ab: refused: {e}", file=sys.stderr)
        return 2

    plan = [(t, arm, i) for t in tasks for i in range(args.n) for arm in arms]
    print(f"skill-ab: {len(plan)} run(s) = {len(tasks)} task(s) x {len(arms)} arm(s) x N={args.n}; "
          f"{args.model}/{args.effort}, max-turns {args.max_turns}; "
          f"work root {work_root if args.work_root else '(new temp dir)'}")
    if args.dry_run:
        print("argv:", " ".join(worker_argv(claude, args, "<prompt>")))
        return 0
    if args.work_root:
        work_root.mkdir(parents=True, exist_ok=True)
    else:
        work_root = Path(tempfile.mkdtemp(prefix="skill-ab-"))

    runs, consecutive_unavailable, aborted = [], 0, False
    for t, arm, i in plan:
        run_dir = work_root / f"{t['id']}-{arm}-{i}"
        tree = run_dir / "repo"
        run_dir.mkdir(parents=True)
        build_run_tree(project, tree, arm, skill, src, removals)
        started = time.time()
        rc, out, err, strays = run_worker(worker_argv(claude, args, t["prompt"]), tree, args.timeout)
        (run_dir / "stream.jsonl").write_text(out, encoding="utf-8")
        (run_dir / "stderr.txt").write_text(err, encoding="utf-8")
        facts = parse_stream(out, skill)
        status = classify(arm, facts, rc)
        if status == "valid" and strays:
            status = "stray-process"  # something kept running in the tree after the worker
        result_file = run_dir / "result.txt"
        result_file.write_text(facts["result_text"], encoding="utf-8")
        oracle_rc, passed = None, False
        if status == "valid":
            oracle_rc, oracle_out = run_oracle(t["oracle"], tree, result_file, args.oracle_timeout)
            (run_dir / "oracle.txt").write_text(oracle_out, encoding="utf-8")
            if oracle_ok(oracle_rc):
                passed = oracle_rc == 0
            else:
                status = "oracle-error"
        run = {"task": t["id"], "arm": arm, "i": i, "rc": rc, "status": status, "passed": passed,
               "oracle_rc": oracle_rc, "strays": strays, "seconds": round(time.time() - started, 1),
               **{k: facts[k] for k in ("invocations", "skill_loaded", "result_subtype",
                                        "terminal_reason", "models")}}
        runs.append(run)
        print(f"  {t['id']} {arm:<8} #{i}: {status}, invoked={run['invocations']}, "
              f"oracle={'pass' if passed else 'fail' if status == 'valid' else '-'} ({run['seconds']}s)")
        consecutive_unavailable = consecutive_unavailable + 1 if status == "unavailable" else 0
        if consecutive_unavailable >= UNAVAILABLE_MAX_CONSECUTIVE:
            print(f"skill-ab: refused: {UNAVAILABLE_MAX_CONSECUTIVE} consecutive runs unavailable "
                  f"(account limit or CLI failure); see {run_dir}/stream.jsonl and stderr.txt",
                  file=sys.stderr)
            aborted = True
            break

    summary = summarize(runs, arms)
    models_used = sorted({m for r in runs for m in r["models"]})
    meta = {"skill": skill, "tasks": [t["id"] for t in tasks], "n": args.n, "model": args.model,
            "effort": args.effort, "max_turns": args.max_turns, "models_used": models_used,
            "aborted": aborted, "runs_planned": len(plan),
            "cli": subprocess.run([claude, "--version"], capture_output=True, text=True).stdout.strip()}
    print()
    print(render(summary, meta))
    receipt = write_receipt(args.out or work_root, {"meta": meta, "summary": summary, "runs": runs})
    print(f"\nreceipt: {receipt}" + ("  (partial: aborted)" if aborted else ""))
    if aborted:
        return 2
    return 1 if any(r["status"] != "valid" for r in runs) else 0


if __name__ == "__main__":
    sys.exit(main())
