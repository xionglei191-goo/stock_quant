from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import datetime, timedelta, timezone
import hashlib
import inspect
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import promote_research_report_clone_to_primary as promotion


NOW = datetime(2026, 7, 21, 4, 0, tzinfo=timezone.utc)


def _plan() -> dict[str, object]:
    companies: list[dict[str, object]] = []
    for symbol in promotion.WATCHLIST_SYMBOLS:
        report_id = f"rr_{symbol.lower()}"
        digest = hashlib.sha256(symbol.encode("utf-8")).hexdigest()
        companies.append(
            {
                "symbol": symbol,
                "status": "planned",
                "identity": {
                    "issuer_id": f"issuer_{symbol.lower()}",
                    "security_id": f"security_{symbol.lower()}",
                    "resolution_status": "resolved_exact_ticker_profile",
                },
                "selected_reports": [
                    {
                        "report_id": report_id,
                        "document_id": f"doc_{report_id}",
                        "content_sha256": digest,
                        "evidence_id_prefix": f"evi_doc_{report_id}_research_",
                        "source_boundary": promotion.BOUNDARY,
                    }
                ],
            }
        )
    core: dict[str, object] = {
        "schema_version": "watchlist-research-report-recovery-plan-v1",
        "related_tasks": ["T-603", "T-604", "T-608"],
        "filesystem_snapshot": {"eligible_report_files": 11702},
        "input_evidence": {"backup_dump_sha256": "1" * 64},
        "settings": {"watchlist_symbols": list(promotion.WATCHLIST_SYMBOLS)},
        "companies": companies,
        "candidate_diagnostics": {},
        "write_contract": {"fact_opinion_boundary": promotion.BOUNDARY},
    }
    return {
        **core,
        "plan_sha256": promotion._payload_sha256(core),
        "execution_allowed": True,
        "status": "ready_for_cloned_pilot",
        "failed_gate_ids": [],
    }


def _execution(plan: dict[str, object], *, created: bool) -> dict[str, object]:
    results: list[dict[str, object]] = []
    for company in plan["companies"]:
        report = company["selected_reports"][0]
        results.append(
            {
                "symbol": company["symbol"],
                "report_id": report["report_id"],
                "document_id": report["document_id"],
                "ingest_created": created,
                "status": "text_indexed",
                "evidence_count": 1,
                "manual_review": False,
                "text_source": "pdftotext",
                "content_sha256": report["content_sha256"],
                "content_identity_verified": True,
                "fact_opinion_boundary": promotion.BOUNDARY,
            }
        )
    return {
        "plan": plan,
        "execution": {
            "schema_version": "watchlist-research-report-recovery-execution-v1",
            "generated_at": NOW.isoformat(),
            "environment": "operator_confirmed_cloned_database_pilot",
            "status": "passed",
            "plan_sha256": plan["plan_sha256"],
            "registry_indexed_count": 11702,
            "selected_report_count": len(results),
            "evidence_count": len(results),
            "needs_evidence_count": 0,
            "content_identity_verified_count": len(results),
            "results": results,
            "delete_operations": [],
            "raw_files_preserved": True,
            "opensearch_index_preserved": True,
            "fact_opinion_boundary": promotion.BOUNDARY,
        },
    }


def _restricted_rights() -> dict[str, object]:
    return {
        "license_class": "local_research_reference",
        "training_allowed": False,
        "redistribution_allowed": False,
        "display_use": "restricted",
        "non_display_use": "restricted",
        "derived_data_use": "restricted",
    }


