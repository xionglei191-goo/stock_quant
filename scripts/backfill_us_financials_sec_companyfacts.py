from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from http.client import IncompleteRead
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_DSN = os.getenv("AI_QUANT_POSTGRES_DSN", "postgresql://ai_quant:ai_quant_dev_password@127.0.0.1:15432/ai_quant")
DEFAULT_ARTIFACT = Path("artifacts/us-financials-sec-companyfacts.json")


US_GAAP_CONCEPTS = {
    "Revenues": "total_revenue",
    "SalesRevenueNet": "total_revenue",
    "NetIncomeLoss": "net_income",
    "OperatingIncomeLoss": "operating_income",
    "Assets": "total_assets",
    "Liabilities": "total_liabilities",
    "StockholdersEquity": "total_equity",
    "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest": "total_equity",
    "NetCashProvidedByUsedInOperatingActivities": "operating_cash_flow",
    "EarningsPerShareBasic": "basic_eps",
    "EarningsPerShareDiluted": "diluted_eps",
}

IFRS_CONCEPTS = {
    "Revenue": "total_revenue",
    "ProfitLoss": "net_income",
    "ProfitLossAttributableToOwnersOfParent": "net_income",
    "OperatingProfitLoss": "operating_income",
    "Assets": "total_assets",
    "Liabilities": "total_liabilities",
    "Equity": "total_equity",
    "EquityAttributableToOwnersOfParent": "total_equity",
    "CashFlowsFromUsedInOperatingActivities": "operating_cash_flow",
    "BasicEarningsLossPerShare": "basic_eps",
    "DilutedEarningsLossPerShare": "diluted_eps",
}


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def known_us_ciks(dsn: str, *, limit: int = 0, offset: int = 0, missing_only: bool = False, min_market_cap: float = 0.0) -> list[dict[str, str]]:
    where_missing = (
        "AND NOT (coalesce(i.payload->'fundamentals', '{}'::jsonb) ? 'financial_summary') "
        "AND NOT (coalesce(i.payload->'fundamentals', '{}'::jsonb) ? 'financial_unavailable')"
        if missing_only
        else ""
    )
    where_market_cap = f"AND coalesce((i.payload #>> '{{valuation_metrics,market_cap}}')::numeric, 0) >= {float(min_market_cap)}" if min_market_cap else ""
    limit_sql = f"LIMIT {int(limit)}" if limit else ""
    offset_sql = f"OFFSET {int(offset)}" if offset else ""
    query = f"""
SELECT upper(s.payload->>'ticker') AS ticker, i.payload->>'cik' AS cik
FROM ai_quant.records s
JOIN ai_quant.records i ON i.collection='issuers' AND i.item_id=s.payload->>'issuer_id'
WHERE s.collection='securities'
  AND s.payload->>'market'='U'
  AND coalesce(s.payload->>'ticker','') <> ''
  AND coalesce(i.payload->>'cik','') <> ''
  {where_missing}
  {where_market_cap}
GROUP BY 1,2
ORDER BY max(coalesce((i.payload #>> '{{valuation_metrics,market_cap}}')::numeric, 0)) DESC, 1
{limit_sql}
{offset_sql}
"""
    result = subprocess.run(["psql", dsn, "-X", "-q", "-t", "-A", "-F", ",", "-c", query], check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    rows: list[dict[str, str]] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        ticker, cik = line.split(",", 1)
        rows.append({"ticker": ticker.strip(), "cik": cik.strip().zfill(10)})
    return rows


def fetch_companyfacts(cik: str, *, retries: int = 3) -> dict[str, Any]:
    headers = {"User-Agent": os.getenv("AI_QUANT_SEC_USER_AGENT", "ai-native-quant-org/0.1 contact@example.com"), "Accept": "application/json"}
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            with urlopen(Request(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json", headers=headers), timeout=30) as response:
                return json.loads(response.read().decode("utf-8", errors="replace"))
        except (HTTPError, URLError, TimeoutError, OSError, IncompleteRead, json.JSONDecodeError) as exc:
            last_error = exc
            time.sleep(min(6, attempt * 1.5))
    raise RuntimeError(f"companyfacts fetch failed after retries for CIK{cik}: {last_error}") from last_error


def latest_fact(units: dict[str, Any], *, preferred_units: tuple[str, ...]) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    for unit in preferred_units:
        for row in units.get(unit) or []:
            if row.get("form") not in {"10-K", "10-Q", "20-F", "40-F"}:
                continue
            if row.get("val") is None:
                continue
            candidates.append(row)
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: (str(item.get("end", "")), str(item.get("filed", ""))), reverse=True)[0]


def summarize_companyfacts(ticker: str, cik: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    facts = payload.get("facts") or {}
    namespaces = [
        ("us-gaap", facts.get("us-gaap") or {}, US_GAAP_CONCEPTS),
        ("ifrs-full", facts.get("ifrs-full") or {}, IFRS_CONCEPTS),
    ]
    summary: dict[str, Any] = {"cik": cik, "entity_name": payload.get("entityName", ""), "currency": "USD"}
    source_refs: dict[str, Any] = {}
    for namespace, namespace_facts, concept_map in namespaces:
        for concept, target in concept_map.items():
            if target in summary:
                continue
            concept_payload = namespace_facts.get(concept) or {}
            units = concept_payload.get("units") or {}
            preferred = ("USD", "USD/shares", "shares")
            fact = latest_fact(units, preferred_units=preferred)
            if fact is None:
                continue
            summary[target] = fact.get("val")
            source_refs[target] = {
                "namespace": namespace,
                "concept": concept,
                "end": fact.get("end"),
                "filed": fact.get("filed"),
                "form": fact.get("form"),
                "accn": fact.get("accn"),
                "fy": fact.get("fy"),
                "fp": fact.get("fp"),
            }
    if len(summary) <= 3:
        return None
    summary["source_refs"] = source_refs
    return {
        "ticker": ticker,
        "cik": cik,
        "fundamentals": summary,
        "source_id": "sec_companyfacts",
        "source_uri": f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json",
    }


def fetch_one(item: dict[str, str]) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
    try:
        payload = fetch_companyfacts(item["cik"])
        row = summarize_companyfacts(item["ticker"], item["cik"], payload)
        if row:
            return row, None
        return None, {"ticker": item["ticker"], "cik": item["cik"], "error": "no_supported_companyfacts"}
    except (HTTPError, URLError, TimeoutError, OSError, IncompleteRead, json.JSONDecodeError, RuntimeError) as exc:
        return None, {"ticker": item["ticker"], "cik": item["cik"], "error": f"{type(exc).__name__}: {exc}"[:500]}


def fetch_rows(items: list[dict[str, str]], *, sleep_seconds: float, workers: int) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    workers = max(1, min(workers, 8))
    if workers == 1:
        for item in items:
            row, error = fetch_one(item)
            if row:
                rows.append(row)
            if error:
                errors.append(error)
            if sleep_seconds:
                time.sleep(sleep_seconds)
        return rows, errors
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = []
        for item in items:
            futures.append(executor.submit(fetch_one, item))
            if sleep_seconds:
                time.sleep(sleep_seconds)
        for future in as_completed(futures):
            row, error = future.result()
            if row:
                rows.append(row)
            if error:
                errors.append(error)
    return rows, errors


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        for row in rows:
            writer.writerow([json.dumps(row, ensure_ascii=False, sort_keys=True)])


def apply_rows(rows: list[dict[str, Any]], *, dsn: str) -> None:
    now = utc_iso()
    for row in rows:
        row["market"] = "U"
        row["backfilled_at"] = now
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        csv_path = tmp / "sec_companyfacts.csv"
        sql_path = tmp / "apply.sql"
        write_csv(csv_path, rows)
        sql_path.write_text(
            f"""
CREATE TEMP TABLE sec_companyfacts_backfill (payload jsonb);
\\copy sec_companyfacts_backfill(payload) FROM '{csv_path}' WITH (FORMAT csv)

WITH src AS (
  SELECT payload FROM sec_companyfacts_backfill
),
matched AS (
  SELECT s.item_id AS security_item_id, s.payload->>'issuer_id' AS issuer_id, src.payload AS src_payload
  FROM ai_quant.records s
  JOIN src ON s.collection='securities'
    AND s.payload->>'market'='U'
    AND upper(s.payload->>'ticker')=src.payload->>'ticker'
),
updated_issuers AS (
  UPDATE ai_quant.records i
  SET payload = i.payload
    || jsonb_build_object(
      'fundamentals',
      coalesce(i.payload->'fundamentals', '{{}}'::jsonb)
      || jsonb_build_object(
        'financial_summary', m.src_payload->'fundamentals',
        'financial_source_id', m.src_payload->>'source_id',
        'financial_source_uri', m.src_payload->>'source_uri',
        'financial_backfilled_at', m.src_payload->>'backfilled_at'
      ),
      'data_sources', (
        SELECT jsonb_agg(DISTINCT value)
        FROM jsonb_array_elements_text(coalesce(i.payload->'data_sources', '[]'::jsonb) || jsonb_build_array('sec_companyfacts')) AS value
      ),
      'updated_at', '{now}'
    )
  FROM matched m
  WHERE i.collection='issuers' AND i.item_id=m.issuer_id
  RETURNING i.item_id
),
updated_positions AS (
  UPDATE ai_quant.records p
  SET payload = p.payload
    || jsonb_build_object(
      'profit_exposure',
      coalesce(p.payload->'profit_exposure', '{{}}'::jsonb)
      || jsonb_build_object(
        'financial_summary', m.src_payload->'fundamentals',
        'source_id', 'sec_companyfacts',
        'source_uri', m.src_payload->>'source_uri',
        'backfilled_at', m.src_payload->>'backfilled_at'
      ),
      'data_quality', CASE
        WHEN coalesce(p.payload->>'data_quality','') IN ('public_basic_info_backfilled','public_basic_and_financials_backfilled') THEN 'public_basic_and_financials_backfilled'
        ELSE coalesce(nullif(p.payload->>'data_quality',''), 'public_financials_backfilled')
      END
    )
  FROM matched m
  WHERE p.collection='company_positions' AND p.payload->>'issuer_id'=m.issuer_id
  RETURNING p.item_id
)
SELECT (SELECT count(*) FROM matched) AS matched_securities, (SELECT count(*) FROM updated_issuers) AS updated_issuers, (SELECT count(*) FROM updated_positions) AS updated_positions;
""",
            encoding="utf-8",
        )
        subprocess.run(["psql", dsn, "-X", "-v", "ON_ERROR_STOP=1", "-f", str(sql_path)], check=True)


def apply_unavailable(errors: list[dict[str, str]], *, dsn: str) -> int:
    permanent = [
        {
            "ticker": item["ticker"],
            "cik": item["cik"],
            "error": item["error"],
            "source_id": "sec_companyfacts",
        }
        for item in errors
        if item.get("error") == "no_supported_companyfacts" or "HTTP Error 404" in item.get("error", "")
    ]
    if not permanent:
        return 0
    now = utc_iso()
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        csv_path = tmp / "sec_companyfacts_unavailable.csv"
        sql_path = tmp / "mark_unavailable.sql"
        write_csv(csv_path, permanent)
        sql_path.write_text(
            f"""
CREATE TEMP TABLE sec_companyfacts_unavailable (payload jsonb);
\\copy sec_companyfacts_unavailable(payload) FROM '{csv_path}' WITH (FORMAT csv)

WITH src AS (
  SELECT payload FROM sec_companyfacts_unavailable
),
matched AS (
  SELECT s.payload->>'issuer_id' AS issuer_id, src.payload AS src_payload
  FROM ai_quant.records s
  JOIN src ON s.collection='securities'
    AND s.payload->>'market'='U'
    AND upper(s.payload->>'ticker')=src.payload->>'ticker'
),
updated_issuers AS (
  UPDATE ai_quant.records i
  SET payload = i.payload
    || jsonb_build_object(
      'fundamentals',
      coalesce(i.payload->'fundamentals', '{{}}'::jsonb)
      || jsonb_build_object(
        'financial_unavailable', true,
        'financial_unavailable_reason', m.src_payload->>'error',
        'financial_source_id', 'sec_companyfacts',
        'financial_checked_at', '{now}'
      ),
      'updated_at', '{now}'
    )
  FROM matched m
  WHERE i.collection='issuers' AND i.item_id=m.issuer_id
  RETURNING i.item_id
)
SELECT count(*) FROM updated_issuers;
""",
            encoding="utf-8",
        )
        subprocess.run(["psql", dsn, "-X", "-v", "ON_ERROR_STOP=1", "-f", str(sql_path)], check=True)
    return len(permanent)


def coverage(dsn: str) -> dict[str, Any]:
    query = """
SELECT jsonb_build_object(
  'us_issuers_with_cik', (SELECT count(*) FROM ai_quant.records WHERE collection='issuers' AND payload->>'country'='US' AND coalesce(payload->>'cik','') <> ''),
  'us_issuers_with_financial_summary', (SELECT count(*) FROM ai_quant.records WHERE collection='issuers' AND payload->>'country'='US' AND payload->'fundamentals' ? 'financial_summary'),
  'us_issuers_total', (SELECT count(*) FROM ai_quant.records WHERE collection='issuers' AND payload->>'country'='US'),
  'us_positions_with_financial_summary', (SELECT count(*) FROM ai_quant.records p JOIN ai_quant.records s ON s.collection='securities' AND s.item_id=p.payload->>'security_id' WHERE p.collection='company_positions' AND s.payload->>'market'='U' AND p.payload->'profit_exposure' ? 'financial_summary'),
  'us_positions_total', (SELECT count(*) FROM ai_quant.records p JOIN ai_quant.records s ON s.collection='securities' AND s.item_id=p.payload->>'security_id' WHERE p.collection='company_positions' AND s.payload->>'market'='U')
)
"""
    result = subprocess.run(["psql", dsn, "-X", "-q", "-t", "-A", "-c", query], check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return json.loads(result.stdout.strip())


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill US financial summaries from SEC companyfacts.")
    parser.add_argument("--dsn", default=DEFAULT_DSN)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--missing-only", action="store_true")
    parser.add_argument("--min-market-cap", type=float, default=0.0)
    parser.add_argument("--sleep-seconds", type=float, default=0.12)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--artifact", type=Path, default=DEFAULT_ARTIFACT)
    args = parser.parse_args()

    started_at = utc_iso()
    items = known_us_ciks(args.dsn, limit=args.limit, offset=args.offset, missing_only=args.missing_only, min_market_cap=args.min_market_cap)
    rows, errors = fetch_rows(items, sleep_seconds=args.sleep_seconds, workers=args.workers)
    apply_rows(rows, dsn=args.dsn)
    unavailable_marked = apply_unavailable(errors, dsn=args.dsn)
    summary = {
        "started_at": started_at,
        "completed_at": utc_iso(),
        "requested": len(items),
        "updated_rows": len(rows),
        "unavailable_marked": unavailable_marked,
        "workers": max(1, min(args.workers, 8)),
        "error_count": len(errors),
        "errors": errors[:200],
        "coverage": coverage(args.dsn),
        "source": "sec_companyfacts",
        "usage_boundary": "public_sec_xbrl_companyfacts_research_only_no_real_trading",
    }
    args.artifact.parent.mkdir(parents=True, exist_ok=True)
    args.artifact.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
