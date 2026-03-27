import json
from ..const import ACTION_NUM_TO_NAME


def _actions_as_names(available_actions: list[dict]) -> str:
    return ", ".join(ACTION_NUM_TO_NAME.get(a["value"], "?") for a in available_actions)


def build_decide_message(
    observe_result: dict,
    summary: dict,
    world_model: dict,
    reports: list[dict],
    available_actions: list[dict],
    max_len: int,
    hint: str = "",
) -> str:
    reports_str = json.dumps(reports[-3:], indent=2, ensure_ascii=False) if reports else "[]"
    actions_names = _actions_as_names(available_actions)
    hint_section = f"\n⚠️ {hint}\n" if hint else ""
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
CONSTRAINT: max sequence length = {max_len}
Available actions: [{actions_names}]

Based on the observation and world model, decide what to do next.

You MUST answer:
1. What is your current win condition hypothesis?
2. What specific thing will this sequence test or accomplish?
3. How will you know if it succeeded or failed?

Respond in JSON:
{{
  "win_condition_hypothesis": "reach the teal(b) region at row 61",
  "reasoning": "why this action sequence",
  "sequence": ["down"],
  "sequence_goal": "move player from (40,38) to (41,38) to test if down moves player",
  "success_condition": "player position changes to row 41",
  "failure_condition": "no change in grid",
  "confidence": 0.4,
  "replan_conditions": ["no_change", "game_over", "new_value"]
}}

Rules:
- win_condition_hypothesis: REQUIRED.
- sequence: use action NAMES [{actions_names}]. Click: ["click", x, y].
  You can return 1 to {max_len} actions. Fewer is fine when uncertain.
- sequence_goal: MUST be specific with coordinates or verifiable conditions.
  BAD: "explore the area"  GOOD: "move to row 45 col 30"
- success_condition / failure_condition: EVALUATE uses these to judge.
- Prioritize testing actions with LOW confidence in the WORLD MODEL.
- Check REPORTS to avoid repeating failed strategies."""
