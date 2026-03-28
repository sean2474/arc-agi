"""액션 이름/숫자 → GameAction 변환. click+object 지원."""

import re
from arcengine import GameAction
from .const import ACTION_NAME_TO_NUM

ACTION_NUM_MAP = {
    1: GameAction.ACTION1, 2: GameAction.ACTION2,
    3: GameAction.ACTION3, 4: GameAction.ACTION4,
    5: GameAction.ACTION5, 6: GameAction.ACTION6,
    7: GameAction.ACTION7,
}

_NUM_TO_NAME = {v: k for k, v in ACTION_NAME_TO_NUM.items()}


def _parse_position(pos_str: str) -> tuple[int, int] | None:
    """position 문자열에서 중심 좌표 추출. 'row 46-47, col 33-37' → (35, 46)"""
    rows = re.findall(r'row\s*(\d+)(?:\s*-\s*(\d+))?', str(pos_str))
    cols = re.findall(r'col\s*(\d+)(?:\s*-\s*(\d+))?', str(pos_str))
    if not rows or not cols:
        return None
    r1 = int(rows[0][0])
    r2 = int(rows[0][1]) if rows[0][1] else r1
    c1 = int(cols[0][0])
    c2 = int(cols[0][1]) if cols[0][1] else c1
    return ((c1 + c2) // 2, (r1 + r2) // 2)  # (x, y)


def resolve_click_object(object_name: str, world_model: dict) -> tuple[int, int] | None:
    """object 이름 → 좌표. name 필드로 검색, fallback으로 bbox center."""
    objects = world_model.get("objects", {})
    # obj_NNN 직접 키 시도 (하위호환)
    obj = objects.get(object_name)
    if not obj:
        # name 필드로 검색
        for v in objects.values():
            if isinstance(v, dict) and v.get("name") == object_name:
                obj = v
                break
    if not obj:
        return None
    # bbox center 우선, position 문자열 fallback
    bbox = obj.get("bbox")
    if bbox:
        x = (bbox.get("col_min", 0) + bbox.get("col_max", 0)) // 2
        y = (bbox.get("row_min", 0) + bbox.get("row_max", 0)) // 2
        return (x, y)
    return _parse_position(obj.get("position", ""))


def action_to_gameaction(item, available_values: set[int], world_model: dict | None = None) -> tuple[GameAction, str] | None:
    """액션 이름/숫자/클릭 → (GameAction, display_name). 무효하면 None."""
    # click: ["click", x, y] (좌표 직접)
    if isinstance(item, list) and len(item) == 3:
        key = item[0]
        if key == "click" or key == 6:
            action = GameAction.ACTION6
            x, y = int(item[1]), int(item[2])
            action.set_data({"x": x, "y": y})
            return action, f"click({x},{y})"
        return None

    # click: ["click", "object_name"] (object 대상)
    if isinstance(item, list) and len(item) == 2:
        key = item[0]
        if (key == "click" or key == 6) and isinstance(item[1], str) and world_model:
            coords = resolve_click_object(item[1], world_model)
            if coords:
                action = GameAction.ACTION6
                action.set_data({"x": coords[0], "y": coords[1]})
                return action, f"click({item[1]}@{coords[0]},{coords[1]})"
        return None

    # 일반 액션 이름
    if isinstance(item, str):
        val = ACTION_NAME_TO_NUM.get(item.lower())
        if val is None:
            return None
    else:
        val = int(item)

    if val not in available_values or val == 0:
        return None

    action = ACTION_NUM_MAP.get(val)
    if action is None:
        return None
    return action, _NUM_TO_NAME.get(val, f"action{val}")
