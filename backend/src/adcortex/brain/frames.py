"""Decode each video frame once while TRIBE's video model walks a clip.

For every 0.5 s step, neuralset gives V-JEPA 2 64 frames from the 4 s before
it, so consecutive steps share most of their frames. moviepy's reader restarts
ffmpeg whenever a read goes backward, so every step decoded its whole window
again. `read_frame_at` instead reads forward in order and keeps the last few
seconds of frames, so each frame is decoded once; it seeks only for a frame
that has left the cache or lies far ahead.
"""

from __future__ import annotations

import math
from collections import OrderedDict
from collections.abc import Callable
from typing import Any, Protocol

import numpy as np

# The 4 s window neuralset reads behind each step, plus one step and a margin.
CACHE_SECONDS = 5.0
# At 720p a frame takes 2.8 MB, so the cache stays under 1 GB.
MAX_CACHED_FRAMES = 320
# Farther ahead than this, seeking is cheaper than decoding every frame.
MAX_READ_AHEAD = 100


class FrameReader(Protocol):
    """The part of moviepy's `FFMPEG_VideoReader` used here."""

    fps: float
    pos: int  # the index of the frame the next read returns
    proc: Any  # the ffmpeg process; None once closed

    def get_frame_number(self, t: float) -> int: ...

    def read_frame(self) -> np.ndarray: ...


class FrameCache:
    """The most recently used frames of one video, by frame index."""

    def __init__(self, capacity: int) -> None:
        self.capacity = capacity
        self._frames: OrderedDict[int, np.ndarray] = OrderedDict()

    def get(self, index: int) -> np.ndarray | None:
        frame = self._frames.get(index)
        if frame is not None:
            self._frames.move_to_end(index)
        return frame

    def put(self, index: int, frame: np.ndarray) -> None:
        self._frames[index] = frame
        self._frames.move_to_end(index)
        while len(self._frames) > self.capacity:
            self._frames.popitem(last=False)


def cache_capacity(fps: float) -> int:
    return max(1, min(MAX_CACHED_FRAMES, math.ceil(fps * CACHE_SECONDS)))


def read_frame_at(
    reader: FrameReader,
    t: float,
    cache: FrameCache,
    seek: Callable[[float], np.ndarray],
) -> np.ndarray:
    """The frame shown at `t`; `seek` is the reader's own `get_frame`."""
    index = reader.get_frame_number(t)
    frame = cache.get(index)
    if frame is not None:
        return frame
    if reader.proc is not None and 0 <= index - reader.pos <= MAX_READ_AHEAD:
        while True:  # keep every frame on the way: later steps reuse them
            position = reader.pos
            frame = reader.read_frame()
            cache.put(position, frame)
            if position >= index:
                return frame
    frame = seek(t)
    cache.put(index, frame)
    return frame
