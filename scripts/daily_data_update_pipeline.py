from __future__ import annotations

import argparse
from datetime import date, datetime, time as datetime_time, timedelta, timezone
import json
from pathlib import Path
import shlex
import subprocess
import sys
import time
from typing import Any, Mapping
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.daily_market_insight import build_daily_market_insight, build_markdown as build_insight_markdown
from scripts.market_data_storage_audit import build_market_data_storage_audit
from scripts.audit_tdx_vipdoc_postgres_coverage import build_report as build_tdx_coverage_report


DEFAULT_DSN = "postgresql://ai_quant:ai_quant_dev_password@127.0.0.1:15432/ai_quant"
DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_OUTPUT = "artifacts/daily-update/daily-update.json"
DEFAULT_SOURCE_A = "public_eod_market_data"
DEFAULT_SOURCE_U = "yahoo_chart_us_eod"
ASHARE_TZ = ZoneInfo("Asia/Shanghai")
US_TZ = ZoneInfo("America/New_York")


def _write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(path: str | Path, text: str) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")


def _run_command(name: str, command: list[str], *, timeout: int, allow_failure: bool = False) -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    result: dict[str, Any] = {
        "name": name,
        "command": " ".join(shlex.quote(part) for part in command),
        "started_at": started.isoformat(),
        "timeout_seconds": timeout,
    }
    try:
        completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=timeout, check=False)
    except Exception as exc:
        result.update(
            {
                "status": "allowed_failure" if allow_failure else "failed",
                "returncode": None,
                "error": str(exc),
                "error_type": type(exc).__name__,
                "elapsed_seconds": round((datetime.now(timezone.utc) - started).total_seconds(), 3),
            }
        )
        if not allow_failure:
            result["blocking"] = True
        return result

    status = "passed" if completed.returncode == 0 else "allowed_failure" if allow_failure else "failed"
    result.update(
        {
            "status": status,
            "returncode": completed.returncode,
            "stdout_tail": completed.stdout[-8000:],
            "stderr_tail": completed.stderr[-8000:],
            "elapsed_seconds": round((datetime.now(timezone.utc) - started).total_seconds(), 3),
        }
    )
    if completed.returncode != 0 and not allow_failure:
        result["blocking"] = True
    return result


def _fetch_json(base_url: str, path: str, *, method: str = "GET", body: dict[str, Any] | None = None, role: str = "system", timeout: float = 15.0) -> dict[str, Any]:
    data = json.dumps(body or {}).encode("utf-8") if body is not None else None
    request = Request(
        base_url.rstrip("/") + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", "X-Role": role, "X-Actor": "daily_data_update_pipeline"},
    )
    with urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"{path} returned non-object JSON")
    return payload


def _latency_probe(name: str, *, base_url: str, method: str, path: str, body: dict[str, Any] | None, role: str, timeout: float, threshold_ms: float) -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    try:
        payload = _fetch_json(base_url, path, method=method, body=body, role=role, timeout=timeout)
        elapsed_ms = (datetime.now(timezone.utc) - started).total_seconds() * 1000
        success = bool(payload.get("success", True)) and elapsed_ms <= threshold_ms
        return {
            "name": name,
            "method": method,
            "path": path,
            "status": "passed" if success else "failed",
            "success": success,
            "elapsed_ms": round(elapsed_ms, 2),
            "threshold_ms": threshold_ms,
            "response_success": bool(payload.get("success", True)),
            "error": payload.get("error"),
        }
    except Exception as exc:
        elapsed_ms = (datetime.now(timezone.utc) - started).total_seconds() * 1000
        return {
            "name": name,
            "method": method,
            "path": path,
            "status": "failed",
            "success": False,
            "elapsed_ms": round(elapsed_ms, 2),
            "threshold_ms": threshold_ms,
            "error": str(exc),
            "error_type": type(exc).__name__,
        }


