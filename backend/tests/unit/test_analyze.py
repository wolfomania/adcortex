from __future__ import annotations

import numpy as np
import pytest

from neuromarketing.analysis.atlas import N_VERTICES, load_atlas
from neuromarketing.analysis.baseline import Baseline, SystemStats
from neuromarketing.analysis.library import apply_library, library_percentiles
from neuromarketing.analysis.run import AnalysisInputs, AnalysisOutput, analyze
from neuromarketing.analysis.systems import load_systems
from neuromarketing.brain.base import BrainPrediction
from neuromarketing.domain.models import LanguageInfo, MediaKind, Scene

DURATION = 12.4


def _prediction(
    *, faces_peak_at: int = 5, drop_second: int | None = None
) -> BrainPrediction:
    """Quiet noise everywhere, plus a sharp faces response at one second."""
    rng = np.random.default_rng(0)
    seconds = [s for s in range(13) if s != drop_second]
    preds = rng.normal(0.0, 0.05, size=(len(seconds), N_VERTICES)).astype(np.float32)
    faces = load_systems().vertex_indices(load_atlas())["faces"]
    for row, second in enumerate(seconds):
        if second == faces_peak_at:
            preds[row, faces] += 2.0
    return BrainPrediction(
        preds=preds, times=np.array(seconds, dtype=np.float64), model="test"
    )


def _inputs(kind: MediaKind = MediaKind.VIDEO, **kwargs: object) -> AnalysisInputs:
    return AnalysisInputs(
        prediction=_prediction(**kwargs),  # type: ignore[arg-type]
        kind=kind,
        duration_s=DURATION,
        scenes=(
            Scene(index=0, start=0.0, end=6.0),
            Scene(index=1, start=6.0, end=DURATION),
        ),
        envelope=(0.1, 0.2),
        language=LanguageInfo(requested="auto", detected="en", full_support=True),
    )


def _baseline() -> Baseline:
    ids = load_systems().ids
    return Baseline.build(
        version="test",
        description="flat reference",
        n_clips=5,
        systems={
            sid: SystemStats(mean=0.0, std=0.1, clip_means=(-0.2, -0.1, 0.0, 0.1, 0.2))
            for sid in ids
        },
        hook=(-1.0, -0.5, 0.0, 0.5, 1.0),
    )


def test_timeline_matches_media_duration_not_segment_count() -> None:
    out = _analyze(_inputs(drop_second=3), None)

    assert out.result.duration_s == DURATION
    assert out.result.times == tuple(float(s) for s in range(13))
    faces = next(s for s in out.result.systems if s.id == "faces")
    assert len(faces.values) == 13
    assert faces.values[3] is None


def test_without_baseline_reports_relative_values_only() -> None:
    out = _analyze(_inputs(), None)

    assert out.result.baseline is None
    assert out.result.scores.response_index is None
    assert out.result.scores.hook is None
    assert all(s.percentile is None for s in out.result.systems)


def test_with_baseline_ranks_systems_and_scores() -> None:
    out = _analyze(_inputs(), _baseline())

    faces = next(s for s in out.result.systems if s.id == "faces")
    # Clip mean is 2.0 / 13 = 0.15: above 4 of the 5 reference clip means.
    assert faces.percentile == 80.0
    assert faces.values[5] == pytest.approx(20.0, rel=0.1)
    assert out.result.baseline is not None
    assert out.result.scores.response_index is not None
    assert out.result.scores.sustain is not None


def test_planted_faces_response_becomes_a_peak_moment() -> None:
    out = _analyze(_inputs(faces_peak_at=5), None)

    peaks = [
        m for m in out.result.moments if m.kind == "peak" and m.system_id == "faces"
    ]
    assert [m.t for m in peaks] == [5.0]
    assert peaks[0].label.startswith("Faces peak")
    assert out.result.scores.peak_count >= 1


def test_audio_input_marks_visual_systems_not_applicable() -> None:
    out = _analyze(_inputs(kind=MediaKind.AUDIO), _baseline())

    applicable = {s.id: s.applicable for s in out.result.systems}
    assert applicable["faces"] is False
    assert applicable["visual"] is False
    assert applicable["speech"] is True
    faces = next(s for s in out.result.systems if s.id == "faces")
    assert faces.percentile is None
    assert all(m.system_id != "faces" for m in out.result.moments)


def test_scene_stats_average_seconds_inside_each_scene() -> None:
    out = _analyze(_inputs(faces_peak_at=5), None)

    first, second = out.result.scene_stats
    assert first.scene_index == 0
    assert first.mean_z["faces"] > second.mean_z["faces"]


def test_frames_cover_every_second_and_vertex() -> None:
    out = _analyze(_inputs(), None)

    assert out.result.frames is not None
    assert out.result.frames.n_frames == 13
    assert len(out.frames) == 13 * N_VERTICES


def test_summary_lists_top_systems_and_raw_means() -> None:
    out = _analyze(_inputs(), _baseline())

    assert out.summary.top_systems[0] == "faces"
    assert set(out.summary.system_means) == set(load_systems().ids)
    assert out.summary.duration_s == DURATION


def test_library_percentiles_need_ten_analyses() -> None:
    means = {"faces": 0.5}

    assert library_percentiles(means, [{"faces": 0.1}] * 9) == {}
    ranked = library_percentiles(means, [{"faces": v / 10} for v in range(10)])
    assert ranked["faces"] == pytest.approx(55.0)


def test_apply_library_sets_library_percentile() -> None:
    out = _analyze(_inputs(), None)

    updated = apply_library(out.result, {"faces": 80.0})

    faces = next(s for s in updated.systems if s.id == "faces")
    assert faces.library_percentile == 80.0
    assert (
        next(s for s in updated.systems if s.id == "visual").library_percentile is None
    )


def _analyze(inputs: AnalysisInputs, baseline: Baseline | None) -> AnalysisOutput:
    return analyze(
        inputs, catalog=load_systems(), atlas=load_atlas(), baseline=baseline
    )
