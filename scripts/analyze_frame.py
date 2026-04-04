#!/usr/bin/env python3
"""프레임 분석 도구 (Planner용).

게임 프레임을 분석하여 오브젝트, 색상 분포, 변화를 출력한다.

Usage:
    python scripts/analyze_frame.py --game ls20 --steps 5
    python scripts/analyze_frame.py --frame frame.npy
"""

import argparse
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import numpy.typing as npt


def analyze_color_distribution(
    frame: npt.NDArray[np.int_],
) -> dict[int, int]:
    """프레임의 색상 분포를 분석한다."""
    unique, counts = np.unique(frame, return_counts=True)
    return dict(zip(unique.tolist(), counts.tolist()))


def find_objects(
    frame: npt.NDArray[np.int_], background_color: int = 0
) -> list[dict]:
    """프레임에서 배경이 아닌 연결된 영역(오브젝트)을 찾는다."""
    visited = np.zeros_like(frame, dtype=bool)
    objects: list[dict] = []

    for y in range(frame.shape[0]):
        for x in range(frame.shape[1]):
            if visited[y, x] or frame[y, x] == background_color:
                continue

            # BFS로 연결 영역 찾기
            color = int(frame[y, x])
            pixels: list[tuple[int, int]] = []
            queue: list[tuple[int, int]] = [(y, x)]
            visited[y, x] = True

            while queue:
                cy, cx = queue.pop(0)
                pixels.append((cx, cy))

                for dy, dx in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    ny, nx = cy + dy, cx + dx
                    if (
                        0 <= ny < frame.shape[0]
                        and 0 <= nx < frame.shape[1]
                        and not visited[ny, nx]
                        and frame[ny, nx] == color
                    ):
                        visited[ny, nx] = True
                        queue.append((ny, nx))

            if len(pixels) >= 2:  # 최소 2픽셀 이상
                xs = [p[0] for p in pixels]
                ys = [p[1] for p in pixels]
                objects.append({
                    "color": color,
                    "pixel_count": len(pixels),
                    "bbox": {
                        "x_min": min(xs),
                        "y_min": min(ys),
                        "x_max": max(xs),
                        "y_max": max(ys),
                    },
                    "center": (
                        sum(xs) // len(xs),
                        sum(ys) // len(ys),
                    ),
                })

    return objects


def compute_diff(
    prev: npt.NDArray[np.int_],
    curr: npt.NDArray[np.int_],
) -> dict:
    """두 프레임 간 차이를 분석한다."""
    changed_mask = prev != curr
    changed_count = int(np.sum(changed_mask))
    total = prev.shape[0] * prev.shape[1]

    changed_positions: list[tuple[int, int]] = []
    if changed_count > 0 and changed_count <= 100:
        ys, xs = np.where(changed_mask)
        changed_positions = list(zip(xs.tolist(), ys.tolist()))

    return {
        "changed_pixels": changed_count,
        "total_pixels": total,
        "change_ratio": changed_count / total if total > 0 else 0,
        "changed_positions": changed_positions[:50],  # 최대 50개
    }


def print_frame_ascii(
    frame: npt.NDArray[np.int_], max_width: int = 64
) -> None:
    """프레임을 ASCII로 출력한다."""
    color_chars = "0123456789ABCDEF"
    h, w = frame.shape
    step = max(1, w // max_width)

    for y in range(0, h, step):
        row = ""
        for x in range(0, w, step):
            val = int(frame[y, x])
            row += color_chars[val] if 0 <= val <= 15 else "?"
        print(row)


def run_game_analysis(game_id: str, steps: int = 5) -> None:
    """게임을 몇 스텝 실행하고 프레임을 분석한다."""
    try:
        from arc_agi import Arcade, OperationMode
        from arcengine import GameAction
    except ImportError:
        print("arc_agi / arcengine이 설치되지 않았습니다.", file=sys.stderr)
        sys.exit(1)

    arc = Arcade(operation_mode=OperationMode.OFFLINE)
    env = arc.make(game_id)

    if env is None:
        print(f"게임 '{game_id}'를 로드할 수 없습니다.", file=sys.stderr)
        sys.exit(1)

    obs = env.reset()
    if obs is None or not obs.frame:
        print("초기 프레임을 가져올 수 없습니다.", file=sys.stderr)
        sys.exit(1)

    frame = obs.frame[0]
    print(f"=== {game_id} 초기 프레임 분석 ===")
    print(f"프레임 크기: {frame.shape}")
    print(f"게임 상태: {obs.state}")
    print(f"사용 가능 액션: {obs.available_actions}")
    print(f"\n색상 분포: {analyze_color_distribution(frame)}")

    objects = find_objects(frame)
    print(f"\n발견된 오브젝트: {len(objects)}개")
    for i, obj in enumerate(objects):
        print(f"  [{i}] color={obj['color']}, pixels={obj['pixel_count']}, "
              f"center={obj['center']}, bbox={obj['bbox']}")

    print(f"\nASCII 미리보기:")
    print_frame_ascii(frame)

    # 각 액션 실행해보기
    if steps > 0:
        prev_frame = frame
        actions = env.action_space
        print(f"\n=== {steps}스텝 실행 ===")
        for i in range(min(steps, len(actions))):
            action = actions[i % len(actions)]
            data = {}
            if action.is_complex():
                data = {"x": 32, "y": 32}

            obs = env.step(action, data=data)
            if obs and obs.frame:
                curr_frame = obs.frame[0]
                diff = compute_diff(prev_frame, curr_frame)
                print(f"\n  Step {i+1}: {action.name} → "
                      f"state={obs.state}, changed={diff['changed_pixels']}px")
                prev_frame = curr_frame


def main() -> int:
    parser = argparse.ArgumentParser(description="프레임 분석 도구")
    parser.add_argument("--game", type=str, help="게임 ID")
    parser.add_argument("--steps", type=int, default=5, help="분석할 스텝 수")
    args = parser.parse_args()

    if args.game:
        run_game_analysis(args.game, args.steps)
    else:
        print("Usage: python scripts/analyze_frame.py --game <game_id>")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
