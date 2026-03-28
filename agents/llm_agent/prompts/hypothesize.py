"""HYPOTHESIZE — Phase 1, SCAN 직후. 초기 가설 수립."""

import json


def build_hypothesize_message(
    scan_result: dict,
    available_actions: list[dict],
) -> str:
    from ..const import ACTION_NUM_TO_NAME
    actions_names = ", ".join(ACTION_NUM_TO_NAME.get(a["value"], "?") for a in available_actions)

    return f"""\
SCAN RESULT (objects found on screen)
{json.dumps(scan_result, indent=2, ensure_ascii=False)}

AVAILABLE ACTIONS: [{actions_names}]

Based on the scan results, form initial hypotheses about this game.

For each object, guess its role:
- Could it be background, wall, path, controllable, goal, danger, decoration?
- What makes you think so? (shape, position, color, size)

For the game overall:
- What type of game could this be?
- What might the win condition be?
- Which action should be tested first and why?

Respond in JSON:
{{
  "object_hypotheses": {{
    "obj_id": {{"type_hypothesis": "...", "reasoning": "..."}}
  }},
  "game_type": {{"hypothesis": "...", "confidence": 0.3, "reasoning": "..."}},
  "goal_hypotheses": [
    {{"description": "...", "confidence": 0.3, "supporting_evidence": [], "contradicting_evidence": []}}
  ],
  "relationship_hypotheses": [
    {{"subject_type": "name (shape, color)", "relation": "...", "object_type": "name (shape, color)", "context": "...", "interaction_result": null, "confidence": 0.3}}
  ],
  "test_priority": ["action1", "action2"],
  "reasoning": "..."
}}

Rules:
- All hypotheses start at confidence 0.3 — nothing is confirmed yet.
- Do NOT assume any specific game type. Consider all possibilities.
- goal_hypotheses: list ALL plausible win conditions you can think of.
- relationship_hypotheses: objects that look dangerous, activatable, or linked. Use "name (shape, color)" format.
- test_priority: which actions to test first, ordered by expected information gain."""
