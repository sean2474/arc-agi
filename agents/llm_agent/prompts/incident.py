import json


def build_incident_gameover_message(
    last_observations: list[dict],
    frame_before_death: list[str],
    frame_at_death: list[str],
) -> str:
    obs_str = json.dumps(last_observations[-3:], indent=2, ensure_ascii=False)
    return f"""\
GAME OVER — ANALYZE WHAT HAPPENED

The game state changed to GAME_OVER. Analyze:

FRAME BEFORE
{chr(10).join(frame_before_death)}

FRAME AT GAME_OVER
{chr(10).join(frame_at_death)}

Steps:
1. What changed between the two frames?
2. Which grid value/position was involved?
3. Were there any warning signs before this happened?
4. What rule can be inferred to avoid this?

Respond in JSON:
{{
  "cause": "...",
  "position": {{"x": 0, "y": 0}},
  "value": "...",
  "warning_signs": [],
  "avoidance_rule": "..."
}}"""


def build_incident_levelcomplete_message(
    prev_level: int,
    curr_level: int,
    last_observations: list[dict],
    frame_before_win: list[str],
    frame_at_win: list[str],
) -> str:
    obs_str = json.dumps(last_observations[-3:], indent=2, ensure_ascii=False)
    return f"""\
LEVEL COMPLETED ({prev_level} -> {curr_level}) — ANALYZE WHAT HAPPENED

The level was cleared. Analyze:

FRAME BEFORE
{chr(10).join(frame_before_win)}

FRAME AT LEVEL_COMPLETE
{chr(10).join(frame_at_win)}

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
