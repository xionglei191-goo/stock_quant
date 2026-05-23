from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DEFAULT_DSN = os.getenv("AI_QUANT_POSTGRES_DSN", "postgresql://ai_quant:ai_quant_dev_password@127.0.0.1:15432/ai_quant")
DEFAULT_ARTIFACT = Path("artifacts/company-financials-public-backfill.json")
USER_AGENT = "ai-native-quant-org/0.1 local-research"


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch_json(url: str, *, headers: dict[str, str] | None = None, retries: int = 4, timeout: int = 15) -> dict[str, Any]:
    request_headers = {"User-Agent": USER_AGENT, "Accept": "application/json,text/plain,*/*"}
    if headers:
        request_headers.update(headers)
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            with urlopen(Request(url, headers=request_headers), timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8", errors="replace"))
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            last_error = exc
            time.sleep(min(8, attempt * 1.5))
    raise RuntimeError(f"fetch_json failed: {url}: {last_error}") from last_error


def clean_text(value: Any) -> str:
    text = str(value if value is not None else "").strip()
    return "" if text in {"", "-", "--", "None", "null"} else text


def clean_number(value: Any) -> float | None:
    text = clean_text(value).replace(",", "").replace("$", "").replace("%", "")
    if not text:
        return None
    multiplier = 1.0
    if text.startswith("(") and text.endswith(")"):
        multiplier = -1.0
        text = text[1:-1]
    try:
        return float(text) * multiplier
    except ValueError:
        return None


def compact_date(value: Any) -> str:
    text = clean_text(value)
    return text[:10] if len(text) >= 10 else text


def fetch_eastmoney_financial_rows(limit: int = 0, *, latest_only: bool = True, max_pages: int = 40) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen_tickers: set[str] = set()
    page = 1
    page_size = 500
    while True:
        params = {
            "sortColumns": "UPDATE_DATE,SECURITY_CODE",
            "sortTypes": "-1,-1",
            "pageSize": page_size,
            "pageNumber": page,
            "reportName": "RPT_LICO_FN_CPD",
            "columns": "ALL",
            "source": "WEB",
            "client": "WEB",
        }
        payload = fetch_json(
            f"https://datacenter-web.eastmoney.com/api/data/v1/get?{urlencode(params)}",
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com/"},
            retries=3,
        )
        result = payload.get("result") or {}
        data = result.get("data") or []
        if not data:
            break
        for item in data:
            ticker = clean_text(item.get("SECURITY_CODE"))
            if not ticker:
                continue
            if latest_only and ticker in seen_tickers:
                continue
            seen_tickers.add(ticker)
            rows.append(
                {
                    "ticker": ticker,
                    "name": clean_text(item.get("SECURITY_NAME_ABBR")),
                    "report_date": compact_date(item.get("REPORTDATE")),
                    "qdate": clean_text(item.get("QDATE")),
                    "report_type": clean_text(item.get("DATATYPE")),
                    "notice_date": compact_date(item.get("NOTICE_DATE")),
                    "fundamentals": {
                        "basic_eps": clean_number(item.get("BASIC_EPS")),
                        "deducted_basic_eps": clean_number(item.get("DEDUCT_BASIC_EPS")),
                        "total_operating_income": clean_number(item.get("TOTAL_OPERATE_INCOME")),
                        "parent_net_profit": clean_number(item.get("PARENT_NETPROFIT")),
                        "weighted_avg_roe": clean_number(item.get("WEIGHTAVG_ROE")),
                        "book_value_per_share": clean_number(item.get("BPS")),
                        "operating_cash_flow_per_share": clean_number(item.get("MGJYXJJE")),
                        "gross_margin": clean_number(item.get("XSMLL")),
                        "revenue_yoy": clean_number(item.get("YSTZ")),
                        "net_profit_yoy": clean_number(item.get("SJLTZ")),
                        "revenue_qoq": clean_number(item.get("YSHZ")),
                        "net_profit_qoq": clean_number(item.get("SJLHZ")),
                        "currency": "CNY",
                    },
                    "source_id": "eastmoney_financial_summary",
                    "source_uri": "https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPT_LICO_FN_CPD",
                }
            )
            if limit and len(rows) >= limit:
                return rows
        pages = int(result.get("pages") or page)
        if page >= pages:
            break
        if max_pages and page >= max_pages:
            break
        page += 1
    return rows


def known_us_tickers(dsn: str, *, limit: int = 0, missing_only: bool = False, offset: int = 0, min_market_cap: float = 0.0) -> list[str]:
    where_missing = "AND NOT (i.payload->'fundamentals' ? 'financial_summary')" if missing_only else ""
    where_market_cap = f"AND coalesce((i.payload #>> '{{valuation_metrics,market_cap}}')::numeric, 0) >= {float(min_market_cap)}" if min_market_cap else ""
    limit_sql = f"LIMIT {int(limit)}" if limit else ""
    offset_sql = f"OFFSET {int(offset)}" if offset else ""
    query = f"""
SELECT upper(s.payload->>'ticker') AS ticker
FROM ai_quant.records s
JOIN ai_quant.records i ON i.collection='issuers' AND i.item_id=s.payload->>'issuer_id'
WHERE s.collection='securities'
  AND s.payload->>'market'='U'
  AND coalesce(s.payload->>'ticker','') <> ''
  {where_missing}
  {where_market_cap}
GROUP BY 1
ORDER BY max(coalesce((i.payload #>> '{{valuation_metrics,market_cap}}')::numeric, 0)) DESC, 1
{limit_sql}
{offset_sql}
"""
    result = subprocess.run(
        ["psql", dsn, "-X", "-q", "-t", "-A", "-c", query],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def parse_nasdaq_financial_table(table: dict[str, Any]) -> dict[str, Any]:
    headers = table.get("headers") or {}
    period_keys = [key for key in sorted(headers) if key.startswith("value") and key != "value1"]
    periods = [clean_text(headers.get(key)) for key in period_keys]
    metrics: dict[str, dict[str, Any]] = {period: {} for period in periods if period}
    label_map = {
        "Total Revenue": "total_revenue",
        "Gross Profit": "gross_profit",
        "Operating Income": "operating_income",
        "Net Income": "net_income",
        "EBITDA": "ebitda",
        "Total Assets": "total_assets",
        "Total Liabilities": "total_liabilities",
        "Total Equity": "total_equity",
        "Cash and Cash Equivalents": "cash_and_equivalents",
        "Net Cash Flow": "net_cash_flow",
        "Cash Flow-Operating Activities": "operating_cash_flow",
        "Cash Flow-Investing Activities": "investing_cash_flow",
        "Cash Flow-Financing Activities": "financing_cash_flow",
        "Current Ratio": "current_ratio",
        "Return on Equity": "return_on_equity",
        "Return on Assets": "return_on_assets",
        "Profit Margin": "profit_margin",
    }
    for row in table.get("rows") or []:
        label = clean_text(row.get("value1"))
        metric = label_map.get(label)
        if not metric:
            continue
        for key, period in zip(period_keys, periods, strict=False):
            if period:
                value = clean_number(row.get(key))
                if value is not None:
                    metrics[period][metric] = value
    return {period: values for period, values in metrics.items() if values}


def fetch_nasdaq_financial_row(ticker: str) -> dict[str, Any] | None:
    safe = re.sub(r"[^A-Za-z0-9.-]", "", ticker).upper()
    if not safe:
        return None
    payload = fetch_json(
        f"https://api.nasdaq.com/api/company/{safe}/financials?frequency=1",
        headers={"User-Agent": "Mozilla/5.0", "Referer": f"https://www.nasdaq.com/market-activity/stocks/{safe.lower()}/financials"},
        retries=2,
    )
    data = payload.get("data") or {}
    if not data:
        return None
    summary = {
        "income_statement": parse_nasdaq_financial_table(data.get("incomeStatementTable") or {}),
        "balance_sheet": parse_nasdaq_financial_table(data.get("balanceSheetTable") or {}),
        "cash_flow": parse_nasdaq_financial_table(data.get("cashFlowTable") or {}),
        "financial_ratios": parse_nasdaq_financial_table(data.get("financialRatiosTable") or {}),
    }
    summary = {key: value for key, value in summary.items() if value}
    if not summary:
        return None
    return {
        "ticker": safe,
        "fundamentals": summary,
        "source_id": "nasdaq_company_financials",
        "source_uri": f"https://api.nasdaq.com/api/company/{safe}/financials?frequency=1",
    }


def fetch_nasdaq_financial_rows(tickers: list[str], *, sleep_seconds: float = 0.15) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for ticker in tickers:
        try:
            row = fetch_nasdaq_financial_row(ticker)
            if row:
                rows.append(row)
            else:
                errors.append({"ticker": ticker, "error": "empty_financials"})
        except Exception as exc:
            errors.append({"ticker": ticker, "error": f"{type(exc).__name__}: {exc}"[:500]})
        if sleep_seconds:
            time.sleep(sleep_seconds)
    return rows, errors


def write_json_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        for row in rows:
            writer.writerow([json.dumps(row, ensure_ascii=False, sort_keys=True)])


def run_psql_file(sql_path: Path, *, dsn: str) -> None:
    subprocess.run(["psql", dsn, "-X", "-v", "ON_ERROR_STOP=1", "-f", str(sql_path)], check=True)


def apply_financial_backfill(rows: list[dict[str, Any]], *, market: str, dsn: str) -> dict[str, Any]:
    now = utc_iso()
    for row in rows:
        row["market"] = market
        row["backfilled_at"] = now
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        csv_path = tmp / "financial_rows.csv"
        sql_path = tmp / "apply_financials.sql"
        write_json_csv(csv_path, rows)
        sql_path.write_text(
            f"""
CREATE TEMP TABLE company_financials_backfill (payload jsonb);
\\copy company_financials_backfill(payload) FROM '{csv_path}' WITH (FORMAT csv)

WITH src AS (
    SELECT payload FROM company_financials_backfill
),
security_match AS (
    SELECT
        s.item_id AS security_item_id,
        s.payload->>'issuer_id' AS issuer_id,
        src.payload AS src_payload
    FROM ai_quant.records s
    JOIN src ON s.collection='securities'
        AND s.payload->>'market' = src.payload->>'market'
        AND upper(s.payload->>'ticker') = upper(src.payload->>'ticker')
),
issuer_src AS (
    SELECT DISTINCT ON (issuer_id) issuer_id, src_payload
    FROM security_match
    ORDER BY issuer_id
),
updated_issuers AS (
    UPDATE ai_quant.records i
    SET payload =
        i.payload
        || jsonb_build_object(
            'fundamentals',
            coalesce(i.payload->'fundamentals', '{{}}'::jsonb)
            || jsonb_build_object(
                'financial_summary', coalesce(isrc.src_payload->'fundamentals', '{{}}'::jsonb),
                'financial_source_id', isrc.src_payload->>'source_id',
                'financial_source_uri', isrc.src_payload->>'source_uri',
                'financial_backfilled_at', isrc.src_payload->>'backfilled_at'
            ),
            'data_sources', (
                SELECT jsonb_agg(DISTINCT value)
                FROM jsonb_array_elements_text(coalesce(i.payload->'data_sources', '[]'::jsonb) || jsonb_build_array(isrc.src_payload->>'source_id')) AS value
            ),
            'updated_at', '{now}'
        )
    FROM issuer_src isrc
    WHERE i.collection='issuers' AND i.item_id=isrc.issuer_id
    RETURNING i.item_id
),
updated_positions AS (
    UPDATE ai_quant.records p
    SET payload =
        p.payload
        || jsonb_build_object(
            'profit_exposure',
            coalesce(p.payload->'profit_exposure', '{{}}'::jsonb)
            || jsonb_build_object(
                'financial_summary', coalesce(sm.src_payload->'fundamentals', '{{}}'::jsonb),
                'source_id', sm.src_payload->>'source_id',
                'source_uri', sm.src_payload->>'source_uri',
                'backfilled_at', sm.src_payload->>'backfilled_at'
            ),
            'data_quality', CASE
                WHEN coalesce(p.payload->>'data_quality', '') = 'public_basic_info_backfilled' THEN 'public_basic_and_financials_backfilled'
                ELSE coalesce(nullif(p.payload->>'data_quality', ''), 'public_financials_backfilled')
            END
        )
    FROM security_match sm
    WHERE p.collection='company_positions'
      AND p.payload->>'issuer_id' = sm.issuer_id
    RETURNING p.item_id
)
SELECT
    (SELECT count(*) FROM security_match) AS matched_securities,
    (SELECT count(*) FROM updated_issuers) AS updated_issuers,
    (SELECT count(*) FROM updated_positions) AS updated_positions;
""",
            encoding="utf-8",
        )
        run_psql_file(sql_path, dsn=dsn)
    return {"market": market, "input_rows": len(rows)}


def coverage(dsn: str) -> dict[str, Any]:
    query = """
SELECT jsonb_build_object(
    'issuer_financial_summary', (SELECT jsonb_object_agg(country, jsonb_build_object('with_financial_summary', with_financial_summary, 'total', total)) FROM (
        SELECT payload->>'country' AS country, count(*) FILTER (WHERE payload->'fundamentals' ? 'financial_summary') AS with_financial_summary, count(*) AS total
        FROM ai_quant.records WHERE collection='issuers' GROUP BY 1
    ) i),
    'company_position_financial_summary', (SELECT jsonb_object_agg(market, jsonb_build_object('with_financial_summary', with_financial_summary, 'total', total)) FROM (
        SELECT s.payload->>'market' AS market, count(*) FILTER (WHERE p.payload->'profit_exposure' ? 'financial_summary') AS with_financial_summary, count(*) AS total
        FROM ai_quant.records p
        JOIN ai_quant.records s ON s.collection='securities' AND s.item_id=p.payload->>'security_id'
        WHERE p.collection='company_positions'
        GROUP BY 1
    ) p)
)
"""
    result = subprocess.run(
        ["psql", dsn, "-X", "-q", "-t", "-A", "-c", f"COPY ({query}) TO STDOUT WITH (FORMAT csv, HEADER false, QUOTE E'\\x01', DELIMITER E'\\x02');"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return json.loads(lines[0]) if lines else {}


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill public financial summaries into issuer fundamentals and company positions.")
    parser.add_argument("--dsn", default=DEFAULT_DSN)
    parser.add_argument("--market", choices=["A", "U", "both"], default="both")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--ashare-all-pages", action="store_true")
    parser.add_argument("--ashare-max-pages", type=int, default=40)
    parser.add_argument("--us-missing-only", action="store_true")
    parser.add_argument("--us-sleep-seconds", type=float, default=0.15)
    parser.add_argument("--us-offset", type=int, default=0)
    parser.add_argument("--us-min-market-cap", type=float, default=0.0)
    parser.add_argument("--artifact", type=Path, default=DEFAULT_ARTIFACT)
    args = parser.parse_args()

    summary: dict[str, Any] = {"started_at": utc_iso(), "markets": {}, "sources": [], "errors": {}}
    if args.market in {"A", "both"}:
        rows = fetch_eastmoney_financial_rows(limit=args.limit, latest_only=not args.ashare_all_pages, max_pages=0 if args.ashare_all_pages else args.ashare_max_pages)
        summary["markets"]["A"] = apply_financial_backfill(rows, market="A", dsn=args.dsn)
        summary["markets"]["A"]["latest_only"] = not args.ashare_all_pages
        summary["markets"]["A"]["max_pages"] = 0 if args.ashare_all_pages else args.ashare_max_pages
        summary["sources"].append("eastmoney_financial_summary")
    if args.market in {"U", "both"}:
        tickers = known_us_tickers(args.dsn, limit=args.limit, missing_only=args.us_missing_only, offset=args.us_offset, min_market_cap=args.us_min_market_cap)
        rows, errors = fetch_nasdaq_financial_rows(tickers, sleep_seconds=args.us_sleep_seconds)
        summary["markets"]["U"] = apply_financial_backfill(rows, market="U", dsn=args.dsn)
        summary["markets"]["U"]["requested_tickers"] = len(tickers)
        summary["markets"]["U"]["offset"] = args.us_offset
        summary["markets"]["U"]["min_market_cap"] = args.us_min_market_cap
        summary["errors"]["U"] = errors[:200]
        summary["error_counts"] = {"U": len(errors)}
        summary["sources"].append("nasdaq_company_financials")
    summary["completed_at"] = utc_iso()
    summary["coverage"] = coverage(args.dsn)
    summary["usage_boundary"] = "public_financial_summary_research_only_no_real_trading"
    args.artifact.parent.mkdir(parents=True, exist_ok=True)
    args.artifact.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
