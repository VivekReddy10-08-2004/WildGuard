"""Single-consumer bounded queue for failure-isolated VLM inference."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from backend.orchestration.events import EventService


@dataclass(frozen=True)
class DescriptionJob:
    event_id: str
    frame_paths: list[str]


class DescriptionWorker:
    def __init__(
        self,
        service: EventService,
        *,
        max_queue_size: int = 4,
        timeout_seconds: float = 60.0,
    ) -> None:
        self.service = service
        self.timeout_seconds = timeout_seconds
        self.queue: asyncio.Queue[DescriptionJob | None] = asyncio.Queue(
            maxsize=max_queue_size
        )
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is None:
            return
        await self.queue.put(None)
        await self._task
        self._task = None

    def submit(self, event_id: str, frame_paths: list[str]) -> bool:
        try:
            self.queue.put_nowait(DescriptionJob(event_id, frame_paths))
        except asyncio.QueueFull:
            self.service.fail_description(event_id, "description_queue_full")
            return False
        return True

    async def wait_until_idle(self) -> None:
        await self.queue.join()

    async def _run(self) -> None:
        while True:
            job = await self.queue.get()
            try:
                if job is None:
                    return
                description = await asyncio.wait_for(
                    self.service.describe_event(job.event_id, job.frame_paths),
                    timeout=self.timeout_seconds,
                )
                self.service.complete_description(job.event_id, description)
            except TimeoutError:
                if job is not None:
                    self.service.fail_description(job.event_id, "description_timeout")
            except Exception as error:
                if job is not None:
                    self.service.fail_description(
                        job.event_id, f"description_failed: {error}"
                    )
            finally:
                self.queue.task_done()
