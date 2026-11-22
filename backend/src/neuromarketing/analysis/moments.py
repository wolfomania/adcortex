"""Peaks and dips in system curves, reported as timestamped moments."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from neuromarketing.domain.models import Moment

PEAK_Z = 1.0
PEAK_PROMINENCE = 0.75
MIN_DISTANCE_S = 3
MAX_MOMENTS = 12


def find_peaks(
    values: Sequence[float | None],
    *,
    min_height: float,
    min_prominence: float,
    min_distance: int,
) -> list[int]:
    """Indices of local maxima, filtered by height, prominence, and spacing.

    Gaps (None) never count as neighbours. On a plateau only the first
    sample is reported. Among peaks closer than `min_distance`, the higher
    one wins.
    """
    valid = [(i, v) for i, v in enumerate(values) if v is not None]
    candidates: list[tuple[int, float]] = []
    for k, (i, v) in enumerate(valid):
        left = valid[k - 1][1] if k > 0 else float("-inf")
        right = valid[k + 1][1] if k + 1 < len(valid) else float("-inf")
        if v > left and v >= right and v >= min_height:
            prominence = v - max(_base(valid, k, -1), _base(valid, k, +1))
            if prominence >= min_prominence:
                candidates.append((i, v))
    chosen: list[int] = []
    for i, _v in sorted(candidates, key=lambda c: c[1], reverse=True):
        if all(abs(i - j) >= min_distance for j in chosen):
            chosen.append(i)
    return sorted(chosen)


def _base(valid: list[tuple[int, float]], k: int, step: int) -> float:
    """Lowest value between sample k and the next higher sample (or the edge)."""
    peak = valid[k][1]
    lowest = peak
    j = k + step
    while 0 <= j < len(valid):
        value = valid[j][1]
        if value > peak:
            break
        lowest = min(lowest, value)
        j += step
    return lowest


def find_moments(
    curves: Mapping[str, Sequence[float | None]],
    labels: Mapping[str, str],
    *,
    limit: int = MAX_MOMENTS,
) -> list[Moment]:
    """Strongest peaks and dips across systems, sorted by time."""
    found: list[Moment] = []
    for system_id, values in curves.items():
        label = labels[system_id]
        for i in _peaks(values):
            z = float(values[i] or 0.0)
            found.append(
                Moment(
                    t=float(i),
                    kind="peak",
                    system_id=system_id,
                    z=round(z, 2),
                    label=f"{label} peak (+{z:.1f} SD)",
                )
            )
        negated = [None if v is None else -v for v in values]
        for i in _peaks(negated):
            z = float(values[i] or 0.0)
            found.append(
                Moment(
                    t=float(i),
                    kind="dip",
                    system_id=system_id,
                    z=round(z, 2),
                    label=f"{label} dip ({z:.1f} SD)",
                )
            )
    strongest = sorted(found, key=lambda m: abs(m.z), reverse=True)[:limit]
    return sorted(strongest, key=lambda m: (m.t, m.system_id))


def _peaks(values: Sequence[float | None]) -> list[int]:
    return find_peaks(
        values,
        min_height=PEAK_Z,
        min_prominence=PEAK_PROMINENCE,
        min_distance=MIN_DISTANCE_S,
    )
