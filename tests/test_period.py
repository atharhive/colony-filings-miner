"""Period parsing tests: every accepted phrasing, and the refusals."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from src.period import UnparsedPeriod, parse  # noqa: E402

TODAY = date(2026, 11, 24)


def test_last_twelve_months_is_the_default_shape():
    w = parse("last 12 months", today=TODAY)
    assert (w.start, w.end) == (date(2025, 11, 24), TODAY)


def test_last_six_months_clamps_the_day():
    w = parse("last 6 months", today=date(2026, 8, 31))
    assert w.start == date(2026, 2, 28)


def test_last_90_days():
    assert parse("past 90 days", today=TODAY).start == date(2026, 8, 26)


def test_lastyear_and_fiscal_year_forms():
    w = parse("FY2025", today=TODAY)
    assert (w.start, w.end) == (date(2025, 1, 1), date(2025, 12, 31))


def test_since_and_ranges():
    assert parse("since 2024-01-01", today=TODAY).start == date(2024, 1, 1)
    w = parse("2024-01-01 to 2024-12-31", today=TODAY)
    assert (w.start, w.end) == (date(2024, 1, 1), date(2024, 12, 31))


def test_window_contains_only_its_dates():
    w = parse("2025", today=TODAY)
    assert w.contains("2025-06-01")
    assert not w.contains("2026-01-01")
    assert not w.contains("not-a-date")


@pytest.mark.parametrize("bad", ["", "recently", "last fortnight", "since tomorrow", "2025-12-31 to 2025-01-01"])
def test_unparseable_periods_raise_instead_of_guessing(bad):
    with pytest.raises(UnparsedPeriod):
        parse(bad, today=TODAY)
