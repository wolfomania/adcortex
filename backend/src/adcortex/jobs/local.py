"""In-process jobs for `ADCORTEX_RUNTIME=local`."""

from __future__ import annotations

import logging
import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor, wait

from adcortex.domain.models import Job, JobRef
from adcortex.jobs.base import JobStatus, Runner

logger = logging.getLogger(__name__)


class LocalDispatcher:
    """Runs jobs on a small thread pool inside the web process."""

    def __init__(self, runner: Runner, *, max_workers: int = 2) -> None:
        self._runner = runner
        self._pool = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="adcortex-job"
        )
        self._futures: dict[str, Future[None]] = {}
        self._lock = threading.Lock()

    def submit(self, job: Job) -> JobRef:
        call_id = uuid.uuid4().hex
        with self._lock:
            self._futures[call_id] = self._pool.submit(self._run, job)
        return JobRef(backend="local", kind=job.kind, call_id=call_id)

    def _run(self, job: Job) -> None:
        try:
            self._runner(job)
        except Exception:
            logger.exception("%s job for %s crashed", job.kind, job.analysis_id)
            raise

    def status(self, ref: JobRef) -> JobStatus:
        future = self._future(ref)
        if future is None:
            # Submitted by an earlier process, whose threads died with it.
            return "failed"
        if not future.done():
            return "running"
        if future.cancelled() or future.exception() is not None:
            return "failed"
        return "finished"

    def cancel(self, ref: JobRef) -> None:
        future = self._future(ref)
        if future is not None:
            future.cancel()

    def drain(self, timeout: float | None = None) -> None:
        """Wait for every submitted job; used by tests and at shutdown."""
        with self._lock:
            futures = list(self._futures.values())
        wait(futures, timeout=timeout)

    def close(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)

    def _future(self, ref: JobRef) -> Future[None] | None:
        with self._lock:
            return self._futures.get(ref.call_id or "")
