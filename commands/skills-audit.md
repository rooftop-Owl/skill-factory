---
description: Quality audit for a specific skill — triggers, description, size
---

Assess the quality of a skill beyond basic validation.

## Usage

```
/skills-audit <skill-name>
```

## Implementation

Read `.claude/skills/<name>/SKILL.md` and check:

1. **Description quality**:
   - Contains trigger phrases (quoted strings like `"deploy"`, `"test"`)? → bonus
   - Starts with "Use when..." or similar action phrase? → bonus
   - Has negative triggers ("Not needed when...")? → bonus
   - Score: 0-3 based on how many of the above are present

2. **Content depth**:
   - File size < 1KB → "sparse — consider adding procedures"
   - File size 1-10KB → "good"
   - File size > 10KB → "large — consider splitting into references/"

3. **Structure**:
   - Has `## Procedures` or `## Steps` section? → good
   - Has `## When to Load` section? → good
   - Has `references/` subdirectory? → good (progressive disclosure)

4. **Trigger coverage**:
   - Count distinct trigger phrases in description
   - < 3 triggers → "low discoverability"
   - 3-6 triggers → "good"
   - > 6 triggers → "excellent"

5. **Trigger output quality**:
   - Read `.sisyphus/skill-index.json` and find the entry for the audited skill
   - Examine its `triggers` array
   - Score each trigger: "actionable" if it contains a verb or is a natural multi-word phrase (e.g. `"plan this"`, `"break this down"`); "junk" if it is a single-word meta-noun with no action (e.g. `"context-aware"`, `"inline"`, `"planning"`, `"context"`, `"following"`, `"true"`, `"false"`)
   - Score: ≥50% actionable → "good"; <50% actionable → "poor — triggers contain meta-terms, not user phrases"
   - If skill not found in index: output `"unindexed — run skill_indexer to check"`
**Output**:
```
Audit: my-skill
  Description quality: 2/3 (missing negative triggers)
  Content depth: good (3.2KB)
  Structure: 2/3 (missing references/)
  Trigger coverage: good (4 triggers)
  Trigger quality: good (8/11 actionable)

  Overall: B — solid skill, add "Not needed when..." to description
```
