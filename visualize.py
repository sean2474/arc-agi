#!/usr/bin/env python3
"""실험 결과 시각화 + 프롬프트 확인 도구.

Usage:
    .venv/bin/python visualize.py                          # 최신 실험
    .venv/bin/python visualize.py --experiment <name>      # 특정 실험
    .venv/bin/python visualize.py --prompt                 # 프롬프트 미리보기
    .venv/bin/python visualize.py --frame                  # 현재 프레임 이미지 저장
"""

import argparse
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from arcengine import ActionInput, GameAction

from src.llm.frame_renderer import frame_to_rgb, frame_to_png_bytes
from src.llm.vlm_prompt_builder import Ls20VLMPromptBuilder
from src.llm.prompt_builder import Ls20PromptBuilder
from src.env.state_extractor import Ls20Extractor
from src.agent.base import GameState


EXPERIMENTS_DIR = Path("experiments")
OUTPUT_DIR = Path("output")


def load_game():
    env_dir = Path("environment_files/ls20")
    for sub in env_dir.iterdir():
        game_file = sub / "ls20.py"
        if game_file.exists():
            spec = importlib.util.spec_from_file_location("ls20_module", game_file)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module.Ls20()
    raise RuntimeError("ls20.py not found")


def find_experiment(name: str | None) -> Path | None:
    if not EXPERIMENTS_DIR.exists():
        return None
    dirs = sorted(EXPERIMENTS_DIR.iterdir(), reverse=True)
    if name:
        for d in dirs:
            if name in d.name:
                return d
    return dirs[0] if dirs else None


def show_experiment(exp_dir: Path) -> None:
    """실험 결과를 시각화한다."""
    print(f"\n{'='*60}")
    print(f"Experiment: {exp_dir.name}")
    print(f"{'='*60}")

    config_path = exp_dir / "config.json"
    if config_path.exists():
        config = json.loads(config_path.read_text())
        print(f"Description: {config.get('description', '')}")
        print(f"Timestamp: {config.get('timestamp', '')}")

    results_path = exp_dir / "results.json"
    if not results_path.exists():
        print("(no results.json)")
        return

    data = json.loads(results_path.read_text())

    # Summary
    summary = data.get("summary", {})
    print(f"\nSummary:")
    print(f"  Episodes: {summary.get('total_episodes', 0)}")
    print(f"  Wins: {summary.get('wins', 0)}")
    print(f"  Win rate: {summary.get('win_rate', 0):.1%}")
    print(f"  Avg steps: {summary.get('avg_steps', 0):.1f}")

    # Episode details
    for i, ep in enumerate(data.get("episodes", [])):
        print(f"\n--- Episode {i+1} ---")
        print(f"  Game: {ep.get('game_id', '?')}")
        print(f"  Result: {ep.get('final_state', '?')}")
        print(f"  Levels: {ep.get('levels_completed', 0)}")
        print(f"  Steps: {ep.get('total_steps', 0)}")
        print(f"  API: {ep.get('api_usage', '?')}")

        history = ep.get("history", [])
        if history:
            actions = [h["action"] for h in history]
            blocked = sum(1 for h in history if not h.get("moved", True))
            print(f"  Actions: {dict(Counter(actions))}")
            print(f"  Blocked: {blocked}/{len(history)} ({blocked/len(history)*100:.0f}%)")

            # Movement trace (compact)
            print(f"\n  Movement trace:")
            for h in history:
                m = "OK" if h.get("moved", True) else "XX"
                pos = h.get("player_pos", [0, 0])
                new = h.get("new_pos", pos)
                event = h.get("event", "")
                step = h.get("step", "?")
                reason = h.get("reasoning", "")[:60]
                if "queued" in reason:
                    reason = "(queued)"
                elif len(reason) > 50:
                    reason = reason[:50] + "..."
                print(f"    {step:>3}: {h['action']:>8} ({pos[0]:>2},{pos[1]:>2})→({new[0]:>2},{new[1]:>2}) [{m}] {event} {reason}")


