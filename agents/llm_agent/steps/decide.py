"""STEP: DECIDE — action_sequence 계획. 이미지 포함."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..agent import LLMAgent

from ..grid_utils import grid_to_image_base64_annotated, grid_to_image_base64
from ..prompts import build_decide_message


def do_decide(agent: LLMAgent, current_subgoal: dict, observe_result: dict, curr_grid: list[str]) -> list[str]:
    """action_sequence (list[str]) 반환."""
    objects = agent.world_model.get_objects()
    if objects:
        curr_img = grid_to_image_base64_annotated(curr_grid, objects)
    else:
        curr_img = grid_to_image_base64(curr_grid)

    msg = build_decide_message(
        current_subgoal=current_subgoal,
        observe_result=observe_result,
        objects=agent.world_model.to_prompt_dict().get("objects", []),
        available_actions=agent.game_info.get("available_actions", []),
        summary=agent.summary,
    )
    parsed = agent._call_vlm(msg, [curr_img], label="decide")

    if parsed is None:
        raise RuntimeError("DECIDE: VLM returned None (parse failed)")

    seq = parsed.get("action_sequence")
    if not seq or not isinstance(seq, list):
        raise RuntimeError(f"DECIDE: missing or invalid action_sequence in response: {parsed}")

    # 유효성 필터: action name 또는 click 리스트
    valid = [a for a in seq[:6] if isinstance(a, (str, list))]
    if not valid:
        raise RuntimeError(f"DECIDE: action_sequence is empty after filtering: {seq}")
    return valid
