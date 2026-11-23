"""Background jobs: run in-process locally, or spawned as a Modal function."""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal, Protocol

from adcortex.domain.models import Job, JobRef

# Name of the Modal function that runs jobs; deploy/modal_app.py defines it.
ORCHESTRATOR_FUNCTION = "orchestrate"

# "unknown": the backend could not say, for example during a Modal API outage.
JobStatus = Literal["running", "finished", "failed", "unknown"]
Runner = Callable[[Job], None]


class Dispatcher(Protocol):
    def submit(self, job: Job) -> JobRef: ...

    def status(self, ref: JobRef) -> JobStatus: ...

    def cancel(self, ref: JobRef) -> None:
        """Best effort: a job that already started may still finish."""
        ...
