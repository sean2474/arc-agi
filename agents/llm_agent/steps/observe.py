"""STEP: OBSERVE — Phase 2+ 전용. VLM + 코드 diff."""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..agent import LLMAgent

from ..grid_utils import grid_to_image_base64, grid_to_image_base64_annotated, summarize_diff
from ..prompts import build_observe_message


def do_observe(agent: LLMAgent, action_taken: str, goal: str, prev_grid: list[str], curr_grid: list[str]) -> dict:
    diff_summary = summarize_diff(prev_grid, curr_grid)
    objects = agent.world_model.get_objects()
    if objects:
        before_img = grid_to_image_base64_annotated(prev_grid, objects)
        after_img = grid_to_image_base64_annotated(curr_grid, objects)
    else:
        before_img = grid_to_image_base64(prev_grid)
        after_img = grid_to_image_base64(curr_grid)

    msg = build_observe_message(
        world_model=agent.world_model.to_prompt_dict(),
        action_taken=action_taken,
        goal=goal,
        diff_summary=diff_summary,
    )
    parsed = agent._call_vlm(msg, [before_img, after_img], label="observe")
    if parsed is None:
        raise RuntimeError("OBSERVE: VLM returned None (parse failed)")
    return parsed
