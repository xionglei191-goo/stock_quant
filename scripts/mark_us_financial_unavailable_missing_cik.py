from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess


DEFAULT_DSN = os.getenv("AI_QUANT_POSTGRES_DSN", "postgresql://ai_quant:ai_quant_dev_password@127.0.0.1:15432/ai_quant")
DEFAULT_ARTIFACT = Path("artifacts/us-financials-missing-cik-unavailable.json")


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def mark_missing_cik(*, dsn: str, dry_run: bool) -> dict:
    now = utc_iso()
    update_clause = "SELECT item_id FROM candidates" if dry_run else f"""
UPDATE ai_quant.records i
SET payload = i.payload
  || jsonb_build_object(
    'fundamentals',
    coalesce(i.payload->'fundamentals', '{{}}'::jsonb)
    || jsonb_build_object(
      'financial_unavailable', true,
      'financial_unavailable_reason', 'missing_sec_cik',
      'financial_source_id', 'sec_companyfacts',
      'financial_checked_at', '{now}'
    ),
    'updated_at', '{now}'
  )
FROM candidates c
WHERE i.collection='issuers' AND i.item_id=c.item_id
RETURNING i.item_id
"""
    query = f"""
WITH candidates AS (
  SELECT item_id
  FROM ai_quant.records
  WHERE collection='issuers'
    AND payload->>'country'='US'
    AND coalesce(payload->>'cik','') = ''
    AND NOT (coalesce(payload->'fundamentals', '{{}}'::jsonb) ? 'financial_summary')
    AND NOT ((coalesce(payload->'fundamentals', '{{}}'::jsonb)->>'financial_unavailable')::boolean IS TRUE)
),
marked AS (
  {update_clause}
),
coverage AS (
  SELECT jsonb_build_object(
    'us_issuers_total', count(*),
    'us_issuers_with_financial_summary', count(*) FILTER (WHERE coalesce(payload->'fundamentals', '{{}}'::jsonb) ? 'financial_summary'),
    'us_issuers_financial_unavailable', count(*) FILTER (WHERE (coalesce(payload->'fundamentals', '{{}}'::jsonb)->>'financial_unavailable')::boolean IS TRUE),
    'us_issuers_missing_cik', count(*) FILTER (WHERE coalesce(payload->>'cik','') = '')
  ) AS payload
  FROM ai_quant.records
  WHERE collection='issuers' AND payload->>'country'='US'
)
SELECT jsonb_build_object(
  'generated_at', '{now}',
  'dry_run', {str(dry_run).lower()},
  'marked_rows', (SELECT count(*) FROM marked),
  'reason', 'missing_sec_cik',
  'source', 'sec_companyfacts',
  'coverage', (SELECT payload FROM coverage),
  'usage_boundary', 'public_sec_companyfacts_accounting_research_only_no_real_trading'
)
"""
    result = subprocess.run(["psql", dsn, "-X", "-q", "-t", "-A", "-c", query], check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return json.loads(result.stdout.strip())


def main() -> int:
    parser = argparse.ArgumentParser(description="Mark US issuers without SEC CIK as unavailable for SEC companyfacts financial backfill.")
    parser.add_argument("--dsn", default=DEFAULT_DSN)
    parser.add_argument("--artifact", type=Path, default=DEFAULT_ARTIFACT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    summary = mark_missing_cik(dsn=args.dsn, dry_run=args.dry_run)
    args.artifact.parent.mkdir(parents=True, exist_ok=True)
    args.artifact.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
