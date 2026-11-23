"""The whole app: uploads run through the real pipeline with the mock brain."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from adcortex.api.app import create_app
from adcortex.api.context import AppContext, build_context
from adcortex.config import Settings
from adcortex.jobs.local import LocalDispatcher
from adcortex.llm.client import LlmConfig
from adcortex.pipeline.services import create_services
from tests.llm_fakes import comparison_args, report_args

pytestmark = pytest.mark.ffmpeg


def _writer(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    """Answers report and comparison requests alike."""
    tool = info.output_tools[0]
    properties = tool.parameters_json_schema.get("properties", {})
    args = comparison_args() if "a_strengths" in properties else report_args(t=1.0)
    return ModelResponse(parts=[ToolCallPart(tool.name, args)])


@pytest.fixture
def app(tmp_path: Path) -> Iterator[tuple[TestClient, AppContext]]:
    settings = Settings(data_dir=tmp_path / "data")
    services = create_services(settings)
    llm = LlmConfig.from_model(FunctionModel(_writer), "test-model", settings)
    context = build_context(settings, services=replace(services, llm=llm))
    with TestClient(create_app(settings, context=context)) as client:
        yield client, context


def _wait(context: AppContext) -> None:
    dispatcher = context.dispatcher
    assert isinstance(dispatcher, LocalDispatcher)
    dispatcher.drain(timeout=60)


def _upload(client: TestClient, path: Path, kind: str) -> str:
    with path.open("rb") as handle:
        response = client.post(
            "/api/analyses",
            data={"kind": kind},
            files={"file": (path.name, handle, "application/octet-stream")},
        )
    assert response.status_code == 202, response.text
    analysis_id = response.json()["data"]["meta"]["id"]
    assert isinstance(analysis_id, str)
    return analysis_id


def _get(client: TestClient, path: str) -> Any:
    body = client.get(path).json()
    assert body["ok"] is True, body
    return body["data"]


def test_upload_analyze_compare_and_rewrite(
    app: tuple[TestClient, AppContext], media_dir: Path
) -> None:
    client, context = app

    video = _upload(client, media_dir / "three_scenes.mp4", "video")
    audio = _upload(client, media_dir / "tone.wav", "audio")
    _wait(context)

    status = _get(client, f"/api/analyses/{video}/status")
    assert status["state"]["status"] == "completed", status["state"]
    assert status["state"]["llm"]["status"] == "ok"
    detail = _get(client, f"/api/analyses/{video}")
    result = detail["result"]
    assert [scene["start"] for scene in result["scenes"]] == [0.0, 2.0, 4.0]
    assert detail["report"]["report"]["headline"] == "Faces land at 5 s."
    frames = client.get(f"/api/analyses/{video}/frames").content
    assert len(frames) == result["frames"]["n_frames"] * result["frames"]["n_vertices"]
    for suffix in ("media", "keyframes/2", "strip"):
        assert client.get(f"/api/analyses/{video}/{suffix}").status_code == 200

    started = client.post("/api/compare", json={"a_id": video, "b_id": audio})
    assert started.status_code == 202
    _wait(context)
    comparison = _get(client, f"/api/compare/{video}/{audio}")
    assert comparison["status"] == "completed"
    assert comparison["comparison"]["report"]["headline"] == "B hooks faster."

    rewrite = client.post(f"/api/analyses/{audio}/report")
    assert rewrite.status_code == 202
    _wait(context)
    rewritten = _get(client, f"/api/analyses/{audio}")
    assert rewritten["analysis"]["state"]["status"] == "completed"
    assert rewritten["report"]["input_mode"] == "audio"

    history = _get(client, "/api/analyses")
    assert [item["meta"]["id"] for item in history] == [audio, video]
    assert client.delete(f"/api/analyses/{video}").status_code == 200
    assert client.get(f"/api/compare/{video}/{audio}").status_code == 404
    assert context.repo.get_comparison(video, audio) is None


def test_local_runtime_builds_its_own_dispatcher(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "data")

    context = build_context(settings)

    assert isinstance(context.dispatcher, LocalDispatcher)
    assert context.services.brain.name == "mock"
    context.close()
