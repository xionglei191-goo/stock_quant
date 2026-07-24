from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import promote_research_report_bulk_clone_to_primary as bulk_promotion
from scripts import promote_research_report_clone_batch_to_primary as promotion
from scripts.build_research_report_registry_decision import payload_sha256


BOUNDARY = "local_research_reports_are_opinion_reference_only_not_fact_or_training_source"


def _rights() -> dict[str, object]:
    return {"license_class": "local_research_reference", "training_allowed": False, "redistribution_allowed": False, "display_use": "restricted", "non_display_use": "restricted", "derived_data_use": "restricted"}


def _plan() -> dict[str, object]:
    entries = []
    for suffix in ("one", "two"):
        report_id = f"rr_{suffix}"
        entries.append({"report_id": report_id, "document_id": f"doc_{report_id}", "content_sha256": hashlib.sha256(suffix.encode()).hexdigest(), "relative_path_sha256": hashlib.sha256((suffix + ".pdf").encode()).hexdigest(), "size_bytes": 1, "file_type": "pdf", "source_key": "source_test", "rights_policy_id": "local-research-reference-restricted-v1"})
    return {"schema_version": "research-report-clone-batch-plan-v1", "related_task": "T-617", "manifest_sha256": "a" * 64, "batch_id": "t613-batch-0006", "batch_sha256": "b" * 64, "raw_content_identity_sha256": "c" * 64, "backup_dump_sha256": "d" * 64, "batch_entries": entries, "write_contract": {"target": "independently_attested_clone_only", "primary_writes_allowed": False, "insert_only": True, "updates_allowed": False, "deletes_allowed": False, "raw_files_preserved": True, "opensearch_preserved": True, "local_opinion_reference_only": True, "training_allowed": False, "broker_connected": False, "live_execution_allowed": False}}


def _run(plan: dict[str, object], *, created: bool, prior_sha: str | None = None) -> dict[str, object]:
    rows = []
    for entry in plan["batch_entries"]:
        manual = entry["report_id"] == "rr_two"
        rows.append({"report_id": entry["report_id"], "document_id": entry["document_id"], "content_sha256": entry["content_sha256"], "ingest_created": created, "status": "needs_text_review" if manual else "text_indexed", "evidence_count": 0 if manual else 1, "manual_review": manual, "text_source": "no_extractable_text" if manual else "pdftotext", "content_identity_verified": True})
    payload: dict[str, object] = {"schema_version": "research-report-clone-batch-execution-v1", "generated_at": "2026-07-22T00:00:00+00:00", "plan_sha256": payload_sha256(plan), "manifest_sha256": plan["manifest_sha256"], "batch_id": plan["batch_id"], "batch_sha256": plan["batch_sha256"], "status": "passed", "selected_report_count": 2, "processed_count": 2, "failed_count": 0, "content_identity_verified_count": 2, "evidence_count": 1, "results": rows, "errors": [], "delete_operations": [], "raw_files_preserved": True, "opensearch_index_preserved": True, "primary_writes_allowed": False, "fact_opinion_boundary": BOUNDARY}
    if prior_sha is not None:
        payload["idempotency_comparison"] = {"passed": True, "prior_run_sha256": prior_sha}
    payload["artifact_sha256"] = payload_sha256(payload)
    return payload


