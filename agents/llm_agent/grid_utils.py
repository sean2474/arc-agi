"""그리드 변환, diff 계산, 이미지 렌더링, 트리거 감지."""

import io
import re
import base64
from collections import Counter
from arcengine import GameState

from .const import ARC_COLORS


def _hex_to_arc_index(hex_str: str) -> str | None:
    """'4FCC30' or '#4FCC30' → ARC index char ('e'). 매치 없으면 None."""
    norm = hex_str.strip().lstrip("#").upper()
    for i, c in enumerate(ARC_COLORS):
        if c.lstrip("#").upper() == norm:
            return format(i, "x")
    return None


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
    1순위: position "row,col" + size "HxW" → bbox 계산
    2순위: grid + value로 직접 스캔 (fallback)
    계산된 bbox는 실제 그리드 크기에 맞게 클램핑.
    """
    max_row = len(grid) - 1 if grid else 63
    max_col = len(grid[0]) - 1 if grid else 63
    for obj in objects.values():
        if not isinstance(obj, dict):
            continue
        if obj.get("bbox") and isinstance(obj["bbox"], dict):
            continue

        pos = obj.get("position", "")

        bbox = None

        # 1순위: position "row,col" + size "HxW"
        pos_nums = re.findall(r"\d+", pos)
        size_nums = re.findall(r"\d+", obj.get("size", ""))
        if len(pos_nums) >= 2 and len(size_nums) >= 2:
            row, col = int(pos_nums[0]), int(pos_nums[1])
            h, w = int(size_nums[0]), int(size_nums[1])
            bbox = {"row_min": row, "row_max": row + h - 1,
                    "col_min": col, "col_max": col + w - 1}
        elif len(pos_nums) == 2:
            row, col = int(pos_nums[0]), int(pos_nums[1])
            bbox = {"row_min": row, "row_max": row,
                    "col_min": col, "col_max": col}

        if bbox:
            # 범위 벗어난 좌표 체크
            if bbox["col_min"] > max_col or bbox["row_min"] > max_row:
                raise RuntimeError(
                    f"Object '{obj.get('name')}' position out of bounds: "
                    f"row={bbox['row_min']}, col={bbox['col_min']} (grid {max_row+1}x{max_col+1})"
                )
            clamped = {
                "row_min": max(0, bbox["row_min"]),
                "row_max": min(max_row, bbox["row_max"]),
                "col_min": max(0, bbox["col_min"]),
                "col_max": min(max_col, bbox["col_max"]),
            }
            if clamped["col_min"] > clamped["col_max"] or clamped["row_min"] > clamped["row_max"]:
                raise RuntimeError(
                    f"Object '{obj.get('name')}' bbox inverted after clamp: {clamped}"
                )
            obj["bbox"] = clamped

            # 색상 검증: bbox 영역에 해당 색상 없으면 에러
            if grid:
                colors = obj.get("colors", [])
                arc_indices = {idx for c in colors if (idx := _hex_to_arc_index(c)) is not None}
                if arc_indices:
                    b = clamped
                    found = any(
                        grid[r][c] in arc_indices
                        for r in range(b["row_min"], b["row_max"] + 1)
                        for c in range(b["col_min"], b["col_max"] + 1)
                    )
                    if not found:
                        raise RuntimeError(
                            f"Object '{obj.get('name')}' colors {colors} not found in bbox {clamped}"
                        )
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


def grid_to_image_base64_with_coords(grid: list[str], scale: int = 8, every: int = 8) -> str:
    """SCAN용: row/col 좌표 레이블 오버레이. every 셀마다 번호 표시."""
    from PIL import ImageDraw

    img = _render_grid(grid, scale)
    draw = ImageDraw.Draw(img)
    rows = len(grid)
    cols = len(grid[0]) if grid else 0

    label_color = (255, 255, 0)  # yellow
    bg_color = (0, 0, 0, 180)

    for r in range(0, rows, every):
        y = r * scale
        draw.rectangle([0, y, scale - 1, y + scale - 1], fill=(0, 0, 0))
        draw.text((1, y + 1), str(r), fill=label_color)

    for c in range(0, cols, every):
        x = c * scale
        draw.rectangle([x, 0, x + scale - 1, scale - 1], fill=(0, 0, 0))
        draw.text((x + 1, 1), str(c), fill=label_color)

    return _img_to_base64(img)


_ANNOTATION_COLORS = [
    "#FFFFFF", "#FFFF00", "#FF00FF", "#00FFFF",
    "#FF8800", "#00FF88", "#FF4444", "#44FF44",
]


def grid_to_image_base64_annotated(
    grid: list[str],
    objects: dict,
    scale: int = 8,
    label_mode: str = "name",  # "name": name or obj_id fallback | "id": always obj_id
) -> str:
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
        x1 = max(x0, (col_max + 1) * scale - 1)
        y1 = max(y0, (row_max + 1) * scale - 1)

        color = _ANNOTATION_COLORS[i % len(_ANNOTATION_COLORS)]
        draw.rectangle([x0, y0, x1, y1], outline=color, width=2)

        if label_mode == "id":
            label = obj_id
        else:
            display_name = obj.get("name") or obj_id
            type_hyp = obj.get("type_hypothesis", "")
            label = display_name if (not type_hyp or type_hyp == "unknown") else f"{display_name}:{type_hyp}"
        draw.text((x0 + 2, y0 + 2), label, fill=color)

    return _img_to_base64(img)


def blobs_to_annotation_dict(blobs: dict) -> dict:
    """BlobManager blobs → grid_to_image_base64_annotated용 dict (present blobs만)."""
    result = {}
    for oid, b in blobs.items():
        if not b.is_present:
            continue
        result[oid] = {
            "name": b.name or oid,
            "bbox": b.bbox,
            "type_hypothesis": b.type_hypothesis or "unknown",
        }
    return result


def format_events_for_prompt(animation_events: list[dict], result_events: list[dict]) -> str:
    """BlobManager events → LLM 프롬프트용 텍스트."""
    lines = []

    def _label(ev: dict, key: str = "obj", name_key: str = "name") -> str:
        oid = ev.get(key, "?")
        name = ev.get(name_key, "")
        return f"{oid}({name})" if name and name != oid else oid

    def _delta_text(dr: int, dc: int) -> str:
        parts = []
        if dr < 0:
            parts.append(f"{abs(dr)} pixel{'s' if abs(dr) != 1 else ''} up")
        elif dr > 0:
            parts.append(f"{dr} pixel{'s' if dr != 1 else ''} down")
        if dc < 0:
            parts.append(f"{abs(dc)} pixel{'s' if abs(dc) != 1 else ''} left")
        elif dc > 0:
            parts.append(f"{dc} pixel{'s' if dc != 1 else ''} right")
        return ", ".join(parts) if parts else "0 pixels (no net movement)"

    def _rot_text(deg) -> str:
        d = int(deg)
        if d > 0:
            return f"rotated {d}° clockwise"
        elif d < 0:
            return f"rotated {abs(d)}° counter-clockwise"
        return "rotated 0°"

    def _fmt(ev: dict) -> str | None:
        t = ev.get("type", "")
        if t == "move":
            dr, dc = ev.get("delta", [0, 0])
            return f"  {_label(ev)} moved {_delta_text(dr, dc)}"
        if t == "collide":
            a = _label(ev, "obj_a", "name_a")
            b = _label(ev, "obj_b", "name_b")
            return f"  {a} and {b} collided"
        if t == "disappear":
            cause = ev.get("cause", "unknown")
            return f"  {_label(ev)} disappeared (cause: {cause})"
        if t == "appear":
            pos = ev.get("pos", ev.get("last_pos", ["?", "?"]))
            return f"  {_label(ev)} appeared at row {pos[0]}, col {pos[1]}"
        if t == "rotation":
            return f"  {_label(ev)} {_rot_text(ev.get('angle_deg', 0))}"
        if t == "transform":
            return f"  {_label(ev)} changed appearance (color diff={ev.get('color_diff', 0):.2f})"
        if t == "merge":
            a = _label(ev, "obj_a", "name_a")
            b = _label(ev, "obj_b", "name_b")
            return f"  {a} and {b} merged into one object"
        if t == "camera_shift":
            dr, dc = ev.get("delta", [0, 0])
            return f"  camera moved {_delta_text(dr, dc)}"
        if t == "camera_rotation":
            return f"  camera {_rot_text(ev.get('angle_deg', 0))}"
        if t == "game_over":
            return f"  game over"
        return None

    if animation_events:
        lines.append("animation:")
        for ev in animation_events:
            s = _fmt(ev)
            if s:
                lines.append(s)
    else:
        lines.append("animation: (none)")

    if result_events:
        lines.append("result:")
        for ev in result_events:
            s = _fmt(ev)
            if s:
                lines.append(s)
    else:
        lines.append("result: (none)")

    return "\n".join(lines)

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
