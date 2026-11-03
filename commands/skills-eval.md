---
description: Evaluate skill usage and effectiveness for the current session, or measure one skill with vs without
argument-hint: "[--ab <skill> --tasks <dir> [--n N] [--control]]"
---

Session-end analysis of which skills were loaded, how well they performed, and what was missed. Spawns the `skill-evaluator` agent, which probes for available session tools and falls back to context window analysis if needed.

## Usage

```
/skills-eval                                            # session review (LLM-judged)
/skills-eval --ab <skill> --tasks <dir> [--n N] [--control]   # with vs without (measured)
```

With no arguments, run the session review below. With `--ab`, skip to [With/without mode](#withwithout-mode).

## Implementation

1. **Spawn the skill-evaluator agent**:
   ```
   task(
     subagent_type="skill-evaluator",
     load_skills=[],
     run_in_background=false,
     description="Evaluate skill usage for this session",
     prompt="Analyze the current session. Discover available session data access methods (Phase 0 in your system prompt), extract skill usage signals, score effectiveness, and produce the structured evaluation report."
   )
   ```

2. **Present the agent's report** to the user as-is. Do not summarize or filter.

3. **If the user requests follow-up audits**, run `/skills-audit <name>` for each flagged skill.

## With/without mode

**Claude Code only, Linux only** — it drives headless `claude -p` and needs `/proc` to stop worker children. The session review above is an LLM judgment of one transcript; it cannot say whether a skill changed the outcome. This mode measures that: each task runs N times with the skill and N times without it, and a deterministic oracle scores every run.

It reports two things separately, because a skill fails in two ways:
- **Adherence** — was the skill invoked (`Skill` tool calls in each run's stream-json)?
- **Effect** — oracle pass rate per arm, the delta, raw pass counts, and a Fisher exact p.

### Task set

```
<tasks>/<task-id>/prompt.txt   # the prompt given to the worker
<tasks>/<task-id>/oracle.sh    # run after the worker stops: bash oracle.sh <run-tree> <result.txt>
```

Oracle exit codes: `0` pass, `1`–`124` fail. A timeout, exit `125` or higher (`126`/`127`: cannot execute, command not found) or a signal marks the run `oracle-error`: excluded, never counted as a fail.

The tasks directory must be outside the project; the script refuses one inside it, because it would be copied into every run tree. A worked example is in `tests/fixtures/ab/` of this plugin.

**Not a sandbox.** The worker runs as you with `--dangerously-skip-permissions`: full access to your files, network and credentials, and no permission prompts. The run tree is only its starting directory. Nothing stops it reading the tasks directory (oracles included) or changing the original project; the oracle is protected only by the worker not being told its path. Run task sets you would let an agent run unattended.

### Run

1. **Dry-run first** (no model calls, checks preconditions, prints the plan and the worker argv):
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/skill_ab.py" --skill <skill> --tasks <dir> --dry-run
   ```
   If `CLAUDE_PLUGIN_ROOT` is unset, find the script with `ls ~/.claude/plugins/cache/*/skill-factory/*/scripts/skill_ab.py`.

2. **State the cost before running**: runs = tasks × arms × N (arms = 2, or 3 with `--control`). Each run is a full headless session. Ask the user to confirm N before spending it.

3. **Run** without `--dry-run`. Options: `--n N` (default 1), `--control`, `--model` (default `sonnet`), `--effort` (default `medium`), `--max-turns` (default 20), `--project` (default `.`), `--out <dir>` (receipt location).

4. **Present the report as printed**, including its label. With fewer than 10 valid runs per arm it says `smoke, not evidence`; do not describe such a result as a measured effect.

### How the arms differ

The run tree, the arms, isolation (`--setting-sources project,local` plus the `system/init` check), run classification, how the worker's processes are stopped, and the files each run keeps are specified once, in the docstring at the top of `scripts/skill_ab.py`. Read it there rather than here. One operator warning from it: the script kills every process rooted in a run tree, so do not `cd` a shell into the work root while it runs.

Exit codes: `0` report written, `1` report written with invalid runs excluded, `2` refused (CLI absent, `/proc` absent or the subreaper prctl fails, bad task set, tasks dir inside the project, a copy of the skill body left in the project, work root under a `CLAUDE.md` or not empty, or 3 consecutive runs unavailable — usually the account's usage limit; in that case a receipt with the completed runs is still written, marked `aborted`).

All tasks are pooled into one 2×2 table per comparison; there is no per-task breakdown or stratified test yet, so read multi-task results with that in mind.
