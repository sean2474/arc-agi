"""STEP: DECIDE — action_sequence 계획. 이미지 포함."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent import LLMAgent

import re as _re

from agent.grid_utils import grid_to_image_base64_annotated, grid_to_image_base64
from agent.prompts import build_decide_message
from agent.fmt import fmt_history


def _no_effect_click_ids(history) -> set:
    """history에서 click 후 no changes observed인 obj_id 집합 반환."""
    result = set()
    for r in history:
        action = r.action or ""
        obs = (r.observation or "").strip().lower()
        if "no changes" in obs and action.startswith("click(obj_"):
            m = _re.search(r"click\((obj_\d+)", action)
            if m:
                result.add(m.group(1))
    return result


def do_decide(agent: LLMAgent, current_subgoal: dict, observe_result: dict, curr_grid: list[str]) -> list[str]:
    """action_sequence (list[str]) 반환."""
    objects = agent.world_model.get_objects()
    if objects:
        curr_img = grid_to_image_base64_annotated(curr_grid, objects)
    else:
        curr_img = grid_to_image_base64(curr_grid)

    excluded = _no_effect_click_ids(agent.history)

    wm_prompt = agent.world_model.to_prompt_dict()
    msg = build_decide_message(
        current_subgoal=current_subgoal,
        observe_result=observe_result,
        objects=wm_prompt.get("objects", []),
        available_actions=agent.game_info.get("available_actions", []),
        summary=agent.summary,
        world_model=wm_prompt,
        history=fmt_history(agent.history[-20:]),
        excluded_click_ids=excluded if excluded else None,
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
