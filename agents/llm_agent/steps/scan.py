"""STEP: SCAN — Phase 1 전용. 첫 프레임 전체 분석."""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..agent import LLMAgent

from ..prompts import build_scan_message


def do_scan(agent: LLMAgent, step: int, curr_grid: list[str], curr_levels: int) -> dict:
    msg = build_scan_message(
        game_id=agent.game_info.get("game_id", "unknown"),
        available_actions=agent.game_info.get("available_actions", []),
        levels_completed=curr_levels,
        win_levels=agent.game_info.get("win_levels", 0),
        step=step,
        grid=curr_grid,
    )
    parsed = agent._call_llm(msg, label="scan")
    if parsed is None:
        print(f"  [PARSE_FAIL] SCAN")
        return {"objects": {}, "patterns": []}
    return parsed
