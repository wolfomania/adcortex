"""Failure paths: broken dependencies, odd requests, and the exported schema."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from neuromarketing.api.app import create_app
from neuromarketing.api.context import AppContext
from neuromarketing.api.errors import UNEXPECTED, describe_validation
from neuromarketing.api.schemas import api_json_schema
from neuromarketing.domain.models import Job, Progress, Status, utcnow
from neuromarketing.storage.local import MemoryProgressStore
from neuromarketing.storage.repository import AnalysisRepository
from tests.integration.conftest import FakeDispatcher, seed


class BrokenProgress(MemoryProgressStore):
    def get(self, analysis_id: str) -> Progress | None:
        raise ConnectionError("progress store unavailable")


def test_unexpected_errors_become_a_generic_500(
    context: AppContext,
    repo: AnalysisRepository,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def explode(**_: object) -> list[object]:
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(repo, "history", explode)
    client = TestClient(create_app(context=context), raise_server_exceptions=False)

    response = client.get("/api/analyses")

    assert response.status_code == 500
    assert response.json()["error"] == {"code": "internal", "message": UNEXPECTED}
    assert "disk on fire" in caplog.text


def test_status_survives_a_progress_store_outage(
    context: AppContext, repo: AnalysisRepository
) -> None:
    broken = replace(
        context, services=replace(context.services, progress=BrokenProgress())
    )
    analysis = seed(repo, status=Status.PREPARING, updated=utcnow())

    with TestClient(create_app(context=broken)) as client:
        response = client.get(f"/api/analyses/{analysis.meta.id}/status")

    assert response.status_code == 200
    assert response.json()["data"]["progress"] is None


def test_streamed_bodies_are_cut_off_at_the_limit(client: TestClient) -> None:
    def chunks() -> Iterator[bytes]:
        for _ in range(100):
            yield b" " * 1024

    response = client.post(
        "/api/compare", content=chunks(), headers={"content-type": "application/json"}
    )

    assert response.status_code == 413
    assert response.json()["error"] == {
        "code": "payload_too_large",
        "message": "The request body is too large.",
    }


def test_cors_is_off_unless_origins_are_configured(
    context: AppContext, client: TestClient
) -> None:
    origin = "http://localhost:5173"
    preflight = {
        "origin": origin,
        "access-control-request-method": "POST",
    }
    settings = context.settings.model_copy(update={"cors_origins": [origin]})
    allowed = TestClient(create_app(context=replace(context, settings=settings)))

    assert (
        "access-control-allow-origin"
        not in client.options("/api/analyses", headers=preflight).headers
    )
    response = allowed.options("/api/analyses", headers=preflight)
    assert response.headers["access-control-allow-origin"] == origin
    assert response.headers["access-control-allow-credentials"] == "true"


def test_a_failed_cancel_does_not_block_deleting(
    client: TestClient, repo: AnalysisRepository, dispatcher: FakeDispatcher
) -> None:
    analysis = seed(repo, status=Status.PREDICTING, updated=utcnow())
    job = Job(kind="analyze", analysis_id=analysis.meta.id)
    repo.save_job(analysis.meta.id, dispatcher.submit(job))

    def refuse(_: object) -> None:
        raise ConnectionError("Modal is down")

    dispatcher.cancel = refuse  # type: ignore[method-assign,assignment]

    assert client.delete(f"/api/analyses/{analysis.meta.id}").status_code == 200
    assert not repo.exists(analysis.meta.id)


def test_any_cached_version_matches_a_wildcard(
    client: TestClient, repo: AnalysisRepository
) -> None:
    analysis = seed(repo)

    response = client.get(
        f"/api/analyses/{analysis.meta.id}/strip", headers={"if-none-match": "*"}
    )

    assert response.status_code == 304


def test_files_without_an_extension_are_refused(
    client: TestClient, tmp_path: Path
) -> None:
    unnamed = tmp_path / "README"
    unnamed.write_bytes(b"data")

    with unnamed.open("rb") as handle:
        response = client.post(
            "/api/analyses",
            data={"kind": "video"},
            files={"file": ("README", handle, "application/octet-stream")},
        )

    assert response.status_code == 422
    assert response.json()["error"]["message"].startswith(
        "'README' files are not supported."
    )


def test_a_completed_analysis_without_its_result_still_loads(
    client: TestClient, repo: AnalysisRepository
) -> None:
    analysis = seed(repo)
    repo.store.remove(f"analyses/{analysis.meta.id}/result.json")

    response = client.get(f"/api/analyses/{analysis.meta.id}")

    assert response.status_code == 200
    assert response.json()["data"]["result"] is None


def test_validation_messages_fall_back_to_a_sentence() -> None:
    assert describe_validation([]) == "The request is invalid."
    assert describe_validation([{"loc": ("body",), "msg": "Field required"}]) == (
        "Field required"
    )


def test_the_exported_schema_holds_every_api_model() -> None:
    defs = api_json_schema()["$defs"]

    for name in ("AppConfig", "Analysis", "AnalysisDetail", "AnalysisResult"):
        assert name in defs
    assert defs["ApiError"]["properties"]["code"]["enum"][0] == "invalid_input"
