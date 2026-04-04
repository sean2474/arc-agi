"""LLM 기반 게임 에이전트.

Haiku API를 호출하여 매 턴 액션을 선택한다.
PromptBuilder가 상태→프롬프트 변환을 담당하고,
AnthropicClient가 API 호출을 담당한다.
"""

import json

from arcengine import GameAction

from src.agent.base import Agent, AgentResponse, GameState
from src.llm.client import AnthropicClient
from src.llm.prompt_builder import PromptBuilder


class LLMAgent(Agent):
    """LLM 기반 에이전트."""

    def __init__(
        self,
        client: AnthropicClient,
        prompt_builder: PromptBuilder,
    ) -> None:
        self._client = client
        self._prompt_builder = prompt_builder
        self._system_prompt = prompt_builder.build_system()
        self._history: list[dict] = []

    def choose_action(self, state: GameState) -> AgentResponse:
        """LLM에게 현재 상태를 보여주고 액션을 받는다."""
        user_msg = self._prompt_builder.build_user_message(state, self._history)

        response = self._client.send(
            system=self._system_prompt,
            messages=[{"role": "user", "content": user_msg}],
        )

        action, reasoning = self._parse_response(response.content)

        # 히스토리 기록
        self._history.append({
            "step": state.step_number,
            "action": action.name,
            "reasoning": reasoning,
        })

        return AgentResponse(
            action=action,
            reasoning=reasoning,
        )

    def _parse_response(self, content: str) -> tuple[GameAction, str]:
        """LLM 응답을 파싱하여 GameAction과 reasoning을 추출한다."""
        import re

        # 1차: "action": N 패턴으로 action 추출 (JSON 파싱 실패에도 동작)
        action_match = re.search(r'"action"\s*:\s*(\d+)', content)
        action_id = int(action_match.group(1)) if action_match else 1

        if action_id < 1 or action_id > 4:
            action_id = 1

        # thinking 추출: "thinking": "..." 패턴
        thinking_match = re.search(r'"thinking"\s*:\s*"(.*?)"(?:\s*[,}])', content, re.DOTALL)
        reasoning = thinking_match.group(1)[:500] if thinking_match else content[:200]

        return GameAction.from_id(action_id), reasoning

    def on_episode_start(self, game_id: str) -> None:
        self._history = []

    def on_episode_end(self, result: str, total_steps: int) -> None:
        pass

    def get_usage(self) -> str:
        """API 사용량 요약."""
        return self._client.get_usage_summary()
