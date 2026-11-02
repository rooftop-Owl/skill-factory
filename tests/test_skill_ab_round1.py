"""Failure modes from review round 1 of PR #7, one test per finding.

Each test drives scripts/skill_ab.py or scripts/skill_usage.py through its public
entry point (main) with the fake CLI from conftest.py, so it ran unchanged against
the pre-fix head to record the before result.
"""
import json
import time
from pathlib import Path

import pytest

import skill_ab
import skill_usage
from conftest import FIX, git

TASKS = FIX / "ab" / "tasks"


def run_main(project, work, fake, *extra, tasks=TASKS):
    return skill_ab.main(["--skill", "ab-fixture", "--tasks", str(tasks), "--project", str(project),
                          "--claude", str(fake), "--work-root", str(work), *extra])


def receipt_runs(work):
    return {(r["task"], r["arm"]): r
            for r in json.loads((work / "skill-ab-receipt.json").read_text())["runs"]}


def tree(work, arm, task="greeting"):
    return work / f"{task}-{arm}-0" / "repo"


# 1 [critical] without/control arms could read the skill from the clone's git history
@pytest.mark.parametrize("arm", ["without", "control"])
def test_skill_text_absent_from_run_tree_git_history(project, fake_cli, tmp_path, arm):
    work = tmp_path / "work"
    run_main(project, work, fake_cli, "--control")
    t = tree(work, arm)
    history = git("log", "--all", "-p", cwd=t) + git("show", "HEAD", cwd=t)
    assert "SF-FIXTURE-7" not in history
    assert "REAL-CONTENT-TOKEN" not in history
    assert git("status", "--porcelain", cwd=t) == ""


# 2 [safety] the run tree's origin pointed back at the user's real project
@pytest.mark.parametrize("arm", ["with", "without"])
def test_run_tree_has_no_git_remote(project, fake_cli, tmp_path, arm):
    work = tmp_path / "work"
    run_main(project, work, fake_cli)
    assert git("remote", cwd=tree(work, arm)).strip() == ""


# 3 a task directory inside the project is copied into the run tree with its oracle
def test_refuses_tasks_dir_inside_project(project, fake_cli, tmp_path, capsys):
    inside = project / "evals"
    (inside / "greeting").mkdir(parents=True)
    for f in ("prompt.txt", "oracle.sh"):
        (inside / "greeting" / f).write_text((TASKS / "greeting" / f).read_text())
    rc = run_main(project, tmp_path / "work", fake_cli, tasks=inside)
    assert rc == 2
    assert "inside the project" in capsys.readouterr().err


# 4 a timeout that cuts a multibyte character crashed the whole matrix (UnicodeDecodeError)
# 5 a timeout killed only claude; its children kept writing into the run tree
def test_timeout_mid_multibyte_char_and_orphan_children_killed(project, fake_cli, tmp_path, monkeypatch):
    mark = tmp_path / "late-write"
    monkeypatch.setenv("FAKE_MODE", "hang")
    monkeypatch.setenv("FAKE_MARK", str(mark))
    work = tmp_path / "work"
    rc = run_main(project, work, fake_cli, "--timeout", "1")
    runs = receipt_runs(work)
    assert {r["rc"] for r in runs.values()} == {124}
    assert all(r["status"] == "valid" for r in runs.values())   # worker started; oracle decides
    assert rc == 0
    time.sleep(3)
    assert not mark.exists(), "a worker child outlived the timeout and wrote after it"


# 6 "unavailable" was a text grep over the whole stream
def test_valid_run_mentioning_rate_limit_stays_valid(project, fake_cli, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_TEXT", "Added a rate limit and a usage limit to the API handler.")
    work = tmp_path / "work"
    run_main(project, work, fake_cli)
    runs = receipt_runs(work)
    assert runs[("greeting", "with")]["result_subtype"] == "error_max_turns"
    assert runs[("greeting", "with")]["status"] == "valid"


def test_529_overloaded_run_is_unavailable_not_a_fail(project, fake_cli, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_RESULT", json.dumps({
        "type": "result", "subtype": "success", "is_error": True,
        "result": "API Error: 529 Overloaded", "terminal_reason": "completed"}))
    work = tmp_path / "work"
    run_main(project, work, fake_cli)
    assert {r["status"] for r in receipt_runs(work).values()} == {"unavailable"}


# 7 an oracle that cannot run was recorded as a measured fail
def test_oracle_that_cannot_run_is_invalid_not_fail(project, fake_cli, tmp_path):
    tasks = tmp_path / "tasks"
    (tasks / "greeting").mkdir(parents=True)
    (tasks / "greeting" / "prompt.txt").write_text("Write the greeting file.\n")
    (tasks / "greeting" / "oracle.sh").write_text("no-such-checker-xyz \"$1/hello.txt\"\n")
    work = tmp_path / "work"
    rc = run_main(project, work, fake_cli, tasks=tasks)
    runs = receipt_runs(work)
    assert {r["status"] for r in runs.values()} == {"oracle-error"}
    assert {r["oracle_rc"] for r in runs.values()} == {127}
    assert rc == 1


