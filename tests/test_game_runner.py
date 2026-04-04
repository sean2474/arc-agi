"""GameRunner 테스트. (통합 테스트는 게임 환경 필요하므로 유닛만)"""

from src.env.game_runner import EpisodeResult


def test_episode_result_creation() -> None:
    result = EpisodeResult(
        game_id="ls20",
        final_state="WIN",
        levels_completed=3,
        total_steps=50,
        history=[{"step": 0, "action": "ACTION1"}],
    )
    assert result.game_id == "ls20"
    assert result.final_state == "WIN"
    assert len(result.history) == 1
