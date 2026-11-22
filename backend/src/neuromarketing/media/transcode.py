"""Browser-friendly previews and model inputs.

The video preview is also what the GPU worker and the LLM receive, so every
downstream step sees the same frames: H.264 + AAC, at most 720 px on the short
side, fast-start for instant seeking, and always with an audio track.
"""

from __future__ import annotations

from pathlib import Path

from neuromarketing.media.ffmpeg import run_ffmpeg

MAX_SHORT_SIDE = 720

# Shorter side limited to MAX_SHORT_SIDE, aspect ratio kept, dimensions even.
_SCALE = (
    "scale="
    f"w='if(lt(iw,ih),trunc(min({MAX_SHORT_SIDE},iw)/2)*2,-2)':"
    f"h='if(lt(iw,ih),-2,trunc(min({MAX_SHORT_SIDE},ih)/2)*2)':"
    "flags=lanczos,format=yuv420p"
)


def make_video_preview(src: Path, dst: Path, *, has_audio: bool) -> None:
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
