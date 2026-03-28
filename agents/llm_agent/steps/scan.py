"""STEP: SCAN — Phase 1 전용. VLM으로 첫 프레임 전체 분석."""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..agent import LLMAgent

from ..grid_utils import grid_to_image_base64
from ..prompts import build_scan_message


def do_scan(agent: LLMAgent, step: int, curr_grid: list[str], curr_levels: int) -> dict:
    img_b64 = grid_to_image_base64(curr_grid)
    msg = build_scan_message(
        game_id=agent.game_info.get("game_id", "unknown"),
        available_actions=agent.game_info.get("available_actions", []),
        levels_completed=curr_levels,
        win_levels=agent.game_info.get("win_levels", 0),
        step=step,
        grid=curr_grid,
    )
    parsed = agent._call_vlm(msg, [img_b64], label="scan", thinking_budget=4096)
    if parsed is None:
        raise RuntimeError("SCAN: VLM returned None (parse failed)")
    # LLM이 list로 반환한 경우 obj_NNN dict로 변환
    raw_objects = parsed.get("objects", {})
    if isinstance(raw_objects, list):
        parsed["objects"] = {
            f"obj_{i+1:03d}": obj
            for i, obj in enumerate(raw_objects)
            if isinstance(obj, dict)
        }
    return parsed
