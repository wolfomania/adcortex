"""Local-disk storage and in-process progress for `ADCORTEX_RUNTIME=local`."""

from __future__ import annotations

import os
import shutil
import tempfile
import threading
from collections.abc import Mapping, Sequence
from pathlib import Path

from adcortex.domain.models import Progress
from adcortex.storage.base import clean_path


class LocalFsStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, path: str) -> Path:
        return self.root / clean_path(path)

    def read_bytes(self, path: str) -> bytes:
        return self._path(path).read_bytes()

    def read_many(self, paths: Sequence[str]) -> dict[str, bytes | None]:
        found: dict[str, bytes | None] = {}
        for path in paths:
            try:
                found[path] = self.read_bytes(path)
            except FileNotFoundError:
                found[path] = None
        return found

    def write_bytes(self, path: str, data: bytes) -> None:
        target = self._path(path)
        with _replacing(target) as tmp:
            tmp.write_bytes(data)

    def upload(self, files: Mapping[str, Path]) -> None:
        for path, src in files.items():
            target = self._path(path)
            with _replacing(target) as tmp:
                shutil.copyfile(src, tmp)

    def download(self, path: str, dst: Path) -> None:
        source = self._path(path)
        if not source.is_file():
            raise FileNotFoundError(path)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dst)

    def local_path(self, path: str) -> Path:
        target = self._path(path)
        if not target.is_file():
            raise FileNotFoundError(path)
        return target

    def list_dir(self, path: str) -> list[str]:
        folder = self._path(path)
        if not folder.is_dir():
            return []
        return sorted(child.name for child in folder.iterdir() if not _is_temp(child))

    def exists(self, path: str) -> bool:
        return self._path(path).exists()

    def remove(self, path: str) -> None:
        target = self._path(path)
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink(missing_ok=True)


TEMP_PREFIX = ".tmp-"


def _is_temp(path: Path) -> bool:
    return path.name.startswith(TEMP_PREFIX)


class _replacing:
    """Write to a temporary sibling, then atomically replace the target."""

    def __init__(self, target: Path) -> None:
        self.target = target

    def __enter__(self) -> Path:
        self.target.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(dir=self.target.parent, prefix=TEMP_PREFIX)
        os.close(fd)
        self.tmp = Path(name)
        return self.tmp

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if exc_type is None:
            self.tmp.replace(self.target)
        else:
            self.tmp.unlink(missing_ok=True)


class MemoryProgressStore:
    def __init__(self) -> None:
        self._progress: dict[str, Progress] = {}
        self._lock = threading.Lock()

    def get(self, analysis_id: str) -> Progress | None:
        with self._lock:
            return self._progress.get(analysis_id)

    def put(self, analysis_id: str, progress: Progress) -> None:
        with self._lock:
            self._progress[analysis_id] = progress

    def clear(self, analysis_id: str) -> None:
        with self._lock:
            self._progress.pop(analysis_id, None)
