"""Place TRIBE predictions on a 1 Hz grid and average them per brain system."""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import numpy.typing as npt

from adcortex.media.scenes import seconds_grid

FloatArray = npt.NDArray[np.float32]
Curve = npt.NDArray[np.float64]


def to_grid(
    preds: FloatArray, times: npt.NDArray[np.float64], duration: float
) -> FloatArray:
    """Return an (n_seconds, n_vertices) array; seconds TRIBE skipped are NaN.

    Row k holds the prediction whose segment starts in [k, k + 1). The time
    comes from the segment, never from the row position: TRIBE drops empty
    segments, so positions and seconds can disagree.
    """
    n = seconds_grid(duration)
    sums = np.zeros((n, preds.shape[1]), dtype=np.float64)
    counts = np.zeros(n, dtype=np.int64)
    index = np.floor(times + 1e-6).astype(np.int64)
    for row, second in enumerate(index):
        if 0 <= second < n:
            sums[second] += preds[row]
            counts[second] += 1
    grid = np.full_like(sums, np.nan, dtype=np.float32)
    filled = counts > 0
    grid[filled] = (sums[filled] / counts[filled, None]).astype(np.float32)
    return grid


def system_curves(
    grid: FloatArray, indices: Mapping[str, npt.NDArray[np.intp]]
) -> dict[str, npt.NDArray[np.float64]]:
    """Mean over each system's vertices, per second (NaN where TRIBE skipped)."""
    return {
        system_id: grid[:, vertices].astype(np.float64).mean(axis=1)
        for system_id, vertices in indices.items()
    }


def nan_to_none(
    values: npt.NDArray[np.float64], digits: int = 3
) -> tuple[float | None, ...]:
    return tuple(None if np.isnan(v) else round(float(v), digits) for v in values)
