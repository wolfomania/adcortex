"""Stage 1: turn the upload into the media every later stage uses.

Videos become a 720p preview, which the player shows and the brain model
sees, plus scenes, keyframes, a thumbnail strip, a loudness envelope, and a
small proxy for the report model. Audio files become a preview and a 16 kHz
WAV. Scripts are read aloud first and then handled as audio.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from adcortex.brain.base import BrainInputKind
from adcortex.config import Settings
from adcortex.domain.errors import MediaError
from adcortex.domain.models import AnalysisMeta, MediaInfo, MediaKind, Scene
from adcortex.media.envelope import audio_envelope
from adcortex.media.probe import probe, validate_media
from adcortex.media.scenes import build_scenes, detect_cuts, uniform_segments
from adcortex.media.speech import speech_language
from adcortex.media.thumbnails import extract_keyframes, extract_strip
from adcortex.media.transcode import (
    make_audio_preview,
    make_llm_video,
    make_video_preview,
    to_wav,
)
from adcortex.pipeline.progress import Tracker
from adcortex.pipeline.services import Services
from adcortex.storage.repository import (
    AUDIO,
    LLM_VIDEO,
    PREVIEW_AUDIO,
    PREVIEW_VIDEO,
    SCRIPT,
    STRIP,
    source_name,
)

STRIP_COLUMNS = 10
ENVELOPE_HZ = 10.0
# Audio and scripts have no cuts; the report discusses them in segments.
AUDIO_SEGMENT_S = 10.0
SPEECH = "speech.mp3"


@dataclass(frozen=True)
class Prepared:
    """Media made from the upload; `files` maps artifact names to local copies."""

    media: MediaInfo
    scenes: tuple[Scene, ...]
    envelope: tuple[float, ...]
    brain_input: str
    brain_kind: BrainInputKind
    language: str
    files: Mapping[str, Path]
    strip: str | None = None
    script: str | None = None

    def read(self, name: str) -> bytes | None:
        path = self.files.get(name)
        return path.read_bytes() if path is not None else None


@dataclass(frozen=True)
class _Context:
    services: Services
    meta: AnalysisMeta
    tracker: Tracker
    work: Path

    def upload(self, files: Mapping[str, Path]) -> None:
        self.tracker.step("Saving the media", 0.24)
        self.services.repo.put_artifacts(self.meta.id, files)


def prepare(
    services: Services, meta: AnalysisMeta, tracker: Tracker, work: Path
) -> Prepared:
    ctx = _Context(services, meta, tracker, work)
    if meta.kind is MediaKind.TEXT:
        return _prepare_script(ctx)
    tracker.step("Fetching the upload", 0.04)
    name = source_name(meta.source.extension)
    src = services.repo.download_artifact(meta.id, name, work / name)
    info = probe(src)
    settings = services.settings
    validate_media(
        info, meta.kind, min_s=settings.min_duration_s, max_s=settings.max_duration_s
    )
    if meta.kind is MediaKind.VIDEO:
        return _prepare_video(ctx, src, info)
    return _prepare_audio(ctx, src, info, language=meta.language)


def _prepare_video(ctx: _Context, src: Path, info: MediaInfo) -> Prepared:
    settings, work, tracker = ctx.services.settings, ctx.work, ctx.tracker
    tracker.step("Converting the video", 0.06)
    preview = work / PREVIEW_VIDEO
    make_video_preview(src, preview, has_audio=info.has_audio)
    # The preview defines the timeline: the player and the brain model use it.
    duration = probe(preview).duration_s
    tracker.step("Detecting scene cuts", 0.12)
    cuts = detect_cuts(preview, threshold=settings.scene_threshold)
    scenes = build_scenes(cuts, duration=duration, min_scene_s=settings.min_scene_s)
    tracker.step("Extracting keyframes", 0.16)
    keyframes = extract_keyframes(preview, scenes, work)
    extract_strip(preview, work / STRIP, duration_s=duration, columns=STRIP_COLUMNS)
    files = {PREVIEW_VIDEO: preview, STRIP: work / STRIP}
    files |= {name: work / name for name in keyframes}
    if ctx.services.wants_llm_video:
        tracker.step("Preparing the video for the report model", 0.2)
        make_llm_video(preview, work / LLM_VIDEO, has_audio=info.has_audio)
        files[LLM_VIDEO] = work / LLM_VIDEO
    envelope = audio_envelope(preview, hz=ENVELOPE_HZ) if info.has_audio else []
    ctx.upload(files)
    return Prepared(
        media=info.model_copy(update={"duration_s": duration}),
        scenes=tuple(
            scene.model_copy(update={"keyframe": name})
            for scene, name in zip(scenes, keyframes, strict=True)
        ),
        envelope=tuple(envelope),
        brain_input=PREVIEW_VIDEO,
        brain_kind="video",
        language=ctx.meta.language,
        files=files,
        strip=STRIP,
    )


def _prepare_audio(
    ctx: _Context,
    src: Path,
    info: MediaInfo,
    *,
    language: str,
    script: str | None = None,
) -> Prepared:
    ctx.tracker.step("Converting the audio", 0.08)
    files = {PREVIEW_AUDIO: ctx.work / PREVIEW_AUDIO, AUDIO: ctx.work / AUDIO}
    make_audio_preview(src, files[PREVIEW_AUDIO])
    to_wav(src, files[AUDIO])
    envelope = audio_envelope(files[AUDIO], hz=ENVELOPE_HZ)
    ctx.upload(files)
    return Prepared(
        media=info,
        scenes=tuple(uniform_segments(info.duration_s, target_s=AUDIO_SEGMENT_S)),
        envelope=tuple(envelope),
        brain_input=AUDIO,
        brain_kind="audio",
        language=language,
        files=files,
        script=script,
    )


def _prepare_script(ctx: _Context) -> Prepared:
    script = ctx.services.repo.read_artifact(ctx.meta.id, SCRIPT).decode("utf-8")
    language = speech_language(ctx.meta.language)
    ctx.tracker.step("Reading the script aloud", 0.04)
    speech = ctx.work / SPEECH
    ctx.services.speak(script, language, speech)
    info = probe(speech)
    _check_reading_time(info.duration_s, ctx.services.settings)
    return _prepare_audio(ctx, speech, info, language=language, script=script)


def _check_reading_time(duration: float, settings: Settings) -> None:
    low, high = settings.min_duration_s, settings.max_duration_s
    if low <= duration <= high:
        return
    advice = "Add more text." if duration < low else "Shorten it."
    raise MediaError(
        f"Read aloud, the script lasts {duration:.1f} s; scripts must last "
        f"between {low:g} and {high:g} seconds. {advice}"
    )
