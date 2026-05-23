from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any
from urllib.request import Request, urlopen


DEFAULT_DSN = os.getenv("AI_QUANT_POSTGRES_DSN", "postgresql://ai_quant:ai_quant_dev_password@127.0.0.1:15432/ai_quant")
DEFAULT_ARTIFACT = Path("artifacts/us-cik-sec-backfill.json")


def fetch_sec_tickers() -> list[dict[str, Any]]:
    headers = {"User-Agent": os.getenv("AI_QUANT_SEC_USER_AGENT", "ai-native-quant-org/0.1 contact@example.com"), "Accept": "application/json"}
    with urlopen(Request("https://www.sec.gov/files/company_tickers_exchange.json", headers=headers), timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8", errors="replace"))
    fields = payload.get("fields") or []
    rows: list[dict[str, Any]] = []
    for raw in payload.get("data") or []:
        item = dict(zip(fields, raw, strict=False))
        ticker = str(item.get("ticker") or "").strip().upper()
        cik = str(item.get("cik") or "").strip()
        if ticker and cik:
            rows.append({"ticker": ticker, "cik": cik.zfill(10), "sec_name": str(item.get("name") or "").strip(), "sec_exchange": str(item.get("exchange") or "").strip()})
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        for row in rows:
            writer.writerow([json.dumps(row, ensure_ascii=False, sort_keys=True)])


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill US CIKs from the SEC public ticker/exchange directory.")
    parser.add_argument("--dsn", default=DEFAULT_DSN)
    parser.add_argument("--artifact", type=Path, default=DEFAULT_ARTIFACT)
    args = parser.parse_args()

    rows = fetch_sec_tickers()
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        csv_path = tmp / "sec_tickers.csv"
        sql_path = tmp / "apply.sql"
        write_csv(csv_path, rows)
        now = datetime.now(timezone.utc).isoformat()
        sql_path.write_text(
            f"""
CREATE TEMP TABLE sec_tickers_backfill (payload jsonb);
\\copy sec_tickers_backfill(payload) FROM '{csv_path}' WITH (FORMAT csv)

WITH src AS (
  SELECT payload FROM sec_tickers_backfill
),
matched AS (
  SELECT s.item_id AS security_item_id, s.payload->>'issuer_id' AS issuer_id, src.payload AS src_payload
  FROM ai_quant.records s
  JOIN src ON s.collection='securities'
    AND s.payload->>'market'='U'
    AND upper(s.payload->>'ticker') = src.payload->>'ticker'
),
updated_securities AS (
  UPDATE ai_quant.records s
  SET payload = s.payload || jsonb_strip_nulls(jsonb_build_object('exchange', nullif(m.src_payload->>'sec_exchange', '')))
  FROM matched m
  WHERE s.collection='securities' AND s.item_id=m.security_item_id
  RETURNING s.item_id
),
updated_issuers AS (
  UPDATE ai_quant.records i
  SET payload = i.payload
    || jsonb_strip_nulls(jsonb_build_object('cik', nullif(m.src_payload->>'cik', ''), 'updated_at', '{now}'))
    || jsonb_build_object(
      'company_details', coalesce(i.payload->'company_details', '{{}}'::jsonb) || jsonb_strip_nulls(jsonb_build_object('sec_name', nullif(m.src_payload->>'sec_name', ''), 'sec_exchange', nullif(m.src_payload->>'sec_exchange', ''))),
      'data_sources', (
        SELECT jsonb_agg(DISTINCT value)
        FROM jsonb_array_elements_text(coalesce(i.payload->'data_sources', '[]'::jsonb) || jsonb_build_array('sec_company_tickers_exchange')) AS value
      )
    )
  FROM matched m
  WHERE i.collection='issuers' AND i.item_id=m.issuer_id
  RETURNING i.item_id
)
SELECT
  (SELECT count(*) FROM matched) AS matched_securities,
  (SELECT count(*) FROM updated_securities) AS updated_securities,
  (SELECT count(*) FROM updated_issuers) AS updated_issuers;
""",
            encoding="utf-8",
        )
        subprocess.run(["psql", args.dsn, "-X", "-v", "ON_ERROR_STOP=1", "-f", str(sql_path)], check=True)

    coverage_sql = """
SELECT jsonb_build_object(
  'us_issuers_with_cik', count(*) FILTER (WHERE coalesce(payload->>'cik','') <> ''),
  'us_issuers_total', count(*)
)
FROM ai_quant.records
WHERE collection='issuers' AND payload->>'country'='US'
"""
    result = subprocess.run(["psql", args.dsn, "-X", "-q", "-t", "-A", "-c", coverage_sql], check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    coverage = json.loads(result.stdout.strip())
    artifact = {"rows": len(rows), "coverage": coverage, "source": "https://www.sec.gov/files/company_tickers_exchange.json", "usage_boundary": "public_sec_cik_directory_research_only"}
    args.artifact.parent.mkdir(parents=True, exist_ok=True)
    args.artifact.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
