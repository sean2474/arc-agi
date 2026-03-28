"""그리드 변환, diff 계산, 이미지 렌더링, 트리거 감지."""

import io
import re
import base64
from collections import Counter
from arcengine import GameState

from .const import ARC_COLORS


def compute_bbox_from_grid(grid: list[str], hex_value: str) -> dict | None:
    """그리드에서 특정 색상(hex) 셀의 bounding box 계산."""
    rows, cols = [], []
    for y, row in enumerate(grid):
        for x, cell in enumerate(row):
            if cell == hex_value:
                rows.append(y)
                cols.append(x)
    if not rows:
        return None
    return {"row_min": min(rows), "row_max": max(rows),
            "col_min": min(cols), "col_max": max(cols)}


def enrich_objects_bbox(objects: dict, grid: list[str] | None = None) -> dict:
    """scan/observe 결과 objects에 bbox 보장.
    position이 "n,n" (단일 좌표) 형태일 때만 bbox 계산.
    "n-n,n-n" (범위) 형태는 건너뜀 (넓은 영역은 아웃라인 불필요).
    """
    for obj in objects.values():
        if not isinstance(obj, dict):
            continue
        if obj.get("bbox") and isinstance(obj["bbox"], dict):
            continue

        pos = obj.get("position", "")

        # 범위 형태(n-n)는 건너뜀
        if "-" in pos:
            continue

        bbox = None

        # grid + value로 직접 계산
        if grid is not None:
            val = obj.get("value", "")
            if val and len(val) == 1:
                bbox = compute_bbox_from_grid(grid, val)

        # fallback: "n,n" 또는 "(n,n)" 파싱
        if bbox is None and pos:
            nums = re.findall(r"\d+", pos)
            if len(nums) == 2:
                bbox = {"row_min": int(nums[0]), "row_max": int(nums[0]),
                        "col_min": int(nums[1]), "col_max": int(nums[1])}

        if bbox:
            obj["bbox"] = bbox
    return objects


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


def _render_grid(grid: list[str], scale: int = 8):
    """compact grid → PIL Image."""
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

    return img


def _img_to_base64(img) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def grid_to_image_base64(grid: list[str], scale: int = 8) -> str:
    """compact grid → base64 PNG 이미지. VLM에 전달용."""
    return _img_to_base64(_render_grid(grid, scale))


_ANNOTATION_COLORS = [
    "#FFFFFF", "#FFFF00", "#FF00FF", "#00FFFF",
    "#FF8800", "#00FF88", "#FF4444", "#44FF44",
]


def grid_to_image_base64_annotated(grid: list[str], objects: dict, scale: int = 8) -> str:
    """compact grid → base64 PNG with bbox outlines + labels for each object."""
    from PIL import ImageDraw

    img = _render_grid(grid, scale)
    draw = ImageDraw.Draw(img)

    for i, (obj_id, obj) in enumerate(objects.items()):
        if not isinstance(obj, dict):
            continue
        bbox = obj.get("bbox")
        if not bbox:
            continue

        row_min = bbox.get("row_min", 0)
        row_max = bbox.get("row_max", row_min)
        col_min = bbox.get("col_min", 0)
        col_max = bbox.get("col_max", col_min)

        x0 = col_min * scale
        y0 = row_min * scale
        x1 = (col_max + 1) * scale - 1
        y1 = (row_max + 1) * scale - 1

        color = _ANNOTATION_COLORS[i % len(_ANNOTATION_COLORS)]
        draw.rectangle([x0, y0, x1, y1], outline=color, width=2)

        type_hyp = obj.get("type_hypothesis", "")
        label = obj_id if (not type_hyp or type_hyp == "unknown") else f"{obj_id}:{type_hyp}"
        draw.text((x0 + 2, y0 + 2), label, fill=color)

    return _img_to_base64(img)

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
