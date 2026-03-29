"""SCAN — Phase 1 전용. 첫 프레임 전체 분석."""

import json
from ..const import ACTION_NUM_TO_NAME, ARC_COLOR_NAMES


def _actions_as_names(available_actions: list[dict]) -> str:
    return ", ".join(ACTION_NUM_TO_NAME.get(a["value"], "?") for a in available_actions)


def _format_blobs_for_scan(blobs: dict) -> str:
    """BlobManager blobs → SCAN 프롬프트용 텍스트."""
    if not blobs:
        return "  (none detected)"
    lines = []
    for oid, b in blobs.items():
        if not b.is_present:
            continue
          
        colors = ",".join(ARC_COLOR_NAMES[c] for c in b.colors)
        lines.append(f"  {oid}: colors=[{colors}] cells={b.cell_count}")
    return "\n".join(lines) if lines else "  (none)"


def build_scan_message(
    available_actions: list[dict],
    levels_completed: int,
    win_levels: int,
    step: int,
    grid: list[str],
    blobs: dict | None = None,
) -> str:
    rows = len(grid)
    cols = len(grid[0]) if grid else 0

    blob_section = ""
    respond_section = ""
    if blobs:
        blob_section = f"""
OBJECTS (exact positions — do NOT re-estimate):
{_format_blobs_for_scan(blobs)}

Each object is outlined and labeled with its ID in the image.
Assign a game-role name and type for each ID.
"""
        respond_section = f"""\
Respond in JSON:
{{
  "object_roles": {{
    "obj_001": {{"name": "role-based name", "type_hypothesis": "", "shape": ""}},
    "obj_002": {{"name": "...", "type_hypothesis": "...", "shape": "..."}}
  }},
  "patterns": []
}}

Rules for "object_roles":
- Assign EVERY obj_id listed above.
- "name": game-role only (e.g. "player", "exit", "wall"). NOT color/shape.
  Unknown role → "unknown_1", "unknown_2", etc.
- Do NOT re-estimate positions. Positions are already exact.
- Objects at screen edges would not always but maybe HUD (step_counter, score, hud).
- Do NOT suggest actions. Analyze ONLY."""
    else:
        respond_section = f"""\
Respond in JSON:
{{
  "objects": [
    {{
      "id": "",
      "name": "role-based name",
      "type_hypothesis": "",
      "shape": "..."
    }}
  ],
  "patterns": []
}}

Field rules:
- "name": game-role name only.
  If role is unknown, use "unknown"
- "shape": visual shape only.

Rules:
- Objects at the extreme corners or edges of the screen are almost certainly HUD elements (step counter, score, timer) — NOT interactive game objects."""

    return f"""\
GAME INFO
  available_actions: [{_actions_as_names(available_actions)}]
  levels_completed: {levels_completed} / {win_levels}
  step: {step}
  grid_size: {rows}x{cols}

{blob_section}
STEP 1 - OBJECTS: What do you see? What is the game role of each object?

STEP 2 - PATTERNS: What structures do you see?
  Rectangles, corridors, borders, isolated pixels, repeating patterns?

{respond_section}"""
