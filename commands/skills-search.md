---
description: Search skills.sh and Skyll marketplaces for skills by keyword
---

Search external skill marketplaces for skills matching a query.

## Usage

```
/skills-search <query>
```

## Implementation

1. **Search Skyll API** (primary — free, no auth):
   ```bash
   curl -s "https://api.skyll.app/search?q=$ARGUMENTS&limit=5"
   ```

2. **Parse results** — the API returns:
   ```json
   {
     "results": [
       {
         "name": "skill-name",
         "description": "What the skill does",
         "source": "owner/repo",
         "relevance_score": 85.5,
         "install_count": 1250
       }
     ]
   }
   ```

3. **Display as table**:
   | # | Name | Source | Installs | Description |
   |---|------|--------|----------|-------------|
   | 1 | skill-name | owner/repo | 1,250 | What the skill does |

4. **Fallback** — if curl fails or returns empty, try:
   ```bash
   npx --yes skills find $ARGUMENTS
   ```

5. **Suggest install**: For each result, show:
   ```
   Install with: /skills-install <source-repo>
   ```

6. **Handle empty results**: "No skills found for '<query>'. Try broader keywords or search GitHub: `gh search repos topic:claude-skills <query>`"
