"""그리드 변환, diff 계산, 이미지 렌더링, 트리거 감지."""

import io
import base64
from collections import Counter
from arcengine import GameState

from .const import ARC_COLORS


def frame_to_compact(frame) -> list[str]:
    """64x64 int8 ndarray → 행별 hex 문자열."""
    return ["".join(format(v, "x") for v in row) for row in frame]


def compute_diff(prev: list[str], curr: list[str]) -> list[dict]:
    """두 compact 그리드 비교 → 변경 셀 목록."""
    changes = []
    for y in range(len(prev)):
        for x in range(len(prev[y])):
            if prev[y][x] != curr[y][x]:
                changes.append({"x": x, "y": y, "from": prev[y][x], "to": curr[y][x]})
    return changes


def summarize_diff(prev: list[str], curr: list[str]) -> str:
    """두 그리드의 diff를 텍스트 요약으로 반환."""
    changes = compute_diff(prev, curr)
    if not changes:
        return "NO CHANGES."

    total = len(changes)
    xs = [c["x"] for c in changes]
    ys = [c["y"] for c in changes]
    region = f"rows {min(ys)}-{max(ys)}, cols {min(xs)}-{max(xs)}"

    transitions = Counter(f"{c['from']}→{c['to']}" for c in changes)
    top_transitions = ", ".join(f"{k}: {v}" for k, v in transitions.most_common(5))

    cell_list = "\n".join(
        f"  ({c['x']},{c['y']}): {c['from']}→{c['to']}" for c in changes[:20]
    )
    truncated = f"\n  ... and {total - 20} more" if total > 20 else ""

    return f"""{total} cells changed in {region}
Transitions: {top_transitions}
Changed cells:
{cell_list}{truncated}"""


def grid_to_image_base64(grid: list[str], scale: int = 8) -> str:
    """compact grid → base64 PNG 이미지. VLM에 전달용."""
    from PIL import Image

    size = len(grid)
    img = Image.new("RGB", (size * scale, size * scale))
    pixels = img.load()

    hex_to_rgb = {}
    for i, color in enumerate(ARC_COLORS):
        r = int(color[1:3], 16)
        g = int(color[3:5], 16)
        b = int(color[5:7], 16)
        hex_to_rgb[format(i, "x")] = (r, g, b)

    for y, row in enumerate(grid):
        for x, cell in enumerate(row):
            rgb = hex_to_rgb.get(cell, (0, 0, 0))
            for dy in range(scale):
                for dx in range(scale):
                    pixels[x * scale + dx, y * scale + dy] = rgb

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")

def detect_triggers(
    prev_grid: list[str] | None,
    curr_grid: list[str],
    prev_levels: int,
    curr_state: GameState,
    curr_levels: int,
    replan_conditions: list[str],
) -> tuple[list[str], list[dict]]:
    """트리거 감지. (triggers, diff) 반환."""
    triggers: list[str] = []
    diff: list[dict] = []

    if prev_grid is None:
        return ["initial"], diff

    diff = compute_diff(prev_grid, curr_grid)

    if curr_state == GameState.GAME_OVER:
        triggers.append("game_over")

    if curr_levels > prev_levels:
        triggers.append(f"level_complete: {prev_levels}→{curr_levels}")

    if len(diff) == 0:
        triggers.append("no_change")

    prev_vals = set(c for row in prev_grid for c in row)
    curr_vals = set(c for row in curr_grid for c in row)
    new_vals = curr_vals - prev_vals
    if new_vals:
        triggers.append(f"new_value_appeared: {sorted(new_vals)}")

    for cond in replan_conditions:
        if cond == "new_value" and new_vals:
            triggers.append(f"replan:{cond}")
        elif cond == "game_over" and curr_state == GameState.GAME_OVER:
            triggers.append(f"replan:{cond}")
        elif cond == "no_change" and len(diff) == 0:
            triggers.append(f"replan:{cond}")

    return triggers, diff
