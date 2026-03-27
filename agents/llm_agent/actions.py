"""액션 이름/숫자 → GameAction 변환."""

from arcengine import GameAction
from .const import ACTION_NAME_TO_NUM

ACTION_NUM_MAP = {
    1: GameAction.ACTION1, 2: GameAction.ACTION2,
    3: GameAction.ACTION3, 4: GameAction.ACTION4,
    5: GameAction.ACTION5, 6: GameAction.ACTION6,
    7: GameAction.ACTION7,
}

_NUM_TO_NAME = {v: k for k, v in ACTION_NAME_TO_NUM.items()}


def action_to_gameaction(item, available_values: set[int]) -> tuple[GameAction, str] | None:
    """액션 이름/숫자/클릭 → (GameAction, display_name). 무효하면 None."""
    if isinstance(item, list) and len(item) == 3:
        key = item[0]
        if key == "click" or key == 6:
            action = GameAction.ACTION6
            x, y = int(item[1]), int(item[2])
            action.set_data({"x": x, "y": y})
            return action, f"click({x},{y})"
        return None

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
