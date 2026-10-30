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

**Claude Code only** — it drives headless `claude -p`. The session review above is an LLM judgment of one transcript; it cannot say whether a skill changed the outcome. This mode measures that: each task runs N times with the skill and N times without it, and a deterministic oracle scores every run.

It reports two things separately, because a skill fails in two ways:
- **Adherence** — was the skill invoked (`Skill` tool calls in each run's stream-json)?
- **Effect** — oracle pass rate per arm, the delta, raw pass counts, and a Fisher exact p.

### Task set

```
<tasks>/<task-id>/prompt.txt   # the prompt given to the worker
<tasks>/<task-id>/oracle.sh    # run after the worker exits: bash oracle.sh <clone> <result.txt>; exit 0 = pass
```

Keep the task set outside the project: the oracle must not be readable by the worker. A worked example is in `tests/fixtures/ab/` of this plugin.

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

- Every run gets its own `git clone --local --no-hardlinks` of the project (HEAD; uncommitted changes outside the skill are not included) under a temp work root.
- `with` copies the skill directory into the clone's `.claude/skills/<name>/`; `without` deletes that directory; nothing else differs.
- `--control` adds a third arm: same `name` and `description`, body replaced by filler of equal byte length. It separates "this skill's content helped" from "any skill-shaped text in context helped".
- Every run passes `--setting-sources project,local`, which drops `~/.claude/skills` and installed plugins, so a user-level or plugin copy of the skill cannot leak into the `without` arm. Each run's `system/init` event lists the loaded skills; a `without` run that lists the skill (`contaminated`) or a `with`/`control` run that does not (`not-loaded`) is excluded and the script exits 1.
- Model and effort are always passed explicitly; the model actually used (from `modelUsage`) is printed as "effect measured on <model>/<effort>".

Exit codes: `0` report written, `1` report written with invalid runs excluded, `2` refused (CLI absent, bad task set, work root under a `CLAUDE.md`, or 3 consecutive runs unavailable — usually the account's usage limit).
