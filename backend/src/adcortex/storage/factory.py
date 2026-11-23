"""Storage for the configured runtime."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from adcortex.config import Settings
from adcortex.storage.base import ProgressStore
from adcortex.storage.local import LocalFsStore, MemoryProgressStore
from adcortex.storage.repository import AnalysisRepository

# Volumes v2 handle many small files and writes from many containers better.
MODAL_VOLUME_VERSION = 2


@dataclass(frozen=True)
class Storage:
    repository: AnalysisRepository
    progress: ProgressStore


def create_storage(settings: Settings) -> Storage:
    if settings.runtime == "modal":
        return _modal_storage(settings)
    return Storage(
        repository=AnalysisRepository(LocalFsStore(settings.data_dir)),
        progress=MemoryProgressStore(),
    )


def _modal_storage(settings: Settings) -> Storage:
    import modal

    from adcortex.storage.modal_store import (
        DictLike,
        ModalDictProgressStore,
        ModalVolumeStore,
        VolumeLike,
    )

    volume = modal.Volume.from_name(
        settings.modal_data_volume, create_if_missing=True, version=MODAL_VOLUME_VERSION
    )
    progress = modal.Dict.from_name(
        settings.modal_progress_dict, create_if_missing=True
    )
    return Storage(
        repository=AnalysisRepository(ModalVolumeStore(cast(VolumeLike, volume))),
        progress=ModalDictProgressStore(cast(DictLike, progress)),
    )
