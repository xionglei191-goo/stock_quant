from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services import PUBLIC_EOD_MARKET_DATA_SOURCE_ID


RIGHTS_TAG = {
    "license_class": "public_eod_reference",
    "training_allowed": False,
    "redistribution_allowed": False,
    "display_use": "allowed",
    "non_display_use": "allowed",
    "derived_data_use": "restricted",
}


def _safe_identifier(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", value.strip()).strip("_").lower()


def _normalize_symbol(value: str) -> str:
    symbol = str(value).strip().lower()
    symbol = re.sub(r"^(sh|sz|bj)", "", symbol)
    symbol = re.sub(r"\.(sh|sz|bj|ss|szse|sse|xshg|xshe|xbei)$", "", symbol)
    digits = re.sub(r"\D+", "", symbol)
    return digits[-6:] if len(digits) >= 6 else digits


def _baostock_code(symbol: str) -> str:
    clean = _normalize_symbol(symbol)
    if clean.startswith(("5", "6", "9")):
        return f"sh.{clean}"
    if clean.startswith(("4", "8")):
        return f"bj.{clean}"
    return f"sz.{clean}"


def _exchange(symbol: str) -> str:
    clean = _normalize_symbol(symbol)
    if clean.startswith(("5", "6", "9")):
        return "SSE"
    if clean.startswith(("4", "8")):
        return "BSE"
    return "SZSE"


def _is_active_a_share(code: str, name: str, stock_type: str, status: str, *, include_b_shares: bool) -> bool:
    symbol = _normalize_symbol(code)
    if len(symbol) != 6 or stock_type != "1" or status != "1":
        return False
    if not include_b_shares and symbol.startswith(("200", "900")):
        return False
    if name.upper().startswith(("B股", "B SHARE")):
        return False
    return symbol.startswith(("000", "001", "002", "003", "300", "301", "600", "601", "603", "605", "688", "689", "430", "830", "831", "832", "833", "834", "835", "836", "837", "838", "839", "870", "871", "872", "873", "920"))


def _market_data_id(security_id: str, as_of_date: str, data_type: str, source_id: str) -> str:
    return _safe_identifier(f"md_{source_id}_{security_id}_{as_of_date}_{data_type}")


def _next_date(value: str) -> str:
    return (date.fromisoformat(value) + timedelta(days=1)).isoformat()


def _fallback_start_date() -> str:
    return (date.today() - timedelta(days=10)).isoformat()


def _upsert(cursor: Any, collection: str, item_id: str, payload: dict[str, Any], *, update: bool = True) -> None:
    if update:
        cursor.execute(
            """
            INSERT INTO ai_quant.records (collection, item_id, payload, position)
            VALUES (%s, %s, %s::jsonb, NULL)
            ON CONFLICT (collection, item_id)
            DO UPDATE SET payload = EXCLUDED.payload, updated_at = now()
            """,
            (collection, item_id, json.dumps(payload, ensure_ascii=False, sort_keys=True)),
        )
        return
    cursor.execute(
        """
        INSERT INTO ai_quant.records (collection, item_id, payload, position)
        VALUES (%s, %s, %s::jsonb, NULL)
        ON CONFLICT (collection, item_id) DO NOTHING
        """,
        (collection, item_id, json.dumps(payload, ensure_ascii=False, sort_keys=True)),
    )


def _source_payload(source_id: str) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "source_type": "public_market_data",
        "description": "Public or locally provided A-share EOD market data; baostock is used only for incremental refresh after local TDX history.",
        "risk_level": "green",
        "field_mapping": {
            "security_id": "code",
            "as_of_date": "date",
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "adjusted_close": "close",
            "volume": "volume",
        },
        "field_whitelist": ["security_id", "as_of_date", "open", "high", "low", "close", "adjusted_close", "volume"],
        "provenance_ref": "local://data/local/tdx/vipdoc; baostock://query_history_k_data_plus",
        "source_tos_uri": "http://baostock.com/",
        "usage_scope": "public_or_local_eod_internal_research_backtest_risk",
        "collection_method": "local_file_or_public_api",
        "robots_policy": "reviewed_public_or_local_source",
        "review_owner_role": "数据工程",
        "rights_tag": RIGHTS_TAG,
    }


