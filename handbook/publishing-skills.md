# Publishing Skills to skills.sh

## How It Works

skills.sh is the open agent skills directory. Any public GitHub repo with `SKILL.md` files is automatically indexed and discoverable.

**No registration required.** Push your repo → it appears on skills.sh.

## Minimum Requirements

1. A **public GitHub repo**
2. At least one `skills/<name>/SKILL.md` file with valid frontmatter:
   ```yaml
   ---
   name: my-skill
   description: Use when the user asks to "do X" or needs help with Y
   ---
   ```

## Recommended Structure

```
my-skills-repo/
├── .claude-plugin/
│   └── plugin.json          # Optional: enables /plugin marketplace add
├── skills/
│   ├── skill-one/
│   │   ├── SKILL.md         # Required
│   │   ├── references/      # Optional: deep-dive docs
│   │   └── examples/        # Optional: usage examples
│   └── skill-two/
│       └── SKILL.md
├── LICENSE                   # MIT recommended
└── README.md
```

## Multi-Skill Repos

A single repo can contain unlimited skills. Each skill is a subdirectory with its own `SKILL.md`. Users can install specific skills:

```bash
npx skills add owner/repo --skill skill-one
npx skills add owner/repo --all        # install everything
```

## Dual-Channel Publishing

To make your repo installable via both channels:

1. **skills.sh** — just have `skills/*/SKILL.md` files (automatic)
2. **Claude Code plugins** — add `.claude-plugin/plugin.json` with your metadata

Both mechanisms coexist in the same repo.

## Leaderboard

skills.sh tracks anonymous install counts. Skills with more installs rank higher on the leaderboard. Ranking categories:
- **All Time** — total installs
- **Trending (24h)** — recent velocity
- **Hot** — current momentum

## Quality Tips

- Write clear `description` fields with trigger phrases — this is what users see in search results
- Include a README with install commands and a skills table
- Add `references/` for complex skills — keeps the main SKILL.md concise
- Use MIT license for maximum compatibility
- Keep skills focused — one capability per skill, not kitchen sinks

## Verify Your Listing

After pushing:
```bash
npx skills find <your-skill-name>
```

If it doesn't appear immediately, allow a few hours for indexing.
