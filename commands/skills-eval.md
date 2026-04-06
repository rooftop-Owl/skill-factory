---
description: Evaluate skill usage and effectiveness for the current session
---

Session-end analysis of which skills were loaded, how well they performed, and what was missed. Spawns the `skill-evaluator` agent, which probes for available session tools and falls back to context window analysis if needed.

## Usage

```
/skills-eval
```

## Implementation

1. **Spawn the skill-evaluator agent**:
   ```
   task(
     subagent_type="skill-evaluator",
     load_skills=[],
     run_in_background=false,
     description="Evaluate skill usage for this session",
     prompt="Analyze the current session. Discover available session data access methods (Phase 0 in your system prompt), extract skill usage signals, score effectiveness, and produce the structured evaluation report."
   )
   ```

3. **Present the agent's report** to the user as-is. Do not summarize or filter.

4. **If the user requests follow-up audits**, run `/skills-audit <name>` for each flagged skill.
