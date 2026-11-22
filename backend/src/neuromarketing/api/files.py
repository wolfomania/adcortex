"""Binary responses: media with ranges, brain frames, and images.

Files of a completed analysis never change, so browsers may cache them for
good. Files of an unfinished analysis can still be replaced by a retry and
are never cached.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi import Request, Response
from fastapi.responses import FileResponse

from neuromarketing.api.context import AppContext
from neuromarketing.domain.models import Analysis, MediaKind, Status
from neuromarketing.storage.repository import (
    FRAMES,
    PREVIEW_AUDIO,
    PREVIEW_VIDEO,
    STRIP,
    keyframe_name,
)

IMMUTABLE = "private, max-age=31536000, immutable"
NO_STORE = "no-store"
JPEG = "image/jpeg"


def file_response(
    request: Request, path: Path, *, media_type: str, etag: str, cache_control: str
) -> Response:
    """A file with ranges, or 304 when the browser already has this version."""
    headers = {"etag": etag, "cache-control": cache_control}
    if _matches(request.headers.get("if-none-match"), etag):
        return Response(status_code=304, headers=headers)
    return FileResponse(path, media_type=media_type, headers=headers)


def make_etag(*parts: object, weak: bool = False) -> str:
    """Weak tags suit bodies that may be gzipped on the way out."""
    digest = hashlib.sha256("/".join(map(str, parts)).encode()).hexdigest()[:24]
    return f'W/"{digest}"' if weak else f'"{digest}"'


def serve_media(ctx: AppContext, request: Request, analysis_id: str) -> Response:
    analysis = ctx.repo.get(analysis_id)
    if analysis.meta.kind is MediaKind.VIDEO:
        return _artifact(ctx, request, analysis, PREVIEW_VIDEO, "video/mp4")
    return _artifact(ctx, request, analysis, PREVIEW_AUDIO, "audio/mp4")


def serve_frames(ctx: AppContext, request: Request, analysis_id: str) -> Response:
    analysis = ctx.repo.get(analysis_id)
    media_type = "application/octet-stream"
    return _artifact(ctx, request, analysis, FRAMES, media_type, weak=True)


def serve_keyframe(
    ctx: AppContext, request: Request, analysis_id: str, scene_index: int
) -> Response:
    analysis = ctx.repo.get(analysis_id)
    return _artifact(ctx, request, analysis, keyframe_name(scene_index), JPEG)


def serve_strip(ctx: AppContext, request: Request, analysis_id: str) -> Response:
    analysis = ctx.repo.get(analysis_id)
    return _artifact(ctx, request, analysis, STRIP, JPEG)


def _artifact(
    ctx: AppContext,
    request: Request,
    analysis: Analysis,
    name: str,
    media_type: str,
    *,
    weak: bool = False,
) -> Response:
    analysis_id = analysis.meta.id
    path = ctx.repo.local_artifact(analysis_id, name)
    done = analysis.state.status is Status.COMPLETED
    return file_response(
        request,
        path,
        media_type=media_type,
        etag=make_etag(analysis_id, name, path.stat().st_size, weak=weak),
        cache_control=IMMUTABLE if done else NO_STORE,
    )


def _matches(header: str | None, etag: str) -> bool:
    """If-None-Match uses weak comparison: W/"x" matches "x"."""
    if not header:
        return False
    if header.strip() == "*":
        return True
    wanted = etag.removeprefix("W/")
    return any(tag.strip().removeprefix("W/") == wanted for tag in header.split(","))
