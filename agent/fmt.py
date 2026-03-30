"""LLM 프롬프트용 텍스트 포맷 헬퍼."""

from agent.const import ARC_COLOR_NAMES
from agent.objects.event_detector.merge import merge_remap


def fmt_colors(colors: list) -> str:
    """['9','a'] → 'blue,light-blue'"""
    return ",".join(ARC_COLOR_NAMES.get(c, c) for c in colors) if colors else ""


def fmt_objects_prompt(objects, excluded_ids: set | None = None) -> str:
    """world model objects (list or dict) → prompt 텍스트."""
    if not objects:
        return "  (none)"
    if isinstance(objects, dict):
        items = list(objects.items())
    else:
        items = [(o.get("instance_id", "?"), o) for o in objects if isinstance(o, dict)]
    if excluded_ids:
        items = [(oid, obj) for oid, obj in items if oid not in excluded_ids]
    lines = []
    for oid, obj in items:
        if not isinstance(obj, dict):
            continue
        name = obj.get("name", oid)
        conf = obj.get("confidence")
        name_str = f"{name}/confidence {conf:.1f}" if isinstance(conf, (int, float)) else name
        parts = [f"{oid}({name_str})"]
        if obj.get("type_hypothesis"):
            parts.append(f"type={obj['type_hypothesis']}")
        if obj.get("position"):
            parts.append(f"pos={obj['position']}")
        if obj.get("colors"):
            parts.append(f"colors=[{fmt_colors(obj['colors'])}]")
        if obj.get("shape"):
            parts.append(f"shape={obj['shape']}")
        if obj.get("size"):
            parts.append(f"size={obj['size']}")
        lines.append("  " + "  ".join(parts))
    return "\n".join(lines) if lines else "  (none)"


def fmt_world_model_prompt(wm: dict) -> str:
    """world model dict → prompt 텍스트."""
    lines = []
    gt = wm.get("game_type", {})
    if isinstance(gt, dict) and gt.get("hypothesis"):
        lines.append(f"game_type: {gt['hypothesis']} (conf: {gt.get('confidence', 0):.1f})")
    if wm.get("phase"):
        lines.append(f"phase: {wm['phase']}")
    objects = wm.get("objects", [])
    if objects:
        lines.append("objects:")
        lines.append(fmt_objects_prompt(objects))
    goals = [g for g in wm.get("goal_hypotheses", []) if isinstance(g, dict) and g.get("confidence", 0) >= 0.3]
    if goals:
        lines.append("goal_hypotheses:")
        for g in goals:
            lines.append(f"  - {g.get('description', '?')} (conf: {g.get('confidence', 0):.1f})")
    active_plans = [p for p in wm.get("plans", []) if isinstance(p, dict) and p.get("status") not in ("done", "failed")]
    if active_plans:
        lines.append("plans:")
        for p in active_plans[:3]:
            lines.append(f"  - [{p.get('status', 'pending')}] {p.get('description', '?')}")
    rels = [r for r in wm.get("relationships", []) if isinstance(r, dict) and r.get("confidence", 0) >= 0.3]
    if rels:
        lines.append("relationships:")
        for r in rels[:5]:
            lines.append(f"  - {r.get('subject', '?')} {r.get('relation', '?')} {r.get('object', '?')} (conf: {r.get('confidence', 0):.1f})")
    return "\n".join(lines) if lines else "(none)"


def fmt_history(history) -> str:
    """StepRecord 리스트 → action→observation 히스토리 텍스트."""
    lines = []
    for r in history:
        obs = (r.observation or "").strip()
        obs_short = obs[:80] + "\u2026" if len(obs) > 80 else obs
        lines.append(f"  {r.step}. {r.action} \u2192 {obs_short or '(no change)'}")
    return "\n".join(lines) if lines else "  (none)"


