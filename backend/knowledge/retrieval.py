"""Deterministic metadata-first retrieval for the curated starter corpus."""

from __future__ import annotations

import re

from backend.knowledge.ingestion import KnowledgeBase, PassageRecord
from shared.contracts import GuidanceRequest, SpeciesSource, UserContext

_TOKEN = re.compile(r"[a-z0-9]+")
_GENERIC_QUESTION_WORDS = {
    "a",
    "advice",
    "an",
    "can",
    "could",
    "do",
    "help",
    "how",
    "i",
    "my",
    "safety",
    "should",
    "the",
    "what",
    "when",
    "where",
    "why",
}
_ROADWAY_SCENARIOS = {
    "animal_in_road",
    "dawn_dusk",
    "habitat",
    "headlights",
    "multiple_animals",
    "night_visibility",
    "roadside_scanning",
    "speed",
    "standoff",
    "stay_in_vehicle",
    "stopping_distance",
    "warning_signs",
}
_IMMEDIATE_ROADWAY_SCENARIOS = {
    "animal_in_road",
    "standoff",
    "stay_in_vehicle",
}
_SUPPORTED_SPECIES = {"moose"}


class GuidanceRetriever:
    def __init__(self, knowledge: KnowledgeBase) -> None:
        self.knowledge = knowledge

    def retrieve(
        self, request: GuidanceRequest, *, limit: int = 4
    ) -> list[PassageRecord]:
        if request.user_context is not UserContext.DRIVER:
            return []
        species = _normalize(request.species)
        generic_detection = (
            request.species_source is SpeciesSource.DETECTOR
            and species == "animal"
        )
        if not generic_detection and (
            request.species_source is not SpeciesSource.USER_CONFIRMED
            or species not in _SUPPORTED_SPECIES
        ):
            return []

        scene_scenarios = (
            _ROADWAY_SCENARIOS
            if _normalize(request.scene_context) in {"road", "roadway", "roadside"}
            else {_normalize(request.scene_context)}
        )
        question_terms = _tokens(request.question) - _GENERIC_QUESTION_WORDS
        ranked: list[tuple[int, PassageRecord]] = []
        for passage in self.knowledge.passages:
            if passage.safety_review_required:
                continue
            if passage.jurisdiction != request.jurisdiction:
                continue
            normalized_species = {_normalize(value) for value in passage.species}
            if generic_detection:
                species_match = "unspecified_wildlife" in normalized_species
            else:
                species_match = (
                    species in normalized_species
                    or "unspecified_wildlife" in normalized_species
                )
            if not species_match:
                continue
            scenario_matches = scene_scenarios.intersection(passage.scenarios)
            if not scenario_matches:
                continue
            searchable = " ".join(
                [passage.text, passage.section_path, *passage.scenarios]
            )
            overlap = question_terms.intersection(_tokens(searchable))
            if question_terms and not overlap:
                continue
            source = self.knowledge.sources[passage.source_id]
            verification_score = {
                "page_text_verified": 3,
                "partial_text": 2,
                "search_text_verified": 1,
            }.get(source.verification_status, 0)
            score = (
                (10 if species in normalized_species else 2)
                + len(scenario_matches) * 3
                + len(scenario_matches & _IMMEDIATE_ROADWAY_SCENARIOS) * 5
                + len(overlap) * 2
                + verification_score
            )
            ranked.append((score, passage))
        ranked.sort(key=lambda item: (-item[0], item[1].passage_id))
        return [passage for _, passage in ranked[:limit]]


def _normalize(value: str) -> str:
    return "_".join(_TOKEN.findall(value.lower()))


def _tokens(value: str) -> set[str]:
    return set(_TOKEN.findall(value.lower()))
