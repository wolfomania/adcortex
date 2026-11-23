from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from modal import exception as modal_errors
from pydantic import ValidationError

from adcortex.analysis.baseline import Baseline
from adcortex.brain.base import BrainPrediction, BrainRequest
from adcortex.brain.client import BrainJob, InProcessBrain
from adcortex.brain.remote import ModalBrainClient
from adcortex.config import Settings
from adcortex.domain.errors import NotFoundError, PipelineError
from adcortex.domain.models import Status, Word
from adcortex.pipeline.services import create_brain_client, create_services
from adcortex.pipeline.worker import run_brain_job
from adcortex.storage.local import LocalFsStore, MemoryProgressStore
from adcortex.storage.repository import AUDIO, AnalysisRepository

ID = "20261122-120000-abcdef"
JOB = BrainJob(
    analysis_id=ID,
    artifact=AUDIO,
    kind="audio",
    duration_s=4.0,
    language="en",
    script="Hello there",
)


def _prediction() -> BrainPrediction:
    return BrainPrediction(
        preds=np.ones((4, 8), dtype=np.float32),
        times=np.arange(4, dtype=np.float64),
        words=(Word(text="Hello", start=0.1, end=0.5),),
        language="en",
        model="stub",
    )


class StubModel:
    name = "stub"

    def __init__(self) -> None:
        self.requests: list[BrainRequest] = []
        self.inputs: list[bytes] = []

    def warmup(self) -> None:
        return None

    def predict(self, request: BrainRequest) -> BrainPrediction:
        self.requests.append(request)
        self.inputs.append(request.media.read_bytes())
        return _prediction()


# ── jobs and the in-process client ─────────────────────────────────────────


@pytest.mark.parametrize(
    ("field", "value"),
    [("artifact", "meta.json"), ("artifact", "../audio.wav"), ("analysis_id", "x")],
)
def test_brain_jobs_name_only_model_inputs(field: str, value: str) -> None:
    payload = {**JOB.model_dump(mode="json"), field: value}

    with pytest.raises(ValidationError):
        BrainJob.model_validate(payload)


def test_in_process_brain_runs_the_model_on_the_local_copy(tmp_path: Path) -> None:
    model = StubModel()
    brain = InProcessBrain(model)
    media = tmp_path / AUDIO
    media.write_bytes(b"RIFF")

    prediction = brain.predict(JOB, media)

    assert (brain.name, brain.remote) == ("stub", False)
    assert model.requests == [
        BrainRequest(
            media=media,
            kind="audio",
            duration_s=4.0,
            language="en",
            script="Hello there",
        )
    ]
    assert prediction.model == "stub"


# ── the Modal client ───────────────────────────────────────────────────────


@dataclass
class FakeMethod:
    result: Any = None
    error: BaseException | None = None
    calls: list[tuple[Any, ...]] = field(default_factory=list)

    def remote(self, *args: Any) -> Any:
        self.calls.append(args)
        if self.error is not None:
            raise self.error
        return self.result

    def spawn(self, *args: Any) -> None:
        self.calls.append(args)


class FakeWorker:
    def __init__(self, predict: FakeMethod) -> None:
        self.predict = predict
        self.warmup = FakeMethod()


def _client(
    method: FakeMethod,
) -> tuple[ModalBrainClient, list[tuple[str, str]], FakeWorker]:
    worker = FakeWorker(method)
    looked_up: list[tuple[str, str]] = []

    def lookup(app_name: str, class_name: str) -> Any:
        looked_up.append((app_name, class_name))
        return lambda: worker

    return ModalBrainClient("adcortex-app", lookup=lookup), looked_up, worker


