"""Constrained WildGuard prompt and output parsing for SmolVLM2."""

from __future__ import annotations

import json

from pydantic import ValidationError

from shared.contracts import SceneDescription, TrackEvidence


def build_prompt(detections: list[TrackEvidence]) -> str:
    context = json.dumps(
        [detection.model_dump(mode="json") for detection in detections],
        separators=(",", ":"),
    )
    return f"""You are WildGuard's wildlife scene description model.

Analyze the provided chronological frames and detector evidence: {context}

Return only one JSON object with these fields:
- scene_description: short visible-scene description
- animal_species: possible species, or "uncertain"
- road_position: visible position relative to the road, or "uncertain"
- observed_motion: motion clearly visible across frames, or "uncertain"
- visibility: relevant visibility limitations, or "clear"
- uncertainties: JSON list of unsupported or ambiguous details

Rules:
- Do not invent animals that are not visible.
- Do not estimate exact distance, speed, collision probability, or alert level.
- Treat detector evidence as metadata, not proof of species.
- Distinguish observations from uncertainty.
"""


def parse_description(text: str) -> SceneDescription:
    start = text.find("{")
    if start < 0:
        raise ValueError("SmolVLM response did not contain a JSON object")
    try:
        payload, _ = json.JSONDecoder().raw_decode(text[start:])
        if not isinstance(payload, dict):
            raise ValueError("SmolVLM JSON response was not an object")
        normalized = dict(payload)
        required_defaults = {
            "animal_species": "uncertain",
            "road_position": "uncertain",
            "observed_motion": "uncertain",
            "visibility": "uncertain",
        }
        omitted = [field for field in required_defaults if field not in normalized]
        for field in omitted:
            normalized[field] = required_defaults[field]
        uncertainties = normalized.get("uncertainties")
        if not isinstance(uncertainties, list) or not all(
            isinstance(item, str) for item in uncertainties
        ):
            uncertainties = []
        if omitted:
            uncertainties.append(f"Model omitted fields: {', '.join(omitted)}")
        normalized["uncertainties"] = uncertainties
        return SceneDescription.model_validate(normalized)
    except (json.JSONDecodeError, ValidationError) as error:
        raise ValueError("SmolVLM response did not match the schema") from error
