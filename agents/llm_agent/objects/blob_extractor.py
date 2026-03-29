from collections import Counter
from .object import Blob


def detect_background_colors(grid: list[str]) -> set[str]:
    counts: Counter = Counter(ch for row in grid for ch in row)
    total = sum(counts.values())
    top = counts.most_common()
    bg: set[str] = set()

    for color, count in top:
        if count / total > 0.15:
            bg.add(color)

    # Checkerboard: 2nd color ≥60% of 1st and >8% of grid → also background
    if len(top) >= 2 and top[0][1] > 0:
        if top[1][1] / top[0][1] >= 0.60 and top[1][1] / total > 0.08:
            bg.add(top[1][0])

    return bg


def _shape_tags(cells: list[tuple], bbox: dict) -> list[str]:
    h = bbox["row_max"] - bbox["row_min"] + 1
    w = bbox["col_max"] - bbox["col_min"] + 1
    fill = len(cells) / (h * w) if h * w > 0 else 0
    tags: list[str] = []

    if h == 1:
        tags.append("line_h")
    elif w == 1:
        tags.append("line_v")
    elif fill > 0.85:
        tags.append("solid")
    elif fill < 0.50:
        tags.append("hollow")
    else:
        tags.append("partial")

    if h == w:
        tags.append("square_bbox")
    elif h > w * 1.5:
        tags.append("tall")
    elif w > h * 1.5:
        tags.append("wide")

    return tags


def _bbox_area(bbox: dict) -> int:
    return (bbox["row_max"] - bbox["row_min"] + 1) * (bbox["col_max"] - bbox["col_min"] + 1)


def _is_enclosed(inner: dict, outer: dict) -> bool:
    """True if inner bbox is completely within outer bbox (edges included)."""
    return (
        outer["row_min"] <= inner["row_min"]
        and outer["row_max"] >= inner["row_max"]
        and outer["col_min"] <= inner["col_min"]
        and outer["col_max"] >= inner["col_max"]
    )


def _merge_enclosed_blobs(blobs: dict[str, Blob]) -> dict[str, Blob]:
    """
    Absorb any blob whose bbox is completely inside another blob's bbox.
    Assumption: at game start no two INDEPENDENT objects share the same bbox space.

    Merge rule:
      - outer has larger bbox_area, OR same area but more cells (tiebreak)
      - outer.colors += inner.colors (deduplicated)
      - outer.cell_count += inner.cell_count
      - inner is removed
    Chain merges (C⊂B⊂A) resolved by following parent to root.
    """
    ids = list(blobs.keys())
    parent: dict[str, str] = {}

    for bid in ids:
        b = blobs[bid]
        b_area = _bbox_area(b.bbox)
        best_parent: str | None = None
        best_area = float("inf")
        for oid in ids:
            if oid == bid:
                continue
            o = blobs[oid]
            if not _is_enclosed(b.bbox, o.bbox):
                continue
            o_area = _bbox_area(o.bbox)
            # outer must be strictly larger, or same area with more cells
            if o_area < b_area:
                continue
            if o_area == b_area and o.cell_count <= b.cell_count:
                continue
            # prefer the tightest enclosing bbox
            if o_area < best_area:
                best_area = o_area
                best_parent = oid
        if best_parent is not None:
            parent[bid] = best_parent

    def find_root(bid: str) -> str:
        seen: set = set()
        while bid in parent and bid not in seen:
            seen.add(bid)
            bid = parent[bid]
        return bid

    to_remove: set[str] = set()
    for bid in list(parent.keys()):
        root = find_root(bid)
        root_blob = blobs[root]
        child_blob = blobs[bid]
        for c in child_blob.colors:
            if c not in root_blob.colors:
                root_blob.colors.append(c)
        new_total = root_blob.cell_count + child_blob.cell_count
        new_ratios: dict[str, float] = {}
        for c, r in root_blob.color_ratios.items():
            new_ratios[c] = r * root_blob.cell_count / new_total
        for c, r in child_blob.color_ratios.items():
            new_ratios[c] = new_ratios.get(c, 0.0) + r * child_blob.cell_count / new_total
        root_blob.color_ratios = new_ratios
        root_blob.cell_count = new_total
        to_remove.add(bid)

    return {k: v for k, v in blobs.items() if k not in to_remove}


def _bboxes_close(bbox_a: dict, bbox_b: dict, max_gap: int = 4) -> bool:
    """True if two bboxes are within max_gap pixels of each other."""
    row_gap = max(0,
                  bbox_a["row_min"] - bbox_b["row_max"] - 1,
                  bbox_b["row_min"] - bbox_a["row_max"] - 1)
    col_gap = max(0,
                  bbox_a["col_min"] - bbox_b["col_max"] - 1,
                  bbox_b["col_min"] - bbox_a["col_max"] - 1)
    return row_gap <= max_gap and col_gap <= max_gap


