#!/usr/bin/env python3
"""Promote the passed T-619 bulk clone into primary in one insert-only transaction."""

from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import promote_research_report_clone_to_primary as base
from scripts.recover_watchlist_research_reports import BOUNDARY


TASK_ID = "T-619"
EXPECTED_REPORTS = 7303
EXPECTED_BATCHES = 30
EXPECTED_MANIFEST = "e932f352047eb58b4e0df797215598b7ee0bdd25b920432bf6c89173a301fa5e"


class BulkPromotionRefused(RuntimeError):
    """Raised when the one-time primary promotion contract is not satisfied."""


def _connect(dsn: str) -> Any:
    try:
        import psycopg
    except ModuleNotFoundError as exc:
        raise BulkPromotionRefused("psycopg is required for bulk primary promotion") from exc
    return psycopg.connect(dsn)


def _load(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BulkPromotionRefused(f"{label} is unreadable") from exc
    if not isinstance(payload, dict):
        raise BulkPromotionRefused(f"{label} must be an object")
    return payload


def _dsn(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise BulkPromotionRefused(f"{name} is required")
    return value


def _snapshot(dsn: str) -> dict[str, Any]:
    with closing(_connect(dsn)) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            return base._query_snapshot(cursor)


def _validate_run(run: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    if (
        run.get("schema_version") != "research-report-bulk-clone-execution-v1"
        or run.get("status") != "passed"
        or run.get("manifest_sha256") != EXPECTED_MANIFEST
        or int(run.get("completed_batches") or 0) != EXPECTED_BATCHES
        or int(run.get("processed_count") or 0) != EXPECTED_REPORTS
        or int(run.get("failed_count", -1)) != 0
        or run.get("primary_writes_allowed") is not False
        or list(run.get("delete_operations") or [])
        or list(run.get("update_operations") or [])
        or run.get("raw_files_preserved") is not True
        or run.get("opensearch_preserved") is not True
        or run.get("fact_opinion_boundary") != BOUNDARY
    ):
        raise BulkPromotionRefused("bulk clone result does not satisfy the one-time promotion contract")
    batches = run.get("batches") if isinstance(run.get("batches"), list) else []
    if len(batches) != EXPECTED_BATCHES:
        raise BulkPromotionRefused("bulk result has an incomplete batch set")
    selected: dict[str, dict[str, Any]] = {}
    for batch in batches:
        if not isinstance(batch, Mapping) or batch.get("status") != "passed" or int(batch.get("failed_count", -1)) != 0:
            raise BulkPromotionRefused("bulk result contains a failed source batch")
        results = batch.get("results") if isinstance(batch.get("results"), list) else []
        if len(results) != int(batch.get("processed_count") or -1):
            raise BulkPromotionRefused("bulk batch result count is inconsistent")
        for result in results:
            if not isinstance(result, Mapping):
                raise BulkPromotionRefused("bulk result row is invalid")
            report_id = str(result.get("report_id") or "")
            document_id = str(result.get("document_id") or "")
            content_sha = str(result.get("content_sha256") or "")
            status = str(result.get("status") or "")
            evidence_count = int(result.get("evidence_count") or 0)
            if (
                not report_id
                or document_id != f"doc_{report_id}"
                or len(content_sha) != 64
                or result.get("content_identity_verified") is not True
                or status not in {"text_indexed", "needs_text_review"}
                or (status == "needs_text_review" and evidence_count != 0)
                or report_id in selected
            ):
                raise BulkPromotionRefused("bulk result identity or review boundary is invalid")
            selected[report_id] = dict(result)
    if len(selected) != EXPECTED_REPORTS:
        raise BulkPromotionRefused("bulk result does not contain exactly 7303 unique reports")
    return selected


def _source_rows(source_dsn: str, selected: Mapping[str, Mapping[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    report_ids = sorted(selected)
    document_ids = sorted(str(item["document_id"]) for item in selected.values())
    with closing(_connect(source_dsn)) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            snapshot = base._query_snapshot(cursor)
            reports = base._fetch_records(cursor, "research_reports", report_ids)
            documents = base._fetch_records(cursor, "documents", document_ids)
            source_ids = {str(row["payload"].get("source_id") or "") for row in reports} - {""}
            sources = base._fetch_records(cursor, "sources", source_ids)
            evidence = base._fetch_citation_evidence(cursor, document_ids)
    if len(reports) != EXPECTED_REPORTS or len(documents) != EXPECTED_REPORTS:
        raise BulkPromotionRefused("clone source is missing selected reports or documents")
    report_by_id = {row["item_id"]: row["payload"] for row in reports}
    document_by_id = {row["item_id"]: row["payload"] for row in documents}
    evidence_by_doc: dict[str, int] = {document_id: 0 for document_id in document_ids}
    for row in evidence:
        payload = row["payload"]
        if payload.get("section") != "research_report_citation":
            raise BulkPromotionRefused("clone source evidence escaped the citation boundary")
        document_id = str(payload.get("document_id") or "")
        if document_id not in evidence_by_doc:
            raise BulkPromotionRefused("clone source has evidence outside the selected documents")
        evidence_by_doc[document_id] += 1
    for report_id, result in selected.items():
        report = report_by_id.get(report_id, {})
        document = document_by_id.get(str(result["document_id"]), {})
        if (
            report.get("report_id") != report_id
            or report.get("document_id") != result["document_id"]
            or report.get("content_sha256") != result["content_sha256"]
            or document.get("document_id") != result["document_id"]
            or document.get("content_sha256") != result["content_sha256"]
            or int(result["evidence_count"]) != evidence_by_doc[str(result["document_id"])]
        ):
            raise BulkPromotionRefused("clone source no longer matches the passed bulk result")
    rows = sorted([*sources, *reports, *documents, *evidence], key=lambda row: (row["collection"], row["item_id"]))
    return snapshot, rows


def _target_rows(target_dsn: str, source_rows: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    keys = base._record_keys(source_rows)
    with closing(_connect(target_dsn)) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            snapshot = base._query_snapshot(cursor)
            rows: list[dict[str, Any]] = []
            for collection in base.ALLOWED_COLLECTIONS:
                rows.extend(base._fetch_records(cursor, collection, keys.get(collection, [])))
    return snapshot, sorted(rows, key=lambda row: (row["collection"], row["item_id"]))


def _event(slice_sha: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    event_id = f"evt_t619_bulk_{base._payload_sha256({'slice': slice_sha, 'run': EXPECTED_MANIFEST})[:32]}"
    return {
        "event_id": event_id,
        "actor": "t619_bulk_primary_promotion",
        "action": "promote_research_report_bulk_clone",
        "resource_type": "research_report_recovery_bulk",
        "resource_id": f"t613-batch-0015-0044:{slice_sha[:24]}",
        "source": "postgres_bulk_clone_insert_only",
        "version": "t619-bulk-v1",
        "model_version": "",
        "prompt_version": "",
        "approval_state": "user_authorized_one_time_insert_only",
        "trace_id": f"t619-bulk:{slice_sha[:24]}",
        "timestamp": now,
    }


def _confirmation(context: Mapping[str, Any]) -> str:
    payload = {
        "task_id": TASK_ID,
        "source_identity": context["source_snapshot"]["identity"],
        "target_identity": context["target_snapshot"]["identity"],
        "run_sha256": context["run_sha256"],
        "slice_sha256": context["slice_sha256"],
        "insert_counts": context["diff"]["insert_counts"],
        "equal_counts": context["diff"]["equal_counts"],
        "target_table_counts": context["target_snapshot"]["table_counts"],
        "target_research_counts": context["target_snapshot"]["research_counts"],
    }
    return f"T619_BULK_PROMOTE:{base._payload_sha256(payload)}"


def _prepare(source_dsn: str, target_dsn: str, run_path: Path) -> dict[str, Any]:
    run = _load(run_path, "bulk clone result")
    selected = _validate_run(run)
    source_snapshot, source_rows = _source_rows(source_dsn, selected)
    target_snapshot, target_rows = _target_rows(target_dsn, source_rows)
    if source_snapshot["identity"]["database_name"] == target_snapshot["identity"]["database_name"]:
        raise BulkPromotionRefused("clone and primary database names must differ")
    if target_snapshot["identity"]["database_name"] != "ai_quant":
        raise BulkPromotionRefused("target is not the primary database")
    if int(target_snapshot["other_database_sessions"]) != 0:
        raise BulkPromotionRefused("primary writers are not quiescent")
    diff = base._target_diff(source_rows, target_rows)
    expected = {"sources": 0, "research_reports": EXPECTED_REPORTS, "documents": EXPECTED_REPORTS, "evidence": int(run["evidence_count"])}
    if diff["insert_counts"] != expected:
        raise BulkPromotionRefused("primary insert set does not match the passed bulk result")
    context = {
        "run_sha256": str(run.get("result_sha256") or ""),
        "source_snapshot": source_snapshot,
        "target_snapshot": target_snapshot,
        "source_rows": source_rows,
        "diff": diff,
        "slice_sha256": base._payload_sha256(source_rows),
    }
    context["event"] = _event(context["slice_sha256"])
    context["required_confirmation"] = _confirmation(context)
    return context


def _public(context: Mapping[str, Any], *, mode: str, executed: bool = False) -> dict[str, Any]:
    return {
        "schema_version": "research-report-primary-bulk-promotion-v1",
        "task_id": TASK_ID,
        "status": "completed" if executed else "ready",
        "mode": mode,
        "executed": executed,
        "source_database": context["source_snapshot"]["identity"]["database_name"],
        "target_database": context["target_snapshot"]["identity"]["database_name"],
        "run_sha256": context["run_sha256"],
        "slice_sha256": context["slice_sha256"],
        "insert_counts": context["diff"]["insert_counts"],
        "equal_existing_counts": context["diff"]["equal_counts"],
        "required_confirmation": "consumed_and_redacted" if executed else context["required_confirmation"],
        "write_contract": {
            "strategy": "single_target_transaction_insert_only",
            "delete_operations": [], "update_operations": [],
            "raw_files_preserved": True, "duplicate_aliases_preserved": True,
            "opensearch_preserved": True, "fact_opinion_boundary": BOUNDARY,
        },
        "classification": "local-only", "acceptable_for_non_local_release": False,
    }


def _promote(target_dsn: str, context: Mapping[str, Any]) -> dict[str, Any]:
    rows = list(context["source_rows"])
    keys = base._record_keys(rows)
    inserted: list[tuple[str, str]] = []
    expected_event = base._audit_storage_row(context["event"])
    with closing(_connect(target_dsn)) as connection:
        with connection.transaction():
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
                cursor.execute("SELECT pg_advisory_xact_lock(%s)", (base.PROMOTION_ADVISORY_LOCK,))
                if base._query_snapshot(cursor) != context["target_snapshot"]:
                    raise BulkPromotionRefused("primary changed after bulk preflight")
                current: list[dict[str, Any]] = []
                for collection in base.ALLOWED_COLLECTIONS:
                    current.extend(base._fetch_records(cursor, collection, keys.get(collection, [])))
                if base._target_diff(rows, current) != context["diff"]:
                    raise BulkPromotionRefused("primary slice changed after bulk preflight")
                for row in rows:
                    if (row["collection"], row["item_id"]) not in context["diff"]["insert_keys"]:
                        continue
                    cursor.execute(
                        "INSERT INTO ai_quant.records (collection, item_id, payload, position) VALUES (%s, %s, %s::jsonb, %s) ON CONFLICT (collection, item_id) DO NOTHING RETURNING item_id",
                        (row["collection"], row["item_id"], base._canonical_json(row["payload"]), row["position"]),
                    )
                    if cursor.fetchone() is None:
                        raise BulkPromotionRefused("primary row changed during bulk insert")
                    inserted.append((row["collection"], row["item_id"]))
                if base._read_audit(cursor, context["event"]["event_id"]) is not None:
                    raise BulkPromotionRefused("bulk promotion audit event already exists")
                event = context["event"]
                cursor.execute(
                    "INSERT INTO ai_quant.audit_log (event_id, actor, action, resource_type, resource_id, source, version, model_version, prompt_version, approval_state, trace_id, payload, timestamp) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)",
                    (event["event_id"], event["actor"], event["action"], event["resource_type"], event["resource_id"], event["source"], event["version"], event["model_version"], event["prompt_version"], event["approval_state"], event["trace_id"], base._canonical_json(event), event["timestamp"]),
                )
    snapshot, rows_after = _target_rows(target_dsn, rows)
    expected_snapshot = dict(context["target_snapshot"])
    expected_snapshot["table_counts"] = dict(expected_snapshot["table_counts"])
    expected_snapshot["research_counts"] = dict(expected_snapshot["research_counts"])
    expected_snapshot["table_counts"]["records"] += len(inserted)
    expected_snapshot["table_counts"]["audit_log"] += 1
    for collection, key in (("research_reports", "research_reports"), ("documents", "research_documents"), ("evidence", "research_report_citation_evidence")):
        expected_snapshot["research_counts"][key] += sum(1 for item in inserted if item[0] == collection)
    if snapshot["identity"] != expected_snapshot["identity"] or snapshot["table_counts"] != expected_snapshot["table_counts"] or snapshot["research_counts"] != expected_snapshot["research_counts"] or rows_after != rows:
        raise BulkPromotionRefused("post-commit bulk verification failed")
    return {"inserted_counts": {collection: sum(1 for item in inserted if item[0] == collection) for collection in base.ALLOWED_COLLECTIONS}, "post_commit_verification": {"status": "passed", "table_counts": snapshot["table_counts"], "research_counts": snapshot["research_counts"], "audit_event_id": context["event"]["event_id"]}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("preflight", "promote"), default="preflight")
    parser.add_argument("--source-dsn-env", required=True)
    parser.add_argument("--target-dsn-env", required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--confirm", default="")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    context = _prepare(_dsn(args.source_dsn_env), _dsn(args.target_dsn_env), args.run)
    if args.mode == "promote":
        if args.confirm != context["required_confirmation"]:
            raise BulkPromotionRefused("--confirm must match the current bulk preflight token")
        result = {**_public(context, mode="promote", executed=True), **_promote(_dsn(args.target_dsn_env), context)}
    else:
        result = _public(context, mode="preflight")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BulkPromotionRefused as exc:
        raise SystemExit(f"bulk promotion refused: {exc}") from exc
