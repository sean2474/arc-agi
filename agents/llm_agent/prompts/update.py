from agents.llm_agent.fmt import fmt_world_model_prompt


def build_update_message(
    summary: dict,
    world_model: dict,
    evaluation: dict,
    discoveries: list[str],
    incident_result: dict | None = None,
) -> str:
    incident_section = ""
    if incident_result:
        inc_lines = []
        if incident_result.get("reasoning"):
            inc_lines.append(f"reasoning: {incident_result['reasoning']}")
        if incident_result.get("key_learnings"):
            inc_lines.append("key_learnings: " + "; ".join(incident_result["key_learnings"]))
        inc_text = "\n".join(inc_lines) if inc_lines else str(incident_result)
        incident_section = f"""
INCIDENT RESULT (game_over or level_complete)
{inc_text}
"""

    summary_text = summary.get("notes", "(none)") if summary else "(none)"
    disc_text = "\n".join(f"  - {d}" for d in discoveries) if discoveries else "  (none)"

    return f"""\
PREVIOUS SUMMARY: {summary_text}

CURRENT WORLD MODEL
{fmt_world_model_prompt(world_model)}

NEW DISCOVERIES
{disc_text}
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
- objects: Set type to "dynamic"/"static"/"controllable".
  Set interaction_tested=true after testing interaction with that object.
- goal_hypotheses: update confidence based on evidence. Add supporting/contradicting evidence.
  Raise confidence for hypotheses supported by this step's result. Lower for contradicted ones.
- relationships: add/update if passive interaction observed. Use "name (shape, color)" for types.
  Fill interaction_result once observed. Set confidence 0.7+ when confirmed.
- interactions: add successful action-triggered interactions. Remove failed ones.
- dangers: add if game_over after interaction with an object.
- plan: update based on top goal hypothesis and current phase.
- Keep concise."""
