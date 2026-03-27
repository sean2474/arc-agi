import json
from ..const import ACTION_NUM_TO_NAME


def _actions_as_names(available_actions: list[dict]) -> str:
    return ", ".join(ACTION_NUM_TO_NAME.get(a["value"], "?") for a in available_actions)


def build_observe_message(
    game_id: str,
    available_actions: list[dict],
    levels_completed: int,
    win_levels: int,
    step: int,
    summary: dict,
    world_model: dict,
    grid: list[str],
    prev_grid: list[str] | None = None,
) -> str:
    prev_section = ""
    if prev_grid:
        prev_section = f"""
PREVIOUS FRAME (before last action)
{chr(10).join(prev_grid)}
"""

    phase = world_model.get("phase", "static_observation")

    return f"""\
GAME INFO
  game_id: {game_id}
  available_actions: [{_actions_as_names(available_actions)}]
  levels_completed: {levels_completed} / {win_levels}
  step: {step}
  phase: {phase}

WORLD MODEL
{json.dumps(world_model, indent=2, ensure_ascii=False)}

SUMMARY
{json.dumps(summary, indent=2, ensure_ascii=False)}
{prev_section}
CURRENT FRAME
{chr(10).join(grid)}

You are ONLY observing. Do NOT decide what to do. Just analyze.

Work through these steps:

STEP 1 - OBJECTS: List every distinguishable object/region on screen.
  For each: hex value, color name, position (row/col range), size, shape.
  An "object" = any visually distinct group of cells (block, line, border, isolated pixel).

STEP 2 - PATTERNS: What structures do you see?
  Rectangles, corridors, borders, isolated pixels, repeating patterns?

STEP 3 - DIFF: Compare PREVIOUS FRAME and CURRENT FRAME.
  What moved? What appeared? What disappeared?
  Which objects changed position? Which stayed static?
  Not all changes are meaningful — focus on changes that correlate with actions.
  If no previous frame, skip this step.

STEP 4 - CLASSIFY OBJECTS: Based on DIFF results:
  - Which objects moved? → type: "dynamic"
  - Which objects didn't move? → type: "static"
  - If no previous frame, all objects are type: "unknown"

STEP 5 - CHALLENGE: What evidence CONTRADICTS your observations?
  - Could something you classified as static actually be dynamic?
  - There may be no controllable element — it could be a board manipulation game.
  - What don't you know that could change everything?

Respond in JSON:
{{
  "objects": {{
    "lime_block": {{"value": "c", "position": "row 46-47, col 33-37", "type": "unknown"}},
    "green_border": {{"value": "3", "position": "row 10-60, scattered", "type": "static"}}
  }},
  "patterns": ["green(3) forms corridors", "gray(5) rectangular blocks"],
  "changes": "lime(c) moved up 2 rows, everything else static",
  "contradictions": ["haven't verified what moves", "could be board manipulation"],
  "unknowns": ["what triggers level complete", "which element is controllable"]
}}

Rules:
- Do NOT suggest actions. Do NOT plan. Observe ONLY.
- STEP 5 (CHALLENGE) is critical. Bad assumptions kill runs.
- Be specific about positions: use row/column ranges.
- List ALL distinguishable objects, even if you think they're just background."""
