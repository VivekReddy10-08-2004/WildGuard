from pathlib import Path

from scripts.evaluate_deer_driver_dataset import (
    Box,
    EvaluatedImage,
    Prediction,
    average_precision,
    box_iou,
    threshold_metrics,
)


def _image(
    ground_truth: tuple[Box, ...], predictions: tuple[Prediction, ...]
) -> EvaluatedImage:
    return EvaluatedImage(
        image=Path("test.jpg"),
        split="test",
        source_dataset="test",
        ground_truth=ground_truth,
        predictions=predictions,
        processing_ms=1.0,
    )


def test_box_iou() -> None:
    assert box_iou((0.0, 0.0, 1.0, 1.0), (0.5, 0.5, 1.0, 1.0)) == 0.25


def test_perfect_detection_metrics() -> None:
    box = (0.1, 0.1, 0.5, 0.5)
    prediction = Prediction(4, "mule_deer", 0.9, box)
    images = [_image((box,), (prediction,)), _image((), ())]

    metrics = threshold_metrics(images, frozenset({4}), confidence=0.25)

    assert metrics["precision"] == 1.0
    assert metrics["recall"] == 1.0
    assert metrics["false_positive_image_rate"] == 0.0
    assert average_precision(images, frozenset({4}), iou_threshold=0.5) == 1.0


def test_wrong_class_is_a_miss_for_strict_view() -> None:
    box = (0.1, 0.1, 0.5, 0.5)
    prediction = Prediction(9, "moose", 0.9, box)

    metrics = threshold_metrics(
        [_image((box,), (prediction,))], frozenset({4}), confidence=0.25
    )

    assert metrics["true_positives"] == 0
    assert metrics["false_negatives"] == 1
