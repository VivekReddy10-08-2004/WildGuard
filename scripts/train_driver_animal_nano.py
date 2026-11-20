"""Fine-tune and benchmark a YOLO26n driver-animal detector."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from ultralytics import YOLO  # type: ignore[attr-defined]

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INITIAL = PROJECT_ROOT / "yolo26n.pt"
DEFAULT_DATASET = PROJECT_ROOT / "data/derived/driver-animal-v3/data.yaml"
DEFAULT_OUTPUT = PROJECT_ROOT / "storage/models/driver_animal_nano"
DEFAULT_BASELINE = PROJECT_ROOT / "storage/models/driver_animal_v2/best.pt"
DEFAULT_NEGATIVES = PROJECT_ROOT / "data/derived/driver-video-hard-negatives-v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--initial", type=Path, default=DEFAULT_INITIAL)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--hard-negatives", type=Path, default=DEFAULT_NEGATIVES)
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--patience", type=int, default=10)
    parser.add_argument("--image-size", type=int, default=960)
    parser.add_argument("--batch-size", type=int, default=48)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--device", default="0")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--confidence", type=float, default=0.10)
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Reuse output/best.pt and regenerate benchmark artifacts.",
    )
    return parser.parse_args()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path.resolve())


def _metrics(result: Any) -> dict[str, float]:
    return {
        "precision": float(result.box.mp),
        "recall": float(result.box.mr),
        "map50": float(result.box.map50),
        "map50_95": float(result.box.map),
        "preprocess_ms_per_image": float(result.speed["preprocess"]),
        "inference_ms_per_image": float(result.speed["inference"]),
        "postprocess_ms_per_image": float(result.speed["postprocess"]),
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
        data=str(dataset),
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


def _load_initial(path: Path) -> tuple[YOLO, Path]:
    resolved = path.resolve()
    if resolved.is_file():
        return YOLO(resolved), resolved
    if path.name != "yolo26n.pt":
        raise FileNotFoundError(f"Initial checkpoint not found: {path}")
    model = YOLO(path.name)
    downloaded = (Path.cwd() / path.name).resolve()
    if not downloaded.is_file():
        raise FileNotFoundError(
            f"Ultralytics did not download the expected checkpoint: {downloaded}"
        )
    return model, downloaded


def train(args: argparse.Namespace) -> dict[str, Any]:
    dataset = args.dataset.resolve()
    output = args.output.resolve()
    baseline = args.baseline.resolve()
    negatives = args.hard_negatives.resolve()
    if not dataset.is_file():
        raise FileNotFoundError(f"Dataset YAML not found: {dataset}")
    if not baseline.is_file():
        raise FileNotFoundError(f"Baseline checkpoint not found: {baseline}")
    if output.exists() and not args.report_only:
        raise FileExistsError(f"Output already exists: {output}")
    output.mkdir(parents=True, exist_ok=args.report_only)

    selected = output / "best.pt"
    if args.report_only:
        if not selected.is_file():
            raise FileNotFoundError(f"Report-only checkpoint not found: {selected}")
        initial = args.initial.resolve()
    else:
        model, initial = _load_initial(args.initial)
        trained = model.train(
            data=str(dataset),
            epochs=args.epochs,
            patience=args.patience,
            imgsz=args.image_size,
            batch=args.batch_size,
            workers=args.workers,
            device=args.device,
            seed=args.seed,
            deterministic=True,
            project=str((output / "runs").resolve()),
            name="coco_init_960",
            exist_ok=False,
            optimizer="AdamW",
            lr0=0.001,
            weight_decay=0.0005,
            close_mosaic=10,
            mosaic=0.5,
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

    comparison: dict[str, dict[str, dict[str, float]]] = {
        "yolo26s_v2": {},
        "yolo26n": {},
    }
    for label, checkpoint in (("yolo26s_v2", baseline), ("yolo26n", selected)):
        for split in ("val", "test"):
            comparison[label][split] = _evaluate(
                checkpoint,
                dataset=dataset,
                split=split,
                output=output,
                name=f"{label}_{split}",
                image_size=args.image_size,
                batch_size=args.batch_size,
                workers=args.workers,
                device=args.device,
            )

    selected_model = YOLO(selected)
    summary: dict[str, Any] = {
        "checkpoint": _relative(selected),
        "checkpoint_sha256": _sha256(selected),
        "initial_checkpoint": _relative(initial),
        "dataset": _relative(dataset),
        "class_names": ["animal"],
        "architecture": "YOLO26n",
        "parameters": sum(
            parameter.numel() for parameter in selected_model.model.parameters()
        ),
        "checkpoint_bytes": selected.stat().st_size,
        "settings": {
            "epochs": args.epochs,
            "patience": args.patience,
            "image_size": args.image_size,
            "batch_size": args.batch_size,
            "learning_rate": 0.001,
            "optimizer": "AdamW",
            "seed": args.seed,
        },
        "validation_and_test_comparison": comparison,
        "reviewed_hard_negative_results": {
            "confidence": args.confidence,
            "result": _hard_negative_stats(
                selected,
                root=negatives,
                confidence=args.confidence,
                image_size=args.image_size,
                device=args.device,
            ),
            "warning": (
                "These frames are part of training and measure targeted correction, "
                "not generalization."
            ),
        },
    }
    (output / "training_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


def main() -> None:
    print(json.dumps(train(parse_args()), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
