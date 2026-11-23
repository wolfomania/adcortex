"""Configuration, login, and health: the routes open without a session."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from adcortex import __version__
from adcortex.api.context import AppContext, Ctx
from adcortex.api.responses import ok
from adcortex.api.schemas import (
    AppConfig,
    Envelope,
    Health,
    LanguageOption,
    Limits,
    LlmSettings,
    LoginRequest,
    SessionInfo,
)
from adcortex.auth.service import SESSION_COOKIE
from adcortex.domain.languages import LANGUAGES, is_fully_supported

router = APIRouter(prefix="/api", tags=["session"])


@router.get("/health", response_model=Envelope[Health])
def health() -> Response:
    return ok(Health(version=__version__))


@router.get("/config", response_model=Envelope[AppConfig])
def config(request: Request, ctx: Ctx) -> Response:
    settings, llm = ctx.settings, ctx.services.llm
    return ok(
        AppConfig(
            version=__version__,
            password_required=ctx.auth.password_required,
            authenticated=ctx.auth.is_authenticated(
                request.cookies.get(SESSION_COOKIE)
            ),
            brain_backend=settings.brain_backend,
            llm=LlmSettings(enabled=llm is not None, model=llm and llm.model_name),
            limits=Limits(
                min_duration_s=settings.min_duration_s,
                max_duration_s=settings.max_duration_s,
                max_upload_mb=settings.max_upload_mb,
                min_script_chars=settings.min_script_chars,
                max_script_chars=settings.max_script_chars,
            ),
            languages=[
                LanguageOption(
                    code=code, name=name, full_support=is_fully_supported(code)
                )
                for code, name in LANGUAGES.items()
            ],
        )
    )


@router.post("/auth/login", response_model=Envelope[SessionInfo])
def login(body: LoginRequest, request: Request, ctx: Ctx) -> Response:
    if not ctx.auth.password_required:
        return ok(SessionInfo(authenticated=True))
    address = request.client.host if request.client else "unknown"
    cookie = ctx.auth.login(body.password, address)
    response = ok(SessionInfo(authenticated=True))
    response.set_cookie(
        SESSION_COOKIE,
        cookie,
        max_age=ctx.auth.session_max_age,
        path="/",
        secure=_secure(request, ctx),
        httponly=True,
        samesite="lax",
    )
    return response


@router.post("/auth/logout", response_model=Envelope[SessionInfo])
def logout(request: Request, ctx: Ctx) -> Response:
    response = ok(SessionInfo(authenticated=not ctx.auth.password_required))
    response.delete_cookie(
        SESSION_COOKIE,
        path="/",
        secure=_secure(request, ctx),
        httponly=True,
        samesite="lax",
    )
    return response


def _secure(request: Request, ctx: AppContext) -> bool:
    """Modal serves only HTTPS; elsewhere trust the scheme or the proxy's header."""
    forwarded = request.headers.get("x-forwarded-proto", "").split(",")[0].strip()
    return (
        ctx.settings.runtime == "modal"
        or request.url.scheme == "https"
        or forwarded.lower() == "https"
    )
