from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Any
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


DEFAULT_DSN = "postgresql://ai_quant:ai_quant_dev_password@127.0.0.1:15432/ai_quant"
SOURCE_ID = "tencent_valuation_snapshot"


def infer_exchange(symbol: str) -> str:
    if symbol.startswith(("60", "68", "90", "50", "51", "56", "58", "11")):
        return "SSE"
    if symbol.startswith(("00", "20", "30", "12", "15", "16")):
        return "SZSE"
    if symbol.startswith(("43", "81", "82", "83", "87", "88", "89", "92")):
        return "BSE"
    return "A"


def tencent_symbol(symbol: str) -> str:
    exchange = infer_exchange(symbol)
    prefix = "sh" if exchange == "SSE" else "bj" if exchange == "BSE" else "sz"
    return f"{prefix}{symbol}"


def fetch_names(symbols: list[str], *, batch_size: int = 80, sleep_seconds: float = 0.2) -> dict[str, str]:
    names: dict[str, str] = {}
    for offset in range(0, len(symbols), batch_size):
        batch = symbols[offset : offset + batch_size]
        query = ",".join(tencent_symbol(symbol) for symbol in batch)
        url = f"https://qt.gtimg.cn/q={query}"
        text = ""
        last_error = ""
        for attempt in range(1, 4):
            try:
                request = Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://gu.qq.com/"})
                with urlopen(request, timeout=20) as response:
                    text = response.read().decode("gbk", errors="replace")
                break
            except Exception as exc:
                last_error = str(exc)
                time.sleep(attempt)
        if not text:
            print(json.dumps({"offset": offset, "error": last_error}, ensure_ascii=False), flush=True)
            continue
        for line in text.splitlines():
            if "=" not in line:
                continue
            key, _, raw = line.partition("=")
            value = raw.strip().strip('"').rstrip(";")
            fields = value.split("~")
            if len(fields) < 3:
                continue
            name = fields[1].strip()
            code = fields[2].strip()
            if re.fullmatch(r"\d{6}", code) and name and name != code:
                names[code] = name
        print(json.dumps({"progress": min(offset + len(batch), len(symbols)), "total": len(symbols), "names": len(names)}, ensure_ascii=False), flush=True)
        time.sleep(sleep_seconds)
    return names


def load_ashare_symbols(cursor: Any, *, only_pending: bool) -> list[str]:
    condition = "and (i.payload->>'legal_name' ~ '^[0-9]{6}$' or i.payload->>'legal_name' like '%待补名称%')" if only_pending else ""
    cursor.execute(
        f"""
        select s.payload->>'ticker'
        from ai_quant.records s
        join ai_quant.records i on i.collection='issuers' and i.item_id = s.payload->>'issuer_id'
        where s.collection='securities'
          and s.payload->>'market'='A'
          and s.payload->>'ticker' ~ '^[0-9]{{6}}$'
          {condition}
        order by s.payload->>'ticker'
        """
    )
    return [row[0] for row in cursor.fetchall()]


def run(args: argparse.Namespace) -> dict[str, Any]:
    try:
        import psycopg  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:
        raise RuntimeError("psycopg is required; run inside the app container or install psycopg[binary]") from exc

    started_at = datetime.now(timezone.utc).isoformat()
    with psycopg.connect(args.dsn) as connection:
        with connection.cursor() as cursor:
            symbols = load_ashare_symbols(cursor, only_pending=not args.all)
            if args.limit:
                symbols = symbols[: args.limit]
            names = fetch_names(symbols, batch_size=args.batch_size, sleep_seconds=args.sleep)
            updated = 0
            exchange_fixed = 0
            missing = []
            for symbol in symbols:
                security_id = f"sec_{symbol}"
                issuer_id = f"issuer_{symbol}"
                exchange = infer_exchange(symbol)
                cursor.execute("select payload from ai_quant.records where collection='issuers' and item_id=%s", (issuer_id,))
                issuer_row = cursor.fetchone()
                cursor.execute("select payload from ai_quant.records where collection='securities' and item_id=%s", (security_id,))
                security_row = cursor.fetchone()
                if not issuer_row or not security_row:
                    continue
                issuer = dict(issuer_row[0])
                security = dict(security_row[0])
                if security.get("exchange") != exchange:
                    security["exchange"] = exchange
                    exchange_fixed += 1
                name = names.get(symbol, "")
                if name:
                    issuer["legal_name"] = name
                    aliases = list(issuer.get("aliases") or [])
                    for alias in [symbol, name]:
                        if alias not in aliases:
                            aliases.append(alias)
                    issuer["aliases"] = aliases
                    issuer["updated_at"] = datetime.now(timezone.utc).isoformat()
                    updated += 1
                else:
                    missing.append(symbol)
                cursor.execute(
                    """
                    insert into ai_quant.records (collection, item_id, payload, position)
                    values ('issuers', %s, %s::jsonb, null)
                    on conflict (collection, item_id) do update set payload=excluded.payload, updated_at=now()
                    """,
                    (issuer_id, json.dumps(issuer, ensure_ascii=False, sort_keys=True)),
                )
                cursor.execute(
                    """
                    insert into ai_quant.records (collection, item_id, payload, position)
                    values ('securities', %s, %s::jsonb, null)
                    on conflict (collection, item_id) do update set payload=excluded.payload, updated_at=now()
                    """,
                    (security_id, json.dumps(security, ensure_ascii=False, sort_keys=True)),
                )
            connection.commit()
    result = {
        "started_at": started_at,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "source_id": SOURCE_ID,
        "symbol_count": len(symbols),
        "name_count": len(names),
        "updated_issuers": updated,
        "exchange_fixed": exchange_fixed,
        "missing_count": len(missing),
        "missing_sample": missing[:50],
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill A-share issuer names from Tencent public quote endpoint.")
    parser.add_argument("--dsn", default=os.environ.get("AI_QUANT_POSTGRES_DSN") or os.environ.get("AI_QUANT_DATABASE_URL") or DEFAULT_DSN)
    parser.add_argument("--artifact", default="artifacts/ashare-name-backfill-tencent.json")
    parser.add_argument("--batch-size", type=int, default=80)
    parser.add_argument("--sleep", type=float, default=0.2)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    result = run(args)
    artifact = Path(args.artifact)
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"artifact": str(artifact), **result}, ensure_ascii=False))


if __name__ == "__main__":
    main()
