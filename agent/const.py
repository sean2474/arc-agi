"""ARC-AGI-3 에이전트 상수 정의."""

# ── 액션 매핑 ──
ACTION_LABELS = {
    1: "UP",
    2: "DOWN",
    3: "LEFT",
    4: "RIGHT",
    5: "INTERACT/SELECT",
    6: "CLICK(x,y)",
    7: "UNDO",
}

# 숫자 → 이름 (LLM 시퀀스용)
ACTION_NUM_TO_NAME = {
    1: "up", 2: "down", 3: "left", 4: "right",
    5: "interact", 6: "click", 7: "undo",
}
ACTION_NAME_TO_NUM = {v: k for k, v in ACTION_NUM_TO_NAME.items()}
ACTION_NAME_TO_NUM["space"] = 5  # backwards compat alias

ACTION_PROMPT_LINE = "  ".join(f"{k}: {v}" for k, v in ACTION_LABELS.items())

# ── ARC 16색 팔레트 ──
ARC_COLOR_NAMES = {
    "0": "white", "1": "off-white", "2": "light-gray", "3": "gray",
    "4": "dark-gray", "5": "black", "6": "magenta", "7": "pink",
    "8": "red", "9": "blue", "a": "light-blue", "b": "yellow",
    "c": "orange", "d": "maroon", "e": "green", "f": "purple",
}

# → "0=black  1=blue  2=red  3=green  4=yellow  5=gray  ..."
ARC_COLORS = [
    "#FFFFFF",  #  0: white
    "#CCCCCC",  #  1: off-white
    "#999999",  #  2: light-gray
    "#666666",  #  3: gray
    "#333333",  #  4: dark-gray
    "#000000",  #  5: black
    "#E53AA3",  #  6: magenta
    "#FF7BCC",  #  7: pink
    "#F93C31",  #  8: red
    "#1E93FF",  #  9: blue
    "#88D8F1",  # 10: light-blue
    "#FFDC00",  # 11: yellow
    "#FF851B",  # 12: orange
    "#921231",  # 13: maroon
    "#4FCC30",  # 14: green
    "#A356D6",  # 15: purple
]
