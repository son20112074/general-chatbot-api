"""In-memory store for long-running extract-file-content jobs."""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Optional


class ExtractFileJobStore:
    def __init__(self, ttl_seconds: int = 3600) -> None:
        self._jobs: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()
        self._ttl = ttl_seconds

    def _purge_expired(self) -> None:
        now = time.time()
        expired = [
            job_id
            for job_id, job in self._jobs.items()
            if now - float(job.get("created_at", now)) > self._ttl
        ]
        for job_id in expired:
            self._jobs.pop(job_id, None)

    async def create(self) -> str:
        job_id = str(uuid.uuid4())
        async with self._lock:
            self._purge_expired()
            self._jobs[job_id] = {
                "job_id": job_id,
                "status": "processing",
                "created_at": time.time(),
                "result": None,
                "error": None,
            }
        return job_id

    async def complete(self, job_id: str, result: dict[str, Any]) -> None:
        async with self._lock:
            if job_id not in self._jobs:
                return
            self._jobs[job_id].update(
                status="completed",
                result=result,
                error=None,
            )

    async def fail(self, job_id: str, error: str) -> None:
        async with self._lock:
            if job_id not in self._jobs:
                return
            self._jobs[job_id].update(
                status="failed",
                result=None,
                error=error,
            )

    async def get(self, job_id: str) -> Optional[dict[str, Any]]:
        async with self._lock:
            self._purge_expired()
            job = self._jobs.get(job_id)
            if not job:
                return None
            return dict(job)


extract_file_jobs = ExtractFileJobStore()
