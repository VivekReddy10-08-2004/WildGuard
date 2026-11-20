"""Fine-tune one-class animal detectors on deer-positive driver data."""

from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ultralytics import YOLO  # type: ignore[attr-defined]

from model_services.image.wildlife_detector import DEFAULT_MODEL_DIR, MODEL_FILENAME

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = PROJECT_ROOT / "data" / "derived" / "deer-driver-v1" / "data.yaml"
DEFAULT_OUTPUT = PROJECT_ROOT / "storage" / "models" / "driver_animal"
WILDLIFE_WEIGHTS = DEFAULT_MODEL_DIR / MODEL_FILENAME
COCO_WEIGHTS = PROJECT_ROOT / "yolo26s.pt"


@dataclass(frozen=True)
class ValidationResult:
    initialization: str
    checkpoint: Path
    precision: float
    recall: float
    map50: float
    map50_95: float

    def as_dict(self) -> dict[str, str | float]:
        return {
            "initialization": self.initialization,
            "checkpoint": str(self.checkpoint),
            "precision": self.precision,
            "recall": self.recall,
            "map50": self.map50,
            "map50_95": self.map50_95,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--initialization",
        choices=("wildlife", "coco", "both"),
        default="both",
    )
    parser.add_argument("--epochs", type=int, default=60)
    parser.add_argument("--patience", type=int, default=12)
    parser.add_argument("--image-size", type=int, default=640)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--device", default="0")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Train one epoch on 10%% of training data and skip test evaluation",
    )
    return parser.parse_args()


def choose_best(results: list[ValidationResult]) -> ValidationResult:
    if not results:
        raise ValueError("At least one validation result is required")
    return max(
        results,
        key=lambda result: (result.map50_95, result.map50, result.recall),
    )


def _metric_summary(metrics: Any) -> dict[str, float]:
    return {
        "precision": float(metrics.box.mp),
        "recall": float(metrics.box.mr),
        "map50": float(metrics.box.map50),
        "map50_95": float(metrics.box.map),
    }


def _resolve_coco_weights() -> Path:
    if COCO_WEIGHTS.is_file():
        return COCO_WEIGHTS
    YOLO(COCO_WEIGHTS.name)
    if not COCO_WEIGHTS.is_file():
        raise FileNotFoundError(
            f"Ultralytics did not download the expected checkpoint: {COCO_WEIGHTS}"
        )
    return COCO_WEIGHTS


def _initialization_weights(initialization: str) -> Path:
    if initialization == "wildlife":
        if not WILDLIFE_WEIGHTS.is_file():
            raise FileNotFoundError(
                f"Wildlife checkpoint not found: {WILDLIFE_WEIGHTS}"
            )
        return WILDLIFE_WEIGHTS
    if initialization == "coco":
        return _resolve_coco_weights()
    raise ValueError(f"Unknown initialization: {initialization}")


def train_one(
    initialization: str,
    *,
    dataset: Path,
    output: Path,
    epochs: int,
    patience: int,
    image_size: int,
    batch_size: int,
    workers: int,
    device: str,
    seed: int,
    smoke_test: bool,
) -> ValidationResult:
    weights = _initialization_weights(initialization)
    run_name = (
        f"{initialization}_init_smoke" if smoke_test else f"{initialization}_init"
    )
    run_dir = output / "runs" / run_name
    if run_dir.exists():
        raise FileExistsError(
            "Training run already exists; move or remove it before rerunning: "
            f"{run_dir}"
        )

    model = YOLO(weights)
    train_metrics = model.train(
        data=str(dataset.resolve()),
        epochs=1 if smoke_test else epochs,
        patience=patience,
        imgsz=image_size,
        batch=batch_size,
        workers=workers,
        device=device,
        seed=seed,
        deterministic=True,
        project=str((output / "runs").resolve()),
        name=run_name,
        exist_ok=False,
        fraction=0.10 if smoke_test else 1.0,
        optimizer="auto",
        close_mosaic=10,
        plots=True,
        save=True,
        verbose=True,
    )
    checkpoint = Path(train_metrics.save_dir) / "weights" / "best.pt"
    if not checkpoint.is_file():
        raise FileNotFoundError(f"Training did not produce best.pt: {checkpoint}")

    validation = YOLO(checkpoint).val(
        data=str(dataset.resolve()),
        split="val",
        imgsz=image_size,
        batch=batch_size,
        workers=workers,
        device=device,
        conf=0.001,
        iou=0.70,
        plots=True,
        project=str((output / "validation").resolve()),
        name=run_name,
        exist_ok=False,
        verbose=True,
    )
    metrics = _metric_summary(validation)
    return ValidationResult(
        initialization=initialization,
        checkpoint=checkpoint,
        **metrics,
    )


def evaluate_test(
    result: ValidationResult,
    *,
    dataset: Path,
    output: Path,
    image_size: int,
    batch_size: int,
    workers: int,
    device: str,
) -> dict[str, float]:
    metrics = YOLO(result.checkpoint).val(
        data=str(dataset.resolve()),
        split="test",
        imgsz=image_size,
        batch=batch_size,
        workers=workers,
        device=device,
        conf=0.001,
        iou=0.70,
        plots=True,
        project=str((output / "test").resolve()),
        name=f"selected_{result.initialization}_init",
        exist_ok=False,
        verbose=True,
    )
    return _metric_summary(metrics)


def train_and_compare(args: argparse.Namespace) -> dict[str, Any]:
    if not args.dataset.is_file():
        raise FileNotFoundError(f"Dataset YAML not found: {args.dataset}")
    args.output.mkdir(parents=True, exist_ok=True)
    initializations = (
        ("wildlife", "coco")
        if args.initialization == "both"
        else (args.initialization,)
    )

    validation_results = [
        train_one(
            initialization,
            dataset=args.dataset,
            output=args.output,
            epochs=args.epochs,
            patience=args.patience,
            image_size=args.image_size,
            batch_size=args.batch_size,
            workers=args.workers,
            device=args.device,
            seed=args.seed,
            smoke_test=args.smoke_test,
        )
        for initialization in initializations
    ]
    selected = choose_best(validation_results)
    test_metrics = (
        None
        if args.smoke_test
        else evaluate_test(
            selected,
            dataset=args.dataset,
            output=args.output,
            image_size=args.image_size,
            batch_size=args.batch_size,
            workers=args.workers,
            device=args.device,
        )
    )

    selected_checkpoint = args.output / "best.pt"
    if not args.smoke_test:
        shutil.copy2(selected.checkpoint, selected_checkpoint)
    summary: dict[str, Any] = {
        "dataset": str(args.dataset.resolve()),
        "class_names": ["animal"],
        "selection_metric": "validation map50_95",
        "settings": {
            "epochs": 1 if args.smoke_test else args.epochs,
            "patience": args.patience,
            "image_size": args.image_size,
            "batch_size": args.batch_size,
            "seed": args.seed,
            "smoke_test": args.smoke_test,
        },
        "validation_results": [result.as_dict() for result in validation_results],
        "selected_initialization": selected.initialization,
        "selected_source_checkpoint": str(selected.checkpoint),
        "selected_checkpoint": (
            str(selected_checkpoint) if not args.smoke_test else None
        ),
        "selected_test_metrics": test_metrics,
    }
    summary_name = "smoke_summary.json" if args.smoke_test else "training_summary.json"
    (args.output / summary_name).write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


def main() -> None:
    args = parse_args()
    summary = train_and_compare(args)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
