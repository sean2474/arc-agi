"""Agent base 인터페이스 테스트."""

from arcengine import GameAction

from src.agent.base import Agent, AgentResponse, GameState


class DummyAgent(Agent):
    """테스트용 더미 에이전트."""

    def choose_action(self, state: GameState) -> AgentResponse:
        return AgentResponse(action=GameAction.ACTION1, reasoning="dummy")


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


def test_agent_response() -> None:
    resp = AgentResponse(action=GameAction.ACTION1, reasoning="test")
    assert resp.action == GameAction.ACTION1
    assert resp.data is None


def test_dummy_agent() -> None:
    agent = DummyAgent()
    state = GameState("test", [], [1], "NOT_FINISHED", 0, 0)
    resp = agent.choose_action(state)
    assert resp.action == GameAction.ACTION1
