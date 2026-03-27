import json


def build_incident_gameover_message(
    last_observations: list[dict],
    frame_before_death: list[str],
    frame_at_death: list[str],
) -> str:
    obs_str = json.dumps(last_observations[-3:], indent=2, ensure_ascii=False)
    return f"""\
GAME OVER — DEATH ANALYSIS

The player died. Analyze:

LAST 3 OBSERVATIONS BEFORE DEATH
{obs_str}

FRAME RIGHT BEFORE DEATH
{chr(10).join(frame_before_death)}

FRAME AT DEATH
{chr(10).join(frame_at_death)}

Steps:
1. What did the player touch/encounter right before dying?
2. Which grid value at which position caused it?
3. Was there a warning sign?
4. How to avoid this in the future?

Respond in JSON:
{{
  "death_cause": "what killed the player",
  "death_position": {{"x": 0, "y": 0}},
  "death_value": "grid value that caused death",
  "warning_signs": ["signs before death"],
  "avoidance_rule": "how to avoid"
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
LEVEL COMPLETED ({prev_level} → {curr_level}) — WIN ANALYSIS

The level was cleared. Analyze:

LAST 3 OBSERVATIONS BEFORE WIN
{obs_str}

FRAME RIGHT BEFORE WIN
{chr(10).join(frame_before_win)}

FRAME AT WIN
{chr(10).join(frame_at_win)}

Steps:
1. What was the final action/position that triggered completion?
2. What is the confirmed win condition?
3. Will this strategy generalize to the next level?

Respond in JSON:
{{
  "win_trigger": "action/position that triggered win",
  "win_condition": "confirmed rule for winning",
  "strategy_generalizes": true,
  "reasoning": "why this will/won't work for next level"
}}"""
