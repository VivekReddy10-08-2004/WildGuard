from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import cv2
import numpy as np
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.orchestration import DescriptionWorker, EventService
from model_services.video.yolo_tracker import (
    TrackObservation,
    VideoTrackingResult,
    YoloVideoProcessor,
    aggregate_tracks,
    preview_size,
)
from shared.contracts import (
    AlertLevel,
    BoundingBox,
    SceneDescription,
    SpeciesRanking,
    TrackEvidence,
    WildlifeAudioAnalysis,
)


def box(x_min: float, y_min: float, x_max: float, y_max: float) -> BoundingBox:
    return BoundingBox(
        x_min=x_min,
        y_min=y_min,
        x_max=x_max,
        y_max=y_max,
    )


def test_track_aggregation_uses_persistence_confidence_and_road_position() -> None:
    tracks = aggregate_tracks(
        [
            TrackObservation(1, 7, 0.6, box(400, 300, 500, 500)),
            TrackObservation(2, 7, 0.9, box(420, 320, 520, 600)),
            TrackObservation(3, 7, 0.8, box(440, 340, 540, 650)),
        ],
        frame_width=1280,
        frame_height=720,
    )

    assert len(tracks) == 1
    assert tracks[0].track_frames == 3
    assert tracks[0].max_confidence == 0.9
    assert tracks[0].bounding_box.y_max == 600
    assert tracks[0].road_overlap is True


def test_preview_size_limits_landscape_and_portrait_video() -> None:
    assert preview_size(1920, 1080) == (1280, 720)
    assert preview_size(1080, 1920) == (720, 1280)
    assert preview_size(640, 480) == (640, 480)


class FakeTensor:
    def __init__(self, value: object) -> None:
        self.value = value

    def int(self) -> FakeTensor:
        return self

    def cpu(self) -> FakeTensor:
        return self

    def tolist(self) -> object:
        return self.value


class FakeBoxes:
    id = FakeTensor([7])
    conf = FakeTensor([0.8])
    xyxy = FakeTensor([[10, 20, 30, 45]])


class FakeResult:
    def __init__(self) -> None:
        self.orig_img = np.zeros((48, 64, 3), dtype=np.uint8)
        self.boxes = FakeBoxes()

    def plot(self) -> np.ndarray[Any, Any]:
        return self.orig_img.copy()


class FakeYolo:
    def __init__(self) -> None:
        self.predict_kwargs: dict[str, object] = {}
        self.track_kwargs: dict[str, object] = {}

    def predict(self, **kwargs: object) -> list[object]:
        self.predict_kwargs = kwargs
        return []

    def track(self, **kwargs: object) -> object:
        self.track_kwargs = kwargs
        return iter([FakeResult(), FakeResult()])


def test_video_processor_streams_fp16_tracking_and_warms_gpu(
    tmp_path: Path,
) -> None:
    video_path = tmp_path / "input.avi"
    source_writer = cv2.VideoWriter(
        str(video_path),
        cv2.VideoWriter_fourcc(*"MJPG"),  # type: ignore[attr-defined]
        10,
        (64, 48),
    )
    source_writer.write(np.zeros((48, 64, 3), dtype=np.uint8))
    source_writer.release()
    model = FakeYolo()
    processor = YoloVideoProcessor(
        model=cast(Any, model),
        device=0,
    )

    result = processor.process(video_path, tmp_path / "evidence")

    assert model.predict_kwargs["quantize"] == 16
    assert model.track_kwargs["source"] == str(video_path)
    assert model.track_kwargs["stream"] is True
    assert model.track_kwargs["quantize"] == 16
    assert model.track_kwargs["vid_stride"] == 2
    assert result.processed_frames == 2
    assert result.detections[0].track_frames == 2
    processor.render_annotated(video_path, result)
    assert Path(result.annotated_video_path or "").is_file()


class Descriptor:
    async def describe(
        self, frame_paths: list[str], detections: list[TrackEvidence]
    ) -> SceneDescription:
        del frame_paths, detections
        return SceneDescription(
            scene_description="An animal is visible on the road.",
            animal_species="uncertain",
            road_position="road",
            observed_motion="uncertain",
            visibility="clear",
        )


