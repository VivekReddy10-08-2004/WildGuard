from pathlib import Path

from scripts.derive_deer_driver_dataset import (
    Box,
    Sample,
    assign_splits,
    coco_box_to_yolo,
    normalize_yolo_box,
    select_balanced_samples,
)


def _sample(path: Path, image_id: str, *, positive: bool) -> Sample:
    return Sample(
        source_dataset="test",
        source_image=path,
        source_image_id=image_id,
        source_labels=("deer",) if positive else (),
        natural_group=f"test:{image_id}",
        boxes=(Box(0.5, 0.5, 0.25, 0.25),) if positive else (),
        license_name="test",
        source_url="https://example.test",
    )


def test_coco_box_to_yolo_clips_to_image() -> None:
    box = coco_box_to_yolo([-10, 10, 30, 40], 100, 100)

    assert box == Box(x_center=0.1, y_center=0.3, width=0.2, height=0.4)


def test_normalize_yolo_box_rejects_empty_box() -> None:
    assert normalize_yolo_box([0.5, 0.5, 0.0, 0.2]) is None


def test_balancing_keeps_all_positives_and_caps_negatives(tmp_path: Path) -> None:
    samples = [
        _sample(tmp_path / f"{index}.jpg", str(index), positive=index < 2)
        for index in range(7)
    ]

    selected = select_balanced_samples(samples, negative_ratio=1.0, seed=42)

    assert sum(sample.is_positive for sample in selected) == 2
    assert sum(not sample.is_positive for sample in selected) == 2


def test_duplicate_files_are_kept_in_same_split(tmp_path: Path) -> None:
    first = tmp_path / "first.jpg"
    duplicate = tmp_path / "duplicate.jpg"
    other = tmp_path / "other.jpg"
    first.write_bytes(b"same image")
    duplicate.write_bytes(b"same image")
    other.write_bytes(b"different image")
    samples = [
        _sample(first, "first", positive=True),
        _sample(duplicate, "duplicate", positive=True),
        _sample(other, "other", positive=False),
    ]

    prepared = assign_splits(samples, seed=42)

    assert prepared[0].split == prepared[1].split
    assert prepared[0].split_group == prepared[1].split_group
