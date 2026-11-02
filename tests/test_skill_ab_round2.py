"""Failure modes from review round 2 of PR #7.

Material 1: worker children that leave the process group (Claude Code's Bash tool
spawns with setsid) survived the kill and could write into the run tree while the
oracle scored it. Material 2: a second copy of the skill (a plugin mirror such as
skills/<name>/SKILL.md) survived into the without and control trees.
"""
import json
import shutil
import time

import skill_ab
from conftest import FIX, git
from test_skill_ab_round1 import TASKS, receipt_runs, run_main, tree


def all_text(root):
    out = []
    for p in sorted(root.rglob("*")):
        if p.is_file() and ".git" not in p.relative_to(root).parts:
            out.append(p.read_bytes())
    return b"\n".join(out)


# ---- material 1: children outside the worker's process group

def test_detached_child_after_normal_exit_is_killed_and_run_invalid(project, fake_cli, tmp_path,
                                                                    monkeypatch):
    mark = tmp_path / "late-write"
    monkeypatch.setenv("FAKE_MODE", "background")
    monkeypatch.setenv("FAKE_MARK", str(mark))
    work = tmp_path / "work"
    rc = run_main(project, work, fake_cli)
    time.sleep(3)
    assert not mark.exists(), "a detached worker child outlived a normal exit and wrote after it"
    runs = receipt_runs(work)
    assert {r["status"] for r in runs.values()} == {"stray-process"}
    assert all(r["strays"] >= 1 for r in runs.values())
    assert rc == 1


def test_refuses_without_proc(project, fake_cli, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(skill_ab, "PROC", tmp_path / "no-proc", raising=False)
    assert run_main(project, tmp_path / "work", fake_cli, "--dry-run") == 2
    assert "/proc" in capsys.readouterr().err


def _oracle_tasks(tmp_path, body):
    tasks = tmp_path / "tasks"
    (tasks / "greeting").mkdir(parents=True)
    (tasks / "greeting" / "prompt.txt").write_text("Write the greeting file.\n")
    (tasks / "greeting" / "oracle.sh").write_text(body)
    return tasks


def test_oracle_timeout_is_oracle_error(project, fake_cli, tmp_path):
    work = tmp_path / "work"
    rc = run_main(project, work, fake_cli, "--oracle-timeout", "1",
                  tasks=_oracle_tasks(tmp_path, "sleep 30\n"))
    runs = receipt_runs(work)
    assert {r["status"] for r in runs.values()} == {"oracle-error"}
    assert {r["oracle_rc"] for r in runs.values()} == {None}
    assert rc == 1


def test_oracle_killed_by_signal_is_oracle_error(project, fake_cli, tmp_path):
    work = tmp_path / "work"
    run_main(project, work, fake_cli, tasks=_oracle_tasks(tmp_path, "kill -9 $$\n"))
    runs = receipt_runs(work)
    assert {r["status"] for r in runs.values()} == {"oracle-error"}
    assert {r["oracle_rc"] for r in runs.values()} == {-9}


def test_oracle_background_child_holding_pipe_does_not_hang(project, fake_cli, tmp_path):
    work = tmp_path / "work"
    started = time.time()
    run_main(project, work, fake_cli, "--oracle-timeout", "1",
             tasks=_oracle_tasks(tmp_path, "sleep 20 &\nexit 0\n"))
    assert time.time() - started < 15, "an oracle child holding the pipe hung the run"


# ---- material 2: second copies of the skill

def _mirror_project(project):
    real = project / ".claude" / "skills" / "ab-fixture"
    shutil.copytree(real, project / "skills" / "ab-fixture")          # plugin mirror
    (project / "docs").mkdir()
    shutil.copy(real / "SKILL.md", project / "docs" / "copy-of-skill.md")  # renamed, same bytes
    git("add", "-A", cwd=project)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "mirror", cwd=project)


def test_mirror_copies_removed_from_without_and_control(project, fake_cli, tmp_path):
    _mirror_project(project)
    work = tmp_path / "work"
    assert run_main(project, work, fake_cli, "--control") == 0
    for arm in ("without", "control"):
        text = all_text(tree(work, arm))
        assert b"SF-FIXTURE-7" not in text, arm
        assert b"REAL-CONTENT-TOKEN" not in text, arm
    assert (tree(work, "with") / "skills" / "ab-fixture" / "SKILL.md").exists()


def test_refuses_when_skill_body_survives_elsewhere(project, fake_cli, tmp_path, capsys):
    body = (project / ".claude" / "skills" / "ab-fixture" / "SKILL.md").read_text().split("---\n", 2)[2]
    (project / "NOTES.md").write_text("Pasted from the skill:\n" + body)
    git("add", "-A", cwd=project)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "notes", cwd=project)
    assert run_main(project, tmp_path / "work", fake_cli, "--dry-run") == 2
    assert "NOTES.md" in capsys.readouterr().err


# ---- local items

def test_non_git_project_copied_without_dot_git(fake_cli, tmp_path):
    proj = tmp_path / "plain"
    skill = proj / ".claude" / "skills" / "ab-fixture"
    skill.mkdir(parents=True)
    shutil.copy(FIX / "ab" / "skill" / "ab-fixture" / "SKILL.md", skill / "SKILL.md")
    (proj / "sub" / ".git").mkdir(parents=True)      # nested .git is not the top-level one
    work = tmp_path / "work"
    assert run_main(proj, work, fake_cli) == 0
    assert not (tree(work, "without") / ".git").exists()
    assert not (tree(work, "without") / ".claude" / "skills" / "ab-fixture").exists()
    assert (tree(work, "with") / "sub" / ".git").is_dir()


def test_dry_run_plan_does_not_print_placeholder_path(project, fake_cli, capsys):
    assert skill_ab.main(["--skill", "ab-fixture", "--tasks", str(TASKS), "--project", str(project),
                          "--claude", str(fake_cli), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "<new>" not in out and "(new temp dir)" in out
