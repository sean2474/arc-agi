from ..const import ACTION_NUM_TO_NAME
from agents.llm_agent.fmt import fmt_objects_prompt, fmt_actions, fmt_relationships


def _actions_as_names(available_actions: list[dict]) -> str:
    return ", ".join(ACTION_NUM_TO_NAME.get(a["value"], "?") for a in available_actions)


def _has_click(available_actions: list[dict]) -> bool:
    return any(
        a.get("type") == "complex" or ACTION_NUM_TO_NAME.get(a.get("value")) == "click"
        for a in available_actions
    )


def build_decide_message(
    current_subgoal: dict,
    observe_result: dict,
    objects: dict,
    available_actions: list[dict],
    summary: dict,
    world_model: dict | None = None,
    history: str = "  (none)",
) -> str:
    actions_names = _actions_as_names(available_actions)
    has_click = _has_click(available_actions)

    non_click = [ACTION_NUM_TO_NAME.get(a["value"], "?") for a in available_actions if ACTION_NUM_TO_NAME.get(a["value"]) != "click"]
    sample = non_click[:2]
    if has_click:
        sample.append('["click", "obj_001"]')
    seq_example = "[" + ", ".join(f'"{s}"' if not s.startswith("[") else s for s in sample) + "]"

    click_rule = (
        '  - Click action: ALWAYS ["click", "obj_id"] — use the obj_id key from KNOWN OBJECTS (e.g. "obj_003").\n'
        '    When exploring with no clear target, pick any obj_id to test.\n'
        '  - NEVER write "click" as a plain string.'
    ) if has_click else (
        ''
    )

    subgoal_text = current_subgoal.get("description", "(none)")
    conf = current_subgoal.get("confidence")
    if isinstance(conf, (int, float)):
        subgoal_text += f" [confidence: {conf:.1f}]"

    obs_text = observe_result.get("changes", "(none)") if observe_result else "(none)"
    history_text = history
    summary_text = summary.get("notes", "(none)") if summary else "(none)"

    wm = world_model or {}
    actions_text = fmt_actions(wm.get("actions", {}))
    rels_text = fmt_relationships(wm.get("relationships", []))

    return f"""\
GOAL: {subgoal_text}

ACTION HISTORY (action → result):
{history_text}

LAST OBSERVATION: {obs_text}

KNOWN OBJECTS
{fmt_objects_prompt(objects)}

ACTIONS
{actions_text}

RELATIONSHIPS
{rels_text}

SUMMARY: {summary_text}

An annotated image of the current frame is provided.
Available actions: [{actions_names}]

Plan a sequence of actions to achieve the current subgoal.
Use the image and object positions check the current state and determine the next action to acheive goal.

Respond in JSON:
{{
  "reasoning": "describe object positions, obstacles, and how you plan to reach the subgoal",
  "action_sequence": {seq_example},
  "subgoal": "..."
}}

Rules:
- action_sequence: 1-6 items. Available: [{actions_names}].
{click_rule}
- reasoning: MUST include current positions of key objects and why you chose this path.
- goal: Focus on achieving goal.
"""
