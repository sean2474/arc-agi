"""VLM 기반 게임 에이전트.

매 스텝 프레임 이미지를 보고 액션 1개를 선택한다.
매번 최신 프레임을 보므로 벽에 막히면 바로 방향 전환 가능.
"""

import re

from arcengine import GameAction

from src.agent.base import Agent, AgentResponse, GameState
from src.llm.client import AnthropicClient
from src.llm.prompt_builder import PromptBuilder


class VLMAgent(Agent):
    """VLM 기반 에이전트 — 매 스텝 이미지 + 단일 액션."""

    def __init__(
        self,
        client: AnthropicClient,
        prompt_builder: PromptBuilder,
    ) -> None:
        self._client = client
        self._prompt_builder = prompt_builder
        self._system = prompt_builder.build_system()
        self._history: list[dict] = []

    def choose_action(self, state: GameState) -> AgentResponse:
        """매 스텝 VLM 호출하여 액션 1개를 받는다."""
        content = self._prompt_builder.build_user_message(state, self._history)

        if isinstance(content, list):
            messages = [{"role": "user", "content": content}]
        else:
            messages = [{"role": "user", "content": content}]

        response = self._client.send(system=self._system, messages=messages)
        action_id, reasoning = self._parse_response(response.content)

        self._history.append({
            "step": state.step_number,
            "action": f"ACTION{action_id}",
            "reasoning": reasoning,
            "player_pos": state.extracted.get("player", {}) if state.extracted else {},
        })

        return AgentResponse(
            action=GameAction.from_id(action_id),
            reasoning=reasoning,
        )

    def _parse_response(self, content: str) -> tuple[int, str]:
        """VLM 응답에서 단일 액션과 reasoning을 추출한다."""
        action_match = re.search(r'"action"\s*:\s*(\d+)', content)
        action_id = int(action_match.group(1)) if action_match else 1

        if action_id < 1 or action_id > 4:
            action_id = 1

        thinking_match = re.search(r'"thinking"\s*:\s*"(.*?)"', content, re.DOTALL)
        reasoning = thinking_match.group(1)[:500] if thinking_match else content[:200]

        return action_id, reasoning

    def on_episode_start(self, game_id: str) -> None:
        self._history = []

    def on_episode_end(self, result: str, total_steps: int) -> None:
        pass

    def get_usage(self) -> str:
        return self._client.get_usage_summary()
