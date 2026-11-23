"""Analysis identifiers: sortable by creation time and safe in paths."""

from __future__ import annotations

import re
import secrets
from datetime import UTC, datetime

from adcortex.domain.errors import NotFoundError
from adcortex.domain.models import ANALYSIS_ID_PATTERN

_ID_RE = re.compile(ANALYSIS_ID_PATTERN)


def new_analysis_id(now: datetime | None = None) -> str:
    """`YYYYMMDD-HHMMSS-mmmrrr`: the milliseconds in hex, then 12 random bits.

    The milliseconds keep uploads made within one second in order.
    """
    moment = (now or datetime.now(UTC)).astimezone(UTC)
    millis = moment.microsecond // 1000
    return f"{moment:%Y%m%d-%H%M%S}-{millis:03x}{secrets.token_hex(2)[:3]}"


def is_analysis_id(value: str) -> bool:
    return bool(_ID_RE.fullmatch(value))


def require_analysis_id(value: str) -> str:
    """Return `value` if it is a well-formed id; otherwise raise NotFoundError.

    Malformed ids are reported as "not found" so the API never echoes
    attacker-controlled path fragments into storage calls.
    """
    if not is_analysis_id(value):
        raise NotFoundError("Analysis not found.")
    return value
