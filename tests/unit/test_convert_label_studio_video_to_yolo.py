from scripts.convert_label_studio_video_to_yolo import (
    Keyframe,
    collect_frame_boxes,
    interpolate_track,
)


def _result(track_id: str, sequence: list[dict[str, object]]) -> dict[str, object]:
    return {
        "id": track_id,
        "type": "videorectangle",
        "value": {"labels": ["animal"], "sequence": sequence},
    }


def test_interpolate_track_ends_before_disabled_frame() -> None:
    boxes = interpolate_track(
        [
            Keyframe(10, True, 10.0, 20.0, 20.0, 40.0),
            Keyframe(13, False, 40.0, 20.0, 20.0, 40.0),
        ]
    )

    assert sorted(boxes) == [10, 11, 12]
    assert boxes[10].x_center == 0.2
    assert boxes[12].x_center == 0.4


def test_collect_frame_boxes_ignores_empty_tracks_and_samples() -> None:
    task = {
        "annotations": [
            {
                "result": [
                    _result("empty", []),
                    _result(
                        "animal-1",
                        [
                            {
                                "frame": 2,
                                "enabled": True,
                                "x": 10.0,
                                "y": 20.0,
                                "width": 20.0,
                                "height": 40.0,
                            },
                            {
                                "frame": 8,
                                "enabled": False,
                                "x": 40.0,
                                "y": 20.0,
                                "width": 20.0,
                                "height": 40.0,
                            },
                        ],
                    ),
                ]
            }
        ]
    }

    frames, stats = collect_frame_boxes(task, frame_stride=3)

    assert sorted(frames) == [2, 5]
    assert frames[2][0].interpolated is False
    assert frames[5][0].interpolated is True
    assert stats == {"empty_tracks_ignored": 1, "nonempty_tracks": 1}


def test_collect_frame_boxes_keeps_each_track_sampling_origin() -> None:
    task = {
        "annotations": [
            {
                "result": [
                    _result(
                        "first",
                        [
                            {
                                "frame": 2,
                                "enabled": True,
                                "x": 10,
                                "y": 10,
                                "width": 10,
                                "height": 10,
                            }
                        ],
                    ),
                    _result(
                        "second",
                        [
                            {
                                "frame": 3,
                                "enabled": True,
                                "x": 20,
                                "y": 20,
                                "width": 10,
                                "height": 10,
                            }
                        ],
                    ),
                ]
            }
        ]
    }

    frames, _ = collect_frame_boxes(task, frame_stride=3)

    assert sorted(frames) == [2, 3]


def test_collect_frame_boxes_can_keep_reviewed_keyframes_and_exclude_one() -> None:
    task = {
        "annotations": [
            {
                "result": [
                    _result(
                        "animal-1",
                        [
                            {
                                "frame": 2,
                                "enabled": True,
                                "x": 10,
                                "y": 10,
                                "width": 10,
                                "height": 10,
                            },
                            {
                                "frame": 5,
                                "enabled": True,
                                "x": 20,
                                "y": 20,
                                "width": 20,
                                "height": 20,
                            },
                            {
                                "frame": 8,
                                "enabled": False,
                                "x": 30,
                                "y": 30,
                                "width": 30,
                                "height": 30,
                            },
                        ],
                    )
                ]
            }
        ]
    }

    frames, _ = collect_frame_boxes(
        task,
        frame_stride=1,
        keyframes_only=True,
        excluded_frames={5},
    )

    assert sorted(frames) == [2]
