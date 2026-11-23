"""Upload, list, inspect, edit, and share analyses."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, Query, Response, UploadFile

from adcortex.api import actions
from adcortex.api.context import Ctx
from adcortex.api.responses import ok
from adcortex.api.schemas import (
    AnalysisDetail,
    Envelope,
    PageMeta,
    RenameRequest,
    ShareLink,
    WarmupState,
)
from adcortex.api.uploads import UploadForm, create_analysis
from adcortex.domain.models import ANALYSIS_ID_PATTERN, Analysis, MediaKind

router = APIRouter(prefix="/api", tags=["analyses"])


@router.post("/analyses", status_code=202, response_model=Envelope[Analysis])
def create(
    ctx: Ctx,
    kind: Annotated[MediaKind, Form()],
    file: Annotated[UploadFile | None, File()] = None,
    script: Annotated[str | None, Form()] = None,
    name: Annotated[str | None, Form()] = None,
    language: Annotated[str | None, Form()] = None,
) -> Response:
    form = UploadForm(kind=kind, file=file, script=script, name=name, language=language)
    return ok(create_analysis(ctx, form), status=202)


@router.get("/analyses", response_model=Envelope[list[Analysis]])
def list_analyses(
    ctx: Ctx,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    before: Annotated[str | None, Query(pattern=ANALYSIS_ID_PATTERN)] = None,
) -> Response:
    items, next_before = actions.history(ctx, limit=limit, before=before)
    return ok(items, meta=PageMeta(next_before=next_before))


@router.get("/analyses/{analysis_id}", response_model=Envelope[AnalysisDetail])
def get_analysis(analysis_id: str, ctx: Ctx) -> Response:
    return ok(actions.detail(ctx.repo, actions.current(ctx, analysis_id)))


@router.get("/analyses/{analysis_id}/status", response_model=Envelope[Analysis])
def get_status(analysis_id: str, ctx: Ctx) -> Response:
    return ok(actions.current(ctx, analysis_id))


@router.patch("/analyses/{analysis_id}", response_model=Envelope[Analysis])
def rename(analysis_id: str, body: RenameRequest, ctx: Ctx) -> Response:
    return ok(actions.rename(ctx, analysis_id, body.name))


@router.delete("/analyses/{analysis_id}", response_model=Envelope[None])
def delete(analysis_id: str, ctx: Ctx) -> Response:
    actions.delete(ctx, analysis_id)
    return ok(None)


@router.post(
    "/analyses/{analysis_id}/retry", status_code=202, response_model=Envelope[Analysis]
)
def retry(analysis_id: str, ctx: Ctx) -> Response:
    return ok(actions.retry(ctx, analysis_id), status=202)


@router.post(
    "/analyses/{analysis_id}/report", status_code=202, response_model=Envelope[Analysis]
)
def rewrite_report(analysis_id: str, ctx: Ctx) -> Response:
    return ok(actions.rewrite_report(ctx, analysis_id), status=202)


@router.post("/analyses/{analysis_id}/share", response_model=Envelope[ShareLink])
def share(analysis_id: str, ctx: Ctx) -> Response:
    return ok(actions.share(ctx, analysis_id))


@router.post("/warmup", response_model=Envelope[WarmupState])
def warmup(ctx: Ctx) -> Response:
    return ok(WarmupState(warming=ctx.warmup.start()))
