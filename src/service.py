"""The answer rule: a count when we could look, "unresolved" when we could not.

The dangerous failure for a filing miner is not an error, it is a confident zero. Zero
means "we searched the right window and found nothing"; unresolved means "we could not
search", and the two must never be confused.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from . import edgar, period


@dataclass
class Answer:
    entity: str
    filing_count: int
    filings: list[str] = field(default_factory=list)
    urls: list[str] = field(default_factory=list)
    status: str = "ok"
    window: str = ""
    source: str = ""
    note: str = ""

    def body(self) -> dict:
        return {
            "entity": self.entity,
            "filing_count": self.filing_count,
            "filings": self.filings,
            "urls": self.urls,
        }

    def as_dict(self) -> dict:
        payload = self.body()
        payload.update({"status": self.status, "window": self.window, "source": self.source, "note": self.note})
        return payload


class FilingsService:
    def __init__(self, cache_dir: Path, fetch=edgar._fetch, today: date | None = None):
        self.tickers = edgar.Tickers(cache_dir / "company_tickers.json", fetch=fetch)
        self.fetch = fetch
        self.today = today

    def answer(self, entity: str, period_text: str) -> Answer:
        entity = (entity or "").strip()
        if not entity:
            return Answer(entity="", filing_count=0, status="unresolved", note="entity is empty")

        try:
            window = period.parse(period_text, today=self.today)
        except period.UnparsedPeriod as exc:
            return Answer(entity=entity, filing_count=0, status="unresolved", note=str(exc))

        start, end = window.start.isoformat(), window.end.isoformat()

        try:
            issuer = self.tickers.resolve(entity)
        except edgar.UpstreamError as exc:
            return Answer(entity=entity, filing_count=0, status="unresolved", window=window.label, note=str(exc))

        if issuer:
            try:
                count, rows = edgar.submissions(issuer["cik"], start, end, fetch=self.fetch)
            except edgar.UpstreamError as exc:
                return Answer(entity=entity, filing_count=0, status="unresolved", window=window.label,
                              source="sec-edgar-submissions", note=str(exc))
            return Answer(
                entity=issuer["title"],
                filing_count=count,
                filings=[f"{f.form} · {f.filed} · {f.title}" for f in rows],
                urls=[f.url for f in rows if f.url],
                status="ok",
                window=window.label,
                source="sec-edgar-submissions",
                note=f"CIK {issuer['cik']}",
            )

        # No CIK means the entity does not file with the SEC as a registrant. Full-text
        # hits are mentions in other companies' filings, not that company's filings, so
        # they are reported and deliberately not counted.
        try:
            total, rows = edgar.fulltext(entity, start, end, fetch=self.fetch)
        except edgar.UpstreamError as exc:
            return Answer(entity=entity, filing_count=0, status="unresolved", window=window.label,
                          source="sec-edgar-fulltext", note=str(exc))
        return Answer(
            entity=entity,
            filing_count=0,
            filings=[f"{f.form} · {f.filed} · {f.title}" for f in rows],
            urls=[f.url for f in rows if f.url],
            status="unresolved",
            window=window.label,
            source="sec-edgar-fulltext",
            note=f"no SEC-registered issuer matched; {total} full-text mentions, not counted as filings",
        )
