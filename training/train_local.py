#!/usr/bin/env python3
"""DPO 학습 오케스트레이터.

게임 실행 -> trajectory 수집 -> preference 쌍 생성 -> DPO 학습.
각 단계는 전용 모듈에 위임한다.

Usage (GPU 서버에서):
    python training/train_local.py --model ./qwen2.5-vl-7b --games ls20 --episodes 100
"""

import argparse
import json
import random
import sys
import time
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가 (GPU 서버에서 src/ 패키지 인식용)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import torch

from arc_agi import Arcade, OperationMode

from src.env.observer import Observer

from training.dpo_trainer import DPOTrainer
from training.evaluator import Evaluator
from training.model_loader import ModelLoader
from training.trajectory_collector import GOALS, TrajectoryCollector


def main() -> None:
    parser = argparse.ArgumentParser(description="DPO Training Loop")
    parser.add_argument("--model", required=True)
    parser.add_argument("--games", type=str, default="ls20")
    parser.add_argument("--episodes", type=int, default=100)
    parser.add_argument("--max-steps", type=int, default=100)
    parser.add_argument(
        "--train-every", type=int, default=5,
        help="N 에피소드마다 DPO 학습",
    )
    parser.add_argument("--lr", type=float, default=1e-5)
    parser.add_argument("--beta", type=float, default=0.1, help="DPO beta")
    parser.add_argument("--save-every", type=int, default=50)
    args = parser.parse_args()

    # ── 모듈 초기화 ──
    loader = ModelLoader(args.model)
    model, processor = loader.load()

    observer = Observer()
    collector = TrajectoryCollector(observer=observer)
    trainer = DPOTrainer(beta=args.beta)

    ref_log_probs_cache: dict = {}
    optimizer = torch.optim.AdamW(
        [p for p in model.parameters() if p.requires_grad],
        lr=args.lr,
    )

    # ── 게임 ──
    arcade = Arcade(operation_mode=OperationMode.OFFLINE)
    all_envs = arcade.get_environments()
    game_filters = [g.strip() for g in args.games.split(",")]
    game_ids = [
        e.game_id for e in all_envs
        if any(e.game_id.startswith(g) for g in game_filters)
    ]
    print(f"Games: {len(game_ids)}")

    # ── 로그 ──
    log_dir = Path("training/logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"dpo_{int(time.time())}.jsonl"
    ckpt_dir = Path("training/checkpoints")
    ckpt_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"DPO Training: {args.episodes} episodes")
    print(f"Train every: {args.train_every} eps, LR: {args.lr}, Beta: {args.beta}")
    print(f"{'='*60}\n")

    wins, total = 0, 0
    all_pairs: list[dict] = []
    reward_history: list[float] = []
    dpo_losses: list[float] = []

    for ep in range(args.episodes):
        game_id = random.choice(game_ids)
        goal = random.choice(GOALS)
        env = arcade.make(game_id)
        if env is None:
            continue

        t0 = time.time()
        model.eval()
        result = collector.collect(
            model, processor, env, game_id, goal, args.max_steps,
        )
        elapsed = time.time() - t0

        if "error" in result:
            continue

        total += 1
        if result["final_state"] == "WIN":
            wins += 1
        reward_history.append(result["total_reward"])

        # Preference 쌍 수집
        pairs = trainer.collect_preferences(result["trajectory"])
        all_pairs.extend(pairs)

        # ref log probs 캐시 (학습 전 모델 상태)
        trainer.cache_ref_log_probs(
            model, processor, pairs, ref_log_probs_cache,
        )

        # N 에피소드마다 DPO 학습
        loss = 0.0
        if total % args.train_every == 0 and all_pairs:
            loss = trainer.train_step(
                model, processor, all_pairs, optimizer, ref_log_probs_cache,
            )
            dpo_losses.append(loss)
            all_pairs = []
            ref_log_probs_cache = {}
            torch.cuda.empty_cache()

        # trajectory의 이미지/frame_raw 해제 (메모리)
        if "trajectory" in result:
            for step_data in result["trajectory"]:
                step_data.pop("image", None)
                step_data.pop("frame_raw", None)

        # 로깅
        entry = {
            "ep": ep, "game": game_id, "state": result["final_state"],
            "steps": result["steps"], "reward": round(result["total_reward"], 3),
            "time": round(elapsed, 1), "loss": round(loss, 4),
            "pairs": len(pairs),
        }
        with log_file.open("a") as f:
            f.write(json.dumps(entry) + "\n")

        recent_r = np.mean(reward_history[-10:]) if reward_history else 0
        loss_str = f"loss={loss:.4f}" if loss > 0 else "          "
        print(
            f"  [{ep:>4}] {game_id[:8]:>8} | "
            f"{result['final_state']:>12} | "
            f"steps={result['steps']:>3} | "
            f"r={result['total_reward']:>6.2f} (avg={recent_r:>6.2f}) | "
            f"{loss_str} | "
            f"pairs={len(pairs):>2} | "
            f"t={elapsed:>5.1f}s | "
            f"wins={wins}/{total}"
        )

        # 체크포인트
        if total > 0 and total % args.save_every == 0:
            loader.save_checkpoint(model, ckpt_dir / f"lora_ep{ep}")

    loader.save_checkpoint(model, ckpt_dir / "lora_final")

    print(f"\n{'='*60}")
    print(f"Done: {total} episodes, {wins} wins ({wins/max(total,1):.1%})")
    print(f"Avg reward (last 10): {np.mean(reward_history[-10:]):.3f}")
    if dpo_losses:
        print(f"Avg DPO loss: {np.mean(dpo_losses):.4f}")
    print(f"Final checkpoint: {ckpt_dir / 'lora_final'}")
    print(f"Log: {log_file}")


if __name__ == "__main__":
    main()
