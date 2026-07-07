---
description: Validate a skill against the agentskills.io spec, and optionally against a target platform's stricter rules (--platform claude-code)
argument-hint: "<skill-name | path> [--platform claude-code]"
---

Check a skill's SKILL.md for correctness. Two layers: the portable **agentskills.io** spec (always), and an optional **platform profile** (`--platform`) that catches what "spec-valid" misses — a skill can pass the open spec and still fail to parse or render on a specific platform.

## Usage

```
/skills-validate <skill-name>
/skills-validate <path/to/SKILL.md>
/skills-validate <skill-name> --platform claude-code
```

## Layer 1 — agentskills.io spec (always)

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

## Layer 2 — platform profile (optional, `--platform`)

`agentskills.io` is the lowest common denominator. Each platform reads `SKILL.md` a little differently — a stricter parser, extra fields, a different name convention. `--platform` runs the target's rules on top of Layer 1. Spec-valid ≠ platform-valid. See `handbook/platform-profiles.md` for the full divergence table.

### `--platform claude-code`

Claude Code's frontmatter parser is **non-standard** (stricter than PyYAML) and it reads extra fields. Checks:

6. **Parser-safe values** — Claude Code mis-parses unquoted frontmatter values in these cases; each must be quoted:
   - a value containing `:` (e.g. `depth: brief|deep`) — parsed as a nested map otherwise
   - a value containing `"` — breaks the scalar
   - a value **starting with** `[` or `{` (e.g. `[--flag]`) — parsed as a YAML flow list/map, not a string
   Flag any offending value with the fix (wrap in quotes; if it holds a `"`, reword or single-quote).
7. **Command `name` convention** — Claude Code slash-commands may use `name: /foo` (leading `/`); the Layer-1 regex rejects the `/`. For a file under `commands/`, accept the leading slash and match `/<dir-or-file-stem>`. (Skills under `skills/` keep the no-slash rule.)
8. **`argument-hint` presence** — if the skill/command takes arguments (its body references `$ARGUMENTS`/`$1`, an `Input`/`Usage` section, or flags), recommend an `argument-hint` field so the Claude Code TUI shows what to pass. Not required by the open spec; missing it is a **WARN**, not a FAIL.
9. **CC-only fields recognized, not flagged** — `argument-hint`, `disable-model-invocation`, `allowed-tools`, `model` are valid on Claude Code though absent from the agentskills.io spec. Report them as present/OK; never fail a skill for carrying them.

Other profiles (`codex`, `cursor`, `gemini`) are stubs in `handbook/platform-profiles.md` — contribute rules as their parsers are characterized.

## Output

Per-check PASS / FAIL / WARN, Layer 1 then (if requested) Layer 2:

```
agentskills.io spec:
✅ File exists: .claude/skills/my-skill/SKILL.md
✅ Frontmatter: valid YAML between --- markers
✅ Name: "my-skill" matches pattern and directory
✅ Description: 156 chars, within limit
✅ Body: 2,340 chars of content

claude-code profile:
✅ Parser-safe values: all frontmatter values quote-safe
✅ Name convention: OK
⚠️  argument-hint: command takes args ($ARGUMENTS) but has no argument-hint — TUI won't show them
✅ CC fields: none present

Result: spec 5/5 · claude-code 3/4 (1 warning)
```

If a check fails, show the specific value/line and how to fix it.
