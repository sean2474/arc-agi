"""STEP 3: EVALUATE — 결과 평가."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...agent import LLMAgent
    
from ...prompts import build_evaluate_message


def do_evaluate(
    agent: LLMAgent,
    observe_result: dict,
    incident_result: dict | None = None,
) -> tuple[dict, list]:
    """(report, discoveries) 반환."""
    last_action = agent.last_action or "unknown"
    last_goal = agent.last_goal or ""

    msg = build_evaluate_message(
        sequence_goal=last_goal,
        success_condition=agent.success_condition,
        failure_condition=agent.failure_condition,
        planned_sequence=[last_action],
        executed_actions=[last_action],
        abort_reason=None,
        observe_result=observe_result,
        incident_result=incident_result,
    )
    parsed = agent._call_vlm(msg, label="evaluate")

    if parsed is None:
        print(f"  [PARSE_FAIL] EVALUATE")
        return {
            "goal": last_goal,
            "action": last_action,
            "goal_achieved": False,
            "reasoning": "evaluate parse failed",
            "key_learnings": [],
        }, []

    report = parsed.get("report", {})
    discoveries = parsed.get("new_discoveries", [])
    return report, discoveries
