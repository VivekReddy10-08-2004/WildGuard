from pathlib import Path

from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.orchestration import DescriptionWorker, EventService
from model_services.video.yolo_tracker import (
    TrackObservation,
    VideoTrackingResult,
    aggregate_tracks,
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
    def process(self, video_path: Path, evidence_dir: Path) -> VideoTrackingResult:
        assert video_path.is_file()
        assert evidence_dir == video_path.parent
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
        )


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
    assert payload["event"]["decision"]["alert_level"] == AlertLevel.WARNING
    assert payload["event"]["decision"]["should_alert"] is True


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