def _latency_audit(base_url: str, *, output: Path, threshold_ms: float, timeout: float) -> dict[str, Any]:
    probes = [
        _latency_probe(
            "market_data_latest",
            base_url=base_url,
            method="GET",
            path="/api/market-data?" + urlencode({"security_id": "sec_000001", "source_id": DEFAULT_SOURCE_A, "data_type": "eod", "limit": 5}),
            body=None,
            role="data_engineer",
            timeout=timeout,
            threshold_ms=threshold_ms,
        ),
        _latency_probe(
            "dashboard_ceo",
            base_url=base_url,
            method="GET",
            path="/api/dashboard/ceo",
            body=None,
            role="CEO",
            timeout=timeout,
            threshold_ms=threshold_ms,
        ),
        _latency_probe(
            "latest_analysis_api",
            base_url=base_url,
            method="GET",
            path="/api/analysis/latest",
            body=None,
            role="CEO",
            timeout=timeout,
            threshold_ms=threshold_ms,
        ),
        _latency_probe(
            "graph_query",
            base_url=base_url,
            method="GET",
            path="/api/graph/query?" + urlencode({"limit": 200}),
            body=None,
            role="analyst",
            timeout=timeout,
            threshold_ms=threshold_ms,
        ),
    ]
    result = {
        "status": "passed" if all(item["success"] for item in probes) else "failed",
        "passed": all(item["success"] for item in probes),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": base_url,
        "threshold_ms": threshold_ms,
        "probes": probes,
        "failure_count": sum(1 for item in probes if not item["success"]),
    }
    _write_json(output, result)
    return result


