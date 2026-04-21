<p align="center">
  <img src="https://img.shields.io/badge/skills-3-blue?style=flat-square" alt="Skills">
  <img src="https://img.shields.io/badge/commands-9-green?style=flat-square" alt="Commands">
  <img src="https://img.shields.io/badge/agents-1-purple?style=flat-square" alt="Agents">
  <img src="https://img.shields.io/badge/platforms-7+-orange?style=flat-square" alt="Platforms">
  <img src="https://img.shields.io/badge/license-MPL--2.0-blue?style=flat-square" alt="License">
  <img src="https://img.shields.io/badge/version-0.2.1-purple?style=flat-square" alt="Version">
</p>

# skill-factory

**The portable skill lifecycle manager for AI coding agents.**

Search 300K+ skills across 6 registries. Import from GitHub in one command. Validate against the open spec. Remove cleanly with provenance tracking. Works with Claude Code, Codex, Cursor, Gemini CLI, and every platform that reads `SKILL.md`.

> No runtime. No server. No lock-in. Your agent IS the engine.

---

## Why skill-factory?

The agent skills ecosystem is exploding — 300K+ skills across a dozen registries, marketplaces, and awesome-lists. But finding the right skill, installing it cleanly, and maintaining it across projects is still manual and fragmented.

skill-factory solves this with **9 slash commands**, **1 agent**, and **3 procedural skills** that turn your agent into a self-service skill manager:

