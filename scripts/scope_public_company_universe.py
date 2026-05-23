from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any


DEFAULT_DSN = os.getenv("AI_QUANT_POSTGRES_DSN", "postgresql://ai_quant:ai_quant_dev_password@127.0.0.1:15432/ai_quant")
DEFAULT_ARTIFACT = Path("artifacts/public-company-universe-scope.json")


def run_query_json(query: str, dsn: str) -> dict[str, Any]:
    command = ["psql", dsn, "-X", "-q", "-t", "-A", "-c", f"SELECT jsonb_pretty(({query})::jsonb);"]
    result = subprocess.run(command, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return json.loads(result.stdout)


def run_sql(sql: str, dsn: str) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".sql", encoding="utf-8", delete=False) as handle:
        handle.write(sql)
        path = Path(handle.name)
    try:
        subprocess.run(["psql", dsn, "-X", "-v", "ON_ERROR_STOP=1", "-f", str(path)], check=True)
    finally:
        path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Constrain automated company universe to records verified by public company info backfill.")
    parser.add_argument("--dsn", default=DEFAULT_DSN)
    parser.add_argument("--artifact", type=Path, default=DEFAULT_ARTIFACT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    before = run_query_json(
        """
jsonb_build_object(
  'ashare_in_scope', (SELECT count(*) FROM ai_quant.records WHERE collection='securities' AND payload->>'market'='A' AND payload->>'company_universe_scope'='in_scope'),
  'ashare_in_scope_without_industry', (SELECT count(*) FROM ai_quant.records WHERE collection='securities' AND payload->>'market'='A' AND payload->>'company_universe_scope'='in_scope' AND coalesce(payload->>'industry','')=''),
  'ashare_directory_positions', (SELECT count(*) FROM ai_quant.records WHERE collection='company_positions' AND item_id LIKE 'pos_a_%_industry'),
  'ashare_directory_positions_without_industry', (SELECT count(*) FROM ai_quant.records WHERE collection='company_positions' AND item_id LIKE 'pos_a_%_industry' AND coalesce(payload #>> '{revenue_exposure,industry}','') IN ('','待补行业','未分类行业')),
  'ashare_directory_positions_non_company', (SELECT count(*) FROM ai_quant.records WHERE collection='company_positions' AND item_id LIKE 'pos_a_%_industry' AND coalesce(payload #>> '{revenue_exposure,industry}','') = '非公司类证券')
)
""",
        args.dsn,
    )

    sql = """
WITH stale AS (
    SELECT DISTINCT
        s.item_id AS security_item_id,
        s.payload->>'issuer_id' AS issuer_id
    FROM ai_quant.records p
    JOIN ai_quant.records s ON s.collection = 'securities' AND s.item_id = p.payload->>'security_id'
    WHERE p.collection = 'company_positions'
      AND p.item_id LIKE 'pos_a_%_industry'
      AND s.payload->>'market' = 'A'
      AND coalesce(p.payload #>> '{revenue_exposure,industry}', '') IN ('', '待补行业', '未分类行业', '非公司类证券')
),
updated_securities AS (
    UPDATE ai_quant.records s
    SET payload = s.payload
        || jsonb_build_object(
            'company_universe_scope', 'out_of_scope',
            'company_universe_reason', CASE
                WHEN coalesce(s.payload->>'market', '') = 'A' THEN 'not_a_current_public_company_or_missing_public_company_info'
                ELSE 'not_matched_by_current_public_company_info_backfill'
            END,
            'status', 'review_required'
        )
    FROM stale
    WHERE s.collection = 'securities' AND s.item_id = stale.security_item_id
    RETURNING s.item_id
),
updated_issuers AS (
    UPDATE ai_quant.records i
    SET payload = i.payload
        || jsonb_build_object(
            'company_universe_scope', 'out_of_scope',
            'company_universe_reason', 'not_a_current_public_company_or_missing_public_company_info',
            'status', 'review_required'
        )
    FROM stale
    WHERE i.collection = 'issuers' AND i.item_id = stale.issuer_id
    RETURNING i.item_id
),
deleted_positions AS (
    DELETE FROM ai_quant.records p
    USING stale
    WHERE p.collection = 'company_positions'
      AND p.item_id LIKE 'pos_a_%_industry'
      AND p.payload->>'issuer_id' = stale.issuer_id
    RETURNING p.item_id
)
SELECT
    (SELECT count(*) FROM updated_securities) AS updated_securities,
    (SELECT count(*) FROM updated_issuers) AS updated_issuers,
    (SELECT count(*) FROM deleted_positions) AS deleted_positions;
"""
    if not args.dry_run:
        run_sql(sql, args.dsn)

    after = run_query_json(
        """
jsonb_build_object(
  'ashare_in_scope', (SELECT count(*) FROM ai_quant.records WHERE collection='securities' AND payload->>'market'='A' AND payload->>'company_universe_scope'='in_scope'),
  'ashare_in_scope_without_industry', (SELECT count(*) FROM ai_quant.records WHERE collection='securities' AND payload->>'market'='A' AND payload->>'company_universe_scope'='in_scope' AND coalesce(payload->>'industry','')=''),
  'ashare_directory_positions', (SELECT count(*) FROM ai_quant.records WHERE collection='company_positions' AND item_id LIKE 'pos_a_%_industry'),
  'ashare_directory_positions_without_industry', (SELECT count(*) FROM ai_quant.records WHERE collection='company_positions' AND item_id LIKE 'pos_a_%_industry' AND coalesce(payload #>> '{revenue_exposure,industry}','') IN ('','待补行业','未分类行业')),
  'ashare_directory_positions_non_company', (SELECT count(*) FROM ai_quant.records WHERE collection='company_positions' AND item_id LIKE 'pos_a_%_industry' AND coalesce(payload #>> '{revenue_exposure,industry}','') = '非公司类证券')
)
""",
        args.dsn,
    )
    artifact = {
        "dry_run": args.dry_run,
        "before": before,
        "after": after,
        "policy": "A-share automated production universe keeps current public companies in company_positions; unmatched TDX historical/stale symbols and non-company securities remain in the securities directory but leave automated industry-chain positions.",
    }
    args.artifact.parent.mkdir(parents=True, exist_ok=True)
    args.artifact.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
