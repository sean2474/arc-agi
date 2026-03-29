"""STEP: OBSERVE — Phase 2+ 전용. VLM + 코드 diff."""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..agent import LLMAgent

from ..grid_utils import (
    grid_to_image_base64, grid_to_image_base64_annotated,
    blobs_to_annotation_dict, summarize_diff,
)
from ..prompts.fmt import format_events_for_prompt
from ..prompts import build_observe_message


def do_observe(
    agent: LLMAgent,
    action_taken: str,
    goal: str,
    prev_grid: list[str],
    curr_grid: list[str],
    blobs: dict | None = None,
    animation_events: list[dict] | None = None,
    result_events: list[dict] | None = None,
) -> dict:
    if blobs:
        ann = blobs_to_annotation_dict(blobs)
        before_img = grid_to_image_base64(prev_grid)
        after_img  = grid_to_image_base64_annotated(curr_grid, ann, label_mode="name")
    else:
        objects = agent.world_model.get_objects()
        if objects:
            before_img = grid_to_image_base64(prev_grid)
            after_img  = grid_to_image_base64_annotated(curr_grid, objects)
        else:
            before_img = grid_to_image_base64(prev_grid)
            after_img  = grid_to_image_base64(curr_grid)

    if animation_events is not None or result_events is not None:
        events_text = format_events_for_prompt(animation_events or [], result_events or [])
        diff_summary = ""
    else:
        events_text = ""
        diff_summary = summarize_diff(prev_grid, curr_grid)

    msg = build_observe_message(
        world_model=agent.world_model.to_prompt_dict(),
        action_taken=action_taken,
        goal=goal,
        diff_summary=diff_summary,
        events_text=events_text,
    )
    parsed = agent._call_vlm(msg, [before_img, after_img], label="observe")
    if parsed is None:
        raise RuntimeError("OBSERVE: VLM returned None (parse failed)")
    return parsed
