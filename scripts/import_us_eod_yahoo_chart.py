from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import json
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


SOURCE_ID = "yahoo_chart_us_eod"


def _safe_identifier(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", value.strip()).strip("_").lower()


def _period(value: str) -> int:
    return int(datetime.combine(date.fromisoformat(value), datetime.min.time(), tzinfo=timezone.utc).timestamp())


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            loaded = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return loaded if isinstance(loaded, dict) else {}
    return {}


def _yahoo_chart_symbol_candidates(ticker: str) -> list[str]:
    raw = str(ticker or "").strip().upper().replace("/", "-")
    candidates = [raw]
    if "." in raw:
        candidates.append(raw.replace(".", "-"))
    if "$" in raw:
        candidates.append(raw.replace("$", "-P"))
        candidates.append(raw.replace("$", "-"))
    if raw.endswith("$"):
        candidates.append(raw.rstrip("$"))
    return [item for item in dict.fromkeys(candidates) if item]


def _fetch_chart(ticker: str, *, start_date: str, end_date: str, user_agent: str, timeout: float) -> dict[str, Any]:
    params = {
        "period1": _period(start_date),
        "period2": _period(end_date) + 86400,
        "interval": "1d",
        "events": "history",
        "includeAdjustedClose": "true",
    }
    errors: list[str] = []
    saw_empty_payload = False
    for yahoo_symbol in _yahoo_chart_symbol_candidates(ticker):
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}?{urlencode(params)}"
        request = Request(url, headers={"User-Agent": user_agent, "Accept": "application/json"})
        try:
            with urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            errors.append(f"{yahoo_symbol}: {type(exc).__name__}: {exc}")
            continue
        error = payload.get("chart", {}).get("error")
        if error:
            errors.append(f"{yahoo_symbol}: {error}")
            continue
        result = (payload.get("chart", {}).get("result") or [None])[0]
        if not result or not result.get("timestamp"):
            saw_empty_payload = True
            continue
        return result
    if saw_empty_payload:
        return {"timestamp": [], "indicators": {}}
    raise RuntimeError("; ".join(errors) or f"Yahoo chart returned no result for {ticker}")


def _rows_from_chart(ticker: str, chart: dict[str, Any]) -> list[dict[str, Any]]:
    timestamps = chart.get("timestamp") or []
    quote = ((chart.get("indicators") or {}).get("quote") or [{}])[0]
    adjclose = ((chart.get("indicators") or {}).get("adjclose") or [{}])[0].get("adjclose") or []
    rows: list[dict[str, Any]] = []
    for index, timestamp in enumerate(timestamps):
        close = quote.get("close", [None] * len(timestamps))[index]
        if close is None:
            continue
        rows.append(
            {
                "ticker": ticker.upper(),
                "as_of_date": datetime.fromtimestamp(int(timestamp), tz=timezone.utc).date().isoformat(),
                "open": float((quote.get("open") or [0.0] * len(timestamps))[index] or 0.0),
                "high": float((quote.get("high") or [0.0] * len(timestamps))[index] or 0.0),
                "low": float((quote.get("low") or [0.0] * len(timestamps))[index] or 0.0),
                "close": float(close),
                "adjusted_close": float((adjclose or [close] * len(timestamps))[index] or close),
                "volume": float((quote.get("volume") or [0.0] * len(timestamps))[index] or 0.0),
            }
        )
    return rows


def _market_data_id(security_id: str, as_of_date: str) -> str:
    return _safe_identifier(f"md_{SOURCE_ID}_{security_id}_{as_of_date}_eod")


def _next_date(value: str) -> str:
    return (date.fromisoformat(value) + timedelta(days=1)).isoformat()


def _manual_ticker_records(tickers: list[str]) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    seen: set[str] = set()
    for ticker in tickers:
        ticker = ticker.strip().upper()
        if not ticker or ticker in seen:
            continue
        safe = _safe_identifier(ticker.lower())
        records.append(
            {
                "ticker": ticker,
                "issuer_id": f"issuer_{safe}",
                "security_id": f"security_{safe}_us",
                "legal_name": ticker,
                "exchange": "US",
                "currency": "USD",
                "source": "manual_tickers",
            }
        )
        seen.add(ticker)
    return records


