"""STEP: HYPOTHESIZE — Phase 1, SCAN 직후. 초기 가설 수립."""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...agent import LLMAgent

from ...prompts import build_hypothesize_message


def do_hypothesize(agent: LLMAgent, scan_result: dict) -> dict:
    msg = build_hypothesize_message(
        scan_result=scan_result,
        available_actions=agent.game_info.get("available_actions", []),
    )
    parsed = agent._call_llm(msg, label="hypothesize")
    if parsed is None:
        print(f"  [PARSE_FAIL] HYPOTHESIZE")
        return {}
    return parsed
