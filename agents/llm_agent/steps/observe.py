"""STEP: OBSERVE — Phase 2+ 전용. 액션 실행 후 변화만 관찰."""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..agent import LLMAgent

from ..prompts import build_observe_message


def do_observe(agent: LLMAgent, action_taken: str, goal: str, prev_grid: list[str], curr_grid: list[str]) -> dict:
    msg = build_observe_message(
        world_model=agent.world_model.to_dict(),
        action_taken=action_taken,
        goal=goal,
        prev_grid=prev_grid,
        curr_grid=curr_grid,
    )
    parsed = agent._call_llm(msg, label="observe")
    if parsed is None:
        print(f"  [PARSE_FAIL] OBSERVE")
        return {"changes": "unknown", "moved_objects": {}, "new_objects": {}, "contradictions": []}
    return parsed
