from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DEFAULT_DSN = os.getenv("AI_QUANT_POSTGRES_DSN", "postgresql://ai_quant:ai_quant_dev_password@127.0.0.1:15432/ai_quant")
DEFAULT_ARTIFACT = Path("artifacts/company-fundamentals-public-backfill.json")
USER_AGENT = "company-intelligence-platform/0.1 local-research"


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch_json(url: str, *, headers: dict[str, str] | None = None, retries: int = 5, timeout: int = 30) -> dict[str, Any]:
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
            time.sleep(min(10, attempt * 1.5))
    raise RuntimeError(f"fetch_json failed: {url}: {last_error}") from last_error


def clean_text(value: Any) -> str:
    text = str(value if value is not None else "").strip()
    return "" if text in {"-", "--", "None", "null"} else text


def clean_number(value: Any) -> float | None:
    text = clean_text(value).replace(",", "").replace("%", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def market_cap_to_float(value: Any) -> float | None:
    text = clean_text(value).replace("$", "").replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def exchange_from_eastmoney(code: str, market_code: Any) -> str:
    market = str(market_code or "")
    if market == "1":
        return "SSE"
    if market == "0":
        return "SZSE"
    if market == "2":
        return "BSE"
    if code.startswith(("6", "9")):
        return "SSE"
    if code.startswith(("8", "4")):
        return "BSE"
    return "SZSE"


def fetch_eastmoney_ashare(limit: int = 0) -> list[dict[str, Any]]:
    fields = "f12,f14,f13,f100,f102,f103,f2,f3,f8,f9,f20,f21,f23"
    fs = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81,m:0+t:83"
    hosts = ["push2delay.eastmoney.com", "push2.eastmoney.com", "push2his.eastmoney.com"]
    rows: list[dict[str, Any]] = []
    page = 1
    page_size = 500
    while True:
        params = {
            "pn": page,
            "pz": page_size,
            "po": 1,
            "np": 1,
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": 2,
            "invt": 2,
            "fid": "f3",
            "fs": fs,
            "fields": fields,
        }
        last_error: Exception | None = None
        payload: dict[str, Any] | None = None
        for host in hosts:
            try:
                payload = fetch_json(
                    f"https://{host}/api/qt/clist/get?{urlencode(params)}",
                    headers={"Referer": "https://quote.eastmoney.com/center/gridlist.html"},
                    retries=1,
                )
                break
            except Exception as exc:
                last_error = exc
        if payload is None:
            raise RuntimeError(f"Eastmoney clist fetch failed for page {page}: {last_error}") from last_error
        data = payload.get("data") or {}
        diff = data.get("diff") or []
        if not diff:
            break
        for item in diff:
            code = clean_text(item.get("f12"))
            name = clean_text(item.get("f14"))
            if not code or not name:
                continue
            industry = clean_text(item.get("f100")) or "未分类行业"
            concepts = [part.strip() for part in clean_text(item.get("f103")).split(",") if part.strip()]
            rows.append(
                {
                    "ticker": code,
                    "name": name,
                    "exchange": exchange_from_eastmoney(code, item.get("f13")),
                    "industry": industry,
                    "region": clean_text(item.get("f102")),
                    "concepts": concepts[:20],
                    "valuation_metrics": {
                        "close": clean_number(item.get("f2")),
                        "pct_change": clean_number(item.get("f3")),
                        "turnover_rate": clean_number(item.get("f8")),
                        "pe_ttm": clean_number(item.get("f9")),
                        "market_cap": clean_number(item.get("f20")),
                        "free_float_market_cap": clean_number(item.get("f21")),
                        "pb": clean_number(item.get("f23")),
                        "currency": "CNY",
                    },
                    "source_id": "eastmoney_ashare_company_list",
                    "source_uri": "https://push2.eastmoney.com/api/qt/clist/get",
                }
            )
            if limit and len(rows) >= limit:
                return rows
        total = int(data.get("total") or len(rows))
        if len(rows) >= total:
            break
        page += 1
    return rows


def fetch_sec_tickers() -> dict[str, dict[str, Any]]:
    payload = fetch_json(
        "https://www.sec.gov/files/company_tickers_exchange.json",
        headers={"User-Agent": os.getenv("AI_QUANT_SEC_USER_AGENT", USER_AGENT), "Accept": "application/json"},
    )
    fields = payload.get("fields") or []
    result: dict[str, dict[str, Any]] = {}
    for row in payload.get("data") or []:
        item = dict(zip(fields, row, strict=False))
        ticker = clean_text(item.get("ticker")).upper()
        if ticker:
            result[ticker] = item
    return result


def fetch_nasdaq_rows(limit: int = 0) -> dict[str, dict[str, Any]]:
    params = {"tableonly": "true", "limit": 25000, "offset": 0, "download": "true"}
    payload = fetch_json(
        f"https://api.nasdaq.com/api/screener/stocks?{urlencode(params)}",
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://www.nasdaq.com",
            "Referer": "https://www.nasdaq.com/market-activity/stocks/screener",
        },
    )
    rows = (payload.get("data") or {}).get("rows") or []
    result: dict[str, dict[str, Any]] = {}
    for row in rows[: limit or None]:
        ticker = clean_text(row.get("symbol")).upper()
        if ticker:
            result[ticker] = row
    return result


