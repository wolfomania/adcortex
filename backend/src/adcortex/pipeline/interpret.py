"""Stage 4: the written report. Optional: the metrics stand without it."""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from adcortex.domain.models import (
    AnalysisMeta,
    AnalysisResult,
    LlmInfo,
    MediaKind,
    Scene,
    Status,
    StoredReport,
)
from adcortex.llm.client import MediaLevel, describe_failure, run_sync
from adcortex.llm.report import ReportMedia, ReportRequest, write_report
from adcortex.media.transcode import make_llm_video
from adcortex.pipeline.progress import Tracker
from adcortex.pipeline.services import Services
from adcortex.storage.repository import AUDIO, LLM_VIDEO, PREVIEW_VIDEO

logger = logging.getLogger(__name__)

# Returns an artifact's bytes, or None when it does not exist.
Reader = Callable[[str], bytes | None]


@dataclass(frozen=True)
class Interpreted:
    llm: LlmInfo
    stored: StoredReport | None = None


def report_inputs(
    kind: MediaKind, scenes: Sequence[Scene], level: MediaLevel
) -> list[str]:
    """Artifacts the report model may receive at the allowed media level."""
    if level == "text":
        return []
    if kind is not MediaKind.VIDEO:
        return [AUDIO] if level == "video" else []
    keyframes = [scene.keyframe for scene in scenes if scene.keyframe]
    return [LLM_VIDEO, *keyframes] if level == "video" else keyframes


def report_media(kind: MediaKind, scenes: Sequence[Scene], read: Reader) -> ReportMedia:
    if kind is not MediaKind.VIDEO:
        return ReportMedia(audio=read(AUDIO))
    keyframes: list[tuple[int, bytes]] = []
    for scene in scenes:
        data = read(scene.keyframe) if scene.keyframe else None
        if data is not None:
            keyframes.append((scene.index, data))
    return ReportMedia(video=read(LLM_VIDEO), keyframes=tuple(keyframes))


def interpret(
    services: Services,
    meta: AnalysisMeta,
    result: AnalysisResult,
    read: Reader,
    script: str | None,
    tracker: Tracker,
) -> Interpreted:
    config = services.llm
    if config is None:
        return Interpreted(LlmInfo(status="skipped"))
    tracker.stage(Status.INTERPRETING)
    media = report_media(meta.kind, result.scenes, read)
    request = ReportRequest(meta=meta, result=result, media=media, script=script)
    try:
        with tracker.timed("report"):
            stored = run_sync(write_report(config, request, catalog=services.catalog))
    except Exception as exc:
        logger.warning("Report for %s failed: %r", meta.id, exc, exc_info=exc)
        error = describe_failure(exc)
        return Interpreted(
            LlmInfo(model=config.model_name, status="failed", error=error)
        )
    services.repo.save_report(meta.id, stored)
    info = LlmInfo(model=stored.model, status="ok", input_mode=stored.input_mode)
    return Interpreted(info, stored)


def ensure_llm_video(
    services: Services, meta: AnalysisMeta, *, has_audio: bool, work: Path
) -> None:
    """Make the report model's video proxy for analyses made without one."""
    repo = services.repo
    if (
        meta.kind is not MediaKind.VIDEO
        or not services.wants_llm_video
        or repo.has_artifact(meta.id, LLM_VIDEO)
    ):
        return
    preview = repo.download_artifact(meta.id, PREVIEW_VIDEO, work / PREVIEW_VIDEO)
    make_llm_video(preview, work / LLM_VIDEO, has_audio=has_audio)
    repo.put_artifacts(meta.id, {LLM_VIDEO: work / LLM_VIDEO})
