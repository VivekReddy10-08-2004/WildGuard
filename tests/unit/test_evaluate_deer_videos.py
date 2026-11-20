from scripts.evaluate_deer_videos import detection_events


def test_detection_events_merge_short_gaps() -> None:
    events = detection_events(
        [(30, [0.4]), (40, [0.6, 0.7]), (90, [0.8])],
        fps=30.0,
        gap_seconds=0.5,
    )

    assert len(events) == 2
    assert events[0].start_seconds == 1.0
    assert events[0].end_seconds == 40 / 30
    assert events[0].detection_frames == 2
    assert events[0].detections == 3
    assert events[0].max_confidence == 0.7
    assert events[1].start_seconds == 3.0


def test_detection_events_handle_no_detections() -> None:
    assert detection_events([], fps=30.0, gap_seconds=0.5) == []
