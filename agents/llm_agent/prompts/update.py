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
    "notes": "..."
  }},
  "updated_world_model": {{
    "game_type": {{"hypothesis": "...", "confidence": 0.0}},
    "actions": {{
      "action_name": {{"effect": "...", "confidence": 0.0}}
    }},
    "objects": {{
      "object_name": {{"value": "...", "position": "...", "type": "unknown|static|dynamic|controllable", "interaction_tested": false}}
    }},
    "controllable": {{"description": "...", "confidence": 0.0}},
    "goal": {{"description": "...", "confidence": 0.0}},
    "dangers": [],
    "interactions": [
      {{"subject": "...", "object": "...", "action": "...", "result": "...", "confidence": 0.0}}
    ],
    "immediate_plan": "...",
    "strategic_plan": "..."
  }}
}}

Rules:
- updated_summary: FULL replacement.
- updated_world_model: update based on what was tested this step.
  - Tested and confirmed → confidence 0.7+
  - Inferred from related action → confidence 0.5
  - Disproven → confidence 0.0 with updated effect
  - Direction keys: if one tested, infer the other 3.
- objects: update positions if they moved. Set type to "dynamic"/"static"/"controllable".
  Set interaction_tested=true after testing interaction with that object.
- interactions: add successful interactions. Remove failed ones.
- dangers: add if game_over occurred near an object.
- immediate_plan / strategic_plan: update based on current phase progress.
- Keep concise. This is the only context OBSERVE and DECIDE will see."""