def _security_preference_score(record: dict[str, str]) -> int:
    ticker = record["ticker"]
    safe = _safe_identifier(ticker.lower())
    security_id = record["security_id"]
    score = 0
    if security_id == f"security_{safe}_us":
        score += 40
    if security_id == f"security_us_{safe}":
        score += 30
    if record.get("legal_name") and record["legal_name"] != ticker:
        score += 5
    if record.get("issuer_id"):
        score += 3
    if record.get("exchange"):
        score += 1
    return score


def _ticker_records_from_db(
    cursor: Any,
    *,
    ticker_filter: set[str] | None = None,
    offset: int = 0,
    max_tickers: int = 0,
) -> list[dict[str, str]]:
    clauses = [
        "s.collection = 'securities'",
        "s.payload->>'market' = 'U'",
        "COALESCE(s.payload->>'status', 'active') = 'active'",
        "COALESCE(s.payload->>'market_data_refresh_scope', 'in_scope') = 'in_scope'",
        "COALESCE(s.payload->>'ticker', '') <> ''",
    ]
    params: list[Any] = []
    if ticker_filter:
        clauses.append("upper(s.payload->>'ticker') = ANY(%s)")
        params.append(sorted(ticker_filter))
    cursor.execute(
        f"""
        SELECT
            s.item_id,
            s.payload,
            i.payload
        FROM ai_quant.records AS s
        LEFT JOIN ai_quant.records AS i
          ON i.collection = 'issuers'
         AND i.item_id = s.payload->>'issuer_id'
        WHERE {' AND '.join(clauses)}
        ORDER BY upper(s.payload->>'ticker'), s.item_id
        """,
        tuple(params),
    )
    by_ticker: dict[str, dict[str, str]] = {}
    for item_id, security_payload, issuer_payload in cursor.fetchall():
        sec = _payload(security_payload)
        issuer = _payload(issuer_payload)
        ticker = str(sec.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        current = {
            "ticker": ticker,
            "issuer_id": str(sec.get("issuer_id") or issuer.get("issuer_id") or ""),
            "security_id": str(sec.get("security_id") or item_id),
            "legal_name": str(issuer.get("legal_name") or sec.get("name") or ticker),
            "exchange": str(sec.get("exchange") or issuer.get("exchange") or "US"),
            "currency": str(sec.get("currency") or "USD"),
            "source": "postgres_securities",
        }
        existing = by_ticker.get(ticker)
        if existing is None or _security_preference_score(current) > _security_preference_score(existing):
            by_ticker[ticker] = current
    records = [by_ticker[ticker] for ticker in sorted(by_ticker)]
    if offset:
        records = records[max(0, offset) :]
    if max_tickers:
        records = records[: max(0, max_tickers)]
    return records


def _latest_dates_for_records(cursor: Any, *, security_ids: list[str], data_type: str = "eod") -> dict[str, str]:
    if not security_ids:
        return {}
    cursor.execute(
        """
        SELECT security_id, MAX(as_of_date)::text
        FROM ai_quant.market_data_bars
        WHERE security_id = ANY(%s)
          AND source_id = %s
          AND data_type = %s
        GROUP BY security_id
        """,
        (security_ids, SOURCE_ID, data_type),
    )
    return {str(security_id): str(latest or "") for security_id, latest in cursor.fetchall()}


def _upsert(cursor: Any, collection: str, item_id: str, payload: dict[str, Any]) -> None:
    cursor.execute(
        """
        INSERT INTO ai_quant.records (collection, item_id, payload, position)
        VALUES (%s, %s, %s::jsonb, NULL)
        ON CONFLICT (collection, item_id)
        DO UPDATE SET payload = EXCLUDED.payload, updated_at = now()
        """,
        (collection, item_id, json.dumps(payload, ensure_ascii=False, sort_keys=True)),
    )


def _upsert_market_data_bar(cursor: Any, payload: dict[str, Any]) -> None:
    cursor.execute(
        """
        INSERT INTO ai_quant.market_data_bars (
            security_id,
            source_id,
            data_type,
            as_of_date,
            market,
            currency,
            open,
            high,
            low,
            close,
            adjusted_close,
            volume,
            amount,
            data_id,
            rights_tag,
            payload,
            created_at
        )
        VALUES (%s, %s, %s, %s::date, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s)
        ON CONFLICT (security_id, source_id, data_type, as_of_date)
        DO UPDATE SET
            market = EXCLUDED.market,
            currency = EXCLUDED.currency,
            open = EXCLUDED.open,
            high = EXCLUDED.high,
            low = EXCLUDED.low,
            close = EXCLUDED.close,
            adjusted_close = EXCLUDED.adjusted_close,
            volume = EXCLUDED.volume,
            amount = EXCLUDED.amount,
            data_id = EXCLUDED.data_id,
            rights_tag = EXCLUDED.rights_tag,
            payload = EXCLUDED.payload,
            updated_at = now()
        """,
        (
            payload["security_id"],
            payload["source_id"],
            payload["data_type"],
            payload["as_of_date"],
            payload["market"],
            payload.get("currency", ""),
            payload.get("open", 0.0),
            payload.get("high", 0.0),
            payload.get("low", 0.0),
            payload["close"],
            payload.get("adjusted_close", payload["close"]),
            payload.get("volume", 0.0),
            payload.get("amount", 0.0),
            payload["data_id"],
            json.dumps(payload.get("rights_tag", {}), ensure_ascii=False, sort_keys=True),
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
            payload.get("created_at"),
        ),
    )


def import_us_eod(args: argparse.Namespace) -> dict[str, Any]:
    import psycopg

    started_at = datetime.now(timezone.utc).isoformat()
    rights_tag = {
        "license_class": "candidate_us_eod_reference",
        "training_allowed": False,
        "redistribution_allowed": False,
        "display_use": "allowed",
        "non_display_use": "restricted",
        "derived_data_use": "restricted",
    }
    source_payload = {
        "source_id": SOURCE_ID,
        "source_type": "public_market_data",
        "description": "Yahoo Finance chart endpoint US EOD/delayed market data for local research and simulated portfolio analysis only.",
        "risk_level": "yellow",
        "field_mapping": {
            "ticker": "symbol",
            "as_of_date": "timestamp",
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "adjusted_close": "adjclose",
            "volume": "volume",
        },
        "field_whitelist": ["ticker", "as_of_date", "open", "high", "low", "close", "adjusted_close", "volume"],
        "retention_policy": "cache_for_local_research_refreshable",
        "cache_ttl_days": 7,
        "provenance_ref": "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}",
        "usage_scope": "local_research_simulated_portfolio_only_not_production_market_data_license",
        "collection_method": "public_chart_endpoint",
        "robots_policy": "needs_periodic_review",
        "review_cadence": "quarterly",
        "review_owner_role": "数据工程",
        "source_tos_uri": "https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html",
        "rights_tag": rights_tag,
    }
    summary = {
        "started_at": started_at,
        "source_id": SOURCE_ID,
        "source_boundary": "candidate_public_reference_for_local_research_only",
        "usage_boundary": "not_a_production_market_data_license_no_live_trading",
        "tickers": [],
        "status": "passed",
        "source_mode": "postgres_securities" if args.tickers_from_db else "manual_tickers",
        "universe_count": 0,
        "offset": max(0, int(args.offset or 0)),
        "max_tickers": max(0, int(args.max_tickers or 0)),
        "symbol_count": 0,
        "created_or_updated_rows": 0,
        "typed_bar_rows": 0,
        "skipped_symbol_count": 0,
        "failed": [],
        "failure_count": 0,
        "min_date": "",
        "max_date": "",
    }
    with psycopg.connect(args.dsn) as connection:
        with connection.cursor() as cursor:
            _upsert(cursor, "sources", SOURCE_ID, source_payload)
            ticker_filter = {item.strip().upper() for item in str(args.ticker_filter or "").split(",") if item.strip()}
            if args.tickers_from_db:
                all_records = _ticker_records_from_db(cursor, ticker_filter=ticker_filter or None)
                summary["universe_count"] = len(all_records)
                ticker_records = all_records[summary["offset"] :]
                if summary["max_tickers"]:
                    ticker_records = ticker_records[: summary["max_tickers"]]
            else:
                ticker_records = _manual_ticker_records(args.tickers)
                summary["universe_count"] = len(ticker_records)
            summary["symbol_count"] = len(ticker_records)
            latest_by_security = _latest_dates_for_records(cursor, security_ids=[record["security_id"] for record in ticker_records])
            for ticker_record in ticker_records:
                ticker = ticker_record["ticker"].strip().upper()
                issuer_id = ticker_record["issuer_id"]
                security_id = ticker_record["security_id"]
                latest = latest_by_security.get(security_id, "")
                start_date = args.start_date
                if latest:
                    start_date = max(start_date, _next_date(latest))
                if start_date > args.end_date:
                    summary["skipped_symbol_count"] += 1
                    summary["tickers"].append(
                        {
                            "ticker": ticker,
                            "security_id": security_id,
                            "issuer_id": issuer_id,
                            "row_count": 0,
                            "status": "skipped_current",
                            "latest_existing_date": latest,
                            "start_date": start_date,
                        }
                    )
                    continue
                try:
                    chart = _fetch_chart(ticker, start_date=start_date, end_date=args.end_date, user_agent=args.user_agent, timeout=args.timeout)
                    rows = _rows_from_chart(ticker, chart)
                except Exception as exc:
                    summary["failed"].append({"ticker": ticker, "security_id": security_id, "error": str(exc), "error_type": type(exc).__name__})
                    continue
                now = datetime.now(timezone.utc).isoformat()
                if not args.tickers_from_db:
                    _upsert(
                        cursor,
                        "issuers",
                        issuer_id,
                        {
                            "issuer_id": issuer_id,
                            "legal_name": ticker_record.get("legal_name") or ticker,
                            "aliases": [ticker],
                            "market": ["U"],
                            "country": "US",
                            "status": "active",
                            "created_at": now,
                            "updated_at": now,
                        },
                    )
                    _upsert(
                        cursor,
                        "securities",
                        security_id,
                        {
                            "security_id": security_id,
                            "issuer_id": issuer_id,
                            "ticker": ticker,
                            "figi": "",
                            "isin": "",
                            "exchange": ticker_record.get("exchange") or "US",
                            "currency": ticker_record.get("currency") or "USD",
                            "market": "U",
                            "status": "active",
                        },
                    )
                for row in rows:
                    as_of_date = row["as_of_date"]
                    summary["min_date"] = as_of_date if not summary["min_date"] else min(summary["min_date"], as_of_date)
                    summary["max_date"] = as_of_date if not summary["max_date"] else max(summary["max_date"], as_of_date)
                    data_id = _market_data_id(security_id, as_of_date)
                    market_payload = {
                        "data_id": data_id,
                        "security_id": security_id,
                        "source_id": SOURCE_ID,
                        "market": "U",
                        "as_of_date": as_of_date,
                        "data_type": "eod",
                        "currency": ticker_record.get("currency") or "USD",
                        "open": row["open"],
                        "high": row["high"],
                        "low": row["low"],
                        "close": row["close"],
                        "adjusted_close": row["adjusted_close"],
                        "volume": row["volume"],
                        "rights_tag": rights_tag,
                        "created_at": now,
                    }
                    _upsert_market_data_bar(cursor, market_payload)
                connection.commit()
                summary["tickers"].append({"ticker": ticker, "security_id": security_id, "issuer_id": issuer_id, "row_count": len(rows), "status": "updated" if rows else "empty", "start_date": start_date})
                summary["created_or_updated_rows"] += len(rows)
                summary["typed_bar_rows"] += len(rows)
    summary["completed_at"] = datetime.now(timezone.utc).isoformat()
    summary["failure_count"] = len(summary["failed"])
    if summary["failure_count"] and len(summary["tickers"]) == 0:
        summary["status"] = "failed"
    elif summary["failure_count"]:
        summary["status"] = "partial"
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Import US EOD prices from Yahoo chart endpoint for local research/simulated analysis.")
    parser.add_argument("--dsn", default="postgresql://ai_quant:ai_quant_dev_password@127.0.0.1:15432/ai_quant")
    parser.add_argument("--tickers", default="AAPL,MSFT,NVDA,TSLA,SPY")
    parser.add_argument("--tickers-from-db", action="store_true", help="Read the active US ticker universe from ai_quant.records(securities) and preserve existing security/issuer IDs.")
    parser.add_argument("--ticker-filter", default="", help="Optional comma-separated ticker filter when --tickers-from-db is used.")
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--max-tickers", type=int, default=0)
    parser.add_argument("--start-date", default="2025-01-01")
    parser.add_argument("--end-date", default=date.today().isoformat())
    parser.add_argument("--user-agent", default="company-intelligence-platform/0.1 contact@example.com")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    args.tickers = [item.strip() for item in str(args.tickers).split(",") if item.strip()]
    result = import_us_eod(args)
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    if result.get("status") == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
