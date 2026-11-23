"""Server tests: the HTTP contract the node will actually call."""

from __future__ import annotations

import json
import sys
import threading
import urllib.error
import urllib.request
from datetime import date
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import edgar  # noqa: E402
from src.server import make_handler  # noqa: E402
from src.service import FilingsService  # noqa: E402

TODAY = date(2026, 11, 24)
TICKERS = {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}}
SUBMISSIONS = {"filings": {"recent": {"form": ["10-K"], "filingDate": ["2026-10-30"],
                                      "primaryDocument": ["a.htm"],
                                      "accessionNumber": ["0000320193-26-000001"],
                                      "primaryDocDescription": ["Annual report"]}}}


def fetch(url: str, timeout: float = 20.0):
    if "company_tickers" in url:
        return json.dumps(TICKERS).encode()
    if "submissions" in url:
        return json.dumps(SUBMISSIONS).encode()
    if "search-index" in url:
        return json.dumps({"hits": {"total": {"value": 0}, "hits": []}}).encode()
    raise edgar.UpstreamError("unexpected upstream")


def start(tmp_path):
    service = FilingsService(tmp_path, fetch=fetch, today=TODAY)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(service))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


def post(base, path, body):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, json.loads(r.read()), dict(r.headers)


def test_health(tmp_path):
    httpd, base = start(tmp_path)
    try:
        with urllib.request.urlopen(base + "/health", timeout=10) as r:
            assert json.loads(r.read())["service"] == "colony-filings"
    finally:
        httpd.shutdown()


def test_filings_returns_the_declared_body_and_an_ok_status(tmp_path):
    httpd, base = start(tmp_path)
    try:
        code, body, headers = post(base, "/filings", {"entity": "Apple", "period": "last 12 months"})
        assert code == 200
        assert set(body) == {"entity", "filing_count", "filings", "urls"}
        assert body["filing_count"] == 1
        assert headers["X-Miner-Status"] == "ok"
    finally:
        httpd.shutdown()


def test_missing_entity_is_a_400_not_a_fake_zero(tmp_path):
    httpd, base = start(tmp_path)
    try:
        try:
            post(base, "/filings", {"period": "last 12 months"})
            assert False, "should have been refused"
        except urllib.error.HTTPError as exc:
            assert exc.code == 400
    finally:
        httpd.shutdown()


def test_repeat_questions_are_served_from_cache(tmp_path):
    calls = {"n": 0}

    def counting(url: str, timeout: float = 20.0):
        calls["n"] += 1
        return fetch(url)

    service = FilingsService(tmp_path, fetch=counting, today=TODAY)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(service))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        post(base, "/filings", {"entity": "Apple", "period": "last 12 months"})
        first = calls["n"]
        post(base, "/filings", {"entity": "Apple", "period": "last 12 months"})
        assert calls["n"] == first
    finally:
        httpd.shutdown()
