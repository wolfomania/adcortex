"""Serve the built single-page app next to the API.

Hashed files under `assets/` are cached for good. Other files are
revalidated. Every other path gets `index.html`, so client-side routes
such as `/a/<id>` and `/s/<token>` load the app.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import FastAPI, Request, Response

from adcortex.api.files import file_response, make_etag
from adcortex.domain.errors import ConfigurationError, NotFoundError

IMMUTABLE = "public, max-age=31536000, immutable"
REVALIDATE = "no-cache"
CONTENT_SECURITY_POLICY = "; ".join(
    (
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data: blob:",
        "media-src 'self' blob:",
        "font-src 'self' data:",
        "connect-src 'self'",
        "worker-src 'self' blob:",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    )
)
mimetypes.add_type("application/wasm", ".wasm")


def resolve_static(root: Path, path: str) -> Path | None:
    """The file at `path` inside `root`, or None; never a path outside it."""
    if not path:
        return None
    candidate = (root / path).resolve()
    if not candidate.is_relative_to(root) or not candidate.is_file():
        return None
    return candidate


def mount_frontend(app: FastAPI, dist: Path) -> None:
    root = dist.resolve()
    index = root / "index.html"
    if not index.is_file():
        raise ConfigurationError(
            f"ADCORTEX_FRONTEND_DIST={dist} has no index.html. "
            "Build the app first: cd frontend && pnpm build."
        )
    page = index.read_bytes()
    page_headers = {
        "cache-control": REVALIDATE,
        "content-security-policy": CONTENT_SECURITY_POLICY,
    }

    @app.get("/{path:path}", include_in_schema=False)
    def app_page(path: str, request: Request) -> Response:
        if path == "api" or path.startswith("api/"):
            raise NotFoundError("Not found.")
        found = resolve_static(root, path)
        if found is not None:
            return _static(request, found, hashed=path.startswith("assets/"))
        if path.startswith("assets/"):
            # An old build's asset: HTML here would fail as a script anyway.
            raise NotFoundError("Not found.")
        return Response(page, media_type="text/html", headers=page_headers)


def _static(request: Request, path: Path, *, hashed: bool) -> Response:
    stat = path.stat()
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return file_response(
        request,
        path,
        media_type=media_type,
        etag=make_etag(path.name, stat.st_mtime_ns, stat.st_size),
        cache_control=IMMUTABLE if hashed else REVALIDATE,
    )
