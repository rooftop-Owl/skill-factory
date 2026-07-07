---
description: Import skills from skills.sh ecosystem into your project
argument-hint: "<owner/repo>"
---

Import skills from a GitHub repository into `.claude/skills/`.

## Usage

```
/skills-install <owner/repo>
```

## Implementation

1. **Check prerequisites**:
   ```bash
   command -v npx || command -v git || echo "ERROR: Install Node.js (npx) or git to use this command."
   ```

2. **Create manifest directory** if needed:
   ```bash
   mkdir -p .claude/skill-factory
   [ -f .claude/skill-factory/manifest.json ] || echo '{"imports":[]}' > .claude/skill-factory/manifest.json
   ```

3. **Install — primary path (npx)**:
   ```bash
   npx --yes skills add $ARGUMENTS --yes
   ```

4. **Install — fallback (git clone, if no npx)**:
   ```bash
   git clone --depth=1 https://github.com/$ARGUMENTS /tmp/skill-import
   for skill_dir in /tmp/skill-import/skills/*/; do
     name=$(basename "$skill_dir")
     if [ -f "$skill_dir/SKILL.md" ]; then
       cp -r "$skill_dir" ".claude/skills/$name/"
     fi
   done
   rm -rf /tmp/skill-import
   ```

5. **Resolve symlinks** — npx creates symlinks, convert to real copies:
   ```bash
   for link in $(find .claude/skills/ -maxdepth 1 -type l 2>/dev/null); do
     target=$(readlink -f "$link")
     rm "$link"
     cp -r "$target" "$link"
   done
   ```

6. **Register in manifest** — for each installed skill:
   ```bash
   python3 -c "
   import json, sys
   from datetime import datetime, timezone
   path = '.claude/skill-factory/manifest.json'
   try: m = json.load(open(path))
   except: m = {'imports': []}
   m['imports'].append({'name': sys.argv[1], 'source_repo': sys.argv[2], 'imported_at': datetime.now(timezone.utc).isoformat(), 'path': f'.claude/skills/{sys.argv[1]}/'})
   json.dump(m, open(path, 'w'), indent=2)
   " "<skill-name>" "<owner/repo>"
   ```

7. **Confirm**: List the newly installed skill names and their locations.

## Notes
- Skills are installed to `.claude/skills/<name>/SKILL.md` — the standard location for all agent platforms
- Newly installed skills are available in the next session; for same-session use, load the `skill-management` skill for the prompt injection workaround
- If the skill already exists in `.claude/skills/`, ask the user before overwriting
