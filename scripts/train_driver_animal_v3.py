"""Continue-transfer driver_animal_v2 with reviewed road hard negatives."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from ultralytics import YOLO  # type: ignore[attr-defined]

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INITIAL = PROJECT_ROOT / "storage/models/driver_animal_v2/best.pt"
DEFAULT_DATASET = PROJECT_ROOT / "data/derived/driver-animal-v3/data.yaml"
DEFAULT_NEGATIVES = PROJECT_ROOT / "data/derived/driver-video-hard-negatives-v1"
DEFAULT_OUTPUT = PROJECT_ROOT / "storage/models/driver_animal_v3"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--initial", type=Path, default=DEFAULT_INITIAL)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--hard-negatives", type=Path, default=DEFAULT_NEGATIVES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--epochs", type=int, default=15)
    parser.add_argument("--patience", type=int, default=5)
    parser.add_argument("--image-size", type=int, default=960)
    parser.add_argument("--batch-size", type=int, default=24)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--device", default="0")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--confidence", type=float, default=0.10)
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Reuse output/best.pt and regenerate evaluation/report artifacts.",
    )
    return parser.parse_args()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _metrics(result: Any) -> dict[str, float]:
    return {
        "precision": float(result.box.mp),
        "recall": float(result.box.mr),
        "map50": float(result.box.map50),
        "map50_95": float(result.box.map),
    }


def _evaluate(
    checkpoint: Path,
    *,
    dataset: Path,
    split: str,
    output: Path,
    name: str,
    image_size: int,
    batch_size: int,
    workers: int,
    device: str,
) -> dict[str, float]:
    result = YOLO(checkpoint).val(
        data=str(dataset.resolve()),
        split=split,
        imgsz=image_size,
        batch=batch_size,
        workers=workers,
        device=device,
        conf=0.001,
        iou=0.70,
        plots=False,
        project=str((output / "evaluation").resolve()),
        name=name,
        exist_ok=True,
        verbose=False,
    )
    return _metrics(result)


def _hard_negative_stats(
    checkpoint: Path,
    *,
    root: Path,
    confidence: float,
    image_size: int,
    device: str,
) -> dict[str, int | float]:
    images = sorted((root / "images/train").glob("*"))
    if not images:
        raise FileNotFoundError(f"No hard-negative images found: {root}")
    detections = 0
    images_with_detections = 0
    maximum = 0.0
    results = YOLO(checkpoint).predict(
        source=[str(path) for path in images],
        conf=confidence,
        imgsz=image_size,
        device=device,
        stream=True,
        verbose=False,
    )
    for result in results:
        count = len(result.boxes)
        detections += count
        images_with_detections += int(count > 0)
        if count:
            maximum = max(maximum, float(result.boxes.conf.max().item()))
    return {
        "images": len(images),
        "images_with_detections": images_with_detections,
        "detections": detections,
        "max_confidence": maximum,
    }


def train(args: argparse.Namespace) -> dict[str, Any]:
    args.initial = args.initial.resolve()
    args.dataset = args.dataset.resolve()
    args.hard_negatives = args.hard_negatives.resolve()
    args.output = args.output.resolve()
    if not args.initial.is_file():
        raise FileNotFoundError(f"Initial checkpoint not found: {args.initial}")
    if not args.dataset.is_file():
        raise FileNotFoundError(f"Dataset YAML not found: {args.dataset}")
    if args.output.exists() and not args.report_only:
        raise FileExistsError(f"Output already exists: {args.output}")
    args.output.mkdir(parents=True, exist_ok=args.report_only)

    old_negative_stats = _hard_negative_stats(
        args.initial,
        root=args.hard_negatives,
        confidence=args.confidence,
        image_size=args.image_size,
        device=args.device,
    )
    selected = args.output / "best.pt"
    if args.report_only:
        if not selected.is_file():
            raise FileNotFoundError(f"Report-only checkpoint not found: {selected}")
    else:
        model = YOLO(args.initial)
        trained = model.train(
            data=str(args.dataset),
            epochs=args.epochs,
            patience=args.patience,
            imgsz=args.image_size,
            batch=args.batch_size,
            workers=args.workers,
            device=args.device,
            seed=args.seed,
            deterministic=True,
            project=str((args.output / "runs").resolve()),
            name="continued_960",
            exist_ok=False,
            optimizer="AdamW",
            lr0=0.0003,
            weight_decay=0.0005,
            close_mosaic=5,
            mosaic=0.3,
            hsv_v=0.5,
            plots=True,
            save=True,
            verbose=True,
        )
        run_checkpoint = Path(trained.save_dir) / "weights/best.pt"
        if not run_checkpoint.is_file():
            raise FileNotFoundError(
                f"Training did not produce best.pt: {run_checkpoint}"
            )
        shutil.copy2(run_checkpoint, selected)

    comparisons: dict[str, dict[str, dict[str, float]]] = {"old": {}, "new": {}}
    for label, checkpoint in (("old", args.initial), ("new", selected)):
        for split in ("val", "test"):
            comparisons[label][split] = _evaluate(
                checkpoint,
                dataset=args.dataset,
                split=split,
                output=args.output,
                name=f"{label}_{split}",
                image_size=args.image_size,
                batch_size=args.batch_size,
                workers=args.workers,
                device=args.device,
            )

    new_negative_stats = _hard_negative_stats(
        selected,
        root=args.hard_negatives,
        confidence=args.confidence,
        image_size=args.image_size,
        device=args.device,
    )
    summary: dict[str, Any] = {
        "checkpoint": str(selected.relative_to(PROJECT_ROOT)),
        "checkpoint_sha256": _sha256(selected),
        "initial_checkpoint": str(args.initial.relative_to(PROJECT_ROOT)),
        "dataset": str(args.dataset.relative_to(PROJECT_ROOT)),
        "class_names": ["animal"],
        "settings": {
            "epochs": args.epochs,
            "patience": args.patience,
            "image_size": args.image_size,
            "batch_size": args.batch_size,
            "learning_rate": 0.0003,
            "optimizer": "AdamW",
            "seed": args.seed,
        },
        "validation_and_test_comparison": comparisons,
        "reviewed_hard_negative_comparison": {
            "confidence": args.confidence,
            "old": old_negative_stats,
            "new": new_negative_stats,
            "warning": (
                "These are training hard negatives and measure targeted correction, "
                "not generalization."
            ),
        },
    }
    (args.output / "training_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


def main() -> None:
    summary = train(parse_args())
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