def apply_color_merge_groups(
    blobs: dict[str, "Blob"],
    merge_groups: list,
    max_gap: int = 4,
) -> dict[str, "Blob"]:
    """
    Enforce learned co-movement merge rules.
    For each merge group (frozenset of color chars), find spatially close blobs
    whose color set is a subset of the group and merge them into one composite blob.
    Called after extract_blobs each frame.
    """
    if not merge_groups:
        return blobs

    result = dict(blobs)
    for group in merge_groups:
        candidates = [
            (oid, b) for oid, b in result.items()
            if frozenset(b.colors) and frozenset(b.colors).issubset(group)
        ]
        if len(candidates) < 2:
            continue
        to_remove: set[str] = set()
        for i, (oid_a, ba) in enumerate(candidates):
            if oid_a in to_remove:
                continue
            for oid_b, bb in candidates[i + 1:]:
                if oid_b in to_remove:
                    continue
                if not _bboxes_close(ba.bbox, bb.bbox, max_gap):
                    continue
                primary, secondary = (
                    (oid_a, oid_b) if ba.cell_count >= bb.cell_count
                    else (oid_b, oid_a)
                )
                pb, sb = result[primary], result[secondary]
                for c in sb.colors:
                    if c not in pb.colors:
                        pb.colors.append(c)
                pb.cell_count += sb.cell_count
                pb.bbox = {
                    "row_min": min(pb.bbox["row_min"], sb.bbox["row_min"]),
                    "row_max": max(pb.bbox["row_max"], sb.bbox["row_max"]),
                    "col_min": min(pb.bbox["col_min"], sb.bbox["col_min"]),
                    "col_max": max(pb.bbox["col_max"], sb.bbox["col_max"]),
                }
                to_remove.add(secondary)
        result = {k: v for k, v in result.items() if k not in to_remove}

    return result


def extract_blobs(
    grid: list[str],
    bg_colors: set[str],
    min_cells: int = 2,
) -> dict[str, Blob]:
    H = len(grid)
    W = len(grid[0]) if H > 0 else 0
    visited = [[False] * W for _ in range(H)]
    blobs: dict[str, Blob] = {}
    obj_count = 0

    for r in range(H):
        for c in range(W):
            ch = grid[r][c]
            if visited[r][c] or ch in bg_colors:
                visited[r][c] = True
                continue

            # BFS flood fill — 4-connected, same color only
            cells: list[tuple] = []
            queue = [(r, c)]
            visited[r][c] = True
            while queue:
                nr, nc = queue.pop(0)
                cells.append((nr, nc))
                for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    rr, cc = nr + dr, nc + dc
                    if (0 <= rr < H and 0 <= cc < W
                            and not visited[rr][cc]
                            and grid[rr][cc] == ch):
                        visited[rr][cc] = True
                        queue.append((rr, cc))

            if len(cells) < min_cells:
                continue

            rs = [p[0] for p in cells]
            cs = [p[1] for p in cells]
            bbox = {
                "row_min": min(rs), "row_max": max(rs),
                "col_min": min(cs), "col_max": max(cs),
            }
            obj_count += 1
            oid = f"obj_{obj_count:03d}"
            blobs[oid] = Blob(
                instance_id=oid,
                colors=[ch],
                bbox=bbox,
                cell_count=len(cells),
                shape_tags=_shape_tags(cells, bbox),
                color_ratios={ch: 1.0},
            )

    return _merge_enclosed_blobs(blobs)


def _color_hist_dist(h1: dict, h2: dict) -> float:
    """L1 distance between two color ratio dicts. Range [0, 2] (0=identical)."""
    all_colors = set(h1) | set(h2)
    return sum(abs(h1.get(c, 0.0) - h2.get(c, 0.0)) for c in all_colors)


def match_blobs_cross_level(
    prev_blobs: dict,
    curr_blobs: dict,
    threshold: float = 0.25,
) -> list[dict]:
    """
    Match new-level blobs to previous-level blobs by color ratio similarity.
    Returns a list of match dicts for the LLM verification payload.
    Each matched curr blob inherits name/type_hypothesis from the best prev match.
    Modifies curr_blobs in-place.
    """
    matches = []
    used_prev: set[str] = set()

    for cid, cb in curr_blobs.items():
        best_pid: str | None = None
        best_dist = threshold + 1
        for pid, pb in prev_blobs.items():
            if pid in used_prev or not pb.is_present:
                continue
            dist = _color_hist_dist(cb.color_ratios, pb.color_ratios)
            if dist < best_dist:
                best_dist = dist
                best_pid = pid

        if best_pid is None:
            continue

        pb = prev_blobs[best_pid]
        cb.name = pb.name
        cb.type_hypothesis = pb.type_hypothesis
        used_prev.add(best_pid)
        matches.append({
            "obj": cid,
            "inherited_from": best_pid,
            "color_match_ratio": round(1.0 - best_dist / 2.0, 3),
            "color_ratios": cb.color_ratios,
            "prev_type_hypothesis": pb.type_hypothesis,
        })

    return matches
