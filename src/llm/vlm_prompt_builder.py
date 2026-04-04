"""VLM용 프롬프트 빌더.

프레임 이미지를 직접 보여주고 상태 텍스트와 함께 전송.
텍스트 맵 대신 이미지로 공간 파악을 시킴.
"""

import numpy as np

from src.agent.base import GameState
from src.llm.frame_renderer import frame_to_base64
from src.llm.prompt_builder import PromptBuilder


class Ls20VLMPromptBuilder(PromptBuilder):
    """ls20 VLM 프롬프트 빌더 — 프레임 이미지 + 상태 텍스트."""

    def build_system(self) -> str:
        return LS20_VLM_SYSTEM

    def build_user_message(self, state: GameState, history: list[dict]) -> str | list:
        """이미지 + 텍스트를 포함한 content 블록을 반환한다."""
        ext = state.extracted
        if not ext:
            return "No state available."

        # 프레임 이미지 생성
        image_block = None
        if state.frame_raw:
            raw = state.frame_raw[0]
            frame = np.array(raw) if not isinstance(raw, np.ndarray) else raw
            b64 = frame_to_base64(frame, scale=8)
            image_block = {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": b64,
                },
            }

        # 상태 텍스트
        player = ext["player"]
        tool = ext["tool"]
        slots = ext["slots"]

        slot_lines = []
        for s in slots:
            match = ">>> MATCH <<<" if s.get("matches_current") else "mismatch"
            slot_lines.append(
                f"  Slot {s['index']} at ({s['x']},{s['y']}): "
                f"needs shape={s['required_shape']}, color={s['required_color']}({_cn(s['required_color'])}), "
                f"rotation={s['required_rotation']}° [{match}]"
            )
        slot_text = "\n".join(slot_lines) if slot_lines else "  All cleared!"

        # 히스토리
        recent = history[-5:] if history else []
        hist_lines = []
        for h in recent:
            moved = h.get("moved", True)
            new = h.get("new_pos", [])
            result = f"→ ({new[0]},{new[1]})" if moved and new else "→ BLOCKED"
            event = h.get("event", "")
            hist_lines.append(f"  {h['step']}: {h['action']} {result} {event}")
        hist_text = "\n".join(hist_lines) if hist_lines else "  (first move)"

        text = f"""Position: ({player['x']},{player['y']})
Tool: shape={tool['shape']}, color={tool['color']}({tool['color_name']}), rotation={tool['rotation']}°
Lives: {ext['lives']}/3 | Energy: {ext['energy']}/{ext['max_energy']} | Slots left: {ext['slots_remaining']} | Level: {ext['level']}

Slot requirements:
{slot_text}

Recent moves:
{hist_text}

Look at the image. Choose your next move."""

        if image_block:
            return [image_block, {"type": "text", "text": text}]
        return text


def _cn(v: int) -> str:
    return {12: "red", 9: "orange", 14: "cyan", 8: "blue"}.get(v, str(v))


LS20_VLM_SYSTEM = """You are playing "ls20", a maze puzzle game on a 64x64 pixel grid.

RULES:
- Move: ACTION1=up(y-5), ACTION2=down(y+5), ACTION3=left(x-5), ACTION4=right(x+5)
- Gray blocks are walls. You cannot move through them.
- You carry a tool with shape/color/rotation properties
- Special pads on the map change your tool (shape/color/rotation cyclers)
- Match your tool to a slot's requirement, then stand on it to clear it
- Clear all slots to win. You have 3 lives and limited energy.

COLOR REFERENCE for the game image:
- Gray = walls/borders
- Small colored shapes = your player and tool indicators
- Bordered areas with colored shapes inside = target slots

RESPONSE FORMAT - respond with ONLY this JSON:
{"thinking": "brief reasoning about current state and next move", "action": N}

where N is 1 (up), 2 (down), 3 (left), or 4 (right).

IMPORTANT:
- If your last move was BLOCKED, you MUST try a different direction.
- Plan ahead: think about which pads you need to visit to change your tool before going to the slot."""
