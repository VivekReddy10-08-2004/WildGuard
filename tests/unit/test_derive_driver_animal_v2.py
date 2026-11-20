import json
from pathlib import Path

import pytest

from scripts.derive_driver_animal_v2 import derive


def _dataset(
    root: Path, rows: list[tuple[str, str, bytes, str]], *, dataset: str
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    manifest = []
    for stem, split, image_content, label in rows:
        image = root / "images" / split / f"{stem}.jpg"
        label_path = root / "labels" / split / f"{stem}.txt"
        image.parent.mkdir(parents=True, exist_ok=True)
        label_path.parent.mkdir(parents=True, exist_ok=True)
        image.write_bytes(image_content)
        label_path.write_text(label, encoding="utf-8")
        manifest.append(
            {
                "derived_image": image.relative_to(root).as_posix(),
                "derived_label": label_path.relative_to(root).as_posix(),
                "split": split,
                "source_dataset": dataset,
            }
        )
    (root / "manifest.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in manifest), encoding="utf-8"
    )


def test_derive_adds_hard_examples_only_to_train_and_freezes_holds(
    tmp_path: Path,
) -> None:
    base = tmp_path / "base"
    hard = tmp_path / "hard"
    output = tmp_path / "output"
    _dataset(
        base,
        [
            ("train-positive", "train", b"train", "0 0.5 0.5 0.2 0.2\n"),
            ("val-negative", "val", b"val", ""),
            ("test-positive", "test", b"test", "0 0.5 0.5 0.2 0.2\n"),
        ],
        dataset="base",
    )
    _dataset(
        hard,
        [("road", "train", b"road", "0 0.5 0.5 0.4 0.4\n")],
        dataset="hard",
    )

    summary = derive(base=base, hard_examples=hard, output=output)

    assert summary["by_split"]["train"]["images"] == 2
    assert summary["by_split"]["val"]["images"] == 1
    assert summary["by_split"]["test"]["images"] == 1
    assert summary["totals"] == {
        "images": 4,
        "positive_images": 3,
        "negative_images": 1,
        "boxes": 3,
    }
    assert len(list((output / "images" / "train").iterdir())) == 2
    assert all(path.is_symlink() for path in (output / "images" / "train").iterdir())


def test_derive_rejects_hard_example_outside_train(tmp_path: Path) -> None:
    base = tmp_path / "base"
    hard = tmp_path / "hard"
    _dataset(base, [], dataset="base")
    _dataset(
        hard,
        [("road", "val", b"road", "0 0.5 0.5 0.4 0.4\n")],
        dataset="hard",
    )

    with pytest.raises(ValueError, match="training-only"):
        derive(base=base, hard_examples=hard, output=tmp_path / "output")


def test_derive_rejects_exact_content_crossing_splits(tmp_path: Path) -> None:
    base = tmp_path / "base"
    hard = tmp_path / "hard"
    _dataset(
        base,
        [("held", "val", b"duplicate", "0 0.5 0.5 0.2 0.2\n")],
        dataset="base",
    )
    _dataset(
        hard,
        [("road", "train", b"duplicate", "0 0.5 0.5 0.4 0.4\n")],
        dataset="hard",
    )

    with pytest.raises(ValueError, match="crosses splits"):
        derive(base=base, hard_examples=hard, output=tmp_path / "output")


def test_derive_combines_multiple_hard_example_datasets(tmp_path: Path) -> None:
    base = tmp_path / "base"
    first = tmp_path / "first-video"
    second = tmp_path / "second-video"
    output = tmp_path / "output"
    _dataset(
        base,
        [("held", "val", b"held", "0 0.5 0.5 0.2 0.2\n")],
        dataset="base",
    )
    _dataset(
        first,
        [("road-a", "train", b"road-a", "0 0.5 0.5 0.2 0.2\n")],
        dataset="first",
    )
    _dataset(
        second,
        [("road-b", "train", b"road-b", "0 0.5 0.5 0.3 0.3\n")],
        dataset="second",
    )

    summary = derive(base=base, hard_examples=[first, second], output=output)

    assert summary["by_split"]["train"]["images"] == 2
    assert summary["policy"]["hard_example_datasets"] == [
        "first-video",
        "second-video",
    ]
    assert summary["by_component"]["first-video"] == {"images": 1, "boxes": 1}
    assert summary["by_component"]["second-video"] == {"images": 1, "boxes": 1}
