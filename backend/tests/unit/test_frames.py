from __future__ import annotations

import numpy as np

from adcortex.brain.frames import (
    MAX_CACHED_FRAMES,
    FrameCache,
    cache_capacity,
    read_frame_at,
)


class FakeReader:
    """Mimics moviepy's FFMPEG_VideoReader: frame k holds the value k."""

    def __init__(self, fps: float = 25.0) -> None:
        self.fps = fps
        self.pos = 0  # the frame the next read returns
        self.proc: object | None = object()
        self.reads = 0
        self.seeks = 0

    def get_frame_number(self, t: float) -> int:
        return int(self.fps * t + 0.00001)

    def read_frame(self) -> np.ndarray:
        frame = np.array([self.pos])
        self.pos += 1
        self.reads += 1
        return frame

    def seek(self, t: float) -> np.ndarray:
        """moviepy's own get_frame where it must seek: restart, read one frame."""
        self.seeks += 1
        self.pos = self.get_frame_number(t)
        return self.read_frame()


def walk_like_neuralset(reader: FakeReader, cache: FrameCache, steps: int) -> None:
    """64 frames from the 4 s before each 0.5 s step, oldest first."""
    for step in range(1, steps + 1):
        end = step * 0.5
        for k in reversed(range(64)):
            t = max(0.0, end - k / 64 * 4)
            frame = read_frame_at(reader, t, cache, reader.seek)
            assert frame[0] == reader.get_frame_number(t)


def test_overlapping_windows_decode_each_frame_once() -> None:
    reader = FakeReader(fps=25.0)
    cache = FrameCache(cache_capacity(reader.fps))

    walk_like_neuralset(reader, cache, steps=40)

    assert reader.seeks == 0
    assert reader.reads == reader.get_frame_number(40 * 0.5) + 1


def test_a_frame_that_left_the_cache_is_sought() -> None:
    reader = FakeReader()
    cache = FrameCache(capacity=10)
    read_frame_at(reader, 2.0, cache, reader.seek)

    frame = read_frame_at(reader, 0.0, cache, reader.seek)

    assert frame[0] == 0
    assert reader.seeks == 1


def test_a_far_jump_ahead_seeks_instead_of_decoding_every_frame() -> None:
    reader = FakeReader(fps=25.0)
    cache = FrameCache(capacity=10)

    frame = read_frame_at(reader, 60.0, cache, reader.seek)

    assert frame[0] == 1500
    assert (reader.seeks, reader.reads) == (1, 1)


def test_a_closed_reader_seeks() -> None:
    reader = FakeReader()
    reader.proc = None
    cache = FrameCache(capacity=10)

    frame = read_frame_at(reader, 0.4, cache, reader.seek)

    assert frame[0] == 10
    assert reader.seeks == 1


def test_the_cache_holds_five_seconds_up_to_a_limit() -> None:
    assert cache_capacity(25.0) == 125
    assert cache_capacity(29.97) == 150
    assert cache_capacity(1000.0) == MAX_CACHED_FRAMES


def test_the_cache_forgets_the_least_recently_used_frame() -> None:
    cache = FrameCache(capacity=2)
    cache.put(1, np.array([1]))
    cache.put(2, np.array([2]))
    assert cache.get(1) is not None

    cache.put(3, np.array([3]))

    assert cache.get(2) is None
    assert cache.get(1) is not None
    assert cache.get(3) is not None
