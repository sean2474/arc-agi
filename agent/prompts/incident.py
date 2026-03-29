def build_incident_gameover_message() -> str:
    return """\
GAME OVER — ANALYZE WHAT HAPPENED

Two images are provided: BEFORE and AT GAME_OVER.

Steps:
1. What changed between the two frames?
2. Which object/position was involved?
3. Were there any warning signs before this happened?
4. What rule can be inferred to avoid this?

Respond in JSON:
{
  "cause": "...",
  "warning_signs": [],
  "avoidance_rule": "..."
}"""


def _format_transition_objects(blobs: dict, level_transition_info: dict) -> str:
    """archive 기반 known/new 오브젝트 목록 생성."""
    if not blobs:
        return ""

    cross_matches = level_transition_info.get("objects", [])
    inherited_ids = {m["obj"] for m in cross_matches}

    known_lines = []
    for m in cross_matches:
        oid = m["obj"]
        b = blobs.get(oid)
        name = (b.name or oid) if b else oid
        match_pct = int(m.get("color_match_ratio", 0) * 100)
        prev_type = m.get("prev_type_hypothesis", "?")
        present = "✓" if (b and b.is_present) else "✗ (absent)"
        known_lines.append(f"  {oid}({name}): {prev_type} match={match_pct}% {present}")

    new_lines = []
    for oid, b in blobs.items():
        if oid not in inherited_ids and b.is_present:
            name = b.name or oid
            colors = ",".join(b.colors) if b.colors else "?"
            new_lines.append(f"  {oid}({name}): colors=[{colors}]")

    sections = []
    if known_lines:
        sections.append("Known objects (carried from previous level):\n" + "\n".join(known_lines))
    if new_lines:
        sections.append("New objects (first seen this level):\n" + "\n".join(new_lines))
    return "\n\n".join(sections)


def build_incident_levelcomplete_message(
    prev_level: int,
    curr_level: int,
    level_transition_info: dict | None = None,
    blobs: dict | None = None,
) -> str:
    obj_section = ""
    if level_transition_info and blobs:
        obj_block = _format_transition_objects(blobs, level_transition_info)
        if obj_block:
            obj_section = f"\n{obj_block}\n"

    return f"""\
LEVEL COMPLETED ({prev_level} -> {curr_level}) — ANALYZE WHAT HAPPENED

Two images are provided: BEFORE (with object labels) and AT LEVEL_COMPLETE (with object labels).
{obj_section}
Steps:
1. What changed between the two frames?
2. What was the final action/condition that triggered completion?
3. Which object was involved in the win condition?
4. Do the "Known objects" still have the same role in the new level?
   If any known object should be renamed or reclassified, list it in renamed_objects.

Respond in JSON:
{{
  "trigger": "...",
  "win_condition": "...",
  "generalizes": true,
  "reasoning": "...",
  "renamed_objects": {{}}
}}

renamed_objects format: {{"obj_001": {{"new_name": "exit", "type_hypothesis": "goal", "reason": "..."}}}}"""
