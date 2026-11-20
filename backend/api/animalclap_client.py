"""HTTP client for the isolated local AnimalCLAP service."""

from pathlib import Path

import httpx

from shared.contracts import WildlifeAudioAnalysis


class AnimalCLAPClient:
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8012",
        timeout_seconds: float = 120.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    async def analyze(self, audio_path: Path) -> WildlifeAudioAnalysis:
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                f"{self.base_url}/analyze",
                json={"audio_path": str(audio_path.resolve())},
            )
            response.raise_for_status()
        return WildlifeAudioAnalysis.model_validate(response.json())
