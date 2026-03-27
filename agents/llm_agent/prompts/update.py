import json


def build_update_message(
    summary: dict,
    world_model: dict,
    evaluation: dict,
    discoveries: list[str],
    incident_result: dict | None = None,
) -> str:
    incident_section = ""
    if incident_result:
        incident_section = f"""
INCIDENT RESULT (game_over or level_complete)
{json.dumps(incident_result, indent=2, ensure_ascii=False)}
"""

    return f"""\
PREVIOUS SUMMARY
{json.dumps(summary, indent=2, ensure_ascii=False)}

CURRENT WORLD MODEL
{json.dumps(world_model, indent=2, ensure_ascii=False)}

EVALUATION RESULT
{json.dumps(evaluation, indent=2, ensure_ascii=False)}

NEW DISCOVERIES
{json.dumps(discoveries, indent=2, ensure_ascii=False)}
{incident_section}
Update both the summary and world model. Respond in JSON:
{{
  "updated_summary": {{
    "game_type": "...",
    "objects": {{}},
    "current_position": "...",
    "known_map": "..."
  }},
  "updated_world_model": {{
    "game_type": {{"hypothesis": "...", "confidence": 0.5}},
    "actions": {{
      "up": {{"effect": "moves player up 1 cell", "confidence": 0.7}},
      "down": {{"effect": "likely moves down", "confidence": 0.5}}
    }},
    "controllable": {{"description": "...", "confidence": 0.7}},
    "goal": {{"description": "...", "confidence": 0.3}},
    "dangers": [],
    "interactions": []
  }}
}}

Rules:
- updated_summary: FULL replacement, not a diff.
- updated_world_model: update confidence based on what was tested.
  - Tested and confirmed → confidence 0.7+
  - Inferred from related action → confidence 0.5
  - Disproven → confidence 0.0 with updated effect
  - Direction keys: if one direction is tested, infer the other 3.
- If death_cause in INCIDENT, add to dangers.
- If win_condition in INCIDENT, update goal confidence.
- Keep concise. This is the only context OBSERVE and DECIDE will see."""
