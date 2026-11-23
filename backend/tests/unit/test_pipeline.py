"""End-to-end jobs on synthetic clips with the mock brain and fake LLMs."""

from __future__ import annotations

import hashlib
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic_ai import BinaryContent
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models.function import AgentInfo, FunctionModel

from adcortex.analysis.atlas import N_VERTICES, load_atlas
from adcortex.analysis.library import MIN_LIBRARY
from adcortex.analysis.systems import load_systems
from adcortex.brain.base import BrainPrediction
from adcortex.brain.client import BrainJob, InProcessBrain
from adcortex.brain.mock import MockBrain
from adcortex.config import Settings
from adcortex.domain.errors import NotFoundError, PipelineError
from adcortex.domain.ids import new_analysis_id
from adcortex.domain.models import (
    Analysis,
    AnalysisMeta,
    AnalysisState,
    AnalysisSummary,
    Job,
    JobKind,
    LanguageInfo,
    LlmInfo,
    MediaKind,
    Progress,
    Scene,
    SourceFile,
    Status,
)
from adcortex.llm.client import LlmConfig, MediaLevel
from adcortex.media.speech import synthesize_speech
from adcortex.pipeline.interpret import report_inputs
from adcortex.pipeline.runner import (
    GENERIC_FAILURE,
    compare_key,
    make_runner,
    run_job,
)
from adcortex.pipeline.services import Services
from adcortex.storage.local import LocalFsStore, MemoryProgressStore
from adcortex.storage.repository import (
    AUDIO,
    FRAMES,
    LLM_VIDEO,
    PREDICTION,
    PREVIEW_AUDIO,
    PREVIEW_VIDEO,
    SCRIPT,
    STRIP,
    AnalysisRepository,
    keyframe_name,
    source_name,
)
from tests.llm_fakes import comparison_args, replying, report_args, user_parts

pytestmark = pytest.mark.ffmpeg

CATALOG = load_systems()
VISUAL = {s.id for s in CATALOG.systems if s.visual}
CREATED = datetime(2026, 11, 22, 12, 0, tzinfo=UTC)
SCRIPT_TEXT = (
    "Fresh coffee, roasted this morning and delivered before you wake up. "
    "Taste the difference."
)

# ── test doubles ───────────────────────────────────────────────────────────


class SpyBrain:
    """The mock brain, recording each job; can fail or act mid-prediction."""

    remote = False

    def __init__(
        self,
        *,
        error: Exception | None = None,
        during: Callable[[], None] | None = None,
    ) -> None:
        self.name = "mock"
        self.jobs: list[BrainJob] = []
        self._brain = InProcessBrain(MockBrain(CATALOG))
        self._error = error
        self._during = during

    def warmup(self) -> None:
        return None

    def predict(self, job: BrainJob, media: Path) -> BrainPrediction:
        self.jobs.append(job)
        if self._during is not None:
            self._during()
        if self._error is not None:
            raise self._error
        return self._brain.predict(job, media)


class SpyProgress(MemoryProgressStore):
    def __init__(self) -> None:
        super().__init__()
        self.history: list[tuple[str, Progress]] = []

    def put(self, analysis_id: str, progress: Progress) -> None:
        self.history.append((analysis_id, progress))
        super().put(analysis_id, progress)


def _speak(text: str, language: str, dst: Path) -> None:
    """Text-to-speech stand-in: a tone lasting one second per 15 characters."""
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=300:duration={len(text) / 15:.2f}",
            "-c:a",
            "libmp3lame",
            str(dst),
        ],
        check=True,
    )


def _llm(
    respond: Callable[[list[ModelMessage], AgentInfo], ModelResponse],
    settings: Settings,
) -> LlmConfig:
    return LlmConfig.from_model(FunctionModel(respond), "test-model", settings)


