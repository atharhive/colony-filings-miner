"""Parse the many ways a caller says "which filings, over what window".

The intent takes a free-text period, e.g. "last 12 months". Every variant that this
module cannot parse is a reason to answer "unresolved" rather than to guess a window
and return a confident count for the wrong dates.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta


class UnparsedPeriod(ValueError):
    pass


@dataclass(frozen=True)
class Window:
    start: date
    end: date
    label: str

    def contains(self, value: str) -> bool:
        try:
            d = date.fromisoformat(value[:10])
        except ValueError:
            return False
        return self.start <= d <= self.end


_REL = re.compile(r"^(?:last|past|previous)\s+(\d{1,3})\s*(day|days|week|weeks|month|months|year|years)$")
_YEAR = re.compile(r"^(?:fy\s*)?((?:19|20)\d{2})$")
_SINCE = re.compile(r"^(?:since|from)\s+((?:19|20)\d{2}-\d{2}-\d{2})$")
_RANGE = re.compile(r"^((?:19|20)\d{2}-\d{2}-\d{2})\s*(?:to|until|through|-)\s*((?:19|20)\d{2}-\d{2}-\d{2})$")


def parse(period: str, today: date | None = None) -> Window:
    raw = (period or "").strip().lower()
    raw = re.sub(r"\s+", " ", raw)
    today = today or date.today()

    if not raw:
        raise UnparsedPeriod("empty period")

    if m := _REL.match(raw):
        n, unit = int(m.group(1)), m.group(2).rstrip("s")
        if unit == "day":
            start = today - timedelta(days=n)
        elif unit == "week":
            start = today - timedelta(weeks=n)
        elif unit == "month":
            start = _shift_months(today, -n)
        else:
            start = _shift_months(today, -12 * n)
        return Window(start=start, end=today, label=f"last {n} {unit}{'' if n == 1 else 's'}")

    if m := _YEAR.match(raw):
        year = int(m.group(1))
        return Window(start=date(year, 1, 1), end=date(year, 12, 31), label=str(year))

    if m := _SINCE.match(raw):
        start = date.fromisoformat(m.group(1))
        if start > today:
            raise UnparsedPeriod("period starts in the future")
        return Window(start=start, end=today, label=f"since {start.isoformat()}")

    if m := _RANGE.match(raw):
        start = date.fromisoformat(m.group(1))
        end = date.fromisoformat(m.group(2))
        if end < start:
            raise UnparsedPeriod("range ends before it starts")
        return Window(start=start, end=end, label=f"{start.isoformat()}..{end.isoformat()}")

    raise UnparsedPeriod(f"unrecognised period: {period!r}")


def _shift_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
                          31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    return date(year, month, day)
