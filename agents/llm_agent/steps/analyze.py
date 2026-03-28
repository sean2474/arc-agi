"""STEP: ACTION ANALYZER — continue/abort/success 판정."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..agent import LLMAgent

from ..prompts import build_analyze_message


def do_analyze(
    agent: LLMAgent,
    current_subgoal: dict,
    planned_sequence: list[str],
    executed_action: str,
    remaining_sequence: list[str],
    observe_result: dict,
) -> dict:
    """Action Analyzer 실행. {status, reason, discoveries} 반환."""
    msg = build_analyze_message(
        current_subgoal=current_subgoal,
        planned_sequence=planned_sequence,
        executed_action=executed_action,
        remaining_sequence=remaining_sequence,
        observe_result=observe_result,
    )
    parsed = agent._call_vlm(msg, label="analyze")

    if parsed is None:
        print("  [PARSE_FAIL] ANALYZE, defaulting to continue")
        return {"status": "continue", "reason": "parse failed", "discoveries": []}

    status = parsed.get("status", "continue")
    if status not in ("continue", "abort", "success"):
        status = "continue"

    return {
        "status": status,
        "reason": parsed.get("reason", ""),
        "discoveries": parsed.get("discoveries", []),
    }
