---
name: skill-management
description: Use when importing, removing, listing, or validating agent skills. Covers the full skill lifecycle — install from skills.sh or GitHub, resolve symlinks, track provenance in manifest, remove cleanly with archival, and validate against agentskills.io spec.
---

# Skill Management

Core procedures for managing imported skills across any agent platform.

## Manifest

All imported skills are tracked in `.claude/skill-factory/manifest.json`:

```json
{
  "imports": [
    {
      "name": "brainstorming",
      "source_repo": "obra/superpowers",
      "imported_at": "2026-03-24T12:00:00Z",
      "path": ".claude/skills/brainstorming/"
    }
  ]
}
```

Create the manifest if it doesn't exist:
```bash
mkdir -p .claude/skill-factory
echo '{"imports":[]}' > .claude/skill-factory/manifest.json
```

## Import Procedure

### Prerequisites
Check before importing: `command -v npx` or `command -v git`. At least one is required.

### Primary Path (npx)
```bash
npx --yes skills add <owner/repo> --yes
```

After npx completes, resolve any symlinks it created:
```bash
for link in $(find .claude/skills/ -maxdepth 1 -type l 2>/dev/null); do
  target=$(readlink -f "$link")
  rm "$link"
  cp -r "$target" "$link"
done
```

### Fallback Path (git clone — when npx is unavailable)
```bash
git clone --depth=1 https://github.com/<owner/repo> /tmp/skill-import
for skill_dir in /tmp/skill-import/skills/*/; do
  name=$(basename "$skill_dir")
  if [ -f "$skill_dir/SKILL.md" ]; then
    cp -r "$skill_dir" ".claude/skills/$name/"
  fi
done
rm -rf /tmp/skill-import
```

### Post-Import
After installing, register each new skill in the manifest:
```bash
python3 -c "
import json, sys
from datetime import datetime, timezone
manifest_path = '.claude/skill-factory/manifest.json'
try:
    manifest = json.load(open(manifest_path))
except (FileNotFoundError, json.JSONDecodeError):
    manifest = {'imports': []}
manifest['imports'].append({
    'name': sys.argv[1],
    'source_repo': sys.argv[2],
    'imported_at': datetime.now(timezone.utc).isoformat(),
    'path': f'.claude/skills/{sys.argv[1]}/'
})
json.dump(manifest, open(manifest_path, 'w'), indent=2)
" "<skill-name>" "<owner/repo>"
```

### Same-Session Use
Newly installed skills won't appear in `load_skills` until the next session. To use immediately, read the skill content and inject it into your prompt:
```
skill_content = read(".claude/skills/<name>/SKILL.md")
# Include skill_content at the top of your task prompt
```

## Remove Procedure

1. **Validate** the skill name: must match `^[a-z0-9]+(-[a-z0-9]+)*$`
2. **Check manifest**: only remove skills tracked in `.claude/skill-factory/manifest.json`
3. **Delete** the skill directory:
   ```bash
   # Symlink-aware removal
   if [ -L ".claude/skills/<name>" ]; then
     rm ".claude/skills/<name>"
   else
     rm -rf ".claude/skills/<name>/"
   fi
   ```
4. **Archive** the manifest entry (add `removed_at`, do NOT delete the entry):
   ```bash
   python3 -c "
   import json
   from datetime import datetime, timezone
   m = json.load(open('.claude/skill-factory/manifest.json'))
   for e in m['imports']:
       if e.get('name') == '$NAME' and 'removed_at' not in e:
           e['removed_at'] = datetime.now(timezone.utc).isoformat()
   json.dump(m, open('.claude/skill-factory/manifest.json', 'w'), indent=2)
   "
   ```

## Validate Procedure

Check a skill against the agentskills.io spec:

1. **Frontmatter exists**: file starts with `---` and has a closing `---`
2. **`name` field**: required, matches `^[a-z0-9]+(-[a-z0-9]+)*$`, max 64 chars
3. **`description` field**: required, max 1024 chars
4. **Name matches directory**: `name` field value == parent directory name
5. **No disallowed top-level keys**: only `name`, `description`, `license`, `metadata` allowed

## List Procedure

Read `.claude/skill-factory/manifest.json` and display:
- Name, source repo, import date, status (active if no `removed_at`, removed otherwise)
- If manifest doesn't exist: "No imported skills. Use /skills-install to add some."

## When to Load This Skill

Load `skill-management` when:
- User asks to install, import, or add skills from external sources
- User asks to remove, uninstall, or delete an imported skill
- User asks to list, show, or check imported skills
- User asks to validate a skill file
- Any command references the import manifest

**Not needed when**:
- Creating a new skill from scratch (use `skill-development`)
- Searching for skills to install (use `/skills-search` command)
- Understanding 3-tier acquisition decision flow (use `external-skill-acquisition`)
