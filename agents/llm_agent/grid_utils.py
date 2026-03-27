"""그리드 변환, diff 계산, 트리거 감지."""

from arcengine import GameState


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
