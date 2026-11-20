"""Local YOLO26n video tracking and event-evidence aggregation."""

from __future__ import annotations

import hashlib
import os
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import cv2
import imageio_ffmpeg
import numpy as np
import torch
from ultralytics import YOLO  # type: ignore[attr-defined]

from shared.contracts import BoundingBox, TrackedFrame, TrackEvidence

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WEIGHTS = PROJECT_ROOT / "storage/models/driver_animal_nano/best.pt"
PREVIEW_LANDSCAPE = (1280, 720)
PREVIEW_PORTRAIT = (720, 1280)
PIPELINE_CACHE_VERSION = "driver-video-v2-h264-preview"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class TrackObservation:
    frame_index: int
    track_id: int
    confidence: float
    bounding_box: BoundingBox


@dataclass(frozen=True)
class FrameAnnotation:
    frame_index: int
    boxes: list[tuple[BoundingBox, float]]


@dataclass(frozen=True)
class VideoTrackingResult:
    detections: list[TrackEvidence]
    frames: list[TrackedFrame]
    processed_frames: int
    fps: float
    duration_seconds: float
    annotated_video_path: str | None = None
    annotations: list[FrameAnnotation] = field(default_factory=list)


def overlaps_road(box: BoundingBox, *, frame_width: int, frame_height: int) -> bool:
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


