from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from neuromarketing.api.app import create_app
from neuromarketing.api.context import AppContext
from neuromarketing.api.warmup import WarmupGate
from neuromarketing.domain.models import (
    Job,
    MediaKind,
    Progress,
    Status,
    utcnow,
)
from neuromarketing.jobs.monitor import DEAD_JOB
from neuromarketing.storage.repository import AnalysisRepository
from tests.integration.conftest import START, FakeDispatcher, seed, with_llm

MISSING = "20261122-120000-abcdef"


def _data(response_json: dict[str, object]) -> object:
    assert response_json["ok"] is True, response_json
    return response_json["data"]


# ── history ────────────────────────────────────────────────────────────────


def test_history_lists_newest_first_in_pages(
    client: TestClient, repo: AnalysisRepository
) -> None:
    ids = [
        seed(repo, created=START + timedelta(minutes=i), name=f"Spot {i}").meta.id
        for i in range(3)
    ]

    first = client.get("/api/analyses", params={"limit": 2}).json()
    second = client.get(
        "/api/analyses", params={"limit": 2, "before": first["meta"]["next_before"]}
    ).json()

    assert [a["meta"]["id"] for a in first["data"]] == [ids[2], ids[1]]
    assert first["meta"]["next_before"] == ids[1]
    assert [a["meta"]["id"] for a in second["data"]] == [ids[0]]
    assert second["meta"]["next_before"] is None
    assert first["data"][0]["progress"] is None


def test_history_rejects_bad_paging(client: TestClient) -> None:
    assert client.get("/api/analyses", params={"limit": 0}).status_code == 422
    assert client.get("/api/analyses", params={"limit": 101}).status_code == 422
    assert client.get("/api/analyses", params={"before": "../x"}).status_code == 422


# ── one analysis ───────────────────────────────────────────────────────────


def test_detail_includes_the_result_and_report(
    client: TestClient, repo: AnalysisRepository
) -> None:
    analysis = seed(repo)

    data = _data(client.get(f"/api/analyses/{analysis.meta.id}").json())

    assert isinstance(data, dict)
    assert data["analysis"]["meta"]["name"] == "Spring spot"
    assert data["result"]["duration_s"] == 6.0
    assert data["report"] is None


def test_detail_of_a_running_analysis_has_progress_but_no_result(
    client: TestClient, repo: AnalysisRepository, context: AppContext
) -> None:
    analysis = seed(repo, status=Status.PREDICTING, updated=utcnow())
    progress = Progress(status=Status.PREDICTING, message="Predicting", fraction=0.4)
    context.progress.put(analysis.meta.id, progress)

    data = _data(client.get(f"/api/analyses/{analysis.meta.id}").json())

    assert isinstance(data, dict)
    assert data["result"] is None
    assert data["analysis"]["progress"]["fraction"] == 0.4


def test_unknown_and_malformed_ids_are_not_found(client: TestClient) -> None:
    for path in (f"/api/analyses/{MISSING}", "/api/analyses/not-an-id"):
        response = client.get(path)
        assert response.status_code == 404
        assert response.json()["error"]["message"] == "Analysis not found."


def test_status_fails_analyses_whose_job_died(
    client: TestClient,
    repo: AnalysisRepository,
    context: AppContext,
    dispatcher: FakeDispatcher,
) -> None:
    analysis = seed(repo, status=Status.PREDICTING, updated=utcnow())
    repo.save_job(
        analysis.meta.id,
        dispatcher.submit(Job(kind="analyze", analysis_id=analysis.meta.id)),
    )
    dispatcher.job_status = "failed"

    data = _data(client.get(f"/api/analyses/{analysis.meta.id}/status").json())

    assert isinstance(data, dict)
    assert data["state"]["status"] == "failed"
    assert data["state"]["error"] == DEAD_JOB
    assert data["progress"] is None


def test_status_keeps_running_analyses_running(
    client: TestClient, repo: AnalysisRepository, dispatcher: FakeDispatcher
) -> None:
    analysis = seed(repo, status=Status.PREPARING, updated=utcnow())
    repo.save_job(
        analysis.meta.id,
        dispatcher.submit(Job(kind="analyze", analysis_id=analysis.meta.id)),
    )

    data = _data(client.get(f"/api/analyses/{analysis.meta.id}/status").json())

    assert isinstance(data, dict)
    assert data["state"]["status"] == "preparing"


