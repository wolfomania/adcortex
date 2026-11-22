"""The built single-page app, served next to the API."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from neuromarketing.api.app import create_app
from neuromarketing.api.context import build_context
from neuromarketing.api.frontend import resolve_static
from neuromarketing.config import Settings
from neuromarketing.domain.errors import ConfigurationError
from neuromarketing.pipeline.services import create_services
from tests.integration.conftest import FakeDispatcher

INDEX = b"<!doctype html><title>Neuro</title>"


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    root = tmp_path / "dist"
    (root / "assets").mkdir(parents=True)
    (root / "brain").mkdir()
    (root / "index.html").write_bytes(INDEX)
    (root / "assets" / "app-3f2a1b.js").write_text("console.log(1)")
    (root / "brain" / "mesh.bin").write_bytes(b"\x01\x02")
    (tmp_path / "secret.txt").write_text("secret")
    return root


@pytest.fixture
def site(tmp_path: Path, dist: Path) -> Iterator[TestClient]:
    settings = Settings(data_dir=tmp_path / "data", frontend_dist=dist)
    context = build_context(
        settings, services=create_services(settings), dispatcher=FakeDispatcher()
    )
    with TestClient(create_app(settings, context=context)) as client:
        yield client


def test_app_routes_get_the_index_page(site: TestClient) -> None:
    for path in ("/", "/history", "/a/20261122-120000-abcdef", "/s/token"):
        response = site.get(path)
        assert response.status_code == 200, path
        assert response.content == INDEX
        assert response.headers["cache-control"] == "no-cache"
        assert "default-src 'self'" in response.headers["content-security-policy"]


def test_hashed_assets_are_cached_for_good(site: TestClient) -> None:
    response = site.get("/assets/app-3f2a1b.js")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/javascript")
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"


def test_other_files_are_revalidated(site: TestClient) -> None:
    response = site.get("/brain/mesh.bin")
    again = site.get(
        "/brain/mesh.bin", headers={"if-none-match": response.headers["etag"]}
    )

    assert response.content == b"\x01\x02"
    assert response.headers["cache-control"] == "no-cache"
    assert again.status_code == 304


def test_missing_assets_are_not_answered_with_the_page(site: TestClient) -> None:
    assert site.get("/assets/app-old.js").status_code == 404
    assert site.get("/favicon.ico").content == INDEX


def test_unknown_api_routes_stay_json(site: TestClient) -> None:
    response = site.get("/api/nope")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_paths_outside_the_build_are_never_served(dist: Path) -> None:
    root = dist.resolve()

    assert resolve_static(root, "../secret.txt") is None
    assert resolve_static(root, "assets/../../secret.txt") is None
    assert resolve_static(root, "assets") is None
    assert resolve_static(root, "assets/app-3f2a1b.js") == root / "assets/app-3f2a1b.js"


def test_a_build_without_an_index_page_is_rejected(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "data", frontend_dist=tmp_path)
    context = build_context(
        settings, services=create_services(settings), dispatcher=FakeDispatcher()
    )

    with pytest.raises(ConfigurationError, match="pnpm build"):
        create_app(settings, context=context)
