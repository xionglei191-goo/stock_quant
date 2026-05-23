from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess


DEFAULT_DSN = "postgresql://ai_quant:ai_quant_dev_password@127.0.0.1:15432/ai_quant"
DEFAULT_OUTPUT = Path("artifacts/company-basic-info-production-audit.json")


def fetch_audit(dsn: str) -> dict:
    query = """
SELECT jsonb_build_object(
  'securities_by_market_scope_status', (
    SELECT jsonb_agg(row_to_json(t))
    FROM (
      SELECT payload->>'market' AS market, coalesce(payload->>'company_universe_scope','') AS scope, payload->>'status' AS status, count(*) AS count
      FROM ai_quant.records
      WHERE collection='securities'
      GROUP BY 1,2,3
      ORDER BY 1,2,3
    ) t
  ),
  'positions_by_market', (
    SELECT jsonb_object_agg(market, jsonb_build_object(
      'total', total,
      'with_industry', with_industry,
      'with_financial_summary', with_financial_summary,
      'industry_coverage_ratio', round(with_industry::numeric / nullif(total,0), 6),
      'financial_coverage_ratio', round(with_financial_summary::numeric / nullif(total,0), 6)
    ))
    FROM (
      SELECT s.payload->>'market' AS market,
             count(*) AS total,
             count(*) FILTER (WHERE coalesce(p.payload #>> '{revenue_exposure,industry}','') NOT IN ('','待补行业','未分类行业')) AS with_industry,
             count(*) FILTER (WHERE p.payload->'profit_exposure' ? 'financial_summary') AS with_financial_summary
      FROM ai_quant.records p
      JOIN ai_quant.records s ON s.collection='securities' AND s.item_id=p.payload->>'security_id'
      WHERE p.collection='company_positions'
      GROUP BY 1
    ) p
  ),
  'ashare_directory_positions', (
    SELECT jsonb_build_object(
      'total', count(*),
      'with_industry', count(*) FILTER (WHERE coalesce(payload #>> '{revenue_exposure,industry}','') NOT IN ('','待补行业','未分类行业')),
      'with_financial_summary', count(*) FILTER (WHERE payload->'profit_exposure' ? 'financial_summary')
    )
    FROM ai_quant.records
    WHERE collection='company_positions' AND item_id LIKE 'pos_a_%_industry'
  ),
  'issuers_by_country', (
    SELECT jsonb_object_agg(country, jsonb_build_object(
      'total', total,
      'with_industry', with_industry,
      'with_valuation', with_valuation,
      'with_details', with_details,
	      'with_financial_summary', with_financial_summary,
	      'with_financial_unavailable', with_financial_unavailable,
	      'with_financial_deferred', with_financial_deferred,
	      'with_financial_unknown', with_financial_unknown,
	      'with_cik', with_cik
	    ))
    FROM (
      SELECT payload->>'country' AS country,
             count(*) AS total,
             count(*) FILTER (WHERE coalesce(payload->>'industry','') <> '') AS with_industry,
             count(*) FILTER (WHERE coalesce(payload->'valuation_metrics','{}'::jsonb) <> '{}'::jsonb) AS with_valuation,
             count(*) FILTER (WHERE coalesce(payload->'company_details','{}'::jsonb) <> '{}'::jsonb) AS with_details,
	             count(*) FILTER (WHERE coalesce(payload->'fundamentals', '{}'::jsonb) ? 'financial_summary') AS with_financial_summary,
	             count(*) FILTER (WHERE (coalesce(payload->'fundamentals', '{}'::jsonb)->>'financial_unavailable')::boolean IS TRUE) AS with_financial_unavailable,
	             count(*) FILTER (WHERE coalesce(coalesce(payload->'fundamentals', '{}'::jsonb)->>'financial_accounting_status', '') = 'deferred_resumable') AS with_financial_deferred,
	             count(*) FILTER (
	               WHERE NOT (coalesce(payload->'fundamentals', '{}'::jsonb) ? 'financial_summary')
	                 AND NOT ((coalesce(payload->'fundamentals', '{}'::jsonb)->>'financial_unavailable')::boolean IS TRUE)
	                 AND coalesce(coalesce(payload->'fundamentals', '{}'::jsonb)->>'financial_accounting_status', '') = ''
	             ) AS with_financial_unknown,
             count(*) FILTER (WHERE coalesce(payload->>'cik','') <> '') AS with_cik
      FROM ai_quant.records
      WHERE collection='issuers'
      GROUP BY 1
    ) i
  )
)
"""
    result = subprocess.run(["psql", dsn, "-X", "-q", "-t", "-A", "-c", query], check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return json.loads(result.stdout.strip())


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit company basic info coverage for local production readiness.")
    parser.add_argument("--dsn", default=DEFAULT_DSN)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--min-us-financial-positions", type=int, default=300)
    args = parser.parse_args()

    data = fetch_audit(args.dsn)
    positions = data.get("positions_by_market") or {}
    issuers = data.get("issuers_by_country") or {}
    a_positions = data.get("ashare_directory_positions") or {}
    u_positions = positions.get("U") or {}
    cn = issuers.get("CN") or {}
    us = issuers.get("US") or {}
    gates = [
        {"gate": "ashare_position_industry_full", "passed": int(a_positions.get("with_industry") or 0) == int(a_positions.get("total") or -1)},
        {"gate": "ashare_position_financial_full", "passed": int(a_positions.get("with_financial_summary") or 0) == int(a_positions.get("total") or -1)},
        {"gate": "cn_issuer_valuation_present", "passed": int(cn.get("with_valuation") or 0) >= int(a_positions.get("total") or 0)},
        {"gate": "cn_issuer_details_present", "passed": int(cn.get("with_details") or 0) >= int(a_positions.get("total") or 0)},
        {"gate": "us_issuer_cik_mostly_present", "passed": int(us.get("with_cik") or 0) >= 5000},
        {"gate": "us_position_industry_mostly_present", "passed": int(u_positions.get("with_industry") or 0) >= 5000},
        {"gate": "us_issuer_valuation_mostly_present", "passed": int(us.get("with_valuation") or 0) >= 5000},
        {"gate": "us_issuer_details_mostly_present", "passed": int(us.get("with_details") or 0) >= 5000},
        {"gate": "us_financial_core_batch_present", "passed": int(u_positions.get("with_financial_summary") or 0) >= args.min_us_financial_positions},
        {
            "gate": "us_financial_status_accounted_for",
            "passed": int(us.get("with_financial_unknown") or 0) == 0,
        },
    ]
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "coverage": data,
        "gates": gates,
        "ready_for_local_production_basic_info": all(gate["passed"] for gate in gates),
        "usage_boundary": "local_research_basic_info_readiness_not_real_trading",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ready_for_local_production_basic_info"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
