from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess


DEFAULT_DSN = os.getenv("AI_QUANT_POSTGRES_DSN", "postgresql://ai_quant:ai_quant_dev_password@127.0.0.1:15432/ai_quant")
DEFAULT_ARTIFACT = Path("artifacts/us-financials-deferred-resumable.json")


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def mark_deferred(*, dsn: str, dry_run: bool, reason: str, manifest_uri: str) -> dict:
    now = utc_iso()
    update_clause = "SELECT item_id FROM candidates" if dry_run else f"""
UPDATE ai_quant.records i
SET payload = i.payload
  || jsonb_build_object(
    'fundamentals',
    coalesce(i.payload->'fundamentals', '{{}}'::jsonb)
    || jsonb_build_object(
      'financial_accounting_status', 'deferred_resumable',
      'financial_accounting_reason', '{reason}',
      'financial_source_id', 'sec_companyfacts',
      'financial_checked_at', '{now}',
      'financial_resume_artifact', '{manifest_uri}'
    ),
    'updated_at', '{now}'
  )
FROM candidates c
WHERE i.collection='issuers' AND i.item_id=c.item_id
RETURNING i.item_id
"""
    mark_query = f"""
WITH candidates AS (
  SELECT item_id
  FROM ai_quant.records
  WHERE collection='issuers'
    AND payload->>'country'='US'
    AND NOT (coalesce(payload->'fundamentals', '{{}}'::jsonb) ? 'financial_summary')
    AND NOT ((coalesce(payload->'fundamentals', '{{}}'::jsonb)->>'financial_unavailable')::boolean IS TRUE)
    AND coalesce(coalesce(payload->'fundamentals', '{{}}'::jsonb)->>'financial_accounting_status', '') = ''
),
marked AS (
  {update_clause}
)
SELECT count(*) FROM marked
"""
    marked_result = subprocess.run(["psql", dsn, "-X", "-q", "-t", "-A", "-c", mark_query], check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    marked_rows = int(marked_result.stdout.strip() or "0")
    coverage_query = """
WITH
coverage AS (
  SELECT jsonb_build_object(
    'us_issuers_total', count(*),
    'us_issuers_with_financial_summary', count(*) FILTER (WHERE coalesce(payload->'fundamentals', '{}'::jsonb) ? 'financial_summary'),
    'us_issuers_financial_unavailable', count(*) FILTER (WHERE (coalesce(payload->'fundamentals', '{}'::jsonb)->>'financial_unavailable')::boolean IS TRUE),
    'us_issuers_financial_deferred', count(*) FILTER (WHERE coalesce(coalesce(payload->'fundamentals', '{}'::jsonb)->>'financial_accounting_status', '') = 'deferred_resumable'),
    'us_issuers_financial_unknown', count(*) FILTER (
      WHERE NOT (coalesce(payload->'fundamentals', '{}'::jsonb) ? 'financial_summary')
        AND NOT ((coalesce(payload->'fundamentals', '{}'::jsonb)->>'financial_unavailable')::boolean IS TRUE)
        AND coalesce(coalesce(payload->'fundamentals', '{}'::jsonb)->>'financial_accounting_status', '') = ''
    )
  ) AS payload
  FROM ai_quant.records
  WHERE collection='issuers' AND payload->>'country'='US'
)
SELECT jsonb_build_object(
  'coverage', (SELECT payload FROM coverage)
)
"""
    coverage_result = subprocess.run(["psql", dsn, "-X", "-q", "-t", "-A", "-c", coverage_query], check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    coverage = json.loads(coverage_result.stdout.strip()).get("coverage", {})
    return {
        "generated_at": now,
        "dry_run": dry_run,
        "marked_rows": marked_rows,
        "reason": reason,
        "source": "sec_companyfacts",
        "resume_artifact": manifest_uri,
        "coverage": coverage,
        "usage_boundary": "local_resumable_sec_companyfacts_accounting_only_not_permanent_unavailability",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Mark remaining US SEC companyfacts financial backfill as deferred and resumable for local batch accounting.")
    parser.add_argument("--dsn", default=DEFAULT_DSN)
    parser.add_argument("--artifact", type=Path, default=DEFAULT_ARTIFACT)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--reason", default="not_in_current_local_sec_companyfacts_batch")
    parser.add_argument("--resume-artifact", default="artifacts/us-companyfacts-batches-continued/manifest.json")
    args = parser.parse_args()

    summary = mark_deferred(dsn=args.dsn, dry_run=args.dry_run, reason=args.reason, manifest_uri=args.resume_artifact)
    args.artifact.parent.mkdir(parents=True, exist_ok=True)
    args.artifact.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
