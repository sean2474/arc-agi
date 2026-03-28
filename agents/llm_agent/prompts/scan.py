"""SCAN — Phase 1 전용. 첫 프레임 전체 분석."""

import json
from ..const import ACTION_NUM_TO_NAME


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
    rows = len(grid)
    cols = len(grid[0]) if grid else 0
    return f"""\
GAME INFO
  game_id: {game_id}
  available_actions: [{_actions_as_names(available_actions)}]
  levels_completed: {levels_completed} / {win_levels}
  step: {step}
  grid_size: {rows}x{cols} (rows x cols, 0-indexed: row 0~{rows-1}, col 0~{cols-1})

STEP 1 - OBJECTS: List every distinguishable object/region.
  An "object" = any visually distinct group of cells.

STEP 2 - PATTERNS: What structures do you see?
  Rectangles, corridors, borders, isolated pixels, repeating patterns?

Respond in JSON:
{{
  "objects": {{
    "obj_NNN": {{
      "name": "role-based name",
      "shape": "square|rectangle|L-shape|...",
      "colors": ["hex1", "hex2"],
      "position": "row,col",
      "size": "HxW"
    }}
  }},
  "patterns": []
}}

Field rules:
- "obj_NNN": use sequential IDs starting from obj_001.
- "name": game-role name only.
  Do NOT use color or shape as name (e.g. "green_block" or "small_square" are WRONG).
  If role is unknown, use "unknown_N" (e.g. "unknown_1").
- "shape": visual shape only.
- "colors": list of hex color values that make up this object. Single-color objects have 1 element.
- "position": "row,col" top-left corner, 0-indexed. MUST be within grid bounds.
- "size": "HxW" in cells. position+size MUST NOT exceed grid bounds ({rows}x{cols}).

Rules:
- Do NOT suggest actions. Do NOT plan. Analyze ONLY.
- List ALL distinguishable objects, even background.
- Group objects of the same game role into ONE entry unless they are clearly separate game elements. Do NOT split one wall/terrain into many pieces — use the bounding box of the entire region."""
