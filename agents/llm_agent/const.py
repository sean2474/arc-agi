"""ARC-AGI-3 에이전트 상수 정의."""

# ── Phase System ──

def _get_action_max_confidence(action_data: dict) -> float:
    """action의 effects에서 최대 confidence 반환."""
    effects = action_data.get("effects", [])
    if not effects:
        return action_data.get("confidence", 0.0)
    return max(e.get("confidence", 0.0) for e in effects)


def get_current_phase(world_model: dict) -> str:
    """world_model 상태를 보고 현재 phase 반환. 비선형."""
    objects = world_model.get("objects", {})
    actions = world_model.get("actions", {})
    goal = world_model.get("goal", {})

    if not objects:
        return "static_observation"

    # untested action 체크
    untested_actions = any(
        _get_action_max_confidence(a) == 0.0
        for a in actions.values()
    )

    # goal 가설이 있어도 untested action이 있으면 action_discovery 우선
    if untested_actions:
        return "action_discovery"

    # goal 가설이 있으면 goal_execution
    if goal.get("confidence", 0) >= 0.3:
        return "goal_execution"

    # untested object 체크
    untested_objects = any(
        not o.get("interaction_tested") and o.get("type_hypothesis") not in ("non-interactive", "background")
        for o in objects.values()
    )
    if untested_objects:
        return "interaction_discovery"

    return "goal_execution"


def get_phase_hint(world_model: dict) -> str:
    """현재 phase에 맞는 DECIDE 힌트 생성."""
    phase = get_current_phase(world_model)
    actions = world_model.get("actions", {})
    objects = world_model.get("objects", {})

    if phase == "static_observation":
        return "Phase: STATIC_OBSERVATION. Scan first."

    if phase == "action_discovery":
        untested = [k for k, v in actions.items() if _get_action_max_confidence(v) == 0.0]
        if untested:
            return f"Phase: ACTION_DISCOVERY. Untested: {untested}. Test one."
        low = [k for k, v in actions.items() if _get_action_max_confidence(v) < 0.7]
        return f"Phase: ACTION_DISCOVERY. Low confidence: {low}. Verify one."

    if phase == "interaction_discovery":
        candidates = [k for k, v in objects.items()
                      if not v.get("interaction_tested") and v.get("type_hypothesis") not in ("non-interactive", "background")]
        return f"Phase: INTERACTION_DISCOVERY. Untested objects: {candidates}. Approach one."

    goal = world_model.get("goal", {})
    return f"Phase: GOAL_EXECUTION. Goal: {goal.get('description', 'unknown')}. Execute strategy."

# ── 액션 매핑 ──
ACTION_LABELS = {
    1: "UP",
    2: "DOWN",
    3: "LEFT",
    4: "RIGHT",
    5: "SPACEBAR",
    6: "CLICK(x,y)",
    7: "UNDO",
}

# 숫자 → 이름 (LLM 시퀀스용)
ACTION_NUM_TO_NAME = {
    1: "up", 2: "down", 3: "left", 4: "right",
    5: "space", 6: "click", 7: "undo",
}
ACTION_NAME_TO_NUM = {v: k for k, v in ACTION_NUM_TO_NAME.items()}

ACTION_PROMPT_LINE = "  ".join(f"{k}: {v}" for k, v in ACTION_LABELS.items())

# ── ARC 16색 팔레트 ──
ARC_COLOR_NAMES = {
    "0": "black", "1": "blue", "2": "red", "3": "green",
    "4": "yellow", "5": "gray", "6": "magenta", "7": "orange",
    "8": "sky", "9": "maroon", "a": "purple", "b": "teal",
    "c": "lime", "d": "burgundy", "e": "olive", "f": "white",
}

COLOR_PROMPT_LINE = "  ".join(f"{k}={v}" for k, v in ARC_COLOR_NAMES.items())
# → "0=black  1=blue  2=red  3=green  4=yellow  5=gray  ..."
ARC_COLORS = [
    "#000000",  #  0: 검정
    "#0074D9",  #  1: 파랑
    "#FF4136",  #  2: 빨강
    "#2ECC40",  #  3: 초록
    "#FFDC00",  #  4: 노랑
    "#AAAAAA",  #  5: 회색
    "#F012BE",  #  6: 마젠타
    "#FF851B",  #  7: 주황
    "#7FDBFF",  #  8: 하늘
    "#870C25",  #  9: 적갈색
    "#B10DC9",  # 10: 보라
    "#39CCCC",  # 11: 청록
    "#01FF70",  # 12: 연두
    "#85144b",  # 13: 자주
    "#3D9970",  # 14: 올리브
    "#FFFFFF",  # 15: 흰색
]
