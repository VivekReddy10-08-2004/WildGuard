"""Convert Label Studio video tracks into sampled YOLO detection frames."""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2

ANIMAL_CLASS_ID = 0


@dataclass(frozen=True)
class Keyframe:
    frame: int
    enabled: bool
    x: float
    y: float
    width: float
    height: float


@dataclass(frozen=True)
class Box:
    x_center: float
    y_center: float
    width: float
    height: float

    def as_yolo(self) -> str:
        return (
            f"{ANIMAL_CLASS_ID} {self.x_center:.8f} {self.y_center:.8f} "
            f"{self.width:.8f} {self.height:.8f}"
        )


@dataclass(frozen=True)
class FrameBox:
    track_id: str
    box: Box
    interpolated: bool


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export", type=Path, help="Label Studio JSON export")
    parser.add_argument("--video", type=Path, required=True, help="Source video")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/derived/driver-video-hard-examples-v1"),
        help="New output directory; it must not already exist",
    )
    parser.add_argument(
        "--frame-stride",
        type=int,
        default=3,
        help="Keep every Nth annotated frame within each visible track",
    )
    parser.add_argument(
        "--keyframes-only",
        action="store_true",
        help="Keep only manually reviewed enabled keyframes, without interpolation",
    )
    parser.add_argument(
        "--exclude-frame",
        action="append",
        default=[],
        type=int,
        help="Source frame to omit after sampling; repeat for multiple frames",
    )
    parser.add_argument("--jpeg-quality", type=int, default=95, choices=range(1, 101))
    return parser.parse_args()


def _task_from_payload(payload: Any) -> dict[str, Any]:
    if isinstance(payload, list):
        if len(payload) != 1:
            raise ValueError(
                "Expected exactly one Label Studio task per conversion, "
                f"found {len(payload)}"
            )
        payload = payload[0]
    if not isinstance(payload, dict):
        raise ValueError("Label Studio export must be a task object or one-item list")
    return payload


def load_task(export_path: Path) -> dict[str, Any]:
    if not export_path.is_file():
        raise FileNotFoundError(f"Label Studio export not found: {export_path}")
    return _task_from_payload(json.loads(export_path.read_text(encoding="utf-8")))


def _number(value: Any, *, field: str) -> float:
    if not isinstance(value, int | float):
        raise ValueError(f"Keyframe field {field!r} must be numeric")
    return float(value)


def _keyframe(raw: dict[str, Any]) -> Keyframe:
    frame = raw.get("frame")
    enabled = raw.get("enabled")
    if not isinstance(frame, int) or frame < 0:
        raise ValueError(f"Invalid keyframe frame: {frame!r}")
    if not isinstance(enabled, bool):
        raise ValueError(f"Invalid keyframe enabled state: {enabled!r}")
    return Keyframe(
        frame=frame,
        enabled=enabled,
        x=_number(raw.get("x"), field="x"),
        y=_number(raw.get("y"), field="y"),
        width=_number(raw.get("width"), field="width"),
        height=_number(raw.get("height"), field="height"),
    )


def _clip_box(x: float, y: float, width: float, height: float) -> Box:
    left = min(max(x, 0.0), 100.0)
    top = min(max(y, 0.0), 100.0)
    right = min(max(x + width, 0.0), 100.0)
    bottom = min(max(y + height, 0.0), 100.0)
    if right <= left or bottom <= top:
        raise ValueError("Label Studio keyframe produces an empty box")
    return Box(
        x_center=((left + right) / 2.0) / 100.0,
        y_center=((top + bottom) / 2.0) / 100.0,
        width=(right - left) / 100.0,
        height=(bottom - top) / 100.0,
    )


def _interpolate(left: Keyframe, right: Keyframe, frame: int) -> Box:
    if right.frame == left.frame:
        ratio = 0.0
    else:
        ratio = (frame - left.frame) / (right.frame - left.frame)
    return _clip_box(
        left.x + (right.x - left.x) * ratio,
        left.y + (right.y - left.y) * ratio,
        left.width + (right.width - left.width) * ratio,
        left.height + (right.height - left.height) * ratio,
    )


