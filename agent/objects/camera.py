"""numpy-based camera shift + 1-degree rotation detection.

Per animation frame pair:
  1. Translation: SSE-minimising shift in ±SHIFT_RANGE (np.roll, vectorised)
  2. Rotation: if translation SSE not satisfactory, search ±ROT_RANGE_DEG at 1° step
  3. Returns (dr, dc, angle_deg) — angle_deg=0 means pure translation
"""

import numpy as np

_SHIFT_RANGE = 4        # cell search range per animation frame
_ROT_RANGE_DEG = 10     # camera rotation search range ±degrees
_DIFF_THRESHOLD = 60    # min changed cells to bother running SSE
_IMPROVE_THRESH = 0.85  # SSE must be < baseline * this to count as significant


# ---------------------------------------------------------------------------
# Grid helpers
# ---------------------------------------------------------------------------

def grid_to_numpy(grid: list[str]) -> np.ndarray:
    """Convert compact string grid to uint8 numpy array (H, W)."""
    return np.array([[int(c, 16) for c in row] for row in grid], dtype=np.uint8)


def _diff_count(g1: list[str], g2: list[str]) -> int:
    return int(np.sum(grid_to_numpy(g1) != grid_to_numpy(g2)))


# ---------------------------------------------------------------------------
# Translation SSE (vectorised with np.roll)
# ---------------------------------------------------------------------------

def _sse_shift(arr_a: np.ndarray, arr_b: np.ndarray, dr: int, dc: int) -> float:
    shifted = np.roll(arr_a, (-dr, -dc), axis=(0, 1))
    return float(np.mean((shifted.astype(np.int16) - arr_b.astype(np.int16)) ** 2))


def _best_translation(
    arr_a: np.ndarray,
    arr_b: np.ndarray,
    sr: int,
    sc: int,
) -> tuple[int, int, float]:
    best_sse = float("inf")
    best_dr = best_dc = 0
    for dr in range(-sr, sr + 1):
        for dc in range(-sc, sc + 1):
            s = _sse_shift(arr_a, arr_b, dr, dc)
            if s < best_sse:
                best_sse = s
                best_dr, best_dc = dr, dc
    return best_dr, best_dc, best_sse


# ---------------------------------------------------------------------------
# Rotation helpers (numpy nearest-neighbour, no scipy)
# ---------------------------------------------------------------------------

def _rotate_np(arr: np.ndarray, angle_deg: float) -> np.ndarray:
    """Rotate arr around its centre by angle_deg (nearest-neighbour, in-place shape)."""
    H, W = arr.shape
    cy, cx = (H - 1) / 2.0, (W - 1) / 2.0
    a = np.radians(angle_deg)
    cos_a, sin_a = np.cos(a), np.sin(a)

    ys, xs = np.mgrid[0:H, 0:W]
    yr = ys - cy
    xr = xs - cx

    src_r = np.round( cos_a * yr + sin_a * xr + cy).astype(np.int32)
    src_c = np.round(-sin_a * yr + cos_a * xr + cx).astype(np.int32)

    valid = (src_r >= 0) & (src_r < H) & (src_c >= 0) & (src_c < W)
    result = np.zeros_like(arr)
    result[ys[valid], xs[valid]] = arr[src_r[valid], src_c[valid]]
    return result


def _best_rotation(
    arr_a: np.ndarray,
    arr_b: np.ndarray,
    max_deg: int,
    post_shift: int = 2,
) -> tuple[float, int, int, float]:
    """
    Search ±max_deg at 1° step. For each rotation, also search ±post_shift translation.
    Returns (angle_deg, dr, dc, best_sse).
    """
    best_sse = float("inf")
    best_angle = 0.0
    best_dr = best_dc = 0

    for deg in range(-max_deg, max_deg + 1):
        if deg == 0:
            continue
        rotated = _rotate_np(arr_a, deg)
        dr, dc, s = _best_translation(rotated, arr_b, post_shift, post_shift)
        if s < best_sse:
            best_sse = s
            best_angle = float(deg)
            best_dr, best_dc = dr, dc

    return best_angle, best_dr, best_dc, best_sse


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_frame_shift(
    grid_a: list[str],
    grid_b: list[str],
    shift_range: int = _SHIFT_RANGE,
    rot_range: int = _ROT_RANGE_DEG,
) -> tuple[int, int, float]:
    """
    Detect camera movement between two consecutive animation frames.

    Returns (dr, dc, angle_deg):
      - (0, 0, 0.0)  → no significant movement
      - (dr, dc, 0.0) → pure translation
      - (0, 0, angle) → rotation without translation
      - (dr, dc, angle) → rotation + translation
    """
    if _diff_count(grid_a, grid_b) < _DIFF_THRESHOLD:
        return (0, 0, 0.0)

    arr_a = grid_to_numpy(grid_a)
    arr_b = grid_to_numpy(grid_b)

    # --- Step 1: best translation ---
    t_dr, t_dc, t_sse = _best_translation(arr_a, arr_b, shift_range, shift_range)
    sse_zero = _sse_shift(arr_a, arr_b, 0, 0)

    # If translation is not significant (no improvement), return early
    if sse_zero == 0:
        return (0, 0, 0.0)

    translation_ok = t_sse < sse_zero * _IMPROVE_THRESH

    # --- Step 2: rotation search (only if translation alone is poor) ---
    r_angle, r_dr, r_dc, r_sse = _best_rotation(arr_a, arr_b, rot_range)
    rotation_better = r_sse < t_sse * _IMPROVE_THRESH

    if rotation_better:
        # Rotation is dominant; also apply its translation correction
        return (r_dr, r_dc, r_angle)

    if translation_ok:
        return (t_dr, t_dc, 0.0)

    return (0, 0, 0.0)


def detect_scale(grid: list[str]) -> int:
    """Detect camera upscale factor N from the rendered 64×64 grid.

    ARCEngine scales a W×H camera viewport up by floor(64 / max(W, H)),
    so every game pixel becomes an N×N screen-pixel block.

    Strategy: for scale=N with a possible letterbox offset, consecutive rows/cols
    inside the same N-row band must be pixel-identical. We search offsets 0..N-1
    to handle odd-pixel letterboxing. Returns 1 (no upscale), 2, 3, or 4.
    """
    arr = grid_to_numpy(grid)
    H, W = arr.shape

    row_same = np.array([np.array_equal(arr[r], arr[r + 1]) for r in range(H - 1)])
    col_same = np.array([np.array_equal(arr[:, c], arr[:, c + 1]) for c in range(W - 1)])

    for n in (2, 3, 4):
        for yo in range(n):
            in_block_r = np.array([(r - yo) % n != n - 1 for r in range(H - 1)])
            pairs_r = row_same[in_block_r]
            if len(pairs_r) == 0 or np.mean(pairs_r) < 0.95:
                continue
            for xo in range(n):
                in_block_c = np.array([(c - xo) % n != n - 1 for c in range(W - 1)])
                pairs_c = col_same[in_block_c]
                if len(pairs_c) > 0 and np.mean(pairs_c) >= 0.95:
                    return n
    return 1


def analyse_animation_shifts(
    prev_grid: list[str],
    anim_frames: list[list[str]],
) -> list[tuple[int, int, float]]:
    """
    Compute (dr, dc, angle_deg) for each consecutive frame pair.
    Returns list of length len(anim_frames).
    """
    sequence = [prev_grid] + anim_frames
    return [
        detect_frame_shift(sequence[i], sequence[i + 1])
        for i in range(len(sequence) - 1)
    ]
