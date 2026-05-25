from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any, Mapping
from urllib.parse import urlencode, urljoin
from urllib.request import urlopen


DEFAULT_DSN = "postgresql://ai_quant:ai_quant_dev_password@127.0.0.1:15432/ai_quant"
DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_OUTPUT = "artifacts/market-data-storage-audit.json"


def _fetch_json(base_url: str, path: str, *, timeout: float) -> dict[str, Any]:
    url = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    with urlopen(url, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise AssertionError(f"{url} did not return a JSON object")
    return payload


def _unwrap(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    if payload.get("success") is True and isinstance(payload.get("data"), Mapping):
        return payload["data"]
    return payload


def _write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_name(f".{output.name}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(output)


def _connect(dsn: str) -> Any:
    try:
        import psycopg  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:
        raise RuntimeError("psycopg is required. Run inside the app container or install psycopg[binary].") from exc
    return psycopg.connect(dsn)


def _fetch_one(cursor: Any, sql: str, params: tuple[Any, ...] = ()) -> tuple[Any, ...]:
    cursor.execute(sql, params)
    row = cursor.fetchone()
    return tuple(row or ())


def _fetch_all(cursor: Any, sql: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    cursor.execute(sql, params)
    return [tuple(row) for row in cursor.fetchall()]


def _market_data_api_smoke(base_url: str, *, security_id: str, source_id: str, data_type: str, timeout: float) -> dict[str, Any]:
    params = urlencode({"security_id": security_id, "source_id": source_id, "data_type": data_type, "limit": 2})
    started = datetime.now(timezone.utc)
    payload = _fetch_json(base_url, f"/api/market-data?{params}", timeout=timeout)
    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    data = _unwrap(payload)
    rows = data.get("market_data", []) if isinstance(data, Mapping) else []
    latest = rows[0] if rows and isinstance(rows[0], Mapping) else {}
    return {
        "success": bool(payload.get("success", True)) and bool(rows),
        "elapsed_seconds": round(elapsed, 3),
        "row_count": len(rows),
        "latest_date": str(latest.get("as_of_date", "")),
        "latest_close": latest.get("close"),
        "latest_data_id": str(latest.get("data_id", "")),
    }


def build_market_data_storage_audit(
    *,
    dsn: str,
    base_url: str = "",
    sample_security_id: str,
    sample_source_id: str,
    sample_data_type: str,
    timeout: float,
) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    def expect(condition: bool, check: str, error: str, **extra: Any) -> None:
        if not condition:
            failures.append({"check": check, "error": error, **extra})

    with _connect(dsn) as connection:
        with connection.cursor() as cursor:
            legacy_count = int(_fetch_one(cursor, "SELECT COUNT(*) FROM ai_quant.records WHERE collection = 'market_data'")[0] or 0)
            typed_count_estimate = _fetch_one(
                cursor,
                """
                SELECT GREATEST(
                    COALESCE((SELECT n_live_tup FROM pg_stat_user_tables WHERE schemaname = 'ai_quant' AND relname = 'market_data_bars'), 0),
                    COALESCE((SELECT reltuples::bigint FROM pg_class WHERE oid = 'ai_quant.market_data_bars'::regclass), 0)
                )::bigint
                """,
            )[0]
            min_date = _fetch_one(cursor, "SELECT as_of_date::text FROM ai_quant.market_data_bars ORDER BY as_of_date ASC LIMIT 1")[0]
            max_date = _fetch_one(cursor, "SELECT as_of_date::text FROM ai_quant.market_data_bars ORDER BY as_of_date DESC LIMIT 1")[0]
            view_rows = _fetch_all(
                cursor,
                """
                SELECT viewname
                FROM pg_views
                WHERE schemaname = 'ai_quant'
                  AND viewname IN ('market_data', 'market_data_records')
                ORDER BY viewname
                """,
            )
            index_rows = _fetch_all(
                cursor,
                """
                SELECT indexname
                FROM pg_indexes
                WHERE schemaname = 'ai_quant'
                  AND indexname IN (
                    'idx_ai_quant_market_data_security_date',
                    'idx_ai_quant_market_data_source',
                    'idx_ai_quant_market_data_bars_data_id',
                    'idx_ai_quant_market_data_bars_market_date',
                    'idx_ai_quant_market_data_bars_source_date',
                    'idx_ai_quant_market_data_bars_security_date',
                    'idx_ai_quant_market_data_bars_as_of_date'
                  )
                ORDER BY indexname
                """,
            )
            size_rows = _fetch_all(
                cursor,
                """
                SELECT 'market_data_bars' AS relname, pg_size_pretty(pg_total_relation_size('ai_quant.market_data_bars'::regclass)) AS total_size
                UNION ALL
                SELECT 'records' AS relname, pg_size_pretty(pg_total_relation_size('ai_quant.records'::regclass)) AS total_size
                ORDER BY relname
                """,
            )
            plan_rows = _fetch_all(
                cursor,
                """
                EXPLAIN (FORMAT JSON)
                SELECT b.data_id
                FROM ai_quant.market_data_bars AS b
                WHERE TRUE
                ORDER BY b.as_of_date DESC, b.data_id DESC
                LIMIT 10
                """,
            )

    views = [row[0] for row in view_rows]
    indexes = [row[0] for row in index_rows]
    sizes = {str(row[0]): str(row[1]) for row in size_rows}
    required_indexes = {
        "idx_ai_quant_market_data_bars_data_id",
        "idx_ai_quant_market_data_bars_market_date",
        "idx_ai_quant_market_data_bars_source_date",
        "idx_ai_quant_market_data_bars_security_date",
        "idx_ai_quant_market_data_bars_as_of_date",
    }
    obsolete_indexes = {"idx_ai_quant_market_data_security_date", "idx_ai_quant_market_data_source"}
    plan_json = plan_rows[0][0] if plan_rows else []
    plan_text = json.dumps(plan_json, ensure_ascii=False)

    api_smoke: dict[str, Any] = {"skipped": True}
    if base_url:
        api_smoke = _market_data_api_smoke(
            base_url,
            security_id=sample_security_id,
            source_id=sample_source_id,
            data_type=sample_data_type,
            timeout=timeout,
        )

    expect(legacy_count == 0, "legacy_market_data_records", "records.collection='market_data' must be empty", value=legacy_count)
    expect(int(typed_count_estimate or 0) > 0, "typed_market_data_bars", "market_data_bars must contain K-line bars", value=int(typed_count_estimate or 0))
    expect(views == ["market_data"], "market_data_views", "only typed ai_quant.market_data view should remain", value=views)
    expect(required_indexes.issubset(set(indexes)), "typed_indexes", "required typed market_data_bars indexes are missing", missing=sorted(required_indexes - set(indexes)))
    expect(not (obsolete_indexes & set(indexes)), "obsolete_jsonb_indexes", "obsolete records market_data indexes must not exist", value=sorted(obsolete_indexes & set(indexes)))
    uses_global_date_index = "idx_ai_quant_market_data_bars_as_of_date" in plan_text and (
        "Index Scan" in plan_text or "Index Only Scan" in plan_text
    )
    expect(uses_global_date_index, "latest_bars_query_plan", "latest bars query should use global as_of_date index", plan=plan_json)
    if base_url:
        expect(bool(api_smoke.get("success")), "market_data_api_smoke", "market data API must return typed K-line rows", value=api_smoke)

    passed = not failures
    return {
        "status": "passed" if passed else "failed",
        "passed": passed,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "production_boundary": "local_only_personal_production_market_data_storage_audit",
        "legacy_market_data_records": legacy_count,
        "typed_market_data_bars": {
            "estimated_count": int(typed_count_estimate or 0),
            "min_date": str(min_date or ""),
            "max_date": str(max_date or ""),
        },
        "views": views,
        "indexes": indexes,
        "sizes": sizes,
        "latest_bars_plan_contains_index": uses_global_date_index,
        "api_smoke": api_smoke,
        "warning_count": len(warnings),
        "failure_count": len(failures),
        "warnings": warnings,
        "failures": failures,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit typed-only market-data K-line storage.")
    parser.add_argument("--dsn", default=DEFAULT_DSN)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--sample-security-id", default="sec_000001")
    parser.add_argument("--sample-source-id", default="public_eod_market_data")
    parser.add_argument("--sample-data-type", default="eod")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    result = build_market_data_storage_audit(
        dsn=args.dsn,
        base_url=args.base_url,
        sample_security_id=args.sample_security_id,
        sample_source_id=args.sample_source_id,
        sample_data_type=args.sample_data_type,
        timeout=args.timeout,
    )
    _write_json(args.output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
