"""SCAN — Phase 1 전용. 첫 프레임 전체 분석."""

import json
from ...const import ACTION_NUM_TO_NAME


def _actions_as_names(available_actions: list[dict]) -> str:
    return ", ".join(ACTION_NUM_TO_NAME.get(a["value"], "?") for a in available_actions)


def build_scan_message(
    game_id: str,
    available_actions: list[dict],
    levels_completed: int,
    win_levels: int,
    step: int,
    grid: list[str],
) -> str:
    return f"""\
GAME INFO
  game_id: {game_id}
  available_actions: [{_actions_as_names(available_actions)}]
  levels_completed: {levels_completed} / {win_levels}
  step: {step}

CURRENT FRAME
{chr(10).join(grid)}

This is the first frame. Analyze everything on screen.

STEP 1 - OBJECTS: List every distinguishable object/region.
  For each: hex value, color name, position (row/col range), size, shape.
  An "object" = any visually distinct group of cells.

STEP 2 - PATTERNS: What structures do you see?
  Rectangles, corridors, borders, isolated pixels, repeating patterns?

Respond in JSON:
{{
  "objects": {{
    "name": {{"value": "...", "position": "...", "size": "..."}}
  }},
  "patterns": []
}}

Rules:
- Do NOT suggest actions. Do NOT plan. Analyze ONLY.
- Be specific about positions: use row/column ranges.
- List ALL distinguishable objects, even if you think they're background."""
