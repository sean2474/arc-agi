"""LLMAgent 테스트.

Mock LLMClient와 ResponseParser를 주입하여 테스트.
"""

from arcengine import GameAction

from src.agent.base import GameState
from src.agent.llm_agent import LLMAgent
from src.llm.client import LLMResponse
from src.llm.prompt_builder import Ls20PromptBuilder
from src.llm.response_parser import JsonActionParser


class MockLLMClient:
    """테스트용 LLMClient. LLMClient Protocol을 구조적으로 만족."""

    def __init__(self, response_content: str = '{"thinking": "go up", "action": 1}') -> None:
        self._response_content = response_content
        self.calls: list[dict] = []

    def send(self, system: str, messages: list[dict]) -> LLMResponse:
        self.calls.append({"system": system, "messages": messages})
        return LLMResponse(
            content=self._response_content,
            input_tokens=100,
            output_tokens=50,
            model="mock",
        )

    def get_usage_summary(self) -> str:
        return f"Mock: {len(self.calls)} calls"


def _make_state(extracted: dict | None = None) -> GameState:
    return GameState(
        game_id="test",
        frame_raw=[],
        available_actions=[1, 2, 3, 4],
        state="NOT_FINISHED",
        levels_completed=0,
        step_number=0,
        extracted=extracted or {
            "player": {"x": 10, "y": 10},
            "tool": {"shape": 0, "shape_name": "shape_0", "color": 12, "color_name": "red", "rotation": 0},
            "slots": [],
            "slots_remaining": 0,
            "energy": 30,
            "max_energy": 42,
            "lives": 3,
            "level": 1,
            "tile_map": ". . .",
        },
    )


def test_llm_agent_choose_action() -> None:
    client = MockLLMClient('{"thinking": "go up to reach slot", "action": 1}')
    parser = JsonActionParser()
    builder = Ls20PromptBuilder()
    agent = LLMAgent(client=client, prompt_builder=builder, parser=parser)

    resp = agent.choose_action(_make_state())
    assert resp.action == GameAction.ACTION1
    assert "go up" in resp.reasoning
    assert len(client.calls) == 1


def test_llm_agent_action_2() -> None:
    client = MockLLMClient('{"thinking": "down", "action": 2}')
    parser = JsonActionParser()
    builder = Ls20PromptBuilder()
    agent = LLMAgent(client=client, prompt_builder=builder, parser=parser)

    resp = agent.choose_action(_make_state())
    assert resp.action == GameAction.ACTION2


def test_llm_agent_invalid_response_fallback() -> None:
    client = MockLLMClient("this is not json")
    parser = JsonActionParser()
    builder = Ls20PromptBuilder()
    agent = LLMAgent(client=client, prompt_builder=builder, parser=parser)

    resp = agent.choose_action(_make_state())
    assert resp.action == GameAction.ACTION1  # fallback


def test_llm_agent_on_episode_start_resets_history() -> None:
    client = MockLLMClient()
    parser = JsonActionParser()
    builder = Ls20PromptBuilder()
    agent = LLMAgent(client=client, prompt_builder=builder, parser=parser)

    agent.choose_action(_make_state())
    assert len(agent._history) == 1

    agent.on_episode_start("test")
    assert len(agent._history) == 0


def test_llm_agent_get_usage() -> None:
    client = MockLLMClient()
    parser = JsonActionParser()
    builder = Ls20PromptBuilder()
    agent = LLMAgent(client=client, prompt_builder=builder, parser=parser)

    assert "Mock" in agent.get_usage()
