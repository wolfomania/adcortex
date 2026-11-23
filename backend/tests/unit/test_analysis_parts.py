from __future__ import annotations

import math

import numpy as np
import pytest

from adcortex.analysis.baseline import Baseline, SystemStats, percentile_of
from adcortex.analysis.curves import system_curves, to_grid
from adcortex.analysis.frames import brain_frames
from adcortex.analysis.moments import find_peaks
from adcortex.brain.base import BrainPrediction
from adcortex.domain.models import Word

# ── grid ───────────────────────────────────────────────────────────────────


def test_to_grid_places_rows_by_segment_start_not_position() -> None:
    preds = np.array([[1.0], [2.0], [4.0]], dtype=np.float32)
    times = np.array([0.0, 1.0, 3.0])  # second 2 was dropped by TRIBE

    grid = to_grid(preds, times, duration=4.2)

    assert grid.shape == (5, 1)
    assert grid[:, 0].tolist()[:2] == [1.0, 2.0]
    assert math.isnan(grid[2, 0])
    assert grid[3, 0] == 4.0
    assert math.isnan(grid[4, 0])


def test_to_grid_ignores_predictions_past_the_end_and_averages_duplicates() -> None:
    preds = np.array([[1.0], [3.0], [9.0]], dtype=np.float32)
    times = np.array([0.0, 0.4, 7.0])

    grid = to_grid(preds, times, duration=2.0)

    assert grid.shape == (2, 1)
    assert grid[0, 0] == pytest.approx(2.0)
    assert math.isnan(grid[1, 0])


def test_system_curves_average_vertices_and_keep_gaps() -> None:
    grid = np.array([[1, 3, 10], [np.nan, np.nan, np.nan]], dtype=np.float32)

    curves = system_curves(grid, {"a": np.array([0, 1]), "b": np.array([2])})

    assert curves["a"][0] == pytest.approx(2.0)
    assert math.isnan(curves["a"][1])
    assert curves["b"][0] == pytest.approx(10.0)


# ── percentiles ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("value", "expected"),
    [(0.0, 0.0), (2.5, 40.0), (3.0, 50.0), (2.0, 30.0), (10.0, 100.0)],
)
def test_percentile_of_uses_mid_rank(value: float, expected: float) -> None:
    assert percentile_of(value, [1.0, 2.0, 3.0, 4.0, 5.0]) == pytest.approx(expected)


def test_percentile_of_empty_sample_is_none() -> None:
    assert percentile_of(1.0, []) is None


def test_baseline_round_trips_vertex_stats() -> None:
    mean = np.linspace(-1, 1, 6, dtype=np.float32)
    std = np.full(6, 0.5, dtype=np.float32)

    baseline = Baseline.build(
        version="t",
        description="test",
        systems={"a": SystemStats(mean=0.0, std=1.0, clip_means=(0.1, 0.2))},
        hook=(0.0, 1.0),
        vertex_mean=mean,
        vertex_std=std,
        n_clips=2,
    )
    loaded = Baseline.model_validate_json(baseline.model_dump_json())

    got_mean, got_std = loaded.vertex_stats()
    assert got_mean is not None
    assert got_std is not None
    np.testing.assert_allclose(got_mean, mean, atol=1e-3)
    np.testing.assert_allclose(got_std, std, atol=1e-3)


# ── peaks ──────────────────────────────────────────────────────────────────


def test_find_peaks_respects_height_prominence_and_distance() -> None:
    values = [0, 0.2, 2.0, 0.1, 0, 1.6, 1.4, 1.7, 0.0, 0, 0.5, 0]

    peaks = find_peaks(values, min_height=1.0, min_prominence=0.75, min_distance=3)

    # 2.0 at 2 and 1.7 at 7 qualify; 1.6 at 5 is too close to 7 and too shallow.
    assert peaks == [2, 7]


def test_find_peaks_skips_gaps() -> None:
    values: list[float | None] = [0.0, None, 3.0, None, 0.0]

    assert find_peaks(values, min_height=1.0, min_prominence=0.5, min_distance=1) == [2]


def test_find_peaks_handles_plateaus_once() -> None:
    values = [0.0, 2.0, 2.0, 0.0]

    assert find_peaks(values, min_height=1.0, min_prominence=0.5, min_distance=1) == [1]


# ── frames ─────────────────────────────────────────────────────────────────


def test_brain_frames_quantize_within_clip_without_baseline() -> None:
    grid = np.array([[0.0, 5.0], [2.0, 5.0], [np.nan, np.nan]], dtype=np.float32)

    data, meta = brain_frames(grid, baseline=None)

    frames = np.frombuffer(data, dtype=np.uint8).reshape(3, 2)
    assert (meta.n_frames, meta.n_vertices) == (3, 2)
    assert (meta.vmin, meta.vmax) == (-3.0, 3.0)
    # Vertex 0 goes from -1 SD to +1 SD; constant vertex 1 stays at the midpoint.
    assert frames[0, 0] < 128 < frames[1, 0]
    assert frames[0, 1] == frames[1, 1] == 128
    # The missing last second repeats the previous frame.
    assert frames[2].tolist() == frames[1].tolist()


def test_prediction_npz_round_trip() -> None:
    prediction = BrainPrediction(
        preds=np.arange(6, dtype=np.float32).reshape(2, 3),
        times=np.array([0.0, 1.0]),
        words=(Word(text="hi", start=0.1, end=0.4),),
        language="en",
        model="mock",
        timings={"predict": 1.5},
    )

    loaded = BrainPrediction.from_npz(prediction.to_npz())

    np.testing.assert_allclose(loaded.preds, prediction.preds)
    assert loaded.times.tolist() == [0.0, 1.0]
    assert loaded.words == prediction.words
    assert (loaded.language, loaded.model) == ("en", "mock")
    assert loaded.timings == {"predict": 1.5}


def test_prediction_rejects_mismatched_shapes() -> None:
    with pytest.raises(ValueError, match="one entry per"):
        BrainPrediction(preds=np.zeros((2, 3), np.float32), times=np.zeros(3))