def format_events_for_prompt(animation_events: list[dict], result_events: list[dict]) -> str:
    """BlobManager events → LLM 프롬프트용 텍스트. merge 이벤트는 숨김."""
    animation_events = merge_remap(animation_events or [])
    result_events = merge_remap(result_events or [])
    lines = []

    def _label(ev: dict, key: str = "obj", name_key: str = "name") -> str:
        oid = ev.get(key, "?")
        name = ev.get(name_key, "")
        return f"{oid}({name})" if name and name != oid else oid

    def _delta_text(dr: int, dc: int) -> str:
        parts = []
        if dr < 0:
            parts.append(f"{abs(dr)} pixel{'s' if abs(dr) != 1 else ''} up")
        elif dr > 0:
            parts.append(f"{dr} pixel{'s' if dr != 1 else ''} down")
        if dc < 0:
            parts.append(f"{abs(dc)} pixel{'s' if abs(dc) != 1 else ''} left")
        elif dc > 0:
            parts.append(f"{dc} pixel{'s' if dc != 1 else ''} right")
        return ", ".join(parts) if parts else "0 pixels (no net movement)"

    def _rot_text(deg) -> str:
        d = int(deg)
        if d > 0:
            return f"rotated {d}° clockwise"
        elif d < 0:
            return f"rotated {abs(d)}° counter-clockwise"
        return "rotated 0°"

    def _fmt(ev: dict) -> str | None:
        t = ev.get("type", "")
        if t == "move":
            dr, dc = ev.get("delta", [0, 0])
            return f"  {_label(ev)} moved {_delta_text(dr, dc)}"
        if t == "collide":
            a = _label(ev, "obj_a", "name_a")
            b = _label(ev, "obj_b", "name_b")
            return f"  {a} and {b} collided"
        if t == "disappear":
            cause = ev.get("cause", "unknown")
            return f"  {_label(ev)} disappeared (cause: {cause})"
        if t == "appear":
            pos = ev.get("pos", ev.get("last_pos", ["?", "?"]))
            return f"  {_label(ev)} appeared at row {pos[0]}, col {pos[1]}"
        if t == "rotation":
            return f"  {_label(ev)} {_rot_text(ev.get('angle_deg', 0))}"
        if t == "transform":
            return f"  {_label(ev)} changed appearance (color diff={ev.get('color_diff', 0):.2f})"
        if t == "camera_shift":
            dr, dc = ev.get("delta", [0, 0])
            return f"  camera moved {_delta_text(dr, dc)}"
        if t == "camera_rotation":
            return f"  camera {_rot_text(ev.get('angle_deg', 0))}"
        if t == "game_over":
            return f"  game over"
        return None

    if animation_events:
        lines.append("animation:")
        for ev in animation_events:
            s = _fmt(ev)
            if s:
                lines.append(s)
    else:
        lines.append("animation: (none)")

    if result_events:
        lines.append("result:")
        for ev in result_events:
            s = _fmt(ev)
            if s:
                lines.append(s)
    else:
        lines.append("result: (none)")

    return "\n".join(lines)


def fmt_scan_result(scan_result: dict) -> str:
    """SCAN 결과 dict → HYPOTHESIZE 프롬프트용 텍스트."""
    lines = []
    roles = scan_result.get("object_roles") or {}
    objects = scan_result.get("objects") or []

    if roles:
        lines.append("objects:")
        for oid, info in roles.items():
            if not isinstance(info, dict):
                continue
            parts = [f"{oid}({info.get('name', oid)})"]
            if info.get("type_hypothesis"):
                parts.append(f"type={info['type_hypothesis']}")
            if info.get("shape"):
                parts.append(f"shape={info['shape']}")
            lines.append("  " + "  ".join(parts))
    elif objects:
        lines.append("objects:")
        for obj in objects:
            if not isinstance(obj, dict):
                continue
            oid = obj.get("id", "?")
            parts = [f"{oid}({obj.get('name', oid)})"]
            if obj.get("type_hypothesis"):
                parts.append(f"type={obj['type_hypothesis']}")
            if obj.get("shape"):
                parts.append(f"shape={obj['shape']}")
            lines.append("  " + "  ".join(parts))

    patterns = scan_result.get("patterns", [])
    if patterns:
        lines.append("patterns:")
        for p in patterns:
            lines.append(f"  - {p}")

    return "\n".join(lines) if lines else "(none)"


def fmt_actions(actions: dict) -> str:
    """world model actions dict → prompt 텍스트."""
    if not actions:
        return "  (none)"
    lines = []
    for name, data in actions.items():
        if not isinstance(data, dict):
            continue
        effect = data.get("effect", "")
        conf = data.get("confidence", 0.0)
        if effect:
            lines.append(f"  {name}: {effect} (conf: {conf:.1f})")
        else:
            lines.append(f"  {name}: (not tested)")
    return "\n".join(lines) if lines else "  (none)"


def fmt_relationships(rels: list) -> str:
    """world model relationships list → prompt 텍스트."""
    filtered = [r for r in rels if isinstance(r, dict) and r.get("confidence", 0) >= 0.3]
    if not filtered:
        return "  (none)"
    lines = []
    for r in filtered:
        result = r.get("interaction_result", "")
        result_str = f" -> {result}" if result else ""
        lines.append(f"  - {r.get('subject','?')} {r.get('relation','?')} {r.get('object','?')}{result_str} (conf: {r.get('confidence',0):.1f})")
    return "\n".join(lines)


def fmt_transition_objects(blobs: dict, level_transition_info: dict) -> str:
    """레벨 전환 시 known/new 오브젝트 목록 포맷."""
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
