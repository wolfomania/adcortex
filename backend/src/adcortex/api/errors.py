"""Turn every error into the envelope, with a message written for people."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException

from adcortex.api.responses import failure
from adcortex.domain.errors import UserFacingError

logger = logging.getLogger(__name__)

UNEXPECTED = "Something went wrong on the server. Try again in a minute."
_FRIENDLY = {404: "Not found.", 405: "Method not allowed."}
_LOCATIONS = frozenset({"body", "query", "path", "header", "cookie"})


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(UserFacingError, _user_error)
    app.add_exception_handler(RequestValidationError, _invalid_request)
    app.add_exception_handler(HTTPException, _http_error)
    app.add_exception_handler(Exception, _unexpected)


def describe_validation(errors: Sequence[Any]) -> str:
    """The first problem as "field: message", e.g. "name: Field required"."""
    if not errors:
        return "The request is invalid."
    first = errors[0]
    field = ".".join(
        str(part) for part in first.get("loc", ()) if part not in _LOCATIONS
    )
    message = str(first.get("msg", "Invalid value"))
    return f"{field}: {message}" if field else message


async def _user_error(request: Request, exc: Exception) -> Response:
    assert isinstance(exc, UserFacingError)
    if exc.status_code >= 500:
        logger.error("%s %s failed: %s", request.method, request.url.path, exc)
    return failure(exc.status_code, str(exc))


async def _invalid_request(request: Request, exc: Exception) -> Response:
    assert isinstance(exc, RequestValidationError)
    return failure(422, describe_validation(exc.errors()))


async def _http_error(request: Request, exc: Exception) -> Response:
    assert isinstance(exc, HTTPException)
    status = exc.status_code
    default = HTTPStatus(status).phrase if status in HTTPStatus else ""
    detail = str(exc.detail)
    message = _FRIENDLY.get(status, detail) if detail == default else detail
    return failure(status, message, headers=exc.headers)


async def _unexpected(request: Request, exc: Exception) -> Response:
    logger.error(
        "Unhandled error on %s %s", request.method, request.url.path, exc_info=exc
    )
    return failure(500, UNEXPECTED)
