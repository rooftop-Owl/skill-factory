# Skill Search Probe Tiers

Reference for implementing cascading skill discovery in `/skills-search`. Search the fastest, highest-signal sources first. Stop when sufficient results are found.

## Design Principles

- **Cascade**: Stop at first tier with ≥3 relevant hits
- **Speed**: API calls → CLI spawns → network search (fastest first)
- **Signal**: Curated registries > aggregators > raw GitHub noise
- **Portable**: No environment-specific dependencies in Phase A

---

## Phase A — Discovery (Portable)

Find candidate skills from external sources. This phase works in any Claude Code project with network access.

### T0 — Local Inventory (instant, no network)

> "Do we already have it?"

| Probe | What it checks |
|---|---|
| `ls .claude/skills/` | Installed project-level skills |
| `ls ~/.claude/skills/` | Installed user-level skills |
| Import manifest (if exists) | Previously imported but unloaded skills |

**Exit**: Found locally → suggest loading it. No external search needed.

### T1 — Structured APIs (<2s, JSON response)

> "Ask registries with real search endpoints"

| Source | Command | Scale | Response |
|---|---|---|---|
| **Skyll** | `curl -s "https://api.skyll.app/search?q=$Q&limit=5"` | 89K+ | JSON: name, description, install_count, relevance_score |
| **LobeHub** | `npx -y @lobehub/market-cli skills search --q "$Q"` | 100K+ | Tabular: identifier, version, installs, rating |

**Why first**: Both return structured data with quality signals (install count, relevance). Covers 190K+ skills combined. Fastest programmatic sources.

**Install from T1**:
```bash
# Skyll / skills.sh
npx --yes skills add owner/repo --skill skill-name

# LobeHub
npx -y @lobehub/market-cli skills install <identifier> --agent claude-code
```

**Exit**: ≥3 relevant results → show with install commands. Done.

### T2 — CLI Package Managers (2-5s, subprocess)

> "Ask the npm-based skill ecosystems"

| Source | Command | Scale | Notes |
|---|---|---|---|
| **skills.sh** | `npx --yes skills find "$Q"` | same as Skyll | Original CLI, text output |
| **openskills** | `npx --yes openskills search "$Q"` | universal | Cross-agent: Claude, Codex, Cursor, Gemini |
| **agent-skills-cli** | `npx --yes agent-skills-cli search "$Q"` | 175K+ | 45-agent support |

**Why tier 2**: Requires npx spawn (slower), output format varies (text, not always JSON), but covers cross-agent sources Tier 1 may miss.

**Install from T2**:
```bash
# openskills
npx --yes openskills install skill-name

# agent-skills-cli
npx --yes agent-skills-cli install @namespace/skill-name
```

**Exit**: ≥3 relevant results → show with install commands. Done.

### T3 — GitHub Discovery (3-8s, broad)

> "Search GitHub directly for SKILL.md files and tagged repos"

| Probe | Command | Signal quality |
|---|---|---|
| **Topic search** | `gh search repos --topic claude-code-skills "$Q" --limit 5 --json name,url,description,stargazersCount` | Medium — depends on tagging |
| **Code search** | `gh search code "SKILL.md" "$Q" --limit 5` | Medium — finds actual skill files |
| **grep.app** | Search `SKILL.md` files for `$Q` across all public repos | High — pattern-level matching |

**Why tier 3**: GitHub has everything but no curation. Filter results by star count (≥10), recency (≤6 months), and license (MIT/Apache-2.0/BSD).

**Install from T3**: Clone → copy skill directory to `.claude/skills/`.

**Exit**: Show results with star counts and last activity. User decides.

### T4 — Curated Awesome-Lists (reference fallback)

> "Check what the community curates for obscure domains"

| Source | Stars | Skills | URL |
|---|---|---|---|
| **ComposioHQ/awesome-claude-skills** | 46.5K | 500+ | github.com/ComposioHQ/awesome-claude-skills |
| **hesreallyhim/awesome-claude-code** | 30.5K | 200+ | github.com/hesreallyhim/awesome-claude-code |
| **sickn33/antigravity-awesome-skills** | 26.2K | 860+ | github.com/sickn33/antigravity-awesome-skills |
| **VoltAgent/awesome-agent-skills** | 12.5K | 380+ | github.com/VoltAgent/awesome-agent-skills |

**Probe method**: These are markdown files. Clone to local cache → `grep -i "$Q"` across READMEs. Human-curated with quality gates — useful when Tiers 1-3 return noise.

### T5 — Official Plugin Marketplace (separate install path)

> "Claude Code's native plugin system"

| Source | Access | Install |
|---|---|---|
| **anthropics/claude-plugins-official** | `gh api repos/anthropics/claude-plugins-official/contents/` | `/plugin install name@claude-plugin-directory` |
| **anthropics/skills** | `gh api repos/anthropics/skills/contents/skills/` | `/plugin marketplace add anthropics/skills` |

