"""Storage interfaces: files addressed by relative paths, and live progress.

Both backends implement the same contract, so the pipeline and the API never
know whether they run on a laptop or on Modal:

- `LocalFsStore` keeps files under `ADCORTEX_DATA_DIR`.
- `ModalVolumeStore` talks to a Modal Volume through its SDK instead of
  mounting it. Every write is visible to every container at once, so the web
  tier, the orchestrator, and the GPU worker never coordinate commits and
  reloads, and a reload can never fail on a file that is still being served.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol

from adcortex.domain.models import Progress

_FORBIDDEN_SEGMENTS = frozenset({"", ".", ".."})


def clean_path(path: str) -> str:
    """Return `path` if it is a safe relative POSIX path; raise ValueError otherwise."""
    if (
        "\\" in path
        or "\x00" in path
        or any(s in _FORBIDDEN_SEGMENTS for s in path.split("/"))
    ):
        raise ValueError(f"Unsafe storage path: {path!r}")
    return path


class ArtifactStore(Protocol):
    """A tree of files. Writes replace whole files; readers never see partial ones."""

    def read_bytes(self, path: str) -> bytes:
        """Raises FileNotFoundError when the file does not exist."""
        ...

    def read_many(self, paths: Sequence[str]) -> dict[str, bytes | None]:
        """Read several files at once; missing files map to None."""
        ...

    def write_bytes(self, path: str, data: bytes) -> None: ...

    def upload(self, files: Mapping[str, Path]) -> None:
        """Copy local files to the given store paths, replacing existing ones."""
        ...

    def download(self, path: str, dst: Path) -> None:
        """Raises FileNotFoundError when the file does not exist."""
        ...

    def local_path(self, path: str) -> Path:
        """A local file with the content of `path`, for streaming with ranges.

        Raises FileNotFoundError when the file does not exist.
        """
        ...

    def list_dir(self, path: str) -> list[str]:
        """Sorted names of the files and folders directly inside `path`."""
        ...

    def exists(self, path: str) -> bool: ...

    def remove(self, path: str) -> None:
        """Delete a file or a folder tree; a missing path is not an error."""
        ...


class ProgressStore(Protocol):
    """Live progress per analysis, updated many times per stage."""

    def get(self, analysis_id: str) -> Progress | None: ...

    def put(self, analysis_id: str, progress: Progress) -> None: ...

    def clear(self, analysis_id: str) -> None: ...
