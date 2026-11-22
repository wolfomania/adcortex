"""A/B comparisons: start the job once, then report where it stands.

A comparison has no state document of its own. It is `completed` once
stored, and `running` or `failed` while its progress entry says so.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from neuromarketing.api.actions import read_progress
from neuromarketing.api.context import AppContext
from neuromarketing.api.schemas import ComparisonState
from neuromarketing.domain.errors import (
    ConflictError,
    InvalidInputError,
    UnavailableError,
)
from neuromarketing.domain.models import Job, Progress, Status, utcnow
from neuromarketing.pipeline.progress import publish
from neuromarketing.pipeline.runner import COMPARE_FAILURE, compare_key

logger = logging.getLogger(__name__)

# Longer than the slowest model call with all its retries.
STALE_AFTER = timedelta(minutes=20)
STOPPED = "The comparison stopped unexpectedly. Try again."
NO_REPORT_MODEL = (
    "No report model is configured. Set NM_LLM_MODEL to compare analyses in writing."
)


def comparison_state(
    ctx: AppContext, a_id: str, b_id: str, *, now: datetime | None = None
) -> ComparisonState:
    stored = ctx.repo.get_comparison(a_id, b_id)
    if stored is not None:
        return ComparisonState(status="completed", comparison=stored)
    progress = read_progress(ctx, compare_key(a_id, b_id))
    if progress is None:
        return ComparisonState(status="none")
    if progress.status is Status.FAILED:
        return ComparisonState(
            status="failed", error=progress.message or COMPARE_FAILURE
        )
    if (now or utcnow()) - progress.updated_at > STALE_AFTER:
        return ComparisonState(status="failed", error=STOPPED)
    return ComparisonState(status="running")


def lookup(ctx: AppContext, a_id: str, b_id: str) -> ComparisonState:
    ctx.repo.get(a_id)
    ctx.repo.get(b_id)
    return comparison_state(ctx, a_id, b_id)


def start(ctx: AppContext, a_id: str, b_id: str) -> ComparisonState:
    if a_id == b_id:
        raise InvalidInputError("Pick two different analyses to compare.")
    analyses = (ctx.repo.get(a_id), ctx.repo.get(b_id))
    if any(item.state.status is not Status.COMPLETED for item in analyses):
        raise ConflictError(
            "Both analyses must be completed before they can be compared."
        )
    if ctx.services.llm is None:
        raise UnavailableError(NO_REPORT_MODEL)
    with ctx.lock:
        state = comparison_state(ctx, a_id, b_id)
        if state.status in ("completed", "running"):
            return state
        key = compare_key(a_id, b_id)
        publish(ctx.progress, key, Progress(status=Status.QUEUED, message="Waiting"))
        try:
            ctx.dispatcher.submit(Job(kind="compare", analysis_id=a_id, other_id=b_id))
        except Exception as exc:
            logger.exception("Could not dispatch the comparison %s", key)
            publish(ctx.progress, key, None)
            raise UnavailableError(
                "Couldn't start the comparison. Try again in a minute."
            ) from exc
    return ComparisonState(status="running")
