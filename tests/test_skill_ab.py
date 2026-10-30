"""Tests for scripts/skill_ab.py and scripts/skill_usage.py.

Stream fixtures (tests/fixtures/stream/) are real `claude -p --output-format
stream-json --setting-sources project,local` captures from Claude Code 2.1.314,
reduced to the keys the parser reads. Transcript lines (tests/fixtures/transcripts/)
are real ~/.claude/projects lines with paths and arguments removed.
"""
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import skill_ab  # noqa: E402
import skill_usage  # noqa: E402

FIX = ROOT / "tests" / "fixtures"


def stream(name):
    return (FIX / "stream" / f"{name}.jsonl").read_text(encoding="utf-8")


# ---------------------------------------------------------------- stream parsing

def test_parse_with_arm_reads_init_skills_and_skill_tool_use():
    f = skill_ab.parse_stream(stream("with"), "sf-probe")
    assert f["init_seen"] and f["skill_loaded"]
    assert f["invocations"] == 1
    assert f["result_subtype"] == "error_max_turns"
    assert f["models"] == ["claude-sonnet-5-5"]


def test_parse_without_arm_skill_absent_from_init():
    f = skill_ab.parse_stream(stream("without"), "sf-probe")
    assert f["init_seen"] and not f["skill_loaded"]
    assert f["invocations"] == 0
    assert f["result_text"] == "ok"


def test_setting_sources_dropped_user_and_plugin_skills_in_capture():
    """The isolation claim the runner rests on: under --setting-sources project,local
    the only non-builtin skill in init is the clone's own, and the without arm has
    one fewer skill than the with arm (that skill)."""
    init = [json.loads(l) for l in stream("with").splitlines()][0]["skills"]
    init_c = [json.loads(l) for l in stream("without").splitlines()][0]["skills"]
    assert set(init) - set(init_c) == {"sf-probe"}
    assert set(init_c) <= set(init)


