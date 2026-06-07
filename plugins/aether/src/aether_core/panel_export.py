"""Background export job registry for the Aether panel.

The legacy ``/api/export`` endpoint built the panel bundle zip in the
request thread, which blocks the panel UI for several seconds when the
visual memory holds many images. The jobs in this module move the
expensive work to a background thread and surface ``/api/export/status``
plus ``/api/export/download`` for the panel to poll.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from .config import LoadedConfig
from .panel_bundle import export_panel_bundle
from .storage import AetherStore


DEFAULT_JOB_TTL_SECONDS = 15 * 60
MAX_CONCURRENT_JOBS = 4


@dataclass
class ExportJob:
    """One running or completed export.

    ``payload`` is only populated once ``status == "complete"``. ``error``
    is only populated once ``status == "failed"``. ``progress`` is a
    coarse 0..100 indicator derived from the bundle build steps.
    """

    job_id: str
    status: str = "running"  # "running" | "complete" | "failed"
    progress: int = 0
    filename: str = ""
    payload: bytes | None = None
    error: str = ""
    created_at: float = field(default_factory=time.time)
    expires_at: float = field(default_factory=lambda: time.time() + DEFAULT_JOB_TTL_SECONDS)


class ExportJobRegistry:
    """Thread-safe registry of background export jobs.

    Jobs are kept in memory; finished jobs older than the TTL are
    reaped on every new ``start()`` call so the dict cannot grow
    unbounded. Each export runs in its own daemon thread so multiple
    panels can export in parallel (capped at ``MAX_CONCURRENT_JOBS``).
    """

    def __init__(
        self,
        *,
        ttl_seconds: float = DEFAULT_JOB_TTL_SECONDS,
        max_concurrent: int = MAX_CONCURRENT_JOBS,
    ) -> None:
        self._jobs: dict[str, ExportJob] = {}
        self._lock = threading.Lock()
        self._ttl = ttl_seconds
        self._max_concurrent = max_concurrent

    def _reap_expired(self) -> None:
        now = time.time()
        expired = [job_id for job_id, job in self._jobs.items() if job.expires_at < now]
        for job_id in expired:
            self._jobs.pop(job_id, None)

    def _running_count(self) -> int:
        return sum(1 for job in self._jobs.values() if job.status == "running")

    def start(
        self,
        config: LoadedConfig,
        store: AetherStore,
        *,
        progress_callback: Any = None,
    ) -> ExportJob:
        """Start a new export job in a background thread.

        Raises ``RuntimeError`` when ``MAX_CONCURRENT_JOBS`` are already
        running; callers should surface a 429-like error to the user.
        """
        with self._lock:
            self._reap_expired()
            if self._running_count() >= self._max_concurrent:
                raise RuntimeError("Too many concurrent export jobs")
            job = ExportJob(job_id=f"export_{uuid.uuid4().hex[:12]}")
            self._jobs[job.job_id] = job
        thread = threading.Thread(
            target=self._run,
            args=(job.job_id, config, store, progress_callback),
            name=f"aether-export-{job.job_id}",
            daemon=True,
        )
        thread.start()
        return job

    def _run(
        self,
        job_id: str,
        config: LoadedConfig,
        store: AetherStore,
        progress_callback: Any,
    ) -> None:
        job = self._jobs.get(job_id)
        if job is None:
            return
        try:
            if progress_callback is not None:
                progress_callback(job, 10)
            payload, filename = export_panel_bundle(config, store)
            if progress_callback is not None:
                progress_callback(job, 90)
            job.payload = payload
            job.filename = filename
            job.status = "complete"
            job.progress = 100
        except Exception as exc:  # noqa: BLE001 — surface the message verbatim
            job.status = "failed"
            job.error = str(exc) or exc.__class__.__name__
            job.progress = 0
        finally:
            job.expires_at = time.time() + self._ttl

    def get(self, job_id: str) -> ExportJob | None:
        with self._lock:
            self._reap_expired()
            return self._jobs.get(job_id)

    def to_status(self, job: ExportJob) -> dict[str, Any]:
        """Return the JSON-serialisable status object for an export job."""
        return {
            "job_id": job.job_id,
            "status": job.status,
            "progress": job.progress,
            "filename": job.filename,
            "error": job.error,
            "ready_to_download": (
                job.status == "complete" and job.payload is not None
            ),
        }
