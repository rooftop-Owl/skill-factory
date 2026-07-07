---
description: Remove an imported skill with manifest archival
argument-hint: "<skill-name>"
---

Remove a skill that was imported via `/skills-install`.

## Usage

```
/skills-remove <skill-name>
```

## Implementation

1. **Validate name** — must match `^[a-z0-9]+(-[a-z0-9]+)*$`:
   ```bash
   echo "$ARGUMENTS" | grep -qE '^[a-z0-9]+(-[a-z0-9]+)*$' || echo "ERROR: Invalid skill name."
   ```

2. **Check manifest** — skill must be tracked in `.claude/skill-factory/manifest.json`:
   ```bash
   python3 -c "
   import json, sys
   m = json.load(open('.claude/skill-factory/manifest.json'))
   found = any(e.get('name') == sys.argv[1] and 'removed_at' not in e for e in m['imports'])
   if not found: print(f'ERROR: \"{sys.argv[1]}\" is not an imported skill. Refusing to remove.'); sys.exit(1)
   " "$ARGUMENTS"
   ```
   If not found and user insists, they can manually `rm -rf .claude/skills/<name>/`.

3. **Remove skill directory** (symlink-aware):
   ```bash
   if [ -L ".claude/skills/$ARGUMENTS" ]; then
     rm ".claude/skills/$ARGUMENTS"
   else
     rm -rf ".claude/skills/$ARGUMENTS/"
   fi
   ```

4. **Archive manifest entry** — add `removed_at` timestamp (do NOT delete the entry):
   ```bash
   python3 -c "
   import json, sys
   from datetime import datetime, timezone
   m = json.load(open('.claude/skill-factory/manifest.json'))
   for e in m['imports']:
       if e.get('name') == sys.argv[1] and 'removed_at' not in e:
           e['removed_at'] = datetime.now(timezone.utc).isoformat()
   json.dump(m, open('.claude/skill-factory/manifest.json', 'w'), indent=2)
   " "$ARGUMENTS"
   ```

5. **Confirm**: "Removed `<name>`. Manifest entry archived. Reinstall with `/skills-install <source>`."
