#!/usr/bin/env python3
"""학습 오케스트레이터 — 로컬에서 실행.

게임 환경 실행 + GPU 서버 호출 + Claude Evaluator 호출을 조합.

Usage:
    .venv/bin/python training/loop.py --server http://gpu-server:8000 --games ls20
    .venv/bin/python training/loop.py --server http://gpu-server:8000  # 전체 게임
"""

import argparse
import json
import random
import sys
import time
from pathlib import Path

import numpy as np
from arc_agi import Arcade, OperationMode
from arcengine import GameAction, GameState

from training.config import TrainingConfig
from training.rewards import step_reward, combine_rewards
from training.evaluator import Evaluator, frame_to_base64_from_list
from training.goal_generator import GoalGenerator
from training.server import TrainingServerClient
from src.llm.frame_renderer import frame_to_base64


def get_frame_list(raw_frame) -> list:
    """FrameDataRaw.frame → list[list[int]] 변환."""
    if raw_frame is None:
        return []
    if hasattr(raw_frame, 'tolist'):
        return raw_frame.tolist()
    return raw_frame


def run_episode(
    env,
    game_id: str,
    goal: str,
    server: TrainingServerClient,
    evaluator: Evaluator,
    config: TrainingConfig,
) -> dict:
    """한 에피소드를 실행하고 trajectory + reward를 반환한다."""
    obs = env.reset()
    if obs is None:
        return {"error": "reset failed"}

    # 프레임 추출
    frame = obs.frame[0] if obs.frame else None
    if frame is None:
        return {"error": "no frame"}

    first_frame = get_frame_list(frame)
    trajectory = []
    total_reward = 0.0
    eval_count = 0

    for step_num in range(config.max_steps_per_episode):
        prev_frame_list = get_frame_list(frame)

        # GPU 서버에 예측 요청
        frame_arr = np.array(frame) if not isinstance(frame, np.ndarray) else frame
        image_b64 = frame_to_base64(frame_arr, scale=4)

        try:
            action_id, confidence = server.predict(image_b64, goal)
        except Exception as e:
            print(f"    Server predict error: {e}")
            action_id = random.randint(1, 4)
            confidence = 0.0

        # 액션 실행
        action = GameAction.from_id(action_id)
        data = {}
        if action.is_complex():
            data = {"x": random.randint(0, 63), "y": random.randint(0, 63)}

        obs = env.step(action, data=data)
        if obs is None:
            break

        frame = obs.frame[0] if obs.frame else frame
        curr_frame_list = get_frame_list(frame)

        # 코드 기반 즉각 reward
        s_reward = step_reward(prev_frame_list, curr_frame_list, config.frame_change_weight)

        # Claude Evaluator reward (N스텝마다)
        g_reward = None
        if step_num > 0 and step_num % config.eval_interval == 0:
            try:
                g_reward = evaluator.evaluate(
                    before_frame=prev_frame_list,
                    after_frame=curr_frame_list,
                    goal=goal,
                    steps_taken=step_num,
                )
                eval_count += 1
            except Exception as e:
                print(f"    Evaluator error: {e}")

        combined = combine_rewards(s_reward, g_reward, config.frame_change_weight, config.goal_reward_weight)
        total_reward += combined

        trajectory.append({
            "image": image_b64,
            "goal": goal,
            "action": action_id,
            "reward": combined,
            "step": step_num,
        })

        # 종료 조건
        if obs.state == GameState.WIN:
            # 승리 보너스
            trajectory[-1]["reward"] += 1.0
            total_reward += 1.0
            break
        if obs.state == GameState.GAME_OVER:
            break

    # 에피소드 종료 시 최종 평가
    last_frame_list = get_frame_list(frame)
    final_state = obs.state.value if obs else "ERROR"

    try:
        episode_reward = evaluator.evaluate_episode(
            first_frame=first_frame,
            last_frame=last_frame_list,
            goal=goal,
            total_steps=len(trajectory),
            game_state=final_state,
        )
        eval_count += 1
    except Exception:
        episode_reward = 0.0

    return {
        "game_id": game_id,
        "goal": goal,
        "steps": len(trajectory),
        "total_reward": total_reward,
        "episode_reward": episode_reward,
        "final_state": final_state,
        "levels_completed": obs.levels_completed if obs else 0,
        "trajectory": trajectory,
        "eval_calls": eval_count,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="RLAIF Training Loop")
    parser.add_argument("--server", required=True, help="GPU 서버 URL")
    parser.add_argument("--games", type=str, help="쉼표 구분 게임 ID (없으면 전체)")
    parser.add_argument("--episodes", type=int, default=100, help="에피소드 수")
    parser.add_argument("--eval-model", type=str, default="claude-sonnet-4-20250514")
    args = parser.parse_args()

    config = TrainingConfig(
        server_url=args.server,
        num_episodes=args.episodes,
        evaluator_model=args.eval_model,
    )

    # 서버 연결 확인
    server = TrainingServerClient(args.server)
    if not server.is_alive():
        print(f"ERROR: Server not reachable at {args.server}")
        sys.exit(1)
    print(f"Server OK: {server.get_status()}")

    # 게임 환경
    arcade = Arcade(operation_mode=OperationMode.OFFLINE)
    all_envs = arcade.get_environments()

    if args.games:
        game_ids = [g.strip() for g in args.games.split(",")]
        game_ids = [e.game_id for e in all_envs if any(e.game_id.startswith(g) for g in game_ids)]
    else:
        game_ids = [e.game_id for e in all_envs]

    if not game_ids:
        print("No games found")
        sys.exit(1)

    print(f"Games: {len(game_ids)}")

    # 컴포넌트 초기화
    evaluator = Evaluator(model=config.evaluator_model)
    goal_gen = GoalGenerator()

    # 결과 로깅
    log_dir = Path("training/logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"train_{int(time.time())}.jsonl"

    print(f"\n{'='*60}")
    print(f"RLAIF Training Loop")
    print(f"Episodes: {config.num_episodes}, Games: {len(game_ids)}")
    print(f"Server: {args.server}")
    print(f"Log: {log_file}")
    print(f"{'='*60}\n")

    total_episodes = 0
    total_wins = 0

    for ep in range(config.num_episodes):
        # 랜덤 게임 선택
        game_id = random.choice(game_ids)
        goal = goal_gen.generate(game_id.split("-")[0])

        env = arcade.make(game_id)
        if env is None:
            print(f"  Skip: {game_id} (make failed)")
            continue

        # 에피소드 실행
        result = run_episode(env, game_id, goal, server, evaluator, config)

        if "error" in result:
            print(f"  [{ep}] {game_id}: ERROR - {result['error']}")
            continue

        total_episodes += 1
        if result["final_state"] == "WIN":
            total_wins += 1

        # 로깅
        log_entry = {
            "episode": ep,
            "game_id": game_id,
            "goal": goal,
            "steps": result["steps"],
            "total_reward": result["total_reward"],
            "episode_reward": result["episode_reward"],
            "final_state": result["final_state"],
            "levels": result["levels_completed"],
            "eval_calls": result["eval_calls"],
        }

        with log_file.open("a") as f:
            f.write(json.dumps(log_entry) + "\n")

        # 서버에 학습 데이터 전송
        try:
            train_result = server.train(result["trajectory"])
        except Exception as e:
            train_result = {"error": str(e)}

        # 진행 표시
        win_rate = total_wins / total_episodes if total_episodes > 0 else 0
        print(
            f"  [{ep:>4}] {game_id[:8]:>8} | "
            f"{result['final_state']:>12} | "
            f"steps={result['steps']:>3} | "
            f"reward={result['total_reward']:>6.2f} | "
            f"wins={total_wins}/{total_episodes} ({win_rate:.1%})"
        )

        # 체크포인트
        if (ep + 1) % config.save_interval == 0:
            print(f"\n  --- Checkpoint at episode {ep + 1} ---")
            print(f"  Evaluator: {evaluator.get_usage()}")
            print()

    print(f"\n{'='*60}")
    print(f"Training complete: {total_episodes} episodes, {total_wins} wins")
    print(f"Evaluator: {evaluator.get_usage()}")
    print(f"Log: {log_file}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
