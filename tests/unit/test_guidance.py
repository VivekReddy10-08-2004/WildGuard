from pathlib import Path

from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.knowledge import GuidanceService
from backend.orchestration import DescriptionWorker, EventService
from shared.contracts import (
    GuidanceRequest,
    GuidanceStatus,
    SceneDescription,
    SpeciesSource,
    TrackEvidence,
    UserContext,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def request(
    *,
    species: str = "moose",
    species_source: SpeciesSource = SpeciesSource.USER_CONFIRMED,
    user_context: UserContext = UserContext.DRIVER,
    question: str = "What should I do?",
) -> GuidanceRequest:
    return GuidanceRequest(
        event_id="event-1",
        species=species,
        species_source=species_source,
        user_context=user_context,
        scene_context="roadway",
        jurisdiction="US-ME",
        question=question,
    )


def service() -> GuidanceService:
    return GuidanceService.from_directory(PROJECT_ROOT / "data/artifacts")


def test_verified_moose_driver_guidance_has_citations() -> None:
    response = service().guide(request())

    assert response.status is GuidanceStatus.SUPPORTED
    assert [source.passage_id for source in response.sources[:2]] == [
        "ME_DOT_010",
        "ME_DOT_011",
    ]
    assert len(response.guidance) == len(response.sources)
    assert all(
        source.url.startswith("https://www.maine.gov/")
        for source in response.sources
    )


def test_guidance_abstains_without_confirmed_supported_context() -> None:
    guidance = service()

    assert guidance.guide(
        request(species="black bear", user_context=UserContext.HIKER)
    ).status is GuidanceStatus.INSUFFICIENT_EVIDENCE
    assert guidance.guide(
        request(species="black bear")
    ).status is GuidanceStatus.INSUFFICIENT_EVIDENCE
    assert guidance.guide(request(species="deer")).status is (
        GuidanceStatus.INSUFFICIENT_EVIDENCE
    )
    assert guidance.guide(
        request(question="How do I repair a tire?")
    ).status is GuidanceStatus.INSUFFICIENT_EVIDENCE


def test_detector_animal_uses_only_generic_roadway_guidance() -> None:
    response = service().guide(
        request(species="animal", species_source=SpeciesSource.DETECTOR)
    )

    assert response.status is GuidanceStatus.SUPPORTED
    assert response.guidance
    assert all(
        source.passage_id in {"ME_DOT_005", "ME_DOT_006", "ME_DOT_009"}
        for source in response.sources
    )


def test_repeated_guidance_request_uses_cache() -> None:
    guidance = service()
    query = request()

    first = guidance.guide(query)
    second = guidance.guide(query)

    assert first == second
    assert guidance.cache_size == 1


class Descriptor:
    async def describe(
        self, frame_paths: list[str], detections: list[TrackEvidence]
    ) -> SceneDescription:
        del frame_paths, detections
        raise AssertionError("Description service should not be called")


class VideoProcessor:
    def process(self, video_path: Path, evidence_dir: Path) -> object:
        del video_path, evidence_dir
        raise AssertionError("Video processor should not be called")


def test_guidance_endpoint_reports_missing_local_sources(tmp_path: Path) -> None:
    event_service = EventService(Descriptor())
    app = create_app(
        service=event_service,
        worker=DescriptionWorker(event_service),
        video_processor=VideoProcessor(),  # type: ignore[arg-type]
        evidence_root=tmp_path / "evidence",
        knowledge_root=tmp_path / "missing",
    )

    with TestClient(app) as client:
        response = client.post("/guidance", json=request().model_dump(mode="json"))

    assert response.status_code == 200
    assert response.json()["status"] == GuidanceStatus.SERVICE_UNAVAILABLE


def test_guidance_endpoint_returns_supported_local_passages(tmp_path: Path) -> None:
    event_service = EventService(Descriptor())
    app = create_app(
        service=event_service,
        worker=DescriptionWorker(event_service),
        video_processor=VideoProcessor(),  # type: ignore[arg-type]
        guidance_provider=service(),
        evidence_root=tmp_path / "evidence",
    )

    with TestClient(app) as client:
        response = client.post("/guidance", json=request().model_dump(mode="json"))

    assert response.status_code == 200
    assert response.json()["status"] == GuidanceStatus.SUPPORTED
    assert response.json()["sources"][0]["passage_id"] == "ME_DOT_010"
