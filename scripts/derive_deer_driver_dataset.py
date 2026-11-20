"""Derive a one-class animal YOLO view from deer-positive source data."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
DEER_CLASS_ID = 0
ENA_DEER_LABEL = "White_Tailed_Deer"
ALBERTA_CLASS_NAMES = (
    "Black bear",
    "Cougar",
    "Cow",
    "Coyote",
    "Dog",
    "Elk",
    "Horse",
    "Human",
    "Moose",
    "Mule deer",
    "Sandhill crane",
    "Vehicle",
    "White-tailed deer",
)
ALBERTA_DEER_CLASS_IDS = {9, 12}
SPLIT_RATIOS = {"train": 0.70, "val": 0.15, "test": 0.15}


@dataclass(frozen=True)
class Box:
    """A normalized YOLO bounding box."""

    x_center: float
    y_center: float
    width: float
    height: float

    def as_yolo(self) -> str:
        return (
            f"{DEER_CLASS_ID} {self.x_center:.8f} {self.y_center:.8f} "
            f"{self.width:.8f} {self.height:.8f}"
        )


@dataclass(frozen=True)
class Sample:
    """One source image and its retained deer annotations."""

    source_dataset: str
    source_image: Path
    source_image_id: str
    source_labels: tuple[str, ...]
    natural_group: str
    boxes: tuple[Box, ...]
    license_name: str
    source_url: str

    @property
    def is_positive(self) -> bool:
        return bool(self.boxes)


@dataclass(frozen=True)
class PreparedSample:
    sample: Sample
    sha256: str
    split_group: str
    split: str


class UnionFind:
    """Build connected groups for both capture groups and exact duplicates."""

    def __init__(self, size: int) -> None:
        self.parent = list(range(size))

    def find(self, item: int) -> int:
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def union(self, left: int, right: int) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root != right_root:
            self.parent[right_root] = left_root


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ena24",
        type=Path,
        default=Path("data/datasets/ena24"),
        help="ENA24 directory containing ena24.json and images",
    )
    parser.add_argument(
        "--alberta",
        type=Path,
        default=Path("data/datasets/alberta-wildlife-v1"),
        help="Alberta YOLO export root",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/derived/deer-driver-v1"),
        help="New derived dataset directory; it must not already exist",
    )
    parser.add_argument(
        "--negative-ratio",
        type=float,
        default=1.0,
        help="Maximum negative images per positive image in each source",
    )
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def _clipped_box(
    x_min: float,
    y_min: float,
    x_max: float,
    y_max: float,
    image_width: float,
    image_height: float,
) -> Box | None:
    x_min = min(max(x_min, 0.0), image_width)
    x_max = min(max(x_max, 0.0), image_width)
    y_min = min(max(y_min, 0.0), image_height)
    y_max = min(max(y_max, 0.0), image_height)
    width = x_max - x_min
    height = y_max - y_min
    if width <= 0 or height <= 0:
        return None
    return Box(
        x_center=((x_min + x_max) / 2) / image_width,
        y_center=((y_min + y_max) / 2) / image_height,
        width=width / image_width,
        height=height / image_height,
    )


def coco_box_to_yolo(
    bbox: Iterable[float], image_width: int, image_height: int
) -> Box | None:
    """Convert a COCO [x, y, width, height] box to normalized YOLO form."""
    x_min, y_min, width, height = bbox
    return _clipped_box(
        x_min,
        y_min,
        x_min + width,
        y_min + height,
        float(image_width),
        float(image_height),
    )


def normalize_yolo_box(values: Iterable[float]) -> Box | None:
    """Clip a normalized YOLO box to the image boundary."""
    x_center, y_center, width, height = values
    return _clipped_box(
        x_center - width / 2,
        y_center - height / 2,
        x_center + width / 2,
        y_center + height / 2,
        1.0,
        1.0,
    )


def load_ena24(root: Path) -> tuple[list[Sample], dict[str, int]]:
    annotation_path = root / "ena24.json"
    if not annotation_path.is_file():
        raise FileNotFoundError(f"ENA24 annotation file not found: {annotation_path}")

    payload: dict[str, Any] = json.loads(annotation_path.read_text(encoding="utf-8"))
    category_names = {
        int(category["id"]): str(category["name"])
        for category in payload["categories"]
    }
    deer_ids = {
        category_id
        for category_id, name in category_names.items()
        if name == ENA_DEER_LABEL
    }
    if len(deer_ids) != 1:
        raise ValueError(f"Expected one ENA24 deer category, found {deer_ids}")

    annotations: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    labels_by_image: defaultdict[str, set[str]] = defaultdict(set)
    for annotation in payload["annotations"]:
        image_id = str(annotation["image_id"])
        annotations[image_id].append(annotation)
        labels_by_image[image_id].add(category_names[int(annotation["category_id"])])

    samples: list[Sample] = []
    missing_images = 0
    invalid_boxes = 0
    for image in payload["images"]:
        image_id = str(image["id"])
        image_path = root / str(image["file_name"])
        if not image_path.is_file():
            missing_images += 1
            continue

        boxes: list[Box] = []
        for annotation in annotations[image_id]:
            if int(annotation["category_id"]) not in deer_ids:
                continue
            box = coco_box_to_yolo(
                annotation["bbox"], int(image["width"]), int(image["height"])
            )
            if box is None:
                invalid_boxes += 1
            else:
                boxes.append(box)

        samples.append(
            Sample(
                source_dataset="ena24",
                source_image=image_path,
                source_image_id=image_id,
                source_labels=tuple(sorted(labels_by_image[image_id])),
                natural_group=f"ena24:image:{image_id}",
                boxes=tuple(boxes),
                license_name="CDLA-Permissive-2.0",
                source_url="https://lila.science/datasets/ena24detection",
            )
        )

    return samples, {
        "metadata_images": len(payload["images"]),
        "local_images": len(samples),
        "missing_images": missing_images,
        "invalid_deer_boxes": invalid_boxes,
    }


def _alberta_capture_group(stem: str) -> str:
    original_stem = stem.split(".rf.", maxsplit=1)[0]
    if "_IMG_" in original_stem and original_stem.startswith("G"):
        return f"alberta:capture:{original_stem.split('_IMG_', maxsplit=1)[0]}"
    return f"alberta:image:{original_stem}"


def load_alberta(root: Path) -> tuple[list[Sample], dict[str, int]]:
    image_dir = root / "train" / "images"
    label_dir = root / "train" / "labels"
    if not image_dir.is_dir() or not label_dir.is_dir():
        raise FileNotFoundError(f"Alberta train/images or train/labels missing: {root}")

    samples: list[Sample] = []
    missing_labels = 0
    invalid_boxes = 0
    for image_path in sorted(image_dir.iterdir()):
        if not image_path.is_file() or image_path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        label_path = label_dir / f"{image_path.stem}.txt"
        boxes: list[Box] = []
        source_labels: set[str] = set()
        if not label_path.is_file():
            missing_labels += 1
        else:
            for line_number, line in enumerate(
                label_path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                if not line.strip():
                    continue
                parts = line.split()
                if len(parts) != 5:
                    raise ValueError(
                        f"Malformed Alberta label {label_path}:{line_number}"
                    )
                class_id = int(parts[0])
                if not 0 <= class_id < len(ALBERTA_CLASS_NAMES):
                    raise ValueError(
                        f"Unknown Alberta class {class_id} in "
                        f"{label_path}:{line_number}"
                    )
                source_labels.add(ALBERTA_CLASS_NAMES[class_id])
                if class_id in ALBERTA_DEER_CLASS_IDS:
                    box = normalize_yolo_box(float(value) for value in parts[1:])
                    if box is None:
                        invalid_boxes += 1
                    else:
                        boxes.append(box)

        samples.append(
            Sample(
                source_dataset="alberta-wildlife-v1",
                source_image=image_path,
                source_image_id=image_path.stem,
                source_labels=tuple(sorted(source_labels)),
                natural_group=_alberta_capture_group(image_path.stem),
                boxes=tuple(boxes),
                license_name="CC-BY-4.0",
                source_url=(
                    "https://universe.roboflow.com/apoorvs-workspace-evhrh/"
                    "alberta-wildlife_2/dataset/1"
                ),
            )
        )

    return samples, {
        "local_images": len(samples),
        "missing_label_files": missing_labels,
        "invalid_deer_boxes": invalid_boxes,
    }


def select_balanced_samples(
    samples: list[Sample], *, negative_ratio: float, seed: int
) -> list[Sample]:
    if negative_ratio < 0:
        raise ValueError("negative_ratio must be non-negative")
    positives = [sample for sample in samples if sample.is_positive]
    negatives = [sample for sample in samples if not sample.is_positive]
    negative_count = min(len(negatives), round(len(positives) * negative_ratio))
    rng = random.Random(seed)
    selected_negatives = rng.sample(negatives, negative_count)
    return sorted(
        [*positives, *selected_negatives],
        key=lambda sample: (sample.source_dataset, sample.source_image_id),
    )


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hash_fraction(value: str) -> float:
    integer = int(hashlib.sha256(value.encode()).hexdigest()[:16], 16)
    return integer / float(0xFFFFFFFFFFFFFFFF)


def assign_splits(samples: list[Sample], *, seed: int) -> list[PreparedSample]:
    """Keep capture groups and exact duplicate files in the same split."""
    hashes = [file_sha256(sample.source_image) for sample in samples]
    union_find = UnionFind(len(samples))
    first_by_natural_group: dict[str, int] = {}
    first_by_hash: dict[str, int] = {}
    for index, (sample, sha256) in enumerate(zip(samples, hashes, strict=True)):
        for key, lookup in (
            (sample.natural_group, first_by_natural_group),
            (sha256, first_by_hash),
        ):
            if key in lookup:
                union_find.union(index, lookup[key])
            else:
                lookup[key] = index

    members_by_root: defaultdict[int, list[int]] = defaultdict(list)
    for index in range(len(samples)):
        members_by_root[union_find.find(index)].append(index)

    split_by_root: dict[int, str] = {}
    group_name_by_root: dict[int, str] = {}
    train_cutoff = SPLIT_RATIOS["train"]
    val_cutoff = train_cutoff + SPLIT_RATIOS["val"]
    for root, members in members_by_root.items():
        group_material = "|".join(
            sorted(
                {
                    *(samples[index].natural_group for index in members),
                    *(hashes[index] for index in members),
                }
            )
        )
        split_group = hashlib.sha256(group_material.encode()).hexdigest()[:16]
        fraction = _hash_fraction(f"{seed}:{split_group}")
        if fraction < train_cutoff:
            split = "train"
        elif fraction < val_cutoff:
            split = "val"
        else:
            split = "test"
        split_by_root[root] = split
        group_name_by_root[root] = split_group

    return [
        PreparedSample(
            sample=sample,
            sha256=hashes[index],
            split_group=group_name_by_root[union_find.find(index)],
            split=split_by_root[union_find.find(index)],
        )
        for index, sample in enumerate(samples)
    ]


def _derived_stem(sample: Sample) -> str:
    safe_id = "".join(
        character if character.isalnum() or character in "-_" else "_"
        for character in sample.source_image_id
    )
    return f"{sample.source_dataset}__{safe_id}"


def _relative_source(path: Path, project_root: Path) -> str:
    try:
        return path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def write_dataset(
    prepared: list[PreparedSample],
    *,
    output: Path,
    project_root: Path,
    source_stats: dict[str, dict[str, int]],
    seed: int,
    negative_ratio: float,
) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(
            f"Output already exists; choose a new path or remove it first: {output}"
        )

    for split in SPLIT_RATIOS:
        (output / "images" / split).mkdir(parents=True)
        (output / "labels" / split).mkdir(parents=True)

    manifest_rows: list[dict[str, Any]] = []
    used_names: set[str] = set()
    for item in sorted(
        prepared,
        key=lambda value: (
            value.split,
            value.sample.source_dataset,
            value.sample.source_image_id,
        ),
    ):
        sample = item.sample
        stem = _derived_stem(sample)
        if stem in used_names:
            stem = f"{stem}__{item.sha256[:10]}"
        if stem in used_names:
            raise ValueError(f"Could not make a unique derived name for {sample}")
        used_names.add(stem)

        image_name = f"{stem}{sample.source_image.suffix.lower()}"
        image_path = output / "images" / item.split / image_name
        label_path = output / "labels" / item.split / f"{stem}.txt"
        relative_target = os.path.relpath(
            sample.source_image.resolve(), image_path.parent
        )
        image_path.symlink_to(relative_target)
        rendered_labels = "\n".join(box.as_yolo() for box in sample.boxes)
        label_path.write_text(
            f"{rendered_labels}\n" if rendered_labels else "", encoding="utf-8"
        )

        manifest_rows.append(
            {
                "derived_image": image_path.relative_to(output).as_posix(),
                "derived_label": label_path.relative_to(output).as_posix(),
                "split": item.split,
                "split_group": item.split_group,
                "source_dataset": sample.source_dataset,
                "source_image": _relative_source(sample.source_image, project_root),
                "source_image_id": sample.source_image_id,
                "source_labels": list(sample.source_labels),
                "license": sample.license_name,
                "source_url": sample.source_url,
                "sha256": item.sha256,
                "is_positive": sample.is_positive,
                "deer_box_count": len(sample.boxes),
            }
        )

    (output / "manifest.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in manifest_rows),
        encoding="utf-8",
    )
    absolute_output = output.resolve().as_posix()
    (output / "data.yaml").write_text(
        f"path: {absolute_output}\n"
        "train: images/train\n"
        "val: images/val\n"
        "test: images/test\n\n"
        "names:\n"
        "  0: animal\n",
        encoding="utf-8",
    )

    summary = build_summary(
        prepared,
        source_stats=source_stats,
        seed=seed,
        negative_ratio=negative_ratio,
    )
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output / "README.md").write_text(
        _dataset_readme(summary), encoding="utf-8"
    )
    return summary


def build_summary(
    prepared: list[PreparedSample],
    *,
    source_stats: dict[str, dict[str, int]],
    seed: int,
    negative_ratio: float,
) -> dict[str, Any]:
    by_split: dict[str, dict[str, int]] = {}
    for split in SPLIT_RATIOS:
        items = [item for item in prepared if item.split == split]
        by_split[split] = {
            "images": len(items),
            "positive_images": sum(item.sample.is_positive for item in items),
            "negative_images": sum(not item.sample.is_positive for item in items),
            "deer_boxes": sum(len(item.sample.boxes) for item in items),
            "split_groups": len({item.split_group for item in items}),
        }

    by_source: dict[str, dict[str, int]] = {}
    for source in sorted({item.sample.source_dataset for item in prepared}):
        items = [item for item in prepared if item.sample.source_dataset == source]
        by_source[source] = {
            "images": len(items),
            "positive_images": sum(item.sample.is_positive for item in items),
            "negative_images": sum(not item.sample.is_positive for item in items),
            "deer_boxes": sum(len(item.sample.boxes) for item in items),
        }

    hash_splits: defaultdict[str, set[str]] = defaultdict(set)
    group_splits: defaultdict[str, set[str]] = defaultdict(set)
    for item in prepared:
        hash_splits[item.sha256].add(item.split)
        group_splits[item.split_group].add(item.split)

    return {
        "dataset": "deer-driver-v1",
        "class_names": ["animal"],
        "seed": seed,
        "negative_ratio_per_source": negative_ratio,
        "split_ratios": SPLIT_RATIOS,
        "totals": {
            "images": len(prepared),
            "positive_images": sum(item.sample.is_positive for item in prepared),
            "negative_images": sum(not item.sample.is_positive for item in prepared),
            "deer_boxes": sum(len(item.sample.boxes) for item in prepared),
            "exact_duplicate_files": len(prepared)
            - len({item.sha256 for item in prepared}),
        },
        "by_split": by_split,
        "by_source": by_source,
        "source_scan": source_stats,
        "validation": {
            "content_hashes_crossing_splits": sum(
                len(splits) > 1 for splits in hash_splits.values()
            ),
            "split_groups_crossing_splits": sum(
                len(splits) > 1 for splits in group_splits.values()
            ),
        },
        "limitations": [
            "Current sources are predominantly camera-trap imagery, not dashcam video.",
            (
                "ENA24 provides no local camera-sequence grouping metadata; its "
                "images are split individually except for exact duplicates."
            ),
            "Alberta capture-style filename prefixes are grouped when available.",
            "A separate representative road-video test set is still required.",
        ],
    }


def _dataset_readme(summary: dict[str, Any]) -> str:
    totals = summary["totals"]
    return f"""# Deer driver v1 (derived)

