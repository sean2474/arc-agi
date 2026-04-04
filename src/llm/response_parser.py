"""LLM 응답 파싱.

에이전트들이 공통으로 사용하는 응답 파싱 로직을 추출.
Protocol 기반으로 다른 파서 구현도 가능.
"""

import json
import re
from typing import Protocol


class ResponseParser(Protocol):
    """액션 응답 파서 인터페이스."""

    def parse(self, content: str) -> tuple[int, str]: ...


class JsonActionParser:
    """LLM 응답에서 {"thinking": "...", "action": N}을 파싱한다.

    LLMAgent, VLMAgent, PAOAgent(Actor)가 공통으로 사용.
    """

    def __init__(
        self,
        max_action: int = 4,
        max_reasoning_len: int = 500,
    ) -> None:
        self._max_action = max_action
        self._max_reasoning_len = max_reasoning_len

    def parse(self, content: str) -> tuple[int, str]:
        """응답 텍스트에서 action ID와 reasoning을 추출한다.

        Returns:
            (action_id, reasoning) — action_id는 1~max_action 범위, 범위 밖이면 1.
        """
        action_match = re.search(r'"action"\s*:\s*(\d+)', content)
        action_id = int(action_match.group(1)) if action_match else 1

        if action_id < 1 or action_id > self._max_action:
            action_id = 1

        thinking_match = re.search(
            r'"thinking"\s*:\s*"(.*?)"', content, re.DOTALL
        )
        reasoning = (
            thinking_match.group(1)[: self._max_reasoning_len]
            if thinking_match
            else content[: min(200, self._max_reasoning_len)]
        )

        return action_id, reasoning


class PlannerResponseParser:
    """Planner 응답에서 {"subgoals": [...]}을 파싱한다."""

    def parse_subgoals(self, content: str) -> list[dict]:
        """응답 텍스트에서 subgoals 리스트를 추출한다.

        Returns:
            subgoals 리스트. 파싱 실패 시 빈 리스트.
        """
        match = re.search(r'"subgoals"\s*:\s*\[', content)
        if not match:
            return []

        try:
            brace_start = content.find("{")
            if brace_start < 0:
                return []

            depth = 0
            end = brace_start
            for i in range(brace_start, len(content)):
                if content[i] == "{":
                    depth += 1
                elif content[i] == "}":
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break

            data = json.loads(content[brace_start:end])
            subgoals = data.get("subgoals", [])

            # target을 리스트로 정규화
            for sg in subgoals:
                if "target" not in sg:
                    sg["target"] = [32, 32]
                elif isinstance(sg["target"], dict):
                    sg["target"] = [
                        sg["target"].get("x", 32),
                        sg["target"].get("y", 32),
                    ]
            return subgoals
        except (json.JSONDecodeError, ValueError):
            return []
