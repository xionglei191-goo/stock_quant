from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from typing import Any


DEFAULT_DSN = "postgresql://ai_quant:ai_quant_dev_password@127.0.0.1:15432/ai_quant"


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            loaded = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(loaded) if isinstance(loaded, dict) else {}
    return {}


def _safe_identifier(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", value.strip()).strip("_").lower()


def _classify_security(ticker: str, legal_name: str, exchange: str) -> dict[str, str]:
    symbol = str(ticker or "").strip().upper()
    text = f"{symbol} {legal_name or ''} {exchange or ''}".lower()
    reference_terms = [
        ("preferred stock", "preferred_stock", "preferred_or_preference_security"),
        ("preferred shares", "preferred_stock", "preferred_or_preference_security"),
        ("preference shares", "preferred_stock", "preferred_or_preference_security"),
        ("warrant", "warrant", "warrant_security"),
        (" rights", "rights", "rights_security"),
        (" unit", "unit", "unit_security"),
        ("notes due", "note_or_bond", "note_or_bond_security"),
        ("senior notes", "note_or_bond", "note_or_bond_security"),
        (" bond", "note_or_bond", "note_or_bond_security"),
        (" etf", "fund_or_etf", "fund_or_etf_security"),
        (" etn", "fund_or_etf", "fund_or_etf_security"),
        (" fund", "fund_or_etf", "fund_or_etf_security"),
    ]
    for term, security_type, reason in reference_terms:
        if term in text:
            return {"scope": "out_of_scope", "security_type": security_type, "reason": reason}
    if "depositary shares" in text and any(term in text for term in ("preferred", "preference", "series ")):
        return {"scope": "out_of_scope", "security_type": "preferred_stock", "reason": "preferred_or_preference_security"}
    if "depositary shares" in text and "american depositary shares" not in text:
        return {"scope": "out_of_scope", "security_type": "preferred_stock", "reason": "preferred_depositary_security"}
    if "$" in symbol or symbol.endswith((".W", ".R", ".U")):
        return {"scope": "out_of_scope", "security_type": "reference_security", "reason": "special_ticker_not_common_equity"}
    return {"scope": "in_scope", "security_type": "common_stock", "reason": "current_us_yahoo_refresh_common_equity"}


def _preference_score(record: dict[str, Any]) -> int:
    ticker = str(record.get("ticker") or "").upper()
    safe = _safe_identifier(ticker.lower())
    security_id = str(record.get("security_id") or "")
    legal_name = str(record.get("legal_name") or "")
    classification = record.get("classification") if isinstance(record.get("classification"), dict) else {}
    score = 0
    if classification.get("scope") == "in_scope":
        score += 100
    if security_id == f"security_{safe}_us":
        score += 40
    if security_id == f"security_us_{safe}":
        score += 30
    if legal_name and legal_name != ticker:
        score += 5
    if "common stock" in legal_name.lower() or "ordinary shares" in legal_name.lower():
        score += 3
    if str(record.get("issuer_id") or ""):
        score += 2
    return score


def run(args: argparse.Namespace) -> dict[str, Any]:
    try:
        import psycopg  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:
        raise RuntimeError("psycopg is required; run inside the app container") from exc

    started_at = datetime.now(timezone.utc).isoformat()
    now = datetime.now(timezone.utc).isoformat()
    ticker_filter = {item.strip().upper() for item in str(args.ticker_filter or "").split(",") if item.strip()}
    rows: list[dict[str, Any]] = []
    with psycopg.connect(args.dsn) as connection:
        with connection.cursor() as cursor:
            clauses = [
                "s.collection = 'securities'",
                "s.payload->>'market' = 'U'",
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
                    i.item_id,
                    i.payload,
                    latest.max_date::text
                FROM ai_quant.records AS s
                LEFT JOIN ai_quant.records AS i
                  ON i.collection = 'issuers'
                 AND i.item_id = s.payload->>'issuer_id'
                LEFT JOIN (
                    SELECT security_id, MAX(as_of_date) AS max_date
                    FROM ai_quant.market_data_bars
                    WHERE market = 'U'
                      AND source_id = 'yahoo_chart_us_eod'
                      AND data_type = 'eod'
                    GROUP BY security_id
                ) AS latest
                  ON latest.security_id = s.payload->>'security_id'
                WHERE {' AND '.join(clauses)}
                ORDER BY upper(s.payload->>'ticker'), s.item_id
                """,
                tuple(params),
            )
            for security_item_id, security_payload, issuer_item_id, issuer_payload, latest_date in cursor.fetchall():
                security = _payload(security_payload)
                issuer = _payload(issuer_payload)
                ticker = str(security.get("ticker") or "").strip().upper()
                legal_name = str(issuer.get("legal_name") or security.get("name") or ticker)
                classification = _classify_security(ticker, legal_name, str(security.get("exchange") or issuer.get("exchange") or "US"))
                rows.append(
                    {
                        "security_item_id": security_item_id,
                        "security": security,
                        "issuer_item_id": issuer_item_id,
                        "issuer": issuer,
                        "ticker": ticker,
                        "security_id": str(security.get("security_id") or security_item_id),
                        "issuer_id": str(security.get("issuer_id") or issuer_item_id or ""),
                        "legal_name": legal_name,
                        "latest_date": str(latest_date or ""),
                        "classification": classification,
                    }
                )

            best_by_ticker: dict[str, str] = {}
            for row in rows:
                if row["classification"]["scope"] != "in_scope":
                    continue
                ticker = row["ticker"]
                current = best_by_ticker.get(ticker)
                if current is None:
                    best_by_ticker[ticker] = row["security_item_id"]
                    continue
                existing_row = next(item for item in rows if item["security_item_id"] == current)
                if _preference_score(row) > _preference_score(existing_row):
                    best_by_ticker[ticker] = row["security_item_id"]

            updated_in_scope = 0
            updated_out_of_scope = 0
            stale_out_of_scope = 0
            samples = {"in_scope": [], "out_of_scope": []}
            for row in rows:
                security = row["security"]
                issuer = row["issuer"]
                classification = dict(row["classification"])
                if classification["scope"] == "in_scope" and best_by_ticker.get(row["ticker"]) != row["security_item_id"]:
                    classification = {"scope": "out_of_scope", "security_type": "duplicate_ticker", "reason": "duplicate_ticker_refresh_record"}
                if (
                    classification["scope"] == "in_scope"
                    and not args.clear_stale
                    and security.get("market_data_refresh_scope") == "out_of_scope"
                    and security.get("market_data_refresh_reason") == "yahoo_latest_bar_before_target_date"
                ):
                    classification = {"scope": "out_of_scope", "security_type": "stale_yahoo_bar", "reason": "yahoo_latest_bar_before_target_date"}
                if (
                    classification["scope"] == "in_scope"
                    and args.mark_stale_out_of_scope
                    and args.target_date
                    and (not row["latest_date"] or row["latest_date"] < args.target_date)
                ):
                    classification = {"scope": "out_of_scope", "security_type": "stale_yahoo_bar", "reason": "yahoo_latest_bar_before_target_date"}
                    stale_out_of_scope += 1

                security.update(
                    {
                        "security_id": row["security_id"],
                        "market_data_refresh_scope": classification["scope"],
                        "market_data_refresh_reason": classification["reason"],
                        "market_data_refresh_classified_at": now,
                        "market_data_latest_yahoo_date": row["latest_date"],
                    }
                )
                if not security.get("security_type"):
                    security["security_type"] = classification["security_type"]
                issuer.update(
                    {
                        "issuer_id": row["issuer_id"] or str(issuer.get("issuer_id") or ""),
                        "market_data_refresh_scope": classification["scope"],
                        "market_data_refresh_reason": classification["reason"],
                        "market_data_refresh_classified_at": now,
                        "updated_at": now,
                    }
                )
                if classification["scope"] == "in_scope":
                    updated_in_scope += 1
                    if len(samples["in_scope"]) < args.sample_limit:
                        samples["in_scope"].append({"ticker": row["ticker"], "security_id": row["security_id"], "latest_date": row["latest_date"]})
                else:
                    updated_out_of_scope += 1
                    if len(samples["out_of_scope"]) < args.sample_limit:
                        samples["out_of_scope"].append(
                            {
                                "ticker": row["ticker"],
                                "security_id": row["security_id"],
                                "latest_date": row["latest_date"],
                                "security_type": classification["security_type"],
                                "reason": classification["reason"],
                            }
                        )

                if args.dry_run:
                    continue
                cursor.execute(
                    """
                    INSERT INTO ai_quant.records (collection, item_id, payload, position)
                    VALUES ('securities', %s, %s::jsonb, NULL)
                    ON CONFLICT (collection, item_id)
                    DO UPDATE SET payload = EXCLUDED.payload, updated_at = now()
                    """,
                    (row["security_item_id"], json.dumps(security, ensure_ascii=False, sort_keys=True)),
                )
                if row["issuer_item_id"]:
                    cursor.execute(
                        """
                        INSERT INTO ai_quant.records (collection, item_id, payload, position)
                        VALUES ('issuers', %s, %s::jsonb, NULL)
                        ON CONFLICT (collection, item_id)
                        DO UPDATE SET payload = EXCLUDED.payload, updated_at = now()
                        """,
                        (row["issuer_item_id"], json.dumps(issuer, ensure_ascii=False, sort_keys=True)),
                    )
            connection.commit()

    return {
        "status": "passed",
        "dry_run": bool(args.dry_run),
        "started_at": started_at,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "ticker_filter": sorted(ticker_filter),
        "target_date": args.target_date,
        "mark_stale_out_of_scope": bool(args.mark_stale_out_of_scope),
        "updated_in_scope": updated_in_scope,
        "updated_out_of_scope": updated_out_of_scope,
        "stale_out_of_scope": stale_out_of_scope,
        "samples": samples,
        "policy": "US Yahoo daily refresh universe uses one in-scope common-equity security per ticker. Duplicate/manual/reference securities and optional stale-attempted tickers keep historical bars but leave the active refresh universe.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Mark US securities that should participate in daily Yahoo EOD refresh.")
    parser.add_argument("--dsn", default=os.environ.get("AI_QUANT_POSTGRES_DSN") or DEFAULT_DSN)
    parser.add_argument("--ticker-filter", default="")
    parser.add_argument("--target-date", default="")
    parser.add_argument("--mark-stale-out-of-scope", action="store_true")
    parser.add_argument("--clear-stale", action="store_true", help="Allow previously stale Yahoo tickers to re-enter the active refresh universe.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--sample-limit", type=int, default=20)
    parser.add_argument("--output", default="artifacts/us-current-yahoo-universe-scope.json")
    args = parser.parse_args()
    result = run(args)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
