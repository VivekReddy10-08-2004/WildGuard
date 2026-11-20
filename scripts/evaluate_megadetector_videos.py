"""Evaluate MegaDetector's animal class on videos and save annotations."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from statistics import fmean
from time import perf_counter
from typing import Any

import cv2
from megadetector.detection import run_detector  # type: ignore[import-untyped]

from scripts.evaluate_deer_videos import (
    DEFAULT_SOURCE,
    DetectionEvent,
    detection_events,
    discover_videos,
    video_metadata,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = (
    PROJECT_ROOT
    / "storage"
    / "models"
    / "megadetector"
    / "md_v1000.0.0-redwood.pt"
)
DEFAULT_OUTPUT = PROJECT_ROOT / "storage" / "evidence" / "megadetector_video_test"
ANIMAL_CATEGORY = "1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--confidence", type=float, default=0.05)
    parser.add_argument("--image-size", type=int, default=1280)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--event-gap-seconds", type=float, default=0.5)
    parser.add_argument("--no-annotated-output", action="store_true")
    return parser.parse_args()


def animal_confidences(result: dict[str, Any]) -> list[float]:
    detections = result.get("detections") or []
    return [
        float(item["conf"])
        for item in detections
        if str(item["category"]) == ANIMAL_CATEGORY
    ]


def draw_animals(
    frame: Any, result: dict[str, Any], *, confidence: float
) -> None:
    height, width = frame.shape[:2]
    for item in result.get("detections") or []:
        if str(item["category"]) != ANIMAL_CATEGORY:
            continue
        score = float(item["conf"])
        if score < confidence:
            continue
        x, y, box_width, box_height = (float(value) for value in item["bbox"])
        left = max(0, min(width - 1, round(x * width)))
        top = max(0, min(height - 1, round(y * height)))
        right = max(left + 1, min(width, round((x + box_width) * width)))
        bottom = max(top + 1, min(height, round((y + box_height) * height)))
        cv2.rectangle(frame, (left, top), (right, bottom), (255, 0, 0), 2)
        cv2.putText(
            frame,
            f"animal {score:.2f}",
            (left, max(18, top - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 0, 0),
            2,
            cv2.LINE_AA,
        )


def _process_batch(
    detector: Any,
    frames: list[Any],
    frame_indices: list[int],
    *,
    image_size: int,
    confidence: float,
) -> tuple[list[dict[str, Any]], float]:
    started = perf_counter()
    raw_results = detector.generate_detections_one_batch(
        frames,
        image_id=[str(index) for index in frame_indices],
        detection_threshold=confidence,
        image_size=image_size,
    )
    elapsed_ms = (perf_counter() - started) * 1000
    return list(raw_results), elapsed_ms / len(frames)


def evaluate_video(
    detector: Any,
    video: Path,
    *,
    output: Path,
    confidence: float,
    image_size: int,
    batch_size: int,
    event_gap_seconds: float,
    save_annotated: bool,
) -> dict[str, Any]:
    metadata = video_metadata(video)
    fps = float(metadata["fps"])
    width = int(metadata["width"])
    height = int(metadata["height"])
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise RuntimeError(f"Could not open video: {video}")

    annotated_path = output / "annotated" / f"{video.stem}.avi"
    writer = None
    if save_annotated:
        annotated_path.parent.mkdir(parents=True, exist_ok=True)
        writer = cv2.VideoWriter(
            str(annotated_path),
            cv2.VideoWriter_fourcc(*"MJPG"),  # type: ignore[attr-defined]
            fps,
            (width, height),
        )
        if not writer.isOpened():
            capture.release()
            raise RuntimeError(f"Could not create annotated video: {annotated_path}")

    frame_detections: list[tuple[int, list[float]]] = []
    inference_times: list[float] = []
    processed_frames = 0
    frames: list[Any] = []
    frame_indices: list[int] = []

    try:
        while True:
            ok, frame = capture.read()
            if ok:
                frames.append(frame)
                frame_indices.append(processed_frames)
                processed_frames += 1

            if frames and (len(frames) == batch_size or not ok):
                results, mean_inference_ms = _process_batch(
                    detector,
                    frames,
                    frame_indices,
                    image_size=image_size,
                    confidence=confidence,
                )
                inference_times.extend([mean_inference_ms] * len(frames))
                for frame_item, frame_index, result in zip(
                    frames, frame_indices, results, strict=True
                ):
                    confidences = animal_confidences(result)
                    if confidences:
                        frame_detections.append((frame_index, confidences))
                    if writer is not None:
                        draw_animals(frame_item, result, confidence=confidence)
                        writer.write(frame_item)
                frames = []
                frame_indices = []

            if not ok:
                break
    finally:
        capture.release()
        if writer is not None:
            writer.release()

    events: list[DetectionEvent] = detection_events(
        frame_detections,
        fps=fps,
        gap_seconds=event_gap_seconds,
    )
    all_confidences = [
        value for _, confidences in frame_detections for value in confidences
    ]
    detection_frames = len(frame_detections)
    return {
        "source": str(video.resolve()),
        **metadata,
        "processed_frames": processed_frames,
        "duration_seconds": processed_frames / fps,
        "detection_frames": detection_frames,
        "detection_frame_rate": (
            detection_frames / processed_frames if processed_frames else 0.0
        ),
        "detections": len(all_confidences),
        "mean_confidence": fmean(all_confidences) if all_confidences else None,
        "max_confidence": max(all_confidences) if all_confidences else None,
        "mean_inference_ms": fmean(inference_times) if inference_times else None,
        "events": [asdict(event) for event in events],
        "annotated_video": str(annotated_path.resolve()) if writer else None,
    }


def main() -> None:
    args = parse_args()
    if not args.model.is_file():
        raise FileNotFoundError(f"MegaDetector checkpoint not found: {args.model}")
    videos = discover_videos(args.source)
    if not videos:
        raise FileNotFoundError(f"No supported videos found in: {args.source}")
    args.output.mkdir(parents=True, exist_ok=True)

    detector = run_detector.load_detector(str(args.model), verbose=True)
    video_results = [
        evaluate_video(
            detector,
            video,
            output=args.output,
            confidence=args.confidence,
            image_size=args.image_size,
            batch_size=args.batch_size,
            event_gap_seconds=args.event_gap_seconds,
            save_annotated=not args.no_annotated_output,
        )
        for video in videos
    ]
    report = {
        "model": str(args.model.resolve()),
        "model_name": "MDv1000-redwood",
        "target_category": "animal",
        "source": str(args.source.resolve()),
        "settings": {
            "confidence": args.confidence,
            "image_size": args.image_size,
            "batch_size": args.batch_size,
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
