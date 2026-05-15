from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .api import ApiRouter, create_default_router
from .services import SystemService
from .store import PostgreSQLStore, SQLiteStore
from .utils import to_plain


def _create_router() -> ApiRouter:
    postgres_dsn = os.environ.get("AI_QUANT_POSTGRES_DSN") or os.environ.get("AI_QUANT_DATABASE_URL")
    if postgres_dsn:
        return ApiRouter(SystemService(PostgreSQLStore(postgres_dsn)))
    db_path = os.environ.get("AI_QUANT_DB")
    if db_path and db_path.startswith(("postgresql://", "postgres://")):
        return ApiRouter(SystemService(PostgreSQLStore(db_path)))
    if db_path:
        return ApiRouter(SystemService(SQLiteStore(db_path)))
    return create_default_router()


ROUTER = _create_router()
STATIC_DIR = Path(__file__).resolve().parent / "static"


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, payload: dict, status: int = 200) -> None:
        data = json.dumps(to_plain(payload), ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_html(self, filename: str) -> None:
        path = STATIC_DIR / filename
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self) -> dict:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(content_length) if content_length else b"{}"
        return json.loads(raw.decode("utf-8")) if raw else {}

    def _actor(self) -> str:
        return self.headers.get("X-Actor", "system")

    def _role(self) -> str:
        return self.headers.get("X-Role", "system")

    def _query_body(self, query: str) -> dict:
        parsed = parse_qs(query, keep_blank_values=True)
        return {key: values if len(values) > 1 else values[0] for key, values in parsed.items()}

    def do_GET(self) -> None:  # noqa: N802
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        if path in {"/ui", "/ui/"}:
            self._send_html("index.html")
            return
        if path == "/":
            self._send_json(
                {
                    "service": "ai-native-quant-org",
                    "ui": "/ui",
                    "routes": [
                        "/api/dashboard/ceo",
                        "/api/dashboard/risk",
                        "/api/health",
                        "/api/metrics",
                        "/api/ingestion/sources",
                        "/api/ingestion/documents",
                        "/api/evidence/extract",
                        "/api/document-parsing/paddleocr",
                        "/api/market-data/tdx/preview",
                        "/api/research-reports",
                        "/api/thesis/create",
                    ],
                }
            )
            return
        response = ROUTER.dispatch("GET", path, self._query_body(parsed_url.query), actor=self._actor(), role=self._role())
        self._send_json(response.to_dict(), response.status_code)

    def do_POST(self) -> None:  # noqa: N802
        body = self._read_json()
        parsed_url = urlparse(self.path)
        response = ROUTER.dispatch("POST", parsed_url.path, body, actor=self._actor(), role=self._role())
        self._send_json(response.to_dict(), response.status_code)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Serving on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    serve()
