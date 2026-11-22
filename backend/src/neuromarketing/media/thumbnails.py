"""Keyframes at scene midpoints and a 1 fps thumbnail strip."""

from __future__ import annotations

import math
from collections.abc import Sequence
from pathlib import Path

from neuromarketing.domain.models import Scene
from neuromarketing.media.ffmpeg import run_ffmpeg


def extract_keyframes(
    src: Path, scenes: Sequence[Scene], out_dir: Path, *, width: int = 640
) -> list[str]:
    """Write `keyframes/NNN.jpg` per scene; return names relative to `out_dir`."""
    (out_dir / "keyframes").mkdir(parents=True, exist_ok=True)
    names: list[str] = []
    for scene in scenes:
        name = f"keyframes/{scene.index:03d}.jpg"
        midpoint = (scene.start + scene.end) / 2
        run_ffmpeg(
            [
                "-ss",
                f"{midpoint:.3f}",
                "-i",
                src,
                "-frames:v",
                "1",
                "-vf",
                f"scale={width}:-2",
                "-q:v",
                "3",
                out_dir / name,
            ],
            error="We couldn't extract keyframes from this video.",
        )
        names.append(name)
    return names


def extract_strip(
    src: Path, dst: Path, *, duration_s: float, columns: int = 10, width: int = 160
) -> int:
    """Tile one frame per second (t = 0, 1, 2, ...) into a JPEG grid.

    Returns the number of tiles. Tile k shows second k, so the browser can
    locate any second with integer math.
    """
    tiles = math.floor(duration_s) + 1
    rows = math.ceil(tiles / columns)
    dst.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(
        [
            "-i",
            src,
            "-vf",
            f"fps=1:round=down,scale={width}:-2,tile={columns}x{rows}",
            "-frames:v",
            "1",
            "-q:v",
            "4",
            dst,
        ],
        error="We couldn't build the thumbnail strip for this video.",
    )
    return tiles
