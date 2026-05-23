from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shlex
import struct
import sys
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services import PUBLIC_EOD_MARKET_DATA_SOURCE_ID
from scripts.import_tdx_vipdoc_postgres import RECORD_SIZE, date_from_int, iter_day_files, normalize_symbol


DEFAULT_START_DATE = "1900-01-01"
DEFAULT_END_DATE = "2099-12-31"
DATE_STRUCT = struct.Struct("<I")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_record_date(raw: bytes) -> str:
    return date_from_int(DATE_STRUCT.unpack_from(raw, 0)[0])


def iter_file_dates(file_path: Path, *, start_date: str, end_date: str, limit: int) -> Iterable[str]:
    yielded = 0
    with file_path.open("rb") as handle:
        while True:
            raw = handle.read(RECORD_SIZE)
            if not raw:
                break
            if len(raw) != RECORD_SIZE:
                raise ValueError(f"invalid trailing record length: {file_path}")
            trade_date = read_record_date(raw)
            if trade_date < start_date:
                continue
            if trade_date > end_date:
                continue
            yield trade_date
            yielded += 1
            if limit and yielded >= limit:
                break


def fast_file_summary(file_path: Path) -> dict[str, Any]:
    size = file_path.stat().st_size
    if size % RECORD_SIZE != 0:
        raise ValueError(f"invalid record length: {file_path}")
    row_count = size // RECORD_SIZE
    if row_count == 0:
        return {"row_count": 0, "min_date": "", "max_date": ""}
    with file_path.open("rb") as handle:
        first = handle.read(RECORD_SIZE)
        handle.seek((row_count - 1) * RECORD_SIZE)
        last = handle.read(RECORD_SIZE)
    return {
        "row_count": row_count,
        "min_date": read_record_date(first),
        "max_date": read_record_date(last),
    }


def parsed_file_summary(file_path: Path, *, start_date: str, end_date: str, limit: int) -> dict[str, Any]:
    dates = sorted(set(iter_file_dates(file_path, start_date=start_date, end_date=end_date, limit=limit)))
    if not dates:
        return {"row_count": 0, "min_date": "", "max_date": "", "dates": []}
    return {
        "row_count": len(dates),
        "min_date": min(dates),
        "max_date": max(dates),
        "dates": dates,
    }


def merge_summary(target: dict[str, Any], addition: dict[str, Any]) -> None:
    target["row_count"] += int(addition["row_count"])
    min_date = addition.get("min_date") or ""
    max_date = addition.get("max_date") or ""
    if min_date:
        target["min_date"] = min_date if not target["min_date"] else min(target["min_date"], min_date)
    if max_date:
        target["max_date"] = max_date if not target["max_date"] else max(target["max_date"], max_date)


