"""PromptBuilder 테스트."""

from src.agent.base import GameState
from src.llm.prompt_builder import Ls20PromptBuilder


def test_system_prompt_has_rules() -> None:
    builder = Ls20PromptBuilder()
    system = builder.build_system()
    assert "ACTION1" in system
    assert "Move up" in system
    assert "Shape pad" in system
    assert "JSON" in system


def test_user_message_with_extracted_state() -> None:
    builder = Ls20PromptBuilder()
    state = GameState(
        game_id="ls20",
        frame_raw=[],
        available_actions=[1, 2, 3, 4],
        state="NOT_FINISHED",
        levels_completed=0,
        step_number=5,
        extracted={
            "player": {"x": 20, "y": 30},
            "tool": {
                "shape": 0,
                "shape_name": "shape_0",
                "color": 12,
                "color_name": "red",
                "rotation": 0,
            },
            "slots": [
                {
                    "index": 0,
                    "x": 35,
                    "y": 10,
                    "required_shape": 2,
                    "required_color": 9,
                    "required_rotation": 90,
                    "matches_current": False,
                }
            ],
            "slots_remaining": 1,
            "energy": 30,
            "max_energy": 42,
            "lives": 3,
            "level": 1,
            "tile_map": " . . .\n . P .\n . . .",
        },
    )

    msg = builder.build_user_message(state, [])
    assert "Position: (20, 30)" in msg
    assert "shape=0" in msg
    assert "Lives: 3/3" in msg
    assert "Slot 0" in msg


def test_user_message_no_state() -> None:
    builder = Ls20PromptBuilder()
    state = GameState("ls20", [], [1], "NOT_FINISHED", 0, 0, extracted=None)
    msg = builder.build_user_message(state, [])
    assert "No state" in msg
