import copy

from .blob_extractor import detect_background_colors, extract_blobs, apply_color_merge_groups, match_blobs_cross_level
from .camera import detect_frame_shift, grid_to_numpy
from .event_detector import detect_frame_events, merge_events, match_blobs, detect_transform_rotation


def frame_to_compact(frame) -> list[str]:
    """Convert a raw ARC frame (2-D int array) to a compact hex-string list."""
    return ["".join(format(v, "x") for v in row) for row in frame]


def _apply_camera_correction(blobs: dict, dr: int, dc: int) -> dict:
    """Return shallow-copied blobs with bbox shifted by (-dr, -dc).
    Absent blobs also get their bbox/last_seen_bbox corrected so that
    reappear distance checks remain valid across multiple camera-moving frames.
    """
    corrected = {}
    for oid, b in blobs.items():
        nb = copy.copy(b)
        nb.bbox = {
            "row_min": b.bbox["row_min"] - dr,
            "row_max": b.bbox["row_max"] - dr,
            "col_min": b.bbox["col_min"] - dc,
            "col_max": b.bbox["col_max"] - dc,
        }
        if b.last_seen_bbox is not None:
            nb.last_seen_bbox = {
                "row_min": b.last_seen_bbox["row_min"] - dr,
                "row_max": b.last_seen_bbox["row_max"] - dr,
                "col_min": b.last_seen_bbox["col_min"] - dc,
                "col_max": b.last_seen_bbox["col_max"] - dc,
            }
        corrected[oid] = nb
    return corrected


_REAPPEAR_DIST = 8


def _remap_blobs(
    corrected_prev: dict,
    curr_raw: dict,
    pairs: list,
    unmatched_prev: list,
    unmatched_curr: list,
    orig_prev: dict,
    next_id: int,
    archive: dict | None = None,  # color_sig → canonical obj_id
) -> tuple[dict, int]:
    """Assign persistent IDs to curr_raw blobs, preserving metadata from prev."""
    new_blobs = {}
    for pid, cid in pairs:
        b = curr_raw[cid]
        b.instance_id = pid
        b.name = orig_prev[pid].name
        b.type_hypothesis = orig_prev[pid].type_hypothesis
        new_blobs[pid] = b
    for pid in unmatched_prev:
        # unmatched_prev only contains present→absent blobs (match_blobs skips absent).
        b = copy.copy(corrected_prev[pid])
        b.is_present = False
        b.last_seen_bbox = corrected_prev[pid].bbox
        new_blobs[pid] = b
    for cid in unmatched_curr:
        b = curr_raw[cid]
        best_oid: str | None = None
        best_dist = _REAPPEAR_DIST + 1
        for oid, ob in corrected_prev.items():
            if ob.is_present:
                continue
            if set(ob.colors) != set(b.colors):
                continue
            ref_bbox = ob.last_seen_bbox or ob.bbox
            ref_center = (
                (ref_bbox["row_min"] + ref_bbox["row_max"]) // 2,
                (ref_bbox["col_min"] + ref_bbox["col_max"]) // 2,
            )
            dist = abs(b.center()[0] - ref_center[0]) + abs(b.center()[1] - ref_center[1])
            if dist < best_dist:
                best_dist = dist
                best_oid = oid
        if best_oid is not None:
            b.instance_id = best_oid
            b.name = orig_prev[best_oid].name
            b.type_hypothesis = orig_prev[best_oid].type_hypothesis
            new_blobs[best_oid] = b
        else:
            # Check archive for a canonical ID matching this blob's color type.
            sig = frozenset(b.colors) if b.colors else frozenset()
            archived_id = archive.get(sig) if archive is not None else None
            if archived_id is not None and archived_id not in new_blobs:
                b.instance_id = archived_id
                if archived_id in orig_prev:
                    b.name = orig_prev[archived_id].name
                    b.type_hypothesis = orig_prev[archived_id].type_hypothesis
                new_blobs[archived_id] = b
            else:
                new_id = f"obj_{next_id:03d}"
                next_id += 1
                b.instance_id = new_id
                new_blobs[new_id] = b
                if archive is not None and sig not in archive:
                    archive[sig] = new_id
    # Carry forward absent blobs that are still absent this frame.
    # match_blobs never puts absent blobs in unmatched_prev, so they would
    # otherwise be silently dropped from new_blobs after 1 frame of absence.
    for oid, ob in corrected_prev.items():
        if not ob.is_present and oid not in new_blobs:
            new_blobs[oid] = ob  # already camera-corrected; last_seen_bbox preserved
    return new_blobs, next_id


