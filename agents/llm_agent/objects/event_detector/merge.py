"""Event merging — collapse consecutive same-direction events into one."""

from __future__ import annotations


def _same_direction(d1: list, d2: list) -> bool:
    """True if d2 does not reverse any component of d1 (no sign flip, no cancellation)."""
    return d1[0] * d2[0] >= 0 and d1[1] * d2[1] >= 0


def merge_events(event_sequence: list[list[dict]]) -> list[dict]:
    """
    Merge per-frame event lists into a summarised event list.

    Consecutive move events for the same object in the same direction are merged
    and their deltas accumulated. A direction change (sign flip) starts a new entry.
    This prevents (-5,0)+(5,0) from collapsing to (0,0) and losing information.
    Uses a per-object dict so multiple simultaneously moving objects are handled correctly.
    """
    flat: list[dict] = [e for frame_events in event_sequence for e in frame_events]
    result: list[dict] = []
    active_move: dict[str, int] = {}  # obj → index into result

    active_camera_shift: int | None = None
    active_camera_rot: int | None = None

    for ev in flat:
        if ev["type"] == "move":
            obj = ev["obj"]
            if obj in active_move:
                prev = result[active_move[obj]]
                if _same_direction(prev["delta"], ev["delta"]):
                    prev["delta"] = [prev["delta"][0] + ev["delta"][0],
                                     prev["delta"][1] + ev["delta"][1]]
                    prev["frames"][1] = ev["frame"]
                    prev["to"] = ev["to"]
                    continue
                else:
                    del active_move[obj]
            new_ev = dict(ev, frames=[ev["frame"], ev["frame"]])
            active_move[obj] = len(result)
            result.append(new_ev)

        elif ev["type"] == "camera_shift":
            if active_camera_shift is not None:
                prev = result[active_camera_shift]
                if _same_direction(prev["delta"], ev["delta"]):
                    prev["delta"] = [prev["delta"][0] + ev["delta"][0],
                                     prev["delta"][1] + ev["delta"][1]]
                    prev["frames"][1] = ev["frame"]
                    continue
            new_ev = dict(ev, frames=[ev["frame"], ev["frame"]])
            active_camera_shift = len(result)
            result.append(new_ev)

        elif ev["type"] == "camera_rotation":
            if active_camera_rot is not None:
                prev = result[active_camera_rot]
                if prev["angle_deg"] * ev["angle_deg"] >= 0:
                    prev["angle_deg"] = prev["angle_deg"] + ev["angle_deg"]
                    prev["frames"][1] = ev["frame"]
                    continue
            new_ev = dict(ev, frames=[ev["frame"], ev["frame"]])
            active_camera_rot = len(result)
            result.append(new_ev)

        else:
            result.append(ev)

    return result
