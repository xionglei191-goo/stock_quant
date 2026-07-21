from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen


DEFAULT_SYMBOLS = "AAPL,NVDA,MSFT,300750,600519"
DEFAULT_OUTPUT = Path("artifacts/personal-intelligence/latest.json")


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_csv(value: str) -> list[str]:
    return [item.strip().upper() for item in value.split(",") if item.strip()]


def request_json(
    base_url: str,
    path: str,
    body: dict[str, Any] | None = None,
    *,
    method: str = "POST",
    role: str = "analyst",
    timeout: float = 120.0,
) -> dict[str, Any]:
    data = json.dumps(body or {}, ensure_ascii=False).encode("utf-8") if method != "GET" else None
    request = Request(
        f"{base_url.rstrip('/')}{path}",
        data=data,
        method=method,
        headers={
            "Content-Type": "application/json",
            "X-Role": role,
            "X-Actor": "personal_intelligence_refresh",
            "X-Client-Origin": "scheduled",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raw = exc.read().decode("utf-8")
        payload = json.loads(raw) if raw else {"success": False, "error": {"message": str(exc)}}
    if not payload.get("success"):
        raise RuntimeError(f"{method} {path} failed: {payload}")
    return payload.get("data") or {}


def summary_from_coverage(symbol: str, row: dict[str, Any]) -> dict[str, Any]:
    counts = row.get("counts") or {}
    missing = row.get("missing_sections") or []
    next_action = "继续日更观察"
    if missing:
        first = str(missing[0])
        action_by_section = {
            "financial_snapshot": "补充财务摘要或 companyfacts",
            "documents": "补充官方/IR 材料 inbox",
            "disclosure_events": "接入公告/披露事件",
            "structured_viewpoints": "结构化研报观点",
            "company_events": "生成事件时间线",
            "company_relationships": "生成关系图谱",
            "simulation_feedback": "生成 paper-only 反馈",
        }
        next_action = action_by_section.get(first, f"补齐 {first}")
    return {
        "symbol": symbol,
        "status": "available",
        "issuer_id": row.get("issuer_id") or "",
        "security_id": "",
        "completeness_status": row.get("coverage_level") or "",
        "completeness_score": row.get("coverage_score"),
        "missing_layers": missing,
        "next_action": {"label": next_action},
        "counts": {
            "company_profiles": 1 if row.get("section_available", {}).get("company_profile") else 0,
            "company_events": counts.get("company_events") or 0,
            "company_relationships": counts.get("company_relationships") or 0,
            "structured_research_reports": counts.get("structured_research_reports") or 0,
            "report_viewpoints": counts.get("report_viewpoints") or 0,
            "observation_items": counts.get("observation_items") or 0,
            "analysis_conclusions": counts.get("analysis_conclusions") or 0,
            "simulation_feedback_records": counts.get("simulation_feedback") or counts.get("simulation_feedback_records") or 0,
        },
    }


def run(
    *,
    base_url: str,
    symbols: list[str],
    execute: bool,
    batch_size: int,
    report_match_limit: int,
    structure_report_limit: int,
    timeout: float,
    output: Path,
) -> dict[str, Any]:
    started_at = utc_iso()
    steps: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    body = {
        "symbols": symbols,
        "limit": len(symbols),
        "batch_size": batch_size,
        "report_match_limit": report_match_limit,
        "structure_reports": True,
        "structure_report_limit": structure_report_limit,
        "build_events": True,
        "build_relationships": True,
        "build_workflow": True,
        "include_market_data": True,
        "include_research_coverage": True,
        "include_disclosures": True,
        "include_structured_disclosures": True,
        "include_disclosure_candidates": True,
        "include_observations": True,
        "include_conclusions": True,
        "include_feedback": True,
        "execute": execute,
        "dry_run": not execute,
        "record_run": True,
    }
    try:
        batch = request_json(base_url, "/api/company-database/batch/build", body, role="data_engineer", timeout=timeout)
        steps.append(
            {
                "name": "company_database_batch_build",
                "status": batch.get("status") or ("executed" if execute else "dry_run"),
                "run_id": batch.get("run_id"),
                "issuer_count": batch.get("issuer_count") or batch.get("target_count") or 0,
                "totals": batch.get("totals") or {},
            }
        )
    except Exception as exc:
        failure = {"name": "company_database_batch_build", "error": str(exc), "error_type": type(exc).__name__}
        failures.append(failure)
        steps.append({"name": "company_database_batch_build", "status": "failed", **failure})

    companies: list[dict[str, Any]] = []
    try:
        coverage = request_json(
            base_url,
            "/api/company-database/coverage/audit",
            {"symbols": symbols, "limit": len(symbols)},
            role="analyst",
            timeout=timeout,
        )
        steps.append(
            {
                "name": "company_database_coverage_audit",
                "status": coverage.get("status") or "unknown",
                "issuer_count": coverage.get("issuer_count") or 0,
                "average_coverage_score": coverage.get("average_coverage_score"),
                "missing_counts": coverage.get("missing_counts") or {},
            }
        )
        rows = coverage.get("companies") or []
        row_by_symbol: dict[str, dict[str, Any]] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            issuer_id = str(row.get("issuer_id") or "").lower()
            display_name = str(row.get("display_name") or "").lower()
            for symbol in symbols:
                if symbol.lower() in {display_name, issuer_id.removeprefix("issuer_")}:
                    row_by_symbol[symbol] = row
        remaining = [row for row in rows if isinstance(row, dict) and row not in row_by_symbol.values()]
        for symbol in symbols:
            row = row_by_symbol.get(symbol)
            if row is None and remaining:
                row = remaining.pop(0)
            if row is None:
                companies.append({"symbol": symbol, "status": "not_found", "missing_layers": ["company_profile"], "next_action": {"label": "建立本地公司主体"}})
            else:
                companies.append(summary_from_coverage(symbol, row))
    except Exception as exc:
        failure = {"name": "company_database_coverage_audit", "error": str(exc), "error_type": type(exc).__name__}
        failures.append(failure)
        steps.append({"name": "company_database_coverage_audit", "status": "failed", **failure})
        for symbol in symbols:
            companies.append({"symbol": symbol, "status": "failed", "error": str(exc)})

    ready_count = sum(1 for item in companies if item.get("status") not in {"failed", "not_found"} and not item.get("missing_layers"))
    company_count = len(companies)
    result = {
        "schema_id": "personal-intelligence-refresh-v1",
        "status": "passed" if not failures else "partial" if companies else "failed",
        "passed": not failures,
        "started_at": started_at,
        "completed_at": utc_iso(),
        "base_url": base_url,
        "execute": execute,
        "watchlist_symbols": symbols,
        "company_count": company_count,
        "ready_count": ready_count,
        "needs_attention_count": max(0, company_count - ready_count),
        "steps": steps,
        "companies": companies,
        "failure_count": len(failures),
        "failures": failures,
        "next_actions": [
            "Add official/IR material manifests for companies with missing fact layers.",
            "Review research viewpoints before treating reports as opinion evidence.",
            "Keep feedback paper-only; no broker connection or automatic order execution is enabled.",
        ],
        "usage_boundary": "personal_watchlist_company_intelligence_refresh_uses_local_records_only_no_live_trading",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh a personal watchlist into company intelligence records.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--symbols", default=DEFAULT_SYMBOLS)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--batch-size", type=int, default=5)
    parser.add_argument("--report-match-limit", type=int, default=100)
    parser.add_argument("--structure-report-limit", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = run(
        base_url=args.base_url,
        symbols=parse_csv(args.symbols),
        execute=args.execute,
        batch_size=args.batch_size,
        report_match_limit=args.report_match_limit,
        structure_report_limit=args.structure_report_limit,
        timeout=args.timeout,
        output=args.output,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.get("status") in {"passed", "partial"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
