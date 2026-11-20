"""Local API: deterministic events plus queued advisory VLM enrichment."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status

from backend.api.schemas import CreateEventRequest
from backend.api.smolvlm_client import SmolVLMClient
from backend.orchestration import DescriptionWorker, EventService
from shared.contracts import DescriptionStatus, WildlifeEvent


def create_app(
    service: EventService | None = None,
    worker: DescriptionWorker | None = None,
) -> FastAPI:
    event_service = service or EventService(
        SmolVLMClient(os.getenv("SMOLVLM_URL", "http://127.0.0.1:8011"))
    )
    description_worker = worker or DescriptionWorker(event_service)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await description_worker.start()
        yield
        await description_worker.stop()

    app = FastAPI(title="WildGuard API", version="0.1.0", lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict[str, str | int]:
        return {
            "status": "ok",
            "description_queue_size": description_worker.queue.qsize(),
        }

    @app.post(
        "/events",
        response_model=WildlifeEvent,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def create_event(request: CreateEventRequest) -> WildlifeEvent:
        event, frame_paths = event_service.create_event(
            source=request.source,
            timestamp=request.timestamp,
            detections=request.detections,
            frames=request.frames,
            audio_evidence=request.audio_evidence,
        )
        if event.description_status is DescriptionStatus.PENDING:
            description_worker.submit(event.event_id, frame_paths)
        return event_service.get_event(event.event_id) or event

    @app.get("/events/{event_id}", response_model=WildlifeEvent)
    async def get_event(event_id: str) -> WildlifeEvent:
        event = event_service.get_event(event_id)
        if event is None:
            raise HTTPException(status_code=404, detail="Event not found")
        return event

    return app


app = create_app()
