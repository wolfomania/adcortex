"""Password sessions and share links.

With `ADCORTEX_PASSWORD` set, logging in issues a session cookie that expires
after `ADCORTEX_SESSION_DAYS`. Its signature covers a digest of the password, so
changing the password ends every session. Share links open one analysis
read-only for `SHARE_DAYS`, with or without a password.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from adcortex.auth.keys import signing_key
from adcortex.auth.limiter import LoginLimiter
from adcortex.auth.tokens import TokenSigner
from adcortex.config import Settings
from adcortex.domain.errors import RateLimitedError, UnauthorizedError
from adcortex.domain.ids import is_analysis_id
from adcortex.storage.base import ArtifactStore

SESSION_COOKIE = "adcortex_session"
SHARE_DAYS = 30
_DAY_S = 86_400
_SHARE = "share"
INVALID_SHARE = "This share link is invalid or has expired."


@dataclass(frozen=True)
class ShareGrant:
    token: str
    expires_at: datetime


class Auth:
    def __init__(
        self,
        *,
        password: str | None,
        key: bytes,
        session_days: int,
        limiter: LoginLimiter | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._password = password or None
        self._signer = TokenSigner(key)
        self._session_s = session_days * _DAY_S
        self._limiter = limiter or LoginLimiter()
        self._clock = clock
        digest = hashlib.sha256((password or "").encode()).hexdigest()
        self._session_purpose = f"session:{digest}"

    @classmethod
    def from_settings(cls, settings: Settings, store: ArtifactStore) -> Auth:
        password = settings.password.get_secret_value() if settings.password else None
        return cls(
            password=password,
            key=signing_key(settings, store),
            session_days=settings.session_days,
        )

    @property
    def password_required(self) -> bool:
        return self._password is not None

    @property
    def session_max_age(self) -> int:
        return self._session_s

    # ── sessions ───────────────────────────────────────────────────────────

    def login(self, password: str, address: str) -> str:
        """Check the password; return the session cookie value."""
        if not self._limiter.allow(address):
            raise RateLimitedError("Too many login attempts. Wait a minute.")
        expected = (self._password or "").encode()
        if not hmac.compare_digest(password.encode(), expected):
            raise UnauthorizedError("Wrong password.")
        expires = int(self._clock()) + self._session_s
        return self._signer.sign(self._session_purpose, str(expires))

    def is_authenticated(self, cookie: str | None) -> bool:
        if not self.password_required:
            return True
        body = self._signer.unsign(self._session_purpose, cookie or "")
        return body is not None and body.isdigit() and int(body) > self._clock()

    # ── share links ────────────────────────────────────────────────────────

    def share(self, analysis_id: str) -> ShareGrant:
        expires = int(self._clock()) + SHARE_DAYS * _DAY_S
        token = self._signer.sign(_SHARE, f"{analysis_id}.{expires}")
        return ShareGrant(token, datetime.fromtimestamp(expires, UTC))

    def open_share(self, token: str) -> str:
        """The analysis a share token opens; UnauthorizedError when invalid."""
        body = self._signer.unsign(_SHARE, token)
        analysis_id, _, expires = (body or "").partition(".")
        if (
            not is_analysis_id(analysis_id)
            or not expires.isdigit()
            or int(expires) <= self._clock()
        ):
            raise UnauthorizedError(INVALID_SHARE)
        return analysis_id
