from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import struct
import sys
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services import PUBLIC_EOD_MARKET_DATA_SOURCE_ID
from app.market_data_storage import upsert_market_data_bar


RECORD_SIZE = 32


def normalize_symbol(value: str) -> str:
    symbol = str(value).strip().lower()
    symbol = re.sub(r"^(sh|sz|bj)", "", symbol)
    symbol = re.sub(r"\.(sh|sz|bj|ss|szse|sse|xshg|xshe|xbei)$", "", symbol)
    digits = re.sub(r"\D+", "", symbol)
    return digits[-6:] if len(digits) >= 6 else digits


def infer_exchange(symbol: str) -> str:
    clean = normalize_symbol(symbol)
    if clean.startswith(("60", "68", "90")):
        return "SSE"
    if clean.startswith(("00", "20", "30")):
        return "SZSE"
    if clean.startswith(("43", "83", "87", "92")):
        return "BSE"
    return "A"


def date_from_int(value: int) -> str:
    raw = str(value)
    if not re.fullmatch(r"\d{8}", raw):
        raise ValueError(f"invalid TDX date {value}")
    return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"


def market_data_id(security_id: str, as_of_date: str, data_type: str, source_id: str) -> str:
    raw = f"md_{source_id}_{security_id}_{as_of_date}_{data_type}"
    return re.sub(r"[^A-Za-z0-9_-]+", "_", raw).strip("_").lower()


def iter_day_files(root: Path, *, prefix: str = "", max_symbols: int = 0) -> Iterable[Path]:
    count = 0
    for file_path in sorted(root.glob("**/*.day")):
        symbol = normalize_symbol(file_path.stem)
        if not symbol:
            continue
        if prefix and not symbol.startswith(prefix):
            continue
        yield file_path
        count += 1
        if max_symbols and count >= max_symbols:
            break


def read_day_rows(file_path: Path, *, start_date: str, end_date: str, limit: int) -> list[dict[str, Any]]:
    data = file_path.read_bytes()
    if len(data) % RECORD_SIZE != 0:
        raise ValueError(f"invalid record length: {file_path}")
    symbol = normalize_symbol(file_path.stem)
    rows: list[dict[str, Any]] = []
    offsets = range(0, len(data), RECORD_SIZE) if limit else range(len(data) - RECORD_SIZE, -1, -RECORD_SIZE)
    for offset in offsets:
        raw_date, raw_open, raw_high, raw_low, raw_close, amount, volume, _reserved = struct.unpack("<IIIIIfII", data[offset : offset + RECORD_SIZE])
        trade_date = date_from_int(raw_date)
        if trade_date > end_date:
            continue
        if trade_date < start_date:
            if limit:
                continue
            break
        rows.append(
            {
                "symbol": symbol,
                "trade_date": trade_date,
                "open": raw_open / 100.0,
                "high": raw_high / 100.0,
                "low": raw_low / 100.0,
                "close": raw_close / 100.0,
                "volume": float(volume),
                "amount": float(amount),
            }
        )
        if limit and len(rows) >= limit:
            break
    if not limit:
        rows.reverse()
    return rows


def upsert_records(cursor: Any, rows: list[tuple[str, str, str]]) -> None:
    if not rows:
        return
    try:
        cursor.executemany(
            """
            INSERT INTO ai_quant.records (collection, item_id, payload, position)
            VALUES (%s, %s, %s::jsonb, NULL)
            ON CONFLICT (collection, item_id)
            DO UPDATE SET payload = EXCLUDED.payload, updated_at = now()
            """,
            rows,
        )
    except Exception:
        raise


