"""Build the reference baseline from the predictions of reference clips.

`scripts/build_baseline.py` runs the clips listed in `baseline/sources.yaml`
through a deployed app and passes their predictions here.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np
import numpy.typing as npt

from adcortex.analysis.baseline import Baseline, SystemStats
from adcortex.analysis.curves import system_curves
from adcortex.analysis.run import zscore
from adcortex.analysis.scores import hook_value

Grid = npt.NDArray[np.float32]
Curve = npt.NDArray[np.float64]


def build_baseline(
    grids: Sequence[Grid],
    indices: Mapping[str, npt.NDArray[np.intp]],
    *,
    version: str,
    description: str,
) -> Baseline:
    """Reference statistics over every predicted second of every clip.

    Each grid is one clip's (n_seconds, n_vertices) prediction from
    `to_grid`; rows of NaN are seconds without a prediction. Each clip's hook
    is the opening response of its z-scores against these statistics, as
    `compute_scores` measures it for a new analysis.
    """
    if not grids:
        raise ValueError("A baseline needs at least one clip.")
    curves = [system_curves(grid, indices) for grid in grids]
    systems = {sid: _system_stats([clip[sid] for clip in curves]) for sid in indices}
    stats_only = Baseline.build(
        version=version,
        description=description,
        systems=systems,
        hook=(),
        n_clips=len(grids),
    )
    hooks = [
        hook_value(
            {sid: zscore(clip[sid], sid, stats_only) for sid in indices}, indices
        )
        for clip in curves
    ]
    seconds = np.vstack([grid[~np.isnan(grid).any(axis=1)] for grid in grids])
    return Baseline.build(
        version=version,
        description=description,
        systems=systems,
        hook=[hook for hook in hooks if hook is not None],
        n_clips=len(grids),
        vertex_mean=seconds.mean(axis=0, dtype=np.float64).astype(np.float32),
        vertex_std=seconds.std(axis=0, dtype=np.float64).astype(np.float32),
    )


def _system_stats(curves: Sequence[Curve]) -> SystemStats:
    values = np.concatenate([curve[~np.isnan(curve)] for curve in curves])
    return SystemStats(
        mean=float(values.mean()),
        std=float(values.std()),
        clip_means=tuple(float(np.nanmean(curve)) for curve in curves),
    )
