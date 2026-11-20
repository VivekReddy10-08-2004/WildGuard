from scripts.evaluate_megadetector_videos import animal_confidences


def test_animal_confidences_filter_other_megadetector_classes() -> None:
    result = {
        "detections": [
            {"category": "1", "conf": 0.8},
            {"category": "2", "conf": 0.9},
            {"category": "3", "conf": 0.7},
            {"category": "1", "conf": 0.4},
        ]
    }

    assert animal_confidences(result) == [0.8, 0.4]


def test_animal_confidences_handle_missing_detections() -> None:
    assert animal_confidences({}) == []