This is a generated one-class YOLO object-detection view for the WildGuard
driver MVP. It links to source images rather than copying or modifying them.

- Object class `0`: `animal`
- Current positive boxes: deer
- Images: {totals['images']}
- Positive images: {totals['positive_images']}
- Negative images: {totals['negative_images']}
- Deer boxes: {totals['deer_boxes']}

Sources are ENA24 (`White_Tailed_Deer`) and Alberta Wildlife v1 (`Mule deer`
and `White-tailed deer`). Those source labels remain in `manifest.jsonl`; the
object detector receives only the shared `animal` label. See `manifest.jsonl`
for per-image source, label, license, hash, grouping, and split provenance. See
`summary.json` for counts and validation results.

This version is a camera-trap-heavy baseline. It must not be treated as proof of
road or nighttime driver-safety performance.
"""


def validate_dataset(output: Path, summary: dict[str, Any]) -> None:
    errors: list[str] = []
    actual_images = 0
    actual_boxes = 0
    for split in SPLIT_RATIOS:
        image_dir = output / "images" / split
        label_dir = output / "labels" / split
        images = [path for path in image_dir.iterdir() if path.is_symlink()]
        labels = list(label_dir.glob("*.txt"))
        actual_images += len(images)
        if len(images) != len(labels):
            errors.append(f"{split}: {len(images)} images but {len(labels)} labels")
        for image in images:
            if not image.exists():
                errors.append(f"broken image link: {image}")
        for label in labels:
            for line_number, line in enumerate(
                label.read_text(encoding="utf-8").splitlines(), start=1
            ):
                parts = line.split()
                if len(parts) != 5 or parts[0] != "0":
                    errors.append(f"malformed label: {label}:{line_number}")
                    continue
                values = [float(value) for value in parts[1:]]
                if not all(0.0 <= value <= 1.0 for value in values):
                    errors.append(f"out-of-range label: {label}:{line_number}")
                if values[2] <= 0 or values[3] <= 0:
                    errors.append(f"non-positive box: {label}:{line_number}")
                actual_boxes += 1

    if actual_images != summary["totals"]["images"]:
        errors.append("image total does not match summary")
    if actual_boxes != summary["totals"]["deer_boxes"]:
        errors.append("box total does not match summary")
    if summary["validation"]["content_hashes_crossing_splits"]:
        errors.append("exact duplicate content crosses splits")
    if summary["validation"]["split_groups_crossing_splits"]:
        errors.append("a split group crosses splits")
    if errors:
        raise ValueError("Dataset validation failed:\n- " + "\n- ".join(errors))


def main() -> None:
    args = parse_args()
    project_root = Path.cwd()
    ena_samples, ena_stats = load_ena24(args.ena24)
    alberta_samples, alberta_stats = load_alberta(args.alberta)

    selected: list[Sample] = []
    for source_index, source_samples in enumerate((ena_samples, alberta_samples)):
        selected.extend(
            select_balanced_samples(
                source_samples,
                negative_ratio=args.negative_ratio,
                seed=args.seed + source_index,
            )
        )

    if not selected or not any(sample.is_positive for sample in selected):
        raise ValueError("No deer-positive samples were found")

    prepared = assign_splits(selected, seed=args.seed)
    source_stats = {"ena24": ena_stats, "alberta-wildlife-v1": alberta_stats}
    summary = write_dataset(
        prepared,
        output=args.output,
        project_root=project_root,
        source_stats=source_stats,
        seed=args.seed,
        negative_ratio=args.negative_ratio,
    )
    validate_dataset(args.output, summary)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
