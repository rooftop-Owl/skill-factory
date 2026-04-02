---
description: Evaluate skill usage and effectiveness for the current session
---

Session-end analysis of which skills were loaded, how well they performed, and what was missed. Spawns the `skill-evaluator` agent to read the session transcript and produce an actionable report.

> Requires session reading tools (`mcp_session_read`, `mcp_session_list`). Works with Claude Code and OpenCode.

## Usage

```
/skills-eval
```

## Implementation

1. **Get current session ID**:
   - Call `mcp_session_list(limit=1)` to get the most recent (current) session
   - Extract the session ID from the result

2. **Spawn the skill-evaluator agent**:
   ```
   task(
     subagent_type="skill-evaluator",
     load_skills=[],
     run_in_background=false,
     description="Evaluate skill usage for session",
     prompt="Analyze session {session_id}. Read the full transcript via mcp_session_read, identify which skills were loaded and how they performed, find missed opportunities, and produce the structured evaluation report as defined in your system prompt."
   )
   ```

3. **Present the agent's report** to the user as-is. Do not summarize or filter.

4. **If the user requests follow-up audits**, run `/skills-audit <name>` for each flagged skill.
