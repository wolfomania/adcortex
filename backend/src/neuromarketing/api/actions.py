"""What the analysis routes do, apart from HTTP.

The web tier writes `state.json` only when no job runs: when it creates or
retries an analysis, or starts a report rewrite. Each job ref is cleared
before the new state is written, so a status check never judges the new job
by the previous one.
"""

from __future__ import annotations

import logging

from neuromarketing.api.context import AppContext
from neuromarketing.api.schemas import AnalysisDetail, ShareLink
from neuromarketing.domain.errors import (
    ConflictError,
    InvalidInputError,
    NotFoundError,
    UnavailableError,
)
from neuromarketing.domain.models import (
    Analysis,
    AnalysisMeta,
    AnalysisState,
    Job,
    Progress,
    Status,
    utcnow,
)
from neuromarketing.jobs.monitor import reconcile
from neuromarketing.pipeline.progress import publish
from neuromarketing.storage.repository import AnalysisRepository

logger = logging.getLogger(__name__)

WAITING = "Waiting to start"
WRITING = "Writing the report"
DISPATCH_FAILED = "The analysis could not be started. Retry the analysis."
NO_REPORT_MODEL = "No report model is configured. Set NM_LLM_MODEL to write reports."
# The metrics are on screen from the moment the report starts being written.
RESULT_READY = frozenset({Status.COMPLETED, Status.INTERPRETING})


def clean_text(value: str) -> str:
    """One line: control characters become spaces, runs of spaces collapse."""
    printable = "".join(ch if ch.isprintable() else " " for ch in value)
    return " ".join(printable.split())


def read_progress(ctx: AppContext, key: str) -> Progress | None:
    try:
        return ctx.progress.get(key)
    except Exception:
        logger.warning("Could not read progress for %s", key, exc_info=True)
        return None


# ── reading ────────────────────────────────────────────────────────────────


def history(
    ctx: AppContext, *, limit: int, before: str | None
) -> tuple[list[Analysis], str | None]:
    items = ctx.repo.history(limit=limit, before=before)
    next_before = items[-1].meta.id if len(items) == limit else None
    return items, next_before


def current(ctx: AppContext, analysis_id: str) -> Analysis:
    """The analysis with live progress, failed first if its job died."""
    analysis = ctx.repo.get(analysis_id)
    if analysis.state.status.is_terminal:
        return analysis
    progress = read_progress(ctx, analysis_id)
    state = reconcile(ctx.repo, ctx.dispatcher, analysis_id, progress=progress)
    live = None if state.status.is_terminal else progress
    return analysis.model_copy(update={"state": state, "progress": live})


def detail(repo: AnalysisRepository, analysis: Analysis) -> AnalysisDetail:
    result = None
    if analysis.state.status in RESULT_READY:
        try:
            result = repo.get_result(analysis.meta.id)
        except NotFoundError:
            result = None
    report = repo.get_report(analysis.meta.id)
    return AnalysisDetail(analysis=analysis, result=result, report=report)


def shared_detail(ctx: AppContext, token: str) -> AnalysisDetail:
    analysis_id = ctx.auth.open_share(token)
    return detail(ctx.repo, ctx.repo.get(analysis_id))


# ── jobs ───────────────────────────────────────────────────────────────────


def start_analysis(ctx: AppContext, meta: AnalysisMeta) -> Analysis:
    queued = AnalysisState(status=Status.QUEUED, message=WAITING)
    ctx.repo.create(meta, queued)
    return Analysis(meta=meta, state=_dispatch_analysis(ctx, meta.id, queued))


def retry(ctx: AppContext, analysis_id: str) -> Analysis:
    with ctx.lock:
        analysis = ctx.repo.get(analysis_id)
        if analysis.state.status is not Status.FAILED:
            raise ConflictError("Only failed analyses can be retried.")
        ctx.repo.clear_job(analysis_id)
        queued = AnalysisState(status=Status.QUEUED, message=WAITING)
        ctx.repo.save_state(analysis_id, queued)
        publish(ctx.progress, analysis_id, None)
        state = _dispatch_analysis(ctx, analysis_id, queued)
    return Analysis(meta=analysis.meta, state=state)


def rewrite_report(ctx: AppContext, analysis_id: str) -> Analysis:
    if ctx.services.llm is None:
        raise UnavailableError(NO_REPORT_MODEL)
    with ctx.lock:
        analysis = ctx.repo.get(analysis_id)
        previous = analysis.state
        if previous.status is not Status.COMPLETED:
            raise ConflictError(
                "The report can be rewritten once the analysis has completed."
            )
        writing = previous.model_copy(
            update={"status": Status.INTERPRETING, "message": WRITING}
            | {"updated_at": utcnow()}
        )
        ctx.repo.clear_job(analysis_id)
        ctx.repo.save_state(analysis_id, writing)
        try:
            ref = ctx.dispatcher.submit(Job(kind="report", analysis_id=analysis_id))
        except Exception as exc:
            logger.exception("Could not dispatch the report for %s", analysis_id)
            ctx.repo.save_state(analysis_id, previous)
            raise UnavailableError(
                "Couldn't start writing the report. Try again in a minute."
            ) from exc
        ctx.repo.save_job(analysis_id, ref)
    return Analysis(meta=analysis.meta, state=writing)


def _dispatch_analysis(
    ctx: AppContext, analysis_id: str, queued: AnalysisState
) -> AnalysisState:
    try:
        ref = ctx.dispatcher.submit(Job(kind="analyze", analysis_id=analysis_id))
    except Exception:
        logger.exception("Could not dispatch the analysis %s", analysis_id)
        failed = queued.model_copy(
            update={"status": Status.FAILED, "message": "Failed to start."}
            | {"error": DISPATCH_FAILED, "updated_at": utcnow()}
        )
        ctx.repo.save_state(analysis_id, failed)
        return failed
    ctx.repo.save_job(analysis_id, ref)
    return queued


# ── editing ────────────────────────────────────────────────────────────────


def rename(ctx: AppContext, analysis_id: str, name: str) -> Analysis:
    clean = clean_text(name)
    if not clean:
        raise InvalidInputError("The name can't be empty.")
    with ctx.lock:
        analysis = ctx.repo.get(analysis_id)
        meta = analysis.meta.model_copy(update={"name": clean})
        ctx.repo.save_meta(meta)
    return Analysis(meta=meta, state=analysis.state)


def delete(ctx: AppContext, analysis_id: str) -> None:
    """Remove the analysis; a running job notices and stops."""
    with ctx.lock:
        analysis = ctx.repo.get(analysis_id)
        job = ctx.repo.get_job(analysis_id)
        if job is not None and not analysis.state.status.is_terminal:
            try:
                ctx.dispatcher.cancel(job)
            except Exception:
                logger.warning(
                    "Could not cancel the job of %s", analysis_id, exc_info=True
                )
        ctx.repo.delete(analysis_id)
    publish(ctx.progress, analysis_id, None)


def share(ctx: AppContext, analysis_id: str) -> ShareLink:
    analysis = ctx.repo.get(analysis_id)
    if analysis.state.status is not Status.COMPLETED:
        raise ConflictError("Only completed analyses can be shared.")
    grant = ctx.auth.share(analysis_id)
    return ShareLink(
        token=grant.token, path=f"/s/{grant.token}", expires_at=grant.expires_at
    )
