"""프레임 변화 관찰자. LLM 호출 없이 코드로 변화를 감지한다.

매 스텝 이전/이후 프레임을 비교하여:
- 이동 성공/실패
- 도구 속성 변경 (패드 밟음)
- 슬롯 클리어
- 에너지/lives 변화
- 위치 리셋 (에너지 소진)
를 감지한다.
"""

from dataclasses import dataclass, field


@dataclass
class Observation:
    """한 스텝의 관찰 결과."""

    moved: bool = False
    blocked: bool = False
    old_pos: tuple[int, int] = (0, 0)
    new_pos: tuple[int, int] = (0, 0)

    tool_changed: bool = False
    tool_change_detail: str = ""  # "shape: 5→0", "color: 9→14", "rotation: 270→0"

    slot_cleared: bool = False
    slots_remaining: int = 0

    energy_changed: bool = False
    old_energy: int = 0
    new_energy: int = 0

    lives_changed: bool = False
    old_lives: int = 0
    new_lives: int = 0

    position_reset: bool = False  # 에너지 소진으로 리셋

    summary: str = ""


class Observer:
    """프레임 변화를 코드로 관찰한다."""

    def __init__(self) -> None:
        self._prev_state: dict | None = None

    def observe(self, extracted: dict) -> Observation:
        """이전 상태와 현재 상태를 비교하여 변화를 감지한다."""
        obs = Observation()

        if self._prev_state is None:
            self._prev_state = extracted
            obs.summary = "Game start"
            obs.new_pos = (extracted["player"]["x"], extracted["player"]["y"])
            obs.slots_remaining = extracted["slots_remaining"]
            return obs

        prev = self._prev_state
        curr = extracted

        # 위치 변화
        old_pos = (prev["player"]["x"], prev["player"]["y"])
        new_pos = (curr["player"]["x"], curr["player"]["y"])
        obs.old_pos = old_pos
        obs.new_pos = new_pos

        # 큰 거리 이동 = 리셋
        dx = abs(new_pos[0] - old_pos[0])
        dy = abs(new_pos[1] - old_pos[1])
        if dx > 5 or dy > 5:
            obs.position_reset = True
            obs.moved = True
        elif old_pos != new_pos:
            obs.moved = True
        else:
            obs.blocked = True

        # 도구 변화
        prev_tool = prev["tool"]
        curr_tool = curr["tool"]
        changes = []
        if prev_tool["shape"] != curr_tool["shape"]:
            changes.append(f"shape: {prev_tool['shape']}→{curr_tool['shape']}")
        if prev_tool["color"] != curr_tool["color"]:
            changes.append(f"color: {prev_tool['color_name']}→{curr_tool['color_name']}")
        if prev_tool["rotation"] != curr_tool["rotation"]:
            changes.append(f"rotation: {prev_tool['rotation']}→{curr_tool['rotation']}")
        if changes:
            obs.tool_changed = True
            obs.tool_change_detail = ", ".join(changes)

        # 슬롯 변화
        obs.slots_remaining = curr["slots_remaining"]
        if curr["slots_remaining"] < prev["slots_remaining"]:
            obs.slot_cleared = True

        # 에너지 변화
        obs.old_energy = prev["energy"]
        obs.new_energy = curr["energy"]
        if prev["energy"] != curr["energy"]:
            obs.energy_changed = True

        # Lives 변화
        obs.old_lives = prev["lives"]
        obs.new_lives = curr["lives"]
        if prev["lives"] != curr["lives"]:
            obs.lives_changed = True

        # 요약 생성
        obs.summary = self._summarize(obs)
        self._prev_state = curr

        return obs

    def _summarize(self, obs: Observation) -> str:
        parts = []

        if obs.position_reset:
            parts.append("RESET! Position was reset (energy depleted)")
        elif obs.blocked:
            parts.append("BLOCKED — wall")
        else:
            parts.append(f"Moved to ({obs.new_pos[0]},{obs.new_pos[1]})")

        if obs.tool_changed:
            parts.append(f"Tool changed: {obs.tool_change_detail}")

        if obs.slot_cleared:
            parts.append("SLOT CLEARED!")

        if obs.lives_changed:
            parts.append(f"Lives: {obs.old_lives}→{obs.new_lives}")

        if obs.energy_changed and not obs.position_reset:
            parts.append(f"Energy: {obs.new_energy}")

        return " | ".join(parts)

    def reset(self) -> None:
        self._prev_state = None
