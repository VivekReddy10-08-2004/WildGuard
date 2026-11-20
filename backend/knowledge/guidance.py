"""Evidence-only guidance responses with validated citations and abstention."""

from __future__ import annotations

from pathlib import Path

from backend.knowledge.ingestion import KnowledgeBase
from backend.knowledge.retrieval import GuidanceRetriever
from shared.contracts import (
    GuidanceCitation,
    GuidanceRequest,
    GuidanceResponse,
    GuidanceStatus,
)


class GuidanceService:
    def __init__(self, knowledge: KnowledgeBase) -> None:
        self.knowledge = knowledge
        self.retriever = GuidanceRetriever(knowledge)
        self._cache: dict[tuple[str, ...], GuidanceResponse] = {}

    @classmethod
    def from_directory(cls, directory: Path) -> GuidanceService:
        return cls(KnowledgeBase.from_directory(directory))

    @property
    def cache_size(self) -> int:
        return len(self._cache)

    def guide(self, request: GuidanceRequest) -> GuidanceResponse:
        key = (
            request.event_id,
            request.species.lower(),
            request.species_source,
            request.user_context,
            request.scene_context.lower(),
            request.jurisdiction,
            request.question.lower().strip(),
        )
        if key in self._cache:
            return self._cache[key]

        passages = self.retriever.retrieve(request)
        if not passages:
            response = GuidanceResponse(
                status=GuidanceStatus.INSUFFICIENT_EVIDENCE,
                event_id=request.event_id,
                species=request.species,
                species_source=request.species_source,
                user_context=request.user_context,
                scene_context=request.scene_context,
                message="No verified guidance was found for this species and context.",
            )
        else:
            citations = []
            for passage in passages:
                source = self.knowledge.sources[passage.source_id]
                citations.append(
                    GuidanceCitation(
                        passage_id=passage.passage_id,
                        title=source.title,
                        section=passage.section_path,
                        url=source.url,
                        jurisdiction=passage.jurisdiction,
                        printed_page_label=passage.printed_page_label,
                        pdf_page_index_1based=passage.pdf_page_index_1based,
                    )
                )
            response = GuidanceResponse(
                status=GuidanceStatus.SUPPORTED,
                event_id=request.event_id,
                species=request.species,
                species_source=request.species_source,
                user_context=request.user_context,
                scene_context=request.scene_context,
                guidance=[passage.text for passage in passages],
                sources=citations,
                message="Verified source passages are available for this context.",
            )
        self._cache[key] = response
        return response
