"""Reproducible first, best, and later evidence-frame selection."""

from shared.contracts import TrackedFrame


def select_evidence_frames(frames: list[TrackedFrame]) -> list[TrackedFrame]:
    if not frames:
        return []

    by_timestamp: dict[float, TrackedFrame] = {}
    for frame in frames:
        current = by_timestamp.get(frame.timestamp_s)
        if current is None or frame.confidence > current.confidence:
            by_timestamp[frame.timestamp_s] = frame

    ordered = sorted(by_timestamp.values(), key=lambda frame: frame.timestamp_s)
    first = ordered[0]
    best = max(ordered, key=lambda frame: (frame.confidence, -frame.timestamp_s))
    later = [frame for frame in ordered if frame.timestamp_s > best.timestamp_s]
    representative = later[-1] if later else ordered[-1]
    selected = {frame.timestamp_s: frame for frame in (first, best, representative)}
    return sorted(selected.values(), key=lambda frame: frame.timestamp_s)
