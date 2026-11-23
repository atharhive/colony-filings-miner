"""HTTP surface for the miner: one POST /filings, one GET /health, stdlib only."""

from __future__ import annotations

import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .service import FilingsService

VERSION = "1.0.0"


def make_handler(service: FilingsService) -> type[BaseHTTPRequestHandler]:
    cache: dict[tuple[str, str], tuple[float, dict, str]] = {}
    ttl = 3600.0

    class Handler(BaseHTTPRequestHandler):
        server_version = f"colony-filings/{VERSION}"

        def _json(self, code: int, payload: dict, status: str = "ok") -> None:
            body = json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Miner-Status", status)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            if urlparse(self.path).path == "/health":
                self._json(200, {"ok": True, "service": "colony-filings", "version": VERSION})
                return
            self._json(404, {"error": "not found"}, status="unresolved")

        def do_POST(self) -> None:  # noqa: N802
            if urlparse(self.path).path not in {"/filings", "/"}:
                self._json(404, {"error": "not found"}, status="unresolved")
                return
            length = int(self.headers.get("Content-Length", 0) or 0)
            if length > 8192:
                self._json(413, {"error": "body too large"}, status="unresolved")
                return
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                self._json(400, {"error": "body must be JSON"}, status="unresolved")
                return

            entity = str(body.get("entity", ""))[:256]
            period = str(body.get("period", ""))[:256]
            if not entity:
                self._json(400, {"error": "entity is required"}, status="unresolved")
                return

            key = (entity.lower(), period.lower())
            hit = cache.get(key)
            if hit and time.time() - hit[0] < ttl:
                self._json(200, hit[1], status=hit[2])
                return

            answer = service.answer(entity, period)
            payload = answer.body()
            cache[key] = (time.time(), payload, answer.status)
            self._json(200, payload, status=answer.status)
            if answer.status != "ok":
                self.log_message("unresolved %s / %s: %s", entity, period, answer.note)

    return Handler


def serve(service: FilingsService, host: str = "127.0.0.1", port: int = 8099) -> None:
    httpd = ThreadingHTTPServer((host, port), make_handler(service))
    print(f"colony-filings on http://{host}:{port}  (POST /filings, GET /health)")
    httpd.serve_forever()


def main() -> int:  # pragma: no cover
    import argparse

    ap = argparse.ArgumentParser(prog="colony-filings")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8099)
    ap.add_argument("--cache-dir", default=".cache")
    args = ap.parse_args()
    serve(FilingsService(Path(args.cache_dir)), args.host, args.port)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
