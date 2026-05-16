from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
from pathlib import Path
import threading
from typing import Any


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class SinkStore:
    name: str
    log_path: Path | None = None
    records: list[dict[str, Any]] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def append(self, record: dict[str, Any]) -> int:
        with self._lock:
            self.records.append(record)
            count = len(self.records)
            if self.log_path is not None:
                self.log_path.parent.mkdir(parents=True, exist_ok=True)
                with self.log_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            return count

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self.records)


def make_handler(store: SinkStore) -> type[BaseHTTPRequestHandler]:
    class LocalHttpSinkHandler(BaseHTTPRequestHandler):
        server_version = "ai-quant-local-http-sink/1.0"

        def _write_json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
            records = store.snapshot()
            if self.path.rstrip("/") in {"", "/health", "/readyz"}:
                self._write_json(200, {"ok": True, "service": store.name, "request_count": len(records)})
                return
            if self.path.startswith("/requests"):
                self._write_json(200, {"service": store.name, "request_count": len(records), "requests": records[-100:]})
                return
            self._write_json(404, {"ok": False, "service": store.name, "error": "not_found"})

        def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0") or 0))
            try:
                parsed_body: Any = json.loads(raw.decode("utf-8")) if raw else None
            except json.JSONDecodeError:
                parsed_body = raw.decode("utf-8", errors="replace")
            record = {
                "service": store.name,
                "path": self.path,
                "method": self.command,
                "received_at": _utcnow(),
                "content_type": self.headers.get("Content-Type", ""),
                "body_sha256": hashlib.sha256(raw).hexdigest(),
                "body_size": len(raw),
                "body": parsed_body,
            }
            count = store.append(record)
            self._write_json(
                202,
                {
                    "received": True,
                    "service": store.name,
                    "path": self.path,
                    "body_sha256": record["body_sha256"],
                    "request_count": count,
                },
            )

        def log_message(self, _format: str, *_args: Any) -> None:
            return

    return LocalHttpSinkHandler


def serve(*, host: str, port: int, name: str, log_path: Path | None = None) -> None:
    store = SinkStore(name=name, log_path=log_path)
    server = ThreadingHTTPServer((host, port), make_handler(store))
    print(json.dumps({"service": name, "host": host, "port": port, "log_path": str(log_path or "")}, sort_keys=True), flush=True)
    server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a local HTTP POST sink for staging webhook acceptance.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--name", default="local-http-sink")
    parser.add_argument("--log", default="")
    args = parser.parse_args()
    serve(host=args.host, port=args.port, name=args.name, log_path=Path(args.log) if args.log else None)


if __name__ == "__main__":
    main()
