---
description: Validate a skill against the agentskills.io specification
---

Check a skill's SKILL.md for correctness against the agentskills.io standard.

## Usage

```
/skills-validate <skill-name>
/skills-validate <path/to/SKILL.md>
```

## Implementation

Run these checks on the target SKILL.md:

1. **File exists**: `.claude/skills/<name>/SKILL.md` or the given path
2. **Frontmatter present**: file starts with `---` and has a closing `---`
3. **`name` field**:
   - Exists and is a string
   - Matches `^[a-z0-9]+(-[a-z0-9]+)*$`
   - Max 64 characters
   - Matches the parent directory name
4. **`description` field**:
   - Exists and is a string
   - Max 1024 characters
   - Not empty
5. **Body content**: at least 50 characters of content after frontmatter

**Output** — per-check PASS/FAIL:
```
✅ File exists: .claude/skills/my-skill/SKILL.md
✅ Frontmatter: valid YAML between --- markers
✅ Name: "my-skill" matches pattern and directory
✅ Description: 156 chars, within limit
✅ Body: 2,340 chars of content

Result: 5/5 checks passed — skill is spec-compliant
```

If any check fails, show the specific error and how to fix it.
