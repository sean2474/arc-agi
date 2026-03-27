"""STEP 2a: INCIDENT — game_over/level_complete 분석."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..agent import LLMAgent
    
from ..prompts import build_incident_gameover_message, build_incident_levelcomplete_message


def do_incident(
    agent: LLMAgent,
    curr_grid: list[str],
    game_over: bool = False,
    level_complete: bool = False,
    prev_level: int = 0,
    curr_level: int = 0,
) -> dict | None:
    if game_over:
        msg = build_incident_gameover_message(
            last_observations=[],
            frame_before_death=agent.prev_grid or [],
            frame_at_death=curr_grid,
        )
    elif level_complete:
        msg = build_incident_levelcomplete_message(
            prev_level=prev_level,
            curr_level=curr_level,
            last_observations=[],
            frame_before_win=agent.prev_grid or [],
            frame_at_win=curr_grid,
        )
    else:
        return None

    parsed = agent._call_llm(msg, label="incident")
    if parsed is None:
        print(f"  [PARSE_FAIL] INCIDENT")
        return None
    return parsed
