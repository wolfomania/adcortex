"""Fail analyses whose job died, on the next status poll.

A crashed container, an out-of-memory kill, or a function timeout ends a job
without the pipeline recording why. The status endpoint calls `reconcile`,
which notices the dead job and records a failure the person can act on.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from neuromarketing.domain.models import (
    AnalysisState,
    JobKind,
    LlmInfo,
    Progress,
    Status,
    utcnow,
)
from neuromarketing.jobs.base import Dispatcher
from neuromarketing.storage.repository import AnalysisRepository

# Progress this recent proves the job is alive; skip the backend call.
FRESH_PROGRESS = timedelta(seconds=30)
# The web tier dispatches right after creating the analysis.
DISPATCH_GRACE = timedelta(minutes=2)
# Longer than any real run, for jobs the backend can no longer describe.
UNKNOWN_JOB_GRACE = timedelta(hours=2)

DEAD_JOB = (
    "The analysis stopped unexpectedly: the worker crashed, ran out of memory, "
    "or timed out. Retry the analysis."
)
DEAD_REPORT = "Writing the report stopped unexpectedly. Regenerate the report."
NEVER_STARTED = "The analysis never started. Retry the analysis."


def reconcile(
    repo: AnalysisRepository,
    dispatcher: Dispatcher,
    analysis_id: str,
    *,
    now: datetime | None = None,
    progress: Progress | None = None,
) -> AnalysisState:
    """The analysis's current state, failed first if its job is gone."""
    now = now or utcnow()
    state = repo.get_state(analysis_id)
    if state.status.is_terminal:
        return state
    if progress is not None and now - progress.updated_at < FRESH_PROGRESS:
        return state
    job = repo.get_job(analysis_id)
    if job is None:
        if now - state.updated_at < DISPATCH_GRACE:
            return state
        return _fail(repo, analysis_id, "analyze", NEVER_STARTED, now)
    status = dispatcher.status(job)
    if status == "running":
        return state
    if status == "unknown" and now - job.dispatched_at < UNKNOWN_JOB_GRACE:
        return state
    return _fail(repo, analysis_id, job.kind, DEAD_JOB, now)


def _fail(
    repo: AnalysisRepository, analysis_id: str, kind: JobKind, error: str, now: datetime
) -> AnalysisState:
    # The job may have finished between the first read and the status check.
    state = repo.get_state(analysis_id)
    if state.status.is_terminal:
        return state
    if kind == "report":
        # Only the report failed; the metrics from the earlier run still stand.
        llm = (state.llm or LlmInfo()).model_copy(
            update={"status": "failed", "error": DEAD_REPORT}
        )
        update = {"status": Status.COMPLETED, "message": "", "llm": llm}
    else:
        update = {"status": Status.FAILED, "message": "Failed", "error": error}
    failed = state.model_copy(update={**update, "updated_at": now})
    repo.save_state(analysis_id, failed)
    return failed
