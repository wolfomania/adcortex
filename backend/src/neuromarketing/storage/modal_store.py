"""Storage on Modal: a Volume used through its SDK, and a Dict for progress.

The Volume is never mounted. SDK writes are committed when the upload
finishes, and SDK reads always see the latest commit, so every container
shares one consistent view without `commit()`/`reload()` calls.

Media is served from a local copy: the first request for a file downloads it
into a size-capped cache, and later requests (including HTTP range requests
while a video is scrubbed) read the local file.
"""

from __future__ import annotations

import contextlib
import io
import logging
import tempfile
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any, BinaryIO, Protocol

from pydantic import ValidationError

from neuromarketing.domain.models import Progress
from neuromarketing.storage.base import clean_path

logger = logging.getLogger(__name__)

READ_WORKERS = 16
CACHE_BYTES = 4 * 1024**3
# A cached file used this recently may still be streaming; never evict it.
CACHE_GRACE_S = 300.0


class VolumeUpload(Protocol):
    def put_file(self, local_file: Path | BinaryIO, remote_path: str) -> Any: ...


class VolumeEntry(Protocol):
    @property
    def path(self) -> str: ...


class VolumeLike(Protocol):
    """The part of `modal.Volume` this store uses."""

    def read_file_into_fileobj(self, path: str, fileobj: IO[bytes]) -> int: ...

    def listdir(
        self, path: str, *, recursive: bool = False
    ) -> Sequence[VolumeEntry]: ...

    def remove_file(self, path: str, recursive: bool = False) -> None: ...

    def batch_upload(
        self, force: bool = False
    ) -> AbstractContextManager[VolumeUpload]: ...


class ModalVolumeStore:
    def __init__(
        self,
        volume: VolumeLike,
        *,
        cache_dir: Path | None = None,
        cache_bytes: int = CACHE_BYTES,
        cache_grace_s: float = CACHE_GRACE_S,
    ) -> None:
        self.volume = volume
        self._cache = LocalCache(
            cache_dir or Path(tempfile.gettempdir()) / "nm-volume-cache",
            max_bytes=cache_bytes,
            grace_s=cache_grace_s,
        )

    def read_bytes(self, path: str) -> bytes:
        buffer = io.BytesIO()
        self.volume.read_file_into_fileobj(clean_path(path), buffer)
        return buffer.getvalue()

    def read_many(self, paths: Sequence[str]) -> dict[str, bytes | None]:
        def read(path: str) -> bytes | None:
            try:
                return self.read_bytes(path)
            except FileNotFoundError:
                return None

        if len(paths) <= 1:
            return {path: read(path) for path in paths}
        with ThreadPoolExecutor(max_workers=min(READ_WORKERS, len(paths))) as pool:
            return dict(zip(paths, pool.map(read, paths), strict=True))

    def write_bytes(self, path: str, data: bytes) -> None:
        with self.volume.batch_upload(force=True) as upload:
            upload.put_file(io.BytesIO(data), clean_path(path))

    def upload(self, files: Mapping[str, Path]) -> None:
        checked = {clean_path(path): src for path, src in files.items()}
        with self.volume.batch_upload(force=True) as upload:
            for path, src in checked.items():
                upload.put_file(src, path)

    def download(self, path: str, dst: Path) -> None:
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            with dst.open("wb") as fileobj:
                self.volume.read_file_into_fileobj(clean_path(path), fileobj)
        except BaseException:
            dst.unlink(missing_ok=True)
            raise

    def local_path(self, path: str) -> Path:
        return self._cache.get(clean_path(path), self.download)

    def list_dir(self, path: str) -> list[str]:
        base = clean_path(path)
        try:
            entries = self.volume.listdir(base)
        except FileNotFoundError:
            return []
        names: set[str] = set()
        for entry in entries:
            name = entry.path.strip("/")
            if name == base:  # a file lists itself
                continue
            # Entry paths are relative to the volume root; accept relative ones too.
            name = name.removeprefix(f"{base}/")
            names.add(name.split("/", 1)[0])
        return sorted(names)

    def exists(self, path: str) -> bool:
        try:
            return bool(self.volume.listdir(clean_path(path)))
        except FileNotFoundError:
            return False

    def remove(self, path: str) -> None:
        with contextlib.suppress(FileNotFoundError):
            self.volume.remove_file(clean_path(path), recursive=True)


@dataclass
class _Cached:
    size: int
    used_at: float


class LocalCache:
    """Least-recently-used local copies of remote files, capped in bytes."""

    def __init__(self, root: Path, *, max_bytes: int, grace_s: float) -> None:
        self.root = root
        self.max_bytes = max_bytes
        self.grace_s = grace_s
        self._entries: OrderedDict[str, _Cached] = OrderedDict()
        self._lock = threading.Lock()
        self._fetching: dict[str, threading.Lock] = {}

    def get(self, path: str, fetch: Callable[[str, Path], None]) -> Path:
        target = self.root / path
        with self._lock:
            if self._touch(path):
                return target
            fetch_lock = self._fetching.setdefault(path, threading.Lock())
        with fetch_lock:
            try:
                with self._lock:
                    if self._touch(path):
                        return target
                partial = target.with_name(f".{target.name}.part")
                fetch(path, partial)
                partial.replace(target)
                with self._lock:
                    self._entries[path] = _Cached(
                        target.stat().st_size, time.monotonic()
                    )
                    self._evict(keep=path)
            finally:
                with self._lock:
                    self._fetching.pop(path, None)
        return target

    def _touch(self, path: str) -> bool:
        entry = self._entries.get(path)
        if entry is None or not (self.root / path).is_file():
            return False
        entry.used_at = time.monotonic()
        self._entries.move_to_end(path)
        return True

    def _evict(self, *, keep: str) -> None:
        total = sum(e.size for e in self._entries.values())
        now = time.monotonic()
        for path, entry in list(self._entries.items()):
            if total <= self.max_bytes:
                break
            if path == keep or now - entry.used_at < self.grace_s:
                continue
            (self.root / path).unlink(missing_ok=True)
            del self._entries[path]
            total -= entry.size


class DictLike(Protocol):
    """The part of `modal.Dict` this store uses."""

    def get(self, key: str, default: Any = None) -> Any: ...

    def put(self, key: str, value: Any, *, skip_if_exists: bool = False) -> bool: ...

    def pop(self, key: str, default: Any = None) -> Any: ...


class ModalDictProgressStore:
    """Progress as JSON strings in a Modal Dict, shared by all containers."""

    def __init__(self, backing: DictLike) -> None:
        self.backing = backing

    def get(self, analysis_id: str) -> Progress | None:
        raw = self.backing.get(analysis_id)
        if raw is None:
            return None
        try:
            return Progress.model_validate_json(raw)
        except ValidationError:
            logger.warning("Ignoring unreadable progress for %s", analysis_id)
            return None

    def put(self, analysis_id: str, progress: Progress) -> None:
        self.backing.put(analysis_id, progress.model_dump_json())

    def clear(self, analysis_id: str) -> None:
        self.backing.pop(analysis_id, None)
