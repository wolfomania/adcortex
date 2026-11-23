"""The TRIBE v2 wrapper's job handling, with a fake model in place of TRIBE."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import numpy as np
import pytest

from neuromarketing.brain.base import BrainRequest
from neuromarketing.brain.tribe import TribeBrain


class FakeTribe:
    """Caches one file per job, and fails like TRIBE's feature caches (exca)
    do when their folder disappears after the model has loaded."""

    def __init__(self, cache: Path) -> None:
        self.folder = cache / "HuggingFaceText._get_data"
        self.folder.mkdir(parents=True)

    def predict(self, events: Any, verbose: bool = False) -> tuple[Any, list[Any]]:
        self.folder.lstat()
        cached = len(list(self.folder.iterdir()))
        (self.folder / f"features-{cached}.npy").write_bytes(b"x" * 10)
        segments = [SimpleNamespace(start=0.0), SimpleNamespace(start=1.0)]
        return np.zeros((2, 4)), segments


@pytest.fixture
def brain(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TribeBrain:
    cache = tmp_path / "features"
    brain = TribeBrain(
        checkpoint="facebook/tribev2", whisperx=cast(Any, None), cache_dir=cache
    )
    brain._model = FakeTribe(cache)
    monkeypatch.setattr(brain, "_events", lambda media, request: (media, "en", []))
    return brain


@pytest.fixture
def request_(tmp_path: Path) -> BrainRequest:
    media = tmp_path / "clip.mp4"
    media.write_bytes(b"video")
    return BrainRequest(media=media, kind="video", duration_s=2.0)


def test_the_feature_cache_survives_between_jobs(
    brain: TribeBrain, request_: BrainRequest
) -> None:
    first = brain.predict(request_)
    second = brain.predict(request_)

    assert first.preds.shape == second.preds.shape == (2, 4)
    assert brain.cache_bytes() == 20


def test_each_job_reads_its_media_from_a_new_path(
    brain: TribeBrain, request_: BrainRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[Path] = []

    def events(media: Path, request: BrainRequest) -> tuple[Any, str, list[Any]]:
        seen.append(media)
        return media, "en", []

    monkeypatch.setattr(brain, "_events", events)

    brain.predict(request_)
    brain.predict(request_)

    assert len({path.name for path in seen}) == 2
    assert all(path.suffix == ".mp4" for path in seen)


def test_an_empty_cache_takes_no_space(tmp_path: Path) -> None:
    brain = TribeBrain(
        checkpoint="facebook/tribev2",
        whisperx=cast(Any, None),
        cache_dir=tmp_path / "missing",
    )

    assert brain.cache_bytes() == 0
