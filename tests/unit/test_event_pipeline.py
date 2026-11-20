import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest

from backend.alerts import evaluate_risk
from backend.orchestration import DescriptionWorker, EventService
from backend.orchestration.frame_selection import select_evidence_frames
from model_services.video.smolvlm.app import resolve_frame_paths
from model_services.video.smolvlm.prompt import parse_description
from shared.contracts import (
    AlertLevel,
    AudioEvidence,
    AudioEvidenceStatus,
    BoundingBox,
    DecisionReasonCode,
    DescriptionStatus,
    EventContext,
    PolicyConfig,
    SceneDescription,
    TrackedFrame,
    TrackEvidence,
    WildlifeEvent,
)

NOW = datetime(2026, 11, 20, 12, tzinfo=UTC)


def detection(
    *, frames: int = 4, confidence: float = 0.8, road_overlap: bool = True
) -> TrackEvidence:
    return TrackEvidence(
        label="animal",
        max_confidence=confidence,
        track_frames=frames,
        road_overlap=road_overlap,
        bounding_box=BoundingBox(x_min=1, y_min=2, x_max=3, y_max=4),
    )


def context(
    detections: list[TrackEvidence] | None = None,
    audio_evidence: AudioEvidence | None = None,
) -> EventContext:
    return EventContext(
        event_id="event-1",
        source="tesla-clip.mp4",
        timestamp=NOW,
        detections=[detection()] if detections is None else detections,
        audio_evidence=audio_evidence,
    )


def frame(path: str = "first.jpg") -> TrackedFrame:
    return TrackedFrame(path=path, timestamp_s=1, confidence=0.8)


def make_service(descriptor: object) -> EventService:
    return EventService(descriptor)  # type: ignore[arg-type]


def create_event(
    service: EventService,
    *,
    detections: list[TrackEvidence] | None = None,
    frames: list[TrackedFrame] | None = None,
    audio_evidence: AudioEvidence | None = None,
) -> tuple[WildlifeEvent, list[str]]:
    return service.create_event(
        source="tesla-clip.mp4",
        timestamp=NOW,
        detections=[detection()] if detections is None else detections,
        frames=[frame()] if frames is None else frames,
        audio_evidence=audio_evidence,
    )


def test_alert_does_not_depend_on_description() -> None:
    event = context(detections=[detection(road_overlap=True)])

    decision = evaluate_risk(event, PolicyConfig())

    assert decision.alert_level == AlertLevel.WARNING
    assert decision.should_alert is True
    assert decision.reason_codes == [
        DecisionReasonCode.PERSISTENT_ANIMAL_ON_ROAD
    ]


def test_decision_engine_is_deterministic() -> None:
    event = context()
    policy = PolicyConfig()

    assert evaluate_risk(event, policy) == evaluate_risk(event, policy)


def test_no_yolo_detections_does_not_alert() -> None:
    decision = evaluate_risk(context(detections=[]), PolicyConfig())

    assert decision.should_alert is False
    assert decision.alert_level == AlertLevel.NONE
    assert decision.reason_codes == [DecisionReasonCode.NO_DETECTIONS]


def test_animalclap_unavailable_does_not_block_visual_warning() -> None:
    event = context(
        audio_evidence=AudioEvidence(status=AudioEvidenceStatus.UNAVAILABLE)
    )

    decision = evaluate_risk(event, PolicyConfig())

    assert decision.alert_level == AlertLevel.WARNING
    assert decision.should_alert is True


def test_frame_selection_is_reproducible_and_deduplicates_timestamps() -> None:
    frames = [
        TrackedFrame(path="later.jpg", timestamp_s=4, confidence=0.7),
        TrackedFrame(path="best.jpg", timestamp_s=2, confidence=0.9),
        TrackedFrame(path="duplicate-low.jpg", timestamp_s=2, confidence=0.2),
        TrackedFrame(path="first.jpg", timestamp_s=1, confidence=0.5),
        TrackedFrame(path="middle.jpg", timestamp_s=3, confidence=0.6),
    ]

    selected = select_evidence_frames(frames)

    assert [item.path for item in selected] == [
        "first.jpg",
        "best.jpg",
        "later.jpg",
    ]
    assert [item.timestamp_s for item in selected] == [1, 2, 4]


class SuccessfulDescriptor:
    async def describe(
        self, frame_paths: list[str], detections: list[TrackEvidence]
    ) -> SceneDescription:
        assert frame_paths == ["first.jpg"]
        assert detections
        return SceneDescription(
            scene_description="An animal is visible beside the road.",
            animal_species="uncertain",
            road_position="roadside",
            observed_motion="uncertain",
            visibility="limited",
            uncertainties=["Species cannot be confirmed"],
        )


class InvalidJSONDescriptor:
    async def describe(
        self, frame_paths: list[str], detections: list[TrackEvidence]
    ) -> SceneDescription:
        del frame_paths, detections
        return parse_description("not JSON")


