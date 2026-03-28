"""SCAN — Phase 1 전용. 첫 프레임 전체 분석."""

import json
from ..const import ACTION_NUM_TO_NAME, COLOR_PROMPT_LINE


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

ARC COLOR INDEX (use these IDs in "colors"):
  {COLOR_PROMPT_LINE}

STEP 1 - OBJECTS: List every distinguishable object/region.
  An "object" = any visually distinct group of cells.

STEP 2 - PATTERNS: What structures do you see?
  Rectangles, corridors, borders, isolated pixels, repeating patterns?

Respond in JSON:
{{
  "objects": [
    {{
      "name": "role-based name",
      "shape": "square|rectangle|L-shape|...",
      "colors": ["e"],
      "position": "row,col",
      "size": "HxW"
    }}
  ],
  "patterns": []
}}

Field rules:
- "name": game-role name only.
  Do NOT use color or shape as name (e.g. "green_block" or "small_square" are WRONG).
  If role is unknown, use "unknown_1", "unknown_2", etc.
- "shape": visual shape only.
- "colors": list of ARC color index chars (e.g. ["e"] for green, ["9"] for blue). NOT hex RGB.
  Use the labeled coordinate grid to count exact cell positions.
- "position": "row,col" top-left corner, 0-indexed. MUST be within grid bounds (0~{rows-1}, 0~{cols-1}).
- "size": "HxW" in cells. position+size MUST NOT exceed grid bounds ({rows}x{cols}).

Rules:
- Do NOT suggest actions. Do NOT plan. Analyze ONLY.
- List ALL distinguishable objects, even background.
- CRITICAL: If multiple regions share the same game role (same color + function), merge them into ONE entry with the bounding box covering all of them. Do NOT list each piece separately.
- List at most 20 objects total. Merge aggressively.
- Objects at the extreme corners or edges of the screen are almost certainly HUD elements (step counter, score, timer) — NOT interactive game objects. Name them "step_counter", "score", or "hud" and mark type_hypothesis as "hud". Do NOT include them as targets for game actions."""
