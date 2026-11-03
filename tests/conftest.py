"""Shared helpers: a fake `claude` CLI that replays captured streams, and a fixture project.

No test makes a real model call.
"""
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "tests" / "fixtures"
sys.path.insert(0, str(ROOT / "scripts"))

# Modes (env FAKE_MODE):
#   replay   the captured with/without stream, chosen by whether the run tree has the
#            skill; writes hello.txt when the skill body holds the token. FAKE_TEXT adds an
#            assistant text block; FAKE_RESULT (JSON) replaces the result event.
#   hang     prints init plus half of a multibyte character, starts a grandchild that
#            writes $FAKE_MARK after 2 s, then sleeps (for the timeout path)
#   background  the replay stream, then starts the same grandchild and exits 0
#   escape   the replay stream, then a grandchild that setsid's, chdir's to /, closes
#            its descriptors, sleeps 2 s and writes <run tree>/late.txt by absolute path
#   holdpipe the replay stream, then a setsid grandchild that keeps stdout open 20 s
# The grandchild is started in a new session (start_new_session=True), as Claude Code's
# Bash tool does (its shell provider spawns with detached: true, i.e. setsid), so it
# leaves the worker's process group.
#   limit    prints init plus a session-limit result and exits 1
# FAKE_STDERR is written to stderr in every mode.
FAKE_CLAUDE = r'''#!/usr/bin/env python3
import json, os, subprocess, sys, time
from pathlib import Path
if sys.argv[1:] == ["--version"]:
    print("0.0.0 (fake)"); sys.exit(0)
assert "--setting-sources" in sys.argv and "project,local" in sys.argv
fix = Path(os.environ["FIX_STREAM"])
mode = os.environ.get("FAKE_MODE", "replay")
sys.stderr.write(os.environ.get("FAKE_STDERR", ""))
skill_md = Path(".claude/skills/ab-fixture/SKILL.md")
has = skill_md.is_file()
lines = [json.loads(l) for l in (fix / ("with.jsonl" if has else "without.jsonl")).read_text().splitlines()]
init = lines[0]
init["skills"] = [("ab-fixture" if s == "sf-probe" else s) for s in init["skills"]]
if mode == "hang":
    sys.stdout.buffer.write((json.dumps(init) + "\n").encode() + "한".encode()[:2])
    sys.stdout.flush()
    subprocess.Popen(["sh", "-c", "sleep 2; echo late > \"$FAKE_MARK\""], start_new_session=True)
    time.sleep(60)
if mode == "limit":
    print(json.dumps(init))
    print(json.dumps({"type": "result", "subtype": "success", "is_error": True,
                      "result": "You've hit your session limit", "terminal_reason": "completed"}))
    sys.exit(1)
out = [init]
for e in lines[1:]:
    if e.get("type") == "assistant":
        for b in e["message"]["content"]:
            if b.get("name") == "Skill":
                b["input"]["skill"] = "ab-fixture"
    out.append(e)
if os.environ.get("FAKE_TEXT"):
    out.insert(1, {"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "text", "text": os.environ["FAKE_TEXT"]}]}})
if os.environ.get("FAKE_RESULT"):
    out[-1] = json.loads(os.environ["FAKE_RESULT"])
for e in out:
    print(json.dumps(e))
if has and "SF-FIXTURE-7" in skill_md.read_text():
    Path("hello.txt").write_text("SF-FIXTURE-7\n")
if mode == "escape":
    sys.stdout.flush()
    code = ("import os, time, sys; os.chdir('/'); time.sleep(2); "
            "open(sys.argv[1], 'w').write('late')")
    child = subprocess.Popen([sys.executable, "-c", code, str(Path.cwd() / "late.txt")],
                             start_new_session=True, stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
    for _ in range(200):  # exit only once the child has left the tree
        try:
            if os.readlink(f"/proc/{child.pid}/cwd") == "/":
                break
        except OSError:
            pass
        time.sleep(0.01)
if mode == "holdpipe":
    sys.stdout.flush()
    subprocess.Popen(["sleep", "20"], start_new_session=True)
if mode == "background":
    sys.stdout.flush()
    subprocess.Popen(["sh", "-c", "sleep 2; echo late > \"$FAKE_MARK\""], start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
'''


@pytest.fixture
def fake_cli(tmp_path, monkeypatch):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    fake = bindir / "claude"
    fake.write_text(FAKE_CLAUDE)
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("FIX_STREAM", str(FIX / "stream"))
    return fake


def git(*args, cwd):
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True).stdout


@pytest.fixture
def project(tmp_path):
    """A git project with the fixture skill committed at .claude/skills/ab-fixture/."""
    proj = tmp_path / "proj"
    skill = proj / ".claude" / "skills" / "ab-fixture"
    (skill / "references").mkdir(parents=True)
    skill.joinpath("SKILL.md").write_text(
        (FIX / "ab" / "skill" / "ab-fixture" / "SKILL.md").read_text(encoding="utf-8"))
    skill.joinpath("references", "guide.md").write_text("REAL-CONTENT-TOKEN SF-FIXTURE-7\n")
    (proj / "README").write_text("x\n")
    git("init", "-q", cwd=proj)
    git("add", "-A", cwd=proj)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init", cwd=proj)
    return proj
