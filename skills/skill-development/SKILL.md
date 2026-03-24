---
name: skill-development
description: Use when creating new agent skills, improving skill descriptions, structuring skill directories, or authoring SKILL.md files. Covers the agentskills.io specification, frontmatter format, trigger phrase design, and publishing workflow.
---

# Skill Development

Guide for authoring high-quality, cross-platform agent skills.

## SKILL.md Format

Every skill is a markdown file with YAML frontmatter:

```yaml
---
name: my-skill-name
description: Use when the user asks to "do X", "perform Y", or needs help with Z. Provides step-by-step procedures for accomplishing the task.
---

# My Skill Name

## Purpose
What this skill enables the agent to do.

## Procedures
Step-by-step instructions the agent follows.

## When to Load
- Load when: [trigger conditions]
- Not needed when: [exclusion conditions]
```

## Frontmatter Spec (agentskills.io)

### Required Fields

| Field | Rules | Example |
|-------|-------|---------|
| `name` | `^[a-z0-9]+(-[a-z0-9]+)*$`, max 64 chars | `react-best-practices` |
| `description` | Max 1024 chars, should start with "Use when..." | `Use when building React components...` |

### Optional Fields

| Field | Purpose | Example |
|-------|---------|---------|
| `license` | SPDX identifier | `MPL-2.0` |
| `metadata.triggers` | Pipe-delimited trigger phrases | `"react hooks \| useState \| components"` |
| `metadata.domains` | Pipe-delimited domain tags | `"frontend \| react"` |
| `metadata.version` | Semver string | `"1.0.0"` |

### Name Rules
- Lowercase letters, digits, hyphens only
- Cannot start or end with a hyphen
- Max 64 characters
- **Must match the parent directory name exactly**

## Directory Structure

```
skill-name/
├── SKILL.md              # Required: main skill file
├── references/           # Optional: supporting documents
│   ├── api-patterns.md
│   └── common-errors.md
└── examples/             # Optional: usage examples
    └── basic-setup.md
```

Reference files enable progressive disclosure — the main SKILL.md stays concise while `references/` holds deep-dive content the agent loads on demand.

See `handbook/agentskills-io-spec.md` for the full specification reference.

## Description Best Practices

The `description` field is the **primary trigger mechanism**. Agents load skills based on keyword matching against descriptions.

### DO
- Start with "Use when..." or "This skill should be used when..."
- Include quoted trigger phrases: `"deploy to production"`, `"fix auth bug"`
- List concrete user prompts that should activate it
- Include negative triggers: "Not needed when..."

### DON'T
- Write vague descriptions: "Helps with development"
- Omit trigger phrases — the skill won't be discoverable
- Make descriptions longer than 1024 characters
- Duplicate another skill's trigger phrases

### Example (good)
```yaml
description: Use when the user asks to "set up authentication", "add login", "implement JWT", "secure API endpoints", or needs guidance on session management, OAuth flows, or password hashing. Not needed for basic CRUD operations or frontend styling.
```

### Example (bad)
```yaml
description: Authentication skill for web applications.
```

## Testing a Skill Locally

Before publishing, verify your skill works:

1. **Place it**: Copy `skill-name/SKILL.md` to `.claude/skills/skill-name/SKILL.md`
2. **Validate frontmatter**:
   ```bash
   python3 -c "
   import yaml
   content = open('.claude/skills/skill-name/SKILL.md').read()
   fm = yaml.safe_load(content.split('---', 2)[1])
   assert fm.get('name') == 'skill-name', 'Name mismatch'
   assert fm.get('description'), 'Missing description'
   print('PASS')
   "
   ```
3. **Test trigger**: Start a new session and type a prompt that should activate the skill
4. **Verify loading**: The agent should load and follow the skill's procedures

## Publishing

See `handbook/publishing-skills.md` for the full publishing guide. Quick version:

1. Create a public GitHub repo
2. Place skills in `skills/<name>/SKILL.md`
3. Push — skills.sh auto-indexes it
4. Verify: `npx skills find <your-skill-name>`

## When to Load This Skill

Load `skill-development` when:
- Creating a new skill from scratch
- Improving a skill's description or trigger phrases
- Structuring a skill directory with references and examples
- Validating frontmatter format
- Preparing a skill for publishing

**Not needed when**:
- Installing existing skills (use `skill-management`)
- Searching for skills (use `/skills-search`)
- Removing skills (use `skill-management`)
