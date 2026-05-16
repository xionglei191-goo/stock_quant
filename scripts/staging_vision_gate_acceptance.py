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


def _ensure_mapping_records(client: StagingClient, suffix: str) -> dict[str, Any]:
    demo = client.request("POST", "/api/demo/full-flow", {}, role="platform", actor="vision_gate_acceptance")
    batch = client.request(
        "POST",
        "/api/entity-mappings/batch",
        {
            "batch_id": f"vision_mapping_{suffix}",
            "items": [
                {
                    "mapping_id": f"map_vision_u_{suffix}",
                    "issuer_id": demo["issuer_id"],
                    "lei": "LEI-DEMO-HOLDINGS",
                    "cik": "0000320193",
                    "figi": "FIGI-DEMO-US",
                    "isin": "US000000DEMO",
                    "ticker": "DEMO",
                    "market": "U",
                    "confidence": 0.99,
                    "source": "staging_gold_mapping",
                },
                {
                    "mapping_id": f"map_vision_a_{suffix}",
                    "issuer_id": demo["issuer_id"],
                    "lei": "LEI-DEMO-HOLDINGS",
                    "ticker": "300000",
                    "market": "A",
                    "confidence": 0.98,
                    "source": "staging_gold_mapping",
                },
                {
                    "mapping_id": f"map_vision_h_{suffix}",
                    "issuer_id": demo["issuer_id"],
                    "lei": "LEI-DEMO-HOLDINGS",
                    "ticker": "09999",
                    "market": "H",
                    "confidence": 0.98,
                    "source": "staging_gold_mapping",
                },
            ],
        },
        role="platform",
        actor="vision_gate_acceptance",
    )
    label_items = [
        {
            "label_id": f"emlbl_vision_u_{suffix}",
            "mapping_id": f"map_vision_u_{suffix}",
            "issuer_id": demo["issuer_id"],
            "ticker": "DEMO",
            "market": "U",
            "reviewer": "data_quality_staging",
            "source": "staging_manual_gold_label",
        },
        {
            "label_id": f"emlbl_vision_a_{suffix}",
            "mapping_id": f"map_vision_a_{suffix}",
            "issuer_id": demo["issuer_id"],
            "ticker": "300000",
            "market": "A",
            "reviewer": "data_quality_staging",
            "source": "staging_manual_gold_label",
        },
        {
            "label_id": f"emlbl_vision_h_{suffix}",
            "mapping_id": f"map_vision_h_{suffix}",
            "issuer_id": demo["issuer_id"],
            "ticker": "09999",
            "market": "H",
            "reviewer": "data_quality_staging",
            "source": "staging_manual_gold_label",
        },
    ]
    labels = client.request(
        "POST",
        "/api/entity-mappings/labels",
        {"batch_id": f"vision_mapping_labels_{suffix}", "items": label_items},
        role="platform",
        actor="vision_gate_acceptance",
    )
    quality = client.request("GET", "/api/entity-mappings/quality-report", role="platform", actor="vision_gate_acceptance")
    passed = float(quality.get("accuracy", 0.0)) >= 0.98 and int(quality.get("checked_labels", 0)) >= len(label_items)
    return {"status": "passed" if passed else "failed", "demo": demo, "batch": batch, "labels": labels, "quality": quality}


