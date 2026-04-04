"""게임 상태를 LLM 프롬프트로 변환한다.

게임별로 다른 프롬프트가 필요하므로 Strategy 패턴.
PromptBuilder는 GameState.extracted를 받아서
system prompt + user message를 생성한다.
"""

from abc import ABC, abstractmethod

from src.agent.base import GameState


class PromptBuilder(ABC):
    """프롬프트 빌더 인터페이스."""

    @abstractmethod
    def build_system(self) -> str:
        """시스템 프롬프트를 생성한다. (캐싱 대상, 매 턴 동일)"""
        ...

    @abstractmethod
    def build_user_message(self, state: GameState, history: list[dict]) -> str | list:
        """현재 상태로부터 유저 메시지를 생성한다.

        Returns:
            str (텍스트 전용) 또는 list (이미지 + 텍스트 블록).
        """
        ...


class Ls20PromptBuilder(PromptBuilder):
    """ls20 전용 프롬프트 빌더."""

    def build_system(self) -> str:
        return LS20_SYSTEM_PROMPT

    def build_user_message(self, state: GameState, history: list[dict]) -> str | list:
        ext = state.extracted
        if not ext:
            return "No state available."

        player = ext["player"]
        tool = ext["tool"]
        slots = ext["slots"]

        # 슬롯 정보
        slot_lines = []
        for s in slots:
            match = "MATCH" if s.get("matches_current") else "mismatch"
            slot_lines.append(
                f"  - Slot {s['index']} at ({s['x']},{s['y']}): "
                f"shape={s['required_shape']}, "
                f"color={s['required_color']}({_color_name(s['required_color'])}), "
                f"rotation={s['required_rotation']}° "
                f"[{match}]"
            )
        slot_text = "\n".join(slot_lines) if slot_lines else "  (all cleared!)"

        # 히스토리
        recent = history[-5:] if history else []
        history_lines = []
        for h in recent:
            event = h.get("event", "")
            moved = h.get("moved", True)
            old = h.get("player_pos", [])
            new = h.get("new_pos", [])
            move_str = f"→ ({new[0]},{new[1]})" if moved and new else "→ BLOCKED (wall!)"
            history_lines.append(
                f"  Step {h['step']}: {h['action']} {move_str}"
                + (f" {event}" if event else "")
            )
        history_text = "\n".join(history_lines) if history_lines else "  (none)"

        # 맵
        tile_map = ext.get("tile_map", "(unavailable)")

        msg = f"""## Current State
- Position: ({player['x']}, {player['y']})
- Tool: shape={tool['shape']}({tool['shape_name']}), color={tool['color']}({tool['color_name']}), rotation={tool['rotation']}°
- Lives: {ext['lives']}/3
- Energy: {ext['energy']}/{ext['max_energy']}
- Slots remaining: {ext['slots_remaining']}
- Level: {ext['level']}

## Slot Requirements
{slot_text}

## Map (P=player, #=wall, Tn=slot, .=open)
{tile_map}

## Recent Actions
{history_text}

Choose your next action."""

        return msg


def _color_name(color_value: int) -> str:
    names = {12: "red", 9: "orange", 14: "cyan", 8: "blue"}
    return names.get(color_value, str(color_value))


LS20_SYSTEM_PROMPT = """You are playing an ARC-AGI-3 puzzle game called "ls20".

## Game Rules

### Movement
- ACTION1: Move up (y -= 5)
- ACTION2: Move down (y += 5)
- ACTION3: Move left (x -= 5)
- ACTION4: Move right (x += 5)
- You move 5 pixels per step on a 64x64 grid
- Walls (#) block movement

### Your Tool
You carry a cursor tool with 3 properties:
- Shape: index 0-5 (6 different shapes)
- Color: one of red(12), orange(9), cyan(14), blue(8)
- Rotation: one of 0°, 90°, 180°, 270°

### Modifier Pads (on the map)
Stepping on special pads changes your tool:
- Shape pad: cycles shape to next index (0→1→2→3→4→5→0)
- Color pad: cycles color (12→9→14→8→12...)
- Rotation pad: rotates +90° (0→90→180→270→0...)

### Win Condition
- Each level has target slots (shown as Tn on map)
- Each slot requires a specific (shape, color, rotation) combination
- When your tool matches a slot's requirement AND you stand on it → slot cleared
- Clear ALL slots to complete the level

### Lose Condition
- You have 3 lives and limited energy per attempt
- Moving without clearing slots costs energy
- Energy depleted → lose a life, position/tool resets
- 0 lives → game over

## Strategy Tips
- Check which slots you can reach with current tool settings
- Plan path through modifier pads to get the right tool configuration
- If a slot shows [MATCH], go directly to it
- Minimize unnecessary moves to conserve energy

## Response Format
Respond with ONLY this JSON (no other text):
{"thinking": "your step-by-step reasoning", "action": N}
where N is 1 (up), 2 (down), 3 (left), or 4 (right)."""
