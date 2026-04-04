"""LLM 기반 게임 에이전트.

Haiku API를 호출하여 매 턴 액션을 선택한다.
PromptBuilder가 상태->프롬프트 변환을 담당하고,
LLMClient가 API 호출을 담당한다.
"""

from arcengine import GameAction

from src.agent.base import AgentResponse, GameState
from src.llm.client import LLMClient
from src.llm.prompt_builder import PromptBuilder
from src.llm.response_parser import ResponseParser


class LLMAgent:
    """LLM 기반 에이전트. Agent Protocol을 구조적으로 만족."""

    def __init__(
        self,
        client: LLMClient,
        prompt_builder: PromptBuilder,
        parser: ResponseParser,
    ) -> None:
        self._client = client
        self._prompt_builder = prompt_builder
        self._parser = parser
        self._system_prompt = prompt_builder.build_system()
        self._history: list[dict] = []

    def choose_action(self, state: GameState) -> AgentResponse:
        """LLM에게 현재 상태를 보여주고 액션을 받는다."""
        user_msg = self._prompt_builder.build_user_message(state, self._history)

        response = self._client.send(
            system=self._system_prompt,
            messages=[{"role": "user", "content": user_msg}],
        )

        action_id, reasoning = self._parser.parse(response.content)

        # 히스토리 기록
        self._history.append({
            "step": state.step_number,
            "action": GameAction.from_id(action_id).name,
            "reasoning": reasoning,
        })

        return AgentResponse(
            action=GameAction.from_id(action_id),
            reasoning=reasoning,
        )

    def on_episode_start(self, game_id: str) -> None:
        self._history = []

    def on_episode_end(self, result: str, total_steps: int) -> None:
        pass

    def get_usage(self) -> str:
        """API 사용량 요약."""
        return self._client.get_usage_summary()
