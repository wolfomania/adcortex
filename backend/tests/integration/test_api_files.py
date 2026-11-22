from __future__ import annotations

import gzip

import pytest
from fastapi.testclient import TestClient

from neuromarketing.domain.models import MediaKind, Status, utcnow
from neuromarketing.storage.repository import AnalysisRepository
from tests.integration.conftest import FRAMES_BYTES, VIDEO_BYTES, seed

IMMUTABLE = "private, max-age=31536000, immutable"


def _share(client: TestClient, analysis_id: str) -> str:
    response = client.post(f"/api/analyses/{analysis_id}/share")
    token = response.json()["data"]["token"]
    assert isinstance(token, str)
    return token


@pytest.fixture
def analysis_id(repo: AnalysisRepository) -> str:
    return seed(repo).meta.id


def test_video_streams_with_ranges_and_caching(
    client: TestClient, analysis_id: str
) -> None:
    full = client.get(f"/api/analyses/{analysis_id}/media")
    part = client.get(
        f"/api/analyses/{analysis_id}/media", headers={"range": "bytes=10-19"}
    )

    assert full.status_code == 200
    assert full.content == VIDEO_BYTES
    assert full.headers["content-type"] == "video/mp4"
    assert full.headers["cache-control"] == IMMUTABLE
    assert full.headers["accept-ranges"] == "bytes"
    assert part.status_code == 206
    assert part.content == VIDEO_BYTES[10:20]
    assert part.headers["content-range"] == f"bytes 10-19/{len(VIDEO_BYTES)}"


def test_unchanged_files_are_not_sent_again(
    client: TestClient, analysis_id: str
) -> None:
    etag = client.get(f"/api/analyses/{analysis_id}/media").headers["etag"]

    response = client.get(
        f"/api/analyses/{analysis_id}/media", headers={"if-none-match": etag}
    )

    assert response.status_code == 304
    assert response.content == b""
    assert response.headers["etag"] == etag
    assert response.headers["cache-control"] == IMMUTABLE


def test_audio_analyses_serve_their_audio_preview(
    client: TestClient, repo: AnalysisRepository
) -> None:
    analysis = seed(repo, kind=MediaKind.AUDIO)

    response = client.get(f"/api/analyses/{analysis.meta.id}/media")

    assert response.headers["content-type"] == "audio/mp4"
    assert client.get(f"/api/analyses/{analysis.meta.id}/strip").status_code == 404


def test_brain_frames_are_compressed_in_transit(
    client: TestClient, analysis_id: str
) -> None:
    response = client.get(
        f"/api/analyses/{analysis_id}/frames", headers={"accept-encoding": "gzip"}
    )

    assert response.status_code == 200
    assert response.content == FRAMES_BYTES
    assert response.headers["content-type"] == "application/octet-stream"
    assert response.headers["etag"].startswith('W/"')


def test_large_frames_are_gzipped(client: TestClient, repo: AnalysisRepository) -> None:
    analysis = seed(repo)
    frames = bytes([128]) * 20_000
    repo.put_artifact_bytes(analysis.meta.id, "frames.bin", frames)

    with client.stream(
        "GET",
        f"/api/analyses/{analysis.meta.id}/frames",
        headers={"accept-encoding": "gzip"},
    ) as response:
        raw = b"".join(response.iter_raw())

    assert response.headers["content-encoding"] == "gzip"
    assert gzip.decompress(raw) == frames


def test_keyframes_and_strip_are_jpegs(client: TestClient, analysis_id: str) -> None:
    keyframe = client.get(f"/api/analyses/{analysis_id}/keyframes/0")
    strip = client.get(f"/api/analyses/{analysis_id}/strip")

    assert keyframe.headers["content-type"] == "image/jpeg"
    assert keyframe.content == b"\xff\xd8keyframe"
    assert strip.content == b"\xff\xd8strip"
    assert client.get(f"/api/analyses/{analysis_id}/keyframes/7").status_code == 404
    assert client.get(f"/api/analyses/{analysis_id}/keyframes/-1").status_code == 422


def test_files_of_unfinished_analyses_are_not_cached(
    client: TestClient, repo: AnalysisRepository
) -> None:
    analysis = seed(repo, status=Status.FAILED)

    response = client.get(f"/api/analyses/{analysis.meta.id}/media")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"


def test_missing_files_and_analyses_are_not_found(
    client: TestClient, repo: AnalysisRepository
) -> None:
    bare = seed(repo, status=Status.PREPARING, updated=utcnow(), artifacts=False)

    assert client.get(f"/api/analyses/{bare.meta.id}/media").status_code == 404
    assert client.get(f"/api/analyses/{bare.meta.id}/frames").status_code == 404
    missing = client.get("/api/analyses/20261122-120000-abcdef/media")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"


def test_shared_links_serve_the_same_files(
    client: TestClient, analysis_id: str
) -> None:
    token = _share(client, analysis_id)

    for suffix in ("media", "frames", "keyframes/0", "strip"):
        shared = client.get(f"/api/shared/{token}/{suffix}")
        direct = client.get(f"/api/analyses/{analysis_id}/{suffix}")
        assert shared.status_code == 200, suffix
        assert shared.content == direct.content
    assert client.get("/api/shared/forged/media").status_code == 401
