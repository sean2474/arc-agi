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
    "goal_hypotheses": [
      {{"description": "...", "confidence": 0.0, "supporting_evidence": [], "contradicting_evidence": []}}
    ],
    "dangers": [],
    "interactions": [
      {{"subject": "...", "object": "...", "action": "...", "result": "...", "confidence": 0.0}}
    ],
    "relationships": [
      {{"subject_type": "name (shape, color)", "relation": "...", "object_type": "name (shape, color)", "context": "...", "interaction_result": null, "confidence": 0.0}}
    ],
    "plan": {{"description": "...", "confidence": 0.0}}
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
- goal_hypotheses: update confidence based on evidence. Add supporting/contradicting evidence.
  Raise confidence for hypotheses supported by this step's result. Lower for contradicted ones.
- relationships: add/update if passive interaction observed. Use "name (shape, color)" for types.
  Fill interaction_result once observed. Set confidence 0.7+ when confirmed.
- interactions: add successful action-triggered interactions. Remove failed ones.
- dangers: add if game_over occurred near an object.
- plan: update based on top goal hypothesis and current phase.
- Keep concise. This is the only context OBSERVE and DECIDE will see."""
