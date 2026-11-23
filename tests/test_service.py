"""Service tests: a real zero, a fake zero, and the difference between them."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import edgar  # noqa: E402
from src.service import FilingsService  # noqa: E402

TODAY = date(2026, 11, 24)
TICKERS = {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
           "1": {"cik_str": 789019, "ticker": "MSFT", "title": "Microsoft Corp"}}

SUBMISSIONS = {
    "filings": {
        "recent": {
            "form": ["10-K", "8-K", "10-Q"],
            "filingDate": ["2026-10-30", "2026-09-01", "2026-07-15"],
            "primaryDocument": ["a.htm", "b.htm", "c.htm"],
            "accessionNumber": ["0000320193-26-000001", "0000320193-26-000002", "0000320193-26-000003"],
            "primaryDocDescription": ["Annual report", "Material event", "Quarterly report"],
        }
    }
}


def fetcher(routes: dict[str, bytes | Exception]):
    def _fetch(url: str, timeout: float = 20.0):
        for needle, payload in routes.items():
            if needle in url:
                if isinstance(payload, Exception):
                    raise payload
                return payload
        raise edgar.UpstreamError(f"no route for {url}")

    return _fetch


def service(tmp_path, routes) -> FilingsService:
    return FilingsService(tmp_path, fetch=fetcher(routes), today=TODAY)


def test_counts_only_filings_inside_the_window(tmp_path):
    svc = service(tmp_path, {"company_tickers": json.dumps(TICKERS).encode(),
                             "submissions": json.dumps(SUBMISSIONS).encode()})
    answer = svc.answer("Apple", "last 12 months")
    assert answer.status == "ok"
    assert answer.filing_count == 3
    assert answer.source == "sec-edgar-submissions"
    assert answer.urls[0].startswith("https://www.sec.gov/Archives/")


def test_a_narrow_window_returns_a_real_zero(tmp_path):
    svc = service(tmp_path, {"company_tickers": json.dumps(TICKERS).encode(),
                             "submissions": json.dumps(SUBMISSIONS).encode()})
    answer = svc.answer("Apple", "2020")
    assert answer.status == "ok"
    assert answer.filing_count == 0
    assert answer.filings == []


def test_upstream_failure_is_unresolved_not_zero(tmp_path):
    svc = service(tmp_path, {"company_tickers": json.dumps(TICKERS).encode(),
                             "submissions": edgar.UpstreamError("HTTP 503 from data.sec.gov")})
    answer = svc.answer("Apple", "last 12 months")
    assert answer.status == "unresolved"
    assert "503" in answer.note


def test_unparseable_period_is_unresolved_and_asks_nothing(tmp_path):
    svc = service(tmp_path, {})
    answer = svc.answer("Apple", "recently")
    assert answer.status == "unresolved"
    assert answer.filing_count == 0


def test_unknown_entity_is_unresolved_and_mentions_are_not_counted(tmp_path):
    hits = {"hits": {"total": {"value": 7}, "hits": []}}
    svc = service(tmp_path, {"company_tickers": json.dumps(TICKERS).encode(),
                             "search-index": json.dumps(hits).encode()})
    answer = svc.answer("Zzz Nonexistent Holdings", "last 12 months")
    assert answer.status == "unresolved"
    assert answer.filing_count == 0
    assert "7 full-text mentions" in answer.note
    assert answer.source == "sec-edgar-fulltext"


def test_the_count_is_not_capped_by_the_listing_limit(tmp_path):
    many = {"filings": {"recent": {
        "form": ["8-K"] * 60,
        "filingDate": ["2026-10-01"] * 60,
        "primaryDocument": ["a.htm"] * 60,
        "accessionNumber": [f"0000320193-26-{i:06d}" for i in range(60)],
        "primaryDocDescription": ["event"] * 60,
    }}}
    svc = service(tmp_path, {"company_tickers": json.dumps(TICKERS).encode(),
                             "submissions": json.dumps(many).encode()})
    answer = svc.answer("Apple", "last 12 months")
    assert answer.filing_count == 60
    assert len(answer.urls) == 50


def test_suffix_normalisation_matches_inc_and_corp(tmp_path):
    svc = service(tmp_path, {"company_tickers": json.dumps(TICKERS).encode()})
    rows = svc.tickers.rows()
    assert edgar.normalise("Microsoft Corporation") == "microsoft"
    assert any(r["title"] == "Microsoft Corp" for r in rows)


def test_body_carries_only_the_declared_fields(tmp_path):
    svc = service(tmp_path, {"company_tickers": json.dumps(TICKERS).encode(),
                             "submissions": json.dumps(SUBMISSIONS).encode()})
    body = svc.answer("Apple", "last 12 months").body()
    assert set(body) == {"entity", "filing_count", "filings", "urls"}
    assert isinstance(body["filing_count"], int)