def interpolate_track(keyframes: list[Keyframe]) -> dict[int, Box]:
    """Expand a track; a disabled keyframe ends visibility at that frame."""
    ordered = sorted(keyframes, key=lambda item: item.frame)
    if len({item.frame for item in ordered}) != len(ordered):
        raise ValueError("A track contains duplicate keyframe frame numbers")
    boxes: dict[int, Box] = {}
    for index, left in enumerate(ordered):
        if not left.enabled:
            continue
        if index + 1 == len(ordered):
            boxes[left.frame] = _clip_box(left.x, left.y, left.width, left.height)
            continue
        right = ordered[index + 1]
        stop = right.frame if not right.enabled else right.frame + 1
        for frame in range(left.frame, stop):
            boxes[frame] = _interpolate(left, right, frame)
    return boxes


def collect_frame_boxes(
    task: dict[str, Any],
    *,
    frame_stride: int,
    keyframes_only: bool = False,
    excluded_frames: set[int] | None = None,
) -> tuple[dict[int, list[FrameBox]], dict[str, int]]:
    if frame_stride <= 0:
        raise ValueError("frame_stride must be positive")
    annotations = task.get("annotations")
    if not isinstance(annotations, list) or len(annotations) != 1:
        raise ValueError("Expected exactly one completed annotation")
    results = annotations[0].get("result")
    if not isinstance(results, list):
        raise ValueError("Annotation result must be a list")

    excluded_frames = excluded_frames or set()
    frame_boxes: defaultdict[int, list[FrameBox]] = defaultdict(list)
    empty_tracks = 0
    nonempty_tracks = 0
    for result in results:
        if not isinstance(result, dict) or result.get("type") != "videorectangle":
            continue
        value = result.get("value")
        if not isinstance(value, dict):
            raise ValueError("Video rectangle value must be an object")
        labels = value.get("labels")
        if labels != ["animal"]:
            raise ValueError(f"Expected the sole label 'animal', found {labels!r}")
        sequence = value.get("sequence")
        if not isinstance(sequence, list):
            raise ValueError("Video rectangle sequence must be a list")
        if not sequence:
            empty_tracks += 1
            continue
        track_id = str(result.get("id", "unknown"))
        keyframes = [_keyframe(item) for item in sequence if isinstance(item, dict)]
        expanded = interpolate_track(keyframes)
        if not expanded:
            empty_tracks += 1
            continue
        nonempty_tracks += 1
        first_frame = min(expanded)
        keyframe_numbers = {item.frame for item in keyframes if item.enabled}
        for frame, box in expanded.items():
            if frame in excluded_frames:
                continue
            if keyframes_only and frame not in keyframe_numbers:
                continue
            if (frame - first_frame) % frame_stride != 0:
                continue
            frame_boxes[frame].append(
                FrameBox(
                    track_id=track_id,
                    box=box,
                    interpolated=frame not in keyframe_numbers,
                )
            )
    return dict(frame_boxes), {
        "empty_tracks_ignored": empty_tracks,
        "nonempty_tracks": nonempty_tracks,
    }


def _safe_stem(value: str) -> str:
    rendered = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return rendered or "video"


