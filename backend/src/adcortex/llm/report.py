"""The report agent: metrics plus the richest media the model accepts."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from pydantic_ai import (
    Agent,
    BinaryContent,
    ModelRetry,
    NativeOutput,
    PromptedOutput,
    RunContext,
)
from pydantic_ai.exceptions import (
    ModelAuthenticationError,
    ModelNotFoundError,
    ModelRequestRejectedError,
)
from pydantic_ai.messages import UserContent

from adcortex.analysis.systems import SystemCatalog
from adcortex.domain.models import (
    AnalysisMeta,
    AnalysisResult,
    LlmInputMode,
    Report,
    StoredReport,
)
from adcortex.llm.client import (
    OUTPUT_RETRIES,
    USAGE_LIMITS,
    LlmConfig,
    OutputMode,
    Sleep,
    call_with_backoff,
)
from adcortex.llm.prompts import REPORT_INSTRUCTIONS, report_brief

logger = logging.getLogger(__name__)

# Providers cap inline request bodies at about 20 MB.
MAX_INLINE_BYTES = 18 * 1024 * 1024
MAX_KEYFRAMES = 16
# A time this close to either end is clamped rather than sent back.
END_TOLERANCE_S = 0.5


@dataclass(frozen=True)
class ReportMedia:
    video: bytes | None = None
    audio: bytes | None = None
    audio_media_type: str = "audio/wav"
    keyframes: tuple[tuple[int, bytes], ...] = ()


@dataclass(frozen=True)
class ReportRequest:
    meta: AnalysisMeta
    result: AnalysisResult
    media: ReportMedia = field(default_factory=ReportMedia)
    script: str | None = None


@dataclass(frozen=True)
class ReportDeps:
    duration_s: float
    scene_indices: frozenset[int]


def choose_input_mode(config: LlmConfig, request: ReportRequest) -> LlmInputMode:
    """The richest input the settings allow and the model accepts."""
    profile = config.model.profile
    media = request.media
    if config.media == "video":
        if _fits(media.video) and profile.get("supports_video_input", True):
            return "video"
        if _fits(media.audio) and profile.get("supports_audio_file_input", True):
            return "audio"
    if (
        config.media != "text"
        and media.keyframes
        and profile.get("supports_image_input", True)
    ):
        return "keyframes"
    return "text"


def _fits(data: bytes | None) -> bool:
    return data is not None and 0 < len(data) <= MAX_INLINE_BYTES


def _fallbacks(mode: LlmInputMode, request: ReportRequest) -> list[LlmInputMode]:
    """Modes to try in order when the model rejects the media it was sent."""
    chain: list[LlmInputMode] = [mode]
    if mode == "video" and request.media.keyframes:
        chain.append("keyframes")
    if mode != "text":
        chain.append("text")
    return chain


async def write_report(
    config: LlmConfig,
    request: ReportRequest,
    *,
    catalog: SystemCatalog,
    sleep: Sleep = asyncio.sleep,
) -> StoredReport:
    modes = _fallbacks(choose_input_mode(config, request), request)
    for position, mode in enumerate(modes):
        try:
            return await _write(config, request, catalog, mode, sleep)
        except ModelRequestRejectedError as exc:
            final = position == len(modes) - 1
            if final or isinstance(exc, ModelAuthenticationError | ModelNotFoundError):
                raise
            logger.warning(
                "Report model rejected %s input (%s); trying %s",
                mode,
                exc,
                modes[position + 1],
            )
    raise AssertionError("unreachable")  # pragma: no cover


async def _write(
    config: LlmConfig,
    request: ReportRequest,
    catalog: SystemCatalog,
    mode: LlmInputMode,
    sleep: Sleep,
) -> StoredReport:
    agent = _agent(config.output_mode)
    deps = ReportDeps(
        duration_s=request.result.duration_s,
        scene_indices=frozenset(s.index for s in request.result.scenes),
    )
    prompt = build_prompt(request, mode, catalog)
    run = await call_with_backoff(
        lambda: agent.run(
            prompt,
            model=config.model,
            deps=deps,
            model_settings=config.model_settings,
            usage_limits=USAGE_LIMITS,
        ),
        retries=config.retries,
        sleep=sleep,
    )
    return StoredReport(model=config.model_name, input_mode=mode, report=run.output)


def build_prompt(
    request: ReportRequest, mode: LlmInputMode, catalog: SystemCatalog
) -> list[UserContent]:
    parts: list[UserContent] = [
        report_brief(request.meta, request.result, catalog, script=request.script)
    ]
    media = request.media
    if mode == "video" and media.video:
        parts += [
            "# Video\nThe ad itself, downscaled to 360 px and 2 frames per second:",
            BinaryContent(data=media.video, media_type="video/mp4"),
        ]
    elif mode == "audio" and media.audio:
        parts += [
            "# Audio\nThe ad itself:",
            BinaryContent(data=media.audio, media_type=media.audio_media_type),
        ]
    elif mode == "keyframes":
        scenes = {s.index: s for s in request.result.scenes}
        parts.append("# Keyframes\nOne frame from the middle of each scene:")
        for index, jpeg in _sample(media.keyframes, MAX_KEYFRAMES):
            scene = scenes.get(index)
            span = f" ({scene.start:.1f}-{scene.end:.1f} s)" if scene else ""
            parts += [
                f"Scene {index}{span}:",
                BinaryContent(data=jpeg, media_type="image/jpeg"),
            ]
    return parts


def _sample(
    items: tuple[tuple[int, bytes], ...], limit: int
) -> list[tuple[int, bytes]]:
    if len(items) <= limit:
        return list(items)
    step = len(items) / limit
    return [items[int(i * step)] for i in range(limit)]


def check_report(
    report: Report, *, duration_s: float, scene_indices: frozenset[int]
) -> Report:
    """Send impossible times and scene indices back to the model; sort moments."""
    problems: list[str] = []

    def in_clip(t: float, where: str) -> float:
        if -END_TOLERANCE_S <= t <= duration_s + END_TOLERANCE_S:
            return min(max(t, 0.0), duration_s)
        problems.append(
            f"{where} = {t:g} s is outside the clip (0 to {duration_s:.1f} s)"
        )
        return t

    moments = [
        m.model_copy(update={"t": in_clip(m.t, f"key_moments[{i}].t")})
        for i, m in enumerate(report.key_moments)
    ]
    recommendations = [
        r
        if r.t is None
        else r.model_copy(update={"t": in_clip(r.t, f"recommendations[{i}].t")})
        for i, r in enumerate(report.recommendations)
    ]
    problems += [
        f"scene_notes[{i}].scene_index = {n.scene_index} is not in the scene list"
        for i, n in enumerate(report.scene_notes)
        if n.scene_index not in scene_indices
    ]
    if problems:
        raise ModelRetry("Fix these fields: " + "; ".join(problems) + ".")
    return report.model_copy(
        update={
            "key_moments": sorted(moments, key=lambda m: m.t),
            "recommendations": recommendations,
        }
    )


def _validate(ctx: RunContext[ReportDeps], report: Report) -> Report:
    return check_report(
        report, duration_s=ctx.deps.duration_s, scene_indices=ctx.deps.scene_indices
    )


def output_type(model: type[Any], mode: OutputMode) -> Any:
    if mode == "native":
        return NativeOutput(model)
    if mode == "prompted":
        return PromptedOutput(model)
    return model


@lru_cache(maxsize=3)
def _agent(mode: OutputMode) -> Agent[ReportDeps, Report]:
    agent: Agent[ReportDeps, Report] = Agent(
        output_type=output_type(Report, mode),
        instructions=REPORT_INSTRUCTIONS,
        deps_type=ReportDeps,
        retries={"output": OUTPUT_RETRIES},
        name="report",
    )
    agent.output_validator(_validate)
    return agent