class VideoProcessor:
    cache_identity = "fake-driver-v1"

    def __init__(self) -> None:
        self.calls = 0

    def process(self, video_path: Path, evidence_dir: Path) -> VideoTrackingResult:
        self.calls += 1
        assert video_path.is_file()
        assert evidence_dir == video_path.parent
        annotated_path = evidence_dir / "annotated.webm"
        annotated_path.write_bytes(b"fake-annotated-video")
        return VideoTrackingResult(
            detections=[
                TrackEvidence(
                    label="animal",
                    max_confidence=0.9,
                    track_frames=5,
                    bounding_box=box(100, 100, 200, 300),
                    road_overlap=True,
                )
            ],
            frames=[],
            processed_frames=30,
            fps=30,
            duration_seconds=1,
            annotated_video_path=str(annotated_path),
        )

    def render_annotated(
        self, video_path: Path, result: VideoTrackingResult
    ) -> None:
        assert video_path.is_file()
        assert result.annotated_video_path is not None


class AudioAnalyzer:
    async def analyze(self, audio_path: Path) -> WildlifeAudioAnalysis:
        assert audio_path.is_file()
        return WildlifeAudioAnalysis(
            possible_species="coyote",
            similarity=0.7,
            score_margin=0.2,
            message="Possible wildlife sound detected — possible species: coyote",
            rankings=[SpeciesRanking(species="coyote", similarity=0.7)],
        )


def test_video_upload_flows_into_existing_decision_engine(tmp_path: Path) -> None:
    service = EventService(Descriptor())
    worker = DescriptionWorker(service)
    app = create_app(
        service=service,
        worker=worker,
        video_processor=VideoProcessor(),
        evidence_root=tmp_path / "evidence",
    )

    with TestClient(app) as client:
        response = client.post(
            "/videos/analyze",
            files={"video": ("drive.mp4", b"fake-video", "video/mp4")},
        )

    assert response.status_code == 202
    payload = response.json()
    assert payload["filename"] == "drive.mp4"
    assert payload["processed_frames"] == 30
    assert payload["source_video_url"].endswith("/source.mp4")
    assert payload["annotated_video_url"].endswith("/annotated.webm")
    assert payload["event"]["decision"]["alert_level"] == AlertLevel.WARNING
    assert payload["event"]["decision"]["should_alert"] is True
    assert payload["cached"] is False


def test_identical_video_upload_reuses_cached_inference(tmp_path: Path) -> None:
    service = EventService(Descriptor())
    processor = VideoProcessor()
    app = create_app(
        service=service,
        worker=DescriptionWorker(service),
        video_processor=processor,
        evidence_root=tmp_path / "evidence",
    )

    with TestClient(app) as client:
        first = client.post(
            "/videos/analyze",
            files={"video": ("first.mp4", b"same-video", "video/mp4")},
        )
        second = client.post(
            "/videos/analyze",
            files={"video": ("renamed.mp4", b"same-video", "video/mp4")},
        )
        health = client.get("/health")

    assert first.json()["cached"] is False
    assert second.json()["cached"] is True
    assert second.json()["filename"] == "renamed.mp4"
    assert second.json()["video_id"] == first.json()["video_id"]
    assert processor.calls == 1
    assert health.json()["video_cache_size"] == 1


def test_audio_upload_flows_into_animalclap_service(tmp_path: Path) -> None:
    service = EventService(Descriptor())
    app = create_app(
        service=service,
        worker=DescriptionWorker(service),
        video_processor=VideoProcessor(),
        audio_analyzer=AudioAnalyzer(),
        evidence_root=tmp_path / "evidence",
    )

    with TestClient(app) as client:
        response = client.post(
            "/audio/analyze",
            files={"audio": ("wildlife.ogg", b"fake-audio", "audio/ogg")},
        )

    assert response.status_code == 200
    analysis = response.json()["analysis"]
    assert analysis["possible_species"] == "coyote"
    assert analysis["message"] == (
        "Possible wildlife sound detected — possible species: coyote"
    )


def test_frontend_port_8001_is_allowed_by_cors(tmp_path: Path) -> None:
    service = EventService(Descriptor())
    app = create_app(
        service=service,
        worker=DescriptionWorker(service),
        video_processor=VideoProcessor(),
        evidence_root=tmp_path / "evidence",
    )

    with TestClient(app) as client:
        response = client.options(
            "/videos/analyze",
            headers={
                "Origin": "http://localhost:8001",
                "Access-Control-Request-Method": "POST",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == (
        "http://localhost:8001"
    )