def _slice_rows(plan: dict[str, object]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    source_id = "local_research_test"
    rows.append(
        {
            "collection": "sources",
            "item_id": source_id,
            "payload": {
                "source_id": source_id,
                "source_type": "local_reference",
                "usage_scope": "local_reference_citation_tracking_only",
                "allowed_document_types": ["research"],
                "rights_tag": _restricted_rights(),
            },
            "position": None,
        }
    )
    for company in plan["companies"]:
        report = company["selected_reports"][0]
        report_id = report["report_id"]
        document_id = report["document_id"]
        common = {
            "issuer_id": company["identity"]["issuer_id"],
            "security_id": company["identity"]["security_id"],
            "source_id": source_id,
            "content_sha256": report["content_sha256"],
            "rights_tag": _restricted_rights(),
        }
        rows.extend(
            [
                {
                    "collection": "research_reports",
                    "item_id": report_id,
                    "payload": {
                        **common,
                        "report_id": report_id,
                        "document_id": document_id,
                        "status": "text_indexed",
                    },
                    "position": None,
                },
                {
                    "collection": "documents",
                    "item_id": document_id,
                    "payload": {
                        **common,
                        "document_id": document_id,
                        "document_type": "research",
                        "source_type": "local_reference",
                        "source_uri": f"research-report://{report_id}",
                        "body": "bounded local opinion citation",
                    },
                    "position": None,
                },
                {
                    "collection": "evidence",
                    "item_id": f"evi_{document_id}_research_0",
                    "payload": {
                        "evidence_id": f"evi_{document_id}_research_0",
                        "document_id": document_id,
                        "section": "research_report_citation",
                        "bbox": f"research_report://{document_id};chunk=0",
                        "span_text": "bounded local opinion citation",
                        "canonical_text": "bounded local opinion citation",
                    },
                    "position": None,
                },
            ]
        )
    return sorted(rows, key=lambda row: (row["collection"], row["item_id"]))


class FakeTransaction(AbstractContextManager[None]):
    def __init__(self, connection: "FakeConnection") -> None:
        self.connection = connection
        self.rows_before: list[dict[str, object]] = []
        self.audit_before: dict[str, dict[str, object]] = {}

    def __enter__(self) -> None:
        self.rows_before = json.loads(json.dumps(self.connection.rows))
        self.audit_before = json.loads(json.dumps(self.connection.audit))
        return None

    def __exit__(self, exc_type, exc, traceback) -> bool:
        if exc_type is not None:
            self.connection.rows[:] = self.rows_before
            self.connection.audit.clear()
            self.connection.audit.update(self.audit_before)
        return False


class FakeCursor(AbstractContextManager["FakeCursor"]):
    def __init__(self, connection: "FakeConnection") -> None:
        self.connection = connection
        self.rowcount = 0

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        return False

    def execute(self, sql: str, params: tuple[object, ...] | None = None) -> None:
        normalized = " ".join(sql.upper().split())
        self.rowcount = 0
        if normalized.startswith("INSERT INTO AI_QUANT.RECORDS"):
            assert params is not None
            collection, item_id, payload, position = params
            key = (str(collection), str(item_id))
            if not any((row["collection"], row["item_id"]) == key for row in self.connection.rows):
                self.connection.rows.append(
                    {
                        "collection": str(collection),
                        "item_id": str(item_id),
                        "payload": json.loads(str(payload)),
                        "position": position,
                    }
                )
                self.connection.rows.sort(key=lambda row: (row["collection"], row["item_id"]))
                self.rowcount = 1
        elif normalized.startswith("INSERT INTO AI_QUANT.AUDIT_LOG"):
            assert params is not None
            event = json.loads(str(params[11]))
            if event["event_id"] not in self.connection.audit:
                self.connection.audit[event["event_id"]] = promotion._audit_storage_row(event)
                self.rowcount = 1


class FakeConnection:
    def __init__(self, rows: list[dict[str, object]], audit: dict[str, dict[str, object]]) -> None:
        self.rows = rows
        self.audit = audit

    def close(self) -> None:
        return None

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def transaction(self) -> FakeTransaction:
        return FakeTransaction(self)


class PrimaryResearchPromotionTests(unittest.TestCase):
    def test_plan_and_two_runs_must_be_exact_and_tamper_evident(self) -> None:
        plan = _plan()
        selected = promotion._selected_plan_rows(plan)
        run1 = _execution(plan, created=True)
        run2 = _execution(plan, created=False)

        first = promotion._validate_execution(run1, label="run1", plan=plan, selected=selected, require_created=True)
        second = promotion._validate_execution(run2, label="run2", plan=plan, selected=selected, require_created=False)
        self.assertEqual(set(first), set(selected))
        self.assertEqual(set(second), set(selected))

        tampered = json.loads(json.dumps(run2))
        tampered["execution"]["results"][0]["content_sha256"] = "0" * 64
        with self.assertRaisesRegex(promotion.PromotionRefused, "strict evidence gate"):
            promotion._validate_execution(tampered, label="run2", plan=plan, selected=selected, require_created=False)

        changed_plan = json.loads(json.dumps(plan))
        changed_plan["companies"][0]["identity"]["issuer_id"] = "issuer_tampered"
        with self.assertRaisesRegex(promotion.PromotionRefused, "canonical SHA"):
            promotion._selected_plan_rows(changed_plan)

    def test_source_slice_is_strictly_bounded_and_content_bound(self) -> None:
        plan = _plan()
        selected = promotion._selected_plan_rows(plan)
        run1 = promotion._validate_execution(_execution(plan, created=True), label="run1", plan=plan, selected=selected, require_created=True)
        run2 = promotion._validate_execution(_execution(plan, created=False), label="run2", plan=plan, selected=selected, require_created=False)
        rows = _slice_rows(plan)

        result = promotion._validate_source_slice(rows, selected=selected, run1=run1, run2=run2)

        self.assertEqual(result["counts"], {"sources": 1, "research_reports": 5, "documents": 5, "evidence": 5})
        escaped = json.loads(json.dumps(rows))
        escaped.append({"collection": "structured_research_reports", "item_id": "bad", "payload": {}, "position": None})
        with self.assertRaisesRegex(promotion.PromotionRefused, "allowlist"):
            promotion._validate_source_slice(escaped, selected=selected, run1=run1, run2=run2)

    def test_unequal_target_conflict_refuses_and_equal_target_is_idempotent(self) -> None:
        rows = _slice_rows(_plan())
        equal = promotion._target_diff(rows, json.loads(json.dumps(rows)))
        self.assertEqual(sum(equal["insert_counts"].values()), 0)
        self.assertEqual(sum(equal["equal_counts"].values()), len(rows))

        conflicting = json.loads(json.dumps(rows[:1]))
        conflicting[0]["payload"]["source_type"] = "changed"
        with self.assertRaisesRegex(promotion.PromotionRefused, "unequal conflicting"):
            promotion._target_diff(rows, conflicting)

    def test_backup_must_match_live_snapshot_and_verified_dump(self) -> None:
        snapshot = {
            "table_counts": {"records": 10, "audit_log": 2, "market_data_bars": 30},
            "research_counts": {key: 0 for key in promotion.RESEARCH_STATE_COUNT_KEYS},
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dump = root / "snapshot.dump"
            dump.write_bytes(b"restore-verified")
            manifest_path = root / "snapshot.manifest.json"
            database_manifest = {
                "table_counts": snapshot["table_counts"],
                "research_state": {"counts": snapshot["research_counts"]},
            }
            manifest = {
                "status": "passed",
                "restore_verified": True,
                "source_db": "ai_quant",
                "generated_at": (NOW - timedelta(minutes=5)).isoformat(),
                "retained_until": (NOW + timedelta(days=7)).isoformat(),
                "source_counts": snapshot["table_counts"],
                "restored_counts": snapshot["table_counts"],
                "collection_counts": snapshot["research_counts"],
                "restored_collection_counts": snapshot["research_counts"],
                "source_database_manifest": database_manifest,
                "restored_database_manifest": database_manifest,
                "dump_path": str(dump),
                "dump_sha256": promotion._file_sha256(dump),
                "dump_size_bytes": dump.stat().st_size,
            }
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            result = promotion._validate_backup_manifest(
                manifest_path, manifest, snapshot=snapshot, expected_database="ai_quant", now=NOW
            )
            self.assertEqual(result["dump_sha256"], promotion._file_sha256(dump))
            changed = {**snapshot, "table_counts": {**snapshot["table_counts"], "records": 11}}
            with self.assertRaisesRegex(promotion.PromotionRefused, "exactly bound"):
                promotion._validate_backup_manifest(
                    manifest_path, manifest, snapshot=changed, expected_database="ai_quant", now=NOW
                )

    def test_quiescence_proof_is_hash_bound_to_stopped_writers_and_target(self) -> None:
        snapshot = {
            "identity": {
                "database_name": "ai_quant",
                "database_oid": "100",
                "postgres_system_identifier": "200",
            },
            "table_counts": {"records": 1, "audit_log": 2, "market_data_bars": 3},
            "research_counts": {key: 0 for key in promotion.RESEARCH_STATE_COUNT_KEYS},
            "other_database_sessions": 0,
        }
        backup = {"dump_sha256": "a" * 64}
        core = {
            "schema_version": "research-report-primary-quiescence-proof-v1",
            "producer": "scripts/promote_research_report_clone_to_primary.py",
            "generated_at": NOW.isoformat(),
            "target_database": "ai_quant",
            "target_database_identity": snapshot["identity"],
            "target_table_counts": snapshot["table_counts"],
            "target_research_counts": snapshot["research_counts"],
            "target_backup_dump_sha256": backup["dump_sha256"],
            "other_database_sessions": 0,
            "writer_containers": [
                {
                    "name": "app",
                    "container_id": "a" * 64,
                    "image_id": "sha256:" + "b" * 64,
                    "running": False,
                    "status": "exited",
                }
            ],
            "operator_boundary": "primary_app_and_all_known_schedulers_stopped_for_t612",
        }
        proof = {**core, "status": "passed", "proof_sha256": promotion._payload_sha256(core)}
        self.assertEqual(
            promotion._validate_quiescence_proof(proof, snapshot=snapshot, target_backup=backup, now=NOW)["proof_sha256"],
            proof["proof_sha256"],
        )
        tampered = {**proof, "target_table_counts": {**snapshot["table_counts"], "records": 9}}
        with self.assertRaisesRegex(promotion.PromotionRefused, "proof hash"):
            promotion._validate_quiescence_proof(tampered, snapshot=snapshot, target_backup=backup, now=NOW)

    def test_transaction_rolls_back_all_rows_and_audit_on_failure(self) -> None:
        rows = _slice_rows(_plan())[:3]
        target_rows: list[dict[str, object]] = []
        audit: dict[str, dict[str, object]] = {}
        connection = FakeConnection(target_rows, audit)
        snapshot = {
            "identity": {"database_name": "ai_quant", "database_oid": "2", "postgres_system_identifier": "3"},
            "table_counts": {"records": 0, "audit_log": 0, "market_data_bars": 0},
            "research_counts": {key: 0 for key in promotion.RESEARCH_STATE_COUNT_KEYS},
            "other_database_sessions": 0,
        }
        event = promotion._audit_event("a" * 64, promotion._payload_sha256(rows), NOW.isoformat())
        context = {
            "source_rows": rows,
            "target_rows": [],
            "target_snapshot": snapshot,
            "target_diff": promotion._target_diff(rows, []),
            "audit_event": event,
        }

        def fake_fetch(cursor: FakeCursor, collection: str, item_ids: object) -> list[dict[str, object]]:
            allowed = set(item_ids)
            return [row for row in cursor.connection.rows if row["collection"] == collection and row["item_id"] in allowed]

        def fail_before_commit() -> None:
            raise RuntimeError("simulated failure")

        with (
            patch.object(promotion, "_query_snapshot", return_value=snapshot),
            patch.object(promotion, "_fetch_records", side_effect=fake_fetch),
            patch.object(promotion, "_read_audit", side_effect=lambda cursor, event_id: cursor.connection.audit.get(event_id)),
        ):
            with self.assertRaisesRegex(RuntimeError, "simulated failure"):
                promotion._insert_slice_transaction(
                    "dbname=ai_quant",
                    context=context,
                    connect=lambda _dsn: connection,
                    before_commit=fail_before_commit,
                )

        self.assertEqual(target_rows, [])
        self.assertEqual(audit, {})

    def test_default_cli_mode_is_read_only_preflight(self) -> None:
        context = {
            "source_database": "ai_quant_clone",
            "target_database": "ai_quant",
            "source_dsn_redacted": "source",
            "target_dsn_redacted": "target",
            "plan_sha256": "a" * 64,
            "selected": {"rr": {}},
            "slice": {"slice_sha256": "b" * 64, "counts": {key: 0 for key in promotion.ALLOWED_COLLECTIONS}},
            "target_diff": {
                "insert_counts": {key: 0 for key in promotion.ALLOWED_COLLECTIONS},
                "equal_counts": {key: 0 for key in promotion.ALLOWED_COLLECTIONS},
            },
            "source_backup": {"dump_sha256": "c" * 64},
            "target_backup": {"dump_sha256": "d" * 64},
            "quiescence": {"proof_sha256": "e" * 64},
            "artifact_hashes": {},
            "required_confirmation": "T612_PROMOTE:" + "f" * 64,
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "preflight.json"
            argv = [
                "--output", str(output),
                "--plan", "plan.json",
                "--run1", "run1.json",
                "--run2", "run2.json",
                "--source-backup", "source.json",
                "--target-backup", "target.json",
                "--quiescence-proof", "proof.json",
            ]
            with (
                patch.object(promotion, "_dsn_from_env", side_effect=["source-dsn", "target-dsn"]),
                patch.object(promotion, "prepare_promotion", return_value=context) as prepare,
                patch.object(promotion, "promote") as promote,
                patch("builtins.print"),
            ):
                self.assertEqual(promotion.main(argv), 0)

            prepare.assert_called_once()
            promote.assert_not_called()
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["mode"], "preflight")
            self.assertFalse(payload["executed"])

    def test_script_contains_no_delete_or_update_mutation_sql(self) -> None:
        source = inspect.getsource(promotion).upper()
        self.assertNotIn("DELETE FROM AI_QUANT", source)
        self.assertNotIn("UPDATE AI_QUANT", source)
        self.assertIn("ON CONFLICT (COLLECTION, ITEM_ID) DO NOTHING", source)
        self.assertIn("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE", source)


if __name__ == "__main__":
    unittest.main()
