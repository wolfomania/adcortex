from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from neuromarketing.api.app import create_app
from neuromarketing.api.compare import STALE_AFTER
from neuromarketing.api.context import AppContext
from neuromarketing.domain.models import (
    ComparisonReport,
    Job,
    Progress,
    Status,
    StoredComparison,
    utcnow,
)
from neuromarketing.pipeline.runner import compare_key
from neuromarketing.storage.repository import AnalysisRepository
from tests.integration.conftest import START, FakeDispatcher, seed, with_llm
from tests.llm_fakes import comparison_args


@pytest.fixture
def llm_client(context: AppContext) -> Iterator[TestClient]:
    enabled = with_llm(context)
    with TestClient(create_app(enabled.settings, context=enabled)) as client:
        yield client


@pytest.fixture
def pair(repo: AnalysisRepository) -> tuple[str, str]:
    a = seed(repo, name="A", created=START).meta.id
    b = seed(repo, name="B", created=START + timedelta(minutes=1)).meta.id
    return a, b


def _state(client: TestClient, a: str, b: str) -> dict[str, object]:
    body = client.get(f"/api/compare/{a}/{b}").json()
    assert body["ok"] is True
    data = body["data"]
    assert isinstance(data, dict)
    return data


def test_comparisons_start_once_and_report_progress(
    llm_client: TestClient, pair: tuple[str, str], dispatcher: FakeDispatcher
) -> None:
    a, b = pair

    first = llm_client.post("/api/compare", json={"a_id": a, "b_id": b})
    second = llm_client.post("/api/compare", json={"a_id": a, "b_id": b})

    assert first.status_code == 202
    assert first.json()["data"] == {
        "status": "running",
        "comparison": None,
        "error": None,
    }
    assert second.status_code == 202
    assert dispatcher.jobs == [Job(kind="compare", analysis_id=a, other_id=b)]
    assert _state(llm_client, a, b)["status"] == "running"


def test_stored_comparisons_are_returned_at_once(
    llm_client: TestClient,
    pair: tuple[str, str],
    repo: AnalysisRepository,
    dispatcher: FakeDispatcher,
) -> None:
    a, b = pair
    stored = StoredComparison(
        a_id=a,
        b_id=b,
        model="test-model",
        report=ComparisonReport.model_validate(comparison_args()),
    )
    repo.save_comparison(stored)

    response = llm_client.post("/api/compare", json={"a_id": a, "b_id": b})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "completed"
    assert data["comparison"]["report"]["headline"] == "B hooks faster."
    assert dispatcher.jobs == []


def test_failed_comparisons_say_why_and_can_start_again(
    llm_client: TestClient,
    pair: tuple[str, str],
    context: AppContext,
    dispatcher: FakeDispatcher,
) -> None:
    a, b = pair
    failed = Progress(status=Status.FAILED, message="Writing the comparison failed.")
    context.progress.put(compare_key(a, b), failed)

    assert _state(llm_client, a, b) == {
        "status": "failed",
        "comparison": None,
        "error": "Writing the comparison failed.",
    }
    assert (
        llm_client.post("/api/compare", json={"a_id": a, "b_id": b}).status_code == 202
    )
    assert len(dispatcher.jobs) == 1


def test_comparisons_that_stopped_reporting_are_failed(
    llm_client: TestClient, pair: tuple[str, str], context: AppContext
) -> None:
    a, b = pair
    stale = Progress(
        status=Status.INTERPRETING, updated_at=utcnow() - STALE_AFTER - timedelta(1)
    )
    context.progress.put(compare_key(a, b), stale)

    state = _state(llm_client, a, b)

    assert state["status"] == "failed"
    assert "stopped" in str(state["error"])


def test_nothing_compared_yet_is_none(
    client: TestClient, pair: tuple[str, str]
) -> None:
    assert _state(client, *pair)["status"] == "none"


def test_comparisons_need_two_completed_analyses(
    llm_client: TestClient, repo: AnalysisRepository, pair: tuple[str, str]
) -> None:
    a, _ = pair
    running = seed(repo, status=Status.PREDICTING, updated=utcnow()).meta.id

    same = llm_client.post("/api/compare", json={"a_id": a, "b_id": a})
    unfinished = llm_client.post("/api/compare", json={"a_id": a, "b_id": running})
    missing = llm_client.post(
        "/api/compare", json={"a_id": a, "b_id": "20261122-120000-abcdef"}
    )
    malformed = llm_client.post("/api/compare", json={"a_id": a, "b_id": "../etc"})

    assert same.status_code == 422
    assert unfinished.status_code == 409
    assert missing.status_code == 404
    assert malformed.status_code == 422


def test_comparisons_need_a_report_model(
    client: TestClient, pair: tuple[str, str]
) -> None:
    a, b = pair

    response = client.post("/api/compare", json={"a_id": a, "b_id": b})

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "unavailable"


def test_a_comparison_that_cannot_be_dispatched_is_unavailable(
    llm_client: TestClient,
    pair: tuple[str, str],
    dispatcher: FakeDispatcher,
) -> None:
    a, b = pair
    dispatcher.error = ConnectionError("Modal is down")

    response = llm_client.post("/api/compare", json={"a_id": a, "b_id": b})

    assert response.status_code == 503
    assert _state(llm_client, a, b)["status"] == "none"


def test_comparison_lookups_check_both_analyses(
    client: TestClient, pair: tuple[str, str]
) -> None:
    a, _ = pair

    response = client.get(f"/api/compare/{a}/20261122-120000-abcdef")

    assert response.status_code == 404
