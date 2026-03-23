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

4. **If no skills found**: "No skills found in `.claude/skills/`. Use `/skills-install` to add some or `/skills-create` to author your own."