def upsert_market_data_bars(cursor: Any, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    for payload in rows:
        upsert_market_data_bar(cursor, payload)


def import_vipdoc(args: argparse.Namespace) -> dict[str, Any]:
    try:
        import psycopg  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:
        raise RuntimeError("psycopg is required: python3 -m pip install 'psycopg[binary]>=3.1'") from exc

    root = Path(args.vipdoc_path)
    if not root.exists():
        raise RuntimeError(f"vipdoc path not found: {root}")

    started_at = datetime.now(timezone.utc).isoformat()
    symbol_count = 0
    created_or_updated_rows = 0
    failed_files: list[dict[str, str]] = []
    min_date = ""
    max_date = ""
    bar_batch: list[dict[str, Any]] = []
    issuer_security_batch: list[tuple[str, str, str]] = []
    rights_tag = {
        "license_class": "public_eod_reference",
        "training_allowed": False,
        "redistribution_allowed": False,
        "display_use": "allowed",
        "non_display_use": "allowed",
        "derived_data_use": "restricted",
    }

    with psycopg.connect(args.dsn) as connection:
        with connection.cursor() as cursor:
            for file_path in iter_day_files(root, prefix=args.symbol_prefix, max_symbols=args.max_symbols):
                symbol = normalize_symbol(file_path.stem)
                security_id = f"sec_{symbol}"
                issuer_id = f"issuer_{symbol}"
                try:
                    rows = read_day_rows(file_path, start_date=args.start_date, end_date=args.end_date, limit=args.limit_per_symbol)
                except Exception as exc:
                    failed_files.append({"file": str(file_path), "error": str(exc)})
                    continue
                if not rows:
                    continue
                symbol_count += 1
                now = datetime.now(timezone.utc).isoformat()
                issuer_payload = {
                    "issuer_id": issuer_id,
                    "legal_name": symbol,
                    "aliases": [symbol],
                    "market": ["A"],
                    "country": "CN",
                    "status": "active",
                    "created_at": now,
                    "updated_at": now,
                }
                security_payload = {
                    "security_id": security_id,
                    "issuer_id": issuer_id,
                    "ticker": symbol,
                    "figi": "",
                    "isin": "",
                    "exchange": infer_exchange(symbol),
                    "currency": "CNY",
                    "market": "A",
                    "status": "active",
                }
                issuer_security_batch.extend(
                    [
                        ("issuers", issuer_id, json.dumps(issuer_payload, ensure_ascii=False, sort_keys=True)),
                        ("securities", security_id, json.dumps(security_payload, ensure_ascii=False, sort_keys=True)),
                    ]
                )
                for row in rows:
                    trade_date = row["trade_date"]
                    min_date = trade_date if not min_date else min(min_date, trade_date)
                    max_date = trade_date if not max_date else max(max_date, trade_date)
                    data_id = market_data_id(security_id, trade_date, args.data_type, args.source_id)
                    payload = {
                        "data_id": data_id,
                        "security_id": security_id,
                        "source_id": args.source_id,
                        "market": "A",
                        "as_of_date": trade_date,
                        "data_type": args.data_type,
                        "currency": "CNY",
                        "open": row["open"],
                        "high": row["high"],
                        "low": row["low"],
                        "close": row["close"],
                        "adjusted_close": row["close"],
                        "volume": row["volume"],
                        "amount": row["amount"],
                        "rights_tag": rights_tag,
                        "created_at": now,
                    }
                    bar_batch.append(payload)
                    if len(bar_batch) >= args.batch_size:
                        upsert_records(cursor, issuer_security_batch)
                        upsert_market_data_bars(cursor, bar_batch)
                        connection.commit()
                        created_or_updated_rows += len(bar_batch)
                        print(f"imported symbols={symbol_count} rows={created_or_updated_rows} latest={symbol}", flush=True)
                        issuer_security_batch = []
                        bar_batch = []
            upsert_records(cursor, issuer_security_batch)
            upsert_market_data_bars(cursor, bar_batch)
            connection.commit()
            created_or_updated_rows += len(bar_batch)

    return {
        "started_at": started_at,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "vipdoc_path": str(root),
        "source_id": args.source_id,
        "data_type": args.data_type,
        "symbol_count": symbol_count,
        "created_or_updated_rows": created_or_updated_rows,
        "typed_bar_rows": created_or_updated_rows,
        "failed_file_count": len(failed_files),
        "failed_files": failed_files[:100],
        "min_date": min_date,
        "max_date": max_date,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Fast import local TDX vipdoc .day files into PostgreSQL typed K-line bars.")
    parser.add_argument("--dsn", default=os.environ.get("AI_QUANT_POSTGRES_DSN", "postgresql://ai_quant:ai_quant_dev_password@127.0.0.1:15432/ai_quant"))
    parser.add_argument("--vipdoc-path", default=os.environ.get("AI_QUANT_TDX_VIPDOC_PATH", "data/local/tdx/vipdoc"))
    parser.add_argument("--source-id", default=PUBLIC_EOD_MARKET_DATA_SOURCE_ID)
    parser.add_argument("--data-type", choices=["eod", "delayed"], default="eod")
    parser.add_argument("--start-date", default="1900-01-01")
    parser.add_argument("--end-date", default="2099-12-31")
    parser.add_argument("--limit-per-symbol", type=int, default=0, help="0 means no per-symbol row limit.")
    parser.add_argument("--symbol-prefix", default="")
    parser.add_argument("--max-symbols", type=int, default=0)
    parser.add_argument("--batch-size", type=int, default=5000)
    parser.add_argument("--output", default="artifacts/tdx-vipdoc-postgres-import.json")
    args = parser.parse_args()
    summary = import_vipdoc(args)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
