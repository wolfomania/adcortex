from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import SecretStr

from neuromarketing.auth.keys import KEY_PATH, signing_key
from neuromarketing.auth.limiter import LoginLimiter
from neuromarketing.auth.service import SHARE_DAYS, Auth
from neuromarketing.auth.tokens import TokenSigner
from neuromarketing.config import Settings
from neuromarketing.domain.errors import RateLimitedError, UnauthorizedError
from neuromarketing.storage.local import LocalFsStore

KEY = b"k" * 32
ANALYSIS_ID = "20261122-120000-abcdef"
DAY = 86_400.0


class Clock:
    def __init__(self, now: float = 1_800_000_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def _auth(
    password: str | None = "open sesame",
    *,
    key: bytes = KEY,
    clock: Clock | None = None,
    limiter: LoginLimiter | None = None,
) -> Auth:
    return Auth(
        password=password,
        key=key,
        session_days=30,
        clock=clock or Clock(),
        limiter=limiter,
    )


# ── signed tokens ──────────────────────────────────────────────────────────


def test_signed_tokens_round_trip_only_for_their_purpose() -> None:
    signer = TokenSigner(KEY)

    token = signer.sign("share", "payload")

    assert signer.unsign("share", token) == "payload"
    assert signer.unsign("session", token) is None
    assert TokenSigner(b"x" * 32).unsign("share", token) is None


@pytest.mark.parametrize(
    "token",
    ["", "payload", "payload.", ".abc", "payload.AAAA", "payload.ü", "p." + "A" * 600],
)
def test_malformed_or_forged_tokens_are_rejected(token: str) -> None:
    assert TokenSigner(KEY).unsign("share", token) is None


# ── password sessions ──────────────────────────────────────────────────────


def test_the_right_password_opens_a_session() -> None:
    auth = _auth()

    cookie = auth.login("open sesame", "203.0.113.7")

    assert auth.password_required
    assert auth.is_authenticated(cookie)
    assert not auth.is_authenticated(None)
    assert auth.session_max_age == 30 * 86_400


def test_a_wrong_password_is_refused() -> None:
    with pytest.raises(UnauthorizedError, match="Wrong password"):
        _auth().login("open sesame ", "203.0.113.7")


def test_sessions_expire() -> None:
    clock = Clock()
    auth = _auth(clock=clock)
    cookie = auth.login("open sesame", "203.0.113.7")

    clock.now += 30 * DAY + 1

    assert not auth.is_authenticated(cookie)


def test_changing_the_password_ends_every_session() -> None:
    cookie = _auth().login("open sesame", "203.0.113.7")

    assert not _auth("new password").is_authenticated(cookie)


@pytest.mark.parametrize("cookie", ["", "123", "9999999999.AAAA", "abc.def.ghi"])
def test_forged_session_cookies_are_rejected(cookie: str) -> None:
    assert not _auth().is_authenticated(cookie)


def test_without_a_password_everyone_is_authenticated() -> None:
    auth = _auth(None)

    assert not auth.password_required
    assert auth.is_authenticated(None)


def test_login_attempts_are_rate_limited_per_address() -> None:
    clock = Clock()
    auth = _auth(limiter=LoginLimiter(attempts=5, window_s=60.0, clock=clock))
    for _ in range(5):
        with pytest.raises(UnauthorizedError):
            auth.login("guess", "203.0.113.7")

    with pytest.raises(RateLimitedError, match="Too many login attempts"):
        auth.login("open sesame", "203.0.113.7")
    assert auth.login("open sesame", "198.51.100.2")

    clock.now += 61
    assert auth.login("open sesame", "203.0.113.7")


def test_the_limiter_forgets_quiet_addresses() -> None:
    clock = Clock()
    limiter = LoginLimiter(attempts=1, window_s=60.0, clock=clock, max_addresses=2)
    for address in ("a", "b"):
        assert limiter.allow(address)
    clock.now += 61

    assert limiter.allow("c")
    assert limiter.tracked == 1


# ── share links ────────────────────────────────────────────────────────────


def test_share_tokens_open_one_analysis_for_thirty_days() -> None:
    clock = Clock()
    auth = _auth(clock=clock)

    grant = auth.share(ANALYSIS_ID)

    assert auth.open_share(grant.token) == ANALYSIS_ID
    assert grant.expires_at == datetime.fromtimestamp(clock.now, UTC) + timedelta(
        days=SHARE_DAYS
    )
    clock.now += SHARE_DAYS * DAY + 1
    with pytest.raises(UnauthorizedError, match="expired"):
        auth.open_share(grant.token)


def test_share_tokens_keep_working_without_a_password() -> None:
    grant = _auth(None).share(ANALYSIS_ID)

    assert _auth(None).open_share(grant.token) == ANALYSIS_ID


@pytest.mark.parametrize(
    "token",
    [
        "",
        "not-a-token",
        f"{ANALYSIS_ID}.4102444800.forged",
        f"../{ANALYSIS_ID}.4102444800.AAAA",
    ],
)
def test_forged_share_tokens_are_rejected(token: str) -> None:
    with pytest.raises(UnauthorizedError, match="invalid or has expired"):
        _auth().open_share(token)


def test_session_cookies_and_share_tokens_are_not_interchangeable() -> None:
    auth = _auth()
    cookie = auth.login("open sesame", "203.0.113.7")
    grant = auth.share(ANALYSIS_ID)

    assert not auth.is_authenticated(grant.token)
    with pytest.raises(UnauthorizedError):
        auth.open_share(cookie)


# ── signing key ────────────────────────────────────────────────────────────


def test_the_signing_key_is_created_once_and_kept_in_the_store(
    tmp_path: Path,
) -> None:
    store = LocalFsStore(tmp_path)
    settings = Settings(data_dir=tmp_path)

    first = signing_key(settings, store)

    assert len(first) == 32
    assert store.read_bytes(KEY_PATH) == first
    assert signing_key(settings, store) == first


def test_a_configured_secret_key_replaces_the_stored_one(tmp_path: Path) -> None:
    store = LocalFsStore(tmp_path)
    settings = Settings(data_dir=tmp_path, secret_key=SecretStr("configured"))

    key = signing_key(settings, store)

    assert key == signing_key(settings, LocalFsStore(tmp_path / "other"))
    assert not store.exists(KEY_PATH)


def test_a_damaged_stored_key_is_replaced(tmp_path: Path) -> None:
    store = LocalFsStore(tmp_path)
    store.write_bytes(KEY_PATH, b"short")

    key = signing_key(Settings(data_dir=tmp_path), store)

    assert len(key) == 32
    assert store.read_bytes(KEY_PATH) == key


def test_auth_reads_the_password_from_settings(tmp_path: Path) -> None:
    store = LocalFsStore(tmp_path)
    settings = Settings(data_dir=tmp_path, password=SecretStr("pw"))

    auth = Auth.from_settings(settings, store)

    assert auth.is_authenticated(auth.login("pw", "203.0.113.7"))
    assert not Auth.from_settings(Settings(data_dir=tmp_path), store).password_required
