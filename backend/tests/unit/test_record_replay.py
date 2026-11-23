"""scripts/record_replay_fixture.py: a real run becomes the replay recording."""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

from adcortex.brain.base import BrainPrediction, BrainRequest
from adcortex.brain.replay import ReplayBrain
from adcortex.domain.models import Word

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "record_replay_fixture.py"
ID = "20261123-121600-3ad554"


@pytest.fixture(scope="module")
def record() -> Iterator[ModuleType]:
    with pytest.MonkeyPatch.context() as patch:
        spec = importlib.util.spec_from_file_location("adcortex_record_replay", SCRIPT)
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        patch.setitem(sys.modules, spec.name, module)
        spec.loader.exec_module(module)
        yield module


def real_run(seconds: int = 40) -> BrainPrediction:
    rng = np.random.default_rng(0)
    return BrainPrediction(
        preds=rng.standard_normal((seconds, 8)).astype(np.float32),
        times=np.arange(seconds, dtype=np.float64),
        words=(Word(text="hello", start=0.5, end=0.9),),
        language="en",
        model="tribev2",
        timings={"predict": 12.0},
    )


def test_the_recording_keeps_the_first_seconds_without_the_transcript(
    record: ModuleType,
) -> None:
    kept = record.recording(real_run(), seconds=30)

    assert kept.preds.shape == (30, 8)
    assert kept.times[-1] == 29.0
    assert (kept.words, kept.language, kept.timings) == ((), None, {})
    assert kept.model == "tribev2"


def test_the_replay_brain_plays_a_recorded_run(
    record: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "replay.npz"
    monkeypatch.setattr(record, "download", lambda volume, id_: real_run().to_npz())

    assert record.main([ID, "--seconds", "5", "--out", str(out)]) == 0

    media = tmp_path / "clip.mp4"
    media.write_bytes(b"video")
    played = ReplayBrain(out).predict(
        BrainRequest(media=media, kind="video", duration_s=7.0)
    )
    assert played.preds.shape == (7, 8)
    assert played.model == "replay:tribev2"


def test_a_missing_prediction_is_reported(
    record: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def missing(volume: str, analysis_id: str) -> bytes:
        raise FileNotFoundError(analysis_id)

    monkeypatch.setattr(record, "download", missing)

    assert record.main([ID, "--out", str(tmp_path / "replay.npz")]) == 1
    assert not (tmp_path / "replay.npz").exists()
