"""Local API: deterministic events plus queued advisory VLM enrichment."""

from __future__ import annotations

import os
import shutil
from asyncio import to_thread
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Protocol
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.api.schemas import CreateEventRequest, VideoAnalysisResponse
from backend.api.smolvlm_client import SmolVLMClient
from backend.orchestration import DescriptionWorker, EventService
from model_services.video.yolo_tracker import VideoTrackingResult, YoloVideoProcessor
from shared.contracts import DescriptionStatus, WildlifeEvent

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EVIDENCE_ROOT = PROJECT_ROOT / "storage/evidence"
VIDEO_SUFFIXES = {".avi", ".mkv", ".mov", ".mp4", ".webm"}
MAX_UPLOAD_BYTES = 500 * 1024 * 1024


class VideoProcessor(Protocol):
    def process(
        self, video_path: Path, evidence_dir: Path
    ) -> VideoTrackingResult: ...


async def save_video_upload(upload: UploadFile, destination: Path) -> None:
    size = 0
    try:
        with destination.open("wb") as output:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="Video exceeds 500 MB")
                output.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()


def create_app(
    service: EventService | None = None,
    worker: DescriptionWorker | None = None,
    video_processor: VideoProcessor | None = None,
    evidence_root: Path = DEFAULT_EVIDENCE_ROOT,
) -> FastAPI:
    event_service = service or EventService(
        SmolVLMClient(os.getenv("SMOLVLM_URL", "http://127.0.0.1:8011"))
    )
    description_worker = worker or DescriptionWorker(event_service)
    processors: dict[str, VideoProcessor] = {}
    if video_processor is not None:
        processors["video"] = video_processor
    evidence_root.mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if "video" not in processors:
            processors["video"] = await to_thread(YoloVideoProcessor)
        await description_worker.start()
        yield
        await description_worker.stop()

    app = FastAPI(title="WildGuard API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://localhost:5173",
            "http://localhost:8000",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:8000",
        ],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.mount("/evidence", StaticFiles(directory=evidence_root), name="evidence")

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

    @app.post(
        "/videos/analyze",
        response_model=VideoAnalysisResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def analyze_video(
        video: Annotated[UploadFile, File(description="A short driving video")]
    ) -> VideoAnalysisResponse:
        filename = video.filename or "video.mp4"
        suffix = Path(filename).suffix.lower()
        if suffix not in VIDEO_SUFFIXES:
            await video.close()
            raise HTTPException(status_code=415, detail="Unsupported video format")

        video_id = uuid4().hex
        run_dir = evidence_root / video_id
        run_dir.mkdir(parents=True)
        upload_path = run_dir / f"source{suffix}"
        await save_video_upload(video, upload_path)
        try:
            result = await to_thread(
                processors["video"].process,
                upload_path,
                run_dir,
            )
        except ValueError as error:
            shutil.rmtree(run_dir, ignore_errors=True)
            raise HTTPException(status_code=422, detail=str(error)) from error

        event, frame_paths = event_service.create_event(
            source=filename,
            timestamp=datetime.now(UTC),
            detections=result.detections,
            frames=result.frames,
        )
        if event.description_status is DescriptionStatus.PENDING:
            description_worker.submit(event.event_id, frame_paths)
        current_event = event_service.get_event(event.event_id) or event
        return VideoAnalysisResponse(
            video_id=video_id,
            filename=filename,
            processed_frames=result.processed_frames,
            fps=result.fps,
            duration_seconds=result.duration_seconds,
            evidence_urls=[
                f"/evidence/{video_id}/{Path(frame.path).name}"
                for frame in result.frames
            ],
            event=current_event,
        )

    @app.get("/events/{event_id}", response_model=WildlifeEvent)
    async def get_event(event_id: str) -> WildlifeEvent:
        event = event_service.get_event(event_id)
        if event is None:
            raise HTTPException(status_code=404, detail="Event not found")
        return event

    return app


app = create_app()
