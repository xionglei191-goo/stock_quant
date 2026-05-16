from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.staging_acceptance import DEFAULT_BASE_URL, StagingClient


def _check(name: str, passed: bool, evidence: dict[str, Any] | None = None, error: str = "") -> dict[str, Any]:
    return {"check": name, "passed": passed, "evidence": evidence or {}, "error": error}


def _record_secret_rotation(client: StagingClient, suffix: str, artifact_prefix: str, provider: str) -> dict[str, Any]:
    rotation = client.request(
        "POST",
        "/api/governance/secret-rotations",
        {
            "rotation_id": f"secrot_staging_kms_{suffix}",
            "secret_name": "AI_QUANT_EXTERNAL_API_KEYS",
            "provider": provider,
            "owner": "platform_security",
            "status": "rotated",
            "rotated_at": "2026-05-16T00:00:00+00:00",
            "next_rotation_due_at": "2026-08-14T00:00:00+00:00",
            "evidence_uri": f"{artifact_prefix.rstrip('/')}/kms-rotation-{suffix}.json",
            "notes": "Staging security acceptance records metadata only; no secret value is persisted.",
        },
        role="platform",
        actor="security_acceptance",
    )
    blocked = client.request_any(
        "POST",
        "/api/governance/secret-rotations",
        {
            "rotation_id": f"secrot_staging_blocked_{suffix}",
            "secret_name": "blocked-secret-value",
            "provider": provider,
            "owner": "platform_security",
            "api_key": "placeholder-secret-value-that-must-not-persist",
        },
        role="platform",
        actor="security_acceptance",
    )
    listed = client.request("GET", "/api/governance/secret-rotations?provider=local-development-metadata-only", role="risk_compliance", actor="security_acceptance")
    passed = (
        rotation.get("rotation_id") == f"secrot_staging_kms_{suffix}"
        and blocked["status_code"] == 422
        and all(
            not any(key in item for key in {"api_key", "secret_value", "token", "password", "private_key"})
            for item in listed.get("rotations", [])
        )
    )
    return {"status": "passed" if passed else "failed", "rotation": rotation, "blocked_secret_value_status": blocked, "listed": listed}


def _source_provenance_review(client: StagingClient, suffix: str) -> dict[str, Any]:
    client.request("POST", "/api/ingestion/sources/seed", {}, role="data_engineer", actor="security_acceptance")
    updated = client.request(
        "POST",
        "/api/governance/sources/public_eod_market_data",
        {
            "field_whitelist": ["security_id", "as_of_date", "open", "high", "low", "close", "volume", "adjusted_close"],
            "retention_policy": "retain_public_eod_with_source_uri_and_field_whitelist",
            "cache_ttl_days": 3650,
            "provenance_ref": "local://data/local/tdx/market_data.duckdb",
            "source_tos_uri": "https://www.tdx.com.cn/",
            "usage_scope": "public_or_local_eod_internal_research_backtest_risk",
            "collection_method": "local_file_or_public_api",
            "robots_policy": "reviewed_public_or_local_source",
            "last_reviewed_at": "2026-05-16T00:00:00+00:00",
            "review_owner": "data_engineering",
            "review_owner_role": "数据工程",
        },
        role="risk_compliance",
        actor="security_acceptance",
    )
    review = client.request(
        "POST",
        "/api/governance/sources/public_eod_market_data/reviews",
        {
            "review_id": f"srrev_security_public_eod_{suffix}",
            "review_period": "2026Q2",
            "status": "approved",
            "publicness_status": "confirmed_public_or_local",
            "tos_status": "reviewed",
            "robots_status": "reviewed_or_not_applicable",
            "usage_scope_status": "within_boundary",
            "next_review_due_at": "2026-08-14T00:00:00+00:00",
            "notes": "Staging security acceptance confirms provenance ledger, field whitelist, and usage boundary for public EOD data.",
            "findings": ["provenance_ref_recorded", "field_whitelist_recorded", "usage_scope_reviewed"],
        },
        role="risk_compliance",
        actor="security_acceptance",
    )
    report = client.request("GET", "/api/governance/sources/report", role="risk_compliance", actor="security_acceptance")
    source_rows = {item["source_id"]: item for item in report.get("sources", [])}
    public_eod = source_rows.get("public_eod_market_data", {})
    passed = (
        bool(updated.get("provenance_ref"))
        and bool(review.get("review_id"))
        and public_eod.get("provenance_ref") == "local://data/local/tdx/market_data.duckdb"
        and "close" in public_eod.get("field_whitelist", [])
        and float(report.get("coverage", 0.0)) >= 0.95
    )
    return {"status": "passed" if passed else "failed", "updated": updated, "review": review, "report": report}


