from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
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
    return int(time.mktime(time.strptime(value, "%Y-%m-%d")))


def _fetch_chart(ticker: str, *, start_date: str, end_date: str, user_agent: str, timeout: float) -> dict[str, Any]:
    params = {
        "period1": _period(start_date),
        "period2": _period(end_date) + 86400,
        "interval": "1d",
        "events": "history",
        "includeAdjustedClose": "true",
    }
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker.upper()}?{urlencode(params)}"
    request = Request(url, headers={"User-Agent": user_agent, "Accept": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    error = payload.get("chart", {}).get("error")
    if error:
        raise RuntimeError(str(error))
    result = (payload.get("chart", {}).get("result") or [None])[0]
    if not result:
        raise RuntimeError(f"Yahoo chart returned no result for {ticker}")
    return result


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
        "created_or_updated_rows": 0,
        "failed": [],
        "min_date": "",
        "max_date": "",
    }
    with psycopg.connect(args.dsn) as connection:
        with connection.cursor() as cursor:
            _upsert(cursor, "sources", SOURCE_ID, source_payload)
            for ticker in args.tickers:
                ticker = ticker.strip().upper()
                if not ticker:
                    continue
                issuer_id = f"issuer_{ticker.lower()}"
                security_id = f"security_{ticker.lower()}_us"
                try:
                    chart = _fetch_chart(ticker, start_date=args.start_date, end_date=args.end_date, user_agent=args.user_agent, timeout=args.timeout)
                    rows = _rows_from_chart(ticker, chart)
                except Exception as exc:
                    summary["failed"].append({"ticker": ticker, "error": str(exc), "error_type": type(exc).__name__})
                    continue
                now = datetime.now(timezone.utc).isoformat()
                _upsert(
                    cursor,
                    "issuers",
                    issuer_id,
                    {
                        "issuer_id": issuer_id,
                        "legal_name": ticker,
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
                        "exchange": "US",
                        "currency": "USD",
                        "market": "U",
                        "status": "active",
                    },
                )
                for row in rows:
                    as_of_date = row["as_of_date"]
                    summary["min_date"] = as_of_date if not summary["min_date"] else min(summary["min_date"], as_of_date)
                    summary["max_date"] = as_of_date if not summary["max_date"] else max(summary["max_date"], as_of_date)
                    data_id = _market_data_id(security_id, as_of_date)
                    _upsert(
                        cursor,
                        "market_data",
                        data_id,
                        {
                            "data_id": data_id,
                            "security_id": security_id,
                            "source_id": SOURCE_ID,
                            "market": "U",
                            "as_of_date": as_of_date,
                            "data_type": "eod",
                            "currency": "USD",
                            "open": row["open"],
                            "high": row["high"],
                            "low": row["low"],
                            "close": row["close"],
                            "adjusted_close": row["adjusted_close"],
                            "volume": row["volume"],
                            "rights_tag": rights_tag,
                            "created_at": now,
                        },
                    )
                connection.commit()
                summary["tickers"].append({"ticker": ticker, "security_id": security_id, "row_count": len(rows)})
                summary["created_or_updated_rows"] += len(rows)
    summary["completed_at"] = datetime.now(timezone.utc).isoformat()
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Import US EOD prices from Yahoo chart endpoint for local research/simulated analysis.")
    parser.add_argument("--dsn", default="postgresql://ai_quant:ai_quant_dev_password@127.0.0.1:15432/ai_quant")
    parser.add_argument("--tickers", default="AAPL,MSFT,NVDA,TSLA,SPY")
    parser.add_argument("--start-date", default="2025-01-01")
    parser.add_argument("--end-date", default=date.today().isoformat())
    parser.add_argument("--user-agent", default="ai-native-quant-org/0.1 contact@example.com")
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


if __name__ == "__main__":
    main()
