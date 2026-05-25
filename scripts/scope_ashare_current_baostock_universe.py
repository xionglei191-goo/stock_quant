from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any


DEFAULT_DSN = "postgresql://ai_quant:ai_quant_dev_password@127.0.0.1:15432/ai_quant"


def _normalize_symbol(value: str) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())[-6:]


def _current_baostock_symbols(*, include_b_shares: bool = False) -> dict[str, dict[str, str]]:
    try:
        import baostock as bs  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:
        raise RuntimeError("baostock is required; run inside the app container") from exc

    login = bs.login()
    if login.error_code != "0":
        raise RuntimeError(f"baostock login failed: {login.error_code} {login.error_msg}")
    try:
        result = bs.query_stock_basic()
        if result.error_code != "0":
            raise RuntimeError(f"baostock query_stock_basic failed: {result.error_code} {result.error_msg}")
        fields = list(getattr(result, "fields", []) or ["code", "code_name", "ipoDate", "outDate", "type", "status"])
        active: dict[str, dict[str, str]] = {}
        while result.next():
            item = dict(zip(fields, result.get_row_data()))
            symbol = _normalize_symbol(str(item.get("code") or ""))
            name = str(item.get("code_name") or "").strip()
            stock_type = str(item.get("type") or "")
            status = str(item.get("status") or "")
            if len(symbol) != 6 or stock_type != "1" or status != "1":
                continue
            if not include_b_shares and symbol.startswith(("200", "900")):
                continue
            active[symbol] = {
                "symbol": symbol,
                "name": name or symbol,
                "baostock_code": str(item.get("code") or ""),
                "ipo_date": str(item.get("ipoDate") or ""),
                "out_date": str(item.get("outDate") or ""),
            }
        return active
    finally:
        bs.logout()


def _security_type(symbol: str) -> str:
    if symbol.startswith(("000", "001", "002", "003", "300", "301", "600", "601", "603", "605", "688", "689", "430", "830", "831", "832", "833", "834", "835", "836", "837", "838", "839", "870", "871", "872", "873", "920")):
        return "common_stock"
    if symbol.startswith(("200", "900")):
        return "b_share"
    if symbol.startswith(("15", "16", "50", "51", "52", "53", "56", "58")):
        return "fund_or_etf"
    if symbol.startswith(("11", "12")):
        return "convertible_bond"
    return "reference_security"


def run(args: argparse.Namespace) -> dict[str, Any]:
    try:
        import psycopg  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:
        raise RuntimeError("psycopg is required; run inside the app container") from exc

    started_at = datetime.now(timezone.utc).isoformat()
    active = _current_baostock_symbols(include_b_shares=args.include_b_shares)
    now = datetime.now(timezone.utc).isoformat()
    updated_in_scope = 0
    updated_out_of_scope = 0
    samples = {"in_scope": [], "out_of_scope": []}

    with psycopg.connect(args.dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT s.item_id, s.payload, i.item_id, i.payload
                FROM ai_quant.records AS s
                LEFT JOIN ai_quant.records AS i
                  ON i.collection = 'issuers'
                 AND i.item_id = s.payload->>'issuer_id'
                WHERE s.collection = 'securities'
                  AND s.payload->>'market' = 'A'
                ORDER BY s.payload->>'ticker'
                """
            )
            rows = cursor.fetchall()
            for security_item_id, security_payload, issuer_item_id, issuer_payload in rows:
                security = dict(security_payload)
                issuer = dict(issuer_payload or {})
                symbol = _normalize_symbol(str(security.get("ticker") or security_item_id))
                if not symbol:
                    continue
                sec_type = _security_type(symbol)
                active_item = active.get(symbol)
                if active_item and sec_type == "common_stock":
                    security.update(
                        {
                            "security_type": "common_stock",
                            "company_universe_scope": "in_scope",
                            "company_universe_reason": "current_baostock_active_common_stock",
                            "company_universe_classified_at": now,
                            "status": "active",
                        }
                    )
                    issuer.update(
                        {
                            "issuer_id": str(security.get("issuer_id") or issuer_item_id or f"issuer_{symbol}"),
                            "legal_name": active_item["name"],
                            "company_universe_scope": "in_scope",
                            "company_universe_reason": "current_baostock_active_common_stock",
                            "status": "active",
                            "updated_at": now,
                        }
                    )
                    updated_in_scope += 1
                    if len(samples["in_scope"]) < args.sample_limit:
                        samples["in_scope"].append({"symbol": symbol, "name": active_item["name"]})
                else:
                    reason = "not_in_current_baostock_active_common_stock"
                    if sec_type != "common_stock":
                        reason = f"non_common_stock_{sec_type}"
                    security.update(
                        {
                            "security_type": sec_type,
                            "company_universe_scope": "out_of_scope",
                            "company_universe_reason": reason,
                            "company_universe_classified_at": now,
                            "status": "reference_only",
                        }
                    )
                    issuer.update(
                        {
                            "issuer_id": str(security.get("issuer_id") or issuer_item_id or f"issuer_{symbol}"),
                            "company_universe_scope": "out_of_scope",
                            "company_universe_reason": reason,
                            "status": "reference_only",
                            "updated_at": now,
                        }
                    )
                    updated_out_of_scope += 1
                    if len(samples["out_of_scope"]) < args.sample_limit:
                        samples["out_of_scope"].append({"symbol": symbol, "security_type": sec_type, "reason": reason})

                if args.dry_run:
                    continue
                cursor.execute(
                    """
                    INSERT INTO ai_quant.records (collection, item_id, payload, position)
                    VALUES ('securities', %s, %s::jsonb, NULL)
                    ON CONFLICT (collection, item_id)
                    DO UPDATE SET payload = EXCLUDED.payload, updated_at = now()
                    """,
                    (security_item_id, json.dumps(security, ensure_ascii=False, sort_keys=True)),
                )
                if issuer_item_id:
                    cursor.execute(
                        """
                        INSERT INTO ai_quant.records (collection, item_id, payload, position)
                        VALUES ('issuers', %s, %s::jsonb, NULL)
                        ON CONFLICT (collection, item_id)
                        DO UPDATE SET payload = EXCLUDED.payload, updated_at = now()
                        """,
                        (issuer_item_id, json.dumps(issuer, ensure_ascii=False, sort_keys=True)),
                    )
            connection.commit()

    result = {
        "status": "passed",
        "dry_run": bool(args.dry_run),
        "started_at": started_at,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "baostock_active_common_stock_count": len(active),
        "updated_in_scope": updated_in_scope,
        "updated_out_of_scope": updated_out_of_scope,
        "samples": samples,
        "policy": "A-share active production universe is the current baostock active common-stock directory. Historical K-line rows are retained, but out-of-scope securities are marked reference_only and excluded from daily active refresh.",
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Mark the A-share active company universe from baostock current stock_basic.")
    parser.add_argument("--dsn", default=os.environ.get("AI_QUANT_POSTGRES_DSN") or DEFAULT_DSN)
    parser.add_argument("--include-b-shares", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--sample-limit", type=int, default=20)
    parser.add_argument("--output", default="artifacts/ashare-current-baostock-universe-scope.json")
    args = parser.parse_args()
    result = run(args)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
