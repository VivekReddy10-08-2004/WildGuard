"""HTTP client for the isolated local SmolVLM service."""

from __future__ import annotations

import httpx

from shared.contracts import SceneDescription, TrackEvidence


class SmolVLMClient:
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8011",
        timeout_seconds: float = 60.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    async def describe(
        self, frame_paths: list[str], detections: list[TrackEvidence]
    ) -> SceneDescription:
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                f"{self.base_url}/describe",
                json={
                    "frame_paths": frame_paths,
                    "detections": [
                        detection.model_dump(mode="json")
                        for detection in detections
                    ],
                },
            )
            response.raise_for_status()
        return SceneDescription.model_validate(response.json())
