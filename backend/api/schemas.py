from datetime import datetime

from pydantic import BaseModel

from shared.contracts import AudioEvidence, TrackedFrame, TrackEvidence


class CreateEventRequest(BaseModel):
    source: str
    timestamp: datetime
    detections: list[TrackEvidence]
    frames: list[TrackedFrame]
    audio_evidence: AudioEvidence | None = None
