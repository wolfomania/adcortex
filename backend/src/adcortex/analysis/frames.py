"""Per-second cortical maps, z-scored and quantized to one byte per vertex."""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

from adcortex.analysis.baseline import Baseline
from adcortex.domain.models import BrainFrames

Z_RANGE = 3.0


def brain_frames(
    grid: npt.NDArray[np.float32], baseline: Baseline | None
) -> tuple[bytes, BrainFrames]:
    """Quantize z-scores in [-3, 3] to uint8 (128 = reference average).

    With a baseline that carries vertex statistics, z-scores compare each
    vertex with the reference clips; otherwise they are relative to this
    clip's own average. Missing seconds repeat the nearest earlier frame.
    """
    z = _zscore(grid, baseline)
    z = _fill_gaps(z)
    clipped = np.clip(z, -Z_RANGE, Z_RANGE)
    quantized = np.round((clipped + Z_RANGE) / (2 * Z_RANGE) * 255).astype(np.uint8)
    meta = BrainFrames(
        n_frames=int(quantized.shape[0]),
        n_vertices=int(quantized.shape[1]),
        vmin=-Z_RANGE,
        vmax=Z_RANGE,
    )
    return quantized.tobytes(), meta


def _zscore(
    grid: npt.NDArray[np.float32], baseline: Baseline | None
) -> npt.NDArray[np.float64]:
    data = grid.astype(np.float64)
    ref_mean, ref_std = baseline.vertex_stats() if baseline else (None, None)
    if (
        ref_mean is not None
        and ref_std is not None
        and ref_mean.shape[0] == data.shape[1]
    ):
        mean = ref_mean.astype(np.float64)
        std = ref_std.astype(np.float64)
    else:
        valid = ~np.isnan(data).all(axis=1)
        if not valid.any():
            return np.zeros_like(data)
        mean = data[valid].mean(axis=0)
        std = data[valid].std(axis=0)
    safe_std = np.where(std > 1e-6, std, np.inf)
    z: npt.NDArray[np.float64] = (data - mean) / safe_std
    return z


def _fill_gaps(z: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    out = z.copy()
    missing = np.isnan(out).all(axis=1)
    if missing.all():
        return np.zeros_like(out)
    first_valid = int(np.argmax(~missing))
    out[:first_valid] = out[first_valid]
    for row in range(first_valid + 1, out.shape[0]):
        if missing[row]:
            out[row] = out[row - 1]
    return np.nan_to_num(out)
