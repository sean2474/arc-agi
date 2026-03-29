"""OBSERVE — Phase 2+ 전용. VLM에 before/after 이미지 + 코드 diff 요약 전달."""

from agents.llm_agent.fmt import fmt_world_model_prompt


def build_observe_message(
    world_model: dict,
    action_taken: str,
    goal: str,
    diff_summary: str = "",
    events_text: str = "",
) -> str:
    change_section = ""
    if events_text:
        change_section = f"""EVENTS (GROUND TRUTH — do NOT contradict these):
{events_text}

These events are computed from pixel diffs and are authoritative.
The two images (BEFORE left, AFTER right) are provided to find additional changes NOT captured above."""
    else:
        change_section = f"""DIFF:
{diff_summary}

The two images show FRAME BEFORE (first) and FRAME AFTER (second)."""

    return f"""\
WORLD MODEL
{fmt_world_model_prompt(world_model)}

ACTION TAKEN: {action_taken}
GOAL: {goal}

{change_section}

NO-CHANGE SHORTCUT: If events are "(none)" AND the two images look identical, skip all steps and respond only with:
{{"changes": "no changes observed", "moved_objects": {{}}, "new_objects": {{}}, "static_objects": [], "renamed_objects": {{}}, "relationship_updates": [], "contradictions": []}}

STEP 1 - ACCEPT EVENTS: Treat events as ground truth.
  For each event, identify the object by its instance_id in WORLD MODEL > objects.
  Do NOT re-derive which object moved from the image — use the event list.

STEP 2 - MISSING: Any changes visible in images NOT already captured in the events above?
  Only report additional changes not mentioned in the event list.

STEP 3 - RECLASSIFY: For every object that MOVED (per events), update its type_hypothesis.
  KEY RULE: An object that MOVED cannot be an "obstacle" or "static platform".
  List all reclassifications in renamed_objects (include new type_hypothesis even if name stays same).

STEP 4 - NAME REVIEW: For each object that moved or changed, is its current "name" still appropriate?
  If a name should change, list it in renamed_objects.
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
  - Keys MUST be obj_id (e.g. "obj_006"), NOT name strings.
  - Include "type_hypothesis" whenever the classification changes (even if name stays same).
  - ALWAYS reclassify any object with type_hypothesis "obstacle"/"unknown"/"static" that appears in the event list as having moved.
relationship_updates: only fill if a passive event was observed (object disappeared, game_over triggered near object, etc.).

Rules:
- Do NOT re-analyze all objects. Focus on CHANGES only.
- Do NOT suggest actions. Observe ONLY.
- Be specific about positions.
- CRITICAL: Do NOT infer effects from the action taken. Only report what you DIRECTLY SEE changed in events or images.
- CRITICAL: If events are "(none)" and images look identical → set changes="no changes observed", leave all other fields empty.
- CRITICAL: If an object moved and is currently labeled "obstacle", it MUST be reclassified. Add it to renamed_objects.
- CRITICAL: obj_id from EVENTS maps directly to instance_id in WORLD MODEL objects. Use this mapping.
- Changes in objects at the extreme corners or edges of the screen are HUD updates (step counter, score) — NOT meaningful game events. Do NOT interpret these as success signals."""
