from __future__ import annotations

from datetime import UTC, datetime

import pytest

from adcortex.domain.errors import InvalidInputError, NotFoundError
from adcortex.domain.ids import (
    is_analysis_id,
    new_analysis_id,
    require_analysis_id,
)
from adcortex.domain.languages import is_fully_supported, normalize_language
from adcortex.domain.models import Status


def test_new_id_is_sortable_and_valid() -> None:
    earlier = new_analysis_id(datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC))
    later = new_analysis_id(datetime(2026, 1, 1, 12, 0, 1, tzinfo=UTC))

    assert earlier.startswith("20260101-120000-")
    assert earlier < later
    assert is_analysis_id(earlier)


def test_ids_from_the_same_second_sort_by_millisecond() -> None:
    first = new_analysis_id(datetime(2026, 1, 1, 12, 0, 0, 9_000, tzinfo=UTC))
    second = new_analysis_id(datetime(2026, 1, 1, 12, 0, 0, 10_000, tzinfo=UTC))
    last = new_analysis_id(datetime(2026, 1, 1, 12, 0, 0, 999_999, tzinfo=UTC))

    assert first < second < last
    assert all(is_analysis_id(i) for i in (first, second, last))


@pytest.mark.parametrize(
    "value", ["", "../etc/passwd", "20260101-120000-ABCDEF", "20260101-120000-a1b2c3/x"]
)
def test_require_id_rejects_malformed_values_as_not_found(value: str) -> None:
    with pytest.raises(NotFoundError):
        require_analysis_id(value)


def test_require_id_returns_valid_id() -> None:
    assert require_analysis_id("20260101-120000-a1b2c3") == "20260101-120000-a1b2c3"


@pytest.mark.parametrize(
    ("raw", "code"), [(None, "auto"), (" EN ", "en"), ("uk", "uk")]
)
def test_normalize_language(raw: str | None, code: str) -> None:
    assert normalize_language(raw) == code


def test_normalize_language_rejects_unknown_code() -> None:
    with pytest.raises(InvalidInputError, match="Unsupported language"):
        normalize_language("xx")


def test_only_english_is_fully_supported() -> None:
    assert is_fully_supported("en")
    assert not is_fully_supported("de")
    assert not is_fully_supported(None)


def test_terminal_statuses() -> None:
    assert Status.COMPLETED.is_terminal
    assert Status.FAILED.is_terminal
    assert not Status.PREDICTING.is_terminal
