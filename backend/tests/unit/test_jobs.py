from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from modal.types import InputStatus

from neuromarketing.config import Settings
from neuromarketing.domain.models import (
    AnalysisMeta,
    AnalysisState,
    Job,
    JobRef,
    LlmInfo,
    MediaKind,
    Progress,
    SourceFile,
    Status,
)
from neuromarketing.jobs.base import JobStatus
from neuromarketing.jobs.factory import create_dispatcher
from neuromarketing.jobs.local import LocalDispatcher
from neuromarketing.jobs.modal_jobs import ModalDispatcher
from neuromarketing.jobs.monitor import reconcile
from neuromarketing.storage.local import LocalFsStore
from neuromarketing.storage.repository import AnalysisRepository

ID = "20261122-090000-cccccc"
OTHER = "20261121-090000-bbbbbb"
NOW = datetime(2026, 11, 22, 12, 0, tzinfo=UTC)
JOB = Job(kind="analyze", analysis_id=ID)

# ── local dispatcher ───────────────────────────────────────────────────────


def test_local_jobs_run_in_the_background() -> None:
    started, release = threading.Event(), threading.Event()
    seen: list[Job] = []

    def runner(job: Job) -> None:
        seen.append(job)
        started.set()
        release.wait(5)

    dispatcher = LocalDispatcher(runner)
    ref = dispatcher.submit(JOB)
    assert started.wait(5)

    assert ref.backend == "local"
    assert dispatcher.status(ref) == "running"
    release.set()
    dispatcher.drain()
    assert dispatcher.status(ref) == "finished"
    assert seen == [JOB]


def test_local_job_that_raises_is_failed(caplog: pytest.LogCaptureFixture) -> None:
    def runner(job: Job) -> None:
        raise RuntimeError("boom")

    dispatcher = LocalDispatcher(runner)
    ref = dispatcher.submit(JOB)
    dispatcher.drain()

    assert dispatcher.status(ref) == "failed"
    assert "boom" in caplog.text


def test_local_jobs_from_an_earlier_process_are_failed() -> None:
    dispatcher = LocalDispatcher(lambda job: None)

    assert dispatcher.status(JobRef(backend="local", call_id="gone")) == "failed"


def test_cancelled_local_job_never_runs() -> None:
    release = threading.Event()
    seen: list[Job] = []

    def runner(job: Job) -> None:
        seen.append(job)
        release.wait(5)

    dispatcher = LocalDispatcher(runner, max_workers=1)
    dispatcher.submit(JOB)
    queued = dispatcher.submit(Job(kind="report", analysis_id=OTHER))
    dispatcher.cancel(queued)
    release.set()
    dispatcher.drain()

    assert seen == [JOB]


# ── Modal dispatcher ───────────────────────────────────────────────────────


@dataclass
class FakeInput:
    function_call_id: str
    status: InputStatus
    children: list[FakeInput] = field(default_factory=list)


@dataclass
class FakeCall:
    object_id: str
    status: InputStatus = InputStatus.PENDING
    cancelled: bool = False
    graph: list[FakeInput] | None = None

    def get_call_graph(self) -> list[FakeInput]:
        if self.graph is not None:
            return self.graph
        # Modal returns the graph from its root: the web request that spawned
        # the job, which finished long before the job did.
        gpu = FakeInput("fc-gpu", InputStatus.PENDING)
        job = FakeInput(self.object_id, self.status, [gpu])
        return [FakeInput("fc-web", InputStatus.SUCCESS, [job])]

    def cancel(self, terminate_containers: bool = False) -> None:
        self.cancelled = True


@dataclass
class FakeFunction:
    spawned: list[tuple[Any, ...]] = field(default_factory=list)

    def spawn(self, *args: Any) -> FakeCall:
        self.spawned.append(args)
        return FakeCall("fc-1")


def _modal(
    calls: dict[str, FakeCall] | None = None,
) -> tuple[ModalDispatcher, FakeFunction]:
    function = FakeFunction()
    known = calls or {}

    def lookup_call(call_id: str) -> FakeCall:
        if call_id not in known:
            raise LookupError(call_id)
        return known[call_id]

    dispatcher = ModalDispatcher(
        "nm-app",
        "orchestrate",
        lookup_function=lambda app, name: function,
        lookup_call=lookup_call,
    )
    return dispatcher, function


def test_modal_jobs_spawn_the_orchestrator_with_a_plain_payload() -> None:
    dispatcher, function = _modal()

    ref = dispatcher.submit(Job(kind="compare", analysis_id=ID, other_id=OTHER))

    assert function.spawned == [
        ({"kind": "compare", "analysis_id": ID, "other_id": OTHER},),
    ]
    assert (ref.backend, ref.kind, ref.call_id) == ("modal", "compare", "fc-1")


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (InputStatus.PENDING, "running"),
        (InputStatus.SUCCESS, "finished"),
        (InputStatus.FAILURE, "failed"),
        (InputStatus.INIT_FAILURE, "failed"),
        (InputStatus.TERMINATED, "failed"),
        (InputStatus.TIMEOUT, "failed"),
    ],
)
def test_modal_job_status_follows_the_call_graph(
    status: InputStatus, expected: JobStatus
) -> None:
    dispatcher, _ = _modal({"fc-1": FakeCall("fc-1", status)})

    assert dispatcher.status(JobRef(backend="modal", call_id="fc-1")) == expected


def test_modal_job_status_is_unknown_when_the_graph_lacks_the_job() -> None:
    web = FakeInput("fc-web", InputStatus.SUCCESS)
    dispatcher, _ = _modal({"fc-1": FakeCall("fc-1", graph=[web])})

    assert dispatcher.status(JobRef(backend="modal", call_id="fc-1")) == "unknown"


