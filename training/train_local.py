#!/usr/bin/env python3
"""GPU 서버에서 직접 실행하는 학습 루프.

게임 + 모델 추론을 같은 머신에서 → 네트워크 왕복 제거.
Claude evaluator만 외부 API 호출.

Usage (GPU 서버에서):
    ANTHROPIC_API_KEY=sk-... python training/train_local.py \
        --model ./qwen2.5-vl-7b \
        --games ls20 \
        --episodes 100
"""

import argparse
import base64
import io
import json
import os
import random
import sys
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from transformers import AutoModelForImageTextToText, AutoProcessor

# ARC 환경
from arc_agi import Arcade, OperationMode
from arcengine import GameAction, GameState


# ── ARC 16색 팔레트 ──
ARC_PALETTE = [
    (255,255,255), (204,204,204), (153,153,153), (102,102,102),
    (51,51,51), (0,0,0), (229,58,163), (255,123,204),
    (249,60,49), (30,147,255), (136,216,241), (255,220,0),
    (255,133,27), (146,18,49), (79,204,48), (163,86,214),
]


def frame_to_pil(frame, scale: int = 2) -> Image.Image:
    """게임 프레임 → PIL Image (RGB)."""
    arr = np.array(frame)
    if arr.ndim == 3:
        arr = arr[0]
    h, w = arr.shape
    rgb = np.zeros((h, w, 3), dtype=np.uint8)
    for val, color in enumerate(ARC_PALETTE):
        rgb[arr == val] = color
    img = Image.fromarray(rgb)
    if scale > 1:
        img = img.resize((w * scale, h * scale), Image.NEAREST)
    return img


def frame_diff_ratio(prev, curr) -> float:
    """두 프레임 간 변화 비율."""
    p = np.array(prev)
    c = np.array(curr)
    if p.shape != c.shape or p.size == 0:
        return 0.0
    return float(np.sum(p != c)) / p.size


def predict_action(model, processor, image: Image.Image, goal: str) -> int:
    """Qwen2.5-VL로 액션 예측. GPU에서 직접 추론."""
    prompt = (
        f"You are playing a game. Goal: {goal}\n"
        f"Choose action: 1=up, 2=down, 3=left, 4=right\n"
        f"Respond with just the number."
    )

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": image},
                {"type": "text", "text": prompt},
            ],
        }
    ]

    text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = processor(
        text=[text],
        images=[image],
        return_tensors="pt",
        padding=True,
    ).to(model.device)

    with torch.no_grad():
        output_ids = model.generate(
            **inputs,
            max_new_tokens=10,
            do_sample=True,
            temperature=0.7,
        )

    output_text = processor.batch_decode(
        output_ids[:, inputs.input_ids.shape[1]:],
        skip_special_tokens=True,
    )[0].strip()

    for ch in output_text:
        if ch in "1234":
            return int(ch)
    return random.randint(1, 4)


def evaluate_with_claude(
    before_frame,
    after_frame,
    goal: str,
    steps: int,
    api_key: str,
) -> float:
    """Claude Sonnet으로 goal 달성 평가. (0~1)"""
    import anthropic
    import re

    def frame_to_b64(frame) -> str:
        img = frame_to_pil(frame, scale=2)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()

    client = anthropic.Anthropic(api_key=api_key)

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=128,
        system="You evaluate game agent progress. Respond ONLY with: {\"score\": 0.0} where score is 0.0-1.0",
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": "BEFORE:"},
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": frame_to_b64(before_frame)}},
                {"type": "text", "text": "AFTER:"},
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": frame_to_b64(after_frame)}},
                {"type": "text", "text": f"GOAL: {goal}\nSteps: {steps}\nScore 0.0-1.0:"},
            ],
        }],
    )

    text = response.content[0].text
    match = re.search(r'"score"\s*:\s*([0-9.]+)', text)
    return float(match.group(1)) if match else 0.0


GOALS = [
    "Explore the environment and interact with objects",
    "Navigate through the maze to discover new areas",
    "Clear the level by completing all objectives",
    "Find and interact with colored objects",
    "Reach the goal area",
]


