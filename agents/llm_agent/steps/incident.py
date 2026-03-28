"""STEP 2a: INCIDENT — game_over/level_complete 분석."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..agent import LLMAgent
    
from ..grid_utils import grid_to_image_base64
from ..prompts import build_incident_gameover_message, build_incident_levelcomplete_message


def do_incident(
    agent: LLMAgent,
    curr_grid: list[str],
    game_over: bool = False,
    level_complete: bool = False,
    prev_level: int = 0,
    curr_level: int = 0,
) -> dict | None:
    prev_img = grid_to_image_base64(agent.prev_grid) if agent.prev_grid else grid_to_image_base64(curr_grid)
    curr_img = grid_to_image_base64(curr_grid)

    if game_over:
        msg = build_incident_gameover_message()
    elif level_complete:
        msg = build_incident_levelcomplete_message(prev_level=prev_level, curr_level=curr_level)
    else:
        return None

    parsed = agent._call_vlm(msg, [prev_img, curr_img], label="incident")
    if parsed is None:
        print(f"  [PARSE_FAIL] INCIDENT")
        return None
    return parsed
