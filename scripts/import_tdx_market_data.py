from __future__ import annotations

import argparse
from datetime import date, timedelta
import json
from pathlib import Path
from typing import Any, Callable, Mapping

from app.errors import ValidationError
from app.services import PUBLIC_EOD_MARKET_DATA_SOURCE_ID, SystemService
from app.store import SQLiteStore
from app.tdx_market_data import TDXMarketDataAdapter, TDXVipdocAdapter


def run_tdx_incremental_import(
    state_db: str | Path,
    *,
    symbols: list[str],
    security_map: Mapping[str, Any] | None = None,
    source_format: str = "duckdb",
    tdx_duckdb_path: str | Path | None = None,
    vipdoc_path: str | Path | None = None,
    start_date: str = "",
    end_date: str = "2099-12-31",
    limit_per_symbol: int = 10000,
    data_type: str = "eod",
    source_id: str = PUBLIC_EOD_MARKET_DATA_SOURCE_ID,
    dry_run: bool = False,
    skip_existing: bool = True,
    duckdb_connect: Callable[[str, bool], Any] | None = None,
) -> dict[str, Any]:
    if not symbols:
        raise ValidationError("symbols are required")
    service = SystemService(SQLiteStore(state_db))
    service.seed_default_sources(actor="tdx_incremental_import")
    if tdx_duckdb_path:
        service.tdx_market_data = TDXMarketDataAdapter(path=tdx_duckdb_path, connect=duckdb_connect)
    elif duckdb_connect:
        service.tdx_market_data = TDXMarketDataAdapter(connect=duckdb_connect)
    if vipdoc_path:
        service.tdx_vipdoc = TDXVipdocAdapter(path=vipdoc_path)

    security_map = dict(security_map or {})
    source_format = source_format.strip().lower() or "duckdb"
    results: list[dict[str, Any]] = []
    totals = {"created_count": 0, "skipped_count": 0, "failed_count": 0, "source_rows": 0}
    for symbol in symbols:
        clean_symbol = service._normalize_tdx_symbol(symbol)
        symbol_start_date = start_date or _next_start_date_for_symbol(service, clean_symbol, security_map, source_id=source_id, data_type=data_type)
        payload = {
            "source_format": source_format,
            "symbols": [clean_symbol],
            "security_map": security_map,
            "source_id": source_id,
            "start_date": symbol_start_date,
            "end_date": end_date,
            "limit": limit_per_symbol,
            "data_type": data_type,
            "skip_existing": skip_existing,
            "batch_id": f"tdx_incremental_{clean_symbol}_{symbol_start_date}_{end_date}",
        }
        if dry_run:
            preview = service.tdx_market_data_preview(payload)
            row = {
                "symbol": clean_symbol,
                "start_date": symbol_start_date,
                "end_date": end_date,
                "source_rows": preview["count"],
                "created_count": 0,
                "skipped_count": 0,
                "failed_count": 0,
                "dry_run": True,
                "adapter": preview["adapter"],
            }
        else:
            imported = service.import_tdx_market_data(payload, actor="tdx_incremental_import")
            row = {
                "symbol": clean_symbol,
                "start_date": symbol_start_date,
                "end_date": end_date,
                "source_rows": imported["source_rows"],
                "created_count": imported["created_count"],
                "skipped_count": imported["skipped_count"],
                "failed_count": imported["failed_count"],
                "errors": imported["errors"][:20],
                "dry_run": False,
                "adapter": imported["adapter"],
            }
        for key in totals:
            totals[key] += int(row.get(key, 0))
        results.append(row)
    service.store.commit()
    return {
        "state_db": str(state_db),
        "source_format": source_format,
        "data_type": data_type,
        "dry_run": dry_run,
        "symbols": len(results),
        **totals,
        "results": results,
    }


def _next_start_date_for_symbol(
    service: SystemService,
    symbol: str,
    security_map: Mapping[str, Any],
    *,
    source_id: str,
    data_type: str,
) -> str:
    security = service._resolve_tdx_security(symbol, security_map)
    if security is None:
        return "1900-01-01"
    dates = [
        date.fromisoformat(point.as_of_date)
        for point in service.store.market_data.values()
        if point.security_id == security.security_id and point.source_id == source_id and point.data_type == data_type
    ]
    if not dates:
        return "1900-01-01"
    return (max(dates) + timedelta(days=1)).isoformat()


def _load_security_map(value: str, file_path: str) -> dict[str, str]:
    if file_path:
        payload = json.loads(Path(file_path).read_text(encoding="utf-8"))
    elif value:
        payload = json.loads(value)
    else:
        payload = {}
    if not isinstance(payload, dict):
        raise ValidationError("security map must be a JSON object")
    return {str(key): str(item) for key, item in payload.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description="Incrementally import local TongDaXin EOD market data into a SQLite AI Quant state DB.")
    parser.add_argument("state_db", help="Path to AI_QUANT_DB SQLite state file")
    parser.add_argument("--symbols", required=True, help="Comma-separated symbols, for example 600000,000001")
    parser.add_argument("--security-map", default="", help='JSON object, for example {"600000":"sec_600000"}')
    parser.add_argument("--security-map-file", default="", help="Path to a JSON symbol->security_id map")
    parser.add_argument("--source-format", choices=["duckdb", "vipdoc"], default="duckdb")
    parser.add_argument("--tdx-duckdb-path", default="", help="Override AI_QUANT_TDX_DUCKDB_PATH")
    parser.add_argument("--vipdoc-path", default="", help="Override AI_QUANT_TDX_VIPDOC_PATH")
    parser.add_argument("--start-date", default="", help="Optional YYYY-MM-DD. Defaults to last imported date + 1 per symbol.")
    parser.add_argument("--end-date", default="2099-12-31")
    parser.add_argument("--limit-per-symbol", type=int, default=10000)
    parser.add_argument("--data-type", choices=["eod", "delayed"], default="eod")
    parser.add_argument("--source-id", default=PUBLIC_EOD_MARKET_DATA_SOURCE_ID)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-skip-existing", action="store_true")
    args = parser.parse_args()
    summary = run_tdx_incremental_import(
        args.state_db,
        symbols=[item.strip() for item in args.symbols.split(",") if item.strip()],
        security_map=_load_security_map(args.security_map, args.security_map_file),
        source_format=args.source_format,
        tdx_duckdb_path=args.tdx_duckdb_path or None,
        vipdoc_path=args.vipdoc_path or None,
        start_date=args.start_date,
        end_date=args.end_date,
        limit_per_symbol=args.limit_per_symbol,
        data_type=args.data_type,
        source_id=args.source_id,
        dry_run=args.dry_run,
        skip_existing=not args.no_skip_existing,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