def _rows(plan: dict[str, object]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = [{"collection": "sources", "item_id": "local_research_test", "payload": {"source_id": "local_research_test", "source_type": "local_reference", "rights_tag": _rights()}, "position": None}]
    for entry in plan["batch_entries"]:
        report_id, document_id = entry["report_id"], entry["document_id"]
        manual = report_id == "rr_two"
        common = {"source_id": "local_research_test", "content_sha256": entry["content_sha256"], "rights_tag": _rights()}
        rows.extend([{"collection": "research_reports", "item_id": report_id, "payload": {**common, "report_id": report_id, "document_id": document_id, "status": "needs_text_review" if manual else "text_indexed"}, "position": None}, {"collection": "documents", "item_id": document_id, "payload": {**common, "document_id": document_id, "document_type": "research", "source_type": "local_reference", "source_uri": f"research-report://{report_id}", "body": "" if manual else "bounded citation"}, "position": None}])
        if not manual:
            rows.append({"collection": "evidence", "item_id": f"evi_{document_id}_research_0", "payload": {"evidence_id": f"evi_{document_id}_research_0", "document_id": document_id, "section": "research_report_citation", "bbox": f"research_report://{document_id};chunk=0", "span_text": "bounded citation", "canonical_text": "bounded citation"}, "position": None})
    return sorted(rows, key=lambda row: (str(row["collection"]), str(row["item_id"])))


def _bulk_run() -> dict[str, object]:
    results = [
        {"report_id": "rr_bulk_one", "document_id": "doc_rr_bulk_one", "content_sha256": "1" * 64, "content_identity_verified": True, "status": "text_indexed", "evidence_count": 1},
        {"report_id": "rr_bulk_two", "document_id": "doc_rr_bulk_two", "content_sha256": "2" * 64, "content_identity_verified": True, "status": "needs_text_review", "evidence_count": 0},
    ]
    return {
        "schema_version": "research-report-bulk-clone-execution-v1",
        "status": "passed",
        "manifest_sha256": bulk_promotion.EXPECTED_MANIFEST,
        "completed_batches": 1,
        "processed_count": len(results),
        "failed_count": 0,
        "primary_writes_allowed": False,
        "delete_operations": [],
        "update_operations": [],
        "raw_files_preserved": True,
        "opensearch_preserved": True,
        "fact_opinion_boundary": BOUNDARY,
        "batches": [{"status": "passed", "processed_count": len(results), "failed_count": 0, "results": results}],
    }


class BatchPrimaryPromotionTests(unittest.TestCase):
    def test_bulk_run_accepts_zero_failures_and_rejects_any_failure(self) -> None:
        with patch.object(bulk_promotion, "EXPECTED_BATCHES", 1), patch.object(bulk_promotion, "EXPECTED_REPORTS", 2):
            run = _bulk_run()
            selected = bulk_promotion._validate_run(run)
            self.assertEqual(sorted(selected), ["rr_bulk_one", "rr_bulk_two"])
            run["failed_count"] = 1
            with self.assertRaisesRegex(bulk_promotion.BulkPromotionRefused, "one-time promotion contract"):
                bulk_promotion._validate_run(run)

    def test_batch_plan_runs_and_manual_review_slice_are_strictly_bound(self) -> None:
        plan = _plan()
        selected = promotion._batch_entries(plan)
        run1 = _run(plan, created=True)
        run1_sha = str(run1["artifact_sha256"])
        run2 = _run(plan, created=False, prior_sha=run1_sha)
        first = promotion._validate_run(run1, label="run1", plan_sha256=payload_sha256(plan), plan=plan, selected=selected, created=True)
        second = promotion._validate_run(run2, label="run2", plan_sha256=payload_sha256(plan), plan=plan, selected=selected, created=False, prior_sha=run1_sha)
        result = promotion._validate_slice(_rows(plan), selected=selected, run2=second)
        self.assertEqual(result["counts"], {"sources": 1, "research_reports": 2, "documents": 2, "evidence": 1})
        self.assertEqual(first["rr_two"]["status"], "needs_text_review")

    def test_campaign_authorization_cannot_widen_or_allow_deletes(self) -> None:
        plan = _plan()
        approval = {"schema_version": "research-report-primary-campaign-approval-v1", "status": "approved", "manifest_sha256": plan["manifest_sha256"], "authorized_batch_ids": [plan["batch_id"]], "primary_writes_allowed": True, "insert_only": True, "updates_allowed": False, "deletes_allowed": False, "raw_files_preserved": True, "duplicate_aliases_preserved": True, "opensearch_preserved": True, "local_opinion_reference_only": True, "training_allowed": False, "broker_connected": False, "live_execution_allowed": False}
        promotion._validate_campaign_approval(approval, plan=plan)
        approval["deletes_allowed"] = True
        with self.assertRaisesRegex(promotion.BatchPromotionRefused, "does not authorize"):
            promotion._validate_campaign_approval(approval, plan=plan)

    def test_run_rejects_manual_review_with_citation_evidence(self) -> None:
        plan = _plan(); selected = promotion._batch_entries(plan); run = _run(plan, created=True)
        run["results"][1]["evidence_count"] = 1; run["evidence_count"] = 2
        run["artifact_sha256"] = payload_sha256({key: value for key, value in run.items() if key != "artifact_sha256"})
        with self.assertRaisesRegex(promotion.BatchPromotionRefused, "strict report gate"):
            promotion._validate_run(run, label="run1", plan_sha256=payload_sha256(plan), plan=plan, selected=selected, created=True)

    def test_independent_clone_requires_attested_live_identity(self) -> None:
        plan = _plan()
        attestation_plan = {"plan_sha256": "clone-plan", "input_evidence": {"backup_dump_sha256": plan["backup_dump_sha256"]}}
        proof = {"schema_version": "research-report-clone-runtime-proof-v1", "database_probe": {"success": True}}
        attestation = {
            "schema_version": "research-report-clone-attestation-v1", "status": "passed",
            "database_name": "ai_quant_clone_0006", "runtime_database_name": "ai_quant_clone_0006",
            "execution_scope": "inside_clone_app_container", "network_isolation": True,
            "raw_mount_read_only": True, "primary_service_reachable": False, "restore_verified": True,
            "object_store_backend": "local", "search_backend": "local", "runtime_proof": proof,
            "runtime_proof_sha256": payload_sha256(proof), "plan_sha256": "clone-plan",
            "source_backup_dump_sha256": plan["backup_dump_sha256"],
            "runtime_identity": {"database_oid": "101", "postgres_system_identifier": "202"},
        }
        source = {"identity": {"database_name": "ai_quant_clone_0006", "database_oid": "101", "postgres_system_identifier": "202"}}
        target = {"identity": {"database_name": "ai_quant", "database_oid": "1", "postgres_system_identifier": "303"}}
        result = promotion._validate_independent_clone_attestation(attestation, attestation_plan=attestation_plan, plan=plan, source_snapshot=source, target_snapshot=target)
        self.assertEqual(result["runtime_postgres_system_identifier"], "202")
        target["identity"]["postgres_system_identifier"] = "202"
        with self.assertRaisesRegex(promotion.BatchPromotionRefused, "distinct_postgres"):
            promotion._validate_independent_clone_attestation(attestation, attestation_plan=attestation_plan, plan=plan, source_snapshot=source, target_snapshot=target)


if __name__ == "__main__":
    unittest.main()
