"""Media, brain frames, and images, by analysis id or by share token."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Request, Response

from neuromarketing.api import actions
from neuromarketing.api.context import Ctx
from neuromarketing.api.files import (
    serve_frames,
    serve_keyframe,
    serve_media,
    serve_strip,
)
from neuromarketing.api.responses import ok
from neuromarketing.api.schemas import AnalysisDetail, Envelope

router = APIRouter(prefix="/api", tags=["media"])

SceneIndex = Annotated[int, Path(ge=0, le=999)]


@router.get("/analyses/{analysis_id}/media")
def media(analysis_id: str, request: Request, ctx: Ctx) -> Response:
    return serve_media(ctx, request, analysis_id)


@router.get("/analyses/{analysis_id}/frames")
def frames(analysis_id: str, request: Request, ctx: Ctx) -> Response:
    return serve_frames(ctx, request, analysis_id)


@router.get("/analyses/{analysis_id}/keyframes/{scene_index}")
def keyframe(
    analysis_id: str, scene_index: SceneIndex, request: Request, ctx: Ctx
) -> Response:
    return serve_keyframe(ctx, request, analysis_id, scene_index)


@router.get("/analyses/{analysis_id}/strip")
def strip(analysis_id: str, request: Request, ctx: Ctx) -> Response:
    return serve_strip(ctx, request, analysis_id)


# ── read-only share links ──────────────────────────────────────────────────


@router.get("/shared/{token}", response_model=Envelope[AnalysisDetail])
def shared(token: str, ctx: Ctx) -> Response:
    return ok(actions.shared_detail(ctx, token))


@router.get("/shared/{token}/media")
def shared_media(token: str, request: Request, ctx: Ctx) -> Response:
    return serve_media(ctx, request, ctx.auth.open_share(token))


@router.get("/shared/{token}/frames")
def shared_frames(token: str, request: Request, ctx: Ctx) -> Response:
    return serve_frames(ctx, request, ctx.auth.open_share(token))


@router.get("/shared/{token}/keyframes/{scene_index}")
def shared_keyframe(
    token: str, scene_index: SceneIndex, request: Request, ctx: Ctx
) -> Response:
    return serve_keyframe(ctx, request, ctx.auth.open_share(token), scene_index)


@router.get("/shared/{token}/strip")
def shared_strip(token: str, request: Request, ctx: Ctx) -> Response:
    return serve_strip(ctx, request, ctx.auth.open_share(token))
