"""An app with the mock brain, local storage, and a dispatcher that only records."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.models.function import FunctionModel

from neuromarketing.api.app import create_app
from neuromarketing.api.context import AppContext, build_context
from neuromarketing.config import Settings
from neuromarketing.domain.ids import new_analysis_id
from neuromarketing.domain.models import (
    Analysis,
    AnalysisMeta,
    AnalysisResult,
    AnalysisState,
    AnalysisSummary,
    BrainFrames,
    Job,
    JobRef,
    LanguageInfo,
    MediaInfo,
    MediaKind,
    Scene,
    Scores,
    SourceFile,
    Status,
)
from neuromarketing.jobs.base import JobStatus
from neuromarketing.llm.client import LlmConfig
from neuromarketing.pipeline.services import Services, create_services
from neuromarketing.storage.repository import (
    FRAMES,
    PREVIEW_AUDIO,
    PREVIEW_VIDEO,
    STRIP,
    AnalysisRepository,
    keyframe_name,
)
from tests.llm_fakes import comparison_args, replying

START = datetime(2026, 11, 22, 12, 0, tzinfo=UTC)
VIDEO_BYTES = bytes(range(256)) * 40
FRAMES_BYTES = bytes([128]) * 24


class FakeDispatcher:
    """Records jobs instead of running them."""

    def __init__(self) -> None:
        self.jobs: list[Job] = []
        self.cancelled: list[JobRef] = []
        self.job_status: JobStatus = "running"
        self.error: Exception | None = None

    def submit(self, job: Job) -> JobRef:
        if self.error is not None:
            raise self.error
        self.jobs.append(job)
        return JobRef(backend="local", kind=job.kind, call_id=f"call-{len(self.jobs)}")

    def status(self, ref: JobRef) -> JobStatus:
        return self.job_status

    def cancel(self, ref: JobRef) -> None:
        self.cancelled.append(ref)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(data_dir=tmp_path / "data")


@pytest.fixture
def dispatcher() -> FakeDispatcher:
    return FakeDispatcher()


@pytest.fixture
def services(settings: Settings) -> Services:
    return create_services(settings)


@pytest.fixture
def context(
    settings: Settings, services: Services, dispatcher: FakeDispatcher
) -> AppContext:
    return build_context(settings, services=services, dispatcher=dispatcher)


@pytest.fixture
def repo(context: AppContext) -> AnalysisRepository:
    return context.repo


@pytest.fixture
def client(settings: Settings, context: AppContext) -> Iterator[TestClient]:
    with TestClient(create_app(settings, context=context)) as test_client:
        yield test_client


def with_llm(context: AppContext) -> AppContext:
    """The same app state, with a report model that writes comparisons."""
    model = FunctionModel(replying(comparison_args))
    llm = LlmConfig.from_model(model, "test-model", context.settings)
    return replace(context, services=replace(context.services, llm=llm))


def sample_result(duration_s: float = 6.0) -> AnalysisResult:
    seconds = int(duration_s)
    return AnalysisResult(
        duration_s=duration_s,
        times=tuple(float(t) for t in range(seconds)),
        systems=(),
        scenes=(Scene(index=0, start=0.0, end=duration_s, keyframe=keyframe_name(0)),),
        scene_stats=(),
        moments=(),
        scores=Scores(response_index=55.0, hook=60.0, sustain=50.0, peak_count=1),
        transcript=(),
        frames=BrainFrames(n_frames=seconds, n_vertices=4, vmin=-3.0, vmax=3.0),
        language=LanguageInfo(),
        strip=STRIP,
    )


def seed(
    repo: AnalysisRepository,
    *,
    status: Status = Status.COMPLETED,
    kind: MediaKind = MediaKind.VIDEO,
    name: str = "Spring spot",
    created: datetime = START,
    updated: datetime | None = None,
    artifacts: bool = True,
) -> Analysis:
    """Store an analysis as the pipeline would have left it."""
    meta = AnalysisMeta(
        id=new_analysis_id(created),
        name=name,
        kind=kind,
        created_at=created,
        source=SourceFile(
            filename="spot.mp4",
            extension=".mp4",
            size_bytes=len(VIDEO_BYTES),
            sha256=hashlib.sha256(name.encode()).hexdigest(),
        ),
    )
    done = status is Status.COMPLETED
    state = AnalysisState(
        status=status,
        updated_at=updated or created + timedelta(seconds=1),
        error="Boom." if status is Status.FAILED else None,
        media=MediaInfo(
            duration_s=6.0, has_video=kind is MediaKind.VIDEO, has_audio=True
        ),
        summary=AnalysisSummary(duration_s=6.0, response_index=55.0) if done else None,
    )
    repo.create(meta, state)
    if done:
        repo.save_result(meta.id, sample_result())
    if artifacts:
        video = kind is MediaKind.VIDEO
        files = [(PREVIEW_VIDEO if video else PREVIEW_AUDIO, VIDEO_BYTES)]
        files.append((FRAMES, FRAMES_BYTES))
        if video:  # audio has no pictures
            files.append((STRIP, b"\xff\xd8strip"))
            files.append((keyframe_name(0), b"\xff\xd8keyframe"))
        for artifact, data in files:
            repo.put_artifact_bytes(meta.id, artifact, data)
    return Analysis(meta=meta, state=state)
