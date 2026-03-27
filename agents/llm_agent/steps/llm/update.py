"""STEP 4: UPDATE — summary + world_model 갱신."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...agent import LLMAgent
    
from ...prompts import build_update_message


def do_update(agent: LLMAgent, evaluation: dict, discoveries: list[str], incident_result: dict | None = None):
    msg = build_update_message(
        summary=agent.summary,
        world_model=agent.world_model.to_dict(),
        evaluation=evaluation,
        discoveries=discoveries,
        incident_result=incident_result,
    )
    parsed = agent._call_llm(msg, label="update")

    if parsed is None:
        print(f"  [PARSE_FAIL] UPDATE, keeping current state")
        return

    updated = parsed.get("updated_summary")
    if updated and isinstance(updated, dict):
        agent.summary = updated

    updated_wm = parsed.get("updated_world_model")
    if updated_wm and isinstance(updated_wm, dict):
        agent.world_model.apply_llm_update(updated_wm)
