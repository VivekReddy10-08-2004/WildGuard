"""Isolated local API for AnimalCLAP wildlife-sound ranking."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Protocol

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from shared.contracts import WildlifeAudioAnalysis


class AnalyzeRequest(BaseModel):
    audio_path: str


class AudioRuntime(Protocol):
    def analyze(self, audio_path: Path) -> WildlifeAudioAnalysis: ...


def load_runtime() -> AudioRuntime:
    from model_services.audio.animalclap.runtime import AnimalCLAPRuntime

    return AnimalCLAPRuntime()


def resolve_audio_path(raw_path: str, evidence_root: Path) -> Path:
    root = evidence_root.resolve()
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("Audio path must be inside the evidence directory")
    if not resolved.is_file():
        raise FileNotFoundError(resolved)
    return resolved


def create_app(
    runtime_factory: Callable[[], AudioRuntime] = load_runtime,
) -> FastAPI:
    evidence_root = Path(os.getenv("WILDGUARD_EVIDENCE_ROOT", "storage/evidence"))
    state: dict[str, AudioRuntime] = {}
    inference_lock = asyncio.Lock()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        state["runtime"] = await asyncio.to_thread(runtime_factory)
        yield

    app = FastAPI(title="WildGuard AnimalCLAP Service", lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok" if "runtime" in state else "loading"}

    @app.post("/analyze", response_model=WildlifeAudioAnalysis)
    async def analyze(request: AnalyzeRequest) -> WildlifeAudioAnalysis:
        try:
            path = resolve_audio_path(request.audio_path, evidence_root)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except FileNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        async with inference_lock:
            return await asyncio.to_thread(state["runtime"].analyze, path)

    return app


app = create_app()
