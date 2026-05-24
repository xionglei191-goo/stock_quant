from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services import SystemService
from app.store import PostgreSQLStore, SQLiteStore


def run_backfill(args: argparse.Namespace) -> dict[str, Any]:
    if args.postgres_dsn:
        store = PostgreSQLStore(args.postgres_dsn)
    else:
        store = SQLiteStore(args.state_db)
    service = SystemService(store)
    payload = {
        "market": args.market,
        "discover_universe": args.discover_universe,
        "symbols": args.symbols,
        "start_date": args.start_date,
        "end_date": args.end_date,
        "fallback_window_days": args.fallback_window_days,
        "offset": args.offset,
        "max_symbols": args.max_symbols,
        "dry_run": args.dry_run,
        "skip_existing": not args.no_skip_existing,
        "refresh_existing": args.refresh_existing,
        "include_etf": args.include_etf,
        "include_b_shares": args.include_b_shares,
        "symbol_prefix": args.symbol_prefix,
        "batch_id": args.batch_id,
    }
    result = service.market_data_backfill(payload, actor=args.actor)
    store.commit()
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill A-share and US EOD market data with gap detection.")
    parser.add_argument("--postgres-dsn", default=os.environ.get("AI_QUANT_POSTGRES_DSN", ""))
    parser.add_argument("--state-db", default=os.environ.get("AI_QUANT_STATE_DB", "data/ai_quant_state.sqlite"))
    parser.add_argument("--market", choices=["A", "U", "both"], default="both")
    parser.add_argument("--discover-universe", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--symbols", default="")
    parser.add_argument("--symbol-prefix", default="")
    parser.add_argument("--start-date", default="")
    parser.add_argument("--end-date", default="")
    parser.add_argument("--fallback-window-days", type=int, default=10)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--max-symbols", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-skip-existing", action="store_true")
    parser.add_argument("--refresh-existing", action="store_true")
    parser.add_argument("--include-etf", action="store_true")
    parser.add_argument("--include-b-shares", action="store_true")
    parser.add_argument("--batch-id", default="")
    parser.add_argument("--actor", default="market_data_backfill_cli")
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    result = run_backfill(args)
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