def run_episode(
    model, processor, env, game_id: str, goal: str,
    max_steps: int, eval_interval: int, api_key: str,
) -> dict:
    """한 에피소드 실행."""
    obs = env.reset()
    if obs is None or not obs.frame:
        return {"error": "reset failed"}

    frame = obs.frame[0]
    first_frame = np.array(frame).tolist()
    trajectory = []
    total_reward = 0.0
    eval_calls = 0

    for step in range(max_steps):
        prev = np.array(frame)
        img = frame_to_pil(frame, scale=2)

        # 추론 (로컬 GPU, 빠름)
        action_id = predict_action(model, processor, img, goal)

        # 액션 실행
        action = GameAction.from_id(action_id)
        data = {}
        if action.is_complex():
            data = {"x": random.randint(0, 63), "y": random.randint(0, 63)}
        obs = env.step(action, data=data)
        if obs is None:
            break

        frame = obs.frame[0] if obs.frame else frame
        curr = np.array(frame)

        # 코드 reward: 프레임 변화
        diff = frame_diff_ratio(prev, curr)
        step_r = diff * 0.5 if diff > 0.001 else -0.1

        # Claude reward (N스텝마다)
        goal_r = None
        if step > 0 and step % eval_interval == 0 and api_key:
            try:
                goal_r = evaluate_with_claude(prev.tolist(), curr.tolist(), goal, step, api_key)
                eval_calls += 1
            except Exception as e:
                print(f"      eval error: {e}")

        reward = step_r + (goal_r * 0.5 if goal_r is not None else 0)
        total_reward += reward

        trajectory.append({
            "action": action_id,
            "reward": reward,
            "diff": diff,
        })

        if obs.state == GameState.WIN:
            total_reward += 1.0
            break
        if obs.state == GameState.GAME_OVER:
            break

    return {
        "game_id": game_id,
        "goal": goal,
        "steps": len(trajectory),
        "total_reward": total_reward,
        "final_state": obs.state.value if obs else "ERROR",
        "levels": obs.levels_completed if obs else 0,
        "eval_calls": eval_calls,
        "trajectory": trajectory,
    }


def main():
    parser = argparse.ArgumentParser(description="Local GPU Training Loop")
    parser.add_argument("--model", required=True, help="모델 경로")
    parser.add_argument("--games", type=str, default="ls20")
    parser.add_argument("--episodes", type=int, default=100)
    parser.add_argument("--max-steps", type=int, default=200)
    parser.add_argument("--eval-interval", type=int, default=10)
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    # 모델 로드
    print(f"Loading model: {args.model}")
    processor = AutoProcessor.from_pretrained(args.model)
    model = AutoModelForImageTextToText.from_pretrained(
        args.model,
        dtype=torch.bfloat16,
        device_map="auto",
    )
    print(f"Model loaded. Device: {model.device}")

    # 게임
    arcade = Arcade(operation_mode=OperationMode.OFFLINE)
    all_envs = arcade.get_environments()
    game_filters = [g.strip() for g in args.games.split(",")]
    game_ids = [e.game_id for e in all_envs if any(e.game_id.startswith(g) for g in game_filters)]
    print(f"Games: {len(game_ids)}")

    # 로그
    log_dir = Path("training/logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"train_{int(time.time())}.jsonl"

    print(f"\n{'='*60}")
    print(f"Training: {args.episodes} episodes, {len(game_ids)} games")
    print(f"Max steps: {args.max_steps}, Eval interval: {args.eval_interval}")
    print(f"Claude API: {'YES' if api_key else 'NO (frame diff only)'}")
    print(f"{'='*60}\n")

    wins = 0
    total = 0

    for ep in range(args.episodes):
        game_id = random.choice(game_ids)
        goal = random.choice(GOALS)
        env = arcade.make(game_id)
        if env is None:
            continue

        t0 = time.time()
        result = run_episode(
            model, processor, env, game_id, goal,
            args.max_steps, args.eval_interval, api_key,
        )
        elapsed = time.time() - t0

        if "error" in result:
            continue

        total += 1
        if result["final_state"] == "WIN":
            wins += 1

        # 로깅
        entry = {k: v for k, v in result.items() if k != "trajectory"}
        entry["time"] = round(elapsed, 1)
        with log_file.open("a") as f:
            f.write(json.dumps(entry) + "\n")

        wr = wins / total if total else 0
        print(
            f"  [{ep:>4}] {game_id[:8]:>8} | "
            f"{result['final_state']:>12} | "
            f"steps={result['steps']:>3} | "
            f"r={result['total_reward']:>6.2f} | "
            f"t={elapsed:>5.1f}s | "
            f"wins={wins}/{total} ({wr:.1%})"
        )

    print(f"\n{'='*60}")
    print(f"Done: {total} episodes, {wins} wins ({wins/max(total,1):.1%})")
    print(f"Log: {log_file}")


if __name__ == "__main__":
    main()