# 8 the control arm replaced only the SKILL.md body; references/ kept the real text
def test_control_arm_replaces_every_skill_file(project, fake_cli, tmp_path):
    work = tmp_path / "work"
    run_main(project, work, fake_cli, "--control")
    ctl = tree(work, "control") / ".claude" / "skills" / "ab-fixture"
    real = project / ".claude" / "skills" / "ab-fixture"
    for f in sorted(p for p in real.rglob("*") if p.is_file()):
        rel = f.relative_to(real)
        data = (ctl / rel).read_bytes()
        assert len(data) == f.stat().st_size, rel
        assert b"SF-FIXTURE-7" not in data and b"REAL-CONTENT-TOKEN" not in data, rel
    assert (ctl / "SKILL.md").read_text().startswith("---\nname: ab-fixture\n")


# 9 a namespaced plugin:skill call counted toward a same-named project skill
def test_namespaced_plugin_invocation_does_not_count_for_project_skill():
    user_cmd, sys_cmd, skill = (FIX / "transcripts" / "lines.jsonl").read_text().splitlines()
    lines = [skill.replace("merge-reviewed-pr", "otherplug:beta"),
             sys_cmd.replace("/rename", "/myplug:beta"),
             skill.replace("merge-reviewed-pr", "alpha")]
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        Path(d, "s.jsonl").write_text("\n".join(lines) + "\n")
        res = skill_usage.scan([Path(d)], ["alpha", "beta"])
    assert res["counts"] == {"alpha": 1, "beta": 0}


# 10 the receipt went through one fixed .tmp path shared by concurrent runs
def test_receipt_temp_path_is_unique(project, fake_cli, tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "skill-ab-receipt.tmp").mkdir()      # another writer's fixed temp path, occupied
    rc = run_main(project, tmp_path / "work", fake_cli, "--out", str(out))
    assert rc == 0
    assert json.loads((out / "skill-ab-receipt.json").read_text())["runs"]


# ---------------------------------------------------------------- local corrections

def test_refused_work_root_inside_project_is_not_created(project, fake_cli):
    wr = project / "wr"
    assert run_main(project, wr, fake_cli, "--dry-run") == 2
    assert not wr.exists()


def test_reused_work_root_is_refused_cleanly(project, fake_cli, tmp_path, capsys):
    work = tmp_path / "work"
    assert run_main(project, work, fake_cli) == 0
    assert run_main(project, work, fake_cli) == 2
    assert "refused" in capsys.readouterr().err


def test_three_unavailable_writes_partial_receipt_and_exits_2(project, fake_cli, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "limit")
    monkeypatch.setenv("FAKE_STDERR", "boom-stderr\n")
    tasks = tmp_path / "tasks"
    for name in ("a", "b"):
        (tasks / name).mkdir(parents=True)
        (tasks / name / "prompt.txt").write_text("x\n")
        (tasks / name / "oracle.sh").write_text("exit 1\n")
    work = tmp_path / "work"
    assert run_main(project, work, fake_cli, tasks=tasks) == 2
    rec = json.loads((work / "skill-ab-receipt.json").read_text())
    assert rec["meta"]["aborted"] and len(rec["runs"]) == 3
    assert (work / "a-with-0" / "stderr.txt").read_text() == "boom-stderr\n"


def test_contaminated_run_exits_1(project, fake_cli, tmp_path, monkeypatch):
    # without-arm init lists the skill -> contaminated, report written, exit 1
    with_init = (FIX / "stream" / "with.jsonl").read_text().splitlines()[0]
    monkeypatch.setenv("FIX_STREAM", str(tmp_path / "streams"))
    (tmp_path / "streams").mkdir()
    (tmp_path / "streams" / "with.jsonl").write_text((FIX / "stream" / "with.jsonl").read_text())
    (tmp_path / "streams" / "without.jsonl").write_text(
        with_init + "\n" + "\n".join((FIX / "stream" / "without.jsonl").read_text().splitlines()[1:]) + "\n")
    work = tmp_path / "work"
    assert run_main(project, work, fake_cli) == 1
    assert receipt_runs(work)[("greeting", "without")]["status"] == "contaminated"


def test_without_arm_removes_committed_skill(project, fake_cli, tmp_path):
    work = tmp_path / "work"
    assert run_main(project, work, fake_cli) == 0
    assert not (tree(work, "without") / ".claude" / "skills" / "ab-fixture").exists()
    assert receipt_runs(work)[("greeting", "without")]["status"] == "valid"


def test_model_unknown_when_no_model_usage():
    meta = {"skill": "s", "tasks": ["t"], "n": 1, "model": "sonnet", "effort": "medium",
            "models_used": []}
    s = skill_ab.summarize([], ["with", "without"])
    assert "model unknown (requested sonnet)" in skill_ab.render(s, meta)


@pytest.mark.parametrize("n", ["0", "-1"])
def test_n_must_be_positive(project, fake_cli, tmp_path, n):
    with pytest.raises(SystemExit) as e:
        run_main(project, tmp_path / "work", fake_cli, "--n", n, "--dry-run")
    assert e.value.code == 2


def test_usage_footer_has_no_unbound_placeholder():
    text = skill_usage.render({"counts": {"a": 0}, "transcripts": 1, "first": None, "last": None})
    assert "(M " not in text


def test_worker_argv_carries_isolation_flags():
    class A:
        model, effort, max_turns = "sonnet", "medium", 3
    argv = skill_ab.worker_argv("claude", A, "p")
    assert argv[argv.index("--setting-sources") + 1] == "project,local"
    assert "--no-session-persistence" in argv
    assert "--fallback-model" not in argv
