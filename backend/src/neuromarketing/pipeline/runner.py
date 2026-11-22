"""Background jobs: a full analysis, a regenerated report, or a comparison.

`run_job` is what the dispatcher runs: in a worker thread locally, or in the
orchestrator function on Modal. Jobs record every outcome, failures included,
where the web tier reads it. Only an error that stops even that write reaches
the dispatcher; the web tier's liveness check then marks the job dead.
"""

from __future__ import annotations

import logging
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from functools import partial
from pathlib import Path

from neuromarketing.domain.errors import NotFoundError, PipelineError, UserFacingError
from neuromarketing.domain.models import (
    Analysis,
    AnalysisMeta,
    AnalysisState,
    AnalysisSummary,
    Job,
    LlmInfo,
    MediaKind,
    Progress,
    Status,
    StoredComparison,
    StoredReport,
)
from neuromarketing.jobs.base import Runner
from neuromarketing.llm.client import describe_failure, run_sync
from neuromarketing.llm.compare import write_comparison
from neuromarketing.pipeline.interpret import (
    Interpreted,
    ensure_llm_video,
    interpret,
    report_inputs,
)
from neuromarketing.pipeline.measure import measure
from neuromarketing.pipeline.predict import predict
from neuromarketing.pipeline.prepare import prepare
from neuromarketing.pipeline.progress import JobCancelled, Tracker, publish
from neuromarketing.pipeline.services import Services
from neuromarketing.storage.repository import SCRIPT

logger = logging.getLogger(__name__)

GENERIC_FAILURE = (
    "Something went wrong while processing this clip. Retry the analysis; "
    "if it fails again, the server logs have the details."
)
REPORT_FAILURE = "Writing the report failed."
COMPARE_FAILURE = "Writing the comparison failed."


def compare_key(a_id: str, b_id: str) -> str:
    """Progress key of the comparison job for an ordered pair."""
    return f"compare:{a_id}--{b_id}"


def make_runner(services: Services) -> Runner:
    return partial(run_job, services)


def run_job(services: Services, job: Job) -> None:
    if job.kind == "analyze":
        run_analysis(services, job.analysis_id)
    elif job.kind == "report":
        run_report(services, job.analysis_id)
    elif job.other_id is not None:
        run_compare(services, job.analysis_id, job.other_id)
    else:
        logger.error("Comparison job without a second analysis: %s", job)


# ── analysis ───────────────────────────────────────────────────────────────


def run_analysis(services: Services, analysis_id: str) -> None:
    analysis = _find(services, analysis_id)
    if analysis is None:
        return
    # A fresh state: a retry must not carry the previous run's error or report.
    state = AnalysisState(status=Status.QUEUED)
    tracker = Tracker(services.repo, services.progress, analysis_id, state)
    with (
        _outcome(services, tracker),
        tempfile.TemporaryDirectory(prefix="nm-job-") as tmp,
    ):
        _analyze(services, analysis.meta, tracker, Path(tmp))


def _analyze(
    services: Services, meta: AnalysisMeta, tracker: Tracker, work: Path
) -> None:
    tracker.stage(Status.PREPARING)
    with tracker.timed("prepare"):
        prepared = prepare(services, meta, tracker, work)
    tracker.record(media=prepared.media)
    with tracker.timed("predict"):
        predicted = predict(services, meta, prepared, tracker)
    with tracker.timed("analyze"):
        output = measure(services, meta, prepared, predicted.prediction, tracker)
    report = interpret(
        services, meta, output.result, prepared.read, prepared.script, tracker
    )
    tracker.complete(
        language=output.result.language,
        summary=with_headline(output.summary, report.stored),
        llm=report.llm,
        reused_from=predicted.reused_from,
    )


@contextmanager
def _outcome(services: Services, tracker: Tracker) -> Iterator[None]:
    """Store how the job ended: a failure becomes the analysis's error."""
    try:
        yield
    except JobCancelled:
        _abandon(services, tracker.analysis_id)
    except Exception as exc:
        if isinstance(exc, UserFacingError):
            logger.info("Analysis %s failed: %s", tracker.analysis_id, exc)
            error = str(exc)
        else:
            logger.error("Analysis %s failed", tracker.analysis_id, exc_info=exc)
            error = GENERIC_FAILURE
        try:
            tracker.fail(error)
        except JobCancelled:
            _abandon(services, tracker.analysis_id)


