# agentskills.io Specification Reference

The open standard for cross-platform agent skills.

## SKILL.md Format

Every skill is a markdown file with YAML frontmatter:

```yaml
---
name: skill-name
description: What this skill does and when to use it
---

# Skill content (markdown)
```

## Required Fields

### `name`
- **Type**: string
- **Pattern**: `^[a-z0-9]+(-[a-z0-9]+)*$`
- **Max length**: 64 characters
- **Rules**: lowercase letters, digits, and hyphens only; cannot start or end with a hyphen
- **Must match**: the parent directory name exactly (`skills/my-skill/SKILL.md` → `name: my-skill`)

### `description`
- **Type**: string
- **Max length**: 1024 characters
- **Purpose**: primary trigger mechanism — agents load skills based on description keyword matching
- **Best practice**: start with "Use when..." and include quoted trigger phrases

## Optional Fields

### `license`
- **Type**: string (SPDX identifier)
- **Example**: `MIT`, `Apache-2.0`, `CC-BY-4.0`

### `metadata`
- **Type**: object (free-form key-value map)
- **Common subfields**:

| Field | Type | Purpose | Example |
|-------|------|---------|---------|
| `metadata.triggers` | string (pipe-delimited) | Explicit trigger phrases | `"react hooks \| useState \| useEffect"` |
| `metadata.domains` | string (pipe-delimited) | Domain classification tags | `"frontend \| react"` |
| `metadata.version` | string (semver) | Skill version | `"1.0.0"` |
| `metadata.internal` | boolean | Hide from public listings | `true` |

## Directory Structure

```
skill-name/
├── SKILL.md              # Required
├── references/           # Optional: supporting deep-dive documents
│   └── *.md
├── examples/             # Optional: usage examples
│   └── *.md
└── scripts/              # Optional: helper scripts
    └── *.sh|*.py
```

## Platform Compatibility

Skills following this spec work across all compatible platforms:

| Platform | Skill Path | Install Method |
|----------|-----------|----------------|
| Claude Code | `.claude/skills/` | `/plugin marketplace add` |
| OpenCode | `.agents/skills/` | `npx skills add` |
| Cursor | `.cursor/skills/` | `npx skills add` |
| Codex | `.agents/skills/` | `npx skills add` |
| Gemini CLI | `.agents/skills/` | `npx skills add` |
| Windsurf | `.windsurf/skills/` | `npx skills add` |
| Roo Code | `.roo/skills/` | `npx skills add` |

The `npx skills` CLI auto-detects installed platforms and places skills in the correct directory.

> **Portable baseline, not identical behavior.** This spec is the lowest common denominator — a skill that passes it *installs* everywhere, but each platform reads `SKILL.md` a little differently (stricter parsers, extra fields, name conventions), so spec-valid ≠ platform-valid. Validate against a specific target with `/skills-validate <skill> --platform <name>`. The divergence each profile encodes is documented in [`platform-profiles.md`](./platform-profiles.md).

## Validation

A skill is spec-compliant when:
1. File is named `SKILL.md` in a named subdirectory
2. Frontmatter parses as valid YAML between `---` markers
3. `name` field matches the regex and directory name
4. `description` field exists and is ≤1024 characters
5. No disallowed top-level frontmatter keys (only `name`, `description`, `license`, `metadata`)

Use `/skills-validate <name>` to check compliance.
