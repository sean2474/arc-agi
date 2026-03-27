"""STEP 1: OBSERVE — 순수 관찰."""

from ..prompts import build_observe_message


def do_observe(agent, step: int, curr_grid: list[str], curr_levels: int) -> dict:
    msg = build_observe_message(
        game_id=agent.game_info.get("game_id", "unknown"),
        available_actions=agent.game_info.get("available_actions", []),
        levels_completed=curr_levels,
        win_levels=agent.game_info.get("win_levels", 0),
        step=step,
        summary=agent.summary,
        world_model=agent.world_model,
        grid=curr_grid,
        prev_grid=agent.prev_grid,
    )
    parsed = agent._call_llm(msg)
    if parsed is None:
        print(f"  [PARSE_FAIL] OBSERVE")
        return {"values": {}, "patterns": [], "unknowns": ["observe failed"]}
    return parsed
