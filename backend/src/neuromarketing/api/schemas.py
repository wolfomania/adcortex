"""Request and response bodies of the HTTP API. See docs/api.md.

Every JSON response is an `Envelope`. Domain documents (`Analysis`,
`AnalysisResult`, `StoredReport`, `StoredComparison`) are returned as stored.
The frontend generates its TypeScript types from `api_json_schema()`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from neuromarketing.config import BrainBackend
from neuromarketing.domain.models import (
    Analysis,
    AnalysisId,
    AnalysisResult,
    StoredComparison,
    StoredReport,
)

ErrorCode = Literal[
    "invalid_input",  # 422: bad field, unsupported or invalid media
    "payload_too_large",  # 413: upload above the size limit
    "unauthorized",  # 401: password required, wrong password, or bad share token
    "not_found",  # 404
    "conflict",  # 409: the action does not fit the analysis's current state
    "rate_limited",  # 429: too many login attempts
    "unavailable",  # 503: a dependency (report model, GPU) is not configured
    "internal",  # 500
]


class ApiError(BaseModel):
    code: ErrorCode
    message: str = Field(description="Plain-language message for the person.")


class PageMeta(BaseModel):
    next_before: str | None = Field(
        default=None,
        description="Pass as ?before= for the next page; null on the last.",
    )


class Envelope[T](BaseModel):
    ok: bool
    data: T | None = None
    error: ApiError | None = None
    meta: PageMeta | None = None


# ── configuration and session ──────────────────────────────────────────────


class LanguageOption(BaseModel):
    code: str
    name: str
    full_support: bool = Field(
        description="False: predictions carry a lower-reliability caveat."
    )


class Limits(BaseModel):
    min_duration_s: float
    max_duration_s: float
    max_upload_mb: int
    min_script_chars: int
    max_script_chars: int


class LlmSettings(BaseModel):
    enabled: bool
    model: str | None = None


class AppConfig(BaseModel):
    """Public: the UI reads it before login."""

    version: str
    password_required: bool
    authenticated: bool
    brain_backend: BrainBackend = Field(
        description='"mock" and "replay" produce demo data; show a banner.'
    )
    llm: LlmSettings
    limits: Limits
    languages: list[LanguageOption]


class LoginRequest(BaseModel):
    password: str = Field(min_length=1, max_length=1024)


class SessionInfo(BaseModel):
    authenticated: bool


class Health(BaseModel):
    status: Literal["ok"] = "ok"
    version: str


# ── analyses ───────────────────────────────────────────────────────────────


class AnalysisDetail(BaseModel):
    analysis: Analysis
    result: AnalysisResult | None = Field(
        default=None,
        description="Set once the metrics are ready: while the report is being "
        "written (`interpreting`) and once `completed`.",
    )
    report: StoredReport | None = Field(
        default=None, description="Set when a report exists."
    )


class RenameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class ShareLink(BaseModel):
    token: str
    path: str = Field(description='App path of the read-only view, "/s/<token>".')
    expires_at: datetime


class WarmupState(BaseModel):
    warming: bool = Field(
        description="True when this call started or found a GPU warm-up."
    )


# ── comparison ─────────────────────────────────────────────────────────────


class CompareRequest(BaseModel):
    a_id: AnalysisId
    b_id: AnalysisId


ComparisonStatus = Literal["none", "running", "completed", "failed"]


class ComparisonState(BaseModel):
    status: ComparisonStatus
    comparison: StoredComparison | None = None
    error: str | None = None


RESPONSE_MODELS: tuple[type[BaseModel], ...] = (
    ApiError,
    PageMeta,
    AppConfig,
    LoginRequest,
    SessionInfo,
    Health,
    Analysis,
    AnalysisDetail,
    RenameRequest,
    ShareLink,
    WarmupState,
    CompareRequest,
    ComparisonState,
)


def api_json_schema() -> dict[str, Any]:
    """One JSON Schema document whose `$defs` hold every API model."""
    defs: dict[str, Any] = {}
    for model in RESPONSE_MODELS:
        schema = model.model_json_schema(ref_template="#/$defs/{model}")
        defs.update(schema.pop("$defs", {}))
        defs[model.__name__] = schema
    return {"$schema": "https://json-schema.org/draft/2020-12/schema", "$defs": defs}
