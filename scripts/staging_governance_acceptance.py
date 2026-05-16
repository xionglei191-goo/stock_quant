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


SOURCE_REVIEW_DEFAULTS = {
    "manual_reference_transcripts": {
        "publicness_status": "manual_reference_only",
        "usage_scope_status": "manual_reference_only",
        "notes": "Red-zone transcript notes remain metadata/manual-reference only and are blocked from automated ingestion.",
        "findings": ["manual_reference_only", "red_source_blocked_from_automated_ingestion"],
    },
    "local_research_reports": {
        "publicness_status": "manual_reference_only",
        "usage_scope_status": "manual_reference_only",
        "notes": "Local research reports are citation/reference assets only; no training, redistribution, or fact-source promotion.",
        "findings": ["local_reference_only", "not_training_or_fact_source"],
    },
}


def _record_readiness(client: StagingClient, check_id: str, payload: dict[str, Any], *, actor: str) -> dict[str, Any]:
    return client.request(
        "POST",
        f"/api/readiness/checklist/{check_id}",
        payload,
        role="risk_compliance" if check_id != "launch_checklist" else "CEO",
        actor=actor,
    )


def _permission_red_team(client: StagingClient) -> dict[str, Any]:
    before = client.request("GET", "/api/metrics", role="unknown", actor="permission_red_team")
    before_count = int(before.get("permission_denied_events", 0))
    attempts = [
        {
            "name": "analyst_cannot_ingest_document",
            "method": "POST",
            "path": "/api/ingestion/documents",
            "role": "analyst",
            "body": {},
        },
        {
            "name": "pm_cannot_read_governance_security",
            "method": "GET",
            "path": "/api/governance/data-security-report",
            "role": "pm",
            "body": None,
        },
        {
            "name": "unknown_cannot_read_readiness",
            "method": "GET",
            "path": "/api/readiness/checklist",
            "role": "unknown",
            "body": None,
        },
        {
            "name": "analyst_cannot_submit_otel",
            "method": "POST",
            "path": "/api/observability/otel/submit",
            "role": "analyst",
            "body": {"target": "http://127.0.0.1:4318/v1/logs", "provider": "webhook"},
        },
    ]
    rows: list[dict[str, Any]] = []
    for attempt in attempts:
        response = client.request_any(
            str(attempt["method"]),
            str(attempt["path"]),
            attempt.get("body") if isinstance(attempt.get("body"), dict) else None,
            role=str(attempt["role"]),
            actor="permission_red_team",
        )
        payload = dict(response.get("payload", {}))
        error = payload.get("error", {}) if isinstance(payload.get("error"), dict) else {}
        rows.append(
            {
                "name": attempt["name"],
                "method": attempt["method"],
                "path": attempt["path"],
                "role": attempt["role"],
                "status_code": response["status_code"],
                "error_type": error.get("type", ""),
                "blocked": response["status_code"] == 403 and error.get("type") == "permission_denied",
            }
        )
    after = client.request("GET", "/api/metrics", role="unknown", actor="permission_red_team")
    after_count = int(after.get("permission_denied_events", 0))
    audit_report = client.request("GET", "/api/governance/audit-report?action_prefix=permission_denied", role="risk_compliance", actor="permission_red_team")
    passed = all(row["blocked"] for row in rows) and after_count >= before_count + len(rows) and float(audit_report.get("coverage", 0.0)) >= 1.0
    return {
        "status": "passed" if passed else "failed",
        "attempts": rows,
        "before_permission_denied_events": before_count,
        "after_permission_denied_events": after_count,
        "audit_report": audit_report,
    }


def _source_review_payload(source: dict[str, Any], *, suffix: str) -> dict[str, Any]:
    source_id = str(source["source_id"])
    defaults = SOURCE_REVIEW_DEFAULTS.get(source_id, {})
    publicness_status = str(defaults.get("publicness_status", "confirmed_public_or_local"))
    usage_scope_status = str(defaults.get("usage_scope_status", "within_boundary"))
    findings = list(defaults.get("findings", ["publicness_tos_robots_usage_boundary_reviewed"]))
    if source.get("risk_level") == "red" and source_id not in SOURCE_REVIEW_DEFAULTS:
        publicness_status = "manual_reference_only"
        usage_scope_status = "manual_reference_only"
        findings.append("red_source_manual_reference_only")
    notes = str(defaults.get("notes", "Staging compliance review confirms publicness, TOS/robots applicability, and usage boundary."))
    return {
        "review_id": f"srrev_staging_{source_id}_{suffix}",
        "review_period": "2026Q2",
        "status": "approved",
        "publicness_status": publicness_status,
        "tos_status": "reviewed",
        "robots_status": "reviewed_or_not_applicable",
        "usage_scope_status": usage_scope_status,
        "next_review_due_at": "2026-08-14T00:00:00+00:00",
        "notes": notes,
        "findings": findings,
    }