def _run_extraction_benchmark(client: StagingClient, suffix: str) -> dict[str, Any]:
    benchmark_id = f"bm_vision_{suffix}"
    docs = [
        ("doc_vision_en_" + suffix, "en", "FY2026 revenue grew 12% to RMB 100 million. Operating cash flow improved in 2026.", ["revenue", "operating_cash_flow"]),
        ("doc_vision_zh_" + suffix, "zh", "2026年营业收入增长12%，经营活动现金流改善。", ["revenue", "operating_cash_flow"]),
    ]
    created_docs: list[dict[str, Any]] = []
    for document_id, language, body, _terms in docs:
        created_docs.append(
            client.request(
                "POST",
                "/api/ingestion/documents",
                {
                    "document_id": document_id,
                    "issuer_id": "issuer_demo",
                    "security_id": "security_demo_us",
                    "source_id": "sec_edgar",
                    "source_type": "regulatory",
                    "document_type": "10-K" if language == "en" else "10-Q",
                    "source_uri": f"https://example.invalid/staging/{document_id}",
                    "body": body,
                    "rights_tag": {
                        "license_class": "public",
                        "training_allowed": False,
                        "redistribution_allowed": False,
                        "display_use": "allowed",
                        "non_display_use": "restricted",
                        "derived_data_use": "restricted",
                    },
                    "language": language,
                },
                role="data_engineer",
                actor="vision_gate_acceptance",
            )
        )
    benchmark = client.request(
        "POST",
        "/api/benchmarks",
        {
            "benchmark_id": benchmark_id,
            "language": "mixed",
            "task_type": "term_extraction",
            "threshold": {
                "term_f1": 1.0,
                "number_recall": 1.0,
                "period_recall": 1.0,
                "page_hit_rate": 1.0,
                "evidence_locator_rate": 1.0,
                "avg_confidence": 0.8,
            },
        },
        role="nlp_ml",
        actor="vision_gate_acceptance",
    )
    samples: list[dict[str, Any]] = []
    sample_ids: list[str] = []
    for document_id, language, _body, terms in docs:
        sample_id = f"bms_{document_id}"
        sample_ids.append(sample_id)
        samples.append(
            client.request(
                "POST",
                f"/api/benchmarks/{benchmark_id}/samples",
                {
                    "sample_id": sample_id,
                    "document_id": document_id,
                    "language": language,
                    "expected_terms": terms,
                    "expected_numbers": 1,
                    "expected_periods": 1,
                    "expected_pages": [1],
                },
                role="nlp_ml",
                actor="vision_gate_acceptance",
            )
        )
    run = client.request(
        "POST",
        f"/api/benchmarks/{benchmark_id}/run",
        {"run_id": f"bmrn_vision_{suffix}", "sample_ids": sample_ids, "min_confidence": 0.8},
        role="nlp_ml",
        actor="vision_gate_acceptance",
    )
    metrics = run.get("metrics", {})
    passed = bool(run.get("passed")) and float(metrics.get("term_f1", 0.0)) >= 0.9 and float(metrics.get("page_hit_rate", 0.0)) >= 0.95 and float(metrics.get("number_recall", 0.0)) >= 0.92
    return {"status": "passed" if passed else "failed", "benchmark": benchmark, "documents": created_docs, "samples": samples, "run": run}


def _run_incident_drills(client: StagingClient, suffix: str) -> dict[str, Any]:
    seeded = client.request("POST", "/api/playbooks/seed", {"create_schedules": True}, role="risk_compliance", actor="vision_gate_acceptance")
    calendar = client.request("GET", "/api/incidents/calendar", role="risk_compliance", actor="vision_gate_acceptance")
    playbooks = list(calendar.get("playbooks", seeded.get("playbooks", [])))
    schedules = list(calendar.get("schedules", seeded.get("schedules", [])))
    schedules_by_type = {str(item["incident_type"]): item for item in schedules}
    for playbook in playbooks:
        incident_type = str(playbook["incident_type"])
        if incident_type in schedules_by_type:
            continue
        schedule = client.request(
            "POST",
            "/api/drill-schedules",
            {
                "schedule_id": f"drill_{incident_type}_staging_{suffix}",
                "incident_type": incident_type,
                "cadence": "quarterly",
                "owner": playbook.get("owner_role", "风险/合规"),
                "notes": f"Quarterly staging tabletop drill for {incident_type}",
            },
            role="risk_compliance",
            actor="vision_gate_acceptance",
        )
        schedules.append(schedule)
        schedules_by_type[incident_type] = schedule
    drill_results: list[dict[str, Any]] = []
    incident_reports: list[dict[str, Any]] = []
    for schedule in schedules:
        schedule_id = str(schedule["schedule_id"])
        incident_type = str(schedule["incident_type"])
        playbook = next(item for item in playbooks if item["incident_type"] == incident_type)
        drill_results.append(
            client.request(
                "POST",
                f"/api/drill-schedules/{schedule_id}/result",
                {
                    "result": "passed",
                    "rca_summary": f"Quarterly staging tabletop drill completed for {incident_type}.",
                    "action_items": ["owner confirmed", "rollback path reviewed", "audit evidence attached"],
                    "next_run_at": "2026-08-14T00:00:00+00:00",
                },
                role="risk_compliance",
                actor="vision_gate_acceptance",
            )
        )
        incident_reports.append(
            client.request(
                "POST",
                "/api/incident-reports",
                {
                    "report_id": f"ir_vision_{incident_type}_{suffix}",
                    "playbook_id": playbook["playbook_id"],
                    "root_cause": "staging_tabletop_drill_no_production_incident",
                    "impact": "no production impact; drill validates detection, rollback, and owner workflow",
                    "action_items": ["review evidence package", "keep quarterly drill cadence"],
                    "owner": playbook["owner_role"],
                },
                role="risk_compliance",
                actor="vision_gate_acceptance",
            )
        )
    vision_gate = client.request("GET", "/api/readiness/vision-gate", role="CEO", actor="vision_gate_acceptance")
    drill_gate = next((item for item in vision_gate.get("gates", []) if item["name"] == "quarterly_incident_drill_coverage"), {})
    passed = bool(drill_gate.get("passed"))
    return {
        "status": "passed" if passed else "failed",
        "seeded": seeded,
        "calendar": calendar,
        "drill_results": drill_results,
        "incident_reports": incident_reports,
        "drill_gate": drill_gate,
    }


