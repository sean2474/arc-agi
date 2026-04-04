"""에이전트 기본 타입 정의.

Agent Protocol + GameState/AgentResponse 데이터 클래스.
"""

from dataclasses import dataclass
from typing import Protocol

from arcengine import GameAction


@dataclass
class GameState:
    """게임에서 추출한 구조화된 상태. (src/ 내부용)"""

    game_id: str
    frame_raw: list  # List[ndarray]
    available_actions: list[int]
    state: str
    levels_completed: int
    step_number: int
    extracted: dict | None = None


@dataclass
class AgentResponse:
    """에이전트의 액션 선택 결과. (src/ 내부용)"""

    action: GameAction
    data: dict | None = None
    reasoning: str = ""


class Agent(Protocol):
    """에이전트 인터페이스. 구조적 서브타이핑(Protocol)으로 구현."""

    def choose_action(self, state: GameState) -> AgentResponse: ...

    def on_episode_start(self, game_id: str) -> None: ...

    def on_episode_end(self, result: str, total_steps: int) -> None: ...
