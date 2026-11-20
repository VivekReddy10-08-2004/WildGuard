from datetime import datetime

from pydantic import BaseModel

from shared.contracts import (
    AudioEvidence,
    TrackedFrame,
    TrackEvidence,
    WildlifeAudioAnalysis,
    WildlifeEvent,
)


class CreateEventRequest(BaseModel):
    source: str
    timestamp: datetime
    detections: list[TrackEvidence]
    frames: list[TrackedFrame]
    audio_evidence: AudioEvidence | None = None


class VideoAnalysisResponse(BaseModel):
    video_id: str
    filename: str
    processed_frames: int
    fps: float
    duration_seconds: float
    evidence_urls: list[str]
    event: WildlifeEvent


class AudioAnalysisResponse(BaseModel):
    audio_id: str
    filename: str
    analysis: WildlifeAudioAnalysis