def test_modal_job_status_is_unknown_when_the_call_cannot_be_found() -> None:
    dispatcher, _ = _modal()

    assert dispatcher.status(JobRef(backend="modal", call_id="fc-404")) == "unknown"
    assert dispatcher.status(JobRef(backend="modal")) == "unknown"


def test_modal_cancel_is_best_effort() -> None:
    call = FakeCall("fc-1")
    dispatcher, _ = _modal({"fc-1": call})

    dispatcher.cancel(JobRef(backend="modal", call_id="fc-1"))
    dispatcher.cancel(JobRef(backend="modal", call_id="fc-404"))

    assert call.cancelled


def test_factory_picks_the_runtime_dispatcher() -> None:
    assert isinstance(
        create_dispatcher(Settings(), runner=lambda job: None), LocalDispatcher
    )
    assert isinstance(
        create_dispatcher(Settings(runtime="modal"), runner=None), ModalDispatcher
    )


# ── reconciling dead jobs ──────────────────────────────────────────────────


class StubDispatcher:
    def __init__(self, status: JobStatus, on_status: Any = None) -> None:
        self._status = status
        self._on_status = on_status
        self.checked = 0

    def submit(self, job: Job) -> JobRef:  # pragma: no cover
        raise NotImplementedError

    def status(self, ref: JobRef) -> JobStatus:
        self.checked += 1
        if self._on_status:
            self._on_status()
        return self._status

    def cancel(self, ref: JobRef) -> None:  # pragma: no cover
        raise NotImplementedError


@pytest.fixture
def repo(tmp_path: Path) -> AnalysisRepository:
    repository = AnalysisRepository(LocalFsStore(tmp_path))
    repository.create(
        AnalysisMeta(
            id=ID,
            name="Clip",
            kind=MediaKind.VIDEO,
            created_at=NOW,
            source=SourceFile(
                filename="a.mp4", extension=".mp4", size_bytes=1, sha256="0" * 64
            ),
        ),
        AnalysisState(status=Status.PREDICTING, updated_at=NOW),
    )
    return repository


def _job(kind: str = "analyze", age: timedelta = timedelta(minutes=5)) -> JobRef:
    return JobRef.model_validate(
        {
            "backend": "modal",
            "kind": kind,
            "call_id": "fc-1",
            "dispatched_at": NOW - age,
        }
    )


def test_running_jobs_are_left_alone(repo: AnalysisRepository) -> None:
    repo.save_job(ID, _job())

    state = reconcile(repo, StubDispatcher("running"), ID, now=NOW)

    assert state.status is Status.PREDICTING


@pytest.mark.parametrize("status", ["failed", "finished"])
def test_a_dead_analysis_job_fails_the_analysis(
    repo: AnalysisRepository, status: JobStatus
) -> None:
    repo.save_job(ID, _job())

    state = reconcile(repo, StubDispatcher(status), ID, now=NOW)

    assert state.status is Status.FAILED
    assert state.error is not None
    assert "stopped unexpectedly" in state.error
    assert repo.get_state(ID) == state


def test_a_dead_report_job_keeps_the_metrics(repo: AnalysisRepository) -> None:
    repo.save_state(
        ID, AnalysisState(status=Status.INTERPRETING, llm=LlmInfo(model="m"))
    )
    repo.save_job(ID, _job("report"))

    state = reconcile(repo, StubDispatcher("failed"), ID, now=NOW)

    assert state.status is Status.COMPLETED
    assert state.llm is not None
    assert state.llm.status == "failed"
    assert state.llm.model == "m"


def test_a_job_that_finishes_during_the_check_is_not_failed(
    repo: AnalysisRepository,
) -> None:
    repo.save_job(ID, _job())

    def finish() -> None:
        repo.save_state(ID, AnalysisState(status=Status.COMPLETED))

    state = reconcile(repo, StubDispatcher("finished", on_status=finish), ID, now=NOW)

    assert state.status is Status.COMPLETED


def test_fresh_progress_skips_the_liveness_check(repo: AnalysisRepository) -> None:
    repo.save_job(ID, _job())
    dispatcher = StubDispatcher("failed")
    fresh = Progress(status=Status.PREDICTING, updated_at=NOW - timedelta(seconds=5))

    state = reconcile(repo, dispatcher, ID, now=NOW, progress=fresh)

    assert state.status is Status.PREDICTING
    assert dispatcher.checked == 0


@pytest.mark.parametrize(
    ("age", "expected"),
    [(timedelta(minutes=1), Status.PREDICTING), (timedelta(hours=3), Status.FAILED)],
)
def test_unknown_jobs_fail_only_when_long_overdue(
    repo: AnalysisRepository, age: timedelta, expected: Status
) -> None:
    repo.save_job(ID, _job(age=age))

    assert reconcile(repo, StubDispatcher("unknown"), ID, now=NOW).status is expected


@pytest.mark.parametrize(
    ("age", "expected"),
    [(timedelta(seconds=10), Status.QUEUED), (timedelta(minutes=5), Status.FAILED)],
)
def test_analyses_that_were_never_dispatched_fail_after_a_grace_period(
    repo: AnalysisRepository, age: timedelta, expected: Status
) -> None:
    repo.save_state(ID, AnalysisState(status=Status.QUEUED, updated_at=NOW - age))

    assert reconcile(repo, StubDispatcher("running"), ID, now=NOW).status is expected


def test_terminal_analyses_are_not_checked(repo: AnalysisRepository) -> None:
    repo.save_state(ID, AnalysisState(status=Status.COMPLETED))
    dispatcher = StubDispatcher("failed")

    assert reconcile(repo, dispatcher, ID, now=NOW).status is Status.COMPLETED
    assert dispatcher.checked == 0
