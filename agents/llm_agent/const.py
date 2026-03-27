"""ARC-AGI-3 에이전트 상수 정의."""

# ── Phase System ──

def get_current_phase(world_model: dict) -> str:
    """world_model 상태를 보고 현재 phase 반환."""
    objects = world_model.get("objects", {})
    actions = world_model.get("actions", {})

    if not objects:
        return "static_observation"

    action_avg = sum(a.get("confidence", 0) for a in actions.values()) / max(len(actions), 1)
    if action_avg < 0.7:
        return "action_discovery"

    untested = [k for k, v in objects.items()
                if v.get("type") in ("unknown", "static") and not v.get("interaction_tested")]
    if untested:
        return "interaction_discovery"

    return "goal_execution"


def get_phase_hint(world_model: dict) -> str:
    """현재 phase에 맞는 DECIDE 힌트 생성."""
    phase = get_current_phase(world_model)

    if phase == "static_observation":
        return "Phase: STATIC_OBSERVATION. First frame — identify all objects on screen."

    if phase == "action_discovery":
        untested = [k for k, v in world_model.get("actions", {}).items() if v.get("confidence", 0) == 0.0]
        if untested:
            return f"Phase: ACTION_DISCOVERY. Untested actions: {untested}. Test one."
        low = [k for k, v in world_model.get("actions", {}).items() if v.get("confidence", 0) < 0.7]
        return f"Phase: ACTION_DISCOVERY. Low confidence actions: {low}. Verify one."

    if phase == "interaction_discovery":
        candidates = [k for k, v in world_model.get("objects", {}).items()
                      if v.get("type") in ("unknown", "static") and not v.get("interaction_tested")]
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
