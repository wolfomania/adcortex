"""Shared fixtures. Media fixtures are generated with ffmpeg, never committed."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    skip = pytest.mark.skip(reason="ffmpeg/ffprobe not installed")
    for item in items:
        if "ffmpeg" in item.keywords and not HAS_FFMPEG:
            item.add_marker(skip)


def _ffmpeg(*args: str) -> None:
    subprocess.run(
        ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", *args],
        check=True,
    )


@pytest.fixture(scope="session")
def media_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Small synthetic clips: three hard cuts, silent video, tones, junk."""
    if not HAS_FFMPEG:
        pytest.skip("ffmpeg/ffprobe not installed")
    root = tmp_path_factory.mktemp("media")
    _ffmpeg(
        "-f",
        "lavfi",
        "-i",
        "color=c=red:s=320x240:d=2:r=25",
        "-f",
        "lavfi",
        "-i",
        "color=c=blue:s=320x240:d=2:r=25",
        "-f",
        "lavfi",
        "-i",
        "testsrc2=s=320x240:d=2:r=25",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:duration=6",
        "-filter_complex",
        "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]",
        "-map",
        "[v]",
        "-map",
        "3:a",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-shortest",
        str(root / "three_scenes.mp4"),
    )
    _ffmpeg(
        "-f",
        "lavfi",
        "-i",
        "testsrc2=s=1920x1080:d=2:r=25",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-preset",
        "ultrafast",
        str(root / "silent_1080p.mp4"),
    )
    _ffmpeg(
        "-f",
        "lavfi",
        "-i",
        "testsrc2=s=360x640:d=1:r=25",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-preset",
        "ultrafast",
        str(root / "portrait_1s.mp4"),
    )
    _ffmpeg(
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=220:duration=5",
        str(root / "tone.wav"),
    )
    _ffmpeg(
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=330:duration=5",
        "-c:a",
        "aac",
        str(root / "tone.m4a"),
    )
    (root / "junk.mp4").write_bytes(b"this is not a video file at all")
    return root
