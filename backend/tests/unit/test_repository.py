from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest

from adcortex.domain.errors import NotFoundError
from adcortex.domain.models import (
    AnalysisMeta,
    AnalysisResult,
    AnalysisState,
    ComparisonReport,
    JobRef,
    KeyMoment,
    LanguageInfo,
    MediaKind,
    Recommendation,
    Report,
    Scores,
    SourceFile,
    Status,
    StoredComparison,
    StoredReport,
)
from adcortex.storage.local import LocalFsStore
from adcortex.storage.repository import PREDICTION, AnalysisRepository

OLD = "20261120-090000-aaaaaa"
MID = "20261121-090000-bbbbbb"
NEW = "20261122-090000-cccccc"
FINGERPRINT = "f" * 64
CREATED = datetime(2026, 11, 22, tzinfo=UTC)


@pytest.fixture
def repo(tmp_path: Path) -> AnalysisRepository:
    return AnalysisRepository(LocalFsStore(tmp_path))


def _meta(analysis_id: str, name: str = "Clip") -> AnalysisMeta:
    return AnalysisMeta(
        id=analysis_id,
        name=name,
        kind=MediaKind.VIDEO,
        created_at=CREATED,
        source=SourceFile(
            filename="ad.mp4", extension=".mp4", size_bytes=3, sha256="0" * 64
        ),
    )


def _state(status: Status = Status.QUEUED) -> AnalysisState:
    return AnalysisState(status=status)


def _create(repo: AnalysisRepository, *ids: str) -> None:
    for analysis_id in ids:
        repo.create(_meta(analysis_id), _state())


def _result() -> AnalysisResult:
    return AnalysisResult(
        duration_s=1.0,
        times=(0.0,),
        systems=(),
        scenes=(),
        scene_stats=(),
        moments=(),
        scores=Scores(response_index=None, hook=None, sustain=None, peak_count=0),
        transcript=(),
        language=LanguageInfo(),
    )


def _report() -> StoredReport:
    return StoredReport(
        model="test",
        input_mode="text",
        created_at=CREATED,
        report=Report(
            headline="h",
            summary="s",
            key_moments=[
                KeyMoment(
                    t=0,
                    title="t",
                    what_happens="w",
                    brain_response="b",
                    why_it_matters="y",
                )
            ],
            strengths=["s"],
            risks=["r"],
            recommendations=[Recommendation(title="t", detail="d")],
        ),
    )


def _comparison(a_id: str, b_id: str) -> StoredComparison:
    return StoredComparison(
        a_id=a_id,
        b_id=b_id,
        model="test",
        created_at=CREATED,
        report=ComparisonReport(
            headline="h",
            summary="s",
            a_strengths=["a"],
            b_strengths=["b"],
            recommendation="r",
        ),
    )


# ── analyses ───────────────────────────────────────────────────────────────


def test_created_analysis_reads_back(repo: AnalysisRepository) -> None:
    repo.create(_meta(NEW, "Launch spot"), _state())

    analysis = repo.get(NEW)

    assert analysis.meta.name == "Launch spot"
    assert analysis.state.status is Status.QUEUED
    assert repo.exists(NEW)


def test_history_is_newest_first_and_pages_backwards(repo: AnalysisRepository) -> None:
    _create(repo, MID, OLD, NEW)

    first_page = repo.history(limit=2)
    second_page = repo.history(limit=2, before=first_page[-1].meta.id)

    assert [a.meta.id for a in first_page] == [NEW, MID]
    assert [a.meta.id for a in second_page] == [OLD]


def test_history_skips_incomplete_and_unreadable_analyses(
    repo: AnalysisRepository, caplog: pytest.LogCaptureFixture
) -> None:
    _create(repo, NEW)
    repo.store.write_bytes(
        f"analyses/{MID}/state.json", _state().model_dump_json().encode()
    )
    repo.store.write_bytes(f"analyses/{OLD}/meta.json", b"not json")
    repo.store.write_bytes(f"analyses/{OLD}/state.json", b"{}")
    repo.store.write_bytes("analyses/stray-folder/meta.json", b"{}")

    with caplog.at_level(logging.WARNING):
        history = repo.history()

    assert [a.meta.id for a in history] == [NEW]
    assert OLD in caplog.text


@pytest.mark.parametrize("analysis_id", [MID, "../../etc", "20261122-090000-CCCCCC"])
def test_unknown_or_malformed_ids_are_not_found(
    repo: AnalysisRepository, analysis_id: str
) -> None:
    _create(repo, NEW)

    with pytest.raises(NotFoundError):
        repo.get(analysis_id)
    assert not repo.exists(analysis_id)


def test_renaming_keeps_the_pipeline_state(repo: AnalysisRepository) -> None:
    _create(repo, NEW)
    repo.save_state(NEW, _state(Status.PREDICTING))

    repo.save_meta(_meta(NEW, "Renamed"))

    analysis = repo.get(NEW)
    assert (analysis.meta.name, analysis.state.status) == ("Renamed", Status.PREDICTING)


