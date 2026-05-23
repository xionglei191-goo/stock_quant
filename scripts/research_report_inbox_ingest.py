from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen


DEFAULT_HOST_ROOT = os.getenv(
    "AI_QUANT_RESEARCH_REPORT_INBOX",
    str(Path(os.getenv("AI_QUANT_HOST_RESEARCH_REPORT_ROOT", "/home/xionglei/文档/6大投行研报汇总")) / "inbox"),
)
DEFAULT_API_ROOT = os.getenv("AI_QUANT_RESEARCH_REPORT_INBOX_API_ROOT", "/data/local/research_reports/inbox")
DEFAULT_OUTPUT = Path("artifacts/research-report-inbox-ingest.json")


class ApiClient:
    def __init__(self, base_url: str, *, timeout: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        data = json.dumps(body or {}).encode("utf-8") if body is not None else None
        request = Request(
            f"{self.base_url}{path}",
            data=data,
            method=method,
            headers={"Content-Type": "application/json", "X-Role": "data_engineer", "X-Actor": "research_report_inbox_ingest"},
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raw = exc.read().decode("utf-8")
            payload = json.loads(raw) if raw else {"success": False, "error": {"message": str(exc)}}
        if not payload.get("success"):
            raise RuntimeError(f"{method} {path} failed: {payload}")
        return payload["data"]


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_inbox_ingest(
    *,
    base_url: str,
    root_path: str,
    api_root_path: str | None = None,
    output: Path,
    extensions: list[str],
    batch_size: int,
    scan_limit: int,
    ocr_budget_mb: float,
    citation_char_limit: int,
    execute: bool,
    dry_run: bool,
    timeout: float,
) -> dict[str, Any]:
    host_root = Path(root_path).expanduser()
    host_root.mkdir(parents=True, exist_ok=True)
    scan_root = api_root_path or str(host_root)
    client = ApiClient(base_url, timeout=timeout)
    payload = {
        "root_path": scan_root,
        "extensions": extensions,
        "batch_size": batch_size,
        "scan_limit": scan_limit,
        "ocr_budget_mb": ocr_budget_mb,
        "citation_char_limit": citation_char_limit,
        "dry_run": dry_run,
        "execute": execute,
        "per_broker_sources": True,
        "parser_version": "research-report-inbox-v1",
    }
    schedule = client.request("POST", "/api/research-reports/incremental-schedule", payload)
    queue: dict[str, Any] = {}
    if execute:
        queue = client.request(
            "POST",
            "/api/research-reports/extraction-queue",
            {
                "execute": False,
                "limit": min(max(batch_size, 1), 100),
                "citation_char_limit": citation_char_limit,
                "parser_version": "research-report-inbox-v1",
            },
        )
    summary = {
        "generated_at": utc_iso(),
        "base_url": base_url,
        "host_root_path": str(host_root),
        "api_root_path": scan_root,
        "dry_run": dry_run,
        "execute": execute,
        "status": "passed",
        "new_count": schedule.get("new_count", 0),
        "changed_count": schedule.get("changed_count", 0),
        "skipped_count": schedule.get("skipped_count", 0),
        "deferred_count": schedule.get("deferred_count", 0),
        "batch_count": schedule.get("batch_count", 0),
        "executed_count": len(schedule.get("executed_results") or []),
        "manual_review_count": sum(1 for row in schedule.get("executed_results") or [] if row.get("manual_review")),
        "failed_count": sum(1 for row in schedule.get("executed_results") or [] if row.get("status") == "failed"),
        "schedule": schedule,
        "post_execute_queue": queue,
        "usage_boundary": "local_research_report_inbox_only_no_external_download_no_training_no_fact_source",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan a local research-report inbox and optionally execute the first extraction batch.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--root-path", default=DEFAULT_HOST_ROOT, help="Host filesystem inbox path where new reports are placed.")
    parser.add_argument("--api-root-path", default=DEFAULT_API_ROOT, help="Path visible to the running API service; defaults to the docker mounted inbox path.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--extensions", default=".pdf,.txt,.md")
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--scan-limit", type=int, default=1000)
    parser.add_argument("--ocr-budget-mb", type=float, default=200.0)
    parser.add_argument("--citation-char-limit", type=int, default=1200)
    parser.add_argument("--execute", action="store_true", help="Register and extract the first batch. Default is dry-run planning only.")
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()
    extensions = [item.strip() for item in args.extensions.split(",") if item.strip()]
    summary = run_inbox_ingest(
        base_url=args.base_url,
        root_path=args.root_path,
        api_root_path=args.api_root_path,
        output=args.output,
        extensions=extensions,
        batch_size=args.batch_size,
        scan_limit=args.scan_limit,
        ocr_budget_mb=args.ocr_budget_mb,
        citation_char_limit=args.citation_char_limit,
        execute=args.execute,
        dry_run=not args.execute,
        timeout=args.timeout,
    )
    return 0 if summary["failed_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
