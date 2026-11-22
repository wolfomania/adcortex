"""Scene boundaries: ffmpeg `scdet` for video, even segments otherwise."""

from __future__ import annotations

import math
import re
from collections.abc import Iterable
from itertools import pairwise
from pathlib import Path

from neuromarketing.domain.models import Scene
from neuromarketing.media.ffmpeg import run_ffmpeg

_TIME_RE = re.compile(rb"lavfi\.scd\.time=([0-9.]+)")


def detect_cuts(src: Path, *, threshold: float) -> list[float]:
    """Return timestamps (s) of hard cuts. Frames are downscaled for speed."""
    out = run_ffmpeg(
        [
            "-i",
            src,
            "-an",
            "-vf",
            f"scale=160:-2,scdet=threshold={threshold:g},"
            "metadata=mode=print:key=lavfi.scd.time:file=-",
            "-f",
            "null",
            "-",
        ],
        error="Scene detection failed for this video.",
    )
    return [float(m.group(1)) for m in _TIME_RE.finditer(out)]


def build_scenes(
    cuts: Iterable[float], *, duration: float, min_scene_s: float
) -> list[Scene]:
    """Turn cut times into contiguous scenes no shorter than `min_scene_s`."""
    bounds = [0.0]
    for cut in sorted(cuts):
        if cut - bounds[-1] >= min_scene_s and duration - cut >= min_scene_s:
            bounds.append(round(cut, 3))
    bounds.append(round(duration, 3))
    return [
        Scene(index=i, start=start, end=end)
        for i, (start, end) in enumerate(pairwise(bounds))
    ]


def uniform_segments(duration: float, *, target_s: float) -> list[Scene]:
    """Equal-length segments no longer than `target_s`, for audio and scripts."""
    count = max(1, math.ceil(duration / target_s - 1e-9))
    step = duration / count
    bounds = [round(i * step, 3) for i in range(count)] + [round(duration, 3)]
    return [
        Scene(index=i, start=start, end=end)
        for i, (start, end) in enumerate(pairwise(bounds))
    ]


def seconds_grid(duration: float) -> int:
    """Number of 1 Hz samples covering `duration` (TRIBE predicts at 1 Hz)."""
    return max(1, math.ceil(duration - 1e-6))
