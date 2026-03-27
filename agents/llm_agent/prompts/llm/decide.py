import json
from ...const import ACTION_NUM_TO_NAME


def _actions_as_names(available_actions: list[dict]) -> str:
    return ", ".join(ACTION_NUM_TO_NAME.get(a["value"], "?") for a in available_actions)


def build_decide_message(
    observe_result: dict,
    summary: dict,
    world_model: dict,
    reports: list[dict],
    available_actions: list[dict],
    hint: str = "",
) -> str:
    reports_str = json.dumps(reports[-3:], indent=2, ensure_ascii=False) if reports else "[]"
    actions_names = _actions_as_names(available_actions)
    hint_section = f"\n>> {hint}\n" if hint else ""
    return f"""\
OBSERVATION RESULT
{json.dumps(observe_result, indent=2, ensure_ascii=False)}

WORLD MODEL (structured knowledge with confidence)
{json.dumps(world_model, indent=2, ensure_ascii=False)}

SUMMARY (accumulated knowledge)
{json.dumps(summary, indent=2, ensure_ascii=False)}

RECENT REPORTS (last 3)
{reports_str}
{hint_section}
Available actions: [{actions_names}]

Choose ONE action to take next.

You MUST answer:
1. What is your current win condition hypothesis?
2. What will this single action test or accomplish?
3. How will you know if it succeeded?

Respond in JSON:
{{
  "win_condition_hypothesis": "...",
  "reasoning": "...",
  "action": "...",
  "goal": "...",
  "success_condition": "...",
  "failure_condition": "..."
}}

Rules:
- action: ONE action name. [{actions_names}]. Click: ["click", "object_id"].
- goal: MUST be specific and verifiable. The system needs to check success/failure.
  BAD: "explore the area"  GOOD: "test what happens when action X is taken"
- Prioritize testing actions with LOW confidence in the WORLD MODEL.
- Check REPORTS to avoid repeating failed strategies."""
