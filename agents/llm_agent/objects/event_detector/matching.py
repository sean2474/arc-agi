"""Blob matching utilities — match prev blobs to curr blobs by color + proximity."""

from __future__ import annotations

import numpy as np

from ..object import Blob


def _manhattan(p1: tuple, p2: tuple) -> int:
    return abs(p1[0] - p2[0]) + abs(p1[1] - p2[1])


def bbox_overlaps(b1: dict, b2: dict) -> bool:
    """True if two bboxes share at least one cell (strict overlap)."""
    return (
        b1["row_min"] <= b2["row_max"] and b2["row_min"] <= b1["row_max"]
        and b1["col_min"] <= b2["col_max"] and b2["col_min"] <= b1["col_max"]
    )


def crop(arr: np.ndarray, bbox: dict) -> np.ndarray:
    return arr[bbox["row_min"]:bbox["row_max"] + 1,
               bbox["col_min"]:bbox["col_max"] + 1]


def match_blobs(
    prev_blobs: dict[str, Blob],
    curr_blobs: dict[str, Blob],
    max_dist: int = 8,
) -> tuple[list[tuple[str, str]], list[str], list[str]]:
    """
    Match prev blobs to curr blobs by color + proximity.
    Camera correction should already be applied to prev_blobs' bboxes before calling.

    Returns:
        pairs:          [(prev_id, curr_id), ...]
        unmatched_prev: [prev_id, ...]  — disappeared
        unmatched_curr: [curr_id, ...]  — appeared
    """
    # Pass 1: distance-sorted Hungarian greedy (color-matched).
    # Sorting by distance ensures the closest pair gets priority, so when
    # identical twins exist, the stationary twin (dist=0) is matched first and
    # the farther one is left unmatched → disappear, not false move.
    candidates: list[tuple[int, str, str]] = []
    for pid, pb in prev_blobs.items():
        if not pb.is_present:
            continue
        pc = pb.center()
        for cid, cb in curr_blobs.items():
            if set(cb.colors) != set(pb.colors):
                continue
            dist = _manhattan(pc, cb.center())
            if dist <= max_dist:
                candidates.append((dist, pid, cid))
    candidates.sort()

    matched_prev: set[str] = set()
    matched_curr: set[str] = set()
    pairs: list[tuple[str, str]] = []
    for dist, pid, cid in candidates:
        if pid in matched_prev or cid in matched_curr:
            continue
        pairs.append((pid, cid))
        matched_prev.add(pid)
        matched_curr.add(cid)

    unmatched_prev = [
        pid for pid, pb in prev_blobs.items()
        if pb.is_present and pid not in matched_prev
    ]
    unmatched_curr_set = set(curr_blobs.keys()) - matched_curr

    # Pass 2: color-agnostic fallback for in-place transforms.
    # Only attempt if the blob's color group did NOT shrink (shrinkage → disappeared,
    # not transformed).  Also restrict to very short distances so we don't
    # accidentally merge a disappeared blob with a newly appeared one.
    prev_sig_count_p2: dict[frozenset, int] = {}
    for _pb2 in prev_blobs.values():
        if _pb2.is_present:
            _s2 = frozenset(_pb2.colors)
            prev_sig_count_p2[_s2] = prev_sig_count_p2.get(_s2, 0) + 1
    curr_sig_count_p2: dict[frozenset, int] = {}
    for _cb2 in curr_blobs.values():
        _s2 = frozenset(_cb2.colors)
        curr_sig_count_p2[_s2] = curr_sig_count_p2.get(_s2, 0) + 1

    max_transform_dist = max(2, max_dist // 4)  # in-place transforms only
    still_unmatched_prev: list[str] = []
    for pid in unmatched_prev:
        pb = prev_blobs[pid]
        sig = frozenset(pb.colors)
        # If the group shrank, this blob simply disappeared — don't absorb into a transform.
        if prev_sig_count_p2.get(sig, 0) > curr_sig_count_p2.get(sig, 0):
            still_unmatched_prev.append(pid)
            continue
        pc = pb.center()
        best_dist = max_transform_dist + 1
        best_cid = None
        for cid in list(unmatched_curr_set):
            cb = curr_blobs[cid]
            if pb.cell_count > 0 and abs(cb.cell_count - pb.cell_count) / pb.cell_count > 0.30:
                continue
            dist = _manhattan(pc, cb.center())
            if dist < best_dist:
                best_dist = dist
                best_cid = cid
        if best_cid is not None:
            pairs.append((pid, best_cid))
            unmatched_curr_set.discard(best_cid)
        else:
            still_unmatched_prev.append(pid)

    return pairs, still_unmatched_prev, list(unmatched_curr_set)