def _latest_date_for_symbol(cursor: Any, *, security_id: str, source_id: str, data_type: str) -> str:
    cursor.execute(
        """
        SELECT MAX(payload->>'as_of_date')
        FROM ai_quant.records
        WHERE collection = 'market_data'
          AND payload->>'security_id' = %s
          AND payload->>'source_id' = %s
          AND payload->>'data_type' = %s
        """,
        (security_id, source_id, data_type),
    )
    row = cursor.fetchone()
    return str(row[0] or "") if row else ""


def _symbols_from_db(cursor: Any, *, symbol_prefix: str = "", include_b_shares: bool = False) -> list[dict[str, str]]:
    cursor.execute(
        """
        SELECT payload->>'ticker', payload->>'security_id', payload->>'issuer_id', payload->>'exchange'
        FROM ai_quant.records
        WHERE collection = 'securities'
          AND payload->>'market' = 'A'
          AND COALESCE(payload->>'status', 'active') = 'active'
        ORDER BY payload->>'ticker'
        """
    )
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for ticker, security_id, issuer_id, exchange in cursor.fetchall():
        symbol = _normalize_symbol(str(ticker or security_id or ""))
        if len(symbol) != 6 or symbol in seen:
            continue
        if symbol_prefix and not symbol.startswith(symbol_prefix):
            continue
        if not include_b_shares and symbol.startswith(("200", "900")):
            continue
        seen.add(symbol)
        rows.append(
            {
                "symbol": symbol,
                "name": symbol,
                "security_id": str(security_id or f"sec_{symbol}"),
                "issuer_id": str(issuer_id or f"issuer_{symbol}"),
                "exchange": str(exchange or _exchange(symbol)),
            }
        )
    return rows


def _symbols_from_baostock(bs: Any, *, symbol_prefix: str = "", include_b_shares: bool = False) -> list[dict[str, str]]:
    result = bs.query_stock_basic()
    if result.error_code != "0":
        raise RuntimeError(f"baostock query_stock_basic failed: {result.error_code} {result.error_msg}")
    fields = list(getattr(result, "fields", []) or ["code", "code_name", "ipoDate", "outDate", "type", "status"])
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    while result.next():
        item = dict(zip(fields, result.get_row_data()))
        code = str(item.get("code") or "")
        name = str(item.get("code_name") or "")
        stock_type = str(item.get("type") or "")
        status = str(item.get("status") or "")
        symbol = _normalize_symbol(code)
        if symbol_prefix and not symbol.startswith(symbol_prefix):
            continue
        if not _is_active_a_share(code, name, stock_type, status, include_b_shares=include_b_shares):
            continue
        if symbol in seen:
            continue
        seen.add(symbol)
        rows.append(
            {
                "symbol": symbol,
                "name": name or symbol,
                "security_id": f"sec_{symbol}",
                "issuer_id": f"issuer_{symbol}",
                "exchange": _exchange(symbol),
            }
        )
    return rows


def _manual_symbols(value: str, *, symbol_prefix: str = "") -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in str(value or "").split(","):
        symbol = _normalize_symbol(item)
        if len(symbol) != 6 or symbol in seen:
            continue
        if symbol_prefix and not symbol.startswith(symbol_prefix):
            continue
        seen.add(symbol)
        rows.append(
            {
                "symbol": symbol,
                "name": symbol,
                "security_id": f"sec_{symbol}",
                "issuer_id": f"issuer_{symbol}",
                "exchange": _exchange(symbol),
            }
        )
    return rows


def _float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _fetch_rows(bs: Any, symbol: str, *, start_date: str, end_date: str, adjustflag: str) -> list[dict[str, Any]]:
    fields = "date,code,open,high,low,close,volume,amount"
    result = bs.query_history_k_data_plus(
        _baostock_code(symbol),
        fields,
        start_date=start_date,
        end_date=end_date,
        frequency="d",
        adjustflag=adjustflag,
    )
    if result.error_code != "0":
        raise RuntimeError(f"baostock query_history_k_data_plus failed: {result.error_code} {result.error_msg}")
    rows: list[dict[str, Any]] = []
    columns = fields.split(",")
    while result.next():
        item = dict(zip(columns, result.get_row_data()))
        close = _float(item.get("close"))
        if close <= 0:
            continue
        rows.append(
            {
                "as_of_date": str(item.get("date") or ""),
                "open": _float(item.get("open")),
                "high": _float(item.get("high")),
                "low": _float(item.get("low")),
                "close": close,
                "volume": _float(item.get("volume")),
                "amount": _float(item.get("amount")),
            }
        )
    return rows


