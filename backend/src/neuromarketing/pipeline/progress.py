"""Stage bookkeeping: the stored state at each stage, live progress in between."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from typing import Any

from neuromarketing.domain.models import AnalysisState, Progress, Status, utcnow
from neuromarketing.storage.base import ProgressStore
from neuromarketing.storage.repository import AnalysisRepository

logger = logging.getLogger(__name__)

# What each stage does; also completes "Failed while ...".
DOING: Mapping[Status, str] = {
    Status.QUEUED: "starting",
    Status.PREPARING: "preparing the media",
    Status.WAITING_FOR_GPU: "waiting for a GPU",
    Status.PREDICTING: "predicting the brain response",
    Status.ANALYZING: "measuring brain systems",
    Status.INTERPRETING: "writing the report",
}

# Overall progress (0-1) when each stage starts; prediction takes longest.
STAGE_START: Mapping[Status, float] = {
    Status.QUEUED: 0.0,
    Status.PREPARING: 0.02,
    Status.WAITING_FOR_GPU: 0.26,
    Status.PREDICTING: 0.3,
    Status.ANALYZING: 0.8,
    Status.INTERPRETING: 0.84,
}

COMPLETED_MESSAGE = "Analysis complete"


def stage_progress(status: Status, message: str | None = None) -> Progress:
    doing = DOING[status]
    return Progress(
        status=status,
        message=message or doing[0].upper() + doing[1:],
        fraction=STAGE_START[status],
    )


def publish(progress: ProgressStore, key: str, update: Progress | None) -> None:
    """Best effort: a lost progress update must never fail a job."""
    try:
        if update is None:
            progress.clear(key)
        else:
            progress.put(key, update)
    except Exception:
        logger.warning("Could not publish progress for %s", key, exc_info=True)


class JobCancelled(Exception):
    """The analysis was deleted while its job ran."""


class Tracker:
    """Writes an analysis's state at each stage and its progress in between.

    A job is the only writer of `state.json` while it runs. Before each write
    the tracker checks that the analysis still exists, so a job whose
    analysis was deleted stops instead of recreating its folder.
    """

    def __init__(
        self,
        repo: AnalysisRepository,
        progress: ProgressStore,
        analysis_id: str,
        state: AnalysisState,
        *,
        measure_total: bool = True,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.analysis_id = analysis_id
        self._repo = repo
        self._progress = progress
        self._state = state
        self._measure_total = measure_total
        self._clock = clock
        self._started = clock()
        self._timings: dict[str, float] = {}

    def stage(self, status: Status, message: str | None = None) -> None:
        update = stage_progress(status, message)
        self._save(status=status, message=update.message, error=None)
        publish(self._progress, self.analysis_id, update)

    def step(self, message: str, fraction: float) -> None:
        """Report progress within the current stage."""
        update = Progress(status=self._state.status, message=message, fraction=fraction)
        publish(self._progress, self.analysis_id, update)

    def record(self, **fields: Any) -> None:
        self._save(**fields)

    def check(self) -> None:
        """Raise JobCancelled if the analysis was deleted, e.g. during a long call."""
        if not self._repo.exists(self.analysis_id):
            raise JobCancelled(self.analysis_id)

    @contextmanager
    def timed(self, name: str) -> Iterator[None]:
        started = self._clock()
        try:
            yield
        finally:
            self._timings[name] = round(self._clock() - started, 2)

    def add_timings(self, timings: Mapping[str, float]) -> None:
        self._timings.update(timings)

    def complete(self, **fields: Any) -> None:
        self._save(
            status=Status.COMPLETED,
            message=COMPLETED_MESSAGE,
            error=None,
            timings=self._all_timings(),
            **fields,
        )
        publish(self._progress, self.analysis_id, None)

    def fail(self, error: str) -> None:
        doing = DOING.get(self._state.status, "processing")
        self._save(
            status=Status.FAILED,
            message=f"Failed while {doing}.",
            error=error,
            timings=self._all_timings(),
        )
        publish(self._progress, self.analysis_id, None)

    def _all_timings(self) -> dict[str, float]:
        timings = {**self._state.timings, **self._timings}
        if self._measure_total:
            timings["total"] = round(self._clock() - self._started, 2)
        return timings

    def _save(self, **fields: Any) -> None:
        self.check()
        self._state = self._state.model_copy(update={**fields, "updated_at": utcnow()})
        self._repo.save_state(self.analysis_id, self._state)