def test_renaming_changes_only_the_name(
    client: TestClient, repo: AnalysisRepository
) -> None:
    analysis = seed(repo)

    response = client.patch(
        f"/api/analyses/{analysis.meta.id}", json={"name": "  Final   cut  "}
    )

    data = _data(response.json())
    assert isinstance(data, dict)
    assert data["meta"]["name"] == "Final cut"
    assert repo.get(analysis.meta.id).meta.name == "Final cut"
    assert repo.get(analysis.meta.id).state == analysis.state


def test_names_must_not_be_blank_or_too_long(
    client: TestClient, repo: AnalysisRepository
) -> None:
    analysis = seed(repo)
    path = f"/api/analyses/{analysis.meta.id}"

    assert client.patch(path, json={"name": " \n "}).status_code == 422
    assert client.patch(path, json={"name": "x" * 121}).status_code == 422


def test_deleting_cancels_the_job_and_removes_everything(
    client: TestClient,
    repo: AnalysisRepository,
    context: AppContext,
    dispatcher: FakeDispatcher,
) -> None:
    analysis = seed(repo, status=Status.PREDICTING, updated=utcnow())
    ref = dispatcher.submit(Job(kind="analyze", analysis_id=analysis.meta.id))
    repo.save_job(analysis.meta.id, ref)
    context.progress.put(analysis.meta.id, Progress(status=Status.PREDICTING))

    response = client.delete(f"/api/analyses/{analysis.meta.id}")

    assert response.status_code == 200
    assert response.json()["data"] is None
    assert dispatcher.cancelled == [ref]
    assert not repo.exists(analysis.meta.id)
    assert context.progress.get(analysis.meta.id) is None
    assert client.delete(f"/api/analyses/{analysis.meta.id}").status_code == 404


def test_deleting_a_finished_analysis_cancels_nothing(
    client: TestClient, repo: AnalysisRepository, dispatcher: FakeDispatcher
) -> None:
    analysis = seed(repo)
    repo.save_job(
        analysis.meta.id,
        dispatcher.submit(Job(kind="analyze", analysis_id=analysis.meta.id)),
    )

    client.delete(f"/api/analyses/{analysis.meta.id}")

    assert dispatcher.cancelled == []


# ── retry and report ───────────────────────────────────────────────────────


def test_failed_analyses_can_be_retried(
    client: TestClient, repo: AnalysisRepository, dispatcher: FakeDispatcher
) -> None:
    analysis = seed(repo, status=Status.FAILED)
    old = dispatcher.submit(Job(kind="analyze", analysis_id=analysis.meta.id))
    repo.save_job(analysis.meta.id, old)

    response = client.post(f"/api/analyses/{analysis.meta.id}/retry")

    assert response.status_code == 202
    data = _data(response.json())
    assert isinstance(data, dict)
    assert data["state"]["status"] == "queued"
    assert data["state"]["error"] is None
    assert dispatcher.jobs[-1] == Job(kind="analyze", analysis_id=analysis.meta.id)
    job = repo.get_job(analysis.meta.id)
    assert job is not None
    assert job.call_id != old.call_id


def test_only_failed_analyses_can_be_retried(
    client: TestClient, repo: AnalysisRepository
) -> None:
    analysis = seed(repo)

    response = client.post(f"/api/analyses/{analysis.meta.id}/retry")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


def test_a_retry_that_cannot_be_dispatched_fails_again(
    client: TestClient, repo: AnalysisRepository, dispatcher: FakeDispatcher
) -> None:
    analysis = seed(repo, status=Status.FAILED)
    dispatcher.error = ConnectionError("Modal is down")

    response = client.post(f"/api/analyses/{analysis.meta.id}/retry")

    data = _data(response.json())
    assert isinstance(data, dict)
    assert data["state"]["status"] == "failed"
    assert "could not be started" in data["state"]["error"]
    assert repo.get_state(analysis.meta.id).status is Status.FAILED


def test_reports_need_a_report_model(
    client: TestClient, repo: AnalysisRepository
) -> None:
    analysis = seed(repo)

    response = client.post(f"/api/analyses/{analysis.meta.id}/report")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "unavailable"


def _client(settings_context: AppContext) -> TestClient:
    return TestClient(create_app(settings_context.settings, context=settings_context))