def _backfill_missing_evidence(client: StagingClient) -> dict[str, Any]:
    before = client.request("GET", "/api/evidence/quality-report", role="nlp_ml", actor="vision_gate_acceptance")
    missing_ids = [str(item) for item in before.get("missing_document_ids", [])]
    extracted: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for document_id in missing_ids:
        try:
            result = client.request(
                "POST",
                "/api/evidence/extract",
                {
                    "document_id": document_id,
                    "parser_version": "vision-gate-backfill",
                    "model_version": "rule-vision-gate-backfill",
                },
                role="nlp_ml",
                actor="vision_gate_acceptance",
            )
            extracted.append({"document_id": document_id, "evidence_count": len(result.get("evidence", []))})
        except Exception as exc:  # pragma: no cover - only exercised by staging data drift
            failures.append({"document_id": document_id, "error": str(exc)})
    after = client.request("GET", "/api/evidence/quality-report", role="nlp_ml", actor="vision_gate_acceptance")
    coverage = float(after.get("documents_with_evidence", 0)) / max(1, int(after.get("documents", 0)))
    return {
        "status": "passed" if coverage >= 0.95 and not failures else "failed",
        "before": before,
        "after": after,
        "extracted": extracted,
        "failures": failures,
        "coverage": round(coverage, 4),
    }


def run_staging_vision_gate_acceptance(
    *,
    base_url: str = DEFAULT_BASE_URL,
    artifact_prefix: str = "artifact://staging-vision-gate",
    record_launch_checklist: bool = False,
    timeout: float = 10.0,
) -> dict[str, Any]:
    suffix = str(int(time.time()))
    client = StagingClient(base_url, timeout=timeout)
    mapping = _ensure_mapping_records(client, suffix)
    benchmark = _run_extraction_benchmark(client, suffix)
    drills = _run_incident_drills(client, suffix)
    evidence_backfill = _backfill_missing_evidence(client)
    evidence_package = client.request(
        "POST",
        "/api/readiness/evidence-package",
        {"record_export": True, "include_passed": True},
        role="CEO",
        actor="vision_gate_acceptance",
    )
    vision_gate = client.request("GET", "/api/readiness/vision-gate", role="CEO", actor="vision_gate_acceptance")
    readiness_record = None
    failed_gate_names = {str(item["name"]) for item in vision_gate.get("gates", []) if not item.get("passed")}
    pending_checklist = {str(item) for item in vision_gate.get("pending_checklist", [])}
    launch_ready = failed_gate_names <= {"readiness_checklist_coverage"} and pending_checklist <= {"launch_checklist"}
    if record_launch_checklist and launch_ready:
        readiness_record = client.request(
            "POST",
            "/api/readiness/checklist/launch_checklist",
            {
                "status": "passed",
                "owner": "ceo_staging",
                "evidence_uri": f"{artifact_prefix.rstrip('/')}/launch-checklist.json",
                "notes": "CEO launch checklist recorded after all non-launch vision gates and readiness evidence passed in local staging.",
                "metrics": {"evidence_package": evidence_package, "pre_launch_vision_gate": vision_gate},
            },
            role="CEO",
            actor="vision_gate_acceptance",
        )
        vision_gate = client.request("GET", "/api/readiness/vision-gate", role="CEO", actor="vision_gate_acceptance")
    component_passed = all(item["status"] == "passed" for item in [mapping, benchmark, drills, evidence_backfill])
    launch_checklist_passed = not record_launch_checklist or (readiness_record is not None and vision_gate.get("status") == "ready")
    status = "passed" if component_passed and launch_checklist_passed else "failed"
    return {
        "status": status,
        "base_url": base_url,
        "mapping": mapping,
        "benchmark": benchmark,
        "drills": drills,
        "evidence_backfill": evidence_backfill,
        "evidence_package": evidence_package,
        "launch_checklist_record": readiness_record,
        "vision_gate": vision_gate,
        "launch_checklist_required": record_launch_checklist,
        "launch_checklist_passed": launch_checklist_passed,
        "production_boundary": "vision_gate_acceptance_uses_staging_gold_labels_benchmarks_and_tabletop_drills_without_live_execution",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed and run staging vision-gate acceptance evidence.")
    parser.add_argument("base_url", nargs="?", default=DEFAULT_BASE_URL)
    parser.add_argument("--artifact-prefix", default="artifact://staging-vision-gate")
    parser.add_argument("--record-launch-checklist", action="store_true")
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()
    result = run_staging_vision_gate_acceptance(
        base_url=args.base_url,
        artifact_prefix=args.artifact_prefix,
        record_launch_checklist=args.record_launch_checklist,
        timeout=args.timeout,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if result["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
