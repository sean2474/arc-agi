"""에피소드 실행 + trajectory 수집."""

import random
from typing import Any

import numpy as np
import torch
from PIL import Image

from arcengine import GameAction, GameState

from src.env.observer import Observation, Observer
from src.llm.frame_renderer import ARC_PALETTE

from training.rewards import observation_reward

# ── 상수 ──

GOALS = [
    "Explore the environment and interact with objects",
    "Navigate through the maze to discover new areas",
    "Clear the level by completing all objectives",
    "Find and interact with colored objects",
    "Reach the goal area",
]

ACTION_PROMPT = (
    "You are playing a game. Goal: {goal}\n"
    "Choose action: 1=up, 2=down, 3=left, 4=right\n"
    "Respond with just the number."
)


# ── 유틸 ──

def frame_to_pil(frame: list | np.ndarray, scale: int = 2) -> Image.Image:
    """프레임을 PIL 이미지로 변환한다."""
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


def frame_diff_ratio(prev: np.ndarray, curr: np.ndarray) -> float:
    """두 프레임 간 변화 비율."""
    p, c = np.array(prev), np.array(curr)
    if p.shape != c.shape or p.size == 0:
        return 0.0
    return float(np.sum(p != c)) / p.size


# ── 모델 추론 ──

def build_prompt_text(
    processor: Any,
    image: Image.Image,
    goal: str,
    action_str: str | None = None,
) -> str:
    """VLM 프롬프트 텍스트를 생성한다."""
    prompt = ACTION_PROMPT.format(goal=goal)
    messages: list[dict] = [
        {"role": "user", "content": [
            {"type": "image", "image": image},
            {"type": "text", "text": prompt},
        ]},
    ]
    if action_str is not None:
        messages.append({"role": "assistant", "content": [
            {"type": "text", "text": action_str},
        ]})
        return processor.apply_chat_template(messages, tokenize=False)
    return processor.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True,
    )


def predict_action(
    model: Any,
    processor: Any,
    image: Image.Image,
    goal: str,
) -> int:
    """모델로 액션 예측."""
    text = build_prompt_text(processor, image, goal)
    inputs = processor(
        text=[text], images=[image], return_tensors="pt", padding=True,
    )
    inputs = {k: v.to(model.device) for k, v in inputs.items()}

    with torch.no_grad():
        output_ids = model.generate(
            **inputs, max_new_tokens=10, do_sample=True, temperature=0.7,
        )

    output_text = processor.batch_decode(
        output_ids[:, inputs["input_ids"].shape[1]:],
        skip_special_tokens=True,
    )[0].strip()

    for ch in output_text:
        if ch in "1234":
            return int(ch)
    return random.randint(1, 4)


# ── Trajectory 수집 ──

class TrajectoryCollector:
    """게임 에피소드를 실행하고 trajectory를 수집한다."""

    def __init__(self, observer: Observer | None = None) -> None:
        self._observer = observer

    def collect(
        self,
        model: Any,
        processor: Any,
        env: Any,
        game_id: str,
        goal: str,
        max_steps: int,
    ) -> dict:
        """에피소드 실행 -> trajectory dict 반환."""
        obs = env.reset()
        if obs is None or not obs.frame:
            return {"error": "reset failed"}

        if self._observer is not None:
            self._observer.reset()

        frame = obs.frame[0]
        trajectory: list[dict] = []
        total_reward = 0.0

        for step in range(max_steps):
            prev = np.array(frame)
            img = frame_to_pil(frame, scale=2)

            action_id = predict_action(model, processor, img, goal)

            action = GameAction.from_id(action_id)
            data = (
                {"x": random.randint(0, 63), "y": random.randint(0, 63)}
                if action.is_complex()
                else {}
            )
            obs = env.step(action, data=data)
            if obs is None:
                break

            frame = obs.frame[0] if obs.frame else frame
            curr = np.array(frame)

            diff = frame_diff_ratio(prev, curr)
            reward = diff * 0.5 if diff > 0.001 else -0.1

            # Observer 기반 보상 추가
            step_observation: Observation | None = None
            if self._observer is not None:
                try:
                    # Observer는 extracted dict를 기대하지만,
                    # 여기서는 간단한 프레임 기반 관찰만 사용
                    step_observation = Observation(
                        moved=(diff > 0.001),
                        blocked=(diff <= 0.001),
                    )
                    reward += observation_reward(step_observation)
                except Exception:
                    pass

            total_reward += reward

            trajectory.append({
                "action": action_id,
                "reward": reward,
                "diff": diff,
                "image": img,
                "frame_raw": prev.tolist(),
                "goal": goal,
                "observation": step_observation,
            })

            if obs.state in (GameState.WIN, GameState.GAME_OVER):
                if obs.state == GameState.WIN:
                    total_reward += 1.0
                break

        return {
            "game_id": game_id,
            "goal": goal,
            "steps": len(trajectory),
            "total_reward": total_reward,
            "final_state": obs.state.value if obs else "ERROR",
            "levels": obs.levels_completed if obs else 0,
            "trajectory": trajectory,
        }
