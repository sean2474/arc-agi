"""StateExtractor 테스트."""

import numpy as np

from src.agent.base import GameState
from src.env.state_extractor import DefaultExtractor


def test_default_extractor_color_distribution() -> None:
    frame = np.zeros((64, 64), dtype=np.int_)
    frame[0:10, 0:10] = 5  # 100 pixels of color 5
    frame[10:20, 0:10] = 3  # 100 pixels of color 3

    state = GameState(
        game_id="test",
        frame_raw=[frame],
        available_actions=[1],
        state="NOT_FINISHED",
        levels_completed=0,
        step_number=0,
    )

    extractor = DefaultExtractor()
    result = extractor.extract(state)

    assert result["frame_shape"] == (64, 64)
    assert result["color_distribution"][5] == 100
    assert result["color_distribution"][3] == 100
    assert result["color_distribution"][0] == 64 * 64 - 200


def test_default_extractor_empty_frame() -> None:
    state = GameState("test", [], [1], "NOT_FINISHED", 0, 0)
    extractor = DefaultExtractor()
    result = extractor.extract(state)
    assert result == {}
