"""실험 결과를 리플레이 JSON으로 변환한다.

게임을 다시 돌리면서 각 스텝의 프레임(hex grid)을 생성.
"""

import importlib.util
import json
from pathlib import Path

import numpy as np
from arcengine import ActionInput, GameAction


def load_game(game_id: str = "ls20"):
    """게임 인스턴스를 로드한다."""
    env_dir = Path("environment_files") / game_id
    for sub in env_dir.iterdir():
        game_file = sub / f"{game_id}.py"
        if game_file.exists():
            spec = importlib.util.spec_from_file_location(f"{game_id}_mod", game_file)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            class_name = game_id.capitalize() if game_id != "ls20" else "Ls20"
            return getattr(module, class_name)()
    raise RuntimeError(f"{game_id}.py not found")


def frame_to_hex_grid(frame) -> list[str]:
    """프레임을 hex 문자열 행 리스트로 변환. 각 픽셀 = 1 hex char."""
    arr = np.array(frame) if not isinstance(frame, np.ndarray) else frame
    rows = []
    for y in range(arr.shape[0]):
        row = "".join(f"{int(arr[y, x]):x}" for x in range(arr.shape[1]))
        rows.append(row)
    return rows


def convert_experiment(experiment_dir: Path, output_path: Path | None = None) -> Path:
    """실험 결과를 리플레이 JSON으로 변환한다."""
    results_path = experiment_dir / "results.json"
    if not results_path.exists():
        raise FileNotFoundError(f"No results.json in {experiment_dir}")

    data = json.loads(results_path.read_text())
    episodes = data.get("episodes", [])
    if not episodes:
        raise ValueError("No episodes in results")

    ep = episodes[0]
    game_id = ep.get("game_id", "ls20").split("-")[0]
    history = ep.get("history", [])

    # 게임을 다시 돌리면서 프레임 수집
    game = load_game(game_id)
    result = game.perform_action(
        ActionInput(id=GameAction.RESET, data={"game_id": game_id})
    )

    trajectory = []

    # 초기 프레임 (step 0 전)
    if result.frame:
        trajectory.append({
            "step": 0,
            "action": "RESET",
            "grid": frame_to_hex_grid(result.frame[0]),
            "state": result.state.value,
            "levels_completed": result.levels_completed,
            "reasoning": "Game start",
        })

    for h in history:
        action_name = h.get("action", "ACTION1")
        action_id = int(action_name.replace("ACTION", ""))
        action = GameAction.from_id(action_id)

        result = game.perform_action(
            ActionInput(id=action, data={"game_id": game_id})
        )

        step_data = {
            "step": h.get("step", 0) + 1,
            "action": action_name,
            "grid": frame_to_hex_grid(result.frame[0]) if result.frame else [],
            "state": result.state.value,
            "levels_completed": result.levels_completed,
            "reasoning": h.get("reasoning", "")[:500],
            "player_pos": h.get("player_pos"),
            "new_pos": h.get("new_pos"),
            "moved": h.get("moved", True),
            "event": h.get("event", ""),
            "llm_called": "queued" not in h.get("reasoning", ""),
        }
        trajectory.append(step_data)

    replay_data = {
        "title": game_id,
        "agent_name": data.get("name", "unknown"),
        "game_id": game_id,
        "final_state": ep.get("final_state", "?"),
        "levels_completed": ep.get("levels_completed", 0),
        "total_steps": ep.get("total_steps", 0),
        "api_usage": ep.get("api_usage", ""),
        "trajectory": trajectory,
    }

    if output_path is None:
        output_path = experiment_dir / "replay.json"

    output_path.write_text(json.dumps(replay_data, ensure_ascii=False))
    return output_path
