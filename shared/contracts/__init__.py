"""Stable data contracts shared across services."""

from shared.contracts.audio import SpeciesRanking, WildlifeAudioAnalysis
from shared.contracts.detection import BoundingBox, Detection, ImagePrediction
from shared.contracts.event import (
    AlertDecision,
    AlertLevel,
    AudioEvidence,
    AudioEvidenceStatus,
    DecisionReasonCode,
    DescriptionStatus,
    EventContext,
    PolicyConfig,
    SceneDescription,
    TrackedFrame,
    TrackEvidence,
    WildlifeEvent,
)

__all__ = [
    "AlertDecision",
    "AlertLevel",
    "AudioEvidence",
    "AudioEvidenceStatus",
    "BoundingBox",
    "DecisionReasonCode",
    "DescriptionStatus",
    "Detection",
    "EventContext",
    "ImagePrediction",
    "PolicyConfig",
    "SceneDescription",
    "SpeciesRanking",
    "TrackedFrame",
    "TrackEvidence",
    "WildlifeAudioAnalysis",
    "WildlifeEvent",
]

