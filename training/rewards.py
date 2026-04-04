"""Reward 함수.

코드 기반 즉각 reward (프레임 변화) + Claude Evaluator reward (goal 달성).
두 신호를 합산하여 동시에 탐색과 목표 지향 학습.
"""

import numpy as np
import numpy.typing as npt


def compute_frame_diff(prev_frame: list, curr_frame: list) -> float:
    """두 프레임 간 변화 비율을 계산한다. (0.0 ~ 1.0)"""
    prev = np.array(prev_frame)
    curr = np.array(curr_frame)

    if prev.shape != curr.shape:
        return 0.0

    total_pixels = prev.size
    if total_pixels == 0:
        return 0.0

    changed = np.sum(prev != curr)
    return float(changed) / total_pixels


def step_reward(
    prev_frame: list,
    curr_frame: list,
    frame_change_weight: float = 0.5,
) -> float:
    """매 스텝 코드 기반 reward.

    프레임 변화가 있으면 + (무언가 일어남),
    변화가 없으면 - (헛된 액션).
    게임 장르에 무관하게 동작.
    """
    diff = compute_frame_diff(prev_frame, curr_frame)

    if diff > 0.001:  # 유의미한 변화
        return diff * frame_change_weight
    else:
        return -0.1  # 변화 없음 패널티


def combine_rewards(
    step_r: float,
    goal_r: float | None,
    frame_change_weight: float = 0.5,
    goal_reward_weight: float = 0.5,
) -> float:
    """코드 reward + Claude reward 합산.

    goal_r이 None이면 (Evaluator 미호출 스텝) step_r만 사용.
    """
    if goal_r is None:
        return step_r

    return step_r * frame_change_weight + goal_r * goal_reward_weight
