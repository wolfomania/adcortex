"""ASGI middleware that runs before any request body is read.

`ApiGate` refuses API requests without a session (when a password is set)
and bodies above the limit, so an anonymous client can never make the server
spool a large upload to disk. `SecurityHeaders` hardens every response.
"""

from __future__ import annotations

from fastapi import HTTPException
from starlette.datastructures import MutableHeaders
from starlette.requests import HTTPConnection
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from adcortex.api.responses import failure
from adcortex.auth.service import SESSION_COOKIE, Auth

PUBLIC_PATHS = frozenset({"/api/health", "/api/config"})
PUBLIC_PREFIXES = ("/api/auth/", "/api/shared/")
UPLOAD_PATH = "/api/analyses"
JSON_BODY_LIMIT = 64 * 1024
# Multipart boundaries and the other form fields, on top of the file.
FORM_OVERHEAD = 1024 * 1024
LOGIN_REQUIRED = "Log in to continue."
BODY_TOO_LARGE = "The request body is too large."


def is_public(path: str) -> bool:
    return path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES)


def upload_too_large(max_upload_mb: int) -> str:
    return f"The file is larger than {max_upload_mb} MB."


class ApiGate:
    def __init__(self, app: ASGIApp, *, auth: Auth, max_upload_mb: int) -> None:
        self.app = app
        self.auth = auth
        self.max_upload_mb = max_upload_mb

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        if scope["type"] != "http" or not path.startswith("/api/"):
            await self.app(scope, receive, send)
            return
        connection = HTTPConnection(scope)
        session = connection.cookies.get(SESSION_COOKIE)
        if not is_public(path) and not self.auth.is_authenticated(session):
            await failure(401, LOGIN_REQUIRED)(scope, receive, send)
            return
        limit, message = self._limit(scope)
        declared = connection.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > limit:
            await failure(413, message)(scope, receive, send)
            return
        await self.app(scope, _capped(receive, limit, message), send)

    def _limit(self, scope: Scope) -> tuple[int, str]:
        if scope["method"] == "POST" and scope["path"] == UPLOAD_PATH:
            limit = self.max_upload_mb * 1024 * 1024 + FORM_OVERHEAD
            return limit, upload_too_large(self.max_upload_mb)
        return JSON_BODY_LIMIT, BODY_TOO_LARGE


def _capped(receive: Receive, limit: int, message: str) -> Receive:
    """Stop bodies sent without a Content-Length once they pass the limit."""
    received = 0

    async def wrapped() -> Message:
        nonlocal received
        event = await receive()
        if event["type"] == "http.request":
            received += len(event.get("body", b""))
            if received > limit:
                raise HTTPException(413, message)
        return event

    return wrapped


class SecurityHeaders:
    HEADERS = (
        ("x-content-type-options", "nosniff"),
        # Share links carry their token in the URL; never pass it on.
        ("referrer-policy", "no-referrer"),
        ("x-frame-options", "DENY"),
    )

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in self.HEADERS:
                    headers.setdefault(name, value)
            await send(message)

        await self.app(scope, receive, send_with_headers)
