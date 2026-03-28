"""STEP 2: DECIDE — 1개 액션 결정."""
from __future__ import annotations

import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..agent import LLMAgent

from arcengine import GameAction

from ..actions import action_to_gameaction
from ..const import get_phase_hint
from ..prompts import build_decide_message


def do_decide(agent: LLMAgent, observe_result: dict) -> tuple[GameAction, str, str | None, str]:
    """(action, action_name, reasoning, goal) 반환."""
    hint = get_phase_hint(agent.world_model.to_dict())

    msg = build_decide_message(
        observe_result=observe_result,
        summary=agent.summary,
        world_model=agent.world_model.to_dict(),
        reports=agent.reports,
        available_actions=agent.game_info.get("available_actions", []),
        hint=hint,
    )
    parsed = agent._call_vlm(msg, label="decide")

    if parsed is None:
        print(f"  [PARSE_FAIL] DECIDE, random fallback")
        val = random.choice(list(agent.available_values))
        result = action_to_gameaction(val, agent.available_values)
        action, name = result if result else (GameAction.ACTION1, "up")
        return action, name, None, "random (parse failed)"

    raw_action = parsed.get("action", "up")
    result = action_to_gameaction(raw_action, agent.available_values, world_model=agent.world_model.to_dict())
    if result is None:
        result = (GameAction.ACTION1, "up")
    action, action_name = result

    reasoning = parsed.get("reasoning", "")
    goal = parsed.get("goal", "")
    agent.success_condition = parsed.get("success_condition", "")
    agent.failure_condition = parsed.get("failure_condition", "")

    return action, action_name, reasoning, goal