def test_modal_brain_sends_the_job_and_decodes_the_prediction(
    tmp_path: Path,
) -> None:
    method = FakeMethod(result=_prediction().to_npz())
    client, looked_up, _ = _client(method)

    prediction = client.predict(JOB, tmp_path / "unused.wav")

    assert (client.name, client.remote) == ("tribev2", True)
    assert looked_up == [("adcortex-app", "BrainWorker")]
    assert method.calls == [(JOB.model_dump(mode="json"),)]
    assert prediction.words == _prediction().words
    np.testing.assert_array_equal(prediction.preds, _prediction().preds)


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (modal_errors.FunctionTimeoutError("timed out"), "took too long"),
        (modal_errors.NotFoundError("no such app"), "make deploy"),
        (modal_errors.RemoteError("container crashed"), "GPU worker failed"),
    ],
)
def test_modal_failures_become_messages_for_the_person(
    tmp_path: Path, error: BaseException, message: str
) -> None:
    client, _, _ = _client(FakeMethod(error=error))

    with pytest.raises(PipelineError, match=message):
        client.predict(JOB, tmp_path / "unused.wav")


def test_user_facing_errors_from_the_worker_pass_through(tmp_path: Path) -> None:
    error = PipelineError("No audio could be extracted from this clip.")
    client, _, _ = _client(FakeMethod(error=error))

    with pytest.raises(PipelineError) as caught:
        client.predict(JOB, tmp_path / "unused.wav")

    assert caught.value is error


def test_modal_warmup_starts_a_worker_without_waiting() -> None:
    client, _, worker = _client(FakeMethod())

    client.warmup()

    assert worker.warmup.calls == [()]


# ── the GPU worker's side ──────────────────────────────────────────────────


@pytest.fixture
def repo(tmp_path: Path) -> AnalysisRepository:
    return AnalysisRepository(LocalFsStore(tmp_path / "store"))


def test_worker_fetches_its_input_and_reports_progress(
    repo: AnalysisRepository,
) -> None:
    repo.put_artifact_bytes(ID, AUDIO, b"RIFF audio")
    progress = MemoryProgressStore()
    model = StubModel()

    data = run_brain_job(model, repo, progress, JOB.model_dump(mode="json"))

    assert BrainPrediction.from_npz(data).words == _prediction().words
    assert model.inputs == [b"RIFF audio"]
    assert model.requests[0].script == "Hello there"
    assert not model.requests[0].media.exists()
    current = progress.get(ID)
    assert current is not None
    assert current.status is Status.PREDICTING


def test_worker_rejects_malformed_jobs(repo: AnalysisRepository) -> None:
    payload = {**JOB.model_dump(mode="json"), "artifact": "../../etc/passwd"}

    with pytest.raises(ValidationError):
        run_brain_job(StubModel(), repo, MemoryProgressStore(), payload)


def test_worker_reports_a_missing_input(repo: AnalysisRepository) -> None:
    with pytest.raises(NotFoundError):
        run_brain_job(
            StubModel(), repo, MemoryProgressStore(), JOB.model_dump(mode="json")
        )


# ── wiring ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("settings", "expected"),
    [
        (Settings(), InProcessBrain),
        (Settings(runtime="modal", brain_backend="mock"), InProcessBrain),
        (Settings(runtime="modal", brain_backend="tribe"), ModalBrainClient),
    ],
)
def test_the_brain_runs_in_process_unless_tribe_runs_on_modal(
    settings: Settings, expected: type
) -> None:
    assert isinstance(create_brain_client(settings), expected)


def test_local_services_use_the_data_folder(tmp_path: Path) -> None:
    services = create_services(Settings(data_dir=tmp_path))
    services.repo.put_artifact_bytes(ID, AUDIO, b"x")

    assert (tmp_path / "analyses" / ID / AUDIO).read_bytes() == b"x"
    assert services.brain.name == "mock"
    assert services.llm is None


def test_only_tribe_output_is_scored_against_the_reference_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reference = Baseline.build(
        version="test", description="d", systems={}, hook=(), n_clips=1
    )
    monkeypatch.setattr("adcortex.pipeline.services.load_baseline", lambda: reference)

    mock = create_services(Settings(data_dir=tmp_path, brain_backend="mock"))
    replay = create_services(Settings(data_dir=tmp_path, brain_backend="replay"))

    assert mock.baseline is None
    assert replay.baseline is reference
