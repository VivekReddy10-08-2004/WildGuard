"""Local YOLO26n video tracking and event-evidence aggregation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import cv2
import torch
from ultralytics import YOLO  # type: ignore[attr-defined]

from shared.contracts import BoundingBox, TrackedFrame, TrackEvidence

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WEIGHTS = PROJECT_ROOT / "storage/models/driver_animal_nano/best.pt"


@dataclass(frozen=True)
class TrackObservation:
    frame_index: int
    track_id: int
    confidence: float
    bounding_box: BoundingBox


@dataclass(frozen=True)
class VideoTrackingResult:
    detections: list[TrackEvidence]
    frames: list[TrackedFrame]
    processed_frames: int
    fps: float
    duration_seconds: float


def overlaps_road(
    box: BoundingBox, *, frame_width: int, frame_height: int
) -> bool:
    """Approximate whether a box's bottom center lies in a dashcam road corridor."""

    bottom = min(box.y_max / frame_height, 1.0)
    if bottom < 0.45:
        return False
    center = ((box.x_min + box.x_max) / 2) / frame_width
    half_width = 0.15 + 0.35 * ((bottom - 0.45) / 0.55)
    # shortcut: this dashcam corridor replaces road segmentation for the demo.
    return 0.5 - half_width <= center <= 0.5 + half_width


def aggregate_tracks(
    observations: list[TrackObservation],
    *,
    frame_width: int,
    frame_height: int,
) -> list[TrackEvidence]:
    grouped: dict[int, list[TrackObservation]] = {}
    for observation in observations:
        grouped.setdefault(observation.track_id, []).append(observation)

    tracks = []
    for track_id in sorted(grouped):
        items = grouped[track_id]
        best = max(items, key=lambda item: (item.confidence, -item.frame_index))
        tracks.append(
            TrackEvidence(
                label="animal",
                max_confidence=best.confidence,
                track_frames=len({item.frame_index for item in items}),
                bounding_box=best.bounding_box,
                road_overlap=any(
                    overlaps_road(
                        item.bounding_box,
                        frame_width=frame_width,
                        frame_height=frame_height,
                    )
                    for item in items
                ),
            )
        )
    return tracks


class YoloVideoProcessor:
    """Load YOLO once and process one uploaded video at a time."""

    def __init__(
        self,
        weights_path: str | Path = DEFAULT_WEIGHTS,
        *,
        confidence: float = 0.25,
        iou: float = 0.7,
        image_size: int = 640,
        device: str | int | None = None,
        model: YOLO | None = None,
    ) -> None:
        weights = Path(weights_path)
        if model is None:
            if not weights.is_file():
                raise FileNotFoundError(f"YOLO checkpoint not found: {weights}")
            model = YOLO(weights)
        self.model = model
        self.confidence = confidence
        self.iou = iou
        self.image_size = image_size
        self.device = device if device is not None else (
            0 if torch.cuda.is_available() else "cpu"
        )

    def process(self, video_path: Path, evidence_dir: Path) -> VideoTrackingResult:
        capture = cv2.VideoCapture(str(video_path))
        if not capture.isOpened():
            raise ValueError("Uploaded file is not a readable video")

        fps = float(capture.get(cv2.CAP_PROP_FPS))
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if fps <= 0 or width <= 0 or height <= 0:
            capture.release()
            raise ValueError("Uploaded video has invalid metadata")

        observations: list[TrackObservation] = []
        candidates: dict[str, tuple[int, float, Any]] = {}
        processed_frames = 0
        try:
            while True:
                readable, image = capture.read()
                if not readable:
                    break
                results = cast(
                    list[Any],
                    self.model.track(
                        source=image,
                        persist=processed_frames > 0,
                        tracker="bytetrack.yaml",
                        conf=self.confidence,
                        iou=self.iou,
                        imgsz=self.image_size,
                        device=self.device,
                        verbose=False,
                    ),
                )
                result = results[0]
                boxes: Any = result.boxes
                frame_confidence = 0.0
                if boxes is not None and boxes.id is not None:
                    ids = boxes.id.int().cpu().tolist()
                    confidences = boxes.conf.cpu().tolist()
                    coordinates = boxes.xyxy.cpu().tolist()
                    for track_id, confidence, coordinates_xyxy in zip(
                        ids, confidences, coordinates, strict=True
                    ):
                        box = BoundingBox(
                            x_min=coordinates_xyxy[0],
                            y_min=coordinates_xyxy[1],
                            x_max=coordinates_xyxy[2],
                            y_max=coordinates_xyxy[3],
                        )
                        observations.append(
                            TrackObservation(
                                frame_index=processed_frames,
                                track_id=track_id,
                                confidence=confidence,
                                bounding_box=box,
                            )
                        )
                        frame_confidence = max(frame_confidence, confidence)

                if frame_confidence:
                    candidate = (processed_frames, frame_confidence, image.copy())
                    candidates.setdefault("first", candidate)
                    if (
                        "best" not in candidates
                        or frame_confidence > candidates["best"][1]
                    ):
                        candidates["best"] = candidate
                    candidates["latest"] = candidate
                processed_frames += 1
        finally:
            capture.release()

        evidence_dir.mkdir(parents=True, exist_ok=True)
        tracked_frames = []
        unique_candidates = {
            candidate[0]: candidate for candidate in candidates.values()
        }
        for frame_index, confidence, image in sorted(unique_candidates.values()):
            path = evidence_dir / f"frame_{frame_index:06d}.jpg"
            if not cv2.imwrite(str(path), image):
                raise RuntimeError(f"Could not save evidence frame: {path}")
            tracked_frames.append(
                TrackedFrame(
                    path=str(path.resolve()),
                    timestamp_s=frame_index / fps,
                    confidence=confidence,
                )
            )

        return VideoTrackingResult(
            detections=aggregate_tracks(
                observations,
                frame_width=width,
                frame_height=height,
            ),
            frames=tracked_frames,
            processed_frames=processed_frames,
            fps=fps,
            duration_seconds=processed_frames / fps,
        )
