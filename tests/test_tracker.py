"""ExperimentTracker 테스트."""

import json
import shutil
from pathlib import Path

from src.experiment.tracker import ExperimentTracker


def test_tracker_creates_directory(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "src.experiment.tracker.EXPERIMENTS_DIR", tmp_path
    )

    tracker = ExperimentTracker("test_exp", "test description")
    assert tracker.dir.exists()
    assert (tracker.dir / "config.json").exists()

    config = json.loads((tracker.dir / "config.json").read_text())
    assert config["name"] == "test_exp"


def test_tracker_records_and_saves(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "src.experiment.tracker.EXPERIMENTS_DIR", tmp_path
    )

    tracker = ExperimentTracker("test_exp")
    tracker.record_episode({"final_state": "WIN", "total_steps": 10})
    tracker.record_episode({"final_state": "GAME_OVER", "total_steps": 50})

    path = tracker.save()
    assert path.exists()

    data = json.loads(path.read_text())
    assert data["summary"]["total_episodes"] == 2
    assert data["summary"]["wins"] == 1
    assert data["summary"]["win_rate"] == 0.5