class BlobManager:
    """Tracks blob state across animation frames and game steps."""

    def __init__(self, initial_grid: list[str]):
        bg = detect_background_colors(initial_grid)
        blobs = extract_blobs(initial_grid, bg)
        self.current_frame: list[str] = initial_grid
        self._bg_colors: set = bg
        self._blobs: dict = blobs
        self._next_id: int = len(blobs) + 1
        self._collide_pairs: set = set()
        self._color_merge_groups: list = []
        self._ever_moved_sigs: set = set()
        self._levels_completed: int = 0
        self._covered_by: dict[str, str] = {}
        # Archive: color_sig (frozenset) → canonical obj_id.
        # Persists across level transitions so the same blob type always gets
        # the same ID, allowing the agent to recognise recurring objects.
        self._archive: dict[frozenset, str] = {}
        for oid, b in blobs.items():
            sig = frozenset(b.colors) if b.colors else frozenset()
            if sig not in self._archive:
                self._archive[sig] = oid

    @property
    def blobs(self) -> dict:
        return self._blobs

    @property
    def blob_count(self) -> int:
        return sum(1 for b in self._blobs.values() if b.is_present)

    @property
    def archive(self) -> dict[frozenset, str]:
        """Color-sig → canonical obj_id. Persists across level transitions."""
        return self._archive

    def serialize_blobs(self) -> list[dict]:
        """Return a JSON-serialisable list of currently present blobs."""
        return [
            {
                "id": oid,
                "name": b.name or oid,
                "bbox": b.bbox,
                "colors": list(b.colors) if b.colors else [],
                "cell_count": b.cell_count,
            }
            for oid, b in self._blobs.items()
            if b.is_present
        ]

    def reset(self, grid: list[str]) -> None:
        """RESET action: re-detect background and blobs from scratch."""
        bg = detect_background_colors(grid)
        blobs = extract_blobs(grid, bg)
        self.current_frame = grid
        self._bg_colors = bg
        self._blobs = blobs
        self._next_id = len(blobs) + 1
        self._collide_pairs = set()
        self._color_merge_groups = []
        self._ever_moved_sigs = set()
        self._levels_completed = 0
        self._covered_by = {}
        # Repopulate archive with reset blobs (archive persists across resets).
        for oid, b in blobs.items():
            sig = frozenset(b.colors) if b.colors else frozenset()
            if sig not in self._archive:
                self._archive[sig] = oid

    def step(
        self,
        anim_frames: list[list[str]],
        levels_completed: int,
        game_state: str = "NOT_FINISHED",
    ) -> tuple[list, list, dict | None]:
        """
        Process a game step.
        anim_frames: compact grid frames from obs_result (already converted).
        levels_completed: from obs_result.levels_completed.
        game_state: obs_result.state.value (e.g. 'NOT_FINISHED', 'GAME_OVER', 'WIN').
        Updates self.current_frame to anim_frames[-1].
        Returns (animation_events, result_events, level_transition_info).
        """
        if game_state == "GAME_OVER":
            self.current_frame = anim_frames[-1]
            return [{"type": "game_over"}], [], None

        if levels_completed > self._levels_completed:
            return self._handle_level_transition(anim_frames[-1], levels_completed)

        animation_events, result_events = self._run_animation_analysis(anim_frames)
        self.current_frame = anim_frames[-1]
        return animation_events, result_events, None

    def _remap_with_archive(self, blobs: dict) -> dict:
        """Replace extract_blobs sequential IDs with archive canonical IDs where known."""
        remapped: dict = {}
        used: set[str] = set()
        for raw_id, b in blobs.items():
            sig = frozenset(b.colors) if b.colors else frozenset()
            archived_id = self._archive.get(sig)
            if archived_id is not None and archived_id not in used:
                b.instance_id = archived_id
                remapped[archived_id] = b
                used.add(archived_id)
            else:
                # Unknown type — assign a new ID and register in archive
                new_id = f"obj_{self._next_id:03d}"
                self._next_id += 1
                b.instance_id = new_id
                remapped[new_id] = b
                if archived_id is None:
                    self._archive[sig] = new_id
        return remapped

    def _handle_level_transition(
        self, last_frame: list[str], levels_completed: int
    ) -> tuple[list, list, dict]:
        prev_blobs_snapshot = dict(self._blobs)
        bg = detect_background_colors(last_frame)
        new_blobs = extract_blobs(last_frame, bg)
        new_blobs = apply_color_merge_groups(new_blobs, self._color_merge_groups)
        # Remap extracted blob IDs using the archive so the same color type
        # always gets the same canonical ID across level transitions.
        new_blobs = self._remap_with_archive(new_blobs)
        cross_matches = match_blobs_cross_level(prev_blobs_snapshot, new_blobs)
        self._blobs = new_blobs
        self._bg_colors = bg
        self._collide_pairs = set()
        self._covered_by = {}
        self._levels_completed = levels_completed
        self.current_frame = last_frame
        return [], [], {
            "event": "level_transition",
            "new_level": levels_completed,
            "objects": cross_matches,
        }

    def _run_animation_analysis(self, anim_frames: list[list[str]]) -> tuple[list, list]:
        prev_grid = self.current_frame
        sequence = [prev_grid] + anim_frames
        frame_events: list[list[dict]] = []
        current_blobs = dict(self._blobs)
        initial_prev_blobs = dict(self._blobs)
        np_prev_grid = grid_to_numpy(prev_grid)
        prev_collide_pairs = set(self._collide_pairs)

        for i, grid_b in enumerate(anim_frames):
            grid_a = sequence[i]
            camera_shift = detect_frame_shift(grid_a, grid_b)
            dr, dc, _angle = camera_shift

            corrected = _apply_camera_correction(current_blobs, dr, dc)
            curr_raw = extract_blobs(grid_b, self._bg_colors)
            curr_raw = apply_color_merge_groups(curr_raw, self._color_merge_groups)

            np_a = grid_to_numpy(grid_a)
            np_b = grid_to_numpy(grid_b)
            is_last = (i == len(anim_frames) - 1)
            is_camera_moving = (dr != 0 or dc != 0 or _angle != 0.0)

            events, prev_collide_pairs, newly_covered = detect_frame_events(
                corrected, curr_raw, camera_shift,
                frame_idx=i, prev_collide_pairs=prev_collide_pairs,
                arr_a=np_a, arr_b=np_b,
                emit_appear=is_last and not is_camera_moving,
                emit_disappear=not is_camera_moving,
            )

            # Camera 이동 중: 카메라 이벤트만 유지, 오브젝트 이벤트 전부 억제
            if is_camera_moving:
                events = [e for e in events
                          if e["type"] in ("camera_shift", "camera_rotation")]
            frame_events.append(events)

            pairs, unmatched_prev, unmatched_curr = match_blobs(corrected, curr_raw)

            # Co-movement merge detection — camera 이동 중에는 스킵 (false merge 방지)
            if not is_camera_moving:
                first_movers: dict[frozenset, list] = {}
                sig_to_pid: dict[frozenset, str] = {}
                ShapeKey = tuple  # (frozenset[str], int)
                prev_shape_count: dict[ShapeKey, int] = {}
                for pb in corrected.values():
                    if pb.is_present:
                        sig = frozenset(pb.colors)
                        sig_to_pid[sig] = pb.instance_id
                        key = (sig, pb.cell_count)
                        prev_shape_count[key] = prev_shape_count.get(key, 0) + 1
                curr_shape_count: dict[ShapeKey, int] = {}
                for cb in curr_raw.values():
                    key = (frozenset(cb.colors), cb.cell_count)
                    curr_shape_count[key] = curr_shape_count.get(key, 0) + 1
                for pid, cid in pairs:
                    pb, cb = corrected[pid], curr_raw[cid]
                    sig = frozenset(pb.colors)
                    if sig in self._ever_moved_sigs:
                        continue
                    if (prev_shape_count.get((sig, pb.cell_count), 0) > 1
                            or curr_shape_count.get((frozenset(cb.colors), cb.cell_count), 0) > 1):
                        continue
                    dr_m = cb.center()[0] - pb.center()[0]
                    dc_m = cb.center()[1] - pb.center()[1]
                    if abs(dr_m) > 1 or abs(dc_m) > 1:
                        if dr_m == -dr and dc_m == -dc:
                            continue
                        first_movers[sig] = [dr_m, dc_m]
                sigs = list(first_movers.keys())
                new_merge_events: list[dict] = []
                for si, sig_a in enumerate(sigs):
                    for sig_b in sigs[si + 1:]:
                        if first_movers[sig_a] == first_movers[sig_b]:
                            merged_group = sig_a | sig_b
                            if merged_group not in self._color_merge_groups:
                                self._color_merge_groups.append(merged_group)
                                pid_a = sig_to_pid.get(sig_a)
                                pid_b = sig_to_pid.get(sig_b)
                                name_a = (corrected[pid_a].name or pid_a) if pid_a else str(sig_a)
                                name_b = (corrected[pid_b].name or pid_b) if pid_b else str(sig_b)
                                new_merge_events.append({
                                    "type": "merge",
                                    "obj_a": name_a,
                                    "obj_b": name_b,
                                    "frame": i,
                                })
                if new_merge_events:
                    merged_name_pairs = {
                        frozenset([me["obj_a"], me["obj_b"]]) for me in new_merge_events
                    }
                    frame_events[-1] = [
                        e for e in frame_events[-1]
                        if not (e["type"] == "collide"
                                and frozenset([e["obj_a"], e["obj_b"]]) in merged_name_pairs)
                    ]
                    merged_pid_pairs = {
                        frozenset([sig_to_pid[sig_a], sig_to_pid[sig_b]])
                        for si2, sig_a in enumerate(sigs)
                        for sig_b in sigs[si2 + 1:]
                        if (first_movers[sig_a] == first_movers[sig_b]
                            and sig_to_pid.get(sig_a) and sig_to_pid.get(sig_b))
                    }
                    prev_collide_pairs -= merged_pid_pairs
                    cur_events = frame_events[-1]
                    insert_at = next(
                        (j for j, e in enumerate(cur_events) if e["type"] == "collide"),
                        len(cur_events),
                    )
                    for k, me in enumerate(new_merge_events):
                        cur_events.insert(insert_at + k, me)
                for sig in first_movers:
                    self._ever_moved_sigs.add(sig)

            current_blobs, self._next_id = _remap_blobs(
                corrected, curr_raw, pairs, unmatched_prev, unmatched_curr,
                current_blobs, self._next_id, self._archive,
            )

            # Deferred disappear — camera 이동 중에는 covered_by 갱신/emit 스킵
            if not is_camera_moving:
                for covered_pid, covering_pid in newly_covered.items():
                    self._covered_by[covered_pid] = covering_pid
                for covered_pid in list(self._covered_by.keys()):
                    cb_blob = current_blobs.get(covered_pid)
                    if cb_blob is None or cb_blob.is_present:
                        del self._covered_by[covered_pid]
                        continue
                    covering_pid = self._covered_by[covered_pid]
                    cov_blob = current_blobs.get(covering_pid)
                    ref = cb_blob.last_seen_bbox or cb_blob.bbox
                    ref_r = (ref["row_min"] + ref["row_max"]) // 2
                    ref_c = (ref["col_min"] + ref["col_max"]) // 2
                    still_covered = (
                        cov_blob is not None
                        and cov_blob.is_present
                        and cov_blob.bbox["row_min"] <= ref_r <= cov_blob.bbox["row_max"]
                        and cov_blob.bbox["col_min"] <= ref_c <= cov_blob.bbox["col_max"]
                    )
                    if not still_covered and is_last:
                        frame_events[-1].append({
                            "type": "disappear",
                            "obj": cb_blob.instance_id,
                            "last_pos": [ref_r, ref_c],
                            "cause": "collide_destroy",
                            "frame": i,
                        })
                        del self._covered_by[covered_pid]

            # Remove blobs absorbed into a CO-MOVEMENT merge group only.
            # Do NOT delete absent blobs whose colors appear as subset due to collision coverage.
            if self._color_merge_groups:
                merge_group_sigs = [frozenset(g) for g in self._color_merge_groups]
                present_sigs = [
                    frozenset(b.colors) for b in current_blobs.values() if b.is_present
                ]
                absorbed = [
                    pid for pid, b in current_blobs.items()
                    if not b.is_present
                    and any(
                        frozenset(b.colors) < psig
                        and any(
                            frozenset(b.colors) <= grp and psig <= grp
                            for grp in merge_group_sigs
                        )
                        for psig in present_sigs
                    )
                ]
                for pid in absorbed:
                    del current_blobs[pid]

            if self._color_merge_groups:
                current_blobs = apply_color_merge_groups(current_blobs, self._color_merge_groups)

        np_final = grid_to_numpy(anim_frames[-1])
        result_events = detect_transform_rotation(
            initial_prev_blobs, current_blobs,
            np_prev_grid, np_final,
            frame_idx=len(anim_frames) - 1,
        )

        self._blobs = current_blobs
        self._collide_pairs = prev_collide_pairs
        return merge_events(frame_events), result_events