def import_ashare_eod(args: argparse.Namespace) -> dict[str, Any]:
    try:
        import baostock as bs  # type: ignore[import-not-found]
        import psycopg  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:
        raise RuntimeError("baostock and psycopg are required in the active Python environment") from exc

    started_at = datetime.now(timezone.utc).isoformat()
    requested_end_date = args.end_date or date.today().isoformat()
    summary: dict[str, Any] = {
        "started_at": started_at,
        "source_id": args.source_id,
        "provider": "baostock",
        "source_boundary": "public_eod_incremental_refresh_for_local_research_and_simulated_analysis",
        "usage_boundary": "not_a_production_market_data_license_no_live_trading",
        "data_type": args.data_type,
        "adjustflag": args.adjustflag,
        "requested_end_date": requested_end_date,
        "symbol_count": 0,
        "queried_symbol_count": 0,
        "updated_symbol_count": 0,
        "created_or_updated_rows": 0,
        "empty_symbol_count": 0,
        "failed_symbol_count": 0,
        "failed_symbols": [],
        "min_date": "",
        "max_date": "",
        "symbol_results": [],
    }
    login = bs.login()
    if login.error_code != "0":
        raise RuntimeError(f"baostock login failed: {login.error_code} {login.error_msg}")
    try:
        with psycopg.connect(args.dsn) as connection:
            with connection.cursor() as cursor:
                _upsert(cursor, "sources", args.source_id, _source_payload(args.source_id), update=False)
                if args.symbols:
                    symbols = _manual_symbols(args.symbols, symbol_prefix=args.symbol_prefix)
                elif args.symbols_from_db:
                    symbols = _symbols_from_db(cursor, symbol_prefix=args.symbol_prefix, include_b_shares=args.include_b_shares)
                else:
                    symbols = _symbols_from_baostock(bs, symbol_prefix=args.symbol_prefix, include_b_shares=args.include_b_shares)
                if args.offset:
                    symbols = symbols[args.offset :]
                if args.max_symbols:
                    symbols = symbols[: args.max_symbols]
                summary["symbol_count"] = len(symbols)

                for index, item in enumerate(symbols, start=1):
                    symbol = item["symbol"]
                    security_id = item["security_id"]
                    issuer_id = item["issuer_id"]
                    latest = _latest_date_for_symbol(cursor, security_id=security_id, source_id=args.source_id, data_type=args.data_type)
                    start_date = args.start_date or (_next_date(latest) if latest else args.fallback_start_date)
                    if start_date > requested_end_date:
                        summary["symbol_results"].append(
                            {"symbol": symbol, "security_id": security_id, "status": "skipped_current", "start_date": start_date, "latest_existing_date": latest}
                        )
                        continue
                    summary["queried_symbol_count"] += 1
                    try:
                        rows = _fetch_rows(bs, symbol, start_date=start_date, end_date=requested_end_date, adjustflag=args.adjustflag)
                    except Exception as exc:
                        summary["failed_symbol_count"] += 1
                        failure = {"symbol": symbol, "security_id": security_id, "error_type": type(exc).__name__, "error": str(exc)}
                        summary["failed_symbols"].append(failure)
                        summary["symbol_results"].append({**failure, "status": "failed", "start_date": start_date})
                        if args.commit_every and index % args.commit_every == 0:
                            connection.commit()
                        continue
                    now = datetime.now(timezone.utc).isoformat()
                    if not rows:
                        summary["empty_symbol_count"] += 1
                        summary["symbol_results"].append({"symbol": symbol, "security_id": security_id, "status": "empty", "start_date": start_date})
                        continue
                    _upsert(
                        cursor,
                        "issuers",
                        issuer_id,
                        {
                            "issuer_id": issuer_id,
                            "legal_name": item.get("name") or symbol,
                            "aliases": [symbol, item.get("name") or symbol],
                            "market": ["A"],
                            "country": "CN",
                            "status": "active",
                            "created_at": now,
                            "updated_at": now,
                        },
                        update=False,
                    )
                    _upsert(
                        cursor,
                        "securities",
                        security_id,
                        {
                            "security_id": security_id,
                            "issuer_id": issuer_id,
                            "ticker": symbol,
                            "figi": "",
                            "isin": "",
                            "exchange": item.get("exchange") or _exchange(symbol),
                            "currency": "CNY",
                            "market": "A",
                            "status": "active",
                            "security_type": "stock",
                        },
                        update=False,
                    )
                    for row in rows:
                        as_of_date = row["as_of_date"]
                        data_id = _market_data_id(security_id, as_of_date, args.data_type, args.source_id)
                        _upsert(
                            cursor,
                            "market_data",
                            data_id,
                            {
                                "data_id": data_id,
                                "security_id": security_id,
                                "source_id": args.source_id,
                                "market": "A",
                                "as_of_date": as_of_date,
                                "data_type": args.data_type,
                                "currency": "CNY",
                                "open": row["open"],
                                "high": row["high"],
                                "low": row["low"],
                                "close": row["close"],
                                "adjusted_close": row["close"],
                                "volume": row["volume"],
                                "rights_tag": RIGHTS_TAG,
                                "created_at": now,
                            },
                        )
                        summary["created_or_updated_rows"] += 1
                        summary["min_date"] = as_of_date if not summary["min_date"] else min(summary["min_date"], as_of_date)
                        summary["max_date"] = as_of_date if not summary["max_date"] else max(summary["max_date"], as_of_date)
                    summary["updated_symbol_count"] += 1
                    summary["symbol_results"].append(
                        {
                            "symbol": symbol,
                            "security_id": security_id,
                            "status": "updated",
                            "start_date": start_date,
                            "row_count": len(rows),
                            "min_date": rows[0]["as_of_date"],
                            "max_date": rows[-1]["as_of_date"],
                        }
                    )
                    if args.commit_every and index % args.commit_every == 0:
                        connection.commit()
                        print(f"imported symbols={index}/{len(symbols)} rows={summary['created_or_updated_rows']} latest={symbol}", flush=True)
                    if args.sleep_seconds > 0:
                        time.sleep(args.sleep_seconds)
                connection.commit()
    finally:
        bs.logout()

    summary["completed_at"] = datetime.now(timezone.utc).isoformat()
    summary["status"] = "passed" if summary["failed_symbol_count"] == 0 else "partial"
    summary["failed_symbols"] = summary["failed_symbols"][:200]
    if len(summary["symbol_results"]) > args.artifact_symbol_limit:
        summary["symbol_results_truncated"] = len(summary["symbol_results"]) - args.artifact_symbol_limit
        summary["symbol_results"] = summary["symbol_results"][: args.artifact_symbol_limit]
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Incrementally import A-share EOD prices from baostock into PostgreSQL.")
    parser.add_argument("--dsn", default=os.environ.get("AI_QUANT_POSTGRES_DSN", "postgresql://ai_quant:ai_quant_dev_password@127.0.0.1:15432/ai_quant"))
    parser.add_argument("--source-id", default=PUBLIC_EOD_MARKET_DATA_SOURCE_ID)
    parser.add_argument("--data-type", choices=["eod", "delayed"], default="eod")
    parser.add_argument("--symbols", default="", help="Comma-separated A-share symbols. If omitted, the baostock active stock universe is used.")
    parser.add_argument("--symbols-from-db", action="store_true", help="Use active A-share securities already registered in PostgreSQL.")
    parser.add_argument("--symbol-prefix", default="")
    parser.add_argument("--include-b-shares", action="store_true")
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--max-symbols", type=int, default=0)
    parser.add_argument("--start-date", default="", help="Optional YYYY-MM-DD. Defaults to last DB date + 1 for each symbol.")
    parser.add_argument("--fallback-start-date", default=_fallback_start_date(), help="Used only when a symbol has no existing DB market-data rows.")
    parser.add_argument("--end-date", default=date.today().isoformat())
    parser.add_argument("--adjustflag", choices=["1", "2", "3"], default="3", help="baostock adjustflag; 3 keeps unadjusted prices to match local TDX raw EOD.")
    parser.add_argument("--commit-every", type=int, default=100)
    parser.add_argument("--sleep-seconds", type=float, default=0.0)
    parser.add_argument("--artifact-symbol-limit", type=int, default=500)
    parser.add_argument("--output", default="artifacts/ashare-eod-baostock-import.json")
    args = parser.parse_args()
    result = import_ashare_eod(args)
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
