"""Stable structured-evidence contracts for WildGuard events."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from shared.contracts.detection import BoundingBox


class AlertLevel(StrEnum):
    NONE = "NONE"
    CAUTION = "CAUTION"
    WARNING = "WARNING"


class DecisionReasonCode(StrEnum):
    NO_DETECTIONS = "NO_DETECTIONS"
    BELOW_CONFIDENCE_THRESHOLD = "BELOW_CONFIDENCE_THRESHOLD"
    INSUFFICIENT_TRACK_PERSISTENCE = "INSUFFICIENT_TRACK_PERSISTENCE"
    PERSISTENT_ANIMAL_NEAR_ROAD = "PERSISTENT_ANIMAL_NEAR_ROAD"
    PERSISTENT_ANIMAL_ON_ROAD = "PERSISTENT_ANIMAL_ON_ROAD"


class DescriptionStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class AudioEvidenceStatus(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    NOT_PROVIDED = "not_provided"


class TrackEvidence(BaseModel):
    """Deterministic evidence produced by detection and tracking."""

    label: str
    max_confidence: float = Field(ge=0, le=1)
    track_frames: int = Field(gt=0)
    bounding_box: BoundingBox
    road_overlap: bool = False


class TrackedFrame(BaseModel):
    """One candidate evidence frame from a tracked event."""

    path: str = Field(min_length=1)
    timestamp_s: float = Field(ge=0)
    confidence: float = Field(ge=0, le=1)


class AudioEvidence(BaseModel):
    """Optional AnimalCLAP evidence; visual policy does not depend on it."""

    status: AudioEvidenceStatus = AudioEvidenceStatus.NOT_PROVIDED
    animal_sound_detected: bool | None = None
    possible_species: str | None = None


class EventContext(BaseModel):
    """Structured inputs consumed by the deterministic decision engine."""

    event_id: str
    source: str
    timestamp: datetime
    detections: list[TrackEvidence]
    audio_evidence: AudioEvidence | None = None


class PolicyConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    minimum_confidence: float = Field(default=0.5, ge=0, le=1)
    minimum_track_frames: int = Field(default=3, gt=0)


class AlertDecision(BaseModel):
    should_alert: bool
    alert_level: AlertLevel
    reason_codes: list[DecisionReasonCode]


class SceneDescription(BaseModel):
    """Validated, advisory VLM output; never an alert-policy input."""

    scene_description: str
    animal_species: str
    road_position: str
    observed_motion: str
    visibility: str
    uncertainties: list[str] = Field(default_factory=list)


class WildlifeEvent(BaseModel):
    event_id: str
    source: str
    timestamp: datetime
    detections: list[TrackEvidence]
    audio_evidence: AudioEvidence | None = None
    decision: AlertDecision
    description_status: DescriptionStatus
    description: SceneDescription | None = None
    description_error: str | None = None
