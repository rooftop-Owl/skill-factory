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
skill, so `git log -p`, `git diff` or `git checkout` cannot recover it.

Adherence (was the skill invoked) and effect (oracle pass rate) are reported
separately: an outcome alone cannot say whether a skill failed because it was not
followed or because following it did not help.

Isolation: every run passes `--setting-sources project,local`, which drops
~/.claude/skills and installed plugins, so the clone's own .claude/skills is the
only non-builtin skill source. Each run's stream-json `system/init` event lists the
loaded skills; a run whose arm disagrees with that list is excluded as invalid.

Not a sandbox: the worker runs as you with --dangerously-skip-permissions and full
access to your files, network and credentials. The run tree is only where it
starts; nothing stops it reading or changing anything else you can, including the
tasks directory and the original project. The tasks directory is refused if it is
inside the project (it would be copied into every run tree), but outside it the
oracle is protected only by the worker not being told its path.

Task layout: <tasks>/<id>/prompt.txt and <tasks>/<id>/oracle.sh. The oracle runs
after the worker (and every process it started) has been stopped, as
`bash oracle.sh <run_tree> <result_text_file>`. Exit 0 is a pass and 1-124 a fail;
a timeout, exit >= 125 (126/127: cannot execute / not found) or a signal makes the
run invalid (oracle-error), never a fail.

Exit codes: 0 report written; 1 report written but some runs were invalid;
2 refused (precondition unmet, CLI absent, 3 consecutive runs unavailable; a
receipt with the completed runs is still written in the last case).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
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


def copy_working_tree(project: Path, dest: Path) -> None:
    """Copy the working tree without .git (git: tracked + untracked-not-ignored files)."""
    if not is_git_project(project):
        shutil.copytree(project, dest, symlinks=True,
                        ignore=lambda d, names: [".git"] if Path(d) == project else [])
        return
    listed = subprocess.run(["git", "-C", str(project), "ls-files", "-z", "--cached", "--others",
                             "--exclude-standard"], capture_output=True, check=True).stdout
    dest.mkdir(parents=True)
    for rel in sorted(set(filter(None, listed.decode("utf-8", "surrogateescape").split("\0")))):
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


def init_run_repo(tree: Path) -> None:
    """A fresh repository with one commit of the arm's tree: no remote, no skill history."""
    g = ["git", "-C", str(tree), "-c", "user.name=skill-ab", "-c", "user.email=skill-ab@localhost",
         "-c", "commit.gpgsign=false"]
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


def prepare_arm(tree: Path, arm: str, skill: str, skill_src: Path, src_rel: Path | None) -> None:
    """Apply the arm. `src_rel` is the skill's own path inside the project, if any:
    it is removed too, so the without/control tree holds no second copy."""
    target = tree / ".claude" / "skills" / skill
    remove_path(target)
    if src_rel is not None:
        remove_path(tree / src_rel)
    if arm == "without":
        return
    shutil.copytree(skill_src, target)
    if arm == CONTROL_ARM:
        for f in sorted(p for p in target.rglob("*") if p.is_file()):
            if f == target / "SKILL.md":
                f.write_text(control_skill_md(f.read_text(encoding="utf-8")), encoding="utf-8")
            else:
                f.write_bytes(filler(f.stat().st_size))


def build_run_tree(project: Path, dest: Path, arm: str, skill: str, skill_src: Path,
                   src_rel: Path | None) -> None:
    copy_working_tree(project, dest)
    prepare_arm(dest, arm, skill, skill_src, src_rel)
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


def run_worker(argv: list, cwd: Path, timeout: int) -> tuple:
    """Run the worker in its own process group; kill the whole group when it ends or
    times out, so no child it started can change the tree while the oracle reads it."""
    proc = subprocess.Popen(argv, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            start_new_session=True)
    try:
        out, err = proc.communicate(timeout=timeout)
        rc = proc.returncode
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        out, err = proc.communicate()
        rc = 124
    try:
        os.killpg(proc.pid, signal.SIGKILL)  # children left running after a normal exit
    except (ProcessLookupError, PermissionError):
        pass
    return rc, out.decode("utf-8", "replace"), err.decode("utf-8", "replace")


def run_oracle(oracle: Path, tree: Path, result_file: Path, timeout: int) -> tuple:
    """(rc, output); rc is None on timeout."""
    try:
        cp = subprocess.run(["bash", str(oracle), str(tree), str(result_file)],
                            cwd=str(tree), capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, "oracle timed out\n"
    return cp.returncode, (cp.stdout + cp.stderr).decode("utf-8", "replace")


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
        tasks_dir = args.tasks.resolve()
        if tasks_dir == project or project in tasks_dir.parents:
            raise Refusal(f"tasks dir {tasks_dir} is inside the project, so every run tree would "
                          "hold its oracles; move it outside the project")
        tasks = load_tasks(tasks_dir)
        arms = list(ARMS) + ([CONTROL_ARM] if args.control else [])
        if args.control:
            control_skill_md((src / "SKILL.md").read_text(encoding="utf-8"))
        # check before creating anything; mkdtemp's dir has the same parents
        work_root = args.work_root or Path(tempfile.gettempdir()) / "skill-ab-<new>"
        check_work_root(work_root, project)
        if args.work_root and work_root.exists() and any(work_root.iterdir()):
            raise Refusal(f"work root {work_root} is not empty (an earlier run?); "
                          "pass a new --work-root")
    except Refusal as e:
        print(f"skill-ab: refused: {e}", file=sys.stderr)
        return 2

    plan = [(t, arm, i) for t in tasks for i in range(args.n) for arm in arms]
    print(f"skill-ab: {len(plan)} run(s) = {len(tasks)} task(s) x {len(arms)} arm(s) x N={args.n}; "
          f"{args.model}/{args.effort}, max-turns {args.max_turns}; work root {work_root}")
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
        build_run_tree(project, tree, arm, skill, src, src_rel)
        started = time.time()
        rc, out, err = run_worker(worker_argv(claude, args, t["prompt"]), tree, args.timeout)
        (run_dir / "stream.jsonl").write_text(out, encoding="utf-8")
        (run_dir / "stderr.txt").write_text(err, encoding="utf-8")
        facts = parse_stream(out, skill)
        status = classify(arm, facts, rc)
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
               "oracle_rc": oracle_rc, "seconds": round(time.time() - started, 1),
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
