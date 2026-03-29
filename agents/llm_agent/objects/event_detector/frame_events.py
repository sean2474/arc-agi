"""Per-frame event detection and one-shot result-frame rotation detection."""

from __future__ import annotations

import numpy as np

from ..object import Blob
from .matching import match_blobs, _bbox_overlaps
from .rotation import _detect_rotation_or_transform


_REAPPEAR_DIST = 8


def detect_frame_events(
    prev_blobs: dict[str, Blob],
    curr_blobs: dict[str, Blob],
    camera_shift: tuple,           # (dr, dc) or (dr, dc, angle_deg)
    frame_idx: int = 0,
    prev_collide_pairs: set | None = None,
    arr_a: np.ndarray | None = None,  # prev frame as numpy (for rotation)
    arr_b: np.ndarray | None = None,  # curr frame as numpy
    emit_appear: bool = True,         # suppress appear on intermediate frames
    emit_disappear: bool = True,      # suppress disappear on intermediate frames
) -> tuple[list[dict], set, dict[str, str]]:
    """
    Detect events between two consecutive (camera-corrected) frames.
    Returns (events, curr_collide_pairs, newly_covered_by).
    """
    if prev_collide_pairs is None:
        prev_collide_pairs = set()

    dr, dc = camera_shift[0], camera_shift[1]
    angle_deg = camera_shift[2] if len(camera_shift) > 2 else 0.0
    pairs, unmatched_prev, unmatched_curr = match_blobs(prev_blobs, curr_blobs)
    events: list[dict] = []

    # --- camera shift / rotation events ---
    if angle_deg != 0.0:
        events.append({"type": "camera_rotation", "angle_deg": angle_deg, "frame": frame_idx})
    elif dr != 0 or dc != 0:
        events.append({"type": "camera_shift", "delta": [dr, dc], "frame": frame_idx})

    # Build reverse lookup: curr_id → prev_id
    curr_to_prev = {cid: pid for pid, cid in pairs}

    # --- move events ---
    for pid, cid in pairs:
        pb, cb = prev_blobs[pid], curr_blobs[cid]
        pc, cc = pb.center(), cb.center()
        moved_dr = cc[0] - pc[0]
        moved_dc = cc[1] - pc[1]
        if abs(moved_dr) > 1 or abs(moved_dc) > 1:
            events.append({
                "type": "move",
                "obj": pb.name or pid,
                "delta": [moved_dr, moved_dc],
                "from": list(pc),
                "to": list(cc),
                "frame": frame_idx,
            })

    # --- rotation / transform events (requires raw grid arrays) ---
    H_a = arr_a.shape[0] if arr_a is not None else 0
    W_a = arr_a.shape[1] if arr_a is not None else 0
    if arr_a is not None and arr_b is not None:
        for pid, cid in pairs:
            pb, cb = prev_blobs[pid], curr_blobs[cid]
            # pb.bbox has been camera-corrected (shifted by -dr, -dc).
            # Undo the correction to get the actual pixel position in arr_a.
            raw_bbox_a = {
                "row_min": max(0, pb.bbox["row_min"] + dr),
                "row_max": min(H_a - 1, pb.bbox["row_max"] + dr),
                "col_min": max(0, pb.bbox["col_min"] + dc),
                "col_max": min(W_a - 1, pb.bbox["col_max"] + dc),
            }
            label = pb.name or pid
            covering = [
                other.bbox for oid, other in curr_blobs.items()
                if oid != cid and other.is_present and _bbox_overlaps(cb.bbox, other.bbox)
            ]
            result = _detect_rotation_or_transform(
                arr_a, arr_b, raw_bbox_a, cb.bbox, pb.cell_count, cb.cell_count,
                debug_label=label,
                covering_bboxes=covering or None,
                colors_a=set(pb.colors) if pb.colors else None,
                colors_b=set(cb.colors) if cb.colors else None,
            )
            if result is None:
                continue
            if result["kind"] == "rotation":
                events.append({
                    "type": "rotation",
                    "obj": pb.name or pid,
                    "angle_deg": result["angle_deg"],
                    "frame": frame_idx,
                })
            else:
                events.append({
                    "type": "transform",
                    "obj": pb.name or pid,
                    "color_diff": result["color_diff"],
                    "frame": frame_idx,
                })

    # Initialise collide tracking state
    curr_collide_pairs: set = set()
    seen: set = set()
    newly_covered_by: dict[str, str] = {}  # covered_pid → covering_pid

    # --- disappear events ---
    # Pre-compute color-sig counts so we can detect group shrinkage.
    # When a group shrinks (fewer curr blobs of that color than prev), the
    # missing blobs simply disappeared — they were NOT covered by a neighbor
    # of the same color, even if that neighbor's bbox happens to contain their
    # center.  The "covered" heuristic is suppressed for those blobs.
    prev_sig_count: dict[frozenset, int] = {}
    for _pid, _pb in prev_blobs.items():
        if _pb.is_present:
            _sig = frozenset(_pb.colors)
            prev_sig_count[_sig] = prev_sig_count.get(_sig, 0) + 1
    curr_sig_count: dict[frozenset, int] = {}
    for _cb in curr_blobs.values():
        _sig = frozenset(_cb.colors)
        curr_sig_count[_sig] = curr_sig_count.get(_sig, 0) + 1

    # Priority 1: collide_destroy if was in collide pair last frame
    # Priority 2: covered  if a curr blob's bbox overlaps the disappeared blob's
    #             last bbox AND the color group did NOT shrink (not a twin vanish)
    # Priority 3: unknown
    for pid in unmatched_prev:
        pb = prev_blobs[pid]
        sig = frozenset(pb.colors)
        group_shrank = prev_sig_count.get(sig, 0) > curr_sig_count.get(sig, 0)

        cause = "unknown"
        for pair in prev_collide_pairs:
            if pid in pair:
                cause = "collide_destroy"
                break
        if cause == "unknown" and not group_shrank:
            pr, pc = pb.center()
            for cid, cb in curr_blobs.items():
                if not (cb.bbox["row_min"] <= pr <= cb.bbox["row_max"]
                        and cb.bbox["col_min"] <= pc <= cb.bbox["col_max"]):
                    continue
                cause = "covered"
                prev_cover = curr_to_prev.get(cid)
                if prev_cover:
                    newly_covered_by[pid] = prev_cover
                    pair_key = frozenset([pid, prev_cover])
                    if pair_key not in prev_collide_pairs and pair_key not in seen:
                        seen.add(pair_key)
                        curr_collide_pairs.add(pair_key)
                        pb_cov = prev_blobs.get(prev_cover)
                        events.append({
                            "type": "collide",
                            "obj_a": (pb_cov.name if pb_cov and pb_cov.name else prev_cover),
                            "obj_b": (pb.name if pb.name else pid),
                            "frame": frame_idx,
                        })
                break
        if emit_disappear and cause != "covered":
            events.append({
                "type": "disappear",
                "obj": pb.name or pid,
                "last_pos": list(pb.center()),
                "cause": cause,
                "frame": frame_idx,
            })

    # --- appear events ---
    absent_prev = {pid: pb for pid, pb in prev_blobs.items() if not pb.is_present}
    for cid in unmatched_curr:
        cb = curr_blobs[cid]
        is_reappear = False
        for pb in absent_prev.values():
            if set(pb.colors) != set(cb.colors):
                continue
            ref = pb.last_seen_bbox or pb.bbox
            ref_center = (
                (ref["row_min"] + ref["row_max"]) // 2,
                (ref["col_min"] + ref["col_max"]) // 2,
            )
            if (abs(cb.center()[0] - ref_center[0])
                    + abs(cb.center()[1] - ref_center[1])) <= _REAPPEAR_DIST:
                is_reappear = True
                break
        if is_reappear:
            continue
        if not emit_appear:
            continue
        events.append({
            "type": "appear",
            "obj": cb.name or cid,
            "pos": list(cb.center()),
            "frame": frame_idx,
        })

    # --- collide detection: bbox overlap between currently present blobs ---
    matched_curr_ids = [cid for _, cid in pairs]
    for i, cid_a in enumerate(matched_curr_ids):
        for cid_b in matched_curr_ids[i + 1:]:
            cb_a, cb_b = curr_blobs[cid_a], curr_blobs[cid_b]
            if not _bbox_overlaps(cb_a.bbox, cb_b.bbox):
                continue
            prev_a = curr_to_prev.get(cid_a)
            prev_b = curr_to_prev.get(cid_b)
            if prev_a is None or prev_b is None:
                continue
            pair_key = frozenset([prev_a, prev_b])
            curr_collide_pairs.add(pair_key)
            if pair_key not in prev_collide_pairs and pair_key not in seen:
                seen.add(pair_key)
                pb_a = prev_blobs.get(prev_a)
                pb_b = prev_blobs.get(prev_b)
                events.append({
                    "type": "collide",
                    "obj_a": (pb_a.name if pb_a and pb_a.name else prev_a),
                    "obj_b": (pb_b.name if pb_b and pb_b.name else prev_b),
                    "frame": frame_idx,
                })

    return events, curr_collide_pairs, newly_covered_by


