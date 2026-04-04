"""Planner-Actor-Observer 프롬프트.

Planner: goal + subgoals 생성 (드물게 호출)
Actor: subgoal + 이미지 → 단일 액션 (매 스텝 호출)
"""

PLANNER_SYSTEM = """You are the PLANNER for an ARC-AGI-3 maze puzzle game "ls20".

GAME RULES:
- 64x64 pixel grid, you move 5 pixels per step
- Actions: 1=up(y-5), 2=down(y+5), 3=left(x-5), 4=right(x+5)
- You carry a tool with shape/color/rotation properties
- Special pads change your tool: shape_pad cycles shape, color_pad cycles color, rotation_pad rotates +90°
- Match tool to slot requirement + stand on slot = clear it
- Clear all slots to win. 3 lives, limited energy per life.

YOUR JOB: Analyze the game state and create a plan with subgoals.

RESPONSE FORMAT (JSON only):
{
  "analysis": "brief analysis of current situation",
  "goal": "the overall objective",
  "subgoals": [
    {"id": 1, "description": "what to do", "target": [x, y], "done_when": "condition to check"},
    {"id": 2, "description": "...", "target": [x, y], "done_when": "..."}
  ]
}

IMPORTANT:
- Each subgoal should be a concrete, achievable step (e.g., "move to rotation pad at (19,30)")
- Include target coordinates when possible
- done_when should be checkable (e.g., "position is (19,30)", "rotation changed to 0")
- Order subgoals logically: modify tool FIRST, then go to slot"""


ACTOR_SYSTEM = """You are the ACTOR for a maze puzzle game. You execute one move at a time toward a subgoal.

Actions: 1=up(y-5), 2=down(y+5), 3=left(x-5), 4=right(x+5)
Gray/black areas are walls. You cannot move through them.

RESPONSE FORMAT (JSON only):
{"thinking": "brief reason", "action": N}

RULES:
- Move toward the target position of your current subgoal
- If BLOCKED, try a different direction to navigate around the wall
- Look at the image to see which directions are open (non-gray/black)"""


def build_planner_message(extracted: dict, observation_history: list[str]) -> str:
    """Planner용 유저 메시지를 생성한다."""
    player = extracted["player"]
    tool = extracted["tool"]
    slots = extracted["slots"]

    slot_lines = []
    for s in slots:
        match = "MATCH" if s.get("matches_current") else "mismatch"
        slot_lines.append(
            f"  Slot {s['index']} at ({s['x']},{s['y']}): "
            f"needs shape={s['required_shape']}, color={s['required_color']}, "
            f"rotation={s['required_rotation']}° [{match}]"
        )
    slot_text = "\n".join(slot_lines) if slot_lines else "  All cleared!"

    recent_obs = "\n".join(f"  {o}" for o in observation_history[-10:]) if observation_history else "  (none)"

    return f"""Current state:
- Position: ({player['x']}, {player['y']})
- Tool: shape={tool['shape']}, color={tool['color']}({tool['color_name']}), rotation={tool['rotation']}°
- Lives: {extracted['lives']}/3, Energy: {extracted['energy']}/{extracted['max_energy']}
- Slots remaining: {extracted['slots_remaining']}

Slot requirements:
{slot_text}

Recent observations:
{recent_obs}

Create a plan with subgoals to clear the remaining slots."""


def _safe_target(subgoal: dict, idx: int) -> str:
    """subgoal의 target 좌표를 안전하게 추출한다."""
    t = subgoal.get("target")
    if t and isinstance(t, (list, tuple)) and len(t) > idx:
        return str(t[idx])
    return "?"


def build_actor_message(
    extracted: dict,
    current_subgoal: dict,
    last_observations: list[str],
    frame_b64: str | None = None,
) -> str | list:
    """Actor용 유저 메시지를 생성한다."""
    player = extracted["player"]
    tool = extracted["tool"]

    obs_text = "\n".join(f"  {o}" for o in last_observations[-3:]) if last_observations else "  (first move)"

    text = f"""Position: ({player['x']},{player['y']})
Tool: shape={tool['shape']}, color={tool['color']}({tool['color_name']}), rotation={tool['rotation']}°
Energy: {extracted['energy']}/{extracted['max_energy']}

Current subgoal: {current_subgoal.get('description', '?')}
Target: ({_safe_target(current_subgoal, 0)}, {_safe_target(current_subgoal, 1)})

Recent observations:
{obs_text}

Choose your next move toward the target."""

    if frame_b64:  # noqa: E501
        return [
            {
                "type": "image",
                "source": {"type": "base64", "media_type": "image/png", "data": frame_b64},
            },
            {"type": "text", "text": text},
        ]
    return text