def merged_us_rows(limit: int = 0) -> list[dict[str, Any]]:
    sec_error = ""
    try:
        sec_rows = fetch_sec_tickers()
    except Exception as exc:
        sec_rows = {}
        sec_error = f"{type(exc).__name__}: {exc}"
    nasdaq_rows = fetch_nasdaq_rows(limit=0)
    tickers = sorted(set(sec_rows) | set(nasdaq_rows))
    if limit:
        tickers = tickers[:limit]
    rows: list[dict[str, Any]] = []
    for ticker in tickers:
        sec = sec_rows.get(ticker, {})
        nasdaq = nasdaq_rows.get(ticker, {})
        rows.append(
            {
                "ticker": ticker,
                "name": clean_text(nasdaq.get("name")) or clean_text(sec.get("name")),
                "exchange": clean_text(sec.get("exchange")) or clean_text(nasdaq.get("exchange")),
                "cik": str(sec.get("cik") or "").zfill(10) if sec.get("cik") not in {None, ""} else "",
                "sector": clean_text(nasdaq.get("sector")),
                "industry": clean_text(nasdaq.get("industry")),
                "country": clean_text(nasdaq.get("country")) or "US",
                "ipo_year": clean_text(nasdaq.get("ipoyear")),
                "valuation_metrics": {
                    "last_sale": market_cap_to_float(nasdaq.get("lastsale")),
                    "net_change": clean_number(nasdaq.get("netchange")),
                    "pct_change": clean_number(nasdaq.get("pctchange")),
                    "market_cap": market_cap_to_float(nasdaq.get("marketCap")),
                    "volume": market_cap_to_float(nasdaq.get("volume")),
                    "currency": "USD",
                },
                "source_id": "nasdaq_screener_sec_company_tickers",
                "source_uri": "https://api.nasdaq.com/api/screener/stocks + https://www.sec.gov/files/company_tickers_exchange.json",
                "source_warning": sec_error,
            }
        )
    return rows


