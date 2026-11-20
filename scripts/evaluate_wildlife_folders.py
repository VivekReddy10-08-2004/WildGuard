"""Evaluate wildlife detection against a species-folder image dataset."""

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Any

from model_services.image import WildlifeDetector
from shared.contracts import ImagePrediction

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
OREGON_LABEL_MAP = {
    "bald_eagle": "bald_eagle",
    "black_bear": "black_bear",
    "bobcat": "bobcat",
    "columbian_black-tailed_deer": "mule_deer",
    "cougar": "mountain_lion",
    "coyote": "coyote",
    "elk": "elk",
    "gray_wolf": "gray_wolf",
    "raven": "raven",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path, help="Directory containing class folders")
    parser.add_argument("--samples-per-class", type=int, default=25)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--confidence", type=float, default=0.25)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--label-map",
        action="append",
        type=parse_label_mapping,
        metavar="DATASET_LABEL=MODEL_LABEL",
        help="Override the default Oregon class mapping; may be repeated",
    )
    return parser.parse_args()


def parse_label_mapping(value: str) -> tuple[str, str]:
    try:
        dataset_label, model_label = value.split("=", maxsplit=1)
    except ValueError as error:
        raise argparse.ArgumentTypeError("mapping must use DATASET=MODEL") from error
    if not dataset_label or not model_label:
        raise argparse.ArgumentTypeError("mapping labels cannot be empty")
    return dataset_label, model_label


def collect_samples(
    dataset: Path,
    *,
    label_map: dict[str, str],
    samples_per_class: int,
    seed: int,
) -> list[tuple[Path, str, str]]:
    rng = random.Random(seed)
    samples: list[tuple[Path, str, str]] = []

    for dataset_label, model_label in label_map.items():
        class_dir = dataset / dataset_label
        if not class_dir.is_dir():
            continue

        images = sorted(
            path
            for path in class_dir.iterdir()
            if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
        )
        chosen = rng.sample(images, min(samples_per_class, len(images)))
        samples.extend((path, dataset_label, model_label) for path in chosen)

    return samples


def evaluate(
    detector: WildlifeDetector,
    samples: list[tuple[Path, str, str]],
    *,
    batch_size: int,
    confidence: float,
) -> dict[str, Any]:
    class_counts: defaultdict[str, dict[str, int]] = defaultdict(
        lambda: {
            "images": 0,
            "any_detection": 0,
            "target_detected": 0,
            "top1_correct": 0,
        }
    )

    for start in range(0, len(samples), batch_size):
        batch = samples[start : start + batch_size]
        predictions = detector.predict(
            [path for path, _, _ in batch],
            confidence=confidence,
        )
        if len(predictions) != len(batch):
            raise RuntimeError("model returned an unexpected number of predictions")

        for (_, dataset_label, expected_label), prediction in zip(
            batch, predictions, strict=True
        ):
            _record_prediction(
                class_counts[dataset_label], prediction, expected_label
            )

    per_class = {
        label: _with_rates(counts) for label, counts in sorted(class_counts.items())
    }
    totals = {
        key: sum(counts[key] for counts in class_counts.values())
        for key in ("images", "any_detection", "target_detected", "top1_correct")
    }
    return {
        "confidence": confidence,
        "model_classes_evaluated": len(per_class),
        "overall": _with_rates(totals),
        "per_class": per_class,
    }


def _record_prediction(
    counts: dict[str, int], prediction: ImagePrediction, expected_label: str
) -> None:
    counts["images"] += 1
    if not prediction.detections:
        return

    counts["any_detection"] += 1
    if any(item.label == expected_label for item in prediction.detections):
        counts["target_detected"] += 1

    top_detection = max(prediction.detections, key=lambda item: item.confidence)
    if top_detection.label == expected_label:
        counts["top1_correct"] += 1


def _with_rates(counts: dict[str, int]) -> dict[str, int | float]:
    images = counts["images"]
    result: dict[str, int | float] = dict(counts)
    result["detection_rate"] = counts["any_detection"] / images if images else 0.0
    result["target_detection_rate"] = (
        counts["target_detected"] / images if images else 0.0
    )
    result["top1_accuracy"] = counts["top1_correct"] / images if images else 0.0
    return result


def main() -> None:
    args = parse_args()
    label_map = dict(args.label_map) if args.label_map else OREGON_LABEL_MAP
    samples = collect_samples(
        args.dataset,
        label_map=label_map,
        samples_per_class=args.samples_per_class,
        seed=args.seed,
    )
    if not samples:
        raise SystemExit("No mapped image classes were found in the dataset")

    report = evaluate(
        WildlifeDetector(),
        samples,
        batch_size=args.batch_size,
        confidence=args.confidence,
    )
    rendered = json.dumps(report, indent=2)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(f"{rendered}\n", encoding="utf-8")


if __name__ == "__main__":
    main()
