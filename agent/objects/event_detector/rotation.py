"""Rotation and transform detection for matched blob pairs."""

from __future__ import annotations

import numpy as np

from ..camera import _rotate_np
from .matching import crop


def _pad_square(c: np.ndarray, S: int) -> np.ndarray:
    out = np.zeros((S, S), dtype=np.int16)
    out[:c.shape[0], :c.shape[1]] = c
    return out


def detect_rotation_or_transform(
    arr_a: np.ndarray,
    arr_b: np.ndarray,
    bbox_a: dict,
    bbox_b: dict,
    cell_count_a: int,
    cell_count_b: int,
    debug_label: str = "",
    covering_bboxes: list | None = None,
    colors_a: set | None = None,
    colors_b: set | None = None,
) -> dict | None:
    """
    Compare matched blob regions. Returns:
      {"kind": "rotation", "angle_deg": N}  — color dist same, shape rotated
      {"kind": "transform", "color_diff": F} — color distribution changed
      None — pixels identical or size mismatch too large
    """
    if cell_count_a == 0:
        return None
    # Ignore if size changed dramatically (merge/split, not rotation)
    if abs(cell_count_b - cell_count_a) / cell_count_a > 0.60:
        if debug_label:
            print(f"  [rot_dbg] {debug_label}: cell_count skip ({cell_count_a}→{cell_count_b})")
        return None

    crop_a = crop(arr_a, bbox_a).astype(np.int16)
    crop_b = crop(arr_b, bbox_b).astype(np.int16)

    # Fast path: if raw crops are identical (same shape, same pixels) there is
    # nothing to detect — rotation/transform SSE cannot go below 0.
    if crop_a.shape == crop_b.shape and np.array_equal(crop_a, crop_b):
        return None

    # Keep only pixels belonging to the blob's own colors; zero out background and
    # neighboring blob pixels.  This prevents false rotation/transform when the blob
    # merely moves to a region with a different background pattern.
    if colors_a:
        mask_a = np.zeros(crop_a.shape, dtype=bool)
        for c in colors_a:
            mask_a |= (crop_a == int(c, 16))
        crop_a[~mask_a] = 0
    if colors_b:
        mask_b = np.zeros(crop_b.shape, dtype=bool)
        for c in colors_b:
            mask_b |= (crop_b == int(c, 16))
        crop_b[~mask_b] = 0

    # Zero out covered regions in BOTH crops so the diff naturally ignores them.
    # covering_bboxes are in arr_b coordinate system; apply to crop_b, and map same
    # absolute region onto crop_a (valid when the blob is stationary or nearly so).
    if covering_bboxes:
        H_a_c, W_a_c = crop_a.shape
        H_b_c, W_b_c = crop_b.shape
        for cb_bbox in covering_bboxes:
            r0b = max(bbox_b["row_min"], cb_bbox["row_min"]) - bbox_b["row_min"]
            r1b = min(bbox_b["row_max"], cb_bbox["row_max"]) - bbox_b["row_min"] + 1
            c0b = max(bbox_b["col_min"], cb_bbox["col_min"]) - bbox_b["col_min"]
            c1b = min(bbox_b["col_max"], cb_bbox["col_max"]) - bbox_b["col_min"] + 1
            if r1b <= r0b or c1b <= c0b:
                continue
            crop_b[max(0, r0b):min(H_b_c, r1b), max(0, c0b):min(W_b_c, c1b)] = 0
            r0a = max(bbox_a["row_min"], cb_bbox["row_min"]) - bbox_a["row_min"]
            r1a = min(bbox_a["row_max"], cb_bbox["row_max"]) - bbox_a["row_min"] + 1
            c0a = max(bbox_a["col_min"], cb_bbox["col_min"]) - bbox_a["col_min"]
            c1a = min(bbox_a["col_max"], cb_bbox["col_max"]) - bbox_a["col_min"] + 1
            if r1a > r0a and c1a > c0a:
                crop_a[max(0, r0a):min(H_a_c, r1a), max(0, c0a):min(W_a_c, c1a)] = 0

    # If bbox dimensions differ (screen-edge clipping), rotation detection is
    # unreliable: the padding asymmetry creates a non-zero baseline SSE that the
    # fine-grained sweep can spuriously "improve" at some angles.
    if crop_a.shape != crop_b.shape:
        return None

    # Pad both to same square size so rotation search stays in frame
    S = max(crop_a.shape[0], crop_a.shape[1], crop_b.shape[0], crop_b.shape[1])
    pa = _pad_square(crop_a, S)
    pb_pad = _pad_square(crop_b, S)

    sse_zero = float(np.mean((pa - pb_pad) ** 2))
    if debug_label:
        print(f"  [rot_dbg] {debug_label}: bbox_a={bbox_a} bbox_b={bbox_b} "
              f"crop_a={crop_a.shape} crop_b={crop_b.shape} sse_zero={sse_zero:.3f}")
    if sse_zero == 0:
        return None  # identical after masking

    ROT_THRESHOLD = 0.88      # SSE must improve by >12%
    pa_u8 = pa.astype(np.uint8)

    # --- Pass 1: 90-degree multiples first ---
    # A 90° rotation changes bbox dimensions, causing false color_diff; check it before histogram.
    best_sse = sse_zero
    best_angle = 0
    rot90_sses = {}
    for deg in (90, 180, 270, -90, -270):
        rotated = _rotate_np(pa_u8, deg).astype(np.int16)
        s = float(np.mean((rotated - pb_pad) ** 2))
        rot90_sses[deg] = round(s, 3)
        if s < best_sse:
            best_sse = s
            best_angle = deg
    if debug_label:
        print(f"  [rot_dbg] {debug_label}: rot90_sses={rot90_sses} best_sse={best_sse:.3f}")
    if best_sse < sse_zero * ROT_THRESHOLD:
        if debug_label:
            print(f"  [rot_dbg] {debug_label}: → ROTATION {best_angle}°")
        return {"kind": "rotation", "angle_deg": best_angle}

    # --- Color diff: pixel-level MAD on masked arrays (normalized 0-1 by max color value 9) ---
    nonzero_mask = (pa != 0) & (pb_pad != 0)
    if nonzero_mask.any():
        color_diff = float(np.mean(np.abs((pa - pb_pad)[nonzero_mask]))) / 9.0
    else:
        color_diff = 0.0
    if debug_label:
        print(f"  [rot_dbg] {debug_label}: color_diff={color_diff:.4f}")
    if color_diff >= 0.05:
        if debug_label:
            print(f"  [rot_dbg] {debug_label}: → TRANSFORM color_diff={color_diff:.3f}")
        return {"kind": "transform", "color_diff": round(color_diff, 3)}
    return None