- **Search** across Skyll (89K+), LobeHub (100K+), skills.sh, openskills, and GitHub in a tiered cascade
- **Import** from any GitHub repo with `npx` or `git clone` fallback + provenance tracking
- **Validate** against the [agentskills.io](https://agentskills.io) open specification
- **Audit** quality — trigger descriptions, frontmatter, progressive disclosure
- **Remove** cleanly with manifest archival (never lose track of what was installed)
- **Evaluate** session-level skill effectiveness — what helped, what didn't, what was missing

---

## Quick Start

### As a Claude Code Plugin

```bash
/plugin marketplace add rooftop-Owl https://github.com/rooftop-Owl/rooftop-owl-marketplace.git
/plugin install skill-factory
```

Installs all 9 commands + 1 agent + 3 skills with auto-discovery.

### Via skills.sh

```bash
npx skills add rooftop-Owl/skill-factory
```

Installs the 3 skills for any SKILL.md-compatible agent.

### Manual

```bash
git clone https://github.com/rooftop-Owl/skill-factory.git
cp -r skill-factory/skills/* ~/.claude/skills/
```

---

## Commands

| Command | Description |
|---|---|
| `/skills-search <query>` | Tiered search across 6+ registries — Skyll API, LobeHub, skills.sh, openskills, GitHub topics, grep.app |
| `/skills-install <owner/repo>` | Import skills from GitHub with npx or git clone fallback. Tracks provenance in manifest |
| `/skills-remove <name>` | Remove an imported skill with manifest archival. Never lose history |
| `/skills-list` | Show all imported skills — source, status, install date |
| `/skills-create <name>` | Scaffold a new `SKILL.md` with valid frontmatter and directory structure |
| `/skills-validate <name>` | Validate against the agentskills.io spec — required fields, size limits, format |
| `/skills-audit <name>` | Quality audit — trigger description quality, progressive disclosure, body size |
| `/skills-health` | Health report across all installed skills — coverage, staleness, spec compliance |
| `/skills-eval` | Session-end skill performance evaluation — analyzes which skills helped, which didn't, and what was missed |

---

## Skills

### skill-management

> *"import skill", "remove skill", "list imported", "validate skill"*

Core lifecycle procedures for managing external skills. Handles the full import → use → maintain → remove cycle with manifest-based provenance tracking.

### skill-development

> *"create skill", "write SKILL.md", "skill frontmatter", "publish skill"*

Authoring guide for writing production-quality skills. Covers the SKILL.md spec, description best practices (third-person, trigger phrases), progressive disclosure (body < 2K words, details in `references/`), and publishing to skills.sh.

### external-skill-acquisition

> *"no skill match", "domain knowledge", "find skill", "acquire skill"*

When you need a skill that doesn't exist yet. Three-tier acquisition: auto-install from trusted sources (MIT/Apache-2.0/MPL-2.0), manual review from spec sources, or synthesize from documentation.

---

## Agent

### skill-evaluator

At session end, run `/skills-eval` to find out whether the right skills were loaded and whether they actually helped.

The agent reads the current session transcript, identifies every skill that was loaded, and scores each as **Effective**, **Neutral**, or **Ineffective**. For underperformers, it diagnoses the root cause (wrong skill, outdated content, poor trigger, too broad, too narrow). For domains where no skill was loaded at all, it flags the missed opportunity.

Output is a structured report with per-skill findings and actionable next steps. Optionally triggers `/skills-audit` on flagged skills.

> Requires Claude Code or OpenCode with session reading tools (`mcp_session_read`).

---

## Search Tiers

skill-factory searches registries in a cascade — fast and high-signal sources first, broader and noisier sources as fallback.

| Tier | Source | Scale | Speed |
|---|---|---|---|
| **T0** | Local inventory | Your installed skills | Instant |
| **T1** | Skyll API + LobeHub | 190K+ | <2s |
| **T2** | skills.sh, openskills, agent-skills-cli | 175K+ | 2-5s |
| **T3** | GitHub topics + grep.app | All public repos | 3-8s |
| **T4** | Curated awesome-lists | 2,000+ vetted | Reference |
| **T5** | Anthropic official plugins | Curated | Separate path |

Stops at the first tier with 3+ relevant results. Full cascade documented in [`handbook/search-tiers.md`](./handbook/search-tiers.md).

---

## Platform Compatibility

skill-factory uses standard tools (`npx`, `git`, `curl`) and produces standard `SKILL.md` files. It works anywhere the open agent skills format is supported:

| Platform | Install Method |
|---|---|
| **Claude Code** | `/plugin install skill-factory` |
| **Codex** | `npx skills add rooftop-Owl/skill-factory` |
| **Cursor** | `npx skills add rooftop-Owl/skill-factory` |
| **Gemini CLI** | `npx skills add rooftop-Owl/skill-factory` |
| **OpenCode** | `npx skills add rooftop-Owl/skill-factory` |
| **Windsurf** | `npx skills add rooftop-Owl/skill-factory` |
| **Roo Code** | `npx skills add rooftop-Owl/skill-factory` |
| **Any SKILL.md agent** | `git clone` + copy to skills directory |

---

## Project Structure

```
skill-factory/
├── .claude-plugin/
│   └── plugin.json                  # Claude Code plugin manifest
├── agents/
│   └── skill-evaluator.md           # Session-end skill performance analysis
├── skills/
│   ├── skill-management/SKILL.md    # Import, remove, list, validate
│   ├── skill-development/SKILL.md   # Author and publish skills
│   └── external-skill-acquisition/
│       └── SKILL.md                 # 3-tier acquisition workflow
├── commands/
│   ├── skills-search.md             # Tiered marketplace search
│   ├── skills-install.md            # GitHub import with fallback
│   ├── skills-remove.md             # Clean removal + archival
│   ├── skills-list.md               # Inventory view
│   ├── skills-create.md             # Scaffold new skill
│   ├── skills-validate.md           # Spec validation
│   ├── skills-audit.md              # Quality audit
│   ├── skills-health.md             # Health report
│   └── skills-eval.md               # Session-end evaluation
├── handbook/
│   ├── search-tiers.md              # Full search cascade reference
│   ├── publishing-skills.md         # How to publish to skills.sh
│   └── agentskills-io-spec.md       # The open SKILL.md spec
├── CLAUDE.md                        # Plugin context for agents
├── LICENSE                          # MPL-2.0
└── README.md
```

---

## Handbook

Deep-dive references for skill authors and power users:

| Guide | Description |
|---|---|
| [Search Tiers](./handbook/search-tiers.md) | Full probe cascade — 6 tiers, install commands, source maintenance notes |
| [Publishing Skills](./handbook/publishing-skills.md) | Step-by-step guide to publishing your skills on skills.sh |
| [agentskills.io Spec](./handbook/agentskills-io-spec.md) | The open SKILL.md specification — frontmatter fields, format rules, validation criteria |

---

## Design Decisions

**Agent IS the engine.** skill-factory provides knowledge (skills), entry points (commands), and one analytical agent — your coding agent's native tool-calling handles all execution. No Python runtime, no server dependencies. Portable across platforms.

**File-level copyleft (MPL-2.0).** Modified files must stay open-source. Patent grant protects contributors. But you can freely combine skill-factory with proprietary projects in separate files. See [LICENSE](./LICENSE).

**Tiered search over single-source.** No single registry has everything. The cascade searches the fastest, highest-signal sources first and stops early when results are sufficient. This balances speed with coverage.

---

## Contributing

skill-factory is open to contributions under MPL-2.0:

1. **New registry backends** — Add a search source to the tiered cascade
2. **Skill quality improvements** — Better trigger descriptions, tighter procedures
3. **Platform adapters** — Test and document installation on new agent platforms
4. **Handbook content** — Guides for specific workflows or domains

Open an issue or PR at [rooftop-Owl/skill-factory](https://github.com/rooftop-Owl/skill-factory).

---

## License

[Mozilla Public License 2.0](./LICENSE) — file-level copyleft with patent grant.

You can use, modify, and distribute freely. Modified files must remain open-source. New files you add can use any license. Patent claims on contributed code are automatically granted to all users.
