"""호환용 데이터 클래스. 공식 Agent는 agents/agent.py를 사용.

기존 src/ 모듈이 참조하는 GameState, AgentResponse만 유지.
Agent ABC는 제거됨 — 공식 agents.agent.Agent를 직접 상속할 것.
"""

from dataclasses import dataclass
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
