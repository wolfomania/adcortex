"""Domain models shared by the pipeline, storage, API, and LLM layers.

Every model is immutable. Stored documents ignore unknown fields so older
analyses keep loading after the schema grows.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

ANALYSIS_ID_PATTERN = r"^\d{8}-\d{6}-[0-9a-f]{6}$"
AnalysisId = Annotated[str, Field(pattern=ANALYSIS_ID_PATTERN)]


def utcnow() -> datetime:
    return datetime.now(UTC)


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")


class MediaKind(StrEnum):
    VIDEO = "video"
    AUDIO = "audio"
    TEXT = "text"


class Status(StrEnum):
    QUEUED = "queued"
    PREPARING = "preparing"
    WAITING_FOR_GPU = "waiting_for_gpu"
    PREDICTING = "predicting"
    ANALYZING = "analyzing"
    INTERPRETING = "interpreting"
    COMPLETED = "completed"
    FAILED = "failed"

    @property
    def is_terminal(self) -> bool:
        return self in (Status.COMPLETED, Status.FAILED)


# ── Analysis documents ────────────────────────────────────────────────────


class SourceFile(Frozen):
    filename: str
    extension: str
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class AnalysisMeta(Frozen):
    """User-facing facts about an analysis. Written only by the web tier."""

    id: AnalysisId
    name: str = Field(min_length=1, max_length=120)
    kind: MediaKind
    created_at: datetime
    source: SourceFile
    language: str = "auto"


class MediaInfo(Frozen):
    duration_s: float = Field(gt=0)
    has_video: bool
    has_audio: bool
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    format_name: str = ""
    video_codec: str | None = None
    audio_codec: str | None = None


class LanguageInfo(Frozen):
    requested: str = "auto"
    detected: str | None = None
    full_support: bool = True


LlmStatus = Literal["ok", "skipped", "failed"]
LlmInputMode = Literal["video", "keyframes", "text"]


class LlmInfo(Frozen):
    model: str | None = None
    status: LlmStatus = "skipped"
    input_mode: LlmInputMode | None = None
    error: str | None = None


class AnalysisSummary(Frozen):
    """Small digest shown on history cards."""

    duration_s: float
    response_index: float | None = None
    top_systems: tuple[str, ...] = ()
    headline: str | None = None
    system_means: dict[str, float] = Field(default_factory=dict)


class AnalysisState(Frozen):
    """Pipeline-owned state. Written only by the pipeline."""

    status: Status
    message: str = ""
    error: str | None = None
    updated_at: datetime = Field(default_factory=utcnow)
    media: MediaInfo | None = None
    language: LanguageInfo | None = None
    llm: LlmInfo | None = None
    timings: dict[str, float] = Field(default_factory=dict)
    summary: AnalysisSummary | None = None
    reused_from: str | None = None


class JobRef(Frozen):
    """Handle of the background job that processes an analysis."""

    backend: Literal["local", "modal"]
    call_id: str | None = None
    dispatched_at: datetime = Field(default_factory=utcnow)


class Progress(Frozen):
    """Live progress, updated far more often than the stored state."""

    status: Status
    message: str = ""
    fraction: float = Field(default=0.0, ge=0.0, le=1.0)
    updated_at: datetime = Field(default_factory=utcnow)


class Analysis(Frozen):
    """Everything the API returns about one analysis, except large artifacts."""

    meta: AnalysisMeta
    state: AnalysisState
    progress: Progress | None = None


# ── Analysis result ────────────────────────────────────────────────────────


class Scene(Frozen):
    index: int = Field(ge=0)
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    keyframe: str | None = None


class Word(Frozen):
    text: str
    start: float
    end: float


Confidence = Literal["high", "medium", "low"]


class SystemSeries(Frozen):
    """One brain system's response over time, as baseline z-scores (1 Hz)."""

    id: str
    label: str
    confidence: Confidence
    applicable: bool = True
    values: tuple[float | None, ...]
    mean_z: float
    percentile: float | None = None
    library_percentile: float | None = None


class SceneStat(Frozen):
    scene_index: int
    mean_z: dict[str, float]


MomentKind = Literal["peak", "dip"]


class Moment(Frozen):
    t: float = Field(ge=0)
    kind: MomentKind
    system_id: str
    z: float
    label: str


class Scores(Frozen):
    """Deterministic headline numbers. Percentiles are 0-100."""

    response_index: float | None
    hook: float | None
    sustain: float | None
    peak_count: int


class BrainFrames(Frozen):
    """Per-second cortical maps, quantized to 8-bit for the 3D viewer."""

    file: str = "frames.bin"
    n_frames: int
    n_vertices: int
    vmin: float
    vmax: float


class BaselineRef(Frozen):
    version: str
    n_clips: int
    description: str


class AnalysisResult(Frozen):
    version: Literal[2] = 2
    duration_s: float
    times: tuple[float, ...]
    systems: tuple[SystemSeries, ...]
    scenes: tuple[Scene, ...]
    scene_stats: tuple[SceneStat, ...]
    moments: tuple[Moment, ...]
    scores: Scores
    transcript: tuple[Word, ...]
    envelope: tuple[float, ...] = ()
    envelope_hz: float = 10.0
    frames: BrainFrames | None = None
    baseline: BaselineRef | None = None
    language: LanguageInfo
    strip: str | None = None
    strip_columns: int = 10


# ── LLM output ─────────────────────────────────────────────────────────────


class KeyMoment(BaseModel):
    t: float = Field(description="Time in seconds from the start of the media.")
    title: str = Field(description="Short label, at most 8 words.")
    what_happens: str = Field(description="What the viewer sees or hears at t.")
    brain_response: str = Field(
        description="Which brain systems respond and how, citing the metrics."
    )
    why_it_matters: str = Field(description="Implication for the creative.")


class SceneNote(BaseModel):
    scene_index: int = Field(description="Index of the scene in the scene list.")
    note: str


class Recommendation(BaseModel):
    title: str
    detail: str
    t: float | None = Field(
        default=None, description="Time in seconds the advice refers to, if any."
    )


class Report(BaseModel):
    headline: str = Field(description="One-sentence verdict, at most 20 words.")
    summary: str = Field(description="Executive summary, 3-5 sentences.")
    key_moments: list[KeyMoment] = Field(min_length=1, max_length=8)
    scene_notes: list[SceneNote] = Field(default_factory=list)
    strengths: list[str] = Field(min_length=1, max_length=6)
    risks: list[str] = Field(min_length=1, max_length=6)
    recommendations: list[Recommendation] = Field(min_length=1, max_length=6)


class StoredReport(Frozen):
    model: str
    input_mode: LlmInputMode
    created_at: datetime = Field(default_factory=utcnow)
    report: Report


class ComparisonReport(BaseModel):
    headline: str = Field(description="One-sentence comparison, at most 20 words.")
    summary: str = Field(description="3-5 sentences comparing A and B.")
    a_strengths: list[str] = Field(min_length=1, max_length=5)
    b_strengths: list[str] = Field(min_length=1, max_length=5)
    recommendation: str = Field(description="Which elements to keep from each.")
