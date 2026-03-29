from agent.fmt import fmt_transition_objects


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


def build_incident_levelcomplete_message(
    prev_level: int,
    curr_level: int,
    level_transition_info: dict | None = None,
    blobs: dict | None = None,
) -> str:
    obj_section = ""
    if level_transition_info and blobs:
        obj_block = fmt_transition_objects(blobs, level_transition_info)
        if obj_block:
            obj_section = f"\n{obj_block}\n"

    return f"""\
LEVEL COMPLETED ({prev_level} -> {curr_level}) — ANALYZE WHAT HAPPENED

Two images are provided: BEFORE (with object labels) and AT LEVEL_COMPLETE (with object labels).
{obj_section}
Steps:
1. What changed between the two frames?
2. What was the final action/condition that triggered completion?
3. Which object was involved in the win condition?
4. Do the "Known objects" still have the same role in the new level?
   If any known object should be renamed or reclassified, list it in renamed_objects.

Respond in JSON:
{{
  "trigger": "...",
  "win_condition": "...",
  "generalizes": true,
  "reasoning": "...",
  "renamed_objects": {{}}
}}

renamed_objects format: {{"obj_001": {{"new_name": "exit", "type_hypothesis": "goal", "reason": "..."}}}}"""
