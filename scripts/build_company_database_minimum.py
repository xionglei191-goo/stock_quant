from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen


DEFAULT_OUTPUT = Path("artifacts/company-database-build.json")


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def request_json(base_url: str, path: str, body: dict[str, Any], *, timeout: float) -> dict[str, Any]:
    request = Request(
        f"{base_url.rstrip('/')}{path}",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json", "X-Role": "data_engineer", "X-Actor": "company_database_builder"},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raw = exc.read().decode("utf-8")
        payload = json.loads(raw) if raw else {"success": False, "error": {"message": str(exc)}}
    if not payload.get("success"):
        raise RuntimeError(f"POST {path} failed: {payload}")
    return payload["data"]


def run(
    *,
    base_url: str,
    symbols: list[str],
    issuer_ids: list[str],
    limit: int,
    report_match_limit: int,
    structure_reports: bool,
    structure_report_limit: int,
    build_events: bool,
    event_limit: int,
    build_relationships: bool,
    relationship_limit: int,
    build_workflow: bool,
    workflow_link_limit: int,
    execute: bool,
    output: Path,
    timeout: float,
) -> dict[str, Any]:
    body = {
        "symbols": symbols,
        "issuer_ids": issuer_ids,
        "limit": limit,
        "report_match_limit": report_match_limit,
        "structure_reports": structure_reports,
        "structure_report_limit": structure_report_limit,
        "execute": execute,
        "dry_run": not execute,
    }
    result = request_json(base_url, "/api/company-database/build", body, timeout=timeout)
    events_result: dict[str, Any] = {}
    if build_events:
        events_result = request_json(
            base_url,
            "/api/company-database/events/build",
            {
                "symbols": symbols,
                "issuer_ids": issuer_ids,
                "limit": limit,
                "event_limit": event_limit,
                "execute": execute,
                "dry_run": not execute,
                "include_market_data": True,
                "include_research_coverage": True,
            },
            timeout=timeout,
        )
    relationships_result: dict[str, Any] = {}
    if build_relationships:
        relationships_result = request_json(
            base_url,
            "/api/company-database/relationships/build",
            {
                "symbols": symbols,
                "issuer_ids": issuer_ids,
                "limit": limit,
                "relationship_limit": relationship_limit,
                "execute": execute,
                "dry_run": not execute,
                "include_listings": True,
                "include_institution_coverage": True,
            },
            timeout=timeout,
        )
    workflow_result: dict[str, Any] = {}
    if build_workflow:
        workflow_result = request_json(
            base_url,
            "/api/company-database/workflow/build",
            {
                "symbols": symbols,
                "issuer_ids": issuer_ids,
                "limit": limit,
                "link_limit": workflow_link_limit,
                "execute": execute,
                "dry_run": not execute,
                "include_observations": True,
                "include_conclusions": True,
                "include_feedback": True,
            },
            timeout=timeout,
        )
    summary = {
        "generated_at": utc_iso(),
        "base_url": base_url,
        "execute": execute,
        "status": "passed",
        "target_count": result.get("target_count", 0),
        "profiles_saved": result.get("profiles_saved", 0),
        "profiles_planned": result.get("profiles_planned", 0),
        "research_reports_matched": result.get("research_reports_matched", 0),
        "research_reports_bound": result.get("research_reports_bound", 0),
        "structure_reports": structure_reports,
        "result": result,
        "build_events": build_events,
        "events_result": events_result,
        "build_relationships": build_relationships,
        "relationships_result": relationships_result,
        "build_workflow": build_workflow,
        "workflow_result": workflow_result,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return summary


def parse_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the minimum company intelligence database from existing local records.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--symbols", default="AAPL,NVDA,600519,300750,600887")
    parser.add_argument("--issuer-ids", default="")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--report-match-limit", type=int, default=100)
    parser.add_argument("--structure-reports", action="store_true")
    parser.add_argument("--structure-report-limit", type=int, default=20)
    parser.add_argument("--build-events", action="store_true", help="Also build minimum company event timelines from existing market data and research coverage.")
    parser.add_argument("--event-limit", type=int, default=100)
    parser.add_argument("--build-relationships", action="store_true", help="Also build minimum company relationships from listings and research coverage.")
    parser.add_argument("--relationship-limit", type=int, default=100)
    parser.add_argument("--build-workflow", action="store_true", help="Also build observation items, baseline conclusions, and paper-only simulation feedback.")
    parser.add_argument("--workflow-link-limit", type=int, default=5)
    parser.add_argument("--execute", action="store_true", help="Persist company profiles and report bindings. Omit for dry-run.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()
    summary = run(
        base_url=args.base_url,
        symbols=parse_csv(args.symbols),
        issuer_ids=parse_csv(args.issuer_ids),
        limit=args.limit,
        report_match_limit=args.report_match_limit,
        structure_reports=args.structure_reports,
        structure_report_limit=args.structure_report_limit,
        build_events=args.build_events,
        event_limit=args.event_limit,
        build_relationships=args.build_relationships,
        relationship_limit=args.relationship_limit,
        build_workflow=args.build_workflow,
        workflow_link_limit=args.workflow_link_limit,
        execute=args.execute,
        output=args.output,
        timeout=args.timeout,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