def detect_transform_rotation(
    prev_blobs: dict[str, Blob],
    curr_blobs: dict[str, Blob],
    arr_a: np.ndarray,
    arr_b: np.ndarray,
    frame_idx: int = 0,
) -> list[dict]:
    """
    One-shot rotation/transform detection comparing initial state (prev_grid)
    vs final animation state (anim_frames[-1]).
    Blobs are matched by ID — same ID means same object survived the animation.
    No camera correction needed: arr_a and arr_b are the raw original grids.
    """
    events = []
    for pid, pb in prev_blobs.items():
        if not pb.is_present:
            continue
        cb = curr_blobs.get(pid)
        if cb is None or not cb.is_present:
            continue
        covering = [
            other.bbox for oid, other in curr_blobs.items()
            if oid != pid and other.is_present and _bbox_overlaps(cb.bbox, other.bbox)
        ]
        result = _detect_rotation_or_transform(
            arr_a, arr_b, pb.bbox, cb.bbox, pb.cell_count, cb.cell_count,
            debug_label=pb.name or pid,
            covering_bboxes=covering or None,
            colors_a=set(pb.colors) if pb.colors else None,
            colors_b=set(cb.colors) if cb.colors else None,
        )
        if result is None:
            continue
        if result["kind"] == "rotation":
            events.append({
                "type": "rotation",
                "obj": pb.name or pid,
                "angle_deg": result["angle_deg"],
                "frame": frame_idx,
            })
        else:
            events.append({
                "type": "transform",
                "obj": pb.name or pid,
                "color_diff": result["color_diff"],
                "frame": frame_idx,
            })
    return events
