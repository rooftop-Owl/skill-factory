# Platform Profiles

`agentskills.io` is the portable **lowest common denominator** for `SKILL.md`. It defines what every platform agrees on. But each platform that reads `SKILL.md` diverges — a stricter frontmatter parser, extra recognized fields, a different `name` convention. A skill can be spec-valid and still fail to parse or render on a specific target.

`/skills-validate <skill> --platform <name>` layers a platform's rules on top of the spec. This page is the divergence reference those profiles encode.

## The portable baseline (agentskills.io)

Required: `name` (`^[a-z0-9]+(-[a-z0-9]+)*$`, ≤64, matches parent dir), `description` (≤1024). Optional: `license`, `metadata.triggers`, `metadata.domains`, `metadata.version`. Nothing else is guaranteed to travel.

## claude-code

Claude Code's frontmatter parser is **non-standard — stricter than PyYAML** — and it reads fields the open spec does not define.

**Parser quirks (a spec-valid value can break here):**
- A value containing `:` is read as a nested map unless quoted. `depth: brief|deep` → quote it.
- A value containing `"` breaks the scalar. Reword or single-quote.
- A value **starting with** `[` or `{` is read as a YAML flow list/map, not a string. `argument-hint: [--flag]` → `argument-hint: "[--flag]"`.

**Extra fields (valid on Claude Code, absent from the spec):**
| Field | Purpose | Applies to |
|-------|---------|-----------|
| `argument-hint` | shows expected args in the TUI slash menu | commands (and arg-taking skills) |
| `disable-model-invocation` | make a skill user-invoked only (never auto-fired) | skills |
| `allowed-tools` | restrict the tool set | commands/skills |
| `model` | pin a model | commands/skills |

**Name convention:** slash-commands under `commands/` may set `name: /foo` (leading `/`) — which the portable regex rejects. The profile accepts the slash for `commands/` files and matches `/<stem>`; skills keep the no-slash rule.

**Rule of thumb:** if a command/skill takes arguments, add `argument-hint` (quoted) so the TUI shows them — the single most common "works but feels broken" gap on Claude Code.

## codex · cursor · gemini (stubs)

Characterize each platform's parser and extra fields, then add its checks to `skills-validate` (Layer 2) and a section here. Contributions welcome — the profile is only as portable as the rules it encodes. Until a platform is characterized, `--platform <that>` should say so rather than imply a pass.
