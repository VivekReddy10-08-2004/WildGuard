"""Evaluate a YOLO checkpoint on a balanced sample from a derived dataset."""

from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Any

import cv2  # type: ignore[import-untyped]
import numpy as np
from ultralytics import YOLO  # type: ignore[attr-defined]

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = PROJECT_ROOT / "data/derived/driver-animal-v3"
DEFAULT_MODEL = PROJECT_ROOT / "storage/models/driver_animal_nano/best.pt"
DEFAULT_OUTPUT = PROJECT_ROOT / "storage/evidence/nano_image_samples"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--split", default="test")
    parser.add_argument("--positives-per-source", type=int, default=4)
    parser.add_argument("--negatives-per-source", type=int, default=2)
    parser.add_argument("--confidence", type=float, default=0.25)
    parser.add_argument("--iou", type=float, default=0.50)
    parser.add_argument("--image-size", type=int, default=960)
    parser.add_argument("--device", default="0")
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def _load_rows(dataset: Path, split: str) -> list[dict[str, Any]]:
    manifest = dataset / "manifest.jsonl"
    if not manifest.is_file():
        raise FileNotFoundError(f"Dataset manifest not found: {manifest}")
    return [
        row
        for line in manifest.read_text(encoding="utf-8").splitlines()
        if (row := json.loads(line))["split"] == split
    ]


def _select_rows(
    rows: list[dict[str, Any]],
    *,
    positives_per_source: int,
    negatives_per_source: int,
    seed: int,
) -> list[dict[str, Any]]:
    groups: dict[tuple[str, bool], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(str(row["source_dataset"]), bool(row["is_positive"]))].append(row)

    selected: list[dict[str, Any]] = []
    generator = random.Random(seed)
    for key in sorted(groups):
        candidates = sorted(groups[key], key=lambda row: str(row["sha256"]))
        count = positives_per_source if key[1] else negatives_per_source
        selected.extend(generator.sample(candidates, min(count, len(candidates))))
    return sorted(
        selected,
        key=lambda row: (
            not bool(row["is_positive"]),
            str(row["source_dataset"]),
            str(row["source_image_id"]),
        ),
    )


def _ground_truth(dataset: Path, row: dict[str, Any]) -> list[list[float]]:
    label = dataset / str(row["derived_label"])
    boxes: list[list[float]] = []
    for line in label.read_text(encoding="utf-8").splitlines():
        _, x_center, y_center, width, height = (float(value) for value in line.split())
        boxes.append(
            [
                x_center - width / 2,
                y_center - height / 2,
                x_center + width / 2,
                y_center + height / 2,
            ]
        )
    return boxes


def _iou(left: list[float], right: list[float]) -> float:
    intersection_width = max(0.0, min(left[2], right[2]) - max(left[0], right[0]))
    intersection_height = max(0.0, min(left[3], right[3]) - max(left[1], right[1]))
    intersection = intersection_width * intersection_height
    left_area = max(0.0, left[2] - left[0]) * max(0.0, left[3] - left[1])
    right_area = max(0.0, right[2] - right[0]) * max(0.0, right[3] - right[1])
    union = left_area + right_area - intersection
    return intersection / union if union else 0.0


def _match(
    ground_truth: list[list[float]],
    predictions: list[list[float]],
    threshold: float,
) -> tuple[int, int, int]:
    matched: set[int] = set()
    true_positives = 0
    for prediction in predictions:
        candidates = [
            (_iou(prediction, box), index)
            for index, box in enumerate(ground_truth)
            if index not in matched
        ]
        best_iou, best_index = max(candidates, default=(0.0, -1))
        if best_iou >= threshold:
            matched.add(best_index)
            true_positives += 1
    return (
        true_positives,
        len(predictions) - true_positives,
        len(ground_truth) - true_positives,
    )