def summarize_expected(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.vipdoc_path)
    if not root.exists():
        raise RuntimeError(f"vipdoc path not found: {root}")

    files = list(iter_day_files(root, prefix=args.symbol_prefix, max_symbols=args.max_symbols))
    security_files: dict[str, list[Path]] = {}
    for file_path in files:
        security_id = f"sec_{normalize_symbol(file_path.stem)}"
        security_files.setdefault(security_id, []).append(file_path)

    duplicate_security_ids = sorted(security_id for security_id, paths in security_files.items() if len(paths) > 1)
    needs_parse = (
        args.strict_file_scan
        or args.limit_per_symbol > 0
        or args.start_date != DEFAULT_START_DATE
        or args.end_date != DEFAULT_END_DATE
    )

    by_security: dict[str, dict[str, Any]] = {}
    failed_files: list[dict[str, str]] = []
    raw_file_row_count = 0
    files_with_rows = 0
    duplicate_date_sets: dict[str, set[str]] = {security_id: set() for security_id in duplicate_security_ids}

    for file_path in files:
        symbol = normalize_symbol(file_path.stem)
        security_id = f"sec_{symbol}"
        duplicate = security_id in duplicate_date_sets
        try:
            if duplicate or needs_parse:
                summary = parsed_file_summary(
                    file_path,
                    start_date=args.start_date,
                    end_date=args.end_date,
                    limit=args.limit_per_symbol,
                )
            else:
                summary = fast_file_summary(file_path)
        except Exception as exc:
            failed_files.append({"file": str(file_path), "error": str(exc)})
            continue

        raw_file_row_count += int(summary["row_count"])
        if int(summary["row_count"]) <= 0:
            continue
        files_with_rows += 1

        if duplicate:
            duplicate_date_sets[security_id].update(summary.get("dates", []))
            continue

        target = by_security.setdefault(
            security_id,
            {
                "security_id": security_id,
                "symbol": symbol,
                "row_count": 0,
                "min_date": "",
                "max_date": "",
                "files": [],
            },
        )
        target["files"].append(str(file_path))
        merge_summary(target, summary)

    for security_id, dates in duplicate_date_sets.items():
        if not dates:
            continue
        paths = security_files[security_id]
        symbol = normalize_symbol(paths[0].stem)
        by_security[security_id] = {
            "security_id": security_id,
            "symbol": symbol,
            "row_count": len(dates),
            "min_date": min(dates),
            "max_date": max(dates),
            "files": [str(path) for path in paths],
        }

    row_count = sum(int(item["row_count"]) for item in by_security.values())
    min_dates = [item["min_date"] for item in by_security.values() if item["min_date"]]
    max_dates = [item["max_date"] for item in by_security.values() if item["max_date"]]

    return {
        "vipdoc_path": str(root),
        "file_count": len(files),
        "files_with_rows": files_with_rows,
        "raw_file_row_count": raw_file_row_count,
        "symbol_count": len(by_security),
        "row_count": row_count,
        "min_date": min(min_dates) if min_dates else "",
        "max_date": max(max_dates) if max_dates else "",
        "failed_file_count": len(failed_files),
        "failed_files": failed_files[:100],
        "duplicate_security_count": len(duplicate_security_ids),
        "duplicate_security_samples": [
            {
                "security_id": security_id,
                "files": [str(path) for path in security_files[security_id]][:10],
            }
            for security_id in duplicate_security_ids[:20]
        ],
        "by_security": by_security,
    }


def summarize_postgres(args: argparse.Namespace) -> dict[str, Any]:
    try:
        import psycopg  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:
        raise RuntimeError("psycopg is required: python3 -m pip install 'psycopg[binary]>=3.1'") from exc

    rows: list[tuple[str, int, str, str]] = []
    with psycopg.connect(args.dsn) as connection:
        with connection.cursor() as cursor:
            if args.statement_timeout_ms:
                cursor.execute("SET LOCAL statement_timeout = %s", (args.statement_timeout_ms,))
            cursor.execute(
                """
                SELECT
                    COALESCE(payload->>'security_id', '') AS security_id,
                    COUNT(*)::bigint AS row_count,
                    MIN(payload->>'as_of_date') AS min_date,
                    MAX(payload->>'as_of_date') AS max_date
                FROM ai_quant.records
                WHERE collection = 'market_data'
                  AND payload->>'source_id' = %s
                  AND payload->>'data_type' = %s
                  AND payload->>'market' = 'A'
                GROUP BY COALESCE(payload->>'security_id', '')
                """,
                (args.source_id, args.data_type),
            )
            rows = [(str(row[0]), int(row[1]), str(row[2] or ""), str(row[3] or "")) for row in cursor.fetchall()]

    by_security = {
        security_id: {
            "security_id": security_id,
            "row_count": row_count,
            "min_date": min_date,
            "max_date": max_date,
        }
        for security_id, row_count, min_date, max_date in rows
    }
    min_dates = [row[2] for row in rows if row[2]]
    max_dates = [row[3] for row in rows if row[3]]
    return {
        "symbol_count": len(by_security),
        "row_count": sum(row[1] for row in rows),
        "min_date": min(min_dates) if min_dates else "",
        "max_date": max(max_dates) if max_dates else "",
        "by_security": by_security,
    }


