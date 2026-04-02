# skill-factory

Portable skill lifecycle manager for AI coding agents.

## What This Plugin Provides

- **9 commands**: `/skills-search`, `/skills-install`, `/skills-remove`, `/skills-list`, `/skills-create`, `/skills-validate`, `/skills-audit`, `/skills-health`, `/skills-eval`
- **3 skills**: `skill-management`, `skill-development`, `external-skill-acquisition`
- **1 agent**: `skill-evaluator` — session-end skill performance analysis

## Key Conventions

- Imported skills are tracked in `.claude/skill-factory/manifest.json`
- Skills are installed to `.claude/skills/<name>/SKILL.md`
- Search uses the Skyll API (`api.skyll.app`) with npx fallback
- The `skill-management` skill contains all lifecycle procedures
- All commands are standalone — no subcommand patterns
- `/skills-eval` spawns the `skill-evaluator` agent to analyze the current session
- Session analysis requires `mcp_session_read` (Claude Code / OpenCode)
