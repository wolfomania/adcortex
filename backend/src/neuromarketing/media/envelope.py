"""Audio loudness envelope for the timeline lane."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from neuromarketing.media.ffmpeg import run_ffmpeg
from neuromarketing.media.probe import probe

_SAMPLE_RATE = 8000
_FLOOR_DB = -60.0


def audio_envelope(src: Path, *, hz: float = 10.0) -> list[float]:
    """RMS loudness per 1/hz s window, mapped from [-60 dBFS, 0 dBFS] to [0, 1].

    Returns an empty list when the file has no audio track.
    """
    if not probe(src).has_audio:
        return []
    raw = run_ffmpeg(
        ["-i", src, "-vn", "-ac", "1", "-ar", str(_SAMPLE_RATE), "-f", "s16le", "-"],
        error="We couldn't decode the audio in this file.",
    )
    samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    window = int(_SAMPLE_RATE / hz)
    n = len(samples) // window
    if n == 0:
        return []
    frames = samples[: n * window].reshape(n, window)
    rms = np.sqrt(np.mean(frames**2, axis=1))
    db = 20 * np.log10(np.maximum(rms, 1e-6))
    level = np.clip((db - _FLOOR_DB) / -_FLOOR_DB, 0.0, 1.0)
    return [round(float(v), 3) for v in level]
