"""Evaluate the wildlife YOLO baseline on the derived deer-driver dataset."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from model_services.image.wildlife_detector import WildlifeDetector

Box = tuple[float, float, float, float]
DEFAULT_DATASET = Path("data/derived/deer-driver-v1")
DEFAULT_REPORT = Path("notebooks/results/deer_driver_v1_baseline_report.json")
DEFAULT_CACHE = Path("notebooks/results/deer_driver_v1_baseline_predictions.jsonl")
MODEL_VIEWS = {
    "strict_mule_deer": frozenset({4}),
    "driver_hazard_union": frozenset({4, 5, 9}),
}
CONFIDENCE_THRESHOLDS = (0.10, 0.25, 0.50)
IOU_THRESHOLDS = tuple(round(0.50 + 0.05 * index, 2) for index in range(10))


@dataclass(frozen=True)
class Prediction:
    class_id: int
    label: str
    confidence: float
    box: Box


@dataclass(frozen=True)
class EvaluatedImage:
    image: Path
    split: str
    source_dataset: str
    ground_truth: tuple[Box, ...]
    predictions: tuple[Prediction, ...]
    processing_ms: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--confidence-floor", type=float, default=0.001)
    parser.add_argument("--reuse-cache", action="store_true")
    return parser.parse_args()


def yolo_to_xyxy(values: Sequence[float]) -> Box:
    x_center, y_center, width, height = values
    return (
        x_center - width / 2,
        y_center - height / 2,
        x_center + width / 2,
        y_center + height / 2,
    )


def box_iou(left: Box, right: Box) -> float:
    x_min = max(left[0], right[0])
    y_min = max(left[1], right[1])
    x_max = min(left[2], right[2])
    y_max = min(left[3], right[3])
    intersection = max(0.0, x_max - x_min) * max(0.0, y_max - y_min)
    left_area = max(0.0, left[2] - left[0]) * max(0.0, left[3] - left[1])
    right_area = max(0.0, right[2] - right[0]) * max(0.0, right[3] - right[1])
    union = left_area + right_area - intersection
    return intersection / union if union else 0.0


def load_ground_truth(dataset: Path) -> list[EvaluatedImage]:
    manifest = dataset / "manifest.jsonl"
    if not manifest.is_file():
        raise FileNotFoundError(f"Derived manifest not found: {manifest}")

    images: list[EvaluatedImage] = []
    for line in manifest.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        label_path = dataset / row["derived_label"]
        boxes: list[Box] = []
        for label_line in label_path.read_text(encoding="utf-8").splitlines():
            parts = label_line.split()
            if len(parts) != 5 or parts[0] != "0":
                raise ValueError(f"Unexpected derived label: {label_path}")
            boxes.append(yolo_to_xyxy([float(value) for value in parts[1:]]))
        images.append(
            EvaluatedImage(
                image=dataset / row["derived_image"],
                split=str(row["split"]),
                source_dataset=str(row["source_dataset"]),
                ground_truth=tuple(boxes),
                predictions=(),
                processing_ms=0.0,
            )
        )
    return images


def run_inference(
    images: list[EvaluatedImage],
    *,
    batch_size: int,
    confidence_floor: float,
) -> tuple[list[EvaluatedImage], dict[int, str]]:
    detector = WildlifeDetector()
    class_names = dict(detector.class_names)
    evaluated: list[EvaluatedImage] = []
    for start in range(0, len(images), batch_size):
        batch = images[start : start + batch_size]
        results = detector.predict(
            [item.image for item in batch],
            confidence=confidence_floor,
            iou=0.70,
            image_size=640,
        )
        if len(results) != len(batch):
            raise RuntimeError("Model returned an unexpected number of results")
        for item, result in zip(batch, results, strict=True):
            predictions = tuple(
                Prediction(
                    class_id=detection.class_id,
                    label=detection.label,
                    confidence=detection.confidence,
                    box=(
                        detection.bounding_box.x_min / result.width,
                        detection.bounding_box.y_min / result.height,
                        detection.bounding_box.x_max / result.width,
                        detection.bounding_box.y_max / result.height,
                    ),
                )
                for detection in result.detections
            )
            evaluated.append(
                EvaluatedImage(
                    image=item.image,
                    split=item.split,
                    source_dataset=item.source_dataset,
                    ground_truth=item.ground_truth,
                    predictions=predictions,
                    processing_ms=result.processing_ms,
                )
            )
    return evaluated, class_names


def save_cache(
    images: list[EvaluatedImage], cache: Path, class_names: dict[int, str]
) -> None:
    cache.parent.mkdir(parents=True, exist_ok=True)
    header = {"type": "metadata", "class_names": class_names}
    rows = [json.dumps(header, sort_keys=True)]
    for item in images:
        rows.append(
            json.dumps(
                {
                    "type": "prediction",
                    "image": str(item.image),
                    "split": item.split,
                    "source_dataset": item.source_dataset,
                    "ground_truth": item.ground_truth,
                    "predictions": [
                        {
                            "class_id": prediction.class_id,
                            "label": prediction.label,
                            "confidence": prediction.confidence,
                            "box": prediction.box,
                        }
                        for prediction in item.predictions
                    ],
                    "processing_ms": item.processing_ms,
                },
                sort_keys=True,
            )
        )
    cache.write_text("\n".join(rows) + "\n", encoding="utf-8")


def load_cache(cache: Path) -> tuple[list[EvaluatedImage], dict[int, str]]:
    lines = cache.read_text(encoding="utf-8").splitlines()
    metadata = json.loads(lines[0])
    class_names = {
        int(class_id): str(name)
        for class_id, name in metadata["class_names"].items()
    }
    images: list[EvaluatedImage] = []
    for line in lines[1:]:
        row = json.loads(line)
        images.append(
            EvaluatedImage(
                image=Path(row["image"]),
                split=str(row["split"]),
                source_dataset=str(row["source_dataset"]),
                ground_truth=tuple(tuple(box) for box in row["ground_truth"]),
                predictions=tuple(
                    Prediction(
                        class_id=int(prediction["class_id"]),
                        label=str(prediction["label"]),
                        confidence=float(prediction["confidence"]),
                        box=tuple(prediction["box"]),
                    )
                    for prediction in row["predictions"]
                ),
                processing_ms=float(row["processing_ms"]),
            )
        )
    return images, class_names


def _target_predictions(
    image: EvaluatedImage, class_ids: frozenset[int], confidence: float = 0.0
) -> list[Prediction]:
    return [
        prediction
        for prediction in image.predictions
        if prediction.class_id in class_ids and prediction.confidence >= confidence
    ]


def _match_image(
    ground_truth: Sequence[Box],
    predictions: Sequence[Prediction],
    *,
    iou_threshold: float,
) -> tuple[int, int, int, set[int]]:
    matched_ground_truth: set[int] = set()
    true_positives = 0
    for prediction in sorted(
        predictions, key=lambda value: value.confidence, reverse=True
    ):
        candidates = [
            (box_iou(prediction.box, box), index)
            for index, box in enumerate(ground_truth)
            if index not in matched_ground_truth
        ]
        best_iou, best_index = max(candidates, default=(0.0, -1))
        if best_iou >= iou_threshold:
            matched_ground_truth.add(best_index)
            true_positives += 1
    false_positives = len(predictions) - true_positives
    false_negatives = len(ground_truth) - true_positives
    return true_positives, false_positives, false_negatives, matched_ground_truth


def threshold_metrics(
    images: Sequence[EvaluatedImage],
    class_ids: frozenset[int],
    *,
    confidence: float,
    iou_threshold: float = 0.50,
) -> dict[str, Any]:
    true_positives = false_positives = false_negatives = 0
    positive_images = negative_images = 0
    detected_positive_images = localized_positive_images = 0
    false_positive_images = 0
    label_counts: Counter[str] = Counter()
    size_totals: Counter[str] = Counter()
    size_matches: Counter[str] = Counter()

    for image in images:
        predictions = _target_predictions(image, class_ids, confidence)
        label_counts.update(prediction.label for prediction in predictions)
        tp, fp, fn, matched = _match_image(
            image.ground_truth, predictions, iou_threshold=iou_threshold
        )
        true_positives += tp
        false_positives += fp
        false_negatives += fn
        if image.ground_truth:
            positive_images += 1
            detected_positive_images += bool(predictions)
            localized_positive_images += bool(matched)
            for index, box in enumerate(image.ground_truth):
                area = (box[2] - box[0]) * (box[3] - box[1])
                size = "small" if area < 0.01 else "medium" if area < 0.05 else "large"
                size_totals[size] += 1
                size_matches[size] += index in matched
        else:
            negative_images += 1
            false_positive_images += bool(predictions)

    precision = true_positives / (true_positives + false_positives or 1)
    recall = true_positives / (true_positives + false_negatives or 1)
    f1 = 2 * precision * recall / (precision + recall or 1)
    return {
        "confidence": confidence,
        "iou": iou_threshold,
        "true_positives": true_positives,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "positive_images": positive_images,
        "negative_images": negative_images,
        "positive_image_detection_recall": (
            detected_positive_images / positive_images if positive_images else 0.0
        ),
        "positive_image_localization_recall": (
            localized_positive_images / positive_images if positive_images else 0.0
        ),
        "false_positive_images": false_positive_images,
        "false_positive_image_rate": (
            false_positive_images / negative_images if negative_images else 0.0
        ),
        "negative_image_specificity": (
            1 - false_positive_images / negative_images if negative_images else 0.0
        ),
        "prediction_label_counts": dict(label_counts.most_common()),
        "recall_by_relative_box_size": {
            size: {
                "ground_truth_boxes": size_totals[size],
                "matched_boxes": size_matches[size],
                "recall": size_matches[size] / size_totals[size]
                if size_totals[size]
                else 0.0,
            }
            for size in ("small", "medium", "large")
        },
    }


def _ranked_outcomes(
    images: Sequence[EvaluatedImage],
    class_ids: frozenset[int],
    iou_threshold: float,
) -> tuple[list[float], list[int], list[int], int]:
    ranked: list[tuple[float, int, Prediction]] = []
    total_ground_truth = sum(len(image.ground_truth) for image in images)
    for image_index, image in enumerate(images):
        ranked.extend(
            (prediction.confidence, image_index, prediction)
            for prediction in _target_predictions(image, class_ids)
        )
    ranked.sort(key=lambda value: value[0], reverse=True)
    matched: defaultdict[int, set[int]] = defaultdict(set)
    confidences: list[float] = []
    true_positives: list[int] = []
    false_positives: list[int] = []
    for confidence, image_index, prediction in ranked:
        ground_truth = images[image_index].ground_truth
        candidates = [
            (box_iou(prediction.box, box), index)
            for index, box in enumerate(ground_truth)
            if index not in matched[image_index]
        ]
        best_iou, best_index = max(candidates, default=(0.0, -1))
        is_match = best_iou >= iou_threshold
        if is_match:
            matched[image_index].add(best_index)
        confidences.append(confidence)
        true_positives.append(int(is_match))
        false_positives.append(int(not is_match))
    return confidences, true_positives, false_positives, total_ground_truth


def average_precision(
    images: Sequence[EvaluatedImage],
    class_ids: frozenset[int],
    *,
    iou_threshold: float,
) -> float:
    _, true_positives, false_positives, total_ground_truth = _ranked_outcomes(
        images, class_ids, iou_threshold
    )
    if not total_ground_truth or not true_positives:
        return 0.0
    cumulative_tp = 0
    cumulative_fp = 0
    recalls: list[float] = []
    precisions: list[float] = []
    for tp, fp in zip(true_positives, false_positives, strict=True):
        cumulative_tp += tp
        cumulative_fp += fp
        recalls.append(cumulative_tp / total_ground_truth)
        precisions.append(cumulative_tp / (cumulative_tp + cumulative_fp))
    return sum(
        max(
            (
                precision
                for recall, precision in zip(recalls, precisions, strict=True)
                if recall >= level
            ),
            default=0.0,
        )
        for level in (index / 100 for index in range(101))
    ) / 101


def best_f1_point(
    images: Sequence[EvaluatedImage], class_ids: frozenset[int]
) -> dict[str, float]:
    confidences, true_positives, false_positives, total_ground_truth = (
        _ranked_outcomes(images, class_ids, 0.50)
    )
    cumulative_tp = cumulative_fp = 0
    best = {"confidence": 1.0, "precision": 0.0, "recall": 0.0, "f1": 0.0}
    for confidence, tp, fp in zip(
        confidences, true_positives, false_positives, strict=True
    ):
        cumulative_tp += tp
        cumulative_fp += fp
        precision = cumulative_tp / (cumulative_tp + cumulative_fp)
        recall = cumulative_tp / total_ground_truth if total_ground_truth else 0.0
        f1 = 2 * precision * recall / (precision + recall or 1)
        if f1 > best["f1"]:
            best = {
                "confidence": confidence,
                "precision": precision,
                "recall": recall,
                "f1": f1,
            }
    return best


def classification_confusion(
    images: Sequence[EvaluatedImage], *, confidence: float = 0.10
) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for image in images:
        if not image.ground_truth:
            continue
        for prediction in image.predictions:
            if prediction.confidence < confidence:
                continue
            if any(box_iou(prediction.box, box) >= 0.50 for box in image.ground_truth):
                counts[prediction.label] += 1
    return dict(counts.most_common())


def evaluate_view(
    images: Sequence[EvaluatedImage], class_ids: frozenset[int]
) -> dict[str, Any]:
    ap_by_iou = {
        f"{iou:.2f}": average_precision(images, class_ids, iou_threshold=iou)
        for iou in IOU_THRESHOLDS
    }
    return {
        "images": len(images),
        "ground_truth_boxes": sum(len(image.ground_truth) for image in images),
        "ap50": ap_by_iou["0.50"],
        "map50_95": sum(ap_by_iou.values()) / len(ap_by_iou),
        "ap_by_iou": ap_by_iou,
        "best_f1_at_iou50": best_f1_point(images, class_ids),
        "thresholds": {
            f"{threshold:.2f}": threshold_metrics(
                images, class_ids, confidence=threshold
            )
            for threshold in CONFIDENCE_THRESHOLDS
        },
    }


def build_report(
    images: list[EvaluatedImage], class_names: dict[int, str]
) -> dict[str, Any]:
    splits = ("train", "val", "test", "all")
    views: dict[str, Any] = {}
    for view_name, class_ids in MODEL_VIEWS.items():
        by_split = {}
        for split in splits:
            subset = (
                images if split == "all" else [i for i in images if i.split == split]
            )
            by_split[split] = evaluate_view(subset, class_ids)
        test_images = [image for image in images if image.split == "test"]
        by_source = {
            source: evaluate_view(
                [image for image in test_images if image.source_dataset == source],
                class_ids,
            )
            for source in sorted({image.source_dataset for image in test_images})
        }
        views[view_name] = {
            "class_ids": sorted(class_ids),
            "class_names": [class_names[class_id] for class_id in sorted(class_ids)],
            "by_split": by_split,
            "test_by_source": by_source,
        }

    processing_times = [image.processing_ms for image in images]
    test_images = [image for image in images if image.split == "test"]
    return {
        "dataset": "deer-driver-v1",
        "model_classes": class_names,
        "evaluation": {
            "confidence_floor": 0.001,
            "iou_thresholds": IOU_THRESHOLDS,
            "size_bins_relative_area": {
                "small": "< 1% of image",
                "medium": "1% to < 5% of image",
                "large": ">= 5% of image",
            },
            "primary_split": "test",
        },
        "runtime": {
            "images": len(images),
            "mean_processing_ms": sum(processing_times) / len(processing_times),
            "estimated_images_per_second": len(processing_times)
            / (sum(processing_times) / 1000),
        },
        "views": views,
        "test_ground_truth_overlap_classification_at_confidence_0.10": (
            classification_confusion(test_images)
        ),
        "limitations": [
            (
                "The derived dataset is camera-trap-heavy and does not establish "
                "road-video safety performance."
            ),
            (
                "The model has no generic deer or white-tailed-deer class; "
                "mule_deer is the strict proxy."
            ),
            (
                "The driver_hazard_union view collapses mule_deer, elk, and "
                "moose for safety-oriented analysis."
            ),
            (
                "Potential overlap between the public model's unknown training "
                "data and these sources has not been ruled out."
            ),
            (
                "Negative images were selected from wildlife datasets and are "
                "not representative driving-video negatives."
            ),
        ],
    }


def evaluate_dataset(
    *,
    dataset: Path = DEFAULT_DATASET,
    report_path: Path = DEFAULT_REPORT,
    cache_path: Path = DEFAULT_CACHE,
    batch_size: int = 32,
    confidence_floor: float = 0.001,
    reuse_cache: bool = False,
) -> dict[str, Any]:
    if reuse_cache and cache_path.is_file():
        images, class_names = load_cache(cache_path)
    else:
        ground_truth = load_ground_truth(dataset)
        images, class_names = run_inference(
            ground_truth,
            batch_size=batch_size,
            confidence_floor=confidence_floor,
        )
        save_cache(images, cache_path, class_names)
    report = build_report(images, class_names)
    report["evaluation"]["confidence_floor"] = confidence_floor
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report


def main() -> None:
    args = parse_args()
    report = evaluate_dataset(
        dataset=args.dataset,
        report_path=args.report,
        cache_path=args.cache,
        batch_size=args.batch_size,
        confidence_floor=args.confidence_floor,
        reuse_cache=args.reuse_cache,
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
