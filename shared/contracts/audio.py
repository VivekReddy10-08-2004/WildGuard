"""Structured output from the advisory wildlife-audio classifier."""

from pydantic import BaseModel, Field


class SpeciesRanking(BaseModel):
    species: str
    similarity: float


class WildlifeAudioAnalysis(BaseModel):
    status: str = "possible_wildlife_sound"
    possible_species: str
    similarity: float
    score_margin: float = Field(ge=0)
    message: str
    rankings: list[SpeciesRanking]
