#!/usr/bin/env python3
"""Count invocations of a project's skills across its Claude Code session transcripts.

Reads ~/.claude/projects/<slug>/ plus every sibling <slug>--worktrees-* directory,
recursing into nested subagent transcripts (<session>/subagents/*.jsonl). An
invocation is a `Skill` tool_use whose input.skill names the skill, or a slash
command `<command-name>/<skill></command-name>` recorded for it. Plugin-namespaced
names (`plugin:skill`) are compared on the bare skill name.

The skill set is the project's .claude/skills/*/SKILL.md only: user-level and
plugin skills are not counted. Claude Code deletes transcripts after
cleanupPeriodDays (default 30), so "never invoked" means never invoked inside the
printed window.

Exit codes: 0 report printed; 2 no transcript directory for this project.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

COMMAND_RE = re.compile(r"<command-name>/?([^<\s]+)</command-name>")
DATE_RE = re.compile(r'"timestamp":"(\d{4}-\d{2}-\d{2})')


def norm_skill(name: str) -> str:
    return name.strip().lstrip("/").split(":")[-1]


def project_slug(cwd: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "-", cwd)


def transcript_dirs(projects_root: Path, cwd: str) -> list:
    slug = project_slug(cwd)
    dirs = [projects_root / slug] if (projects_root / slug).is_dir() else []
    dirs += sorted(p for p in projects_root.glob(slug + "--worktrees-*") if p.is_dir())
    return dirs


def project_skills(project: Path) -> list:
    root = project / ".claude" / "skills"
    return sorted(p.parent.name for p in root.glob("*/SKILL.md")) if root.is_dir() else []


def invocations_in_line(line: str) -> list:
    """Skill names invoked by one transcript line (raw, before normalisation)."""
    if '"Skill"' not in line and "<command-name>" not in line:
        return []
    try:
        ev = json.loads(line)
    except ValueError:
        return []
    found = []
    msg = ev.get("message") or {}
    content = msg.get("content")
    if ev.get("type") == "assistant" and isinstance(content, list):
        for block in content:
            if (isinstance(block, dict) and block.get("type") == "tool_use"
                    and block.get("name") == "Skill"):
                found.append(str((block.get("input") or {}).get("skill", "")))
    elif ev.get("type") in ("user", "system"):
        text = content if isinstance(content, str) else ev.get("content")
        if isinstance(text, str):
            found += COMMAND_RE.findall(text)
    return found


def scan(dirs: list, skills: list) -> dict:
    counts = {s: 0 for s in skills}
    files, dates = 0, []
    for d in dirs:
        for f in sorted(d.rglob("*.jsonl")):
            files += 1
            with f.open(encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    m = DATE_RE.search(line)
                    if m:
                        dates.append(m.group(1))
                    for name in invocations_in_line(line):
                        n = norm_skill(name)
                        if n in counts:  # drops built-ins such as /model, /clear
                            counts[n] += 1
    return {"counts": counts, "transcripts": files,
            "first": min(dates) if dates else None, "last": max(dates) if dates else None}


def render(res: dict) -> str:
    counts = res["counts"]
    never = sorted(s for s, c in counts.items() if c == 0)
    window = f"{res['first']}–{res['last']}" if res["first"] else "no dated entries"
    lines = [f"never invoked: {len(never)} of {len(counts)} project skills across "
             f"{res['transcripts']} transcripts, {window}"]
    if never:
        lines.append("  " + ", ".join(never))
    used = sorted(((c, s) for s, c in counts.items() if c), reverse=True)
    if used:
        lines.append("invoked: " + ", ".join(f"{s} ({c})" for c, s in used))
    lines.append("(M counts project .claude/skills/ only; Claude Code deletes transcripts after cleanupPeriodDays, default 30)")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--project", default=".", type=Path)
    ap.add_argument("--projects-root", default=Path.home() / ".claude" / "projects", type=Path)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    project = args.project.resolve()
    dirs = transcript_dirs(args.projects_root, str(project))
    if not dirs:
        print(f"skill-usage: no transcripts for {project} under {args.projects_root} "
              f"(expected {project_slug(str(project))}); Claude Code only", file=sys.stderr)
        return 2
    res = scan(dirs, project_skills(project))
    print(json.dumps(res, indent=2) if args.json else render(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