def _failing(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    raise RuntimeError("provider exploded")


# ── fixtures and helpers ───────────────────────────────────────────────────


@pytest.fixture
def brain() -> SpyBrain:
    return SpyBrain()


@pytest.fixture
def services(tmp_path: Path, brain: SpyBrain) -> Services:
    return Services(
        settings=Settings(data_dir=tmp_path),
        repo=AnalysisRepository(LocalFsStore(tmp_path / "store")),
        progress=SpyProgress(),
        brain=brain,
        llm=None,
        catalog=CATALOG,
        atlas=load_atlas(),
        baseline=None,
        speak=_speak,
    )


def _create(
    services: Services, kind: MediaKind, source: SourceFile, language: str
) -> str:
    meta = AnalysisMeta(
        id=new_analysis_id(),
        name="Test clip",
        kind=kind,
        created_at=CREATED,
        source=source,
        language=language,
    )
    services.repo.create(meta, AnalysisState(status=Status.QUEUED))
    return meta.id


def _source(name: str, data: bytes) -> SourceFile:
    return SourceFile(
        filename=name,
        extension=Path(name).suffix,
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
    )


def _upload(
    services: Services, path: Path, kind: MediaKind, *, language: str = "auto"
) -> str:
    """What the web tier does on upload: create the analysis, store the file."""
    data = path.read_bytes()
    analysis_id = _create(services, kind, _source(path.name, data), language)
    services.repo.put_artifact_bytes(analysis_id, source_name(path.suffix), data)
    return analysis_id


def _upload_script(
    services: Services, text: str = SCRIPT_TEXT, *, language: str = "auto"
) -> str:
    data = text.encode()
    analysis_id = _create(
        services, MediaKind.TEXT, _source("script.txt", data), language
    )
    services.repo.put_artifact_bytes(analysis_id, SCRIPT, data)
    return analysis_id


def _run(
    services: Services,
    analysis_id: str,
    kind: JobKind = "analyze",
    other_id: str | None = None,
) -> Analysis:
    make_runner(services)(Job(kind=kind, analysis_id=analysis_id, other_id=other_id))
    return services.repo.get(analysis_id)


def _completed(analysis: Analysis) -> AnalysisState:
    assert analysis.state.status is Status.COMPLETED, analysis.state.error
    return analysis.state


# ── full analyses ──────────────────────────────────────────────────────────


def test_video_analysis_runs_end_to_end(services: Services, media_dir: Path) -> None:
    analysis_id = _upload(services, media_dir / "three_scenes.mp4", MediaKind.VIDEO)

    state = _completed(_run(services, analysis_id))

    repo = services.repo
    result = repo.get_result(analysis_id)
    assert state.media is not None
    assert state.media.duration_s == pytest.approx(6.0, abs=0.1)
    assert state.llm == LlmInfo(status="skipped")
    assert state.summary is not None
    assert state.summary.top_systems
    assert {"prepare", "predict", "analyze", "total"} <= state.timings.keys()
    assert [round(s.start) for s in result.scenes] == [0, 2, 4]
    assert [s.keyframe for s in result.scenes] == [keyframe_name(i) for i in range(3)]
    assert result.strip == STRIP
    assert len(result.envelope) == pytest.approx(60, abs=2)
    assert result.frames is not None
    frames = repo.read_artifact(analysis_id, FRAMES)
    assert len(frames) == result.frames.n_frames * N_VERTICES
    for name in (PREVIEW_VIDEO, STRIP, PREDICTION, keyframe_name(2)):
        assert repo.has_artifact(analysis_id, name), name
    assert not repo.has_artifact(analysis_id, LLM_VIDEO)
    assert services.progress.get(analysis_id) is None


def test_progress_only_moves_forward(services: Services, media_dir: Path) -> None:
    analysis_id = _upload(services, media_dir / "three_scenes.mp4", MediaKind.VIDEO)

    _run(services, analysis_id)

    assert isinstance(services.progress, SpyProgress)
    updates = [p for key, p in services.progress.history if key == analysis_id]
    statuses = [p.status for p in updates]
    fractions = [p.fraction for p in updates]
    assert statuses[0] is Status.PREPARING
    assert {Status.PREDICTING, Status.ANALYZING} <= set(statuses)
    assert fractions == sorted(fractions)


def test_audio_analysis_skips_visual_systems(
    services: Services, brain: SpyBrain, media_dir: Path
) -> None:
    analysis_id = _upload(services, media_dir / "tone.wav", MediaKind.AUDIO)

    _completed(_run(services, analysis_id))

    result = services.repo.get_result(analysis_id)
    assert [(s.start, s.end) for s in result.scenes] == [(0.0, 5.0)]
    assert all(not s.applicable for s in result.systems if s.id in VISUAL)
    assert result.strip is None
    assert services.repo.has_artifact(analysis_id, PREVIEW_AUDIO)
    assert (brain.jobs[0].artifact, brain.jobs[0].kind) == (AUDIO, "audio")


def test_scripts_are_read_aloud_and_analyzed_as_speech(
    services: Services, brain: SpyBrain
) -> None:
    analysis_id = _upload_script(services)

    _completed(_run(services, analysis_id))

    job = brain.jobs[0]
    assert (job.kind, job.language, job.script) == ("audio", "en", SCRIPT_TEXT)
    result = services.repo.get_result(analysis_id)
    assert result.language == LanguageInfo(
        requested="auto", detected="en", full_support=True
    )
    assert result.transcript[0].text == "Fresh"


def test_non_english_speech_carries_the_reliability_caveat(
    services: Services, brain: SpyBrain
) -> None:
    analysis_id = _upload_script(services, language="de")

    _completed(_run(services, analysis_id))

    assert brain.jobs[0].language == "de"
    language = services.repo.get_result(analysis_id).language
    assert (language.detected, language.full_support) == ("de", False)


# ── failures ───────────────────────────────────────────────────────────────


def test_scripts_in_languages_without_a_voice_fail_clearly(
    services: Services, brain: SpyBrain
) -> None:
    services = replace(services, speak=synthesize_speech)
    analysis_id = _upload_script(services, language="fa")

    state = _run(services, analysis_id).state

    assert state.status is Status.FAILED
    assert state.error is not None
    assert "Persian" in state.error
    assert brain.jobs == []


def test_scripts_that_read_too_short_fail_with_advice(services: Services) -> None:
    analysis_id = _upload_script(services, "Buy coffee now, today!")

    state = _run(services, analysis_id).state

    assert state.status is Status.FAILED
    assert state.error is not None
    assert "lasts 1.5 s" in state.error
    assert "Add more text" in state.error


def test_unreadable_uploads_fail_while_preparing(
    services: Services, media_dir: Path
) -> None:
    analysis_id = _upload(services, media_dir / "junk.mp4", MediaKind.VIDEO)

    state = _run(services, analysis_id).state

    assert state.status is Status.FAILED
    assert state.message == "Failed while preparing the media."
    assert state.error not in (None, GENERIC_FAILURE)
    assert services.progress.get(analysis_id) is None


def test_clips_over_the_length_limit_fail(services: Services, media_dir: Path) -> None:
    services = replace(services, settings=Settings(max_duration_s=4))
    analysis_id = _upload(services, media_dir / "three_scenes.mp4", MediaKind.VIDEO)

    state = _run(services, analysis_id).state

    assert state.status is Status.FAILED
    assert state.error is not None
    assert "too long" in state.error


def test_unexpected_errors_are_logged_and_reported_generically(
    services: Services, media_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    services = replace(services, brain=SpyBrain(error=RuntimeError("CUDA OOM")))
    analysis_id = _upload(services, media_dir / "tone.wav", MediaKind.AUDIO)

    state = _run(services, analysis_id).state

    assert state.status is Status.FAILED
    assert state.message == "Failed while predicting the brain response."
    assert state.error == GENERIC_FAILURE
    assert "CUDA OOM" in caplog.text


def test_user_facing_brain_errors_are_shown_as_they_are(
    services: Services, media_dir: Path
) -> None:
    error = PipelineError("No audio could be extracted from this clip.")
    services = replace(services, brain=SpyBrain(error=error))
    analysis_id = _upload(services, media_dir / "tone.wav", MediaKind.AUDIO)

    state = _run(services, analysis_id).state

    assert state.error == str(error)


@pytest.mark.parametrize("error", [None, RuntimeError("worker lost")])
def test_deleting_an_analysis_mid_run_leaves_nothing_behind(
    services: Services, media_dir: Path, error: Exception | None
) -> None:
    holder: list[str] = []
    brain = SpyBrain(error=error, during=lambda: services.repo.delete(holder[0]))
    services = replace(services, brain=brain)
    holder.append(_upload(services, media_dir / "tone.wav", MediaKind.AUDIO))

    run_job(services, Job(kind="analyze", analysis_id=holder[0]))

    assert services.repo.store.list_dir("analyses") == []
    assert services.progress.get(holder[0]) is None


def test_jobs_for_unknown_analyses_do_nothing(services: Services) -> None:
    kinds: tuple[JobKind, ...] = ("analyze", "report")
    for kind in kinds:
        run_job(services, Job(kind=kind, analysis_id="20261122-120000-000000"))

    assert services.repo.store.list_dir("analyses") == []


def test_progress_outages_do_not_fail_jobs(
    services: Services, media_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    class BrokenProgress(MemoryProgressStore):
        def put(self, analysis_id: str, progress: Progress) -> None:
            raise ConnectionError("progress store unavailable")

    services = replace(services, progress=BrokenProgress())
    analysis_id = _upload(services, media_dir / "tone.wav", MediaKind.AUDIO)

    _completed(_run(services, analysis_id))

    assert "Could not publish progress" in caplog.text


def test_comparison_jobs_need_a_second_analysis(
    services: Services, caplog: pytest.LogCaptureFixture
) -> None:
    run_job(services, Job(kind="compare", analysis_id="20261122-120000-000000"))

    assert "without a second analysis" in caplog.text


# ── repeat uploads ─────────────────────────────────────────────────────────


def test_identical_uploads_reuse_the_prediction(
    services: Services, brain: SpyBrain, media_dir: Path
) -> None:
    first = _upload(services, media_dir / "tone.wav", MediaKind.AUDIO)
    _run(services, first)
    second = _upload(services, media_dir / "tone.wav", MediaKind.AUDIO)

    state = _completed(_run(services, second))

    repo = services.repo
    assert len(brain.jobs) == 1
    assert state.reused_from == first
    assert repo.read_artifact(second, PREDICTION) == repo.read_artifact(
        first, PREDICTION
    )
    assert repo.get_result(second).systems == repo.get_result(first).systems


def test_a_retry_reuses_its_own_prediction(
    services: Services, brain: SpyBrain, media_dir: Path
) -> None:
    analysis_id = _upload(services, media_dir / "tone.wav", MediaKind.AUDIO)
    _run(services, analysis_id)

    state = _completed(_run(services, analysis_id))

    assert len(brain.jobs) == 1
    assert state.reused_from is None


def test_a_prediction_deleted_after_the_lookup_is_predicted_again(
    services: Services,
    brain: SpyBrain,
    media_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _upload(services, media_dir / "tone.wav", MediaKind.AUDIO)
    _run(services, first)
    second = _upload(services, media_dir / "tone.wav", MediaKind.AUDIO)
    read = services.repo.read_artifact

    def vanished(analysis_id: str, name: str) -> bytes:
        if name == PREDICTION:
            raise NotFoundError("File not found.")
        return read(analysis_id, name)

    monkeypatch.setattr(services.repo, "read_artifact", vanished)

    state = _completed(_run(services, second))

    assert len(brain.jobs) == 2
    assert state.reused_from is None


def test_another_language_is_predicted_again(
    services: Services, brain: SpyBrain, media_dir: Path
) -> None:
    _run(services, _upload(services, media_dir / "tone.wav", MediaKind.AUDIO))
    second = _upload(services, media_dir / "tone.wav", MediaKind.AUDIO, language="de")

    _completed(_run(services, second))

    assert [job.language for job in brain.jobs] == ["auto", "de"]


# ── the library of past analyses ───────────────────────────────────────────


def test_percentiles_against_the_library_once_it_is_large_enough(
    services: Services, media_dir: Path
) -> None:
    for i in range(MIN_LIBRARY):
        _create_completed(services, f"past-{i}".encode(), value=float(i) - 4.5)
    analysis_id = _upload(services, media_dir / "tone.wav", MediaKind.AUDIO)

    _completed(_run(services, analysis_id))

    systems = services.repo.get_result(analysis_id).systems
    assert all(s.library_percentile is not None for s in systems if s.applicable)
    assert all(s.library_percentile is None for s in systems if not s.applicable)


def _create_completed(services: Services, data: bytes, *, value: float) -> None:
    analysis_id = _create(services, MediaKind.AUDIO, _source("a.wav", data), "auto")
    summary = AnalysisSummary(
        duration_s=5.0, system_means=dict.fromkeys(CATALOG.ids, value)
    )
    services.repo.save_state(
        analysis_id, AnalysisState(status=Status.COMPLETED, summary=summary)
    )


# ── reports ────────────────────────────────────────────────────────────────


def _with_report(
    services: Services, headline: str = "Faces land at 5 s."
) -> tuple[Services, list[list[ModelMessage]]]:
    seen: list[list[ModelMessage]] = []

    def args(_: int) -> dict[str, Any]:
        return {**report_args(t=1.0), "headline": headline}

    config = _llm(replying(args, seen), services.settings)
    return replace(services, llm=config), seen


def test_reports_are_written_from_the_video_and_the_metrics(
    services: Services, media_dir: Path
) -> None:
    services, seen = _with_report(services)
    analysis_id = _upload(services, media_dir / "three_scenes.mp4", MediaKind.VIDEO)

    state = _completed(_run(services, analysis_id))

    assert state.llm == LlmInfo(model="test-model", status="ok", input_mode="video")
    report = services.repo.get_report(analysis_id)
    assert report is not None
    assert state.summary is not None
    assert state.summary.headline == report.report.headline == "Faces land at 5 s."
    assert "report" in state.timings
    videos = [
        p
        for p in user_parts(seen[0])
        if isinstance(p, BinaryContent) and p.media_type == "video/mp4"
    ]
    assert videos
    assert videos[0].data == services.repo.read_artifact(analysis_id, LLM_VIDEO)


def test_audio_reports_hear_the_audio(services: Services, media_dir: Path) -> None:
    services, seen = _with_report(services)
    analysis_id = _upload(services, media_dir / "tone.wav", MediaKind.AUDIO)

    state = _completed(_run(services, analysis_id))

    assert state.llm is not None
    assert state.llm.input_mode == "audio"
    sounds = [p for p in user_parts(seen[0]) if isinstance(p, BinaryContent)]
    assert sounds[0].media_type == "audio/wav"


def test_a_failed_report_keeps_the_metrics(services: Services, media_dir: Path) -> None:
    services = replace(services, llm=_llm(_failing, services.settings))
    analysis_id = _upload(services, media_dir / "tone.wav", MediaKind.AUDIO)

    state = _completed(_run(services, analysis_id))

    assert state.llm == LlmInfo(
        model="test-model", status="failed", error="Writing the report failed."
    )
    assert services.repo.get_report(analysis_id) is None
    assert services.repo.get_result(analysis_id).systems


def test_regenerating_a_report_replaces_it(services: Services, media_dir: Path) -> None:
    first, _ = _with_report(services, headline="First take.")
    analysis_id = _upload(first, media_dir / "tone.wav", MediaKind.AUDIO)
    _run(first, analysis_id)
    second, _ = _with_report(services, headline="Second take.")

    state = _completed(_run(second, analysis_id, kind="report"))

    report = services.repo.get_report(analysis_id)
    assert report is not None
    assert report.report.headline == "Second take."
    assert state.summary is not None
    assert state.summary.headline == "Second take."
    assert {"prepare", "report", "total"} <= state.timings.keys()


def test_regenerating_makes_the_video_proxy_an_older_analysis_lacks(
    services: Services, media_dir: Path
) -> None:
    analysis_id = _upload(services, media_dir / "three_scenes.mp4", MediaKind.VIDEO)
    _run(services, analysis_id)
    with_llm, _ = _with_report(services)

    state = _completed(_run(with_llm, analysis_id, kind="report"))

    assert state.llm is not None
    assert state.llm.input_mode == "video"
    assert services.repo.has_artifact(analysis_id, LLM_VIDEO)


def test_failed_report_rewrites_keep_the_analysis_completed(
    services: Services, media_dir: Path
) -> None:
    analysis_id = _upload(services, media_dir / "three_scenes.mp4", MediaKind.VIDEO)
    _run(services, analysis_id)
    services.repo.store.remove(f"analyses/{analysis_id}/{PREVIEW_VIDEO}")
    with_llm, _ = _with_report(services)

    state = _completed(_run(with_llm, analysis_id, kind="report"))

    assert state.llm == LlmInfo(
        model="test-model", status="failed", error="File not found."
    )


def test_deleting_during_a_report_rewrite_leaves_nothing_behind(
    services: Services, media_dir: Path
) -> None:
    analysis_id = _upload(services, media_dir / "tone.wav", MediaKind.AUDIO)
    _run(services, analysis_id)
    answer = replying(lambda _: report_args(t=1.0))

    def delete_then_answer(
        messages: list[ModelMessage], info: AgentInfo
    ) -> ModelResponse:
        services.repo.delete(analysis_id)
        return answer(messages, info)

    with_llm = replace(services, llm=_llm(delete_then_answer, services.settings))

    run_job(with_llm, Job(kind="report", analysis_id=analysis_id))

    assert services.repo.store.list_dir("analyses") == []


def test_a_report_rewrite_for_a_deleted_analysis_never_calls_the_model(
    services: Services, media_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    analysis_id = _upload(services, media_dir / "tone.wav", MediaKind.AUDIO)
    _run(services, analysis_id)
    with_llm, seen = _with_report(services)
    read = services.repo.read_artifacts

    def delete_then_read(
        analysis_id: str, names: Sequence[str]
    ) -> dict[str, bytes | None]:
        services.repo.delete(analysis_id)
        return read(analysis_id, names)

    monkeypatch.setattr(services.repo, "read_artifacts", delete_then_read)

    run_job(with_llm, Job(kind="report", analysis_id=analysis_id))

    assert seen == []
    assert services.repo.store.list_dir("analyses") == []


# ── comparisons ────────────────────────────────────────────────────────────


def _two_analyses(services: Services, media_dir: Path) -> tuple[str, str]:
    a = _upload(services, media_dir / "tone.wav", MediaKind.AUDIO)
    b = _upload(services, media_dir / "tone.m4a", MediaKind.AUDIO)
    _run(services, a)
    _run(services, b)
    return a, b


def test_comparisons_are_stored(services: Services, media_dir: Path) -> None:
    a, b = _two_analyses(services, media_dir)
    services = replace(services, llm=_llm(replying(comparison_args), services.settings))

    run_job(services, Job(kind="compare", analysis_id=a, other_id=b))

    stored = services.repo.get_comparison(a, b)
    assert stored is not None
    assert stored.report.headline == "B hooks faster."
    assert services.progress.get(compare_key(a, b)) is None


@pytest.mark.parametrize(
    ("llm", "message"),
    [(True, "Writing the comparison failed."), (False, "No report model")],
)
def test_failed_comparisons_say_why(
    services: Services, media_dir: Path, llm: bool, message: str
) -> None:
    a, b = _two_analyses(services, media_dir)
    config = _llm(_failing, services.settings) if llm else None
    services = replace(services, llm=config)

    run_job(services, Job(kind="compare", analysis_id=a, other_id=b))

    progress = services.progress.get(compare_key(a, b))
    assert progress is not None
    assert progress.status is Status.FAILED
    assert message in progress.message
    assert services.repo.get_comparison(a, b) is None


def test_comparisons_of_deleted_analyses_fail(
    services: Services, media_dir: Path
) -> None:
    a, b = _two_analyses(services, media_dir)
    services.repo.delete(b)
    services = replace(services, llm=_llm(replying(comparison_args), services.settings))

    run_job(services, Job(kind="compare", analysis_id=a, other_id=b))

    progress = services.progress.get(compare_key(a, b))
    assert progress is not None
    assert progress.message == "Analysis not found."


@pytest.mark.parametrize(
    ("kind", "level", "expected"),
    [
        (MediaKind.VIDEO, "video", [LLM_VIDEO, "keyframes/000.jpg"]),
        (MediaKind.VIDEO, "keyframes", ["keyframes/000.jpg"]),
        (MediaKind.VIDEO, "text", []),
        (MediaKind.AUDIO, "video", [AUDIO]),
        (MediaKind.TEXT, "keyframes", []),
    ],
)
def test_report_rewrites_fetch_only_the_allowed_media(
    kind: MediaKind, level: MediaLevel, expected: list[str]
) -> None:
    scenes = (Scene(index=0, start=0.0, end=2.0, keyframe="keyframes/000.jpg"),)

    assert report_inputs(kind, scenes, level) == expected
