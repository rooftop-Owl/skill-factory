"""Failure modes from review round 3 of PR #7.

Material: a worker descendant that setsid's, chdir's out of the run tree and closes
its descriptors escaped the /proc cwd/fd sweep and wrote into the tree while the
oracle scored the run. Local: the worker's own group children, dying after a normal
exit, were counted as strays.
"""
import subprocess
import sys
import time

import skill_ab
from test_skill_ab_round1 import receipt_runs, run_main, tree


def test_escaped_descendant_chdir_closed_fds_is_killed(project, fake_cli, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "escape")
    work = tmp_path / "work"
    rc = run_main(project, work, fake_cli)
    time.sleep(3)
    for arm in ("with", "without"):
        assert not (tree(work, arm) / "late.txt").exists(), \
            "an escaped descendant wrote into the run tree after the sweep"
    runs = receipt_runs(work)
    assert {r["status"] for r in runs.values()} == {"stray-process"}
    assert rc == 1


def test_normal_exit_group_children_are_not_strays(tmp_path):
    """30 children left in the worker's own group at a normal exit are killed by the
    group kill and must not be counted as strays (pre-fix: 5 of 20 trials counted them)."""
    try:
        skill_ab.set_subreaper()
    except AttributeError:   # pre-fix module has no subreaper
        pass
    for i in range(40):
        t = tmp_path / f"t{i}"
        t.mkdir()
        rc, _, _, strays = skill_ab.run_group(
            ["bash", "-c", "for i in $(seq 30); do sleep 30 & done; exit 0"], t, 10)
        assert (rc, strays) == (0, 0), f"trial {i}"


def test_refuses_when_subreaper_cannot_be_set(project, fake_cli, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(skill_ab, "PR_SET_CHILD_SUBREAPER", 99999, raising=False)
    assert run_main(project, tmp_path / "work", fake_cli, "--dry-run") == 2
    assert "subreaper" in capsys.readouterr().err


def test_open_file_check_finds_non_descendant_holding_a_tree_file(tmp_path):
    """The cwd/fd sweep is for processes that are not the script's descendants (a
    command started through a long-running server). Here: cwd /, one open file."""
    held = tmp_path / "tree"
    held.mkdir()
    code = "import os, sys, time; f = open(sys.argv[1], 'w'); os.chdir('/'); time.sleep(30)"
    p = subprocess.Popen([sys.executable, "-c", code, str(held / "held.txt")], cwd="/")
    try:
        for _ in range(50):
            if (held / "held.txt").exists():
                break
            time.sleep(0.05)
        time.sleep(0.2)
        assert p.pid in skill_ab.processes_rooted_in(held)
    finally:
        p.kill()
        p.wait()


def test_pipe_read_time_limit_bounds_a_held_pipe(project, fake_cli, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "holdpipe")
    monkeypatch.setattr(skill_ab, "PIPE_DRAIN_SECONDS", 1)
    # disable every kill so only the time limit can end the read
    monkeypatch.setattr(skill_ab, "kill_rooted", lambda tree: 0)
    monkeypatch.setattr(skill_ab, "kill_descendants", lambda pgid: 0, raising=False)
    started = time.time()
    run_main(project, tmp_path / "work", fake_cli)
    assert time.time() - started < 8, "a held stdout pipe was read without a time limit"
