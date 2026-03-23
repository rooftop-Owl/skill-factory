# skill-factory

**Portable skill lifecycle manager for AI coding agents.**

Import, search, validate, and remove agent skills across the skills.sh ecosystem. Works with Claude Code, OpenCode, Cursor, Codex, Gemini CLI, and any SKILL.md-compatible platform.

## Quick Start

### As a Claude Code Plugin (full experience)

```bash
/plugin marketplace add rooftop-Owl/skill-factory
```

Gets you 8 commands + 3 skills.

### Via skills.sh (skills only)

```bash
npx skills add rooftop-Owl/skill-factory
```

Gets you the 3 skills for manual use.

## Commands

| Command | What It Does |
|---------|-------------|
| `/skills-search <query>` | Search skills.sh + Skyll marketplace by keyword |
| `/skills-install <owner/repo>` | Import skills from GitHub — npx or git clone fallback |
| `/skills-remove <name>` | Remove an imported skill with manifest archival |
| `/skills-list` | Show imported skills with source and status |
| `/skills-create <name>` | Scaffold a new SKILL.md with valid frontmatter |
| `/skills-validate <name>` | Validate against the agentskills.io spec |
| `/skills-audit <name>` | Quality audit — triggers, description, size |
| `/skills-health` | Health report across all installed skills |

## Skills

| Skill | Triggers | What It Does |
|-------|----------|-------------|
| [skill-management](./skills/skill-management/SKILL.md) | "import skill", "remove skill", "list imported", "validate skill" | Core lifecycle procedures — import, remove, list, validate with manifest tracking |
| [skill-development](./skills/skill-development/SKILL.md) | "create skill", "write SKILL.md", "skill frontmatter", "publish skill" | Authoring guide — spec format, description best practices, testing, publishing |
| [external-skill-acquisition](./skills/external-skill-acquisition/SKILL.md) | "no skill match", "domain knowledge", "find skill", "acquire skill" | 3-tier acquisition workflow — auto-install, manual review, or synthesize from docs |

## Platform Compatibility

These skills and commands use standard tools (`npx`, `git`, `curl`) and work with any agent platform that reads SKILL.md files:

| Platform | Supported | Install |
|----------|-----------|---------|
| Claude Code | ✅ | `/plugin marketplace add` |
| OpenCode | ✅ | `npx skills add` |
| Cursor | ✅ | `npx skills add` |
| Codex | ✅ | `npx skills add` |
| Gemini CLI | ✅ | `npx skills add` |
| Windsurf | ✅ | `npx skills add` |
| Roo Code | ✅ | `npx skills add` |

## Structure

```
skill-factory/
├── .claude-plugin/
│   └── plugin.json               # Plugin identity
├── skills/
│   ├── skill-management/
│   │   └── SKILL.md              # Import, remove, list, validate
│   ├── skill-development/
│   │   └── SKILL.md              # Author and publish skills
│   └── external-skill-acquisition/
│       └── SKILL.md              # 3-tier acquisition workflow
├── commands/
│   ├── skills-search.md          # Marketplace search
│   ├── skills-install.md         # Import from repos
│   ├── skills-remove.md          # Graceful removal
│   ├── skills-list.md            # List imported
│   ├── skills-create.md          # Scaffold new skill
│   ├── skills-validate.md        # Spec validation
│   ├── skills-audit.md           # Quality audit
│   └── skills-health.md          # Health report
├── handbook/
│   ├── publishing-skills.md      # How to publish to skills.sh
│   └── agentskills-io-spec.md    # Full spec reference
├── LICENSE                        # MIT
└── README.md
```

## Handbook

Human-readable guides for deeper understanding:

- [Publishing Skills](./handbook/publishing-skills.md) — How to publish your skills to skills.sh
- [agentskills.io Spec](./handbook/agentskills-io-spec.md) — The full SKILL.md specification reference

## License

MIT
