"""LLMAgent 파싱 테스트. (API 호출 없이 파싱 로직만)"""

from arcengine import GameAction

from src.agent.llm_agent import LLMAgent


def test_parse_valid_json() -> None:
    # _parse_response는 인스턴스 메서드이므로 직접 테스트
    # client/builder 없이 파싱만 테스트
    agent = LLMAgent.__new__(LLMAgent)

    action, reasoning = agent._parse_response(
        '{"thinking": "go up to reach slot", "action": 1}'
    )
    assert action == GameAction.ACTION1
    assert "go up" in reasoning


def test_parse_action_2() -> None:
    agent = LLMAgent.__new__(LLMAgent)
    action, _ = agent._parse_response('{"thinking": "down", "action": 2}')
    assert action == GameAction.ACTION2


def test_parse_invalid_json_fallback() -> None:
    agent = LLMAgent.__new__(LLMAgent)
    action, reasoning = agent._parse_response("this is not json")
    assert action == GameAction.ACTION1  # fallback
    assert "parse error" in reasoning


def test_parse_out_of_range_action() -> None:
    agent = LLMAgent.__new__(LLMAgent)
    action, _ = agent._parse_response('{"thinking": "test", "action": 99}')
    assert action == GameAction.ACTION1  # fallback to 1
