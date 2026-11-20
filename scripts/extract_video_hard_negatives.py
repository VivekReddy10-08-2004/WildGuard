"""Extract a reviewed empty-video interval as training-only YOLO negatives."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import cv2  # type: ignore[import-untyped]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--start-seconds", type=float, default=0.0)
    parser.add_argument("--end-seconds", type=float, required=True)
    parser.add_argument("--interval-seconds", type=float, default=0.25)
    parser.add_argument(
        "--dataset-name", default="driver-video-hard-negatives-v1"
    )
    parser.add_argument(
        "--review-note",
        default="Interval manually reviewed and confirmed to contain no animals.",
    )
    return parser.parse_args()


def sample_frame_indices(
    *, fps: float, start_seconds: float, end_seconds: float, interval_seconds: float
) -> list[int]:
    if fps <= 0:
        raise ValueError("Video FPS must be positive")
    if start_seconds < 0 or end_seconds < start_seconds:
        raise ValueError("Invalid sampling interval")
    if interval_seconds <= 0:
        raise ValueError("Sampling interval must be positive")
    indices: list[int] = []
    step = 0
    while True:
        seconds = start_seconds + step * interval_seconds
        if seconds > end_seconds + 1e-9:
            break
        frame = round(seconds * fps)
        if not indices or indices[-1] != frame:
            indices.append(frame)
        step += 1
    return indices


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_stem(value: str) -> str:
    rendered = "".join(
        character.lower() if character.isalnum() else "_" for character in value
    )
    return "_".join(part for part in rendered.split("_") if part) or "video"


def extract(
    *,
    video: Path,
    output: Path,
    start_seconds: float,
    end_seconds: float,
    interval_seconds: float,
    dataset_name: str,
    review_note: str,
) -> dict[str, Any]:
    if not video.is_file():
        raise FileNotFoundError(f"Source video not found: {video}")
    if output.exists():
        raise FileExistsError(f"Output already exists: {output}")

    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise ValueError(f"Could not open source video: {video}")
    fps = float(capture.get(cv2.CAP_PROP_FPS))
    source_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    indices = sample_frame_indices(
        fps=fps,
        start_seconds=start_seconds,
        end_seconds=end_seconds,
        interval_seconds=interval_seconds,
    )
    invalid = [index for index in indices if index < 0 or index >= source_frames]
    if invalid:
        capture.release()
        raise ValueError(f"Sampled frames exceed source video: {invalid}")

    image_dir = output / "images" / "train"
    label_dir = output / "labels" / "train"
    image_dir.mkdir(parents=True)
    label_dir.mkdir(parents=True)
    video_stem = _safe_stem(video.stem)
    rows: list[dict[str, Any]] = []
    for frame_index in indices:
        capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        ok, frame = capture.read()
        if not ok:
            capture.release()
            raise RuntimeError(f"Could not decode frame {frame_index}: {video}")
        stem = f"{video_stem}__negative_frame_{frame_index:06d}"
        image_path = image_dir / f"{stem}.jpg"
        label_path = label_dir / f"{stem}.txt"
        if not cv2.imwrite(str(image_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 95]):
            capture.release()
            raise RuntimeError(f"Could not write extracted frame: {image_path}")
        label_path.write_text("", encoding="utf-8")
        rows.append(
            {
                "box_count": 0,
                "derived_image": image_path.relative_to(output).as_posix(),
                "derived_label": label_path.relative_to(output).as_posix(),
                "frame": frame_index,
                "is_positive": False,
                "review_note": review_note,
                "seconds": frame_index / fps,
                "sha256": _sha256(image_path),
                "source_video": video.resolve().as_posix(),
                "split": "train",
            }
        )
    capture.release()

    summary: dict[str, Any] = {
        "dataset": dataset_name,
        "class_names": ["animal"],
        "source_video": video.resolve().as_posix(),
        "sampling": {
            "start_seconds": start_seconds,
            "end_seconds": end_seconds,
            "interval_seconds": interval_seconds,
            "fps": fps,
        },
        "totals": {"images": len(rows), "negative_images": len(rows), "boxes": 0},
        "review_note": review_note,
        "limitations": [
            "All samples come from one manually reviewed interval in one video.",
            "These samples are training-only and cannot measure generalization.",
        ],
    }
    (output / "manifest.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    (output / "data.yaml").write_text(
        f"path: {output.resolve().as_posix()}\n"
        "train: images/train\n\n"
        "names:\n"
        "  0: animal\n",
        encoding="utf-8",
    )
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


def main() -> None:
    args = parse_args()
    summary = extract(
        video=args.video,
        output=args.output,
        start_seconds=args.start_seconds,
        end_seconds=args.end_seconds,
        interval_seconds=args.interval_seconds,
        dataset_name=args.dataset_name,
        review_note=args.review_note,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