class StallingDescriptor:
    async def describe(
        self, frame_paths: list[str], detections: list[TrackEvidence]
    ) -> SceneDescription:
        del frame_paths, detections
        await asyncio.Event().wait()
        raise AssertionError("unreachable")


@pytest.mark.asyncio
async def test_successful_description_completes_in_background() -> None:
    service = make_service(SuccessfulDescriptor())
    worker = DescriptionWorker(service)
    event, paths = create_event(service)

    assert event.decision.should_alert is True
    assert event.description_status is DescriptionStatus.PENDING

    await worker.start()
    assert worker.submit(event.event_id, paths) is True
    await worker.wait_until_idle()
    updated = service.get_event(event.event_id)
    await worker.stop()

    assert updated is not None
    assert updated.description_status is DescriptionStatus.COMPLETED
    assert updated.description is not None


@pytest.mark.asyncio
async def test_invalid_vlm_json_fails_description_not_alert() -> None:
    service = make_service(InvalidJSONDescriptor())
    worker = DescriptionWorker(service)
    event, paths = create_event(service)

    await worker.start()
    worker.submit(event.event_id, paths)
    await worker.wait_until_idle()
    updated = service.get_event(event.event_id)
    await worker.stop()

    assert updated is not None
    assert updated.decision.alert_level is AlertLevel.WARNING
    assert updated.description_status is DescriptionStatus.FAILED
    assert "did not contain a JSON object" in (updated.description_error or "")


@pytest.mark.asyncio
async def test_description_timeout_does_not_delay_or_change_alert() -> None:
    service = make_service(StallingDescriptor())
    worker = DescriptionWorker(service, timeout_seconds=0.01)
    event, paths = create_event(service)

    assert event.decision.alert_level is AlertLevel.WARNING
    assert event.decision.should_alert is True

    await worker.start()
    worker.submit(event.event_id, paths)
    await worker.wait_until_idle()
    updated = service.get_event(event.event_id)
    await worker.stop()

    assert updated is not None
    assert updated.decision == event.decision
    assert updated.description_status is DescriptionStatus.FAILED
    assert updated.description_error == "description_timeout"


def test_no_usable_frames_skips_description_but_keeps_alert() -> None:
    service = make_service(SuccessfulDescriptor())

    event, paths = create_event(service, frames=[])

    assert paths == []
    assert event.decision.alert_level is AlertLevel.WARNING
    assert event.description_status is DescriptionStatus.SKIPPED


def test_description_queue_full_fails_only_description() -> None:
    service = make_service(SuccessfulDescriptor())
    worker = DescriptionWorker(service, max_queue_size=1)
    first, first_paths = create_event(service)
    second, second_paths = create_event(service)

    assert worker.submit(first.event_id, first_paths) is True
    assert worker.submit(second.event_id, second_paths) is False
    updated = service.get_event(second.event_id)

    assert updated is not None
    assert updated.decision.alert_level is AlertLevel.WARNING
    assert updated.description_status is DescriptionStatus.FAILED
    assert updated.description_error == "description_queue_full"


def test_no_detections_skips_description() -> None:
    service = make_service(SuccessfulDescriptor())

    event, paths = create_event(service, detections=[])

    assert paths == ["first.jpg"]
    assert event.decision.alert_level is AlertLevel.NONE
    assert event.description_status is DescriptionStatus.SKIPPED


def test_description_parser_accepts_fenced_json() -> None:
    parsed = parse_description(
        '```json\n{"scene_description":"Animal by road",'
        '"animal_species":"uncertain","road_position":"roadside",'
        '"observed_motion":"uncertain","visibility":"limited",'
        '"uncertainties":[]}\n```'
    )

    assert parsed.road_position == "roadside"


def test_description_parser_ignores_trailing_model_text() -> None:
    parsed = parse_description(
        '{"scene_description":"Animal by road",'
        '"animal_species":"uncertain","road_position":"roadside",'
        '"observed_motion":"uncertain","visibility":"limited",'
        '"uncertainties":[]}\n{"detector_metadata":true}'
    )

    assert parsed.scene_description == "Animal by road"


def test_description_parser_marks_omitted_fields_uncertain() -> None:
    parsed = parse_description('{"scene_description":"Animal by road"}')

    assert parsed.animal_species == "uncertain"
    assert parsed.road_position == "uncertain"
    assert parsed.observed_motion == "uncertain"
    assert parsed.visibility == "uncertain"
    assert parsed.uncertainties == [
        "Model omitted fields: animal_species, road_position, observed_motion, "
        "visibility"
    ]


def test_description_parser_rejects_invalid_json() -> None:
    with pytest.raises(ValueError, match="did not contain a JSON object"):
        parse_description("not JSON")


def test_frame_paths_cannot_escape_evidence_root(tmp_path: Path) -> None:
    evidence_root = tmp_path / "evidence"
    evidence_root.mkdir()
    outside = tmp_path / "outside.jpg"
    outside.touch()

    with pytest.raises(ValueError, match="inside the evidence"):
        resolve_frame_paths([str(outside)], evidence_root)
