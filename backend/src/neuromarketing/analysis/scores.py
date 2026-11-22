"""Deterministic headline scores derived from the system z-curves.

* response_index: mean reference percentile of the applicable systems.
* hook: reference percentile of the mean response in the first 3 seconds.
* sustain: share of seconds (%) where the mean response is above the
  reference average.
* peak_count: number of peak moments.

All three need a baseline; without one they are None.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping

import numpy as np
import numpy.typing as npt

from neuromarketing.analysis.baseline import Baseline, percentile_of
from neuromarketing.domain.models import Scores

HOOK_SECONDS = 3
Curve = npt.NDArray[np.float64]


def composite(z: Mapping[str, Curve], system_ids: Collection[str]) -> Curve:
    """Per-second mean across systems, ignoring seconds with no prediction."""
    rows = [z[sid] for sid in system_ids]
    if not rows:
        return np.array([], dtype=np.float64)
    stacked = np.vstack(rows)
    valid = ~np.isnan(stacked)
    counts = valid.sum(axis=0)
    sums = np.where(valid, stacked, 0.0).sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(counts > 0, sums / np.maximum(counts, 1), np.nan)


def hook_value(z: Mapping[str, Curve], system_ids: Collection[str]) -> float | None:
    head = composite(z, system_ids)[:HOOK_SECONDS]
    head = head[~np.isnan(head)]
    return float(head.mean()) if head.size else None


def compute_scores(
    z: Mapping[str, Curve],
    applicable: Collection[str],
    percentiles: Mapping[str, float | None],
    baseline: Baseline | None,
    peak_count: int,
) -> Scores:
    ranked = [
        p for sid, p in percentiles.items() if sid in applicable and p is not None
    ]
    response_index = round(float(np.mean(ranked)), 1) if ranked else None
    hook = None
    sustain = None
    if baseline is not None:
        value = hook_value(z, applicable)
        if value is not None and baseline.hook:
            hook = percentile_of(value, baseline.hook)
        comp = composite(z, applicable)
        comp = comp[~np.isnan(comp)]
        if comp.size:
            sustain = round(100.0 * float((comp > 0).mean()), 1)
    return Scores(
        response_index=response_index,
        hook=hook,
        sustain=sustain,
        peak_count=peak_count,
    )
