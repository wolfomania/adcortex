"""Read media metadata with ffprobe and check it against the upload rules."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from neuromarketing.domain.errors import MediaError
from neuromarketing.domain.models import MediaInfo, MediaKind
from neuromarketing.media.ffmpeg import run_ffprobe

VIDEO_EXTENSIONS = frozenset({".mp4", ".mov", ".webm", ".mkv", ".avi"})
AUDIO_EXTENSIONS = frozenset({".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac"})
TEXT_EXTENSIONS = frozenset({".txt"})


def kind_for_extension(filename: str) -> MediaKind:
    suffix = Path(filename).suffix.lower()
    if suffix in VIDEO_EXTENSIONS:
        return MediaKind.VIDEO
    if suffix in AUDIO_EXTENSIONS:
        return MediaKind.AUDIO
    if suffix in TEXT_EXTENSIONS:
        return MediaKind.TEXT
    allowed = sorted(VIDEO_EXTENSIONS | AUDIO_EXTENSIONS | TEXT_EXTENSIONS)
    raise MediaError(
        f"'{suffix or filename}' files are not supported. Use one of: "
        + " ".join(allowed)
    )


def parse_rate(value: str | None) -> float | None:
    """Parse ffprobe frame rates such as '30000/1001'; None when unknown."""
    if not value:
        return None
    num, _, den = value.partition("/")
    try:
        rate = float(num) / float(den) if den else float(num)
    except (ValueError, ZeroDivisionError):
        return None
    return round(rate, 3) if rate > 0 else None


def probe(path: Path) -> MediaInfo:
    if not path.is_file():
        raise MediaError("We couldn't read this file: it does not exist.")
    raw = run_ffprobe(
        ["-print_format", "json", "-show_format", "-show_streams", path],
        error="We couldn't read this file. Is it a valid audio or video file?",
    )
    try:
        data: dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise MediaError("We couldn't read this file's metadata.") from exc
    return _media_info(data)


def _media_info(data: dict[str, Any]) -> MediaInfo:
    streams: list[dict[str, Any]] = data.get("streams") or []
    fmt: dict[str, Any] = data.get("format") or {}
    video = next(
        (
            s
            for s in streams
            if s.get("codec_type") == "video"
            and not (s.get("disposition") or {}).get("attached_pic")
        ),
        None,
    )
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    durations = [_float(fmt.get("duration"))] + [
        _float(s.get("duration")) for s in streams
    ]
    duration = max((d for d in durations if d is not None), default=0.0)
    if duration <= 0 or (video is None and audio is None):
        raise MediaError(
            "We couldn't read this file. Is it a valid audio or video file?"
        )
    return MediaInfo(
        duration_s=round(duration, 3),
        has_video=video is not None,
        has_audio=audio is not None,
        width=_int(video.get("width")) if video else None,
        height=_int(video.get("height")) if video else None,
        fps=parse_rate(video.get("avg_frame_rate")) if video else None,
        format_name=str(fmt.get("format_name", "")),
        video_codec=video.get("codec_name") if video else None,
        audio_codec=audio.get("codec_name") if audio else None,
    )


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def validate_media(
    info: MediaInfo, kind: MediaKind, *, min_s: float, max_s: float
) -> None:
    if kind is MediaKind.VIDEO and not info.has_video:
        raise MediaError(
            "This file has no video track. Upload it on the Audio tab instead."
        )
    if kind is MediaKind.AUDIO and not info.has_audio:
        raise MediaError("This file has no audio track.")
    if info.duration_s < min_s:
        raise MediaError(
            f"The clip is too short ({info.duration_s:.1f} s). "
            f"Use clips between {min_s:g} and {max_s:g} seconds."
        )
    if info.duration_s > max_s:
        raise MediaError(
            f"The clip is too long ({info.duration_s:.1f} s). "
            f"Use clips between {min_s:g} and {max_s:g} seconds."
        )
