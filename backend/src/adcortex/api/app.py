"""The ASGI app: API routes, middleware, error handling, and the built UI.

Run it locally with `uvicorn --factory adcortex.api.app:create_app`.
On Modal, the web function returns `create_app()`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from adcortex import __version__
from adcortex.api.context import AppContext, build_context
from adcortex.api.errors import install_error_handlers
from adcortex.api.frontend import mount_frontend
from adcortex.api.middleware import ApiGate, SecurityHeaders
from adcortex.api.routes import analyses, compare, media, session
from adcortex.config import Settings, get_settings

# Already compressed; gzip would only cost CPU (and break byte ranges).
COMPRESSED_TYPES = (
    "text/event-stream",
    "video/mp4",
    "audio/mp4",
    "image/jpeg",
    "image/png",
    "image/webp",
    "font/woff2",
)


def create_app(
    settings: Settings | None = None, *, context: AppContext | None = None
) -> FastAPI:
    ctx = context or build_context(settings or get_settings())

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            ctx.close()

    app = FastAPI(
        title="AI AdCortex",
        version=__version__,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    app.state.context = ctx
    install_error_handlers(app)
    for module in (session, analyses, media, compare):
        app.include_router(module.router)
    if ctx.settings.frontend_dist is not None:
        mount_frontend(app, ctx.settings.frontend_dist)
    # Added innermost first: the security headers wrap everything else.
    app.add_middleware(
        GZipMiddleware, minimum_size=1024, exclude_content_types=COMPRESSED_TYPES
    )
    app.add_middleware(ApiGate, auth=ctx.auth, max_upload_mb=ctx.settings.max_upload_mb)
    if ctx.settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=ctx.settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    app.add_middleware(SecurityHeaders)
    return app
