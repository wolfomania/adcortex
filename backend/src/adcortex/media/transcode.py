"""Browser-friendly previews and model inputs.

The video preview is also what the GPU worker receives, so the player and the
brain model see the same frames: H.264 + AAC, at most 720 px on the short
side, fast-start for instant seeking, and always with an audio track. The
report model gets a smaller proxy, because providers cap inline uploads at
about 20 MB and sample video at 1 frame per second anyway.
"""

from __future__ import annotations

from pathlib import Path

from adcortex.media.ffmpeg import run_ffmpeg

MAX_SHORT_SIDE = 720
LLM_SHORT_SIDE = 360
LLM_FPS = 2


def _scale(short_side: int) -> str:
    """Shorter side limited to `short_side`, aspect ratio kept, even sizes."""
    return (
        "scale="
        f"w='if(lt(iw,ih),trunc(min({short_side},iw)/2)*2,-2)':"
        f"h='if(lt(iw,ih),-2,trunc(min({short_side},ih)/2)*2)':"
        "flags=lanczos,format=yuv420p"
    )


_SCALE = _scale(MAX_SHORT_SIDE)


def make_video_preview(src: Path, dst: Path, *, has_audio: bool) -> None:
    """The video defines the length: audio is padded with silence or cut."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    inputs: list[str | Path] = ["-i", src]
    audio_map = "0:a:0"
    if not has_audio:
        inputs += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
        audio_map = "1:a:0"
    run_ffmpeg(
        [
            *inputs,
            "-map",
            "0:v:0",
            "-map",
            audio_map,
            "-vf",
            _SCALE,
            "-af",
            "apad",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-ac",
            "2",
            "-ar",
            "48000",
            "-shortest",
            "-movflags",
            "+faststart",
            dst,
        ],
        error="We couldn't convert this video. Try exporting it as H.264 MP4.",
    )


def make_llm_video(src: Path, dst: Path, *, has_audio: bool) -> None:
    """A few-MB proxy for the report model: 360 px, 2 fps, mono audio."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    audio = ["-c:a", "aac", "-b:a", "64k", "-ac", "1"] if has_audio else ["-an"]
    run_ffmpeg(
        [
            "-i",
            src,
            "-map",
            "0:v:0",
            *(["-map", "0:a:0"] if has_audio else []),
            "-vf",
            f"fps={LLM_FPS},{_scale(LLM_SHORT_SIDE)}",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "30",
            *audio,
            "-movflags",
            "+faststart",
            dst,
        ],
        error="We couldn't prepare the video for the report model.",
    )


def make_audio_preview(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(
        [
            "-i",
            src,
            "-vn",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-ac",
            "2",
            "-ar",
            "48000",
            "-movflags",
            "+faststart",
            dst,
        ],
        error="We couldn't convert this audio file.",
    )


def to_wav(src: Path, dst: Path, *, sample_rate: int = 16000) -> None:
    """Mono 16-bit PCM WAV, the format TRIBE's audio path expects."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(
        [
            "-i",
            src,
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(sample_rate),
            "-c:a",
            "pcm_s16le",
            dst,
        ],
        error="We couldn't decode the audio in this file.",
    )
