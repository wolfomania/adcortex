"""Turn a brain prediction into the analysis result the UI and LLM consume."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from neuromarketing.analysis.atlas import Atlas
from neuromarketing.analysis.baseline import Baseline, percentile_of
from neuromarketing.analysis.curves import Curve, nan_to_none, system_curves, to_grid
from neuromarketing.analysis.frames import brain_frames
from neuromarketing.analysis.moments import find_moments
from neuromarketing.analysis.scores import compute_scores
from neuromarketing.analysis.systems import SystemCatalog
from neuromarketing.brain.base import BrainPrediction
from neuromarketing.domain.models import (
    AnalysisResult,
    AnalysisSummary,
    LanguageInfo,
    MediaKind,
    Scene,
    SceneStat,
    SystemSeries,
)

TOP_SYSTEMS = 3


@dataclass(frozen=True)
class AnalysisInputs:
    prediction: BrainPrediction
    kind: MediaKind
    duration_s: float
    scenes: tuple[Scene, ...]
    language: LanguageInfo
    envelope: tuple[float, ...] = ()
    strip: str | None = None
    strip_columns: int = 10


@dataclass(frozen=True)
class AnalysisOutput:
    result: AnalysisResult
    frames: bytes
    summary: AnalysisSummary


def analyze(
    inputs: AnalysisInputs,
    *,
    catalog: SystemCatalog,
    atlas: Atlas,
    baseline: Baseline | None,
) -> AnalysisOutput:
    pred = inputs.prediction
    grid = to_grid(pred.preds, pred.times, inputs.duration_s)
    raw = system_curves(grid, catalog.vertex_indices(atlas))
    applicable = [
        s.id for s in catalog.systems if inputs.kind is MediaKind.VIDEO or not s.visual
    ]
    z = {sid: _zscore(curve, sid, baseline) for sid, curve in raw.items()}
    raw_means = {sid: _nanmean(curve) for sid, curve in raw.items()}
    percentiles = {
        sid: _percentile(sid, raw_means[sid], baseline) if sid in applicable else None
        for sid in raw
    }
    labels = {s.id: s.label for s in catalog.systems}
    z_lists = {sid: nan_to_none(curve) for sid, curve in z.items()}
    moments = find_moments({sid: z_lists[sid] for sid in applicable}, labels)
    series = tuple(
        SystemSeries(
            id=s.id,
            label=s.label,
            confidence=s.confidence,
            applicable=s.id in applicable,
            values=z_lists[s.id],
            mean_z=round(_nanmean(z[s.id]), 3),
            percentile=percentiles[s.id],
        )
        for s in catalog.systems
    )
    frames, frames_meta = brain_frames(grid, baseline)
    scores = compute_scores(
        z,
        applicable,
        percentiles,
        baseline,
        peak_count=sum(1 for m in moments if m.kind == "peak"),
    )
    result = AnalysisResult(
        duration_s=inputs.duration_s,
        times=tuple(float(i) for i in range(grid.shape[0])),
        systems=series,
        scenes=inputs.scenes,
        scene_stats=_scene_stats(inputs.scenes, z, applicable),
        moments=tuple(moments),
        scores=scores,
        transcript=pred.words,
        envelope=inputs.envelope,
        frames=frames_meta,
        baseline=baseline.ref() if baseline else None,
        language=inputs.language,
        strip=inputs.strip,
        strip_columns=inputs.strip_columns,
    )
    summary = AnalysisSummary(
        duration_s=inputs.duration_s,
        response_index=scores.response_index,
        top_systems=_top_systems(series),
        system_means={sid: round(v, 5) for sid, v in raw_means.items()},
    )
    return AnalysisOutput(result=result, frames=frames, summary=summary)


def _zscore(curve: Curve, system_id: str, baseline: Baseline | None) -> Curve:
    stats = baseline.systems.get(system_id) if baseline else None
    if stats is not None and stats.std > 0:
        return (curve - stats.mean) / stats.std
    valid = curve[~np.isnan(curve)]
    if valid.size < 2 or valid.std() == 0:
        return np.where(np.isnan(curve), np.nan, 0.0)
    return (curve - valid.mean()) / valid.std()


def _nanmean(curve: Curve) -> float:
    valid = curve[~np.isnan(curve)]
    return float(valid.mean()) if valid.size else 0.0


def _percentile(
    system_id: str, value: float, baseline: Baseline | None
) -> float | None:
    stats = baseline.systems.get(system_id) if baseline else None
    return percentile_of(value, stats.clip_means) if stats else None


def _scene_stats(
    scenes: tuple[Scene, ...], z: dict[str, Curve], applicable: list[str]
) -> tuple[SceneStat, ...]:
    stats = []
    for scene in scenes:
        centers = np.arange(len(next(iter(z.values())))) + 0.5
        inside = (centers >= scene.start) & (centers < scene.end)
        means: dict[str, float] = {}
        for sid in applicable:
            values = z[sid][inside]
            values = values[~np.isnan(values)]
            if values.size:
                means[sid] = round(float(values.mean()), 3)
        stats.append(SceneStat(scene_index=scene.index, mean_z=means))
    return tuple(stats)


def _top_systems(series: tuple[SystemSeries, ...]) -> tuple[str, ...]:
    candidates = [s for s in series if s.applicable]
    ranked = sorted(
        candidates,
        key=lambda s: (s.percentile if s.percentile is not None else -1.0, s.mean_z),
        reverse=True,
    )
    return tuple(s.id for s in ranked[:TOP_SYSTEMS])
