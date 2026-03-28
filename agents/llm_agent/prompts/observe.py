"""OBSERVE — Phase 2+ 전용. VLM에 before/after 이미지 + 코드 diff 요약 전달."""

import json


def build_observe_message(
    world_model: dict,
    action_taken: str,
    goal: str,
    diff_summary: str,
) -> str:
    return f"""\
WORLD MODEL
{json.dumps(world_model, indent=2, ensure_ascii=False)}

ACTION TAKEN: {action_taken}
GOAL: {goal}

CODE-COMPUTED DIFF:
{diff_summary}

The two images show FRAME BEFORE (first) and FRAME AFTER (second).
Use both the images and the code-computed diff to analyze changes.

STEP 1 - INTERPRET: What do the changed cells mean?
  Match changed positions to objects in the WORLD MODEL.
  Which object moved? Which direction? How far?

STEP 2 - CLASSIFY: Based on the changes:
  - Which objects moved? -> type: "dynamic"
  - Which objects stayed? -> type: "static"

STEP 3 - NEW OBJECTS: Any objects not in the WORLD MODEL?

STEP 4 - NAME REVIEW: For each object in the WORLD MODEL, is the current "name" still appropriate?
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
    {{"subject_type": "name (shape, color)", "relation": "...", "object_type": "name (shape, color)", "context": "...", "interaction_result": "...", "confidence": 0.7}}
  ],
  "contradictions": []
}}

renamed_objects format: {{"obj_001": {{"new_name": "exit", "reason": "..."}}}}
relationship_updates: only fill if a passive event was observed (object disappeared, game_over triggered near object, etc.).
  Use "name (shape, color)" format from the WORLD MODEL objects.

Rules:
- Do NOT re-analyze all objects. Focus on CHANGES only.
- Do NOT suggest actions. Observe ONLY.
- Be specific about positions.
- Changes in objects at the extreme corners or edges of the screen are HUD updates (step counter, score) — NOT meaningful game events. Do NOT interpret these as success signals."""
