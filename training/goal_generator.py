"""Goal 생성기.

학습용 다양한 goal을 생성한다.
코드 기반 (단순) + Claude 기반 (게임 특화) 혼합.
"""

import json
import random
from pathlib import Path

SIMPLE_GOALS = [
    "Explore the environment and interact with objects",
    "Find and reach colored objects on the screen",
    "Navigate through the maze to discover new areas",
    "Interact with every unique element visible on screen",
    "Clear the level by completing all objectives",
]


class GoalGenerator:
    """학습용 goal을 생성한다."""

    def __init__(self, cache_dir: Path | None = None) -> None:
        self._cache_dir = cache_dir or Path("training/goal_cache")
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._game_goals: dict[str, list[str]] = {}
        self._load_cache()

    def generate(self, game_id: str) -> str:
        """게임에 맞는 goal을 반환한다."""
        # 캐시된 게임별 goal이 있으면 사용
        if game_id in self._game_goals and self._game_goals[game_id]:
            return random.choice(self._game_goals[game_id])

        # 없으면 범용 goal
        return random.choice(SIMPLE_GOALS)

    def add_goals(self, game_id: str, goals: list[str]) -> None:
        """게임별 goal을 추가하고 캐시한다."""
        if game_id not in self._game_goals:
            self._game_goals[game_id] = []
        self._game_goals[game_id].extend(goals)
        self._save_cache()

    def _load_cache(self) -> None:
        cache_file = self._cache_dir / "goals.json"
        if cache_file.exists():
            self._game_goals = json.loads(cache_file.read_text())

    def _save_cache(self) -> None:
        cache_file = self._cache_dir / "goals.json"
        cache_file.write_text(
            json.dumps(self._game_goals, indent=2, ensure_ascii=False)
        )