def convert(
    *,
    export_path: Path,
    video_path: Path,
    output: Path,
    frame_stride: int,
    jpeg_quality: int,
    keyframes_only: bool = False,
    excluded_frames: set[int] | None = None,
) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(
            f"Output already exists; choose a new path or remove it first: {output}"
        )
    if not video_path.is_file():
        raise FileNotFoundError(f"Source video not found: {video_path}")
    task = load_task(export_path)
    frame_boxes, track_stats = collect_frame_boxes(
        task,
        frame_stride=frame_stride,
        keyframes_only=keyframes_only,
        excluded_frames=excluded_frames,
    )
    if not frame_boxes:
        raise ValueError("No enabled animal boxes remain after sampling")

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise ValueError(f"Could not open source video: {video_path}")
    fps = float(capture.get(cv2.CAP_PROP_FPS))
    source_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    invalid_frames = sorted(frame for frame in frame_boxes if frame >= source_frames)
    if invalid_frames:
        capture.release()
        raise ValueError(
            f"Annotations reference frames beyond the video: {invalid_frames}"
        )

    image_dir = output / "images" / "train"
    label_dir = output / "labels" / "train"
    image_dir.mkdir(parents=True)
    label_dir.mkdir(parents=True)
    video_stem = _safe_stem(video_path.stem)
    manifest_rows: list[dict[str, Any]] = []
    wanted = set(frame_boxes)
    frame_index = 0
    try:
        while wanted:
            ok, image = capture.read()
            if not ok:
                break
            if frame_index in wanted:
                name = f"{video_stem}__frame_{frame_index:06d}"
                image_path = image_dir / f"{name}.jpg"
                label_path = label_dir / f"{name}.txt"
                if not cv2.imwrite(
                    str(image_path), image, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality]
                ):
                    raise OSError(f"Could not write extracted frame: {image_path}")
                items = frame_boxes[frame_index]
                label_path.write_text(
                    "\n".join(item.box.as_yolo() for item in items) + "\n",
                    encoding="utf-8",
                )
                manifest_rows.append(
                    {
                        "derived_image": image_path.relative_to(output).as_posix(),
                        "derived_label": label_path.relative_to(output).as_posix(),
                        "source_video": video_path.resolve().as_posix(),
                        "source_export_name": export_path.name,
                        "source_task_id": task.get("id"),
                        "frame": frame_index,
                        "seconds": frame_index / fps,
                        "track_ids": [item.track_id for item in items],
                        "interpolated_boxes": sum(item.interpolated for item in items),
                        "box_count": len(items),
                        "split": "train",
                    }
                )
                wanted.remove(frame_index)
            frame_index += 1
    finally:
        capture.release()
    if wanted:
        raise ValueError(f"Could not decode annotated frames: {sorted(wanted)}")

    (output / "manifest.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in manifest_rows),
        encoding="utf-8",
    )
    (output / "data.yaml").write_text(
        f"path: {output.resolve().as_posix()}\n"
        "train: images/train\n\n"
        "names:\n"
        "  0: animal\n",
        encoding="utf-8",
    )
    summary: dict[str, Any] = {
        "dataset": output.name,
        "class_names": ["animal"],
        "source_video": video_path.resolve().as_posix(),
        "source_export_name": export_path.name,
        "source_task_id": task.get("id"),
        "settings": {
            "frame_stride": frame_stride,
            "jpeg_quality": jpeg_quality,
            "keyframes_only": keyframes_only,
            "excluded_frames": sorted(excluded_frames or set()),
            "split": "train",
        },
        "video": {
            "fps": fps,
            "frames": source_frames,
            "width": width,
            "height": height,
        },
        "tracks": track_stats,
        "totals": {
            "images": len(manifest_rows),
            "boxes": sum(row["box_count"] for row in manifest_rows),
            "interpolated_boxes": sum(
                row["interpolated_boxes"] for row in manifest_rows
            ),
        },
        "limitations": [
            "All frames come from one video encounter and are training-only.",
            "Empty legacy Label Studio tracks were ignored.",
            "The output must be combined with independent road-video validation data.",
        ],
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


def main() -> None:
    args = parse_args()
    summary = convert(
        export_path=args.export,
        video_path=args.video,
        output=args.output,
        frame_stride=args.frame_stride,
        jpeg_quality=args.jpeg_quality,
        keyframes_only=args.keyframes_only,
        excluded_frames=set(args.exclude_frame),
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
