from __future__ import annotations

import numpy as np
import numpy.typing as npt
import pytest

from adcortex.analysis.reference import build_baseline

NAN = np.nan
INDICES = {"a": np.array([0, 1]), "b": np.array([2])}


def _grid(rows: list[list[float]]) -> npt.NDArray[np.float32]:
    return np.array(rows, dtype=np.float32)


def _two_clips() -> list[npt.NDArray[np.float32]]:
    return [
        _grid([[1, 1, 0], [3, 3, 0]]),
        _grid([[5, 5, 0], [NAN, NAN, NAN]]),
    ]


def test_system_statistics_pool_every_second_of_every_clip() -> None:
    baseline = build_baseline(_two_clips(), INDICES, version="v1", description="d")

    a = baseline.systems["a"]
    assert a.mean == pytest.approx(3.0)
    assert a.std == pytest.approx(np.std([1.0, 3.0, 5.0]))
    assert a.clip_means == pytest.approx((2.0, 5.0))
    assert baseline.n_clips == 2


def test_vertex_statistics_skip_seconds_without_a_prediction() -> None:
    baseline = build_baseline(_two_clips(), INDICES, version="v1", description="d")

    mean, std = baseline.vertex_stats()

    assert mean is not None
    assert std is not None
    assert mean == pytest.approx([3.0, 3.0, 0.0], rel=1e-3)
    assert std == pytest.approx([np.std([1.0, 3.0, 5.0])] * 2 + [0.0], rel=1e-3)


def test_each_clips_hook_is_its_opening_response_against_the_baseline() -> None:
    indices = {"a": np.array([0]), "b": np.array([1])}
    clips = [
        _grid([[2, 1], [2, 1], [2, 1], [0, 1]]),
        _grid([[0, 1], [0, 1], [0, 1], [0, 1]]),
    ]

    baseline = build_baseline(clips, indices, version="v1", description="d")

    a = np.array([2, 2, 2, 0, 0, 0, 0, 0], dtype=np.float64)
    # b never varies, so its z-score is 0 and halves the two-system composite.
    expected = ((2 - a.mean()) / a.std() / 2, (0 - a.mean()) / a.std() / 2)
    assert baseline.hook == pytest.approx(expected)


def test_a_baseline_needs_a_clip() -> None:
    with pytest.raises(ValueError, match="at least one clip"):
        build_baseline([], INDICES, version="v1", description="d")
