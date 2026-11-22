"""Thin, safe wrappers around the ffmpeg and ffprobe binaries.

Arguments are always passed as a list (never through a shell), and every call
has a timeout so a malformed file cannot hang a worker.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

from neuromarketing.domain.errors import MediaError

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT_S = 900.0


def _binary(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise MediaError(f"{name} is not installed on this server.")
    return path


def run_ffmpeg(
    args: Sequence[str | Path],
    *,
    timeout: float = DEFAULT_TIMEOUT_S,
    error: str = "We couldn't process this media file.",
) -> bytes:
    """Run ffmpeg and return stdout. Raise MediaError with `error` on failure."""
    cmd = [
        _binary("ffmpeg"),
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        *map(str, args),
    ]
    return _run(cmd, timeout=timeout, error=error)


def run_ffprobe(
    args: Sequence[str | Path],
    *,
    timeout: float = 60.0,
    error: str = "We couldn't read this file. Is it a valid audio or video file?",
) -> bytes:
    cmd = [_binary("ffprobe"), "-v", "error", *map(str, args)]
    return _run(cmd, timeout=timeout, error=error)


def _run(cmd: list[str], *, timeout: float, error: str) -> bytes:
    try:
        proc = subprocess.run(  # noqa: S603 - fixed binary, list arguments
            cmd, capture_output=True, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired as exc:
        raise MediaError(f"{error} (timed out after {timeout:.0f} s)") from exc
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip()[-800:]
        log.warning("%s failed (%s): %s", Path(cmd[0]).name, proc.returncode, detail)
        raise MediaError(error)
    return proc.stdout
