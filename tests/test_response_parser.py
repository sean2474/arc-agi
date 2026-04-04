"""ResponseParser 테스트."""

from src.llm.response_parser import JsonActionParser, PlannerResponseParser


# --- JsonActionParser ---


def test_parse_valid_json() -> None:
    parser = JsonActionParser()
    action_id, reasoning = parser.parse(
        '{"thinking": "go up to reach slot", "action": 1}'
    )
    assert action_id == 1
    assert "go up" in reasoning


def test_parse_action_2() -> None:
    parser = JsonActionParser()
    action_id, _ = parser.parse('{"thinking": "down", "action": 2}')
    assert action_id == 2


def test_parse_action_3() -> None:
    parser = JsonActionParser()
    action_id, _ = parser.parse('{"thinking": "left", "action": 3}')
    assert action_id == 3


def test_parse_action_4() -> None:
    parser = JsonActionParser()
    action_id, _ = parser.parse('{"thinking": "right", "action": 4}')
    assert action_id == 4


def test_parse_invalid_input_fallback() -> None:
    parser = JsonActionParser()
    action_id, reasoning = parser.parse("this is not json")
    assert action_id == 1  # fallback
    assert "this is not json" in reasoning


def test_parse_out_of_range_action() -> None:
    parser = JsonActionParser()
    action_id, _ = parser.parse('{"thinking": "test", "action": 99}')
    assert action_id == 1  # fallback to 1


def test_parse_zero_action() -> None:
    parser = JsonActionParser()
    action_id, _ = parser.parse('{"thinking": "test", "action": 0}')
    assert action_id == 1  # fallback


def test_parse_custom_max_action() -> None:
    parser = JsonActionParser(max_action=7)
    action_id, _ = parser.parse('{"thinking": "test", "action": 6}')
    assert action_id == 6


def test_parse_reasoning_truncation() -> None:
    parser = JsonActionParser(max_reasoning_len=10)
    _, reasoning = parser.parse('{"thinking": "this is a very long reasoning text", "action": 1}')
    assert len(reasoning) <= 10


# --- PlannerResponseParser ---


def test_parse_subgoals_valid() -> None:
    parser = PlannerResponseParser()
    content = '''{
        "analysis": "need to clear slot",
        "goal": "win",
        "subgoals": [
            {"id": 1, "description": "go to pad", "target": [10, 20], "done_when": "position is (10,20)"},
            {"id": 2, "description": "go to slot", "target": [30, 40], "done_when": "slot cleared"}
        ]
    }'''
    result = parser.parse_subgoals(content)
    assert len(result) == 2
    assert result[0]["target"] == [10, 20]
    assert result[1]["description"] == "go to slot"


def test_parse_subgoals_no_target_gets_default() -> None:
    parser = PlannerResponseParser()
    content = '{"subgoals": [{"id": 1, "description": "explore"}]}'
    result = parser.parse_subgoals(content)
    assert len(result) == 1
    assert result[0]["target"] == [32, 32]


def test_parse_subgoals_dict_target_converted() -> None:
    parser = PlannerResponseParser()
    content = '{"subgoals": [{"id": 1, "description": "go", "target": {"x": 15, "y": 25}}]}'
    result = parser.parse_subgoals(content)
    assert result[0]["target"] == [15, 25]


def test_parse_subgoals_invalid_json() -> None:
    parser = PlannerResponseParser()
    result = parser.parse_subgoals("not json at all")
    assert result == []


def test_parse_subgoals_no_subgoals_key() -> None:
    parser = PlannerResponseParser()
    result = parser.parse_subgoals('{"analysis": "test"}')
    assert result == []


def test_parse_subgoals_with_surrounding_text() -> None:
    parser = PlannerResponseParser()
    content = 'Here is my plan:\n{"subgoals": [{"id": 1, "description": "test", "target": [5, 5]}]}\nDone.'
    result = parser.parse_subgoals(content)
    assert len(result) == 1
    assert result[0]["target"] == [5, 5]
