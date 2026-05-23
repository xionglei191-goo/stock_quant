from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any
from urllib.parse import urlparse, urlunparse
from urllib.error import HTTPError
from urllib.request import Request, urlopen


class ApiClient:
    def __init__(self, base_url: str, *, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def request(self, method: str, path: str, body: dict[str, Any] | None = None, *, role: str = "analyst", actor: str = "evidence_backfill") -> dict[str, Any]:
        data = json.dumps(body or {}).encode("utf-8") if body is not None else None
        request = Request(
            f"{self.base_url}{path}",
            data=data,
            method=method,
            headers={"Content-Type": "application/json", "X-Role": role, "X-Actor": actor},
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raw = exc.read().decode("utf-8")
            payload = json.loads(raw) if raw else {"success": False, "error": {"message": str(exc)}}
        if not payload.get("success"):
            raise AssertionError(f"{method} {path} failed: {payload}")
        return payload["data"]


def _load_document_rows(dsn: str, *, limit: int) -> list[dict[str, Any]]:
    import psycopg

    parsed = urlparse(dsn)
    if parsed.hostname in {"postgres", "127.0.0.1", "localhost"} and parsed.port in {None, 15432}:
        netloc = parsed.netloc.replace("@127.0.0.1:15432", "@postgres:5432").replace("@localhost:15432", "@postgres:5432")
        dsn = urlunparse(parsed._replace(netloc=netloc))
    with psycopg.connect(dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                WITH evidence_docs AS (
                    SELECT DISTINCT payload->>'document_id' AS document_id
                    FROM ai_quant.records
                    WHERE collection = 'evidence'
                )
                SELECT d.payload
                FROM ai_quant.records d
                LEFT JOIN evidence_docs e ON e.document_id = d.payload->>'document_id'
                WHERE d.collection = 'documents'
                  AND e.document_id IS NULL
                ORDER BY d.payload->>'published_at' DESC NULLS LAST, d.item_id
                LIMIT %s
                """,
                (limit,),
            )
            return [payload for (payload,) in cursor.fetchall()]


def run_backfill(base_url: str, *, dsn: str, limit: int, timeout: float) -> dict[str, Any]:
    client = ApiClient(base_url, timeout=timeout)
    documents = _load_document_rows(dsn, limit=limit)
    metrics = client.request("GET", "/api/metrics", role="unknown")
    created: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for document in documents:
        document_id = str(document.get("document_id", "")).strip()
        if not document_id:
            continue
        try:
            result = client.request(
                "POST",
                "/api/evidence/extract",
                {"document_id": document_id, "parser_version": "latest-backfill-v1", "model_version": "rule-latest-backfill-v1"},
                role="analyst",
            )
            created_count = len(result.get("evidence", []))
            created.append({"document_id": document_id, "created_count": created_count})
        except Exception as exc:
            failed.append({"document_id": document_id, "error": str(exc), "document_type": document.get("document_type", ""), "language": document.get("language", "")})
    after_metrics = client.request("GET", "/api/metrics", role="unknown")
    return {
        "status": "passed" if not failed else "partial",
        "documents_seen": len(documents),
        "created_document_count": len(created),
        "created_evidence_count": sum(item["created_count"] for item in created),
        "failed_count": len(failed),
        "created": created,
        "failed": failed,
        "metrics_before": metrics.get("counts", {}),
        "metrics_after": after_metrics.get("counts", {}),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill evidence for recently ingested documents via the local API.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--dsn", default=os.environ.get("AI_QUANT_POSTGRES_DSN") or os.environ.get("AI_QUANT_DATABASE_URL") or "postgresql://ai_quant:ai_quant_dev_password@127.0.0.1:15432/ai_quant")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    result = run_backfill(args.base_url, dsn=args.dsn, limit=args.limit, timeout=args.timeout)
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    if result["status"] not in {"passed", "partial"}:
        sys.exit(1)


if __name__ == "__main__":
    main()