**Why separate**: Different install mechanism (`/plugin` not `npx skills`), different format (plugin.json, not standalone SKILL.md). Show results separately with plugin-specific install commands.

---

## Phase B — Analysis (Enhanced, Optional)

Qualify candidates found in Phase A using deeper analysis tools. This phase requires MCP-capable environments (DeepWiki, GitNexus, Context7, etc.) and is not available in all setups.

### When to Run Phase B

Run analysis when:
- Installing a skill for production use (not just experimentation)
- Multiple candidates compete and need comparison
- Candidate repo is unfamiliar with no star/review signal
- Domain has security or correctness implications

Skip when:
- Candidate is from a known-trusted source (anthropics/, obra/superpowers)
- Quick experiment or one-off use
- Star count >1K with recent activity

### B1 — Institutional Memory Check

> "Do we already have captured knowledge about this domain?"

| Tool | What it answers | Command |
|---|---|---|
| **QMD** (if available) | "Have we indexed knowledge about this domain?" | `qmd_search(query="$Q")` or `qmd_vector_search(query="$Q")` |
| **Digest search** | "Did we capture patterns about this in a strategic digest?" | `grep -ri "$Q" .sisyphus/landscape/clusters/ .sisyphus/digests/` |

**Value**: May reveal that an existing digest already captured the patterns the skill teaches — skip installing, use the reference directly.

### B2 — Repo Architecture Analysis

> "What does this skill repo actually do? Is it well-structured?"

| Tool | What it answers |
|---|---|
| **DeepWiki** | Full architectural overview: how the skill works, dependencies, quality signals, patterns used |

```
# Interrogate candidate repo
deepwiki_get-deepwiki-index(owner="owner", repo="repo")
deepwiki_get-deepwiki-page(path="/architecture")
```

**Value**: Reveals whether the skill is well-designed vs. a thin wrapper around a prompt. Surface implementation quality before installing.

### B3 — Domain SOTA Validation

> "Does this skill follow current best practices for its domain?"

| Tool | What it answers |
|---|---|
| **Context7** | Official documentation and best practices for the domain the skill covers |

```
# Check SOTA for the skill's domain
context7_resolve-library-id(libraryName="library", query="best practices for X")
context7_query-docs(libraryId="/org/lib", query="recommended patterns for X")
```

**Value**: Validates whether the skill teaches current best practices vs. outdated patterns.

### B4 — Overlap Detection

> "Do we already have a skill that covers this?"

| Tool | What it answers |
|---|---|
| **GitNexus** (if indexed) | Structural overlap: existing skills, functions, modules that already cover this domain |
| **Scout Cache** (if available) | Fast local scan of existing skill content for keyword overlap |

```
# Check for existing coverage
gitnexus_query(query="skill for $DOMAIN", goal="find existing coverage")
```

**Value**: Prevents installing a skill that duplicates existing capabilities.

### B5 — Real-World Usage Patterns

> "How do production codebases actually use this pattern?"

| Tool | What it answers |
|---|---|
| **grep.app** | Real code examples from 1M+ public repos showing how the pattern is used in practice |

```
# Find production usage
grep_app_searchGitHub(query="pattern-from-skill", language=["TypeScript"])
```

**Value**: Cross-validates the skill's approach against real-world usage. Catches skills that teach anti-patterns.

---

## Cascade Summary

```
Query: "typescript testing"

Phase A — Discovery (portable)
    ├─ T0: ls .claude/skills/ | grep -i test     →  found tdd-workflow? DONE
    ├─ T1: Skyll API + LobeHub                    →  ≥3 hits? SHOW + DONE
    ├─ T2: skills.sh + openskills + agent-skills  →  ≥3 hits? SHOW + DONE
    ├─ T3: gh search + grep.app                   →  any hits? SHOW + DONE
    ├─ T4: grep awesome-lists cache               →  any hits? SHOW + DONE
    └─ T5: /plugin marketplace search             →  any hits? SHOW separately

Phase B — Analysis (enhanced, optional)
    ├─ B1: QMD / digest-search                    →  already have knowledge? SKIP install
    ├─ B2: DeepWiki on candidate repo             →  architecture quality check
    ├─ B3: Context7 for domain SOTA               →  best practices validation
    ├─ B4: GitNexus / Scout for overlap           →  duplication check
    └─ B5: grep.app for real-world usage          →  anti-pattern detection
```

**Typical case** (T0+T1): <2 seconds.
**Full cascade** (T0-T5 + B1-B5): ~30 seconds.

---

## Source Maintenance

This document reflects the skill ecosystem as of March 2026. Sources to watch:

- **Emerging**: PolySkill (polyskill.ai), SkillReg (skillreg.dev), Skill Compose
- **MCP registries**: smithery.ai, glama.ai, mcp.run (overlap with skills but different install path)
- **Official**: Anthropic may ship built-in `/skills search` (tracked in anthropics/claude-code#29828)

Update this document when new sources reach ≥1K indexed skills with a working search API.