def test_namespaced_skill_tool_use_counts_on_bare_name():
    line = json.dumps({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Skill", "input": {"skill": "myplug:sf-probe"}}]}})
    assert skill_ab.parse_stream(stream("with") + line + "\n", "sf-probe")["invocations"] == 2


@pytest.mark.parametrize("arm,fixture,rc,expected", [
    ("with", "with", 1, "valid"),          # error_max_turns exits 1 but is a real run
    ("without", "without", 0, "valid"),
    ("without", "with", 0, "contaminated"),
    ("with", "without", 0, "not-loaded"),
    ("control", "without", 0, "not-loaded"),
])
def test_classify(arm, fixture, rc, expected):
    raw = stream(fixture)
    assert skill_ab.classify(arm, skill_ab.parse_stream(raw, "sf-probe"), rc, raw) == expected


def test_classify_unavailable_on_session_limit_and_on_no_init():
    raw = json.dumps({"type": "result", "subtype": "success", "is_error": True,
                      "result": "You've hit your session limit"})
    f = skill_ab.parse_stream(raw, "x")
    assert skill_ab.classify("with", f, 1, raw) == "unavailable"
    lim = stream("without").splitlines()[0] + "\n" + raw
    assert skill_ab.classify("without", skill_ab.parse_stream(lim, "x"), 1, lim) == "unavailable"


# ---------------------------------------------------------------- statistics

@pytest.mark.parametrize("table,expected", [
    ((8, 2, 1, 9), 0.005477),   # scipy.stats.fisher_exact([[8,2],[1,9]]).pvalue
    ((1, 0, 0, 1), 1.0),
    ((5, 0, 0, 5), 0.007937),   # 2 / C(10,5)
    ((3, 1, 1, 3), 0.485714),
    ((0, 0, 0, 0), 1.0),
])
def test_fisher_exact_matches_reference_values(table, expected):
    assert skill_ab.fisher_exact(*table) == pytest.approx(expected, abs=1e-6)


def _run(arm, status="valid", passed=False, inv=0):
    return {"arm": arm, "status": status, "passed": passed, "invocations": inv}


def test_summarize_separates_adherence_from_effect_and_labels_smoke():
    runs = ([_run("with", passed=True, inv=1)] * 3 + [_run("with", inv=0)]
            + [_run("without")] * 3 + [_run("without", passed=True)]
            + [_run("without", status="contaminated", passed=True)])
    s = skill_ab.summarize(runs, ["with", "without"])
    w, o = s["arms"]["with"], s["arms"]["without"]
    assert (w["n_valid"], w["invoked"], w["passed"], w["passed_when_invoked"]) == (4, 3, 3, 3)
    assert (o["n_valid"], o["n_invalid"], o["passed"]) == (4, 1, 1)   # invalid run excluded
    assert s["comparisons"]["with_vs_without"]["delta"] == pytest.approx(0.5)
    assert s["comparisons"]["with_vs_without"]["fisher_p"] == pytest.approx(
        skill_ab.fisher_exact(3, 1, 1, 3))
    assert s["label"] == "smoke, not evidence"


def test_summarize_label_measured_at_smoke_threshold():
    runs = [_run(a) for a in ("with", "without") for _ in range(skill_ab.SMOKE_N)]
    assert skill_ab.summarize(runs, ["with", "without"])["label"] == "measured"


# ---------------------------------------------------------------- arms and workspace

def test_control_keeps_frontmatter_and_matches_body_bytes():
    text = (FIX / "ab" / "skill" / "ab-fixture" / "SKILL.md").read_text(encoding="utf-8")
    ctl = skill_ab.control_skill_md(text)
    head = text[: text.index("\n---\n", 4) + 5]
    assert ctl.startswith(head)
    assert len(ctl.encode()) == len(text.encode())
    assert "SF-FIXTURE-7" not in ctl


def test_check_work_root_refuses_parent_claude_md(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("x")
    (tmp_path / "w").mkdir()
    with pytest.raises(skill_ab.Refusal):
        skill_ab.check_work_root(tmp_path / "w", tmp_path / "elsewhere")


def test_check_work_root_refuses_inside_project(tmp_path):
    (tmp_path / "proj" / "w").mkdir(parents=True)
    with pytest.raises(skill_ab.Refusal):
        skill_ab.check_work_root(tmp_path / "proj" / "w", (tmp_path / "proj").resolve())


def test_refuses_when_cli_absent(tmp_path, capsys):
    rc = skill_ab.main(["--skill", str(FIX / "ab" / "skill" / "ab-fixture"),
                        "--tasks", str(FIX / "ab" / "tasks"), "--project", str(tmp_path),
                        "--claude", "no-such-claude-cli"])
    assert rc == 2
    assert "Claude Code only" in capsys.readouterr().err


FAKE_CLAUDE = r'''#!/usr/bin/env python3
"""Replays the captured streams: with-arm if the clone has the skill dir."""
import json, os, sys
from pathlib import Path
if sys.argv[1:] == ["--version"]:
    print("0.0.0 (fake)"); sys.exit(0)
assert "--setting-sources" in sys.argv and "project,local" in sys.argv
fix = Path(os.environ["FIX_STREAM"])
has = Path(".claude/skills/ab-fixture/SKILL.md").is_file()
lines = (fix / ("with.jsonl" if has else "without.jsonl")).read_text().splitlines()
for l in lines:
    e = json.loads(l)
    if e.get("subtype") == "init":
        e["skills"] = [("ab-fixture" if s == "sf-probe" else s) for s in e["skills"]]
    if e.get("type") == "assistant":
        for b in e["message"]["content"]:
            if b.get("name") == "Skill":
                b["input"]["skill"] = "ab-fixture"
    print(json.dumps(e))
if has and "SF-FIXTURE-7" in Path(".claude/skills/ab-fixture/SKILL.md").read_text():
    Path("hello.txt").write_text("SF-FIXTURE-7\n")
'''


def test_end_to_end_with_fake_cli(tmp_path, monkeypatch, capsys):
    """Clone per run, arm preparation, oracle after exit, report: no model spend."""
    proj = tmp_path / "proj"
    proj.mkdir()
    subprocess.run(["git", "init", "-q", str(proj)], check=True)
    (proj / "README").write_text("x")
    subprocess.run(["git", "-C", str(proj), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(proj), "-c", "user.name=t", "-c", "user.email=t@t",
                    "commit", "-qm", "init"], check=True)
    bindir = tmp_path / "bin"
    bindir.mkdir()
    fake = bindir / "claude"
    fake.write_text(FAKE_CLAUDE)
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("FIX_STREAM", str(FIX / "stream"))
    work = tmp_path / "work"
    rc = skill_ab.main(["--skill", str(FIX / "ab" / "skill" / "ab-fixture"),
                        "--tasks", str(FIX / "ab" / "tasks"), "--project", str(proj),
                        "--claude", str(fake), "--control", "--work-root", str(work)])
    out = capsys.readouterr().out
    receipt = json.loads((work / "skill-ab-receipt.json").read_text())
    arms = receipt["summary"]["arms"]
    assert rc == 0, out
    assert (arms["with"]["passed"], arms["with"]["invoked"]) == (1, 1)
    assert (arms["without"]["passed"], arms["without"]["invoked"]) == (0, 0)
    # control: skill loaded and invoked, filler body has no token -> oracle fails
    assert (arms["control"]["passed"], arms["control"]["invoked"]) == (0, 1)
    assert "smoke, not evidence" in out
    assert not (proj / "hello.txt").exists()   # worker ran in the clone, not the project


# ---------------------------------------------------------------- skill_usage

def _lines():
    return (FIX / "transcripts" / "lines.jsonl").read_text(encoding="utf-8").splitlines()


def test_usage_line_parsing_on_real_shapes():
    user_cmd, sys_cmd, skill = _lines()
    assert skill_usage.invocations_in_line(user_cmd) == ["clear"]
    assert skill_usage.invocations_in_line(sys_cmd) == ["rename"]
    assert skill_usage.invocations_in_line(skill) == ["merge-reviewed-pr"]


def test_project_slug_matches_claude_code_rule():
    assert (skill_usage.project_slug("/home/doyoon/.astraeus/harness/astraea")
            == "-home-doyoon--astraeus-harness-astraea")


def test_usage_scan_counts_worktrees_and_subagents_and_drops_builtins(tmp_path):
    user_cmd, sys_cmd, skill = _lines()
    proj = tmp_path / "proj"
    for s in ("alpha", "beta", "gamma", "delta", "unused"):
        (proj / ".claude" / "skills" / s).mkdir(parents=True)
        (proj / ".claude" / "skills" / s / "SKILL.md").write_text("---\nname: %s\n---\n" % s)
    root = tmp_path / "projects"
    slug = skill_usage.project_slug(str(proj))
    main = root / slug
    (main / "sess1" / "subagents").mkdir(parents=True)
    (main / "s1.jsonl").write_text("\n".join([
        user_cmd,                                             # /clear: built-in, ignored
        skill.replace("merge-reviewed-pr", "alpha"),
        sys_cmd.replace("/rename", "/myplug:beta"),           # namespaced -> beta
    ]) + "\n")
    (main / "sess1" / "subagents" / "agent-1.jsonl").write_text(
        skill.replace("merge-reviewed-pr", "alpha") + "\n")
    wt = root / (slug + "--worktrees-feat-x")
    wt.mkdir()
    (wt / "s2.jsonl").write_text(user_cmd.replace("/clear", "/gamma") + "\n")
    other = root / (slug + "-other")                          # not a worktree sibling
    other.mkdir()
    (other / "s3.jsonl").write_text(skill.replace("merge-reviewed-pr", "delta") + "\n")

    dirs = skill_usage.transcript_dirs(root, str(proj))
    res = skill_usage.scan(dirs, skill_usage.project_skills(proj))
    assert res["counts"] == {"alpha": 2, "beta": 1, "gamma": 1, "delta": 0, "unused": 0}
    assert res["transcripts"] == 3
    assert (res["first"], res["last"]) == ("2026-09-19", "2026-09-29")
    text = skill_usage.render(res)
    assert text.startswith("never invoked: 2 of 5 project skills across 3 transcripts, "
                           "2026-09-19–2026-09-29")
    assert "delta, unused" in text


def test_usage_exit_2_without_transcripts(tmp_path):
    assert skill_usage.main(["--project", str(tmp_path), "--projects-root", str(tmp_path / "none")]) == 2
