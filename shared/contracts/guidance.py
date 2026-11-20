"""Contracts for source-grounded wildlife safety guidance."""

from enum import StrEnum

from pydantic import BaseModel, Field


class GuidanceStatus(StrEnum):
    SUPPORTED = "supported"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    SERVICE_UNAVAILABLE = "service_unavailable"


class SpeciesSource(StrEnum):
    USER_CONFIRMED = "user_confirmed"
    DETECTOR = "detector"
    VLM = "vlm"
    UNKNOWN = "unknown"


class UserContext(StrEnum):
    DRIVER = "driver"
    HIKER = "hiker"
    RANGER = "ranger"


class GuidanceRequest(BaseModel):
    event_id: str = Field(min_length=1)
    species: str = Field(min_length=1)
    species_source: SpeciesSource
    user_context: UserContext
    scene_context: str = Field(min_length=1)
    jurisdiction: str = "US-ME"
    question: str = Field(default="What should I do?", min_length=1)


class GuidanceCitation(BaseModel):
    passage_id: str
    title: str
    section: str
    url: str
    jurisdiction: str
    printed_page_label: str | None = None
    pdf_page_index_1based: int | None = Field(default=None, gt=0)


class GuidanceResponse(BaseModel):
    status: GuidanceStatus
    event_id: str
    species: str
    species_source: SpeciesSource
    user_context: UserContext
    scene_context: str
    guidance: list[str] = Field(default_factory=list)
    sources: list[GuidanceCitation] = Field(default_factory=list)
    message: str
