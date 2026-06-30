from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .api import ApiRouter, create_default_router
from .services import SystemService
from .store import PostgreSQLStore, SQLiteStore
from .utils import env_text, to_plain


ROOT_DIR = Path(__file__).resolve().parents[1]


def _load_dotenv(path: Path = ROOT_DIR / ".env") -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or key in os.environ:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ[key] = value

def _validate_startup_security_mode() -> None:
    deployment_mode = str(env_text("AI_QUANT_DEPLOYMENT_MODE", "local") or "local").strip().lower()
    auth_mode = str(env_text("AI_QUANT_AUTH_MODE", "x-role-header") or "x-role-header").strip().lower()
    if deployment_mode in {"preprod", "staging", "production", "nonlocal", "non-local"} and auth_mode in {"x-role-header", "header", "none"}:
        raise RuntimeError(
            "AI_QUANT_DEPLOYMENT_MODE is non-local but AI_QUANT_AUTH_MODE is not production-safe. "
            "Set AI_QUANT_AUTH_MODE to service-token/jwt/oidc before startup."
        )


def _server_port(default: int = 8000) -> int:
    raw_port = str(env_text("AI_QUANT_PORT", str(default)) or str(default)).strip()
    try:
        port = int(raw_port)
    except ValueError as exc:
        raise RuntimeError("AI_QUANT_PORT must be an integer") from exc
    if port < 1 or port > 65535:
        raise RuntimeError("AI_QUANT_PORT must be between 1 and 65535")
    return port


def _create_router() -> ApiRouter:
    _validate_startup_security_mode()
    postgres_dsn = env_text("AI_QUANT_POSTGRES_DSN") or env_text("AI_QUANT_DATABASE_URL")
    if postgres_dsn:
        return ApiRouter(SystemService(PostgreSQLStore(postgres_dsn)))
    db_path = env_text("AI_QUANT_DB")
    if db_path and db_path.startswith(("postgresql://", "postgres://")):
        return ApiRouter(SystemService(PostgreSQLStore(db_path)))
    if db_path:
        return ApiRouter(SystemService(SQLiteStore(db_path)))
    return create_default_router()


ROUTER: ApiRouter | None = None
STATIC_DIR = Path(__file__).resolve().parent / "static"


def get_router() -> ApiRouter:
    global ROUTER
    if ROUTER is None:
        ROUTER = _create_router()
    return ROUTER


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
        if path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return
        if path == "/":
            self._send_json(
                {
                    "service": "company-intelligence-platform",
                    "ui": "/ui",
                    "routes": [
                        "/api/dashboard/ceo",
                        "/api/dashboard/risk",
                        "/api/health",
                        "/api/metrics",
                        "/api/ingestion/sources",
                        "/api/governance/source-reviews",
                        "/api/ingestion/documents",
                        "/api/research/manual-references",
                        "/api/evidence/extract",
                        "/api/document-parsing/paddleocr",
                        "/api/market-data/tdx/preview",
                        "/api/research-reports",
                        "/api/thesis/create",
                    ],
                }
            )
            return
        response = get_router().dispatch("GET", path, self._query_body(parsed_url.query), actor=self._actor(), role=self._role())
        self._send_json(response.to_dict(), response.status_code)

    def do_POST(self) -> None:  # noqa: N802
        body = self._read_json()
        parsed_url = urlparse(self.path)
        response = get_router().dispatch("POST", parsed_url.path, body, actor=self._actor(), role=self._role())
        self._send_json(response.to_dict(), response.status_code)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Serving on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    _load_dotenv()
    get_router()
    serve(host=str(env_text("AI_QUANT_HOST", "127.0.0.1") or "127.0.0.1"), port=_server_port())
