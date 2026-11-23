from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from adcortex.analysis.atlas import N_VERTICES, load_atlas
from adcortex.analysis.systems import load_systems
from adcortex.brain.base import BrainPrediction, BrainRequest
from adcortex.brain.factory import create_brain
from adcortex.brain.mock import MockBrain
from adcortex.brain.replay import ReplayBrain
from adcortex.config import Settings
from adcortex.domain.errors import NeuroError
from adcortex.domain.models import Word


def _system_curve(prediction: BrainPrediction, system_id: str) -> np.ndarray:
    vertices = load_systems().vertex_indices(load_atlas())[system_id]
    return prediction.preds[:, vertices].mean(axis=1)


# ── mock ───────────────────────────────────────────────────────────────────


@pytest.mark.ffmpeg
def test_mock_covers_every_second_and_vertex(media_dir: Path) -> None:
    request = BrainRequest(
        media=media_dir / "three_scenes.mp4", kind="video", duration_s=6.0
    )

    prediction = MockBrain().predict(request)

    assert prediction.preds.shape == (6, N_VERTICES)
    assert prediction.times.tolist() == [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]
    assert prediction.model == "mock"


@pytest.mark.ffmpeg
def test_mock_is_deterministic_per_file_and_seed(media_dir: Path) -> None:
    request = BrainRequest(
        media=media_dir / "three_scenes.mp4", kind="video", duration_s=6.0
    )
    brain = MockBrain()

    first = brain.predict(request)
    again = brain.predict(request)
    reseeded = brain.predict(
        BrainRequest(media=request.media, kind="video", duration_s=6.0, seed=1)
    )

    np.testing.assert_array_equal(first.preds, again.preds)
    assert not np.array_equal(first.preds, reseeded.preds)


@pytest.mark.ffmpeg
def test_mock_visual_response_follows_scene_cuts(media_dir: Path) -> None:
    # three_scenes.mp4 cuts at 2 s and 4 s.
    request = BrainRequest(
        media=media_dir / "three_scenes.mp4", kind="video", duration_s=6.0
    )

    visual = _system_curve(MockBrain().predict(request), "visual")

    assert visual[2] > visual[1]
    assert visual[4] > visual[3]


@pytest.mark.ffmpeg
def test_mock_audio_input_keeps_visual_systems_quiet(media_dir: Path) -> None:
    request = BrainRequest(media=media_dir / "tone.wav", kind="audio", duration_s=5.0)

    prediction = MockBrain().predict(request)

    visual = _system_curve(prediction, "visual")
    sound = _system_curve(prediction, "sound")
    assert np.abs(visual).max() < np.abs(sound).max()


def test_mock_survives_unreadable_media(tmp_path: Path) -> None:
    junk = tmp_path / "junk.mp4"
    junk.write_bytes(b"not a video")

    prediction = MockBrain().predict(
        BrainRequest(media=junk, kind="video", duration_s=3.5)
    )

    assert prediction.preds.shape == (4, N_VERTICES)
    assert np.isfinite(prediction.preds).all()


def test_mock_spreads_script_words_over_the_clip(tmp_path: Path) -> None:
    audio = tmp_path / "speech.wav"
    audio.write_bytes(b"")
    request = BrainRequest(
        media=audio,
        kind="audio",
        duration_s=4.0,
        language="en",
        script="Fresh coffee every morning.",
    )

    prediction = MockBrain().predict(request)

    assert [w.text for w in prediction.words] == [
        "Fresh",
        "coffee",
        "every",
        "morning.",
    ]
    assert prediction.words[0].start == 0.0
    assert prediction.words[-1].end <= 4.0
    assert prediction.language == "en"


# ── replay ─────────────────────────────────────────────────────────────────


def _fixture(tmp_path: Path, rows: int = 10) -> Path:
    prediction = BrainPrediction(
        preds=np.arange(rows * 4, dtype=np.float32).reshape(rows, 4),
        times=np.arange(rows, dtype=np.float64),
        words=(Word(text="fixture", start=0.0, end=0.5),),
        language="en",
        model="tribev2",
    )
    path = tmp_path / "replay.npz"
    path.write_bytes(prediction.to_npz())
    return path


def test_replay_truncates_the_recording_to_the_clip(tmp_path: Path) -> None:
    brain = ReplayBrain(_fixture(tmp_path))

    prediction = brain.predict(
        BrainRequest(media=tmp_path / "x.mp4", kind="video", duration_s=4.5)
    )

    assert prediction.times.tolist() == [0.0, 1.0, 2.0, 3.0, 4.0]
    assert prediction.preds[4].tolist() == [16.0, 17.0, 18.0, 19.0]
    assert prediction.model == "replay:tribev2"
    assert prediction.words == ()


def test_replay_loops_a_short_recording(tmp_path: Path) -> None:
    brain = ReplayBrain(_fixture(tmp_path, rows=10))

    prediction = brain.predict(
        BrainRequest(media=tmp_path / "x.mp4", kind="video", duration_s=25.0)
    )

    assert prediction.preds.shape == (25, 4)
    np.testing.assert_array_equal(prediction.preds[12], prediction.preds[2])


def test_replay_without_recording_fails_at_start_up(tmp_path: Path) -> None:
    with pytest.raises(NeuroError, match="Replay recording not found"):
        ReplayBrain(tmp_path / "missing.npz")


# ── factory ────────────────────────────────────────────────────────────────


def test_factory_builds_the_configured_backend(tmp_path: Path) -> None:
    assert isinstance(create_brain(Settings(brain_backend="mock")), MockBrain)
    replay = create_brain(
        Settings(brain_backend="replay", replay_fixture=_fixture(tmp_path))
    )
    assert isinstance(replay, ReplayBrain)


def test_factory_defers_tribe_imports_until_first_use() -> None:
    brain = create_brain(Settings(brain_backend="tribe"))

    assert brain.name == "tribev2"
