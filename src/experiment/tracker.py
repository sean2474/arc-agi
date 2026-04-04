"""실험 추적.

실험 시작/종료, 결과 저장, 이전 실험과 비교.
"""

import json
from datetime import datetime
from pathlib import Path


EXPERIMENTS_DIR = Path(__file__).parent.parent.parent / "experiments"


class ExperimentTracker:
    """실험을 추적하고 결과를 저장한다."""

    def __init__(self, name: str, description: str = "", reuse: bool = True) -> None:
        self._name = name
        self._results: list[dict] = []

        # 기존 실험 디렉토리가 있으면 재사용
        if reuse:
            existing = self._find_existing(name)
            if existing:
                self._dir = existing
                self._timestamp = existing.name.split("_")[0]
                return

        self._timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._dir = EXPERIMENTS_DIR / f"{self._timestamp}_{name}"
        self._dir.mkdir(parents=True, exist_ok=True)

        config = {
            "name": name,
            "timestamp": datetime.now().isoformat(),
            "description": description,
        }
        (self._dir / "config.json").write_text(
            json.dumps(config, indent=2, ensure_ascii=False)
        )

    @staticmethod
    def _find_existing(name: str) -> Path | None:
        """같은 이름의 기존 실험 디렉토리를 찾는다."""
        if not EXPERIMENTS_DIR.exists():
            return None
        for d in sorted(EXPERIMENTS_DIR.iterdir(), reverse=True):
            if d.is_dir() and d.name.endswith(f"_{name}"):
                return d
        return None

    @property
    def dir(self) -> Path:
        return self._dir

    def record_episode(self, result: dict) -> None:
        """에피소드 결과를 기록한다."""
        self._results.append(result)

    def save(self) -> Path:
        """실험 결과를 저장한다."""
        results_path = self._dir / "results.json"
        data = {
            "name": self._name,
            "timestamp": self._timestamp,
            "episodes": self._results,
            "summary": self._summarize(),
        }
        results_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False)
        )
        return results_path

    def _summarize(self) -> dict:
        """결과 요약."""
        if not self._results:
            return {}

        wins = sum(1 for r in self._results if r.get("final_state") == "WIN")
        total = len(self._results)
        avg_steps = sum(r.get("total_steps", 0) for r in self._results) / total

        return {
            "total_episodes": total,
            "wins": wins,
            "win_rate": wins / total if total > 0 else 0,
            "avg_steps": avg_steps,
        }

    @staticmethod
    def list_experiments() -> list[dict]:
        """이전 실험 목록을 반환한다."""
        experiments = []
        if not EXPERIMENTS_DIR.exists():
            return experiments

        for exp_dir in sorted(EXPERIMENTS_DIR.iterdir()):
            results_file = exp_dir / "results.json"
            if results_file.exists():
                data = json.loads(results_file.read_text())
                experiments.append({
                    "dir": str(exp_dir),
                    "name": data.get("name", ""),
                    "summary": data.get("summary", {}),
                })

        return experiments