def _storage_policy(client: StagingClient) -> dict[str, Any]:
    policy = client.request(
        "POST",
        "/api/governance/storage-policy-templates",
        {
            "environment": "staging",
            "bucket": "ai-quant-staging",
            "prefix": "objects/staging",
            "opensearch_index": "ai-quant-staging-search-*",
            "postgres_schema": "ai_quant",
            "app_role": "ai_quant_staging_app",
            "migration_role": "ai_quant_staging_migrator",
            "transition_after_days": 30,
            "archive_after_days": 180,
            "delete_after_days": 2555,
        },
        role="risk_compliance",
        actor="security_acceptance",
    )
    checks = policy.get("checks", {})
    s3_actions = {
        action
        for stmt in policy.get("templates", {}).get("s3_iam_policy", {}).get("Statement", [])
        for action in stmt.get("Action", [])
    }
    passed = (
        checks.get("s3_delete_object_not_granted") is True
        and checks.get("s3_full_access_not_granted") is True
        and checks.get("postgres_no_drop_grant_for_app_role") is True
        and "s3:DeleteObject" not in s3_actions
        and "s3:*" not in s3_actions
    )
    return {"status": "passed" if passed else "failed", "policy": policy, "s3_actions": sorted(s3_actions)}


def _cache_retention_external_delete(client: StagingClient, suffix: str, artifact_prefix: str) -> dict[str, Any]:
    run_id = f"crun_security_staging_{suffix}"
    client.request("POST", "/api/demo/full-flow", {}, role="platform", actor="security_acceptance")
    client.request("POST", "/api/ingestion/sources/seed", {}, role="data_engineer", actor="security_acceptance")
    client.request(
        "POST",
        "/api/governance/sources/sec_edgar",
        {
            "retention_policy": "retain_public_filings_short_cache_for_security_acceptance",
            "cache_ttl_days": 1,
            "provenance_ref": "https://www.sec.gov/Archives/security-acceptance",
            "source_tos_uri": "https://www.sec.gov/os/accessing-edgar-data",
            "usage_scope": "public_filings_internal_research",
            "collection_method": "official_public_endpoint",
            "robots_policy": "robots_and_tos_reviewed_2026q2",
            "last_reviewed_at": "2026-05-16T00:00:00+00:00",
        },
        role="risk_compliance",
        actor="security_acceptance",
    )
    client.request(
        "POST",
        "/api/ingestion/documents",
        {
            "document_id": f"doc_security_cache_expired_{suffix}",
            "issuer_id": "issuer_demo",
            "security_id": "security_demo_us",
            "source_id": "sec_edgar",
            "source_type": "regulatory",
            "document_type": "10-K",
            "title": "Security acceptance expired public filing cache",
            "source_uri": f"https://www.sec.gov/Archives/security-acceptance/{suffix}.txt",
            "published_at": "2026-05-01T00:00:00+00:00",
            "ingested_at": "2026-05-01T00:00:00+00:00",
            "body": "Public filing body cached for staging security lifecycle validation.",
            "rights_tag": {
                "license_class": "public",
                "training_allowed": False,
                "redistribution_allowed": False,
                "display_use": "allowed",
                "non_display_use": "restricted",
                "derived_data_use": "restricted",
            },
        },
        role="data_engineer",
        actor="security_acceptance",
    )
    report = client.request(
        "POST",
        "/api/governance/cache-retention-report",
        {
            "as_of": "2026-05-16T00:00:00+00:00",
            "include_retained": False,
            "include_runtime_cache": True,
            "record_run": True,
            "execute": True,
            "run_id": run_id,
            "limit": 100,
        },
        role="risk_compliance",
        actor="security_acceptance",
    )
    executed = client.request(
        "POST",
        f"/api/governance/cache-retention-runs/{run_id}/execute",
        {
            "execute": True,
            "provider": "local_runtime_cache_retention_executor",
            "executed_at": "2026-05-16T00:30:00+00:00",
            "notes": "Runtime cache executor ran; object/search deletes remain external handoff tasks.",
        },
        role="platform",
        actor="security_acceptance",
    )
    evidence = client.request(
        "POST",
        f"/api/governance/cache-retention-runs/{run_id}/execution-evidence",
        {
            "evidence_uri": f"{artifact_prefix.rstrip('/')}/external-delete-evidence-{suffix}.json",
            "provider": "s3_lifecycle_opensearch_qdrant_kms_dlp_executor",
            "deleted_count": report.get("deletion_required_count", 0),
            "executed_at": "2026-05-16T01:00:00+00:00",
            "notes": "External lifecycle/search/KMS-DLP executor evidence recorded in staging acceptance.",
        },
        role="platform",
        actor="security_acceptance",
    )
    listed = client.request("GET", f"/api/governance/cache-retention-runs?status=executed_outside_app&actor=security_acceptance", role="risk_compliance", actor="security_acceptance")
    passed = (
        report.get("status") == "approval_required"
        and bool(report.get("run", {}).get("run_id") == run_id)
        and "governance_evidence" in str(report.get("usage_boundary", ""))
        and executed.get("requires_external_handoff") is True
        and int(executed.get("external_handoff_count", 0)) >= 1
        and evidence.get("status") == "executed_outside_app"
        and evidence.get("execution_provider") == "s3_lifecycle_opensearch_qdrant_kms_dlp_executor"
        and int(evidence.get("external_deleted_count", 0)) >= 1
        and int(listed.get("executed_outside_app", 0)) >= 1
    )
    return {"status": "passed" if passed else "failed", "report": report, "executed": executed, "evidence": evidence, "listed": listed}


