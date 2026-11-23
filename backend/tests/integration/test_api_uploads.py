from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from adcortex.api.app import create_app
from adcortex.api.context import build_context
from adcortex.config import Settings
from adcortex.domain.models import Job
from adcortex.pipeline.services import create_services
from adcortex.storage.repository import SCRIPT, AnalysisRepository
from tests.integration.conftest import FakeDispatcher

pytestmark = pytest.mark.ffmpeg

SCRIPT_TEXT = "Fresh coffee, roasted this morning, delivered to your door by noon."


def _upload(
    client: TestClient,
    path: Path,
    kind: str,
    *,
    filename: str | None = None,
    **fields: str,
) -> Any:
    with path.open("rb") as handle:
        return client.post(
            "/api/analyses",
            data={"kind": kind, **fields},
            files={"file": (filename or path.name, handle, "application/octet-stream")},
        )


def _client(tmp_path: Path, **overrides: Any) -> TestClient:
    settings = Settings(data_dir=tmp_path / "custom", **overrides)
    context = build_context(
        settings, services=create_services(settings), dispatcher=FakeDispatcher()
    )
    return TestClient(create_app(settings, context=context))


def _error(response: Any, status: int) -> str:
    assert response.status_code == status, response.text
    message = response.json()["error"]["message"]
    assert isinstance(message, str)
    return message


def test_videos_are_probed_stored_and_queued(
    client: TestClient,
    media_dir: Path,
    repo: AnalysisRepository,
    dispatcher: FakeDispatcher,
) -> None:
    path = media_dir / "three_scenes.mp4"

    response = _upload(client, path, "video")

    assert response.status_code == 202
    data = response.json()["data"]
    analysis_id = data["meta"]["id"]
    assert data["meta"]["name"] == "three_scenes"
    assert data["meta"]["kind"] == "video"
    assert data["meta"]["language"] == "auto"
    assert data["meta"]["source"] == {
        "filename": "three_scenes.mp4",
        "extension": ".mp4",
        "size_bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    assert data["state"]["status"] == "queued"
    assert dispatcher.jobs == [Job(kind="analyze", analysis_id=analysis_id)]
    assert repo.read_artifact(analysis_id, "source.mp4") == path.read_bytes()
    assert repo.get_job(analysis_id) is not None


def test_audio_keeps_the_requested_language_and_name(
    client: TestClient, media_dir: Path
) -> None:
    response = _upload(
        client,
        media_dir / "tone.wav",
        "audio",
        language="de",
        name="  Radio\tspot\n",
        filename="C:\\Users\\me\\radio.WAV",
    )

    meta = response.json()["data"]["meta"]
    assert meta["language"] == "de"
    assert meta["name"] == "Radio spot"
    assert meta["source"]["filename"] == "radio.WAV"
    assert meta["source"]["extension"] == ".wav"


def test_scripts_are_stored_for_text_to_speech(
    client: TestClient, repo: AnalysisRepository, dispatcher: FakeDispatcher
) -> None:
    response = client.post(
        "/api/analyses", data={"kind": "text", "script": f"  {SCRIPT_TEXT}  "}
    )

    assert response.status_code == 202
    meta = response.json()["data"]["meta"]
    assert meta["kind"] == "text"
    assert meta["name"] == "Fresh coffee, roasted this morning, delivered to your…"
    assert meta["source"]["filename"] == "script.txt"
    assert meta["source"]["sha256"] == hashlib.sha256(SCRIPT_TEXT.encode()).hexdigest()
    assert repo.read_artifact(meta["id"], SCRIPT) == SCRIPT_TEXT.encode()
    assert len(dispatcher.jobs) == 1


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"script": "Too short."}, "at least 20 characters"),
        ({"script": "word " * 700}, "at most 3000 characters"),
        ({"script": SCRIPT_TEXT, "language": "fa"}, "Persian can't be read aloud"),
        ({"script": SCRIPT_TEXT, "language": "xx"}, "Unsupported language 'xx'"),
        ({}, "at least 20 characters"),
    ],
)
def test_unusable_scripts_are_refused(
    client: TestClient, fields: dict[str, str], message: str
) -> None:
    response = client.post("/api/analyses", data={"kind": "text", **fields})

    assert message in _error(response, 422)


def test_media_uploads_need_a_file(client: TestClient) -> None:
    response = client.post("/api/analyses", data={"kind": "video"})

    assert _error(response, 422) == "Choose a file to upload."


def test_unsupported_file_types_are_refused(
    client: TestClient, media_dir: Path
) -> None:
    response = _upload(
        client, media_dir / "three_scenes.mp4", "video", filename="spot.exe"
    )

    assert "'.exe' files are not supported" in _error(response, 422)


def test_audio_files_are_not_videos(client: TestClient, media_dir: Path) -> None:
    response = _upload(client, media_dir / "tone.wav", "video")

    assert "'.wav' files are not supported" in _error(response, 422)


def test_videos_need_a_video_track(
    client: TestClient, media_dir: Path, tmp_path: Path
) -> None:
    audio_only = tmp_path / "voice.mp4"
    shutil.copy(media_dir / "tone.m4a", audio_only)

    response = _upload(client, audio_only, "video")

    assert "no video track" in _error(response, 422)


def test_audio_tracks_of_videos_can_be_analyzed(
    client: TestClient, media_dir: Path
) -> None:
    response = _upload(client, media_dir / "three_scenes.mp4", "audio")

    assert response.status_code == 202


def test_unreadable_files_are_refused(client: TestClient, media_dir: Path) -> None:
    response = _upload(client, media_dir / "junk.mp4", "video")

    assert "couldn't read" in _error(response, 422)


def test_clips_outside_the_duration_limits_are_refused(
    tmp_path: Path, media_dir: Path
) -> None:
    with _client(tmp_path, max_duration_s=4) as client:
        response = _upload(client, media_dir / "three_scenes.mp4", "video")

    assert "too long" in _error(response, 422)


def test_files_over_the_size_limit_are_refused(tmp_path: Path) -> None:
    big = tmp_path / "big.mp4"
    big.write_bytes(b"\0" * (1024 * 1024 + 1))

    with _client(tmp_path, max_upload_mb=1) as client:
        response = _upload(client, big, "video")

    assert _error(response, 413) == "The file is larger than 1 MB."


def test_empty_files_are_refused(client: TestClient, tmp_path: Path) -> None:
    empty = tmp_path / "empty.mp4"
    empty.write_bytes(b"")

    assert _error(_upload(client, empty, "video"), 422) == "The file is empty."


def test_names_longer_than_the_limit_are_refused(
    client: TestClient, media_dir: Path
) -> None:
    response = _upload(client, media_dir / "tone.wav", "audio", name="x" * 121)

    assert "at most 120 characters" in _error(response, 422)


def test_uploads_that_cannot_be_dispatched_fail_visibly(
    client: TestClient, media_dir: Path, dispatcher: FakeDispatcher
) -> None:
    dispatcher.error = ConnectionError("Modal is down")

    response = _upload(client, media_dir / "tone.wav", "audio")

    assert response.status_code == 202
    state = response.json()["data"]["state"]
    assert state["status"] == "failed"
    assert state["error"] == "The analysis could not be started. Retry the analysis."
