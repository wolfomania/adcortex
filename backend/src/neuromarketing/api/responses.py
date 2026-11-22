"""JSON responses in the API envelope: `{ok, data, error, meta}`."""

from __future__ import annotations

from collections.abc import Mapping
from http import HTTPStatus
from typing import Any

from fastapi import Response

from neuromarketing.api.schemas import ApiError, Envelope, ErrorCode, PageMeta

JSON = "application/json"

ERROR_CODES: dict[int, ErrorCode] = {
    HTTPStatus.BAD_REQUEST: "invalid_input",
    HTTPStatus.UNAUTHORIZED: "unauthorized",
    HTTPStatus.NOT_FOUND: "not_found",
    HTTPStatus.METHOD_NOT_ALLOWED: "invalid_input",
    HTTPStatus.CONFLICT: "conflict",
    HTTPStatus.REQUEST_ENTITY_TOO_LARGE: "payload_too_large",
    HTTPStatus.UNPROCESSABLE_ENTITY: "invalid_input",
    HTTPStatus.TOO_MANY_REQUESTS: "rate_limited",
    HTTPStatus.SERVICE_UNAVAILABLE: "unavailable",
}


def ok(data: Any, *, status: int = 200, meta: PageMeta | None = None) -> Response:
    body = Envelope[Any](ok=True, data=data, meta=meta).model_dump_json()
    return Response(body, status_code=status, media_type=JSON)


def failure(
    status: int, message: str, *, headers: Mapping[str, str] | None = None
) -> Response:
    error = ApiError(code=ERROR_CODES.get(status, "internal"), message=message)
    body = Envelope[Any](ok=False, error=error).model_dump_json()
    return Response(body, status_code=status, media_type=JSON, headers=headers)
