"""OBSERVE — Phase 2+ 전용. 액션 실행 후 변화만 관찰."""

import json


def build_observe_message(
    world_model: dict,
    action_taken: str,
    goal: str,
    prev_grid: list[str],
    curr_grid: list[str],
) -> str:
    return f"""\
WORLD MODEL
{json.dumps(world_model, indent=2, ensure_ascii=False)}

ACTION TAKEN: {action_taken}
GOAL: {goal}

FRAME BEFORE
{chr(10).join(prev_grid)}

FRAME AFTER
{chr(10).join(curr_grid)}

What changed after the action? Focus ONLY on differences.

STEP 1 - DIFF: Compare FRAME BEFORE and FRAME AFTER.
  Which cells changed? Which objects moved, appeared, or disappeared?
  Not all changes are meaningful — focus on changes that correlate with the action.

STEP 2 - CLASSIFY: Based on the changes:
  - Which objects moved? -> type: "dynamic"
  - Which objects stayed? -> type: "static"

STEP 3 - NEW OBJECTS: Any objects that weren't in the WORLD MODEL before?

STEP 4 - CHALLENGE: What could contradict your observations?
  - Could something classified as static actually be dynamic?
  - Did something unexpected happen?

Respond in JSON:
{{
  "changes": "...",
  "moved_objects": {{}},
  "new_objects": {{}},
  "static_objects": [],
  "contradictions": []
}}

Rules:
- Do NOT re-analyze all objects from scratch. Focus on CHANGES only.
- Do NOT suggest actions or plan. Observe ONLY.
- Be specific about positions."""