def _gallery(images: list[tuple[np.ndarray, str]], output: Path) -> None:
    cell_width, cell_height = 480, 360
    columns = 4
    rows = (len(images) + columns - 1) // columns
    canvas = np.zeros((rows * cell_height, columns * cell_width, 3), dtype=np.uint8)
    for index, (image, caption) in enumerate(images):
        image_height, image_width = image.shape[:2]
        scale = min(cell_width / image_width, (cell_height - 34) / image_height)
        resized = cv2.resize(
            image,
            (round(image_width * scale), round(image_height * scale)),
            interpolation=cv2.INTER_AREA,
        )
        row, column = divmod(index, columns)
        x = column * cell_width + (cell_width - resized.shape[1]) // 2
        y = row * cell_height + 34 + (cell_height - 34 - resized.shape[0]) // 2
        canvas[y : y + resized.shape[0], x : x + resized.shape[1]] = resized
        cv2.putText(
            canvas,
            caption,
            (column * cell_width + 8, row * cell_height + 24),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.52,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
    cv2.imwrite(str(output), canvas)


def evaluate(args: argparse.Namespace) -> dict[str, Any]:
    dataset = args.dataset.resolve()
    model_path = args.model.resolve()
    output = args.output.resolve()
    if not model_path.is_file():
        raise FileNotFoundError(f"Model not found: {model_path}")
    if output.exists():
        raise FileExistsError(f"Output already exists: {output}")
    output.mkdir(parents=True)
    predictions_dir = output / "predictions"
    predictions_dir.mkdir()

    selected = _select_rows(
        _load_rows(dataset, args.split),
        positives_per_source=args.positives_per_source,
        negatives_per_source=args.negatives_per_source,
        seed=args.seed,
    )
    sources = [str(dataset / str(row["derived_image"])) for row in selected]
    results = YOLO(model_path).predict(
        source=sources,
        conf=args.confidence,
        iou=0.70,
        imgsz=args.image_size,
        device=args.device,
        verbose=False,
    )

    records: list[dict[str, Any]] = []
    gallery: list[tuple[np.ndarray, str]] = []
    totals = {"true_positives": 0, "false_positives": 0, "false_negatives": 0}
    for index, (row, result) in enumerate(zip(selected, results, strict=True)):
        ground_truth = _ground_truth(dataset, row)
        predicted = result.boxes.xyxyn.cpu().tolist()
        true_positives, false_positives, false_negatives = _match(
            ground_truth, predicted, args.iou
        )
        totals["true_positives"] += true_positives
        totals["false_positives"] += false_positives
        totals["false_negatives"] += false_negatives
        annotated = result.plot()
        filename = f"{index + 1:02d}_{Path(str(row['derived_image'])).name}"
        cv2.imwrite(str(predictions_dir / filename), annotated)
        status = f"TP {true_positives} FP {false_positives} FN {false_negatives}"
        gallery.append(
            (
                annotated,
                f"{row['source_dataset']} | {status}",
            )
        )
        records.append(
            {
                "image": str(row["derived_image"]),
                "source_dataset": row["source_dataset"],
                "source_labels": row["source_labels"],
                "is_positive": row["is_positive"],
                "ground_truth_boxes": len(ground_truth),
                "predictions": len(predicted),
                "true_positives": true_positives,
                "false_positives": false_positives,
                "false_negatives": false_negatives,
                "max_confidence": (
                    float(result.boxes.conf.max().item()) if len(result.boxes) else 0.0
                ),
            }
        )

    precision = totals["true_positives"] / (
        totals["true_positives"] + totals["false_positives"] or 1
    )
    recall = totals["true_positives"] / (
        totals["true_positives"] + totals["false_negatives"] or 1
    )
    summary = {
        "model": str(model_path),
        "dataset": str(dataset),
        "split": args.split,
        "selection_seed": args.seed,
        "confidence": args.confidence,
        "iou": args.iou,
        "sample_images": len(records),
        "totals": {**totals, "precision": precision, "recall": recall},
        "images": records,
    }
    (output / "report.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _gallery(gallery, output / "gallery.jpg")
    return summary


def main() -> None:
    print(json.dumps(evaluate(parse_args()), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
