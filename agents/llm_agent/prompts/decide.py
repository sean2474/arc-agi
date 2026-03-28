import json
from ..const import ACTION_NUM_TO_NAME


def _actions_as_names(available_actions: list[dict]) -> str:
    return ", ".join(ACTION_NUM_TO_NAME.get(a["value"], "?") for a in available_actions)


def build_decide_message(
    current_subgoal: dict,
    observe_result: dict,
    objects: dict,
    available_actions: list[dict],
    summary: dict,
) -> str:
    actions_names = _actions_as_names(available_actions)
    return f"""\
CURRENT SUBGOAL
{json.dumps(current_subgoal, indent=2, ensure_ascii=False)}

LAST OBSERVATION
{json.dumps(observe_result, indent=2, ensure_ascii=False)}

KNOWN OBJECTS (name, position, bbox)
{json.dumps(objects, indent=2, ensure_ascii=False)}

SUMMARY
{json.dumps(summary, indent=2, ensure_ascii=False)}

An annotated image of the current frame is provided.
Available actions: [{actions_names}]

Plan a sequence of actions to achieve the current subgoal.
Use the image and object positions/bboxes to reason about the path.

Respond in JSON:
{{
  "reasoning": "describe object positions, obstacles, and how you plan to reach the subgoal",
  "action_sequence": ["action1", "action2", ...],
  "subgoal": "..."
}}

Rules:
- action_sequence: 1–6 actions. [{actions_names}]. Click: ["click", "obj_id"].
- reasoning: MUST include current positions of key objects and why you chose this path.
- Do NOT include game goals or win conditions — only focus on achieving the current subgoal.
- If the subgoal requires clicking: ["click", "obj_id"] counts as one action."""