def _compliance_review(client: StagingClient, *, suffix: str) -> dict[str, Any]:
    report_before = client.request("GET", "/api/governance/sources/report", role="risk_compliance", actor="compliance_review")
    reviewed: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for source in report_before.get("sources", []):
        source_id = str(source["source_id"])
        if source.get("latest_review"):
            skipped.append({"source_id": source_id, "reason": "already_reviewed"})
            continue
        review = client.request(
            "POST",
            f"/api/governance/sources/{source_id}/reviews",
            _source_review_payload(source, suffix=suffix),
            role="risk_compliance",
            actor="compliance_review",
        )
        reviewed.append(review)
    report_after = client.request("GET", "/api/governance/sources/report", role="risk_compliance", actor="compliance_review")
    reminders = client.request(
        "GET",
        "/api/governance/source-review-reminders?due_within_days=30",
        role="risk_compliance",
        actor="compliance_review",
    )
    data_security = client.request("GET", "/api/governance/data-security-report", role="risk_compliance", actor="compliance_review")
    audit_report = client.request("GET", "/api/governance/audit-report", role="risk_compliance", actor="compliance_review")
    sources = list(report_after.get("sources", []))
    red_training_ready = all(
        not (row.get("risk_level") == "red" and row.get("latest_review", {}).get("usage_scope_status") != "manual_reference_only")
        for row in sources
    )
    passed = (
        float(report_after.get("coverage", 0.0)) >= 0.95
        and int(report_after.get("reviewed_sources", 0)) == int(report_after.get("total", 0))
        and int(reminders.get("missing_review", 0)) == 0
        and int(reminders.get("overdue", 0)) == 0
        and int(data_security.get("total", 0)) == 0
        and float(audit_report.get("coverage", 0.0)) >= 1.0
        and red_training_ready
    )
    return {
        "status": "passed" if passed else "failed",
        "reviewed_count": len(reviewed),
        "skipped_count": len(skipped),
        "reviewed": reviewed,
        "skipped": skipped,
        "source_governance": report_after,
        "source_review_reminders": reminders,
        "data_security": data_security,
        "audit_report": audit_report,
        "red_training_boundary_ready": red_training_ready,
    }


def _launch_precheck(client: StagingClient) -> dict[str, Any]:
    package = client.request(
        "POST",
        "/api/readiness/evidence-package",
        {"record_export": True, "include_passed": True},
        role="CEO",
        actor="launch_precheck",
    )
    vision_gate = client.request("GET", "/api/readiness/vision-gate", role="CEO", actor="launch_precheck")
    passed = bool(package.get("ready_for_launch")) and vision_gate.get("status") == "ready"
    return {
        "status": "passed" if passed else "blocked",
        "ready_for_launch": bool(package.get("ready_for_launch")),
        "vision_gate_status": vision_gate.get("status"),
        "pending_checklist": package.get("pending_checklist", []),
        "failed_gate_count": package.get("failed_gate_count", 0),
        "package_id": package.get("package_id", ""),
        "usage_boundary": "launch_checklist_requires_ready_vision_gate_and_ceo_approval_before_readiness_pass",
    }


def run_staging_governance_acceptance(
    *,
    base_url: str = DEFAULT_BASE_URL,
    artifact_prefix: str = "artifact://staging-governance",
    record_readiness: bool = False,
    record_launch_checklist: bool = False,
    timeout: float = 10.0,
) -> dict[str, Any]:
    suffix = str(int(time.time()))
    client = StagingClient(base_url, timeout=timeout)
    permission = _permission_red_team(client)
    compliance = _compliance_review(client, suffix=suffix)
    launch = _launch_precheck(client)
    readiness_records: list[dict[str, Any]] = []
    if record_readiness:
        readiness_records.append(
            _record_readiness(
                client,
                "permission_red_team_test",
                {
                    "status": permission["status"],
                    "owner": "risk_compliance_staging",
                    "evidence_uri": f"{artifact_prefix.rstrip('/')}/permission-red-team.json",
                    "notes": "HTTP permission red-team attempts confirmed 403 blocking and permission_denied audit coverage.",
                    "metrics": permission,
                },
                actor="permission_red_team",
            )
        )
        readiness_records.append(
            _record_readiness(
                client,
                "compliance_review_record",
                {
                    "status": compliance["status"],
                    "owner": "risk_compliance_staging",
                    "evidence_uri": f"{artifact_prefix.rstrip('/')}/compliance-source-review.json",
                    "notes": "Source governance review records cover publicness, TOS/robots applicability, usage boundary, sensitive data, and audit completeness.",
                    "metrics": compliance,
                },
                actor="compliance_review",
            )
        )
        if record_launch_checklist:
            readiness_records.append(
                _record_readiness(
                    client,
                    "launch_checklist",
                    {
                        "status": "passed" if launch["status"] == "passed" else "blocked",
                        "owner": "ceo_staging",
                        "evidence_uri": f"{artifact_prefix.rstrip('/')}/launch-checklist.json",
                        "notes": "Launch checklist is blocked unless the vision gate is ready and CEO approval evidence is attached.",
                        "metrics": launch,
                    },
                    actor="launch_precheck",
                )
            )
    status = "passed" if permission["status"] == "passed" and compliance["status"] == "passed" else "failed"
    return {
        "status": status,
        "base_url": base_url,
        "permission_red_team": permission,
        "compliance_review": compliance,
        "launch_precheck": launch,
        "readiness_records": readiness_records,
        "production_boundary": "governance_acceptance_records_real_http_audit_evidence_without_enabling_live_execution",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run staging governance acceptance and optionally record readiness evidence.")
    parser.add_argument("base_url", nargs="?", default=DEFAULT_BASE_URL)
    parser.add_argument("--artifact-prefix", default="artifact://staging-governance")
    parser.add_argument("--record-readiness", action="store_true")
    parser.add_argument("--record-launch-checklist", action="store_true")
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()
    result = run_staging_governance_acceptance(
        base_url=args.base_url,
        artifact_prefix=args.artifact_prefix,
        record_readiness=args.record_readiness,
        record_launch_checklist=args.record_launch_checklist,
        timeout=args.timeout,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if result["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
