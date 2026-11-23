"""In-memory stand-ins for the Modal SDK calls the app makes.

They mirror the behavior the real calls document: missing paths raise
FileNotFoundError, and uploads refuse to overwrite unless `force=True`.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any, BinaryIO

from modal.exception import NotFoundError

FILE = 1
DIRECTORY = 2


@dataclass(frozen=True)
class FakeEntry:
    path: str
    type: int
    mtime: int = 0
    size: int = 0


class FakeUpload:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}

    def put_file(self, local_file: Path | str | BinaryIO, remote_path: str) -> None:
        if isinstance(local_file, str | Path):
            data = Path(local_file).read_bytes()
        else:
            data = local_file.read()
        self.files[remote_path.strip("/")] = data


class FakeVolume:
    """Files keyed by path; directories exist only through their contents."""

    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.reads = 0

    def read_file_into_fileobj(self, path: str, fileobj: IO[bytes]) -> int:
        self.reads += 1
        data = self.files.get(path.strip("/"))
        if data is None:
            raise FileNotFoundError(path)
        fileobj.write(data)
        return len(data)

    def listdir(self, path: str, *, recursive: bool = False) -> list[FakeEntry]:
        path = path.strip("/")
        if path in self.files:
            return [FakeEntry(path, FILE, size=len(self.files[path]))]
        prefix = f"{path}/" if path else ""
        children: dict[str, FakeEntry] = {}
        for name, data in self.files.items():
            if name.startswith(prefix):
                head, _, tail = name[len(prefix) :].partition("/")
                child = prefix + head
                kind = DIRECTORY if tail else FILE
                children[child] = FakeEntry(child, kind, size=0 if tail else len(data))
        if not children:
            # As the real Volume does: Modal's error, not FileNotFoundError.
            raise NotFoundError(f'path "/{path}" does not exist')
        # The real listing has no defined order.
        return sorted(children.values(), key=lambda e: e.path, reverse=True)

    def remove_file(self, path: str, recursive: bool = False) -> None:
        path = path.strip("/")
        if path in self.files:
            del self.files[path]
            return
        inside = [name for name in self.files if name.startswith(f"{path}/")]
        if not inside:
            raise FileNotFoundError(path)
        if not recursive:
            raise IsADirectoryError(path)
        for name in inside:
            del self.files[name]

    @contextmanager
    def batch_upload(self, force: bool = False) -> Iterator[FakeUpload]:
        upload = FakeUpload()
        yield upload
        clashes = [name for name in upload.files if name in self.files]
        if clashes and not force:
            raise FileExistsError(clashes[0])
        self.files.update(upload.files)


class FakeDict:
    def __init__(self) -> None:
        self.data: dict[str, Any] = {}

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def put(self, key: str, value: Any, *, skip_if_exists: bool = False) -> bool:
        if skip_if_exists and key in self.data:
            return False
        self.data[key] = value
        return True

    def pop(self, key: str, default: Any = None) -> Any:
        return self.data.pop(key, default)
