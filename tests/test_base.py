"""Agent base 데이터 클래스 + Protocol 테스트."""

from arcengine import GameAction

from src.agent.base import Agent, AgentResponse, GameState


def test_game_state_creation() -> None:
    state = GameState(
        game_id="test",
        frame_raw=[],
        available_actions=[1, 2, 3, 4],
        state="NOT_FINISHED",
        levels_completed=0,
        step_number=0,
    )
    assert state.game_id == "test"
    assert state.extracted is None


def test_game_state_with_extracted() -> None:
    state = GameState(
        game_id="test",
        frame_raw=[],
        available_actions=[1],
        state="NOT_FINISHED",
        levels_completed=0,
        step_number=0,
        extracted={"player": (10, 20)},
    )
    assert state.extracted == {"player": (10, 20)}


def test_agent_response() -> None:
    resp = AgentResponse(action=GameAction.ACTION1, reasoning="test")
    assert resp.action == GameAction.ACTION1
    assert resp.data is None


def test_agent_response_with_data() -> None:
    resp = AgentResponse(
        action=GameAction.ACTION6,
        data={"x": 32, "y": 32},
        reasoning="click",
    )
    assert resp.data == {"x": 32, "y": 32}
    assert resp.reasoning == "click"


def test_agent_protocol_is_importable() -> None:
    """Agent Protocol이 정상적으로 import 가능한지 확인."""
    assert hasattr(Agent, "choose_action")
    assert hasattr(Agent, "on_episode_start")
    assert hasattr(Agent, "on_episode_end")
