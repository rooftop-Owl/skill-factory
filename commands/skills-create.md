---
description: Scaffold a new SKILL.md with valid agentskills.io frontmatter
argument-hint: "<skill-name>"
---

Create a new skill directory with a properly structured SKILL.md template.

## Usage

```
/skills-create <skill-name>
```

## Implementation

1. **Validate name** — must match `^[a-z0-9]+(-[a-z0-9]+)*$`, max 64 chars

2. **Check for existing**: if `.claude/skills/<name>/` exists, warn and ask before overwriting

3. **Create directory structure**:
   ```bash
   mkdir -p .claude/skills/$ARGUMENTS/references .claude/skills/$ARGUMENTS/examples
   ```

4. **Write SKILL.md template**:
   ```markdown
   ---
   name: <skill-name>
   description: Use when the user asks to "..." or needs help with ...
   ---

   # <Skill Name>

   ## Purpose
   What this skill enables the agent to do.

   ## Procedures
   Step-by-step instructions for the agent.

   ## When to Load
   - Load when: [trigger conditions]
   - Not needed when: [exclusion conditions]
   ```

5. **Confirm**: "Created `.claude/skills/<name>/SKILL.md`. Edit the description and procedures, then test with `/skills-validate <name>`."
