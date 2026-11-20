"""Create deterministic events and manage advisory description state."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import uuid4

from backend.alerts import evaluate_risk
from backend.orchestration.frame_selection import select_evidence_frames
from shared.contracts import (
    AudioEvidence,
    DescriptionStatus,
    EventContext,
    PolicyConfig,
    SceneDescription,
    TrackedFrame,
    TrackEvidence,
    WildlifeEvent,
)


class SceneDescriptor(Protocol):
    async def describe(
        self, frame_paths: list[str], detections: list[TrackEvidence]
    ) -> SceneDescription: ...


class EventService:
    def __init__(
        self,
        descriptor: SceneDescriptor,
        policy_config: PolicyConfig | None = None,
    ) -> None:
        self.descriptor = descriptor
        self.policy_config = policy_config or PolicyConfig()
        self.events: dict[str, WildlifeEvent] = {}

    def create_event(
        self,
        *,
        source: str,
        timestamp: datetime,
        detections: list[TrackEvidence],
        frames: list[TrackedFrame],
        audio_evidence: AudioEvidence | None = None,
    ) -> tuple[WildlifeEvent, list[str]]:
        event_id = str(uuid4())
        context = EventContext(
            event_id=event_id,
            source=source,
            timestamp=timestamp,
            detections=detections,
            audio_evidence=audio_evidence,
        )
        selected = select_evidence_frames(frames)
        frame_paths = [frame.path for frame in selected]
        description_status = (
            DescriptionStatus.PENDING
            if detections and frame_paths
            else DescriptionStatus.SKIPPED
        )
        event = WildlifeEvent(
            **context.model_dump(),
            decision=evaluate_risk(context, self.policy_config),
            description_status=description_status,
        )
        self.events[event.event_id] = event
        return event, frame_paths

    async def describe_event(
        self, event_id: str, frame_paths: list[str]
    ) -> SceneDescription:
        event = self.events[event_id]
        return await self.descriptor.describe(frame_paths, event.detections)

    def complete_description(
        self, event_id: str, description: SceneDescription
    ) -> WildlifeEvent:
        return self._update_description(
            event_id,
            status=DescriptionStatus.COMPLETED,
            description=description,
        )

    def fail_description(self, event_id: str, error: str) -> WildlifeEvent:
        return self._update_description(
            event_id,
            status=DescriptionStatus.FAILED,
            error=error,
        )

    def _update_description(
        self,
        event_id: str,
        *,
        status: DescriptionStatus,
        description: SceneDescription | None = None,
        error: str | None = None,
    ) -> WildlifeEvent:
        event = self.events[event_id]
        updated = event.model_copy(
            update={
                "description_status": status,
                "description": description,
                "description_error": error,
            }
        )
        self.events[event_id] = updated
        return updated

    def get_event(self, event_id: str) -> WildlifeEvent | None:
        return self.events.get(event_id)
