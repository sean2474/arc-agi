"""우리 에이전트 — 공식 Agent 인터페이스 직접 구현.

현재는 랜덤 기반으로 시작. 이후 src/ 모듈을 연결하여 확장.
"""

import random
import time
from typing import Any

from arcengine import FrameData, GameAction, GameState

from ..agent import Agent


class OurAgent(Agent):
    """ARC-AGI-3 에이전트 — 공식 Agent 인터페이스."""

    MAX_ACTIONS = 500

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        seed = int(time.time() * 1000000) + hash(self.game_id) % 1000000
        random.seed(seed)

    def is_done(self, frames: list[FrameData], latest_frame: FrameData) -> bool:
        return latest_frame.state is GameState.WIN

    def choose_action(
        self, frames: list[FrameData], latest_frame: FrameData
    ) -> GameAction:
        # 게임 시작/오버 시 리셋
        if latest_frame.state in [GameState.NOT_PLAYED, GameState.GAME_OVER]:
            action = GameAction.RESET
            action.reasoning = "Reset: game not started or game over"
            return action

        # 랜덤 액션 (향후 src/ 로직으로 교체)
        action = random.choice([a for a in GameAction if a is not GameAction.RESET])

        if action.is_simple():
            action.reasoning = f"Random action: {action.value}"
        elif action.is_complex():
            action.set_data({
                "x": random.randint(0, 63),
                "y": random.randint(0, 63),
            })
            action.reasoning = {"action": action.value, "policy": "random"}

        return action
