"""FastAPI service that isolates SmolVLM2 from the YOLO runtime."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Protocol

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from shared.contracts import SceneDescription, TrackEvidence


class DescribeRequest(BaseModel):
    frame_paths: list[str] = Field(min_length=1, max_length=3)
    detections: list[TrackEvidence] = Field(min_length=1)


class DescriptionRuntime(Protocol):
    def describe(
        self, frame_paths: list[Path], detections: list[TrackEvidence]
    ) -> SceneDescription: ...


def load_runtime() -> DescriptionRuntime:
    # Keep Transformers isolated from imports used by the main API and tests.
    from model_services.video.smolvlm.runtime import SmolVLMRuntime

    return SmolVLMRuntime()


def resolve_frame_paths(raw_paths: list[str], evidence_root: Path) -> list[Path]:
    paths = []
    root = evidence_root.resolve()
    for raw_path in raw_paths:
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = root / candidate
        resolved = candidate.resolve()
        if not resolved.is_relative_to(root):
            raise ValueError("Frame path must be inside the evidence directory")
        if not resolved.is_file():
            raise FileNotFoundError(resolved)
        paths.append(resolved)
    return paths


def create_app(
    runtime_factory: Callable[[], DescriptionRuntime] = load_runtime,
) -> FastAPI:
    evidence_root = Path(
        os.getenv("WILDGUARD_EVIDENCE_ROOT", "storage/evidence")
    )
    state: dict[str, DescriptionRuntime] = {}

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        state["runtime"] = await asyncio.to_thread(runtime_factory)
        yield

    app = FastAPI(title="WildGuard SmolVLM Service", lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok" if "runtime" in state else "loading"}

    @app.post("/describe", response_model=SceneDescription)
    async def describe(request: DescribeRequest) -> SceneDescription:
        try:
            paths = resolve_frame_paths(request.frame_paths, evidence_root)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except FileNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return await asyncio.to_thread(
            state["runtime"].describe,
            paths,
            request.detections,
        )

    return app


app = create_app()
