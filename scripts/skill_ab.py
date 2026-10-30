#!/usr/bin/env python3
"""With/without-skill eval for Claude Code (headless `claude -p`).

Runs each task N times per arm in a fresh clone of the target project and scores
each run with that task's deterministic oracle. Arms:

  with     the skill present at .claude/skills/<name>/
  without  .claude/skills/<name>/ removed; nothing else differs
  control  (--control) same name + description, body replaced by filler of equal
           byte length: separates "the skill's content helped" from "any skill-shaped
           text in context helped"

Adherence (was the skill invoked) and effect (oracle pass rate) are reported
separately: an outcome alone cannot say whether a skill failed because it was not
followed or because following it did not help.

Isolation: every run passes `--setting-sources project,local`, which drops
~/.claude/skills and installed plugins, so the clone's own .claude/skills is the
only non-builtin skill source. Each run's stream-json `system/init` event lists the
loaded skills; a run whose arm disagrees with that list is excluded as invalid.

Task layout: <tasks>/<id>/prompt.txt and <tasks>/<id>/oracle.sh. The oracle runs
after the worker exits as `bash oracle.sh <clone_dir> <result_text_file>`; exit 0 is
a pass. Oracles live outside the clone, so the worker cannot read or edit them.

Exit codes: 0 report written; 1 report written but some runs were invalid;
2 refused (precondition unmet, CLI absent, account unavailable).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ARMS = ("with", "without")
CONTROL_ARM = "control"
SMOKE_N = 10
UNAVAILABLE_MAX_CONSECUTIVE = 3
UNAVAILABLE_MARKERS = ("hit your session limit", "usage limit", "rate limit")
FILLER_LINE = "This line is filler text of matched length and carries no instructions.\n"
PARENT_CONTEXT_FILES = ("CLAUDE.md", "CLAUDE.local.md", ".claude/skills",
                        ".claude/settings.json", ".claude/settings.local.json")


class Refusal(Exception):
    pass


def norm_skill(name: str) -> str:
    """Plugin skills are namespaced (`plugin:skill`); compare on the bare name."""
    return name.strip().lstrip("/").split(":")[-1]


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
        "result_text": (result or {}).get("result") or "",
        "models": models,
    }


def classify(arm: str, facts: dict, rc: int, raw: str) -> str:
    """valid | unavailable | contaminated | not-loaded."""
    low = raw.lower()
    # rc 124 = timed out: the worker started, so the oracle still decides the run.
    if not facts["init_seen"] or (rc not in (0, 124) and not facts["result_seen"]):
        return "unavailable"
    if facts["is_error"] and any(m in low for m in UNAVAILABLE_MARKERS):
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
        f"Effect measured on {'/'.join(meta['models_used']) or meta['model']}/{meta['effort']}"
        f"  [{summary['label']}]",
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
    """Refuse a work root that would leak context into the clone.

    CLAUDE.md is discovered by walking up from cwd, so a parent of the clone that
    holds one (or a skills/settings dir) would be read by every arm.
    """
    wr = work_root.resolve()
    if wr == project or project in wr.parents:
        raise Refusal(f"work root {wr} is inside the project; use a directory outside it")
    for parent in [wr, *wr.parents]:
        for rel in PARENT_CONTEXT_FILES:
            if (parent / rel).exists():
                raise Refusal(f"{parent / rel} would be discovered by every run; "
                              "choose a --work-root with no Claude context above it")


def make_clone(project: Path, dest: Path) -> None:
    if (project / ".git").exists():
        subprocess.run(["git", "clone", "-q", "--local", "--no-hardlinks", str(project), str(dest)],
                       check=True)
    else:
        shutil.copytree(project, dest, symlinks=True)


def control_skill_md(text: str) -> str:
    """Same frontmatter, body replaced by neutral filler of equal byte length."""
    m = re.match(r"(?s)\A(---\n.*?\n---\n)(.*)\Z", text)
    if not m:
        raise Refusal("SKILL.md has no frontmatter block; cannot build a control")
    head, body = m.group(1), m.group(2)
    size = len(body.encode("utf-8"))
    filler = (FILLER_LINE * (size // len(FILLER_LINE) + 1))[:size]
    return head + filler


def prepare_arm(clone: Path, arm: str, skill: str, skill_src: Path) -> None:
    target = clone / ".claude" / "skills" / skill
    if target.exists() or target.is_symlink():
        if target.is_symlink() or target.is_file():
            target.unlink()
        else:
            shutil.rmtree(target)
    if arm == "without":
        return
    shutil.copytree(skill_src, target)
    if arm == CONTROL_ARM:
        md = target / "SKILL.md"
        md.write_text(control_skill_md(md.read_text(encoding="utf-8")), encoding="utf-8")


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
    # --dangerously-skip-permissions: headless has no one to approve a write; the run
    #   happens in a disposable clone.
    return [claude, "-p", "--verbose", "--output-format", "stream-json",
            "--no-session-persistence", "--setting-sources", "project,local",
            "--dangerously-skip-permissions",
            "--model", args.model, "--effort", args.effort,
            "--max-turns", str(args.max_turns), prompt]


def run_oracle(oracle: Path, clone: Path, result_file: Path, timeout: int) -> bool:
    try:
        cp = subprocess.run(["bash", str(oracle), str(clone), str(result_file)],
                            cwd=str(clone), capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False
    return cp.returncode == 0


# ---------------------------------------------------------------- main

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--skill", required=True,
                    help="skill name in <project>/.claude/skills/, or a path to a skill directory")
    ap.add_argument("--tasks", required=True, type=Path)
    ap.add_argument("--project", default=".", type=Path)
    ap.add_argument("--n", type=int, default=1, help="runs per arm per task (default 1)")
    ap.add_argument("--control", action="store_true", help="add the length-matched control arm")
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--max-turns", type=int, default=20)
    ap.add_argument("--timeout", type=int, default=900, help="seconds per worker run")
    ap.add_argument("--oracle-timeout", type=int, default=120)
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
        tasks = load_tasks(args.tasks.resolve())
        arms = list(ARMS) + ([CONTROL_ARM] if args.control else [])
        if args.control:
            control_skill_md((src / "SKILL.md").read_text(encoding="utf-8"))
        work_root = args.work_root or Path(tempfile.mkdtemp(prefix="skill-ab-"))
        work_root.mkdir(parents=True, exist_ok=True)
        check_work_root(work_root, project)
    except Refusal as e:
        print(f"skill-ab: refused: {e}", file=sys.stderr)
        return 2

    plan = [(t, arm, i) for t in tasks for i in range(args.n) for arm in arms]
    print(f"skill-ab: {len(plan)} run(s) = {len(tasks)} task(s) x {len(arms)} arm(s) x N={args.n}; "
          f"{args.model}/{args.effort}, max-turns {args.max_turns}; work root {work_root}")
    if args.dry_run:
        print("argv:", " ".join(worker_argv(claude, args, "<prompt>")))
        return 0

    runs, consecutive_unavailable = [], 0
    for t, arm, i in plan:
        run_dir = work_root / f"{t['id']}-{arm}-{i}"
        clone = run_dir / "repo"
        run_dir.mkdir(parents=True)
        make_clone(project, clone)
        prepare_arm(clone, arm, skill, src)
        started = time.time()
        try:
            cp = subprocess.run(worker_argv(claude, args, t["prompt"]), cwd=str(clone),
                                capture_output=True, text=True, timeout=args.timeout)
            rc, out, err = cp.returncode, cp.stdout, cp.stderr
        except subprocess.TimeoutExpired as e:
            out = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
            rc, err = 124, ""
        (run_dir / "stream.jsonl").write_text(out, encoding="utf-8")
        facts = parse_stream(out, skill)
        status = classify(arm, facts, rc, out + err)
        result_file = run_dir / "result.txt"
        result_file.write_text(facts["result_text"], encoding="utf-8")
        passed = status == "valid" and run_oracle(t["oracle"], clone, result_file, args.oracle_timeout)
        run = {"task": t["id"], "arm": arm, "i": i, "rc": rc, "status": status, "passed": passed,
               "seconds": round(time.time() - started, 1),
               **{k: facts[k] for k in ("invocations", "skill_loaded", "result_subtype", "models")}}
        runs.append(run)
        print(f"  {t['id']} {arm:<8} #{i}: {status}, invoked={run['invocations']}, "
              f"oracle={'pass' if passed else 'fail'} ({run['seconds']}s)")
        consecutive_unavailable = consecutive_unavailable + 1 if status == "unavailable" else 0
        if consecutive_unavailable >= UNAVAILABLE_MAX_CONSECUTIVE:
            print(f"skill-ab: refused: {UNAVAILABLE_MAX_CONSECUTIVE} consecutive runs unavailable "
                  f"(account limit or CLI failure); see {run_dir}/stream.jsonl", file=sys.stderr)
            return 2

    summary = summarize(runs, arms)
    models_used = sorted({m for r in runs for m in r["models"]})
    meta = {"skill": skill, "tasks": [t["id"] for t in tasks], "n": args.n, "model": args.model,
            "effort": args.effort, "max_turns": args.max_turns, "models_used": models_used,
            "cli": subprocess.run([claude, "--version"], capture_output=True, text=True).stdout.strip()}
    print()
    print(render(summary, meta))
    out_dir = args.out or work_root
    out_dir.mkdir(parents=True, exist_ok=True)
    receipt = out_dir / "skill-ab-receipt.json"
    tmp = receipt.with_suffix(".tmp")
    tmp.write_text(json.dumps({"meta": meta, "summary": summary, "runs": runs}, indent=2), encoding="utf-8")
    os.replace(tmp, receipt)
    print(f"\nreceipt: {receipt}")
    return 1 if any(r["status"] != "valid" for r in runs) else 0


if __name__ == "__main__":
    sys.exit(main())
