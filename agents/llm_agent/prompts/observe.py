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
PREVIOUS FRAME (before last sequence)
{chr(10).join(prev_grid)}
"""
    return f"""\
GAME INFO
  game_id: {game_id}
  available_actions: [{_actions_as_names(available_actions)}]
  levels_completed: {levels_completed} / {win_levels}
  step: {step}

WORLD MODEL
{json.dumps(world_model, indent=2, ensure_ascii=False)}

SUMMARY
{json.dumps(summary, indent=2, ensure_ascii=False)}
{prev_section}
CURRENT FRAME
{chr(10).join(grid)}

You are ONLY observing. Do NOT decide what to do. Just analyze.

Work through these steps:

STEP 1 - VALUES: List every unique hex value in the frame.
  For each: what color, roughly where, how much area?

STEP 2 - PATTERNS: What structures do you see?
  Rectangles, corridors, borders, isolated pixels, repeating patterns?

STEP 3 - DIFF: Compare PREVIOUS FRAME and CURRENT FRAME directly.
  What cells changed? What moved? What appeared/disappeared?
  Note: Not all changes are meaningful. Some may be decorative or environmental.
  Focus on changes that correlate with your actions.
  If no previous frame, skip this step.

STEP 4 - HYPOTHESIZE:
  - What type of game is this? (navigation, puzzle, pattern-matching, clicking, etc.)
  - Is there a player character? If so, which value and where? If not, what do you control?
  - What are static elements? (walls, floors, borders)
  - What might be the goal/win condition?

STEP 5 - CHALLENGE: What evidence CONTRADICTS your hypotheses?
  - Could this be a completely different type of game than you assumed?
  - There may be no "player" — it could be a click/selection game.
  - What assumptions are unproven?
  - What don't you know that could change everything?

STEP 6 - CONCLUDE: Summarize as facts only.

Respond in JSON:
{{
  "values": {{"0": "black, isolated pixels at row 32-33 col 20-21", "3": "green, corridors"}},
  "patterns": ["green(3) forms corridors", "gray(5) rectangular blocks"],
  "changes_from_summary": "lime(c) block moved up 2 rows",
  "game_type_hypothesis": {{"type": "navigation", "confidence": 0.5}},
  "controllable_element": {{"description": "lime(c) block at row 40-41", "type": "player_character", "confidence": 0.7}},
  "goal_hypothesis": {{"description": "navigate to teal(b) region at row 61", "confidence": 0.3}},
  "contradictions": ["could be a click/selection game, not navigation", "haven't verified what actually moves"],
  "unknowns": ["what triggers level complete", "is there a player or do I manipulate the board?"]
}}

Rules:
- Do NOT suggest actions. Do NOT plan. Observe ONLY.
- STEP 5 (CHALLENGE) is critical. Bad assumptions kill runs.
- Be specific about positions: use row/column ranges."""
