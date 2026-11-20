"""Combine the frozen deer-driver benchmark with training-only hard examples."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any

SPLITS = ("train", "val", "test")
DEFAULT_HARD_EXAMPLES = (
    Path("data/derived/driver-video-hard-examples-v1"),
    Path("data/derived/driver-video-hard-examples-oh-deer-v1"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base",
        type=Path,
        default=Path("data/derived/deer-driver-v1"),
        help="Frozen dataset providing train, validation, and test splits",
    )
    parser.add_argument(
        "--hard-examples",
        type=Path,
        action="append",
        help=(
            "Training-only YOLO supplement; repeat for multiple datasets. "
            "By default, both reviewed driving-video supplements are used."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/derived/driver-animal-v2"),
        help="New combined dataset directory; it must not already exist",
    )
    parser.add_argument(
        "--dataset-name",
        default="driver-animal-v2",
        help="Name recorded in generated metadata and documentation",
    )
    return parser.parse_args()


def load_manifest(root: Path) -> list[dict[str, Any]]:
    path = root / "manifest.jsonl"
    if not path.is_file():
        raise FileNotFoundError(f"Dataset manifest not found: {path}")
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"Invalid JSON at {path}:{line_number}") from error
        if not isinstance(row, dict):
            raise ValueError(f"Manifest row is not an object: {path}:{line_number}")
        rows.append(row)
    return rows


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _box_count(label_path: Path) -> int:
    count = 0
    for line_number, line in enumerate(
        label_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        parts = line.split()
        if len(parts) != 5 or parts[0] != "0":
            raise ValueError(f"Malformed YOLO label: {label_path}:{line_number}")
        values = [float(value) for value in parts[1:]]
        if not all(0.0 <= value <= 1.0 for value in values):
            raise ValueError(f"Out-of-range YOLO label: {label_path}:{line_number}")
        if values[2] <= 0.0 or values[3] <= 0.0:
            raise ValueError(f"Empty YOLO box: {label_path}:{line_number}")
        count += 1
    return count


def _source_paths(root: Path, row: dict[str, Any]) -> tuple[Path, Path, str]:
    image_value = row.get("derived_image")
    label_value = row.get("derived_label")
    split = row.get("split")
    if not isinstance(image_value, str) or not isinstance(label_value, str):
        raise ValueError(f"Manifest row lacks derived paths: {row}")
    if split not in SPLITS:
        raise ValueError(f"Manifest row has invalid split: {split!r}")
    image_path = root / image_value
    label_path = root / label_value
    if not image_path.is_file():
        raise FileNotFoundError(f"Manifest image not found: {image_path}")
    if not label_path.is_file():
        raise FileNotFoundError(f"Manifest label not found: {label_path}")
    return image_path, label_path, split


def _link(source: Path, destination: Path) -> None:
    relative_target = os.path.relpath(source.resolve(), destination.parent)
    destination.symlink_to(relative_target)


def derive(
    *,
    base: Path,
    hard_examples: Path | Sequence[Path],
    output: Path,
    dataset_name: str = "driver-animal-v2",
) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(
            f"Output already exists; choose a new path or remove it first: {output}"
        )
    base_rows = load_manifest(base)
    hard_roots = (
        [hard_examples] if isinstance(hard_examples, Path) else list(hard_examples)
    )
    if not hard_roots:
        raise ValueError("At least one hard-example dataset is required")
    if len({root.name for root in hard_roots}) != len(hard_roots):
        raise ValueError("Hard-example dataset directory names must be unique")
    hard_manifests = [(root, load_manifest(root)) for root in hard_roots]
    if any(row.get("split") != "train" for _, rows in hard_manifests for row in rows):
        raise ValueError("Every hard-example row must be training-only")

    for split in SPLITS:
        (output / "images" / split).mkdir(parents=True)
        (output / "labels" / split).mkdir(parents=True)

    combined_rows: list[dict[str, Any]] = []
    used_names: set[tuple[str, str]] = set()
    components = [(base.name, "base", base, base_rows)]
    components.extend(
        (root.name, f"hard_{index:02d}", root, rows)
        for index, (root, rows) in enumerate(hard_manifests, start=1)
    )
    for component_name, prefix, root, rows in components:
        for row in rows:
            source_image, source_label, split = _source_paths(root, row)
            stem = f"{prefix}__{source_image.stem}"
            name_key = (split, stem)
            if name_key in used_names:
                raise ValueError(f"Duplicate derived name in {split}: {stem}")
            used_names.add(name_key)

            image_path = output / "images" / split / f"{stem}{source_image.suffix}"
            label_path = output / "labels" / split / f"{stem}.txt"
            _link(source_image, image_path)
            _link(source_label, label_path)
            boxes = _box_count(source_label)
            image_hash = row.get("sha256")
            if not isinstance(image_hash, str):
                image_hash = _sha256(source_image)

            combined_row = dict(row)
            combined_row.update(
                {
                    "component_dataset": component_name,
                    "component_image": row["derived_image"],
                    "component_label": row["derived_label"],
                    "derived_image": image_path.relative_to(output).as_posix(),
                    "derived_label": label_path.relative_to(output).as_posix(),
                    "sha256": image_hash,
                    "box_count": boxes,
                    "is_positive": boxes > 0,
                }
            )
            combined_rows.append(combined_row)

    hash_splits: defaultdict[str, set[str]] = defaultdict(set)
    for row in combined_rows:
        hash_splits[str(row["sha256"])].add(str(row["split"]))
    crossing_hashes = {
        digest: sorted(splits)
        for digest, splits in hash_splits.items()
        if len(splits) > 1
    }
    if crossing_hashes:
        raise ValueError(f"Exact image content crosses splits: {crossing_hashes}")

    by_split: dict[str, dict[str, int]] = {}
    for split in SPLITS:
        rows = [row for row in combined_rows if row["split"] == split]
        by_split[split] = {
            "images": len(rows),
            "positive_images": sum(bool(row["is_positive"]) for row in rows),
            "negative_images": sum(not bool(row["is_positive"]) for row in rows),
            "boxes": sum(int(row["box_count"]) for row in rows),
        }
    by_component: dict[str, dict[str, int]] = {}
    for component_name, _, _, _ in components:
        rows = [
            row for row in combined_rows if row["component_dataset"] == component_name
        ]
        by_component[component_name] = {
            "images": len(rows),
            "boxes": sum(int(row["box_count"]) for row in rows),
        }

    summary: dict[str, Any] = {
        "dataset": dataset_name,
        "class_names": ["animal"],
        "policy": {
            "base_validation_and_test_frozen": True,
            "hard_examples_split": "train",
            "hard_example_datasets": [root.name for root in hard_roots],
            "video_groups_crossing_splits": 0,
        },
        "totals": {
            "images": len(combined_rows),
            "positive_images": sum(bool(row["is_positive"]) for row in combined_rows),
            "negative_images": sum(
                not bool(row["is_positive"]) for row in combined_rows
            ),
            "boxes": sum(int(row["box_count"]) for row in combined_rows),
        },
        "by_split": by_split,
        "by_component": by_component,
        "validation": {
            "content_hashes_crossing_splits": 0,
            "base_validation_images": by_split["val"]["images"],
            "base_test_images": by_split["test"]["images"],
        },
        "limitations": [
            "Only manually reviewed road-video examples are added to training.",
            "Source encounters used for training cannot evaluate the resulting model.",
            "Independent road/night validation and test videos are still required.",
        ],
    }
    (output / "manifest.jsonl").write_text(
        "".join(
            json.dumps(row, sort_keys=True) + "\n"
            for row in sorted(
                combined_rows,
                key=lambda item: (
                    str(item["split"]),
                    str(item["component_dataset"]),
                    str(item["derived_image"]),
                ),
            )
        ),
        encoding="utf-8",
    )
    (output / "data.yaml").write_text(
        f"path: {output.resolve().as_posix()}\n"
        "train: images/train\n"
        "val: images/val\n"
        "test: images/test\n\n"
        "names:\n"
        "  0: animal\n",
        encoding="utf-8",
    )
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output / "README.md").write_text(
        f"# {dataset_name} (derived)\n\n"
        "This generated one-class YOLO dataset preserves every deer-driver-v1 "
        "validation and test sample and adds reviewed road-video hard examples "
        "only to training. Class `0` is `animal`. See `manifest.jsonl` for "
        "component and source provenance and `summary.json` for validation.\n\n"
        "The Tesla encounter is part of training and must not be used to report "
        "generalization. Independent road/night videos remain required.\n",
        encoding="utf-8",
    )
    return summary


def main() -> None:
    args = parse_args()
    summary = derive(
        base=args.base,
        hard_examples=args.hard_examples or DEFAULT_HARD_EXAMPLES,
        output=args.output,
        dataset_name=args.dataset_name,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
