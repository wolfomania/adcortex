"""Percentiles against the user's own past analyses ("your library")."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from neuromarketing.analysis.baseline import percentile_of
from neuromarketing.domain.models import AnalysisResult

MIN_LIBRARY = 10


def library_percentiles(
    system_means: Mapping[str, float], library: Sequence[Mapping[str, float]]
) -> dict[str, float]:
    """Rank each system mean within the library; empty below MIN_LIBRARY."""
    if len(library) < MIN_LIBRARY:
        return {}
    ranked: dict[str, float] = {}
    for system_id, value in system_means.items():
        samples = [m[system_id] for m in library if system_id in m]
        percentile = percentile_of(value, samples)
        if percentile is not None and len(samples) >= MIN_LIBRARY:
            ranked[system_id] = percentile
    return ranked


def apply_library(
    result: AnalysisResult, percentiles: Mapping[str, float]
) -> AnalysisResult:
    systems = tuple(
        s.model_copy(
            update={
                "library_percentile": percentiles.get(s.id) if s.applicable else None
            }
        )
        for s in result.systems
    )
    return result.model_copy(update={"systems": systems})
