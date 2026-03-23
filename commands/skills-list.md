---
description: List imported skills with source and status
---

Show all skills imported via skill-factory with their provenance.

## Usage

```
/skills-list
```

## Implementation

1. **Read manifest**:
   ```bash
   cat .claude/skill-factory/manifest.json 2>/dev/null
   ```

2. **If no manifest exists**: Print "No imported skills. Use `/skills-install <owner/repo>` to add some."

3. **Display as table** — for each entry in `imports[]`:
   | Name | Source | Imported | Status |
   |------|--------|----------|--------|
   | brainstorming | obra/superpowers | 2026-03-24 | active |
   | writing-plans | obra/superpowers | 2026-03-24 | removed |

   - Status: `active` if no `removed_at` field, `removed` if `removed_at` is present
   - Show removed entries dimmed or with strikethrough

4. **Summary line**: "N active skills from M sources. N removed (archived)."
