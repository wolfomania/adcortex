"""Stage 3: turn the prediction into curves, scores, and brain frames."""

from __future__ import annotations

from dataclasses import replace

from neuromarketing.analysis.library import apply_library, library_percentiles
from neuromarketing.analysis.run import AnalysisInputs, AnalysisOutput, analyze
from neuromarketing.brain.base import BrainPrediction
from neuromarketing.domain.languages import AUTO, is_fully_supported
from neuromarketing.domain.models import AnalysisMeta, LanguageInfo, Status
from neuromarketing.pipeline.prepare import STRIP_COLUMNS, Prepared
from neuromarketing.pipeline.progress import Tracker
from neuromarketing.pipeline.services import Services
from neuromarketing.storage.repository import FRAMES, AnalysisRepository

# How many recent analyses form "your library" for percentiles.
LIBRARY_SIZE = 200


def measure(
    services: Services,
    meta: AnalysisMeta,
    prepared: Prepared,
    prediction: BrainPrediction,
    tracker: Tracker,
) -> AnalysisOutput:
    tracker.stage(Status.ANALYZING)
    inputs = AnalysisInputs(
        prediction=prediction,
        kind=meta.kind,
        duration_s=prepared.media.duration_s,
        scenes=prepared.scenes,
        language=language_info(meta.language, prediction),
        envelope=prepared.envelope,
        strip=prepared.strip,
        strip_columns=STRIP_COLUMNS,
    )
    output = analyze(
        inputs,
        catalog=services.catalog,
        atlas=services.atlas,
        baseline=services.baseline,
    )
    library = _library(services.repo, meta)
    percentiles = library_percentiles(output.summary.system_means, library)
    result = apply_library(output.result, percentiles)
    services.repo.put_artifact_bytes(meta.id, FRAMES, output.frames)
    services.repo.save_result(meta.id, result)
    return replace(output, result=result)


def language_info(requested: str, prediction: BrainPrediction) -> LanguageInfo:
    """TRIBE v2 learned from English speech; other spoken languages are flagged."""
    detected = prediction.language
    spoken = detected or (None if requested == AUTO else requested)
    reliable = not prediction.words or spoken is None or is_fully_supported(spoken)
    return LanguageInfo(requested=requested, detected=detected, full_support=reliable)


def _library(repo: AnalysisRepository, meta: AnalysisMeta) -> list[dict[str, float]]:
    """System means of earlier completed analyses of the same kind, one per file."""
    seen = {meta.source.sha256}
    library: list[dict[str, float]] = []
    for item in repo.history(limit=LIBRARY_SIZE):
        summary = item.state.summary
        if (
            item.meta.kind is not meta.kind
            or item.state.status is not Status.COMPLETED
            or summary is None
            or not summary.system_means
            or item.meta.source.sha256 in seen
        ):
            continue
        seen.add(item.meta.source.sha256)
        library.append(summary.system_means)
    return library