def test_documents_round_trip(repo: AnalysisRepository) -> None:
    _create(repo, NEW)

    assert repo.get_job(NEW) is None
    assert repo.get_report(NEW) is None
    with pytest.raises(NotFoundError, match="not ready"):
        repo.get_result(NEW)

    repo.save_job(NEW, JobRef(backend="modal", call_id="fc-123"))
    repo.save_result(NEW, _result())
    repo.save_report(NEW, _report())

    job = repo.get_job(NEW)
    assert job is not None
    assert job.call_id == "fc-123"
    assert repo.get_result(NEW) == _result()
    assert repo.get_report(NEW) == _report()
    assert repo.get_state(NEW).status is Status.QUEUED


# ── artifacts ──────────────────────────────────────────────────────────────


def test_artifacts_round_trip(repo: AnalysisRepository, tmp_path: Path) -> None:
    _create(repo, NEW)
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"video")

    repo.put_artifacts(NEW, {"preview.mp4": clip, "keyframes/000.jpg": clip})
    repo.put_artifact_bytes(NEW, "keyframes/001.jpg", b"jpg")

    assert repo.read_artifact(NEW, "keyframes/001.jpg") == b"jpg"
    assert repo.local_artifact(NEW, "preview.mp4").read_bytes() == b"video"
    assert repo.list_artifacts(NEW, "keyframes") == ["000.jpg", "001.jpg"]
    assert (
        repo.download_artifact(NEW, "preview.mp4", tmp_path / "d.mp4").read_bytes()
        == b"video"
    )


def test_missing_artifacts_are_not_found(
    repo: AnalysisRepository, tmp_path: Path
) -> None:
    _create(repo, NEW)

    with pytest.raises(NotFoundError):
        repo.read_artifact(NEW, "strip.jpg")
    with pytest.raises(NotFoundError):
        repo.local_artifact(NEW, "strip.jpg")
    with pytest.raises(NotFoundError):
        repo.download_artifact(NEW, "strip.jpg", tmp_path / "x")


# ── repeat uploads ─────────────────────────────────────────────────────────


def test_fingerprint_finds_an_analysis_only_once_its_prediction_exists(
    repo: AnalysisRepository,
) -> None:
    _create(repo, NEW)
    repo.remember_fingerprint(FINGERPRINT, NEW)

    assert repo.find_fingerprint(FINGERPRINT) is None
    repo.put_artifact_bytes(NEW, PREDICTION, b"npz")
    assert repo.find_fingerprint(FINGERPRINT) == NEW
    assert repo.find_fingerprint("e" * 64) is None


def test_fingerprints_must_be_sha256_hex(repo: AnalysisRepository) -> None:
    with pytest.raises(ValueError, match="fingerprint"):
        repo.remember_fingerprint("../escape", NEW)


# ── comparisons ────────────────────────────────────────────────────────────


def test_comparisons_are_stored_per_ordered_pair(repo: AnalysisRepository) -> None:
    _create(repo, OLD, NEW)

    repo.save_comparison(_comparison(OLD, NEW))

    assert repo.get_comparison(OLD, NEW) == _comparison(OLD, NEW)
    assert repo.get_comparison(NEW, OLD) is None


# ── deletion ───────────────────────────────────────────────────────────────


def test_delete_removes_the_analysis_and_everything_pointing_at_it(
    repo: AnalysisRepository,
) -> None:
    _create(repo, OLD, MID, NEW)
    repo.put_artifact_bytes(NEW, PREDICTION, b"npz")
    repo.remember_fingerprint(FINGERPRINT, NEW)
    repo.save_comparison(_comparison(OLD, NEW))
    repo.save_comparison(_comparison(NEW, MID))
    repo.save_comparison(_comparison(OLD, MID))

    repo.delete(NEW)

    assert not repo.exists(NEW)
    assert [a.meta.id for a in repo.history()] == [MID, OLD]
    assert repo.find_fingerprint(FINGERPRINT) is None
    assert repo.get_comparison(OLD, NEW) is None
    assert repo.get_comparison(NEW, MID) is None
    assert repo.get_comparison(OLD, MID) is not None


def test_delete_keeps_a_fingerprint_that_moved_to_another_analysis(
    repo: AnalysisRepository,
) -> None:
    _create(repo, OLD, NEW)
    repo.put_artifact_bytes(OLD, PREDICTION, b"npz")
    repo.remember_fingerprint(FINGERPRINT, NEW)
    repo.remember_fingerprint(FINGERPRINT, OLD)

    repo.delete(NEW)

    assert repo.find_fingerprint(FINGERPRINT) == OLD


def test_deleting_an_unknown_analysis_is_not_found(repo: AnalysisRepository) -> None:
    with pytest.raises(NotFoundError):
        repo.delete(NEW)


def test_artifact_checks_and_batch_reads(repo: AnalysisRepository) -> None:
    _create(repo, NEW)
    repo.put_artifact_bytes(NEW, "keyframes/000.jpg", b"jpg")

    assert repo.has_artifact(NEW, "keyframes/000.jpg")
    assert not repo.has_artifact(NEW, "llm.mp4")
    assert repo.read_artifacts(NEW, ["keyframes/000.jpg", "llm.mp4"]) == {
        "keyframes/000.jpg": b"jpg",
        "llm.mp4": None,
    }


def test_discard_removes_what_a_job_wrote_after_deletion(
    repo: AnalysisRepository,
) -> None:
    _create(repo, OLD, NEW)
    repo.delete(NEW)
    repo.put_artifact_bytes(NEW, PREDICTION, b"late write")

    repo.discard(NEW)

    assert repo.store.list_dir("analyses") == [OLD]