def show_prompt_preview() -> None:
    """현재 프롬프트 구성을 미리보기."""
    print("\n" + "=" * 60)
    print("PROMPT PREVIEW")
    print("=" * 60)

    game = load_game()
    result = game.perform_action(
        ActionInput(id=GameAction.RESET, data={"game_id": "ls20"})
    )

    extractor = Ls20Extractor(game)
    frame_list = result.frame if hasattr(result, "frame") and result.frame else []

    state = GameState(
        game_id="ls20",
        frame_raw=frame_list,
        available_actions=[1, 2, 3, 4],
        state="NOT_FINISHED",
        levels_completed=0,
        step_number=0,
    )
    state.extracted = extractor.extract(state)

    # Text prompt
    print("\n--- TEXT PROMPT (Ls20PromptBuilder) ---")
    text_builder = Ls20PromptBuilder()
    print("\n[SYSTEM]")
    system = text_builder.build_system()
    print(system[:500] + "..." if len(system) > 500 else system)
    print(f"\n  (total {len(system)} chars)")

    print("\n[USER MESSAGE]")
    user_msg = text_builder.build_user_message(state, [])
    print(user_msg)

    # VLM prompt
    print("\n--- VLM PROMPT (Ls20VLMPromptBuilder) ---")
    vlm_builder = Ls20VLMPromptBuilder()
    print("\n[SYSTEM]")
    vlm_system = vlm_builder.build_system()
    print(vlm_system[:500] + "..." if len(vlm_system) > 500 else vlm_system)
    print(f"\n  (total {len(vlm_system)} chars)")

    print("\n[USER MESSAGE (text part)]")
    vlm_msg = vlm_builder.build_user_message(state, [])
    if isinstance(vlm_msg, list):
        for block in vlm_msg:
            if block.get("type") == "text":
                print(block["text"])
            elif block.get("type") == "image":
                print("[IMAGE: 512x512 PNG, base64 encoded]")
    else:
        print(vlm_msg)

    # Extracted state
    print("\n--- EXTRACTED STATE ---")
    print(json.dumps(state.extracted, indent=2, ensure_ascii=False, default=str))


def save_frame_image() -> None:
    """현재 게임 프레임을 이미지로 저장."""
    OUTPUT_DIR.mkdir(exist_ok=True)

    game = load_game()
    result = game.perform_action(
        ActionInput(id=GameAction.RESET, data={"game_id": "ls20"})
    )

    if not result.frame:
        print("No frame data")
        return

    raw = result.frame[0]
    frame = np.array(raw) if not isinstance(raw, np.ndarray) else raw

    # 여러 스케일로 저장
    for scale in [1, 4, 8]:
        png = frame_to_png_bytes(frame, scale=scale)
        path = OUTPUT_DIR / f"ls20_frame_x{scale}.png"
        path.write_bytes(png)
        h, w = frame.shape[0] * scale, frame.shape[1] * scale
        print(f"Saved: {path} ({w}x{h})")

    # 몇 스텝 실행 후 프레임도
    actions = [GameAction.ACTION1, GameAction.ACTION1, GameAction.ACTION3]
    for i, action in enumerate(actions):
        result = game.perform_action(
            ActionInput(id=action, data={"game_id": "ls20"})
        )
        if result.frame:
            raw = result.frame[0]
            frame = np.array(raw) if not isinstance(raw, np.ndarray) else raw
            png = frame_to_png_bytes(frame, scale=8)
            path = OUTPUT_DIR / f"ls20_frame_step{i+1}_x8.png"
            path.write_bytes(png)
            print(f"Saved: {path} (after {action.name})")

    print(f"\nAll frames saved to {OUTPUT_DIR}/")


def replay_experiment(exp_dir: Path) -> None:
    """실험의 각 스텝을 프레임 이미지로 저장."""
    results_path = exp_dir / "results.json"
    if not results_path.exists():
        print("No results.json")
        return

    data = json.loads(results_path.read_text())
    episodes = data.get("episodes", [])
    if not episodes:
        print("No episodes")
        return

    replay_dir = exp_dir / "replay"
    replay_dir.mkdir(exist_ok=True)

    game = load_game()
    game.perform_action(ActionInput(id=GameAction.RESET, data={"game_id": "ls20"}))

    history = episodes[0].get("history", [])
    print(f"Replaying {len(history)} steps...")

    for h in history:
        action_name = h["action"]
        action = GameAction.from_id(int(action_name.replace("ACTION", "")))

        result = game.perform_action(
            ActionInput(id=action, data={"game_id": "ls20"})
        )

        if result.frame:
            raw = result.frame[0]
            frame = np.array(raw) if not isinstance(raw, np.ndarray) else raw
            png = frame_to_png_bytes(frame, scale=8)
            step = h["step"]
            path = replay_dir / f"step_{step:03d}_{action_name}.png"
            path.write_bytes(png)

    print(f"Replay frames saved to {replay_dir}/ ({len(history)} frames)")


def main() -> None:
    parser = argparse.ArgumentParser(description="실험 시각화 도구")
    parser.add_argument("--experiment", "-e", type=str, help="실험 이름 (부분 매치)")
    parser.add_argument("--prompt", action="store_true", help="프롬프트 미리보기")
    parser.add_argument("--frame", action="store_true", help="현재 프레임 이미지 저장")
    parser.add_argument("--replay", action="store_true", help="실험 리플레이 이미지 생성")
    args = parser.parse_args()

    if args.prompt:
        show_prompt_preview()
    elif args.frame:
        save_frame_image()
    elif args.replay:
        exp = find_experiment(args.experiment)
        if exp:
            replay_experiment(exp)
        else:
            print("No experiment found")
    else:
        exp = find_experiment(args.experiment)
        if exp:
            show_experiment(exp)
        else:
            print("No experiments found. Run an experiment first.")


if __name__ == "__main__":
    main()
