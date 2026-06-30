#!/usr/bin/env python3
"""Backfill Evidence records for documents used by a knowledge-network graph."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "artifacts" / "knowledge-network-evidence-backfill.json"


class ApiClient:
    def __init__(self, base_url: str, *, timeout: float):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def request(self, method: str, path: str, body: dict[str, Any] | None = None, *, role: str = "analyst", actor: str = "knowledge_network_evidence_backfill") -> dict[str, Any]:
        data = json.dumps(body or {}, ensure_ascii=False).encode("utf-8") if body is not None else None
        request = Request(
            f"{self.base_url}{path}",
            data=data,
            method=method,
            headers={"Content-Type": "application/json", "X-Role": role, "X-Actor": actor},
        )
        with urlopen(request, timeout=self.timeout) as response:
            envelope = json.loads(response.read().decode("utf-8"))
        if not envelope.get("success"):
            raise RuntimeError(json.dumps(envelope.get("error", envelope), ensure_ascii=False))
        return envelope["data"]


def graph_query_path(issuer_id: str, security_id: str = "") -> str:
    query = {"issuer_id": issuer_id}
    if security_id:
        query["security_id"] = security_id
    return f"/api/graph/query?{urlencode(query)}"


def readiness_payload(issuer_id: str, security_id: str = "") -> dict[str, Any]:
    payload: dict[str, Any] = {"issuer_id": issuer_id}
    if security_id:
        payload["security_id"] = security_id
    return payload


def run_backfill(
    base_url: str,
    *,
    issuer_id: str,
    security_id: str = "",
    execute: bool = False,
    limit: int = 20,
    timeout: float = 20.0,
) -> dict[str, Any]:
    if not issuer_id:
        raise ValueError("issuer_id is required")
    client = ApiClient(base_url, timeout=timeout)
    before = client.request("POST", "/api/graph/knowledge-network/readiness", readiness_payload(issuer_id, security_id))
    graph = client.request("GET", graph_query_path(issuer_id, security_id))
    documents = [row for row in graph.get("documents", []) if isinstance(row, dict)]
    evidence_document_ids = {str(row.get("document_id", "") or "") for row in graph.get("evidence", []) if isinstance(row, dict)}
    candidates = [
        {
            "document_id": str(row.get("document_id", "") or ""),
            "title": str(row.get("title", "") or ""),
            "document_type": str(row.get("document_type", "") or ""),
            "source_id": str(row.get("source_id", "") or ""),
        }
        for row in documents
        if str(row.get("document_id", "") or "") and str(row.get("document_id", "") or "") not in evidence_document_ids
    ][: max(0, limit)]
    created: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    if execute:
        for candidate in candidates:
            document_id = candidate["document_id"]
            try:
                result = client.request(
                    "POST",
                    "/api/evidence/extract",
                    {
                        "document_id": document_id,
                        "parser_version": "knowledge-network-backfill-v1",
                        "model_version": "rule-knowledge-network-backfill-v1",
                    },
                )
                evidence = [row for row in result.get("evidence", []) if isinstance(row, dict)]
                created.append({"document_id": document_id, "created_count": len(evidence), "evidence_ids": [str(row.get("evidence_id", "")) for row in evidence]})
            except (HTTPError, URLError, TimeoutError, RuntimeError) as exc:
                failed.append({"document_id": document_id, "error": str(exc)})
    after = client.request("POST", "/api/graph/knowledge-network/readiness", readiness_payload(issuer_id, security_id)) if execute else before
    return {
        "schema_id": "knowledge-network-evidence-backfill-v1",
        "status": "executed" if execute and not failed else ("partial" if failed else "dry_run"),
        "execute": execute,
        "issuer_id": issuer_id,
        "security_id": security_id,
        "candidate_count": len(candidates),
        "created_document_count": len(created),
        "created_evidence_count": sum(item["created_count"] for item in created),
        "failed_count": len(failed),
        "candidates": candidates,
        "created": created,
        "failed": failed,
        "readiness_before": before,
        "readiness_after": after,
        "automation_allowed": False,
        "live_execution_allowed": False,
        "usage_boundary": "knowledge_network_evidence_backfill_extracts_local_document_evidence_only_no_broker_no_trade_execution",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url", nargs="?", default="http://127.0.0.1:8000")
    parser.add_argument("--issuer-id", required=True)
    parser.add_argument("--security-id", default="")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args(argv)
    try:
        result = run_backfill(
            args.base_url,
            issuer_id=args.issuer_id,
            security_id=args.security_id,
            execute=args.execute,
            limit=args.limit,
            timeout=args.timeout,
        )
    except (HTTPError, URLError, TimeoutError, RuntimeError, ValueError) as exc:
        print(f"knowledge-network evidence backfill failed: {exc}", file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] in {"dry_run", "executed", "partial"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
