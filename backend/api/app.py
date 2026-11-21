"""Local API: deterministic events plus queued advisory VLM enrichment."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import os
import shutil
from asyncio import to_thread
from collections import OrderedDict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal, Protocol
from uuid import uuid4

import httpx
from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from backend.api.animalclap_client import AnimalCLAPClient
from backend.api.schemas import (
    AudioAnalysisResponse,
    CreateEventRequest,
    SessionEventRecord,
    VideoAnalysisResponse,
)
from backend.api.session_report import (
    OllamaSessionReportGenerator,
    SessionReportGenerator,
)
from backend.api.smolvlm_client import SmolVLMClient
from backend.knowledge import GuidanceService
from backend.orchestration import DescriptionWorker, EventService
from backend.storage import LocalSessionStore
from model_services.video.yolo_tracker import VideoTrackingResult, YoloVideoProcessor
from shared.contracts import (
    DescriptionStatus,
    GuidanceRequest,
    GuidanceResponse,
    GuidanceStatus,
    WildlifeAudioAnalysis,
    WildlifeEvent,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOGGER = logging.getLogger(__name__)
DEFAULT_EVIDENCE_ROOT = PROJECT_ROOT / "storage/evidence"
DEFAULT_DATABASE_PATH = PROJECT_ROOT / "storage/wildguard.sqlite3"
DEFAULT_KNOWLEDGE_ROOT = PROJECT_ROOT / "data/artifacts"
VIDEO_SUFFIXES = {".avi", ".mkv", ".mov", ".mp4", ".webm"}
MAX_UPLOAD_BYTES = 500 * 1024 * 1024
AUDIO_SUFFIXES = {".flac", ".m4a", ".mp3", ".ogg", ".wav"}
MAX_AUDIO_UPLOAD_BYTES = 50 * 1024 * 1024
VIDEO_CACHE_LIMIT = 8


def persistent_video_cache_key(video_digest: str, processor_identity: str) -> str:
    """Version one uploaded video and the complete inference configuration."""

    value = f"video\0{video_digest}\0{processor_identity}".encode()
    return hashlib.sha256(value).hexdigest()


def cached_evidence_exists(
    response: VideoAnalysisResponse,
    evidence_root: Path,
    *,
    require_annotated: bool,
) -> bool:
    root = evidence_root.resolve()
    run_dir = (root / response.video_id).resolve()
    if not run_dir.is_relative_to(root) or not run_dir.is_dir():
        return False
    if not (run_dir / Path(response.source_video_url).name).is_file():
        return False
    if (
        require_annotated
        and response.annotated_video_url
        and not (run_dir / Path(response.annotated_video_url).name).is_file()
    ):
        return False
    return True


def video_session_event(
    response: VideoAnalysisResponse,
    *,
    filename: str,
    cached: bool,
) -> SessionEventRecord:
    score = max(
        (detection.max_confidence for detection in response.event.detections),
        default=0.0,
    )
    count = len(response.event.detections)
    return SessionEventRecord(
        id=uuid4().hex,
        created_at=datetime.now(UTC),
        modality="Video",
        source=filename,
        result=f"{count} tracked animal{'s' if count != 1 else ''}",
        model="YOLO26n + ByteTrack",
        score=score,
        decision=response.event.decision.alert_level.value,
        cached=cached,
        flow=[
            "Road video",
            "YOLO26n",
            "ByteTrack",
            "Decision engine",
            "Alert + guidance",
        ],
    )


def audio_session_event(response: AudioAnalysisResponse) -> SessionEventRecord:
    species = response.analysis.possible_species.replace("_", " ").title()
    return SessionEventRecord(
        id=uuid4().hex,
        created_at=datetime.now(UTC),
        modality="Audio",
        source=response.filename,
        result=f"Possible {species}",
        model="AnimalCLAP",
        score=response.analysis.similarity,
        decision="CAUTION",
        cached=False,
        flow=[
            "Audio clip",
            "AnimalCLAP",
            "Species ranking",
            "Caution",
            "Phone + watch",
        ],
    )


class VideoProcessor(Protocol):
    def process(self, video_path: Path, evidence_dir: Path) -> VideoTrackingResult: ...

    def render_annotated(
        self, video_path: Path, result: VideoTrackingResult
    ) -> None: ...


class AudioAnalyzer(Protocol):
    async def analyze(self, audio_path: Path) -> WildlifeAudioAnalysis: ...


class GuidanceProvider(Protocol):
    def guide(self, request: GuidanceRequest) -> GuidanceResponse: ...


async def save_upload(
    upload: UploadFile,
    destination: Path,
    *,
    max_bytes: int,
    size_label: str,
    calculate_sha256: bool = False,
) -> str | None:
    size = 0
    digest = hashlib.sha256() if calculate_sha256 else None
    try:
        with destination.open("wb") as output:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(status_code=413, detail=size_label)
                output.write(chunk)
                if digest is not None:
                    digest.update(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()
    return digest.hexdigest() if digest is not None else None


def render_video_preview(
    processor: VideoProcessor,
    video_path: Path,
    result: VideoTrackingResult,
) -> None:
    try:
        processor.render_annotated(video_path, result)
    except Exception:
        LOGGER.exception("Annotated video rendering failed for %s", video_path)


def create_app(
    service: EventService | None = None,
    worker: DescriptionWorker | None = None,
    video_processor: VideoProcessor | None = None,
    audio_analyzer: AudioAnalyzer | None = None,
    guidance_provider: GuidanceProvider | None = None,
    evidence_root: Path = DEFAULT_EVIDENCE_ROOT,
    knowledge_root: Path = DEFAULT_KNOWLEDGE_ROOT,
    database_path: Path | None = None,
    session_report_generator: SessionReportGenerator | None = None,
) -> FastAPI:
    event_service = service or EventService(
        SmolVLMClient(os.getenv("SMOLVLM_URL", "http://127.0.0.1:8011"))
    )
    description_worker = worker or DescriptionWorker(event_service)
    wildlife_audio = audio_analyzer or AnimalCLAPClient(
        os.getenv("ANIMALCLAP_URL", "http://127.0.0.1:8012")
    )
    report_generator = session_report_generator or OllamaSessionReportGenerator(
        base_url=os.getenv("OLLAMA_URL", "http://127.0.0.1:11434"),
        model_name=os.getenv("WILDGUARD_EXPORT_MODEL", "qwen2.5-coder:7b"),
    )
    if guidance_provider is None:
        try:
            guidance_provider = GuidanceService.from_directory(knowledge_root)
        except (FileNotFoundError, ValueError):
            guidance_provider = None
    processors: dict[str, VideoProcessor] = {}
    video_cache: OrderedDict[tuple[str, str], VideoAnalysisResponse] = OrderedDict()
    if video_processor is not None:
        processors["video"] = video_processor
    evidence_root.mkdir(parents=True, exist_ok=True)
    session_store = LocalSessionStore(
        database_path
        or (
            DEFAULT_DATABASE_PATH
            if evidence_root == DEFAULT_EVIDENCE_ROOT
            else evidence_root.parent / "wildguard.sqlite3"
        )
    )

    def remember_video_response(
        key: tuple[str, str], response: VideoAnalysisResponse
    ) -> None:
        video_cache[key] = response
        video_cache.move_to_end(key)
        if len(video_cache) > VIDEO_CACHE_LIMIT:
            video_cache.popitem(last=False)

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
            "http://localhost:8001",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:8000",
            "http://127.0.0.1:8001",
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
            "video_cache_size": len(video_cache),
            "persistent_video_cache_size": await to_thread(session_store.cache_count),
            "session_event_count": await to_thread(session_store.event_count),
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
        background_tasks: BackgroundTasks,
        video: Annotated[UploadFile, File(description="A short driving video")],
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
        video_digest = await save_upload(
            video,
            upload_path,
            max_bytes=MAX_UPLOAD_BYTES,
            size_label="Video exceeds 500 MB",
            calculate_sha256=True,
        )
        assert video_digest is not None
        processor = processors["video"]
        processor_identity = str(
            getattr(
                processor,
                "cache_identity",
                f"{type(processor).__module__}.{type(processor).__qualname__}",
            )
        )
        cache_key = (video_digest, processor_identity)
        database_cache_key = persistent_video_cache_key(
            video_digest, processor_identity
        )
        cached_response = video_cache.get(cache_key)
        if cached_response is not None:
            if cached_evidence_exists(
                cached_response,
                evidence_root,
                require_annotated=False,
            ):
                video_cache.move_to_end(cache_key)
                shutil.rmtree(run_dir)
                current_event = (
                    event_service.get_event(cached_response.event.event_id)
                    or cached_response.event
                )
                response = cached_response.model_copy(
                    update={
                        "cached": True,
                        "event": current_event,
                        "filename": filename,
                    }
                )
                await to_thread(session_store.record_cache_hit, database_cache_key)
                await to_thread(
                    session_store.record_session_event,
                    video_session_event(
                        response, filename=filename, cached=True
                    ).model_dump(mode="json"),
                )
                return response
            del video_cache[cache_key]

        stored_analysis = await to_thread(
            session_store.get_analysis, database_cache_key
        )
        if stored_analysis is not None:
            try:
                persistent_response = VideoAnalysisResponse.model_validate_json(
                    stored_analysis.response_json
                )
            except ValueError:
                await to_thread(session_store.delete_analysis, database_cache_key)
            else:
                if cached_evidence_exists(
                    persistent_response,
                    evidence_root,
                    require_annotated=True,
                ):
                    shutil.rmtree(run_dir)
                    event = persistent_response.event
                    if event.description_status is DescriptionStatus.PENDING:
                        event = event.model_copy(
                            update={
                                "description_status": DescriptionStatus.SKIPPED,
                                "description_error": (
                                    "description_not_resumed_from_cache"
                                ),
                            }
                        )
                    response = persistent_response.model_copy(
                        update={
                            "cached": True,
                            "event": event,
                            "filename": filename,
                        }
                    )
                    remember_video_response(cache_key, response)
                    await to_thread(session_store.record_cache_hit, database_cache_key)
                    await to_thread(
                        session_store.record_session_event,
                        video_session_event(
                            response, filename=filename, cached=True
                        ).model_dump(mode="json"),
                    )
                    return response
                await to_thread(session_store.delete_analysis, database_cache_key)
        try:
            result = await to_thread(
                processor.process,
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
        if result.annotated_video_path:
            background_tasks.add_task(
                render_video_preview,
                processors["video"],
                upload_path,
                result,
            )
        response = VideoAnalysisResponse(
            video_id=video_id,
            filename=filename,
            processed_frames=result.processed_frames,
            fps=result.fps,
            duration_seconds=result.duration_seconds,
            source_video_url=f"/evidence/{video_id}/{upload_path.name}",
            annotated_video_url=(
                f"/evidence/{video_id}/{Path(result.annotated_video_path).name}"
                if result.annotated_video_path
                else None
            ),
            evidence_urls=[
                f"/evidence/{video_id}/{Path(frame.path).name}"
                for frame in result.frames
            ],
            event=current_event,
        )
        remember_video_response(cache_key, response)
        await to_thread(
            session_store.put_analysis,
            cache_key=database_cache_key,
            modality="video",
            input_digest=video_digest,
            model_identity=processor_identity,
            response_json=response.model_dump_json(),
            evidence_dir=video_id,
        )
        await to_thread(
            session_store.record_session_event,
            video_session_event(response, filename=filename, cached=False).model_dump(
                mode="json"
            ),
        )
        return response

    @app.post("/audio/analyze", response_model=AudioAnalysisResponse)
    async def analyze_audio(
        audio: Annotated[UploadFile, File(description="A short wildlife audio clip")],
    ) -> AudioAnalysisResponse:
        filename = audio.filename or "audio.wav"
        suffix = Path(filename).suffix.lower()
        if suffix not in AUDIO_SUFFIXES:
            await audio.close()
            raise HTTPException(status_code=415, detail="Unsupported audio format")

        audio_id = uuid4().hex
        run_dir = evidence_root / "audio" / audio_id
        run_dir.mkdir(parents=True)
        upload_path = run_dir / f"source{suffix}"
        await save_upload(
            audio,
            upload_path,
            max_bytes=MAX_AUDIO_UPLOAD_BYTES,
            size_label="Audio exceeds 50 MB",
        )
        try:
            analysis = await wildlife_audio.analyze(upload_path)
        except (httpx.HTTPError, TimeoutError) as error:
            raise HTTPException(
                status_code=503,
                detail="AnimalCLAP service is unavailable",
            ) from error
        response = AudioAnalysisResponse(
            audio_id=audio_id,
            filename=filename,
            analysis=analysis,
        )
        await to_thread(
            session_store.record_session_event,
            audio_session_event(response).model_dump(mode="json"),
        )
        return response

    @app.get("/session/events", response_model=list[SessionEventRecord])
    async def list_session_events(limit: int = 50) -> list[SessionEventRecord]:
        records = await to_thread(
            session_store.list_session_events,
            limit=max(1, min(limit, 100)),
        )
        return [SessionEventRecord.model_validate(record) for record in records]

    @app.get("/session/events/export")
    async def export_session_events(
        format: Literal["json", "csv", "ai"] = "json",
    ) -> Response:
        records = await to_thread(session_store.list_session_events, limit=100)
        timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        if format == "json":
            content = json.dumps(records, indent=2, ensure_ascii=True)
            media_type = "application/json"
            suffix = "json"
        elif format == "csv":
            output = io.StringIO()
            fields = [
                "id",
                "created_at",
                "modality",
                "source",
                "result",
                "model",
                "score",
                "decision",
                "cached",
                "flow",
            ]
            writer = csv.DictWriter(output, fieldnames=fields)
            writer.writeheader()
            for record in records:
                row = {field: record.get(field, "") for field in fields}
                row["flow"] = " -> ".join(record.get("flow", []))
                writer.writerow(row)
            content = output.getvalue()
            media_type = "text/csv"
            suffix = "csv"
        else:
            if not records:
                raise HTTPException(
                    status_code=422,
                    detail="Run an audio or video analysis before generating a report",
                )
            try:
                content = await report_generator.generate(records)
            except (httpx.HTTPError, TimeoutError, ValueError) as error:
                raise HTTPException(
                    status_code=503,
                    detail="The local AI report model is unavailable",
                ) from error
            media_type = "text/markdown"
            suffix = "md"

        headers = {
            "Content-Disposition": (
                f'attachment; filename="wildguard-session-{timestamp}.{suffix}"'
            )
        }
        if format == "ai":
            headers["X-WildGuard-Model"] = report_generator.model_name
        return Response(content=content, media_type=media_type, headers=headers)

    @app.delete("/session/events")
    async def clear_session_events() -> dict[str, int]:
        return {"cleared": await to_thread(session_store.clear_session_events)}

    @app.post("/guidance", response_model=GuidanceResponse)
    async def get_guidance(request: GuidanceRequest) -> GuidanceResponse:
        if guidance_provider is None:
            return GuidanceResponse(
                status=GuidanceStatus.SERVICE_UNAVAILABLE,
                event_id=request.event_id,
                species=request.species,
                species_source=request.species_source,
                user_context=request.user_context,
                scene_context=request.scene_context,
                message="The local guidance source files are unavailable.",
            )
        return await to_thread(guidance_provider.guide, request)

    @app.get("/events/{event_id}", response_model=WildlifeEvent)
    async def get_event(event_id: str) -> WildlifeEvent:
        event = event_service.get_event(event_id)
        if event is None:
            raise HTTPException(status_code=404, detail="Event not found")
        return event

    return app


app = create_app()