# ── report ─────────────────────────────────────────────────────────────────


def run_report(services: Services, analysis_id: str) -> None:
    """Rewrite the report of a completed analysis; the metrics stay as they are."""
    analysis = _find(services, analysis_id)
    if analysis is None:
        return
    tracker = Tracker(
        services.repo,
        services.progress,
        analysis_id,
        analysis.state,
        measure_total=False,
    )
    try:
        report = _rewrite_report(services, analysis, tracker)
    except JobCancelled:
        _abandon(services, analysis_id)
        return
    except Exception as exc:
        logger.error("Report job for %s failed", analysis_id, exc_info=exc)
        model = services.llm.model_name if services.llm else None
        error = _message(exc, REPORT_FAILURE)
        report = Interpreted(LlmInfo(model=model, status="failed", error=error))
    summary = analysis.state.summary
    try:
        tracker.complete(
            llm=report.llm,
            summary=with_headline(summary, report.stored) if summary else None,
        )
    except JobCancelled:
        _abandon(services, analysis_id)


def _rewrite_report(
    services: Services, analysis: Analysis, tracker: Tracker
) -> Interpreted:
    meta, repo = analysis.meta, services.repo
    result = repo.get_result(meta.id)
    media = analysis.state.media
    with tempfile.TemporaryDirectory(prefix="nm-report-") as tmp:
        ensure_llm_video(
            services,
            meta,
            has_audio=media.has_audio if media else True,
            work=Path(tmp),
        )
    level = services.llm.media if services.llm else "text"
    names = report_inputs(meta.kind, result.scenes, level)
    stored = repo.read_artifacts(meta.id, names)
    script = (
        repo.read_artifact(meta.id, SCRIPT).decode("utf-8")
        if meta.kind is MediaKind.TEXT
        else None
    )
    return interpret(services, meta, result, stored.get, script, tracker)


# ── comparison ─────────────────────────────────────────────────────────────


def run_compare(services: Services, a_id: str, b_id: str) -> None:
    key = compare_key(a_id, b_id)
    running = Progress(
        status=Status.INTERPRETING,
        message="Comparing the two analyses",
        fraction=0.5,
    )
    publish(services.progress, key, running)
    try:
        services.repo.save_comparison(_compare(services, a_id, b_id))
    except Exception as exc:
        logger.warning("Comparison %s failed: %r", key, exc, exc_info=exc)
        message = _message(exc, COMPARE_FAILURE)
        publish(services.progress, key, Progress(status=Status.FAILED, message=message))
        return
    publish(services.progress, key, None)


def _compare(services: Services, a_id: str, b_id: str) -> StoredComparison:
    config = services.llm
    if config is None:
        raise PipelineError(
            "No report model is configured. Set NM_LLM_MODEL to compare analyses."
        )
    repo = services.repo
    a = (repo.get(a_id).meta, repo.get_result(a_id))
    b = (repo.get(b_id).meta, repo.get_result(b_id))
    return run_sync(write_comparison(config, a, b, catalog=services.catalog))


# ── helpers ────────────────────────────────────────────────────────────────


def with_headline(
    summary: AnalysisSummary, stored: StoredReport | None
) -> AnalysisSummary:
    if stored is None:
        return summary
    return summary.model_copy(update={"headline": stored.report.headline})


def _find(services: Services, analysis_id: str) -> Analysis | None:
    try:
        return services.repo.get(analysis_id)
    except NotFoundError:
        logger.info("Analysis %s no longer exists; skipping its job", analysis_id)
        return None


def _abandon(services: Services, analysis_id: str) -> None:
    logger.info("Analysis %s was deleted while its job ran", analysis_id)
    publish(services.progress, analysis_id, None)
    services.repo.discard(analysis_id)


def _message(exc: BaseException, fallback: str) -> str:
    if isinstance(exc, UserFacingError):
        return str(exc)
    return describe_failure(exc, fallback=fallback)
