"""ACTION ANALYZER — 시퀀스 실행 중 매 action 후 continue/abort/success 판정."""

import json


def build_analyze_message(
    current_subgoal: dict,
    planned_sequence: list[str],
    executed_action: str,
    remaining_sequence: list[str],
    observe_result: dict,
) -> str:
    return f"""\
CURRENT SUBGOAL
{json.dumps(current_subgoal, indent=2, ensure_ascii=False)}

PLANNED SEQUENCE
{json.dumps(planned_sequence, ensure_ascii=False)}

JUST EXECUTED
{json.dumps(executed_action, ensure_ascii=False)}

REMAINING SEQUENCE
{json.dumps(remaining_sequence, ensure_ascii=False)}

OBSERVATION RESULT (after executed action)
{json.dumps(observe_result, indent=2, ensure_ascii=False)}

Determine whether to continue the planned sequence, abort and re-plan, or declare success.

Respond in JSON:
{{
  "status": "continue | abort | success",
  "reason": "...",
  "discoveries": []
}}

Rules:
- continue: observation matches expectations. Proceed with remaining sequence.
- abort: unexpected change detected (e.g. unexpected object moved/disappeared, game state changed in an unplanned way).
  Abort means the remaining sequence is no longer valid. The planner will re-plan.
- success: the subgoal has been achieved. Mark plan as done.
- discoveries: list of new facts learned (even on continue). Can be empty.
- Be honest. Do NOT rationalize failures as success."""
