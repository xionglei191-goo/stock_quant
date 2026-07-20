from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import statistics
from typing import Any


DEFAULT_DSN = "postgresql://ai_quant:ai_quant_dev_password@127.0.0.1:15432/ai_quant"
TABLES = {"legacy": "market_data_bars", "compact": "market_data_bars_v2"}


def _connect(dsn: str) -> Any:
    try:
        import psycopg  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:
        raise RuntimeError("psycopg is required; install the postgres project extra") from exc
    return psycopg.connect(dsn)


def _index_names(plan: Any) -> list[str]:
    names: list[str] = []
    if isinstance(plan, dict):
        if plan.get("Index Name"):
            names.append(str(plan["Index Name"]))
        for value in plan.values():
            names.extend(_index_names(value))
    elif isinstance(plan, list):
        for value in plan:
            names.extend(_index_names(value))
    return sorted(set(names))


def benchmark(dsn: str, *, repeats: int = 5) -> dict[str, Any]:
    if repeats < 2:
        raise ValueError("repeats must be at least 2 so the cold run can be discarded")
    scenarios = {
        "security_history": ("WHERE security_id = %s AND source_id = %s AND data_type = 'eod' ORDER BY as_of_date DESC LIMIT 1000", ("sec_000001", "public_eod_market_data")),
        "global_latest": ("ORDER BY as_of_date DESC, data_id DESC LIMIT 50", ()),
        "market_latest": ("WHERE market = 'A' ORDER BY as_of_date DESC, security_id LIMIT 100", ()),
        "source_latest": ("WHERE source_id = %s AND data_type = 'eod' ORDER BY as_of_date DESC LIMIT 100", ("public_eod_market_data",)),
        "data_id_lookup": ("WHERE data_id = %s LIMIT 1", ("md_public_eod_market_data_sec_000001_2026_07_17_eod",)),
    }
    results: dict[str, Any] = {}
    with _connect(dsn) as connection:
        with connection.cursor() as cursor:
            for scenario, (suffix, params) in scenarios.items():
                scenario_result: dict[str, Any] = {}
                for label, table in TABLES.items():
                    elapsed: list[float] = []
                    indexes: set[str] = set()
                    for _ in range(repeats):
                        cursor.execute(
                            f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) SELECT data_id FROM ai_quant.{table} {suffix}",
                            params,
                        )
                        payload = cursor.fetchone()[0]
                        root = payload[0]
                        elapsed.append(float(root.get("Execution Time", 0.0)))
                        indexes.update(_index_names(root.get("Plan", {})))
                    warm = elapsed[1:]
                    scenario_result[label] = {
                        "all_execution_ms": elapsed,
                        "warm_median_ms": round(statistics.median(warm), 3),
                        "warm_max_ms": round(max(warm), 3),
                        "indexes": sorted(indexes),
                    }
                old_ms = scenario_result["legacy"]["warm_median_ms"]
                new_ms = scenario_result["compact"]["warm_median_ms"]
                limit_ms = max(old_ms * 1.2, old_ms + 2.0)
                scenario_result["compact_vs_legacy_ratio"] = round(new_ms / old_ms, 3) if old_ms else 0.0
                scenario_result["passed"] = new_ms <= limit_ms
                results[scenario] = scenario_result
    return {
        "status": "passed" if all(item["passed"] for item in results.values()) else "failed",
        "passed": all(item["passed"] for item in results.values()),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repeats": repeats,
        "scenarios": results,
        "environment": "local-postgresql-comparison",
        "owner_group": "Platform and Quality",
        "classification": "local-only",
        "contains_sensitive_data": False,
        "acceptable_for_non_local_release": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare legacy and compact market-data query plans and bounded latency.")
    parser.add_argument("--dsn", default=os.environ.get("AI_QUANT_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--output", default="artifacts/t602-market-data-storage-benchmark.json")
    args = parser.parse_args()
    result = benchmark(args.dsn, repeats=args.repeats)
    if args.output:
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
