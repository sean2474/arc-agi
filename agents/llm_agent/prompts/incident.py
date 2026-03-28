def build_incident_gameover_message() -> str:
    return """\
GAME OVER — ANALYZE WHAT HAPPENED

Two images are provided: BEFORE and AT GAME_OVER.

Steps:
1. What changed between the two frames?
2. Which object/position was involved?
3. Were there any warning signs before this happened?
4. What rule can be inferred to avoid this?

Respond in JSON:
{
  "cause": "...",
  "warning_signs": [],
  "avoidance_rule": "..."
}"""


def build_incident_levelcomplete_message(prev_level: int, curr_level: int) -> str:
    return f"""\
LEVEL COMPLETED ({prev_level} -> {curr_level}) — ANALYZE WHAT HAPPENED

Two images are provided: BEFORE and AT LEVEL_COMPLETE.

Steps:
1. What changed between the two frames?
2. What was the final action/condition that triggered completion?
3. What rule can be inferred about the win condition?

Respond in JSON:
{{
  "trigger": "...",
  "win_condition": "...",
  "generalizes": true,
  "reasoning": "..."
}}"""