def _latest_db_dates(dsn: str) -> dict[str, Any]:
    try:
        import psycopg  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        return {"status": "missing_psycopg"}
    with psycopg.connect(dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT market, source_id, COUNT(*) AS rows, MIN(as_of_date)::text AS min_date, MAX(as_of_date)::text AS max_date
                FROM ai_quant.market_data_bars
                GROUP BY market, source_id
                ORDER BY market, source_id
                """
            )
            return {
                "status": "passed",
                "sources": [
                    {"market": row[0], "source_id": row[1], "rows": int(row[2] or 0), "min_date": str(row[3] or ""), "max_date": str(row[4] or "")}
                    for row in cursor.fetchall()
                ],
            }


def _latest_market_date(summary: Mapping[str, Any], *, market: str, source_id: str) -> str:
    for item in summary.get("sources", []) if isinstance(summary.get("sources"), list) else []:
        if not isinstance(item, Mapping):
            continue
        if item.get("market") == market and item.get("source_id") == source_id:
            return str(item.get("max_date") or "")
    return ""


def _previous_weekday(value: str) -> str:
    current = date.fromisoformat(value)
    while current.weekday() >= 5:
        current -= timedelta(days=1)
    return current.isoformat()


def _latest_ready_weekday(now: datetime, *, tz: ZoneInfo, ready_hour: int, ready_minute: int = 0) -> str:
    local_now = now.astimezone(tz)
    candidate = local_now.date()
    if candidate.weekday() >= 5 or local_now.time() < datetime_time(max(0, min(23, ready_hour)), max(0, min(59, ready_minute))):
        candidate -= timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate.isoformat()


def _effective_market_end_dates(args: argparse.Namespace, *, now: datetime | None = None) -> dict[str, Any]:
    requested_end_date = args.end_date or args.run_date or date.today().isoformat()
    if args.end_date:
        return {
            "requested_end_date": requested_end_date,
            "forced_end_date": args.end_date,
            "effective_end_dates": {"A": args.end_date, "TDX": args.end_date, "U": args.end_date},
            "strategy": {
                "mode": "forced_end_date",
                "reason": "--end-date was provided",
                "forced_end_date": args.end_date,
            },
        }

    now_utc = now or datetime.now(timezone.utc)
    ashare_end_date = _latest_ready_weekday(
        now_utc,
        tz=ASHARE_TZ,
        ready_hour=args.ashare_eod_ready_hour_cst,
        ready_minute=args.ashare_eod_ready_minute_cst,
    )
    us_end_date = _latest_ready_weekday(
        now_utc,
        tz=US_TZ,
        ready_hour=args.us_eod_ready_hour_ny,
        ready_minute=args.us_eod_ready_minute_ny,
    )
    return {
        "requested_end_date": requested_end_date,
        "forced_end_date": "",
        "effective_end_dates": {"A": ashare_end_date, "TDX": ashare_end_date, "U": us_end_date},
        "strategy": {
            "mode": "market_close_ready_window",
            "now_utc": now_utc.isoformat(),
            "ashare_timezone": "Asia/Shanghai",
            "ashare_ready_after_local_time": f"{args.ashare_eod_ready_hour_cst:02d}:{args.ashare_eod_ready_minute_cst:02d}",
            "ashare_local_now": now_utc.astimezone(ASHARE_TZ).isoformat(),
            "us_timezone": "America/New_York",
            "us_ready_after_local_time": f"{args.us_eod_ready_hour_ny:02d}:{args.us_eod_ready_minute_ny:02d}",
            "us_local_now": now_utc.astimezone(US_TZ).isoformat(),
            "note": "When --end-date is omitted, each market only targets an EOD date after that market's ready window has passed; holidays still rely on source/audit results.",
        },
    }


def run_daily_pipeline(args: argparse.Namespace) -> dict[str, Any]:
    started_at = datetime.now(timezone.utc)
    run_date = args.run_date or date.today().isoformat()
    output_root = Path(args.output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    steps: list[dict[str, Any]] = []
    artifacts: dict[str, str] = {}

    def artifact(name: str, suffix: str = ".json") -> Path:
        path = output_root / f"{name}-{run_date}{suffix}"
        artifacts[name] = str(path)
        return path

    db_before = _latest_db_dates(args.dsn)
    date_plan = _effective_market_end_dates(args)
    requested_end_date = date_plan["requested_end_date"]
    effective_end_dates = date_plan["effective_end_dates"]
    ashare_end_date = effective_end_dates["A"]
    us_end_date = effective_end_dates["U"]
    tdx_end_date = effective_end_dates["TDX"]

    if args.run_ashare_scope_refresh and not args.skip_ashare:
        scope_output = artifact("ashare-current-baostock-universe-scope")
        command = [
            sys.executable,
            "scripts/scope_ashare_current_baostock_universe.py",
            "--dsn",
            args.dsn,
            "--output",
            str(scope_output),
        ]
        steps.append(_run_command("ashare_current_universe_scope", command, timeout=args.import_timeout_seconds, allow_failure=args.allow_import_failure))

    if args.run_ashare_incremental and not args.skip_ashare:
        ashare_output = artifact("ashare-eod-baostock-incremental")
        command = [
            sys.executable,
            "scripts/import_ashare_eod_baostock.py",
            "--dsn",
            args.dsn,
            "--symbols-from-db",
            "--end-date",
            ashare_end_date,
            "--commit-every",
            str(args.commit_every),
            "--artifact-symbol-limit",
            str(args.artifact_symbol_limit),
            "--output",
            str(ashare_output),
        ]
        if args.max_ashare_symbols:
            command.extend(["--max-symbols", str(args.max_ashare_symbols)])
        elif args.ashare_batch_size:
            command.extend(["--max-symbols", str(args.ashare_batch_size)])
        if args.ashare_offset:
            command.extend(["--offset", str(args.ashare_offset)])
        if args.ashare_start_date:
            command.extend(["--start-date", args.ashare_start_date])
        else:
            command.extend(["--fallback-start-date", ashare_end_date])
        steps.append(_run_command("ashare_baostock_incremental", command, timeout=args.import_timeout_seconds, allow_failure=args.allow_import_failure))

    if args.tdx_incremental and args.vipdoc_path:
        tdx_output = artifact("tdx-vipdoc-incremental")
        start_date = args.tdx_start_date or (date.fromisoformat(run_date) - timedelta(days=args.tdx_lookback_days)).isoformat()
        command = [
            sys.executable,
            "scripts/import_tdx_vipdoc_postgres.py",
            "--dsn",
            args.dsn,
            "--vipdoc-path",
            args.vipdoc_path,
            "--start-date",
            start_date,
            "--end-date",
            tdx_end_date,
            "--batch-size",
            str(args.tdx_batch_size),
            "--output",
            str(tdx_output),
        ]
        steps.append(_run_command("tdx_vipdoc_incremental", command, timeout=args.import_timeout_seconds, allow_failure=args.allow_import_failure))

    if args.vipdoc_path and not args.skip_tdx_coverage_audit:
        tdx_coverage_output = artifact("tdx-vipdoc-coverage-audit")
        tdx_coverage_started = datetime.now(timezone.utc)
        coverage_start_date = args.tdx_coverage_start_date or (date.fromisoformat(run_date) - timedelta(days=args.tdx_coverage_lookback_days)).isoformat()
        try:
            tdx_coverage_args = argparse.Namespace(
                dsn=args.dsn,
                vipdoc_path=args.vipdoc_path,
                source_id=DEFAULT_SOURCE_A,
                data_type="eod",
                start_date=coverage_start_date,
                end_date=tdx_end_date,
                limit_per_symbol=0,
                symbol_prefix=args.tdx_symbol_prefix,
                max_symbols=args.tdx_coverage_max_symbols,
                sample_limit=args.tdx_coverage_sample_limit,
                statement_timeout_ms=args.tdx_coverage_statement_timeout_ms,
                strict_file_scan=args.tdx_coverage_strict_file_scan,
                strict_extra_db_symbols=False,
                strict_surplus_db_rows=False,
                fail_on_needs_import=False,
                output=str(tdx_coverage_output),
                import_output=artifacts.get("tdx-vipdoc-incremental", str(output_root / f"tdx-vipdoc-incremental-{run_date}.json")),
            )
            tdx_coverage = build_tdx_coverage_report(tdx_coverage_args)
            _write_json(tdx_coverage_output, tdx_coverage)
            blocking = bool(args.fail_on_tdx_coverage_needs_import and not tdx_coverage.get("ready_to_skip_import"))
            steps.append(
                {
                    "name": "tdx_vipdoc_coverage_audit",
                    "status": "failed" if blocking else tdx_coverage["status"],
                    "artifact": str(tdx_coverage_output),
                    "ready_to_skip_import": tdx_coverage.get("ready_to_skip_import"),
                    "recommended_action": tdx_coverage.get("recommended_action"),
                    "elapsed_seconds": round((datetime.now(timezone.utc) - tdx_coverage_started).total_seconds(), 3),
                    "blocking": blocking,
                }
            )
        except Exception as exc:
            steps.append(
                {
                    "name": "tdx_vipdoc_coverage_audit",
                    "status": "failed",
                    "artifact": str(tdx_coverage_output),
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "elapsed_seconds": round((datetime.now(timezone.utc) - tdx_coverage_started).total_seconds(), 3),
                    "blocking": True,
                }
            )

    if not args.skip_us:
        if args.run_us_scope_refresh:
            us_scope_output = artifact("us-current-yahoo-universe-scope")
            command = [
                sys.executable,
                "scripts/scope_us_current_yahoo_universe.py",
                "--dsn",
                args.dsn,
                "--target-date",
                us_end_date,
                "--output",
                str(us_scope_output),
            ]
            steps.append(_run_command("us_yahoo_universe_scope", command, timeout=args.import_timeout_seconds, allow_failure=args.allow_import_failure))

        us_output = artifact("us-eod-yahoo-incremental")
        us_start = args.us_start_date or (date.fromisoformat(run_date) - timedelta(days=args.us_lookback_days)).isoformat()
        command = [
            sys.executable,
            "scripts/import_us_eod_yahoo_chart.py",
            "--dsn",
            args.dsn,
            "--start-date",
            us_start,
            "--end-date",
            us_end_date,
            "--output",
            str(us_output),
        ]
        if args.us_tickers_from_db:
            command.append("--tickers-from-db")
            if args.us_ticker_filter:
                command.extend(["--ticker-filter", args.us_ticker_filter])
            if args.us_offset:
                command.extend(["--offset", str(args.us_offset)])
            if args.max_us_tickers:
                command.extend(["--max-tickers", str(args.max_us_tickers)])
            elif args.us_batch_size:
                command.extend(["--max-tickers", str(args.us_batch_size)])
        else:
            command.extend(["--tickers", args.us_tickers])
        steps.append(_run_command("us_yahoo_incremental", command, timeout=args.import_timeout_seconds, allow_failure=args.allow_import_failure))
        if args.run_us_scope_refresh and args.us_tickers_from_db:
            us_scope_post_output = artifact("us-current-yahoo-universe-scope-post-import")
            command = [
                sys.executable,
                "scripts/scope_us_current_yahoo_universe.py",
                "--dsn",
                args.dsn,
                "--target-date",
                us_end_date,
                "--mark-stale-out-of-scope",
                "--output",
                str(us_scope_post_output),
            ]
            steps.append(_run_command("us_yahoo_universe_scope_post_import", command, timeout=args.import_timeout_seconds, allow_failure=args.allow_import_failure))

    storage_output = artifact("market-data-storage-audit")
    storage_started = datetime.now(timezone.utc)
    try:
        storage_audit = build_market_data_storage_audit(
            dsn=args.dsn,
            base_url=args.base_url,
            sample_security_id=args.sample_security_id,
            sample_source_id=args.sample_source_id,
            sample_data_type="eod",
            timeout=args.api_timeout_seconds,
        )
        _write_json(storage_output, storage_audit)
        steps.append(
            {
                "name": "market_data_storage_audit",
                "status": storage_audit["status"],
                "artifact": str(storage_output),
                "elapsed_seconds": round((datetime.now(timezone.utc) - storage_started).total_seconds(), 3),
                "blocking": not storage_audit.get("passed"),
            }
        )
    except Exception as exc:
        steps.append(
            {
                "name": "market_data_storage_audit",
                "status": "failed",
                "artifact": str(storage_output),
                "error": str(exc),
                "error_type": type(exc).__name__,
                "elapsed_seconds": round((datetime.now(timezone.utc) - storage_started).total_seconds(), 3),
                "blocking": True,
            }
        )

    if not args.skip_research_binding:
        binding_output = artifact("research-report-asset-binding")
        command = [
            sys.executable,
            "scripts/bind_research_reports_to_assets.py",
            "--dsn",
            args.dsn,
            "--market",
            args.research_binding_market,
            "--tickers",
            args.research_binding_tickers,
            "--limit",
            str(args.research_binding_limit),
            "--max-matches-per-report",
            str(args.research_binding_max_matches_per_report),
            "--artifact-limit",
            str(args.research_binding_artifact_limit),
            "--output",
            str(binding_output),
        ]
        if args.research_binding_dry_run:
            command.append("--dry-run")
        steps.append(
            _run_command(
                "research_report_asset_binding",
                command,
                timeout=args.research_binding_timeout_seconds,
                allow_failure=args.allow_research_binding_failure,
            )
        )

    if not args.skip_latest_analysis:
        latest_output_dir = output_root / f"latest-analysis-{run_date}"
        artifacts["latest_analysis"] = str(latest_output_dir / "latest-analysis.json")
        command = [
            sys.executable,
            "scripts/latest_analysis_run.py",
            "--base-url",
            args.base_url,
            "--symbols",
            args.latest_symbols,
            "--us-tickers",
            args.us_tickers,
            "--output-dir",
            str(latest_output_dir),
            "--timeout",
            str(args.api_timeout_seconds),
            "--semantic-timeout-seconds",
            str(args.latest_analysis_semantic_timeout_seconds),
        ]
        steps.append(_run_command("latest_analysis", command, timeout=args.analysis_timeout_seconds, allow_failure=args.allow_latest_analysis_failure))

    insight_output = artifact("daily-insight-json")
    insight_md_output = artifact("daily-insight-md", ".md")
    insight_started = datetime.now(timezone.utc)
    try:
        insight = build_daily_market_insight(
            dsn=args.dsn,
            as_of_date=run_date,
            source_a=DEFAULT_SOURCE_A,
            source_u=DEFAULT_SOURCE_U,
            data_type="eod",
            top_limit=args.insight_top_limit,
            current_row_limit=args.insight_current_row_limit,
            history_rows=args.insight_history_rows,
            recent_days=args.insight_recent_days,
            min_direct_evidence_companies=args.min_direct_evidence_companies,
        )
        _write_json(insight_output, insight)
        _write_text(insight_md_output, build_insight_markdown(insight))
        steps.append(
            {
                "name": "daily_market_insight",
                "status": insight["status"],
                "artifact": str(insight_output),
                "markdown_artifact": str(insight_md_output),
                "elapsed_seconds": round((datetime.now(timezone.utc) - insight_started).total_seconds(), 3),
                "blocking": not insight.get("passed"),
            }
        )
    except Exception as exc:
        steps.append(
            {
                "name": "daily_market_insight",
                "status": "failed",
                "artifact": str(insight_output),
                "error": str(exc),
                "error_type": type(exc).__name__,
                "elapsed_seconds": round((datetime.now(timezone.utc) - insight_started).total_seconds(), 3),
                "blocking": True,
            }
        )

    latency_output = artifact("latency-audit")
    latency = _latency_audit(args.base_url, output=latency_output, threshold_ms=args.latency_threshold_ms, timeout=args.api_timeout_seconds)
    steps.append(
        {
            "name": "latency_audit",
            "status": latency["status"],
            "artifact": str(latency_output),
            "blocking": not latency.get("passed"),
        }
    )

    if not args.skip_local_production_audit:
        local_output = artifact("local-production-audit")
        command = [
            sys.executable,
            "scripts/local_production_audit.py",
            "--base-url",
            args.base_url,
            "--output",
            str(local_output),
        ]
        steps.append(_run_command("local_production_audit", command, timeout=args.audit_timeout_seconds, allow_failure=False))

    if args.run_project_completion_audit and not args.skip_project_completion_audit:
        project_output = artifact("project-completion-audit")
        local_audit_path = artifacts.get("local-production-audit") or "artifacts/local-production-audit.json"
        command = [
            sys.executable,
            "scripts/project_completion_audit.py",
            "--local-production-audit",
            local_audit_path,
            "--output",
            str(project_output),
        ]
        steps.append(_run_command("project_completion_audit", command, timeout=args.audit_timeout_seconds, allow_failure=False))

    db_after = _latest_db_dates(args.dsn)
    blocking_failures = [step for step in steps if step.get("blocking") or step.get("status") == "failed"]
    result = {
        "status": "passed" if not blocking_failures else "failed",
        "passed": not blocking_failures,
        "started_at": started_at.isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "run_date": run_date,
        "requested_end_date": requested_end_date,
        "effective_end_dates": {
            "A": ashare_end_date,
            "U": us_end_date,
            "TDX": tdx_end_date,
        },
        "market_date_strategy": date_plan["strategy"],
        "production_boundary": "local_personal_production_daily_refresh_no_live_broker_no_auto_order",
        "db_before": db_before,
        "db_after": db_after,
        "steps": steps,
        "artifacts": artifacts,
        "failure_count": len(blocking_failures),
        "blocking_failures": blocking_failures,
        "usage_note": "Schedule this script from cron/systemd. Without --end-date it targets each market's latest EOD date only after that market's ready window has passed; A-share refresh is resumable with --ashare-offset and --ashare-batch-size.",
    }
    _write_json(args.output, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Daily local production data refresh: incremental market data, storage audit, latest analysis, insight, latency, and production audit.")
    parser.add_argument("--dsn", default=DEFAULT_DSN)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--run-date", default=date.today().isoformat())
    parser.add_argument("--end-date", default="", help="Force public-source probing through this date for every market.")
    parser.add_argument("--ashare-eod-ready-hour-cst", type=int, default=18, help="Default A-share EOD target advances to the local trade date only after this Asia/Shanghai hour.")
    parser.add_argument("--ashare-eod-ready-minute-cst", type=int, default=0)
    parser.add_argument("--us-eod-ready-hour-ny", type=int, default=18, help="Default US EOD target advances to the local trade date only after this America/New_York hour.")
    parser.add_argument("--us-eod-ready-minute-ny", type=int, default=0)
    parser.add_argument("--output-dir", default="artifacts/daily-update")
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--run-ashare-incremental", action="store_true", help="Run resumable A-share baostock incremental batch. Disabled by default because public-source per-symbol probing is slow.")
    parser.add_argument("--run-ashare-scope-refresh", action="store_true", help="Refresh active A-share in_scope/reference_only flags from baostock stock_basic before the A-share incremental batch.")
    parser.add_argument("--skip-ashare", action="store_true")
    parser.add_argument("--skip-us", action="store_true")
    parser.add_argument("--tdx-incremental", action="store_true")
    parser.add_argument("--vipdoc-path", default="")
    parser.add_argument("--tdx-start-date", default="")
    parser.add_argument("--tdx-lookback-days", type=int, default=7)
    parser.add_argument("--tdx-batch-size", type=int, default=5000)
    parser.add_argument("--skip-tdx-coverage-audit", action="store_true")
    parser.add_argument("--fail-on-tdx-coverage-needs-import", action="store_true")
    parser.add_argument("--tdx-coverage-start-date", default="")
    parser.add_argument("--tdx-coverage-lookback-days", type=int, default=30)
    parser.add_argument("--tdx-coverage-max-symbols", type=int, default=0)
    parser.add_argument("--tdx-symbol-prefix", default="")
    parser.add_argument("--tdx-coverage-sample-limit", type=int, default=20)
    parser.add_argument("--tdx-coverage-statement-timeout-ms", type=int, default=120000)
    parser.add_argument("--tdx-coverage-strict-file-scan", action="store_true")
    parser.add_argument("--ashare-start-date", default="")
    parser.add_argument("--ashare-offset", type=int, default=0)
    parser.add_argument("--ashare-batch-size", type=int, default=100, help="A-share incremental batch size when --run-ashare-incremental is set. Use offset on subsequent runs to resume the full universe.")
    parser.add_argument("--max-ashare-symbols", type=int, default=0)
    parser.add_argument("--us-tickers", default="AAPL,MSFT,NVDA,TSLA,SPY")
    parser.add_argument("--us-tickers-from-db", action="store_true", help="Use the registered US securities universe for the Yahoo import step; latest analysis still uses --us-tickers.")
    parser.add_argument("--run-us-scope-refresh", action="store_true", help="Refresh US Yahoo active refresh scope before the DB-universe import step.")
    parser.add_argument("--us-ticker-filter", default="")
    parser.add_argument("--us-offset", type=int, default=0)
    parser.add_argument("--us-batch-size", type=int, default=100, help="US Yahoo import batch size when --us-tickers-from-db is set.")
    parser.add_argument("--max-us-tickers", type=int, default=0)
    parser.add_argument("--us-start-date", default="")
    parser.add_argument("--us-lookback-days", type=int, default=7)
    parser.add_argument("--latest-symbols", default="600000,000001,300750,600519")
    parser.add_argument("--sample-security-id", default="sec_000001")
    parser.add_argument("--sample-source-id", default=DEFAULT_SOURCE_A)
    parser.add_argument("--commit-every", type=int, default=200)
    parser.add_argument("--artifact-symbol-limit", type=int, default=500)
    parser.add_argument("--allow-import-failure", action="store_true", help="Keep later audits running when public-data imports fail; final status still records allowed_failure.")
    parser.add_argument("--skip-research-binding", action="store_true")
    parser.add_argument("--allow-research-binding-failure", action="store_true")
    parser.add_argument("--research-binding-dry-run", action="store_true")
    parser.add_argument("--research-binding-market", default="", choices=["", "A", "U"])
    parser.add_argument("--research-binding-tickers", default="AAPL,MSFT,NVDA,TSLA,SPY,300750,600519,000001,600000")
    parser.add_argument("--research-binding-limit", type=int, default=20000)
    parser.add_argument("--research-binding-max-matches-per-report", type=int, default=3)
    parser.add_argument("--research-binding-artifact-limit", type=int, default=40)
    parser.add_argument("--research-binding-timeout-seconds", type=int, default=1800)
    parser.add_argument("--skip-latest-analysis", action="store_true")
    parser.add_argument("--allow-latest-analysis-failure", action="store_true", help="Continue daily insight and audits if the heavier latest_analysis_run step times out or fails.")
    parser.add_argument("--latest-analysis-semantic-timeout-seconds", type=float, default=8.0)
    parser.add_argument("--skip-local-production-audit", action="store_true")
    parser.add_argument("--skip-project-completion-audit", action="store_true")
    parser.add_argument("--run-project-completion-audit", action="store_true", help="Run the heavier project completion audit. Disabled by default in daily refresh because it imports UI/PIL audit dependencies.")
    parser.add_argument("--latency-threshold-ms", type=float, default=5000.0)
    parser.add_argument("--api-timeout-seconds", type=float, default=30.0)
    parser.add_argument("--import-timeout-seconds", type=int, default=7200)
    parser.add_argument("--analysis-timeout-seconds", type=int, default=1800)
    parser.add_argument("--audit-timeout-seconds", type=int, default=600)
    parser.add_argument("--insight-top-limit", type=int, default=12)
    parser.add_argument("--insight-current-row-limit", type=int, default=50000)
    parser.add_argument("--insight-history-rows", type=int, default=20)
    parser.add_argument("--insight-recent-days", type=int, default=7)
    parser.add_argument("--min-direct-evidence-companies", type=int, default=1)
    args = parser.parse_args()

    result = run_daily_pipeline(args)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if not result.get("passed"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