def run_staging_security_acceptance(
    *,
    base_url: str = DEFAULT_BASE_URL,
    artifact_prefix: str = "artifact://local-staging",
    secret_manager_provider: str = "local-development-metadata-only",
    timeout: float = 10.0,
) -> dict[str, Any]:
    suffix = str(int(time.time() * 1000))
    client = StagingClient(base_url, timeout=timeout)
    checks: list[dict[str, Any]] = []

    for name, fn in [
        ("secret_rotation_metadata_only", lambda: _record_secret_rotation(client, suffix, artifact_prefix, secret_manager_provider)),
        ("source_provenance_ledger", lambda: _source_provenance_review(client, suffix)),
        ("least_privilege_storage_policy", lambda: _storage_policy(client)),
        ("cache_retention_external_delete_evidence", lambda: _cache_retention_external_delete(client, suffix, artifact_prefix)),
    ]:
        try:
            evidence = fn()
            checks.append(_check(name, evidence.get("status") == "passed", evidence))
        except Exception as exc:  # pragma: no cover - exercised by real staging failures
            checks.append(_check(name, False, {}, str(exc)))

    audit = client.request("GET", "/api/governance/audit-report", role="risk_compliance", actor="security_acceptance")
    data_security = client.request("GET", "/api/governance/data-security-report", role="risk_compliance", actor="security_acceptance")
    checks.append(_check("audit_completeness", float(audit.get("coverage", 0.0)) >= 1.0, audit))
    checks.append(_check("data_security_no_findings", int(data_security.get("total", 0)) == 0, data_security))

    failed = [item for item in checks if not item["passed"]]
    return {
        "status": "passed" if not failed else "failed",
        "mode": "staging_security_acceptance",
        "base_url": base_url,
        "artifact_prefix": artifact_prefix,
        "secret_manager_provider": secret_manager_provider,
        "checks": checks,
        "failed_count": len(failed),
        "production_boundary": "local_staging_security_governance_acceptance_records_metadata_and_external_executor_evidence_no_secret_values",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run staging security/KMS/lifecycle governance acceptance.")
    parser.add_argument("base_url", nargs="?", default=DEFAULT_BASE_URL)
    parser.add_argument("--artifact-prefix", default="artifact://local-staging")
    parser.add_argument("--secret-manager-provider", default="local-development-metadata-only")
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()
    result = run_staging_security_acceptance(
        base_url=args.base_url,
        artifact_prefix=args.artifact_prefix,
        secret_manager_provider=args.secret_manager_provider,
        timeout=args.timeout,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if result["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