def sample(items: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    return items[: max(0, limit)]


def compare_coverage(args: argparse.Namespace, expected: dict[str, Any], postgres: dict[str, Any]) -> dict[str, Any]:
    expected_by_security = expected["by_security"]
    postgres_by_security = postgres["by_security"]

    missing_symbols: list[dict[str, Any]] = []
    deficient_symbols: list[dict[str, Any]] = []
    surplus_symbols: list[dict[str, Any]] = []

    for security_id, expected_item in sorted(expected_by_security.items()):
        db_item = postgres_by_security.get(security_id)
        if not db_item:
            missing_symbols.append(expected_item)
            continue

        reasons = []
        expected_count = int(expected_item["row_count"])
        db_count = int(db_item["row_count"])
        expected_min = expected_item.get("min_date") or ""
        expected_max = expected_item.get("max_date") or ""
        db_min = db_item.get("min_date") or ""
        db_max = db_item.get("max_date") or ""

        if db_count < expected_count:
            reasons.append("row_count_below_expected")
        if expected_min and (not db_min or db_min > expected_min):
            reasons.append("min_date_after_expected")
        if expected_max and (not db_max or db_max < expected_max):
            reasons.append("max_date_before_expected")
        if reasons:
            deficient_symbols.append({"security_id": security_id, "expected": expected_item, "postgres": db_item, "reasons": reasons})
            continue

        surplus_reasons = []
        if db_count > expected_count:
            surplus_reasons.append("row_count_above_expected")
        if expected_min and db_min and db_min < expected_min:
            surplus_reasons.append("min_date_before_expected")
        if expected_max and db_max and db_max > expected_max:
            surplus_reasons.append("max_date_after_expected")
        if surplus_reasons:
            surplus_symbols.append({"security_id": security_id, "expected": expected_item, "postgres": db_item, "reasons": surplus_reasons})

    extra_security_ids = sorted(set(postgres_by_security) - set(expected_by_security))
    extra_symbols = [postgres_by_security[security_id] for security_id in extra_security_ids]

    blocking_issue_count = expected["failed_file_count"] + len(missing_symbols) + len(deficient_symbols)
    if args.strict_extra_db_symbols:
        blocking_issue_count += len(extra_symbols)
    if args.strict_surplus_db_rows:
        blocking_issue_count += len(surplus_symbols)

    status = "passed" if blocking_issue_count == 0 else "needs_import"
    ready_to_skip_import = status == "passed"

    return {
        "status": status,
        "ready_to_skip_import": ready_to_skip_import,
        "blocking_issue_count": blocking_issue_count,
        "missing_symbol_count": len(missing_symbols),
        "deficient_symbol_count": len(deficient_symbols),
        "surplus_symbol_count": len(surplus_symbols),
        "extra_db_symbol_count": len(extra_symbols),
        "sample_missing_symbols": sample(missing_symbols, args.sample_limit),
        "sample_deficient_symbols": sample(deficient_symbols, args.sample_limit),
        "sample_surplus_symbols": sample(surplus_symbols, args.sample_limit),
        "sample_extra_db_symbols": sample(extra_symbols, args.sample_limit),
    }


def build_import_command(args: argparse.Namespace) -> str:
    parts = [
        "python3",
        "scripts/import_tdx_vipdoc_postgres.py",
        "--dsn",
        args.dsn,
        "--vipdoc-path",
        args.vipdoc_path,
        "--source-id",
        args.source_id,
        "--data-type",
        args.data_type,
        "--start-date",
        args.start_date,
        "--end-date",
        args.end_date,
        "--output",
        args.import_output,
    ]
    if args.limit_per_symbol:
        parts.extend(["--limit-per-symbol", str(args.limit_per_symbol)])
    if args.symbol_prefix:
        parts.extend(["--symbol-prefix", args.symbol_prefix])
    if args.max_symbols:
        parts.extend(["--max-symbols", str(args.max_symbols)])
    return " ".join(shlex.quote(part) for part in parts)


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    started_at = utc_now()
    expected = summarize_expected(args)
    postgres = summarize_postgres(args)
    comparison = compare_coverage(args, expected, postgres)
    recommendation = "skip_import" if comparison["ready_to_skip_import"] else "run_import"

    expected_public = dict(expected)
    postgres_public = dict(postgres)
    expected_public.pop("by_security", None)
    postgres_public.pop("by_security", None)

    return {
        "status": comparison["status"],
        "ready_to_skip_import": comparison["ready_to_skip_import"],
        "started_at": started_at,
        "completed_at": utc_now(),
        "source_id": args.source_id,
        "data_type": args.data_type,
        "start_date": args.start_date,
        "end_date": args.end_date,
        "limit_per_symbol": args.limit_per_symbol,
        "symbol_prefix": args.symbol_prefix,
        "max_symbols": args.max_symbols,
        "expected": expected_public,
        "postgres": postgres_public,
        "comparison": comparison,
        "recommended_action": recommendation,
        "recommended_command": "" if recommendation == "skip_import" else build_import_command(args),
        "notes": [
            "Use this coverage audit before re-running the full TDX PostgreSQL import.",
            "Full import remains idempotent, but it rewrites a large JSONB market_data surface and should be reserved for missing or deficient coverage.",
            "Surplus PostgreSQL rows are warnings by default because re-importing does not delete them.",
        ],
    }


def write_report(output: str, report: dict[str, Any]) -> None:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit local TDX vipdoc .day coverage against PostgreSQL before deciding whether to re-import.")
    parser.add_argument("--dsn", default=os.environ.get("AI_QUANT_POSTGRES_DSN", "postgresql://ai_quant:ai_quant_dev_password@127.0.0.1:15432/ai_quant"))
    parser.add_argument("--vipdoc-path", default=os.environ.get("AI_QUANT_TDX_VIPDOC_PATH", "data/local/tdx/vipdoc"))
    parser.add_argument("--source-id", default=PUBLIC_EOD_MARKET_DATA_SOURCE_ID)
    parser.add_argument("--data-type", choices=["eod", "delayed"], default="eod")
    parser.add_argument("--start-date", default=DEFAULT_START_DATE)
    parser.add_argument("--end-date", default=DEFAULT_END_DATE)
    parser.add_argument("--limit-per-symbol", type=int, default=0, help="Match import_tdx_vipdoc_postgres.py semantics; 0 means no limit.")
    parser.add_argument("--symbol-prefix", default="")
    parser.add_argument("--max-symbols", type=int, default=0)
    parser.add_argument("--sample-limit", type=int, default=20)
    parser.add_argument("--statement-timeout-ms", type=int, default=0, help="Optional PostgreSQL statement timeout for the coverage aggregation.")
    parser.add_argument("--strict-file-scan", action="store_true", help="Parse every record date instead of using file-size plus first/last date summaries.")
    parser.add_argument("--strict-extra-db-symbols", action="store_true", help="Treat DB symbols absent from the current vipdoc scan as blocking.")
    parser.add_argument("--strict-surplus-db-rows", action="store_true", help="Treat DB rows beyond current vipdoc coverage as blocking.")
    parser.add_argument("--fail-on-needs-import", action="store_true", help="Return exit code 2 when coverage is insufficient.")
    parser.add_argument("--output", default="artifacts/tdx-vipdoc-postgres-coverage.json")
    parser.add_argument("--import-output", default="artifacts/tdx-vipdoc-postgres-import-full.json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        report = build_report(args)
        exit_code = 2 if args.fail_on_needs_import and not report["ready_to_skip_import"] else 0
    except Exception as exc:
        report = {
            "status": "failed",
            "ready_to_skip_import": False,
            "started_at": utc_now(),
            "completed_at": utc_now(),
            "error": str(exc),
        }
        exit_code = 1
    write_report(args.output, report)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
