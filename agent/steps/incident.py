"""STEP 2a: INCIDENT — game_over/level_complete 분석."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent import LLMAgent
    
from agent.grid_utils import (
    grid_to_image_base64, grid_to_image_base64_annotated, blobs_to_annotation_dict
)
from agent.prompts import build_incident_gameover_message, build_incident_levelcomplete_message


def do_incident(
    agent: LLMAgent,
    curr_grid: list[str],
    game_over: bool = False,
    level_complete: bool = False,
    prev_level: int = 0,
    curr_level: int = 0,
    level_transition_info: dict | None = None,
) -> dict | None:
    blobs = agent._blob_manager.blobs if agent._blob_manager else None

    if agent.prev_grid:
        if blobs:
            ann = blobs_to_annotation_dict(blobs)
            prev_img = grid_to_image_base64_annotated(agent.prev_grid, ann, label_mode="name")
        else:
            prev_img = grid_to_image_base64(agent.prev_grid)
    else:
        prev_img = grid_to_image_base64(curr_grid)

    if blobs:
        ann = blobs_to_annotation_dict(blobs)
        curr_img = grid_to_image_base64_annotated(curr_grid, ann, label_mode="name")
    else:
        curr_img = grid_to_image_base64(curr_grid)

    if game_over:
        msg = build_incident_gameover_message()
    elif level_complete:
        msg = build_incident_levelcomplete_message(
            prev_level=prev_level,
            curr_level=curr_level,
            level_transition_info=level_transition_info,
            blobs=blobs,
        )
    else:
        return None

    parsed = agent._call_vlm(msg, [prev_img, curr_img], label="incident")
    if parsed is None:
        print(f"  [PARSE_FAIL] INCIDENT")
        return None
    return parsed
