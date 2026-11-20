"""Validated loading for curated source and passage JSONL files."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field


class SourceRecord(BaseModel):
    source_id: str
    title: str
    jurisdiction: str
    source_type: str
    url: str
    verification_status: str
    checked_on: str


class PassageRecord(BaseModel):
    passage_id: str
    source_id: str
    jurisdiction: str
    section_path: str
    printed_page_label: str | None = None
    pdf_page_index_1based: int | None = Field(default=None, gt=0)
    text: str = Field(min_length=1)
    species: list[str] = Field(min_length=1)
    scenarios: list[str] = Field(min_length=1)
    safety_review_required: bool
    source_url: str


class KnowledgeBase:
    def __init__(
        self,
        sources: dict[str, SourceRecord],
        passages: list[PassageRecord],
    ) -> None:
        self.sources = sources
        self.passages = passages

    @classmethod
    def from_directory(cls, directory: Path) -> KnowledgeBase:
        sources = [
            SourceRecord.model_validate(row)
            for row in _read_jsonl(directory / "source_registry.jsonl")
        ]
        passages = [
            PassageRecord.model_validate(row)
            for row in _read_jsonl(directory / "tagged_passages.jsonl")
        ]
        source_map = {source.source_id: source for source in sources}
        if len(source_map) != len(sources):
            raise ValueError("Knowledge source IDs must be unique")
        passage_ids = {passage.passage_id for passage in passages}
        if len(passage_ids) != len(passages):
            raise ValueError("Knowledge passage IDs must be unique")
        missing = sorted(
            {passage.source_id for passage in passages} - set(source_map)
        )
        if missing:
            raise ValueError(f"Passages reference missing sources: {missing}")
        return cls(source_map, passages)


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.is_file():
        raise FileNotFoundError(path)
    rows = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"Invalid JSONL at {path}:{line_number}") from error
        if not isinstance(value, dict):
            raise ValueError(f"Expected JSON object at {path}:{line_number}")
        rows.append(value)
    if not rows:
        raise ValueError(f"Knowledge file is empty: {path}")
    return rows