def preview_size(width: int, height: int) -> tuple[int, int]:
    max_width, max_height = PREVIEW_LANDSCAPE if width >= height else PREVIEW_PORTRAIT
    scale = min(max_width / width, max_height / height, 1.0)
    preview_width = max(2, int(width * scale) // 2 * 2)
    preview_height = max(2, int(height * scale) // 2 * 2)
    return preview_width, preview_height


def annotation_filter_chain(
    annotations: list[FrameAnnotation],
    *,
    input_size: tuple[int, int],
    output_size: tuple[int, int],
) -> str:
    """Build deterministic FFmpeg filters for sampled detection boxes."""

    input_width, input_height = input_size
    output_width, output_height = output_size
    x_scale = output_width / input_width
    y_scale = output_height / input_height
    filters = [f"scale={output_width}:{output_height}"]
    default_span = (
        max(1, annotations[1].frame_index - annotations[0].frame_index)
        if len(annotations) > 1
        else 1
    )
    for index, annotation in enumerate(annotations):
        next_frame = (
            annotations[index + 1].frame_index
            if index + 1 < len(annotations)
            else annotation.frame_index + default_span
        )
        end_frame = max(annotation.frame_index, next_frame - 1)
        enabled = f"between(n\\,{annotation.frame_index}\\,{end_frame})"
        for box, _confidence in annotation.boxes:
            x = max(0, min(output_width - 1, round(box.x_min * x_scale)))
            y = max(0, min(output_height - 1, round(box.y_min * y_scale)))
            width = max(
                1,
                min(output_width - x, round((box.x_max - box.x_min) * x_scale)),
            )
            height = max(
                1,
                min(
                    output_height - y,
                    round((box.y_max - box.y_min) * y_scale),
                ),
            )
            filters.append(
                "drawbox="
                f"x={x}:y={y}:w={width}:h={height}:"
                f"color=0x50dc78@0.95:t=3:enable={enabled}"
            )
    return ",".join(filters)


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
        warmup: bool = True,
        frame_stride: int = 2,
    ) -> None:
        weights = Path(weights_path)
        injected_model = model is not None
        if model is None:
            if not weights.is_file():
                raise FileNotFoundError(f"YOLO checkpoint not found: {weights}")
            model = YOLO(weights)
        self.model = model
        self.confidence = confidence
        self.iou = iou
        self.image_size = image_size
        if frame_stride < 1:
            raise ValueError("Frame stride must be at least 1")
        self.frame_stride = frame_stride
        self.device = (
            device
            if device is not None
            else (0 if torch.cuda.is_available() else "cpu")
        )
        self.quantization = 16 if self.device != "cpu" else None
        model_identity = (
            f"injected:{type(model).__module__}.{type(model).__qualname__}"
            if injected_model
            else file_sha256(weights)
        )
        self.cache_identity = ":".join(
            [
                PIPELINE_CACHE_VERSION,
                model_identity,
                str(self.confidence),
                str(self.iou),
                str(self.image_size),
                str(self.frame_stride),
                str(self.quantization),
            ]
        )
        if warmup:
            self.model.predict(
                source=np.zeros((self.image_size, self.image_size, 3), dtype=np.uint8),
                imgsz=self.image_size,
                device=self.device,
                quantize=self.quantization,
                verbose=False,
            )

    def process(self, video_path: Path, evidence_dir: Path) -> VideoTrackingResult:
        capture = cv2.VideoCapture(str(video_path))
        if not capture.isOpened():
            raise ValueError("Uploaded file is not a readable video")

        fps = float(capture.get(cv2.CAP_PROP_FPS))
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        if fps <= 0 or width <= 0 or height <= 0:
            capture.release()
            raise ValueError("Uploaded video has invalid metadata")
        capture.release()

        observations: list[TrackObservation] = []
        annotations: list[FrameAnnotation] = []
        candidates: dict[str, tuple[int, float, Any]] = {}
        processed_frames = 0
        evidence_dir.mkdir(parents=True, exist_ok=True)
        annotated_path = evidence_dir / "annotated.mp4"
        results = cast(
            Iterable[Any],
            self.model.track(
                source=str(video_path),
                stream=True,
                tracker="bytetrack.yaml",
                conf=self.confidence,
                iou=self.iou,
                imgsz=self.image_size,
                device=self.device,
                quantize=self.quantization,
                vid_stride=self.frame_stride,
                verbose=False,
            ),
        )
        for result in results:
            image: Any = result.orig_img
            source_frame_index = processed_frames * self.frame_stride
            boxes: Any = result.boxes
            frame_confidence = 0.0
            frame_boxes: list[tuple[BoundingBox, float]] = []
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
                    frame_boxes.append((box, confidence))
                    observations.append(
                        TrackObservation(
                            frame_index=source_frame_index,
                            track_id=track_id,
                            confidence=confidence,
                            bounding_box=box,
                        )
                    )
                    frame_confidence = max(frame_confidence, confidence)
            annotations.append(FrameAnnotation(source_frame_index, frame_boxes))

            if frame_confidence:
                candidate = (source_frame_index, frame_confidence, image.copy())
                candidates.setdefault("first", candidate)
                if "best" not in candidates or frame_confidence > candidates["best"][1]:
                    candidates["best"] = candidate
                candidates["latest"] = candidate
            processed_frames += 1

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
            duration_seconds=(
                total_frames / fps
                if total_frames > 0
                else processed_frames * self.frame_stride / fps
            ),
            annotated_video_path=str(annotated_path.resolve()),
            annotations=annotations,
        )

    def render_annotated(
        self,
        video_path: Path,
        result: VideoTrackingResult,
    ) -> None:
        if result.annotated_video_path is None:
            return
        output_path = Path(result.annotated_video_path)
        temporary_path = output_path.with_name("annotated.rendering.mp4")
        capture = cv2.VideoCapture(str(video_path))
        if not capture.isOpened():
            raise ValueError("Uploaded file is not a readable video")
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        output_size = preview_size(width, height)
        capture.release()
        ffmpeg = os.getenv("WILDGUARD_FFMPEG") or imageio_ffmpeg.get_ffmpeg_exe()
        filters = annotation_filter_chain(
            result.annotations,
            input_size=(width, height),
            output_size=output_size,
        )
        command = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(video_path),
            "-an",
            "-vf",
            filters,
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-tune",
            "zerolatency",
            "-crf",
            "25",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(temporary_path),
        ]
        try:
            encoder = subprocess.run(  # noqa: S603 - fixed local encoder command
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                check=False,
                timeout=max(60, int(result.duration_seconds * 4)),
            )
        except subprocess.TimeoutExpired as error:
            temporary_path.unlink(missing_ok=True)
            raise RuntimeError("Annotated-video encoder timed out") from error
        error_output = encoder.stderr.decode(errors="replace").strip()
        if encoder.returncode != 0:
            temporary_path.unlink(missing_ok=True)
            raise RuntimeError(
                f"Annotated-video encoder failed: {error_output or encoder.returncode}"
            )
        temporary_path.replace(output_path)
