"""STEP 3: EVALUATE — 결과 평가."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent import LLMAgent

from agent.prompts import build_evaluate_message


def do_evaluate(
    agent: LLMAgent,
    observe_result: dict,
    incident_result: dict | None = None,
) -> tuple[dict, list]:
    """(report, discoveries) 반환."""
    last_action = agent.last_action or "unknown"
    subgoal = agent.current_subgoal or {}
    last_goal = subgoal.get("description", "")
    success_condition = subgoal.get("success_condition", "")
    failure_condition = subgoal.get("failure_condition", "")
    planned = getattr(agent, "planned_sequence", [last_action])

    msg = build_evaluate_message(
        sequence_goal=last_goal,
        success_condition=success_condition,
        failure_condition=failure_condition,
        planned_sequence=planned,
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
