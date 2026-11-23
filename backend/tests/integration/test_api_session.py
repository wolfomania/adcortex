from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from adcortex import __version__
from adcortex.api.app import create_app
from adcortex.api.context import build_context
from adcortex.auth.service import SESSION_COOKIE
from adcortex.config import Settings
from adcortex.pipeline.services import create_services
from tests.integration.conftest import FakeDispatcher, seed

PASSWORD = "open sesame"


@pytest.fixture
def locked(tmp_path: Path) -> Iterator[TestClient]:
    settings = Settings(data_dir=tmp_path / "data", password=SecretStr(PASSWORD))
    context = build_context(
        settings, services=create_services(settings), dispatcher=FakeDispatcher()
    )
    with TestClient(create_app(settings, context=context)) as client:
        yield client


def _error(response_json: dict[str, object]) -> object:
    assert response_json["ok"] is False
    assert response_json["data"] is None
    error = response_json["error"]
    assert isinstance(error, dict)
    return error["code"]


def test_health_reports_the_version(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "data": {"status": "ok", "version": __version__},
        "error": None,
        "meta": None,
    }


def test_config_describes_limits_languages_and_backends(client: TestClient) -> None:
    data = client.get("/api/config").json()["data"]

    assert data["password_required"] is False
    assert data["authenticated"] is True
    assert data["brain_backend"] == "mock"
    assert data["llm"] == {"enabled": False, "model": None}
    assert data["limits"] == {
        "min_duration_s": 3.0,
        "max_duration_s": 180.0,
        "max_upload_mb": 500,
        "min_script_chars": 20,
        "max_script_chars": 3000,
    }
    languages = {item["code"]: item for item in data["languages"]}
    assert languages["en"] == {"code": "en", "name": "English", "full_support": True}
    assert languages["de"]["full_support"] is False
    assert "auto" not in languages


def test_without_a_password_login_is_a_formality(client: TestClient) -> None:
    response = client.post("/api/auth/login", json={"password": "anything"})

    assert response.json()["data"] == {"authenticated": True}
    assert SESSION_COOKIE not in response.cookies


def test_with_a_password_only_public_routes_answer(locked: TestClient) -> None:
    assert locked.get("/api/health").status_code == 200
    config = locked.get("/api/config").json()["data"]
    assert config["password_required"] is True
    assert config["authenticated"] is False

    for method, path in (
        ("GET", "/api/analyses"),
        ("POST", "/api/analyses"),
        ("POST", "/api/warmup"),
        ("GET", "/api/analyses/20261122-120000-abcdef/media"),
        ("POST", "/api/compare"),
        ("GET", "/api/docs"),
    ):
        response = locked.request(method, path)
        assert response.status_code == 401, path
        assert _error(response.json()) == "unauthorized"
        assert response.json()["error"]["message"] == "Log in to continue."


def test_logging_in_sets_a_session_cookie_that_opens_the_api(
    locked: TestClient,
) -> None:
    response = locked.post("/api/auth/login", json={"password": PASSWORD})

    assert response.status_code == 200
    assert response.json()["data"] == {"authenticated": True}
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{SESSION_COOKIE}=")
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "Max-Age=2592000" in cookie
    assert "Path=/" in cookie
    assert locked.get("/api/analyses").status_code == 200
    assert locked.get("/api/config").json()["data"]["authenticated"] is True


def test_cookies_are_secure_over_https(locked: TestClient) -> None:
    response = locked.post(
        "/api/auth/login",
        json={"password": PASSWORD},
        headers={"x-forwarded-proto": "https"},
    )

    assert "Secure" in response.headers["set-cookie"]


def test_logging_out_clears_the_cookie(locked: TestClient) -> None:
    locked.post("/api/auth/login", json={"password": PASSWORD})

    response = locked.post("/api/auth/logout")

    assert response.json()["data"] == {"authenticated": False}
    assert 'adcortex_session=""' in response.headers["set-cookie"]
    assert locked.get("/api/analyses").status_code == 401


def test_a_wrong_password_is_refused(locked: TestClient) -> None:
    response = locked.post("/api/auth/login", json={"password": "guess"})

    assert response.status_code == 401
    assert response.json()["error"] == {
        "code": "unauthorized",
        "message": "Wrong password.",
    }


def test_repeated_login_attempts_are_rate_limited(locked: TestClient) -> None:
    for _ in range(5):
        locked.post("/api/auth/login", json={"password": "guess"})

    response = locked.post("/api/auth/login", json={"password": PASSWORD})

    assert response.status_code == 429
    assert _error(response.json()) == "rate_limited"


def test_share_links_work_without_logging_in(locked: TestClient) -> None:
    locked.post("/api/auth/login", json={"password": PASSWORD})
    context = locked.app.state.context  # type: ignore[attr-defined]
    analysis = seed(context.repo)
    token = locked.post(f"/api/analyses/{analysis.meta.id}/share").json()["data"][
        "token"
    ]
    locked.post("/api/auth/logout")

    detail = locked.get(f"/api/shared/{token}")
    media = locked.get(f"/api/shared/{token}/media")

    assert detail.status_code == 200
    assert detail.json()["data"]["analysis"]["meta"]["id"] == analysis.meta.id
    assert media.status_code == 200
    assert locked.get(f"/api/analyses/{analysis.meta.id}").status_code == 401


def test_bodies_larger_than_the_limit_are_refused_before_reading(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/compare",
        content=b"{}",
        headers={"content-length": str(10 * 1024 * 1024)},
    )

    assert response.status_code == 413
    assert _error(response.json()) == "payload_too_large"


def test_unknown_routes_and_methods_answer_in_the_envelope(client: TestClient) -> None:
    missing = client.get("/api/nope")
    wrong_method = client.put("/api/health")

    assert missing.status_code == 404
    assert _error(missing.json()) == "not_found"
    assert wrong_method.status_code == 405
    assert _error(wrong_method.json()) == "invalid_input"


def test_invalid_bodies_name_the_field(client: TestClient) -> None:
    response = client.post("/api/auth/login", json={})

    assert response.status_code == 422
    assert response.json()["error"] == {
        "code": "invalid_input",
        "message": "password: Field required",
    }


def test_responses_carry_security_headers(client: TestClient) -> None:
    headers = client.get("/api/health").headers

    assert headers["x-content-type-options"] == "nosniff"
    assert headers["referrer-policy"] == "no-referrer"
    assert headers["x-frame-options"] == "DENY"
