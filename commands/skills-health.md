---
description: Health report across all installed skills
---

Scan all skills in `.claude/skills/` and produce an aggregate health report.

## Usage

```
/skills-health
```

## Implementation

1. **Scan**: `find .claude/skills/ -name "SKILL.md" -type f`

2. **Per-skill checks**:
   - Frontmatter exists and parses as valid YAML
   - `name` field present and matches directory name
   - `description` field present and non-empty
   - File size within bounds (50 bytes - 50KB)

3. **Aggregate report**:
   ```
   Skill Health Report
   ═══════════════════
   Total skills: 12
   Healthy: 10
   Issues: 2

   ⚠ brainstorming — name mismatch (dir: brainstorming, name: brainstorm)
   ⚠ my-draft-skill — missing description

   Summary:
     Avg description length: 142 chars
     Skills with references/: 4 (33%)
     Skills with metadata.triggers: 6 (50%)
     Imported (via manifest): 5
     Native: 7
   ```

4. **Never-used count** (Claude Code only): run
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/skill_usage.py" --project .
   ```
   It reads this project's session transcripts in `~/.claude/projects/<slug>/` (slug = the project path with every non-alphanumeric character replaced by `-`), every sibling `<slug>--worktrees-*` directory, and nested subagent transcripts, and counts `Skill` tool calls and `/<skill>` slash commands per project skill. Append its output to the report:
   ```
   never invoked: 12 of 25 project skills across 1011 transcripts, 2026-07-03–2026-10-30
     agora-council, armory, ...
   invoked: external-adoption (11), eval-integrity (8), ...
   ```
   M counts only the project's `.claude/skills/`, not user-level or plugin skills. Claude Code deletes transcripts after `cleanupPeriodDays` (default 30), so "never invoked" holds only for the printed window. Exit 2 means no transcripts exist for this project (another platform, or a new project): print "Never-used count: no Claude Code transcripts for this project" and continue.

5. **If no skills found**: "No skills found in `.claude/skills/`. Use `/skills-install` to add some or `/skills-create` to author your own."
