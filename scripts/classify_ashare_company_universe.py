from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from typing import Any


DEFAULT_DSN = "postgresql://ai_quant:ai_quant_dev_password@127.0.0.1:15432/ai_quant"


def _security_type(symbol: str, name: str) -> str:
    if symbol.startswith(("11", "12")):
        return "convertible_bond"
    if symbol.startswith(("15", "16", "50", "51", "52", "53", "56", "58")):
        return "fund_or_etf"
    if symbol.startswith(("13", "18", "39", "88", "89", "99")):
        return "index_or_board_series"
    if symbol.startswith(("20", "90")):
        return "b_share"
    lower_name = name.lower()
    if any(term in lower_name for term in ["etf", "lof", "reits", "基金", "指数", "转债", "定转", "债"]):
        return "fund_or_bond_like"
    return "common_stock"


def _is_pending_name(name: str) -> bool:
    return bool(re.fullmatch(r"\d{6}", name or "") or "待补名称" in (name or ""))


def _company_scope(symbol: str, name: str, security_type: str) -> tuple[str, str]:
    pending = _is_pending_name(name)
    if security_type != "common_stock":
        return "out_of_scope", "non_company_security"
    if pending:
        return "out_of_scope", "unresolved_or_stale_tdx_symbol"
    return "in_scope", "listed_company"


def run(args: argparse.Namespace) -> dict[str, Any]:
    try:
        import psycopg  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:
        raise RuntimeError("psycopg is required; run inside the app container or install psycopg[binary]") from exc

    started_at = datetime.now(timezone.utc).isoformat()
    samples: dict[str, list[dict[str, str]]] = {"out_of_scope": [], "unresolved": [], "in_scope": []}
    type_counts: Counter[str] = Counter()
    scope_counts: Counter[str] = Counter()
    deleted_positions = 0
    updated_securities = 0
    updated_issuers = 0

    with psycopg.connect(args.dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                select s.item_id, s.payload, i.item_id, i.payload
                from ai_quant.records s
                join ai_quant.records i on i.collection='issuers' and i.item_id=s.payload->>'issuer_id'
                where s.collection='securities'
                  and s.payload->>'market'='A'
                  and s.payload->>'ticker' ~ '^[0-9]{6}$'
                order by s.payload->>'ticker'
                """
            )
            rows = cursor.fetchall()
            for security_item_id, security_payload, issuer_item_id, issuer_payload in rows:
                security = dict(security_payload)
                issuer = dict(issuer_payload)
                symbol = str(security.get("ticker") or "")
                name = str(issuer.get("legal_name") or "")
                sec_type = _security_type(symbol, name)
                scope, reason = _company_scope(symbol, name, sec_type)

                type_counts[sec_type] += 1
                scope_counts[scope] += 1

                security["security_type"] = sec_type
                security["company_universe_scope"] = scope
                security["company_universe_reason"] = reason
                security["company_universe_classified_at"] = datetime.now(timezone.utc).isoformat()
                issuer["company_universe_scope"] = scope
                issuer["company_universe_reason"] = reason
                issuer["updated_at"] = datetime.now(timezone.utc).isoformat()
                if scope == "out_of_scope":
                    issuer["status"] = "reference_only"
                elif issuer.get("status") == "reference_only":
                    issuer["status"] = "active"

                cursor.execute(
                    """
                    insert into ai_quant.records (collection, item_id, payload, position)
                    values ('securities', %s, %s::jsonb, null)
                    on conflict (collection, item_id) do update set payload=excluded.payload, updated_at=now()
                    """,
                    (security_item_id, json.dumps(security, ensure_ascii=False, sort_keys=True)),
                )
                cursor.execute(
                    """
                    insert into ai_quant.records (collection, item_id, payload, position)
                    values ('issuers', %s, %s::jsonb, null)
                    on conflict (collection, item_id) do update set payload=excluded.payload, updated_at=now()
                    """,
                    (issuer_item_id, json.dumps(issuer, ensure_ascii=False, sort_keys=True)),
                )
                updated_securities += 1
                updated_issuers += 1

                sample_key = "in_scope" if scope == "in_scope" else "unresolved" if reason == "unresolved_or_stale_tdx_symbol" else "out_of_scope"
                if len(samples[sample_key]) < 30:
                    samples[sample_key].append({"symbol": symbol, "name": name, "security_type": sec_type, "reason": reason})

                if scope == "out_of_scope" and not args.keep_positions:
                    cursor.execute(
                        """
                        delete from ai_quant.records
                        where collection='company_positions'
                          and payload->>'security_id'=%s
                          and item_id like 'pos_a_%%_industry'
                        """,
                        (security_item_id,),
                    )
                    deleted_positions += cursor.rowcount
            connection.commit()

    return {
        "started_at": started_at,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "updated_securities": updated_securities,
        "updated_issuers": updated_issuers,
        "deleted_out_of_scope_company_positions": deleted_positions,
        "company_scope_counts": dict(scope_counts),
        "security_type_counts": dict(type_counts),
        "samples": samples,
        "policy": {
            "in_scope": "named common stock only",
            "out_of_scope": "funds, bonds, indexes, B shares, board series, and unresolved stale TDX symbols remain in the securities directory but are excluded from company industry-chain positions",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify local TDX A-share securities into company universe scope.")
    parser.add_argument("--dsn", default=os.environ.get("AI_QUANT_POSTGRES_DSN") or os.environ.get("AI_QUANT_DATABASE_URL") or DEFAULT_DSN)
    parser.add_argument("--artifact", default="artifacts/ashare-company-universe-classification.json")
    parser.add_argument("--keep-positions", action="store_true")
    args = parser.parse_args()
    result = run(args)
    artifact = Path(args.artifact)
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"artifact": str(artifact), **result}, ensure_ascii=False))


if __name__ == "__main__":
    main()