def test_reports_are_rewritten_for_completed_analyses(
    repo: AnalysisRepository, context: AppContext, dispatcher: FakeDispatcher
) -> None:
    analysis = seed(repo)
    client = _client(with_llm(context))

    response = client.post(f"/api/analyses/{analysis.meta.id}/report")

    assert response.status_code == 202
    data = _data(response.json())
    assert isinstance(data, dict)
    assert data["state"]["status"] == "interpreting"
    assert data["state"]["summary"]["response_index"] == 55.0
    assert dispatcher.jobs == [Job(kind="report", analysis_id=analysis.meta.id)]
    job = repo.get_job(analysis.meta.id)
    assert job is not None
    assert job.kind == "report"
    detail = _data(client.get(f"/api/analyses/{analysis.meta.id}").json())
    assert isinstance(detail, dict)
    assert detail["result"] is not None


def test_reports_wait_for_the_analysis_to_complete(
    repo: AnalysisRepository, context: AppContext
) -> None:
    analysis = seed(repo, status=Status.FAILED)

    response = _client(with_llm(context)).post(
        f"/api/analyses/{analysis.meta.id}/report"
    )

    assert response.status_code == 409


def test_a_report_that_cannot_be_dispatched_leaves_the_analysis_as_it_was(
    repo: AnalysisRepository, context: AppContext, dispatcher: FakeDispatcher
) -> None:
    analysis = seed(repo)
    dispatcher.error = ConnectionError("Modal is down")

    response = _client(with_llm(context)).post(
        f"/api/analyses/{analysis.meta.id}/report"
    )

    assert response.status_code == 503
    assert repo.get_state(analysis.meta.id).status is Status.COMPLETED


# ── share and warm-up ──────────────────────────────────────────────────────


def test_completed_analyses_can_be_shared(
    client: TestClient, repo: AnalysisRepository
) -> None:
    analysis = seed(repo)

    data = _data(client.post(f"/api/analyses/{analysis.meta.id}/share").json())

    assert isinstance(data, dict)
    assert data["path"] == f"/s/{data['token']}"
    shared = _data(client.get(f"/api/shared/{data['token']}").json())
    assert isinstance(shared, dict)
    assert shared["analysis"]["meta"]["id"] == analysis.meta.id
    assert shared["result"] is not None


def test_running_analyses_cannot_be_shared(
    client: TestClient, repo: AnalysisRepository
) -> None:
    analysis = seed(repo, status=Status.ANALYZING, updated=utcnow())

    assert client.post(f"/api/analyses/{analysis.meta.id}/share").status_code == 409


def test_invalid_share_tokens_are_refused(client: TestClient) -> None:
    response = client.get("/api/shared/forged.token")

    assert response.status_code == 401
    assert response.json()["error"]["message"] == (
        "This share link is invalid or has expired."
    )


def test_share_links_stop_working_once_the_analysis_is_deleted(
    client: TestClient, repo: AnalysisRepository
) -> None:
    analysis = seed(repo)
    token = _data(client.post(f"/api/analyses/{analysis.meta.id}/share").json())
    assert isinstance(token, dict)
    client.delete(f"/api/analyses/{analysis.meta.id}")

    assert client.get(f"/api/shared/{token['token']}").status_code == 404


def test_warmup_is_a_no_op_without_a_gpu_worker(client: TestClient) -> None:
    assert _data(client.post("/api/warmup").json()) == {"warming": False}


class RemoteBrain:
    name = "tribev2"
    remote = True

    def __init__(self, error: Exception | None = None) -> None:
        self.warmups = 0
        self.error = error

    def warmup(self) -> None:
        self.warmups += 1
        if self.error is not None:
            raise self.error

    def predict(self, job: object, media: Path) -> object:
        raise NotImplementedError


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_warmup_starts_the_gpu_worker_once_per_cooldown() -> None:
    brain = RemoteBrain()
    clock = Clock()
    gate = WarmupGate(brain, cooldown_s=240.0, clock=clock)

    assert gate.start()
    assert gate.start()
    assert brain.warmups == 1
    clock.now += 241
    assert gate.start()
    assert brain.warmups == 2


def test_a_failed_warmup_is_retried_on_the_next_call() -> None:
    brain = RemoteBrain(error=ConnectionError("Modal is down"))
    gate = WarmupGate(brain, cooldown_s=240.0)

    assert not gate.start()
    assert not gate.start()
    assert brain.warmups == 2


def test_upload_kind_is_validated(client: TestClient) -> None:
    response = client.post("/api/analyses", data={"kind": "hologram"})

    assert response.status_code == 422
    assert response.json()["error"]["message"].startswith("kind:")
    assert MediaKind.VIDEO.value in response.json()["error"]["message"]