def psql_json(query: str, *, dsn: str = DEFAULT_DSN) -> list[dict[str, Any]]:
    with tempfile.NamedTemporaryFile("w+", suffix=".json", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        command = ["psql", dsn, "-X", "-q", "-t", "-A", "-c", f"COPY ({query}) TO STDOUT WITH (FORMAT csv, HEADER false, QUOTE E'\\x01', DELIMITER E'\\x02');"]
        result = subprocess.run(command, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        rows: list[dict[str, Any]] = []
        for raw in result.stdout.splitlines():
            if raw.strip():
                rows.append(json.loads(raw))
        return rows
    finally:
        tmp_path.unlink(missing_ok=True)


def write_json_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        for row in rows:
            writer.writerow([json.dumps(row, ensure_ascii=False, sort_keys=True)])


def run_psql_file(sql_path: Path, *, dsn: str = DEFAULT_DSN) -> None:
    subprocess.run(["psql", dsn, "-X", "-v", "ON_ERROR_STOP=1", "-f", str(sql_path)], check=True)


def apply_backfill(rows: list[dict[str, Any]], *, market: str, dsn: str = DEFAULT_DSN) -> dict[str, Any]:
    now = utc_iso()
    for row in rows:
        row["market"] = market
        row["backfilled_at"] = now
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        jsonl_path = tmp / "rows.csv"
        sql_path = tmp / "apply.sql"
        write_json_csv(jsonl_path, rows)
        sql_path.write_text(
            f"""
CREATE TEMP TABLE company_fundamentals_backfill (payload jsonb);
\\copy company_fundamentals_backfill(payload) FROM '{jsonl_path}' WITH (FORMAT csv)

WITH src AS (
    SELECT payload FROM company_fundamentals_backfill
),
security_match AS (
    SELECT
        s.collection,
        s.item_id,
        s.payload AS security_payload,
        src.payload AS src_payload,
        s.payload->>'issuer_id' AS issuer_id
    FROM ai_quant.records s
    JOIN src ON s.collection = 'securities'
        AND s.payload->>'market' = src.payload->>'market'
        AND upper(s.payload->>'ticker') = upper(src.payload->>'ticker')
),
updated_securities AS (
    UPDATE ai_quant.records s
    SET payload =
        s.payload
        || jsonb_strip_nulls(jsonb_build_object(
            'exchange', nullif(sm.src_payload->>'exchange', ''),
            'sector', nullif(sm.src_payload->>'sector', ''),
            'industry', nullif(sm.src_payload->>'industry', ''),
            'listing_date', nullif(sm.src_payload->>'ipo_year', ''),
            'board', nullif(sm.src_payload->>'region', '')
        ))
    FROM security_match sm
    WHERE s.collection = 'securities' AND s.item_id = sm.item_id
    RETURNING s.item_id
),
issuer_src AS (
    SELECT DISTINCT ON (issuer_id)
        issuer_id,
        src_payload
    FROM security_match
    ORDER BY issuer_id
),
updated_issuers AS (
    UPDATE ai_quant.records i
    SET payload =
        i.payload
        || jsonb_strip_nulls(jsonb_build_object(
            'legal_name', coalesce(nullif(isrc.src_payload->>'name', ''), i.payload->>'legal_name'),
            'cik', coalesce(nullif(isrc.src_payload->>'cik', ''), i.payload->>'cik'),
            'sector', nullif(isrc.src_payload->>'sector', ''),
            'industry', nullif(isrc.src_payload->>'industry', ''),
            'region', nullif(isrc.src_payload->>'region', ''),
            'updated_at', '{now}'
        ))
        || jsonb_build_object(
            'company_details', coalesce(i.payload->'company_details', '{{}}'::jsonb) || jsonb_strip_nulls(jsonb_build_object(
                'country', nullif(isrc.src_payload->>'country', ''),
                'ipo_year', nullif(isrc.src_payload->>'ipo_year', ''),
                'concepts', coalesce(isrc.src_payload->'concepts', '[]'::jsonb),
                'source_uri', isrc.src_payload->>'source_uri'
            )),
            'valuation_metrics', coalesce(i.payload->'valuation_metrics', '{{}}'::jsonb) || coalesce(isrc.src_payload->'valuation_metrics', '{{}}'::jsonb),
            'fundamentals', coalesce(i.payload->'fundamentals', '{{}}'::jsonb) || jsonb_strip_nulls(jsonb_build_object(
                'sector', nullif(isrc.src_payload->>'sector', ''),
                'industry', nullif(isrc.src_payload->>'industry', ''),
                'region', nullif(isrc.src_payload->>'region', '')
            )),
            'data_sources', (
                SELECT jsonb_agg(DISTINCT value)
                FROM jsonb_array_elements_text(coalesce(i.payload->'data_sources', '[]'::jsonb) || jsonb_build_array(isrc.src_payload->>'source_id')) AS value
            )
        )
    FROM issuer_src isrc
    WHERE i.collection = 'issuers' AND i.item_id = isrc.issuer_id
    RETURNING i.item_id
),
position_src AS (
    SELECT
        sm.issuer_id,
        sm.src_payload,
        coalesce(nullif(sm.src_payload->>'industry', ''), nullif(sm.src_payload->>'sector', ''), '未分类行业') AS industry_name
    FROM security_match sm
),
updated_positions AS (
    UPDATE ai_quant.records p
    SET payload =
        p.payload
        || jsonb_build_object(
            'revenue_exposure', coalesce(p.payload->'revenue_exposure', '{{}}'::jsonb) || jsonb_strip_nulls(jsonb_build_object(
                'industry', ps.industry_name,
                'sector', nullif(ps.src_payload->>'sector', ''),
                'region', nullif(ps.src_payload->>'region', ''),
                'concepts', coalesce(ps.src_payload->'concepts', '[]'::jsonb),
                'source_id', ps.src_payload->>'source_id',
                'source_uri', ps.src_payload->>'source_uri',
                'backfilled_at', ps.src_payload->>'backfilled_at'
            )),
            'valuation_metrics', coalesce(p.payload->'valuation_metrics', '{{}}'::jsonb) || coalesce(ps.src_payload->'valuation_metrics', '{{}}'::jsonb) || jsonb_build_object('source_id', ps.src_payload->>'source_id'),
            'data_quality', 'public_basic_info_backfilled'
        )
    FROM position_src ps
    WHERE p.collection = 'company_positions'
      AND p.payload->>'issuer_id' = ps.issuer_id
      AND p.item_id LIKE CASE WHEN ps.src_payload->>'market' = 'A' THEN 'pos_a_%_industry' ELSE 'pos_u_%_industry' END
    RETURNING p.item_id
)
SELECT
    (SELECT count(*) FROM security_match) AS matched_securities,
    (SELECT count(*) FROM updated_securities) AS updated_securities,
    (SELECT count(*) FROM updated_issuers) AS updated_issuers,
    (SELECT count(*) FROM updated_positions) AS updated_positions;
""",
            encoding="utf-8",
        )
        run_psql_file(sql_path, dsn=dsn)
    return {"input_rows": len(rows), "market": market}


def coverage(dsn: str = DEFAULT_DSN) -> dict[str, Any]:
    query = """
SELECT jsonb_build_object(
    'securities', (SELECT jsonb_object_agg(market, count) FROM (SELECT payload->>'market' AS market, count(*) AS count FROM ai_quant.records WHERE collection='securities' GROUP BY 1) s),
    'issuer_industry', (SELECT jsonb_object_agg(country, jsonb_build_object('with_industry', with_industry, 'total', total)) FROM (
        SELECT payload->>'country' AS country, count(*) FILTER (WHERE coalesce(payload->>'industry','') <> '') AS with_industry, count(*) AS total
        FROM ai_quant.records WHERE collection='issuers' GROUP BY 1
    ) i),
    'issuer_valuation', (SELECT jsonb_object_agg(country, jsonb_build_object('with_valuation', with_valuation, 'total', total)) FROM (
        SELECT payload->>'country' AS country, count(*) FILTER (WHERE coalesce(payload->'valuation_metrics', '{}'::jsonb) <> '{}'::jsonb) AS with_valuation, count(*) AS total
        FROM ai_quant.records WHERE collection='issuers' GROUP BY 1
    ) v),
    'company_position_industry_missing', (SELECT count(*) FROM ai_quant.records WHERE collection='company_positions' AND item_id LIKE 'pos_a_%_industry' AND coalesce(payload #>> '{revenue_exposure,industry}', '') IN ('', '待补行业', '未分类行业')),
    'company_position_industry_total', (SELECT count(*) FROM ai_quant.records WHERE collection='company_positions' AND item_id LIKE 'pos_a_%_industry')
)
"""
    rows = psql_json(query, dsn=dsn)
    return rows[0] if rows else {}


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill public A/U company industry, sector, valuation, and basic details.")
    parser.add_argument("--dsn", default=DEFAULT_DSN)
    parser.add_argument("--market", choices=["A", "U", "both"], default="both")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--artifact", type=Path, default=DEFAULT_ARTIFACT)
    args = parser.parse_args()

    started_at = utc_iso()
    summary: dict[str, Any] = {"started_at": started_at, "markets": {}, "sources": []}
    if args.market in {"A", "both"}:
        rows = fetch_eastmoney_ashare(limit=args.limit)
        summary["markets"]["A"] = apply_backfill(rows, market="A", dsn=args.dsn)
        summary["sources"].append("eastmoney_ashare_company_list")
    if args.market in {"U", "both"}:
        rows = merged_us_rows(limit=args.limit)
        summary["markets"]["U"] = apply_backfill(rows, market="U", dsn=args.dsn)
        summary["sources"].extend(["sec_company_tickers_exchange", "nasdaq_screener_stocks"])
    summary["completed_at"] = utc_iso()
    summary["coverage"] = coverage(dsn=args.dsn)
    summary["usage_boundary"] = "public_company_basic_info_research_only_no_real_trading"
    args.artifact.parent.mkdir(parents=True, exist_ok=True)
    args.artifact.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
