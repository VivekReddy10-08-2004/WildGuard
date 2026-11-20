"""Run the deer-trained animal detector over videos and summarize detections."""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import fmean
from typing import Any

import cv2
from ultralytics import YOLO  # type: ignore[attr-defined]

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = PROJECT_ROOT / "data" / "datasets" / "Youtube_Deer"
DEFAULT_MODEL = (
    PROJECT_ROOT / "storage" / "models" / "driver_animal_v2" / "best.pt"
)
DEFAULT_OUTPUT = PROJECT_ROOT / "storage" / "evidence" / "animal_video_test"
VIDEO_SUFFIXES = {".avi", ".mkv", ".mov", ".mp4", ".webm"}


@dataclass(frozen=True)
class DetectionEvent:
    start_seconds: float
    end_seconds: float
    detection_frames: int
    detections: int
    max_confidence: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--confidence", type=float, default=0.25)
    parser.add_argument("--iou", type=float, default=0.70)
    parser.add_argument("--image-size", type=int, default=640)
    parser.add_argument("--device", default="0")
    parser.add_argument("--event-gap-seconds", type=float, default=0.5)
    parser.add_argument(
        "--no-annotated-output",
        action="store_true",
        help="Compute statistics without rendering annotated videos",
    )
    return parser.parse_args()


def discover_videos(source: Path) -> list[Path]:
    if source.is_file():
        return [source]
    if not source.is_dir():
        raise FileNotFoundError(f"Video source does not exist: {source}")
    return sorted(
        path
        for path in source.rglob("*")
        if path.is_file() and path.suffix.lower() in VIDEO_SUFFIXES
    )


def video_metadata(path: Path) -> dict[str, float | int]:
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise RuntimeError(f"Could not open video: {path}")
    try:
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        return {
            "fps": fps,
            "source_frames": int(capture.get(cv2.CAP_PROP_FRAME_COUNT)),
            "width": int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)),
            "height": int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        }
    finally:
        capture.release()


def detection_events(
    frame_detections: list[tuple[int, list[float]]],
    *,
    fps: float,
    gap_seconds: float,
) -> list[DetectionEvent]:
    if not frame_detections:
        return []

    max_gap_frames = max(1, math.ceil(fps * gap_seconds))
    groups: list[list[tuple[int, list[float]]]] = [[frame_detections[0]]]
    for item in frame_detections[1:]:
        if item[0] - groups[-1][-1][0] <= max_gap_frames:
            groups[-1].append(item)
        else:
            groups.append([item])

    events = []
    for group in groups:
        confidences = [value for _, values in group for value in values]
        events.append(
            DetectionEvent(
                start_seconds=group[0][0] / fps,
                end_seconds=group[-1][0] / fps,
                detection_frames=len(group),
                detections=len(confidences),
                max_confidence=max(confidences),
            )
        )
    return events


def evaluate_video(
    model: YOLO,
    video: Path,
    *,
    output: Path,
    confidence: float,
    iou: float,
    image_size: int,
    device: str,
    event_gap_seconds: float,
    save_annotated: bool,
) -> dict[str, Any]:
    metadata = video_metadata(video)
    fps = float(metadata["fps"])
    if fps <= 0:
        raise ValueError(f"Video reports an invalid frame rate: {video}")

    run_name = video.stem
    results = model.predict(
        source=str(video),
        stream=True,
        save=save_annotated,
        project=str((output / "annotated").resolve()),
        name=run_name,
        exist_ok=True,
        conf=confidence,
        iou=iou,
        imgsz=image_size,
        device=device,
        verbose=False,
    )

    processed_frames = 0
    frame_detections: list[tuple[int, list[float]]] = []
    inference_times: list[float] = []
    for frame_index, raw_result in enumerate(results):
        result: Any = raw_result
        processed_frames += 1
        inference_times.append(float(result.speed["inference"]))
        confidences = (
            []
            if result.boxes is None
            else [float(value) for value in result.boxes.conf.cpu().tolist()]
        )
        if confidences:
            frame_detections.append((frame_index, confidences))

    events = detection_events(
        frame_detections,
        fps=fps,
        gap_seconds=event_gap_seconds,
    )
    all_confidences = [
        value for _, confidences in frame_detections for value in confidences
    ]
    duration_seconds = processed_frames / fps
    detection_frames = len(frame_detections)
    return {
        "source": str(video.resolve()),
        **metadata,
        "processed_frames": processed_frames,
        "duration_seconds": duration_seconds,
        "detection_frames": detection_frames,
        "detection_frame_rate": (
            detection_frames / processed_frames if processed_frames else 0.0
        ),
        "detections": len(all_confidences),
        "mean_confidence": fmean(all_confidences) if all_confidences else None,
        "max_confidence": max(all_confidences) if all_confidences else None,
        "mean_inference_ms": fmean(inference_times) if inference_times else None,
        "events": [asdict(event) for event in events],
        "annotated_directory": (
            str((output / "annotated" / run_name).resolve())
            if save_annotated
            else None
        ),
    }


def main() -> None:
    args = parse_args()
    if not args.model.is_file():
        raise FileNotFoundError(f"Model checkpoint not found: {args.model}")
    videos = discover_videos(args.source)
    if not videos:
        raise FileNotFoundError(f"No supported videos found in: {args.source}")

    args.output.mkdir(parents=True, exist_ok=True)
    model = YOLO(args.model)
    video_results = [
        evaluate_video(
            model,
            video,
            output=args.output,
            confidence=args.confidence,
            iou=args.iou,
            image_size=args.image_size,
            device=args.device,
            event_gap_seconds=args.event_gap_seconds,
            save_annotated=not args.no_annotated_output,
        )
        for video in videos
    ]
    report = {
        "model": str(args.model.resolve()),
        "source": str(args.source.resolve()),
        "settings": {
            "confidence": args.confidence,
            "iou": args.iou,
            "image_size": args.image_size,
            "device": args.device,
            "event_gap_seconds": args.event_gap_seconds,
            "save_annotated": not args.no_annotated_output,
        },
        "videos": video_results,
        "totals": {
            "videos": len(video_results),
            "frames": sum(item["processed_frames"] for item in video_results),
            "detection_frames": sum(
                item["detection_frames"] for item in video_results
            ),
            "detections": sum(item["detections"] for item in video_results),
            "events": sum(len(item["events"]) for item in video_results),
        },
    }
    report_path = args.output / "report.json"
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    print(f"Saved report: {report_path.resolve()}")


if __name__ == "__main__":
    main()
