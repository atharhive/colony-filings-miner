"""SEC EDGAR client: resolve a company, then count its filings in a window.

Three public endpoints, no key:
  company_tickers.json   ticker and canonical name per CIK, refreshed daily
  submissions/CIK*.json  the filings index for one issuer
  LATEST/search-index    full-text search, used when no issuer resolves

Every call has its own timeout and every failure is raised, not swallowed, so the
service can decide between "zero filings" and "we could not look".
"""

from __future__ import annotations

import gzip
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

USER_AGENT = "Colony Filings Miner contact@atharlogs.com"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{document}"

SUFFIXES = {
    "inc", "incorporated", "corp", "corporation", "co", "company", "ltd", "limited",
    "plc", "llc", "lp", "llp", "ag", "sa", "nv", "bv", "gmbh", "as", "asa", "ab",
    "oyj", "spa", "srl", "holdings", "holding", "group", "the",
}


class UpstreamError(RuntimeError):
    """The source did not answer, or answered with something we cannot use."""


@dataclass
class Filing:
    form: str
    filed: str
    title: str
    url: str


def _fetch(url: str, timeout: float = 20.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            if resp.headers.get("Content-Encoding") == "gzip":
                body = gzip.decompress(body)
            return body
    except urllib.error.HTTPError as exc:
        raise UpstreamError(f"HTTP {exc.code} from {urllib.parse.urlparse(url).netloc}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise UpstreamError(f"{type(exc).__name__} from {urllib.parse.urlparse(url).netloc}") from exc


def normalise(name: str) -> str:
    cleaned = re.sub(r"[^a-z0-9 ]", " ", name.lower())
    tokens = [t for t in cleaned.split() if t and t not in SUFFIXES]
    return " ".join(tokens)


class Tickers:
    """CIK lookup with a day-long on-disk cache, so the miner is one request per day."""

    def __init__(self, cache_path: Path, ttl_seconds: int = 86_400, fetch=_fetch):
        self.cache_path = cache_path
        self.ttl = ttl_seconds
        self.fetch = fetch
        self._rows: list[dict] | None = None

    def rows(self) -> list[dict]:
        if self._rows is not None:
            return self._rows
        fresh = self.cache_path.exists() and (time.time() - self.cache_path.stat().st_mtime) < self.ttl
        if fresh:
            data = json.loads(self.cache_path.read_text())
        else:
            payload = self.fetch(TICKERS_URL)
            data = json.loads(payload)
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(json.dumps(data))
        self._rows = [{"cik": int(row["cik_str"]), "ticker": row["ticker"], "title": row["title"]}
                      for row in data.values()]
        return self._rows

    def resolve(self, entity: str) -> dict | None:
        """Exact normalised match first, then containment, then token overlap."""
        want = normalise(entity)
        if not want:
            return None
        rows = self.rows()

        for row in rows:
            if normalise(row["title"]) == want:
                return row

        shorter = want.replace(" ", "")
        for row in rows:
            title = normalise(row["title"])
            if shorter and (shorter in title.replace(" ", "") or title.replace(" ", "") in shorter):
                return row

        want_tokens = set(want.split())
        best, best_score = None, 0.0
        for row in rows:
            title_tokens = set(normalise(row["title"]).split())
            if not title_tokens:
                continue
            overlap = len(want_tokens & title_tokens) / len(want_tokens | title_tokens)
            if overlap > best_score:
                best, best_score = row, overlap
        return best if best_score >= 0.6 else None


def submissions(cik: int, start: str, end: str, limit: int = 50, fetch=_fetch) -> tuple[int, list[Filing]]:
    """Return (count in window, newest `limit` filings).

    The count must be the whole window: filing_count is the scored field, and a count
    silently capped at the listing limit would report a wrong number to the node.
    """
    payload = json.loads(fetch(SUBMISSIONS_URL.format(cik=cik)))
    recent = payload.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    docs = recent.get("primaryDocument", [])
    accs = recent.get("accessionNumber", [])
    descs = recent.get("primaryDocDescription", [])

    out: list[Filing] = []
    matched = 0
    for i, filed in enumerate(dates):
        if not (start <= filed <= end):
            continue
        matched += 1
        form = forms[i] if i < len(forms) else ""
        document = docs[i] if i < len(docs) else ""
        accession = (accs[i] if i < len(accs) else "").replace("-", "")
        title = descs[i] if i < len(descs) and descs[i] else f"{form} filed {filed}"
        url = ARCHIVE_URL.format(cik=cik, accession=accession, document=document) if document else ""
        if len(out) < limit:
            out.append(Filing(form=form, filed=filed, title=title, url=url))
    return matched, out


def fulltext(entity: str, start: str, end: str, limit: int = 25, fetch=_fetch) -> tuple[int, list[Filing]]:
    """Fallback for entities with no CIK: count full-text hits in the window."""
    query = urllib.parse.urlencode({
        "q": f'"{entity}"',
        "startdt": start,
        "enddt": end,
        "forms": "10-K,10-Q,8-K,20-F,6-K",
    })
    payload = json.loads(fetch(f"{SEARCH_URL}?{query}"))
    total = int(payload.get("hits", {}).get("total", {}).get("value", 0))
    filings: list[Filing] = []
    for hit in payload.get("hits", {}).get("hits", [])[:limit]:
        src = hit.get("_source", {})
        acc = (src.get("adsh") or "").replace("-", "")
        cik = int(src.get("ciks", ["0"])[0]) if src.get("ciks") else 0
        doc = (src.get("file_date", "") and src.get("file_type", "")) and src.get("file_type", "")
        url = ARCHIVE_URL.format(cik=cik, accession=acc, document="") if acc and cik else ""
        filings.append(Filing(
            form=src.get("file_type", ""),
            filed=src.get("file_date", ""),
            title=src.get("display_names", [entity])[0] if src.get("display_names") else entity,
            url=url,
        ))
    return total, filings
