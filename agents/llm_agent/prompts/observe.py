"""OBSERVE — Phase 2+ 전용. VLM에 before/after 이미지 + 코드 diff 요약 전달."""

import json


def build_observe_message(
    world_model: dict,
    action_taken: str,
    goal: str,
    diff_summary: str = "",
    events_text: str = "",
) -> str:
    change_section = ""
    if events_text:
        change_section = f"""CODE-DETECTED EVENTS:
{events_text}

Objects in the images are outlined with their name labels (BEFORE left, AFTER right)."""
    else:
        change_section = f"""CODE-COMPUTED DIFF:
{diff_summary}

The two images show FRAME BEFORE (first) and FRAME AFTER (second)."""

    return f"""\
WORLD MODEL
{json.dumps(world_model, indent=2, ensure_ascii=False)}

ACTION TAKEN: {action_taken}
GOAL: {goal}

{change_section}

STEP 1 - VERIFY: Do the images confirm the events above?
  Match labeled objects in images to events. Note any contradictions.

STEP 2 - MISSING: Any changes visible in images NOT captured in events?

STEP 3 - RECLASSIFY: Based on movement, update type_hypothesis for any object whose classification is now wrong.
  KEY RULE: An object that MOVED cannot be an "obstacle" or "static platform".
  - Object moved directly in response to the action → "controllable" (note: some games have no player; the action may instead move the environment, a cursor, or multiple objects)
  - Object moved but not action-controlled → "dynamic"
  - Object stayed completely still → "static" or "obstacle" or "platform"
  List all reclassifications in renamed_objects (include new type_hypothesis even if name stays same).

STEP 4 - NAME REVIEW: For each object, is the current "name" still appropriate?
  If a name should change (e.g. you now know "unknown_1" is actually the "exit"), list it in renamed_objects.
  Keep names game-role based — not color or shape based.

STEP 5 - CHALLENGE: What could contradict your observations?

Respond in JSON:
{{
  "changes": "...",
  "moved_objects": {{}},
  "new_objects": {{}},
  "static_objects": [],
  "renamed_objects": {{}},
  "relationship_updates": [
    {{"subject_name": "...", "object_name": "...", "relation": "...", "context": "...", "interaction_result": "...", "confidence": 0.7}}
  ],
  "contradictions": []
}}

renamed_objects format: {{"obj_001": {{"new_name": "", "type_hypothesis": "", "reason": "moved in response to action"}}}}
  - Include "type_hypothesis" whenever the classification changes (even if name stays same).
  - ALWAYS reclassify any object labeled "obstacle" or "unknown" that moved this step.
relationship_updates: only fill if a passive event was observed (object disappeared, game_over triggered near object, etc.).

Rules:
- Do NOT re-analyze all objects. Focus on CHANGES only.
- Do NOT suggest actions. Observe ONLY.
- Be specific about positions.
- CRITICAL: If an object moved and is currently labeled "obstacle", it MUST be reclassified. Add it to renamed_objects.
- Changes in objects at the extreme corners or edges of the screen are HUD updates (step counter, score) — NOT meaningful game events. Do NOT interpret these as success signals."""
