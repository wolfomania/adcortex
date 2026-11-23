from __future__ import annotations

from pathlib import Path

import modal
import pytest

from adcortex.config import Settings
from adcortex.domain.models import Progress, Status
from adcortex.storage.base import ArtifactStore, ProgressStore
from adcortex.storage.factory import create_storage
from adcortex.storage.local import LocalFsStore, MemoryProgressStore
from adcortex.storage.modal_store import ModalDictProgressStore, ModalVolumeStore
from tests.fakes import FakeDict, FakeVolume

# ── artifact stores: one contract, two backends ────────────────────────────


@pytest.fixture(params=["local", "modal"])
def store(request: pytest.FixtureRequest, tmp_path: Path) -> ArtifactStore:
    if request.param == "local":
        return LocalFsStore(tmp_path / "data")
    return ModalVolumeStore(FakeVolume(), cache_dir=tmp_path / "cache")


def test_written_bytes_read_back_and_can_be_overwritten(store: ArtifactStore) -> None:
    store.write_bytes("a/doc.json", b"{}")
    store.write_bytes("a/doc.json", b"[1]")

    assert store.read_bytes("a/doc.json") == b"[1]"


def test_missing_files_raise_file_not_found(
    store: ArtifactStore, tmp_path: Path
) -> None:
    with pytest.raises(FileNotFoundError):
        store.read_bytes("missing.json")
    with pytest.raises(FileNotFoundError):
        store.download("missing.bin", tmp_path / "out.bin")
    with pytest.raises(FileNotFoundError):
        store.local_path("missing.bin")


def test_read_many_returns_none_for_missing_files(store: ArtifactStore) -> None:
    store.write_bytes("x/one", b"1")

    assert store.read_many(["x/one", "x/two"]) == {"x/one": b"1", "x/two": None}


def test_uploaded_files_download_intact(store: ArtifactStore, tmp_path: Path) -> None:
    src = tmp_path / "src.bin"
    src.write_bytes(b"payload")
    dst = tmp_path / "out" / "copy.bin"

    store.upload({"a/src.bin": src, "a/sub/copy.bin": src})
    store.upload({"a/src.bin": src})
    store.download("a/sub/copy.bin", dst)

    assert dst.read_bytes() == b"payload"


def test_listing_names_immediate_children_in_order(store: ArtifactStore) -> None:
    store.write_bytes("root/b/file", b"1")
    store.write_bytes("root/a.json", b"2")

    assert store.list_dir("root") == ["a.json", "b"]
    assert store.list_dir("missing") == []
    assert store.exists("root/a.json")
    assert store.exists("root/b")
    assert not store.exists("root/c")


def test_remove_deletes_files_and_folders(store: ArtifactStore) -> None:
    store.write_bytes("t/x/1", b"1")
    store.write_bytes("t/y", b"2")
    store.write_bytes("keep", b"3")

    store.remove("t/x")
    store.remove("t/y")
    store.remove("t/missing")

    assert store.list_dir("t") == []
    assert store.exists("keep")


def test_local_path_is_a_readable_file(store: ArtifactStore) -> None:
    store.write_bytes("m/clip.mp4", b"video")

    assert store.local_path("m/clip.mp4").read_bytes() == b"video"


@pytest.mark.parametrize(
    "bad", ["", "/abs", "../x", "a/../b", "a//b", "a/./b", "a\\b", "a/"]
)
def test_unsafe_paths_are_rejected(store: ArtifactStore, bad: str) -> None:
    with pytest.raises(ValueError, match="Unsafe storage path"):
        store.read_bytes(bad)


# ── Modal specifics ────────────────────────────────────────────────────────


def test_modal_store_downloads_each_file_once(tmp_path: Path) -> None:
    volume = FakeVolume()
    store = ModalVolumeStore(volume, cache_dir=tmp_path)
    store.write_bytes("m/clip.mp4", b"video")

    first = store.local_path("m/clip.mp4")
    second = store.local_path("m/clip.mp4")

    assert first == second
    assert volume.reads == 1


def test_modal_cache_evicts_the_least_recently_used_file(tmp_path: Path) -> None:
    store = ModalVolumeStore(
        FakeVolume(), cache_dir=tmp_path, cache_bytes=10, cache_grace_s=0
    )
    for name in "abc":
        store.write_bytes(f"m/{name}", b"x" * 4)

    a = store.local_path("m/a")
    b = store.local_path("m/b")
    store.local_path("m/a")
    store.local_path("m/c")

    assert a.exists()
    assert not b.exists()


def test_modal_cache_keeps_files_that_are_still_being_served(tmp_path: Path) -> None:
    store = ModalVolumeStore(
        FakeVolume(), cache_dir=tmp_path, cache_bytes=1, cache_grace_s=60
    )
    store.write_bytes("m/a", b"xx")
    store.write_bytes("m/b", b"yy")

    a = store.local_path("m/a")
    store.local_path("m/b")

    assert a.exists()


# ── progress ───────────────────────────────────────────────────────────────


@pytest.fixture(params=["memory", "modal"])
def progress(request: pytest.FixtureRequest) -> ProgressStore:
    if request.param == "memory":
        return MemoryProgressStore()
    return ModalDictProgressStore(FakeDict())


def test_progress_round_trip(progress: ProgressStore) -> None:
    update = Progress(status=Status.PREDICTING, message="Predicting", fraction=0.5)

    assert progress.get("a") is None
    progress.put("a", update)
    assert progress.get("a") == update
    progress.clear("a")
    progress.clear("a")
    assert progress.get("a") is None


def test_unreadable_progress_is_ignored() -> None:
    backing = FakeDict()
    backing.put("a", "not json")

    assert ModalDictProgressStore(backing).get("a") is None


# ── factory ────────────────────────────────────────────────────────────────


def test_local_runtime_stores_under_the_data_dir(tmp_path: Path) -> None:
    storage = create_storage(Settings(data_dir=tmp_path))

    storage.repository.store.write_bytes("probe", b"1")

    assert (tmp_path / "probe").read_bytes() == b"1"
    assert isinstance(storage.progress, MemoryProgressStore)


def test_modal_runtime_opens_the_named_volume_and_dict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened: dict[str, tuple[str, dict[str, object]]] = {}

    def volume(name: str, **kwargs: object) -> FakeVolume:
        opened["volume"] = (name, kwargs)
        return FakeVolume()

    def progress_dict(name: str, **kwargs: object) -> FakeDict:
        opened["dict"] = (name, kwargs)
        return FakeDict()

    monkeypatch.setattr(modal.Volume, "from_name", volume)
    monkeypatch.setattr(modal.Dict, "from_name", progress_dict)

    storage = create_storage(
        Settings(runtime="modal", modal_data_volume="vol", modal_progress_dict="dct")
    )

    assert opened == {
        "volume": ("vol", {"create_if_missing": True, "version": 2}),
        "dict": ("dct", {"create_if_missing": True}),
    }
    assert isinstance(storage.repository.store, ModalVolumeStore)
    assert isinstance(storage.progress, ModalDictProgressStore)
