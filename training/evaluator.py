"""Claude Evaluator — goal 달성 여부를 평가하고 reward를 반환한다.

학습 시에만 사용. before/after 프레임 + goal을 Claude에게 보여주고
0~1 점수를 받는다.
"""

import re

from src.llm.client import AnthropicClient
from src.llm.frame_renderer import frame_to_base64

EVALUATOR_SYSTEM = """You are a reward evaluator for a game-playing AI agent.

You will see:
1. A BEFORE frame (game state before the agent's actions)
2. An AFTER frame (game state after the agent's actions)
3. A GOAL description

Evaluate how much progress the agent made toward the goal.

Respond with ONLY this JSON:
{"score": 0.0, "reason": "brief explanation"}

score must be between 0.0 and 1.0:
- 1.0 = goal fully achieved
- 0.5 = meaningful progress toward goal
- 0.0 = no progress or moved away from goal
- Negative values not allowed, use 0.0 for bad outcomes"""


class Evaluator:
    """Claude 기반 goal 달성 평가자."""

    def __init__(self, model: str = "claude-sonnet-4-20250514") -> None:
        self._client = AnthropicClient(model=model, max_tokens=256)

    def evaluate(
        self,
        before_frame: list,
        after_frame: list,
        goal: str,
        steps_taken: int = 0,
    ) -> float:
        """before/after 프레임과 goal을 보고 0~1 점수를 반환한다."""
        before_b64 = frame_to_base64_from_list(before_frame)
        after_b64 = frame_to_base64_from_list(after_frame)

        content = [
            {"type": "text", "text": "BEFORE frame:"},
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": before_b64}},
            {"type": "text", "text": "AFTER frame:"},
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": after_b64}},
            {"type": "text", "text": f"GOAL: {goal}\nSteps taken: {steps_taken}"},
        ]

        response = self._client.send(
            system=EVALUATOR_SYSTEM,
            messages=[{"role": "user", "content": content}],
        )

        return self._parse_score(response.content)

    def evaluate_episode(
        self,
        first_frame: list,
        last_frame: list,
        goal: str,
        total_steps: int,
        game_state: str,
    ) -> float:
        """에피소드 전체를 평가한다. (첫 프레임 vs 마지막 프레임)"""
        score = self.evaluate(first_frame, last_frame, goal, total_steps)

        # WIN이면 보너스
        if game_state == "WIN":
            score = min(1.0, score + 0.5)

        return score

    def _parse_score(self, content: str) -> float:
        """응답에서 score를 추출한다."""
        match = re.search(r'"score"\s*:\s*([0-9.]+)', content)
        if match:
            score = float(match.group(1))
            return max(0.0, min(1.0, score))
        return 0.0

    def get_usage(self) -> str:
        return self._client.get_usage_summary()


def frame_to_base64_from_list(frame: list, scale: int = 4) -> str:
    """list[list[int]] 프레임을 base64 PNG로 변환."""
    import numpy as np
    arr = np.array(frame)
    # 3D면 첫 레이어만
    if arr.ndim == 3:
        arr = arr[0]
    return frame_to_base64(arr, scale=scale)
