from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.recover_watchlist_research_reports import (
    BOUNDARY,
    RecoveryRefused,
    WATCHLIST_SYMBOLS,
    build_recovery_plan,
    execute_cloned_pilot,
    identities_from_company_profiles,
    inventory_raw_reports,
    main,
    match_watchlist_symbols,
    validate_clone_attestation_static,
    verify_execute_confirmation,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FakeClient:
    def __init__(self, report_ids: list[str]) -> None:
        self.report_ids = report_ids
        self.calls: list[tuple[str, str, dict[str, object]]] = []

    def request(self, method: str, path: str, body: dict[str, object] | None = None) -> dict[str, object]:
        self.calls.append((method, path, dict(body or {})))
        if path == "/api/research-reports/scan":
            return {
                "indexed_count": len(self.report_ids),
                "reports": [{"report_id": report_id} for report_id in self.report_ids],
            }
        if path.endswith("/ingest"):
            content_sha256 = str((body or {}).get("content_sha256") or "")
            return {
                "created": not any(call_path == path for _method, call_path, _body in self.calls[:-1]),
                "report": {"content_sha256": content_sha256},
                "document": {"content_sha256": content_sha256},
            }
        if path.endswith("/extract"):
            report_id = path.split("/")[-2]
            return {"status": "text_indexed", "evidence": [{"evidence_id": f"evi_{report_id}"}], "manual_review": None}
        raise AssertionError(path)


class WatchlistResearchReportRecoveryTests(unittest.TestCase):
    def _raw_files(self, root: Path) -> None:
        fixtures = {
            "高盛研报/2026/2026-05-07-GS-Apple Inc (AAPL) update.txt": b"apple opinion",
            "高盛研报/2026/2026-05-08-GS-NVIDIA Corp (NVDA) update.txt": b"nvidia opinion",
            "高盛研报/2026/2026-05-09-GS-Microsoft Corp (MSFT) update.txt": b"microsoft opinion",
            "高盛研报/2026/2026-05-10-GS-CATL (300750.SZ) update.txt": b"catl opinion",
            "高盛研报/2026/2026-05-11-GS-Kweichow Moutai (600519.SS) update.txt": b"moutai opinion",
            "高盛研报/2026/2026-05-12-GS-AAPL-and-NVDA-sector-note.txt": b"ambiguous opinion",
            "高盛研报/2026/2026-05-13-GS-Apple-supply-chain.txt": b"weak alias",
        }
        for relative, content in fixtures.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)

    def _identities(self) -> dict[str, dict[str, str]]:
        return {
            symbol: {
                "issuer_id": f"issuer_{symbol.lower()}",
                "security_id": f"security_{symbol.lower()}",
                "profile_name": symbol,
                "resolution_status": "resolved_exact_ticker_profile",
            }
            for symbol in WATCHLIST_SYMBOLS
        }

    def _inputs(self, root: Path) -> tuple[Path, dict[str, object], Path, dict[str, object]]:
        registry_root = Path("/data/local/research_reports")
        inventory = inventory_raw_reports(root, registry_root=registry_root, extensions={".txt"})
        dump = root / "backup.dump"
        dump.write_bytes(b"backup")
        now = datetime.now(timezone.utc)
        manifest_path = root / "backup.manifest.json"
        collection_counts = {
            "research_reports": 7,
            "research_documents": 7,
            "research_report_citation_evidence": 7,
        }
        manifest = {
            "status": "passed",
            "restore_verified": True,
            "dump_path": str(dump),
            "dump_size_bytes": dump.stat().st_size,
            "dump_sha256": _sha256(dump),
            "retained_until": (now + timedelta(days=7)).isoformat(),
            "source_counts": {"records": 10},
            "restored_counts": {"records": 10},
            "collection_counts": collection_counts,
            "restored_collection_counts": collection_counts,
        }
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        reconciliation_path = root / "reconciliation.json"
        reconciliation: dict[str, object] = {
            "schema_version": "research-report-state-reconciliation-v1",
            "generated_at": now.isoformat(),
            "summary": {"audit_status": "complete", "reconciliation_status": "drift_detected"},
            "stores": {
                "filesystem": {
                    "availability": "available",
                    "counts": {"eligible_report_files": inventory["eligible_report_files"]},
                    "eligible_manifest_sha256": inventory["eligible_manifest_sha256"],
                },
                "postgres": {"availability": "available", "collection_counts": {"research_reports": 0}},
                "opensearch": {"availability": "available"},
                "object_store": {"availability": "available"},
            },
            "backup_evidence": {
                "manifest": str(manifest_path),
                "restore_verified": True,
                "research_collection_count_recorded": True,
            },
            "recovery_assessment": {
                "backup_protects_current_research_state": True,
                "backup_protects_expected_research_state": True,
                "recovery_readiness": "manual_review_required",
                "safe_to_delete_raw_reports": False,
                "safe_to_delete_search_index": False,
                "safe_to_treat_opensearch_as_source_of_truth": False,
            },
        }
        reconciliation_path.write_text(json.dumps(reconciliation), encoding="utf-8")
        return reconciliation_path, reconciliation, manifest_path, manifest

    def _plan(self, root: Path) -> dict[str, object]:
        reconciliation_path, reconciliation, manifest_path, manifest = self._inputs(root)
        return build_recovery_plan(
            filesystem_root=root,
            registry_root=Path("/data/local/research_reports"),
            extensions={".txt"},
            reconciliation_path=reconciliation_path,
            reconciliation=reconciliation,
            backup_manifest_path=manifest_path,
            backup_manifest=manifest,
            identities=self._identities(),
            identity_source="test",
            max_reports_per_symbol=1,
            content_hash_budget_bytes=1024 * 1024,
        )

    def _clone_attestation(self, plan: dict[str, object], *, base_url: str = "http://127.0.0.1:18001") -> dict[str, object]:
        evidence = plan["input_evidence"]
        generated_at = datetime.now(timezone.utc).isoformat()
        database_name = "ai_quant_t608_clone"
        runtime_identity = {
            "app_container_id": "a" * 64,
            "app_container_hostname": "a" * 12,
            "app_image_id": "sha256:" + "1" * 64,
            "postgres_container_id": "b" * 64,
            "postgres_image_id": "sha256:" + "2" * 64,
            "isolated_network_id": "c" * 64,
            "database_oid": "16384",
            "postgres_system_identifier": "7612345678901234567",
        }
        runtime_proof: dict[str, object] = {
            "schema_version": "research-report-clone-runtime-proof-v1",
            "producer": "scripts/probe_research_report_clone_runtime.py",
            "generated_at": generated_at,
            "base_url": base_url,
            "execution_scope": "inside_clone_app_container",
            "health_probe": {
                "status": "ok",
                "store": "PostgreSQLStore",
                "object_store_backend": "local",
                "search_backend": "local",
                "transport": "docker_exec_loopback",
            },
            "database_probe": {
                "query_id": "select_current_database",
                "success": True,
                "current_database": database_name,
                "database_oid": runtime_identity["database_oid"],
                "postgres_system_identifier": runtime_identity["postgres_system_identifier"],
                "table_counts": evidence["backup_source_counts"],
                "collection_counts": evidence["backup_collection_counts"],
            },
            "environment_summary": {
                "runtime_database_name": database_name,
                "object_store_backend": "local",
                "search_backend": "local",
                "network_isolation": True,
                "isolated_network_name": "ai_quant_t608_pilot_net",
                "network_names": ["ai_quant_t608_pilot_net"],
                "network_internal": True,
                "network_members_limited_to_app_and_postgres": True,
                "raw_mount_read_only": True,
                "root_filesystem_read_only": True,
                "primary_service_reachable": False,
                "execution_scope": "inside_clone_app_container",
            },
            "runtime_identity": runtime_identity,
        }
        runtime_proof_sha256 = hashlib.sha256(
            json.dumps(runtime_proof, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
        ).hexdigest()
        return {
            "schema_version": "research-report-clone-attestation-v1",
            "status": "passed",
            "generated_at": generated_at,
            "environment": "cloned_database_pilot",
            "base_url": base_url,
            "execution_scope": "inside_clone_app_container",
            "database_name": database_name,
            "runtime_database_name": database_name,
            "object_store_backend": "local",
            "search_backend": "local",
            "network_isolation": True,
            "raw_mount_read_only": True,
            "primary_service_reachable": False,
            "restore_verified": True,
            "source_backup_dump_sha256": evidence["backup_dump_sha256"],
            "plan_sha256": plan["plan_sha256"],
            "source_counts": evidence["backup_source_counts"],
            "restored_counts": evidence["backup_source_counts"],
            "collection_counts": evidence["backup_collection_counts"],
            "restored_collection_counts": evidence["backup_collection_counts"],
            "runtime_identity": runtime_identity,
            "runtime_proof": runtime_proof,
            "runtime_proof_sha256": runtime_proof_sha256,
        }

    def test_filename_matching_quarantines_weak_and_multi_company_aliases(self) -> None:
        exact = match_watchlist_symbols("Apple Inc (AAPL) update.pdf")
        canonical_only = match_watchlist_symbols("NVIDIA Corporation update.pdf")
        weak = match_watchlist_symbols("Apple supply chain.pdf")
        multiple = match_watchlist_symbols("AAPL and NVDA sector note.pdf")

        self.assertEqual(exact[0]["symbol"], "AAPL")
        self.assertEqual(exact[0]["strength"], "exact_ticker")
        self.assertEqual(canonical_only[0]["strength"], "canonical_company_name_needs_review")
        self.assertEqual(weak, [{"symbol": "AAPL", "strength": "ambiguous_alias", "matched_terms": ["Apple"]}])
        self.assertEqual({item["symbol"] for item in multiple}, {"AAPL", "NVDA"})

    def test_plan_is_deterministic_and_has_five_collision_free_batches(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._raw_files(root)
            reconciliation_path, reconciliation, manifest_path, manifest = self._inputs(root)
            kwargs = {
                "filesystem_root": root,
                "registry_root": Path("/data/local/research_reports"),
                "extensions": {".txt"},
                "reconciliation_path": reconciliation_path,
                "reconciliation": reconciliation,
                "backup_manifest_path": manifest_path,
                "backup_manifest": manifest,
                "identities": self._identities(),
                "identity_source": "test",
                "max_reports_per_symbol": 1,
                "content_hash_budget_bytes": 1024 * 1024,
            }
            first = build_recovery_plan(**kwargs)
            second = build_recovery_plan(**kwargs)

        self.assertEqual(first["plan_sha256"], second["plan_sha256"])
        self.assertTrue(first["execution_allowed"])
        self.assertEqual(first["status"], "ready_for_cloned_pilot")
        self.assertEqual([item["symbol"] for item in first["companies"]], list(WATCHLIST_SYMBOLS))
        self.assertTrue(all(item["selected_count"] == 1 for item in first["companies"]))
        report_ids = [item["selected_reports"][0]["report_id"] for item in first["companies"]]
        self.assertEqual(len(report_ids), len(set(report_ids)))
        self.assertTrue(all(item["selected_reports"][0]["dedup_key"].startswith("sha256:") for item in first["companies"]))
        self.assertEqual(first["candidate_diagnostics"]["ambiguous_multi_symbol_count"], 1)
        self.assertEqual(first["write_contract"]["delete_operations"], [])

    def test_missing_evidence_and_identity_remain_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "desk" / "2026-05-07-Apple Inc (AAPL).txt"
            path.parent.mkdir(parents=True)
            path.write_text("opinion", encoding="utf-8")
            reconciliation_path, reconciliation, manifest_path, manifest = self._inputs(root)
            plan = build_recovery_plan(
                filesystem_root=root,
                registry_root=Path("/data/local/research_reports"),
                extensions={".txt"},
                reconciliation_path=reconciliation_path,
                reconciliation=reconciliation,
                backup_manifest_path=manifest_path,
                backup_manifest=manifest,
                identities={},
                identity_source="unavailable",
                max_reports_per_symbol=1,
                content_hash_budget_bytes=1024,
            )

        by_symbol = {item["symbol"]: item for item in plan["companies"]}
        self.assertEqual(by_symbol["AAPL"]["status"], "needs_identity")
        self.assertEqual(by_symbol["NVDA"]["status"], "needs_evidence")
        self.assertFalse(plan["execution_allowed"])
        self.assertIn("five_company_batches_present", plan["failed_gate_ids"])
        self.assertIn("five_company_identities_resolved", plan["failed_gate_ids"])

    def test_current_style_backup_without_collection_restore_counts_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._raw_files(root)
            reconciliation_path, reconciliation, manifest_path, manifest = self._inputs(root)
            manifest.pop("collection_counts")
            manifest.pop("restored_collection_counts")
            reconciliation["backup_evidence"]["research_collection_count_recorded"] = False
            reconciliation["recovery_assessment"]["backup_protects_current_research_state"] = False
            reconciliation["recovery_assessment"]["backup_protects_expected_research_state"] = False
            reconciliation["recovery_assessment"]["recovery_readiness"] = "blocked_missing_collection_aware_rollback_evidence"
            plan = build_recovery_plan(
                filesystem_root=root,
                registry_root=Path("/data/local/research_reports"),
                extensions={".txt"},
                reconciliation_path=reconciliation_path,
                reconciliation=reconciliation,
                backup_manifest_path=manifest_path,
                backup_manifest=manifest,
                identities=self._identities(),
                identity_source="test",
                max_reports_per_symbol=1,
                content_hash_budget_bytes=1024 * 1024,
            )

        self.assertFalse(plan["execution_allowed"])
        self.assertIn("backup_collection_metrics_present", plan["failed_gate_ids"])
        self.assertIn("backup_collection_restore_counts_match", plan["failed_gate_ids"])
        self.assertIn("reconciliation_clone_pilot_review_ready", plan["failed_gate_ids"])

    def test_zero_state_backup_can_authorize_only_the_attested_clone_pilot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._raw_files(root)
            reconciliation_path, reconciliation, manifest_path, manifest = self._inputs(root)
            zero_counts = {
                "research_reports": 0,
                "research_documents": 0,
                "research_report_citation_evidence": 0,
            }
            manifest["collection_counts"] = zero_counts
            manifest["restored_collection_counts"] = zero_counts
            reconciliation["recovery_assessment"]["backup_protects_current_research_state"] = True
            reconciliation["recovery_assessment"]["backup_protects_expected_research_state"] = False
            reconciliation["recovery_assessment"]["recovery_readiness"] = "clone_pilot_review_required"

            plan = build_recovery_plan(
                filesystem_root=root,
                registry_root=Path("/data/local/research_reports"),
                extensions={".txt"},
                reconciliation_path=reconciliation_path,
                reconciliation=reconciliation,
                backup_manifest_path=manifest_path,
                backup_manifest=manifest,
                identities=self._identities(),
                identity_source="test",
                max_reports_per_symbol=1,
                content_hash_budget_bytes=1024 * 1024,
            )

        self.assertTrue(plan["execution_allowed"])
        self.assertEqual(plan["status"], "ready_for_cloned_pilot")
        self.assertNotIn("reconciliation_backup_protects_current_state", plan["failed_gate_ids"])

    def test_execute_confirmation_refuses_before_any_client_call(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._raw_files(root)
            plan = self._plan(root)

        with self.assertRaises(RecoveryRefused):
            verify_execute_confirmation(
                plan,
                base_url="http://127.0.0.1:18001",
                clone_attestation=self._clone_attestation(plan),
                confirm_plan_sha256="wrong",
                acknowledge_opinion_boundary=True,
                allow_full_registry_scan=True,
                confirm_clone_target=True,
            )

    def test_clone_pilot_uses_only_post_upserts_and_is_rerunnable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._raw_files(root)
            plan = self._plan(root)
            verify_execute_confirmation(
                plan,
                base_url="http://127.0.0.1:18001",
                clone_attestation=self._clone_attestation(plan),
                confirm_plan_sha256=str(plan["plan_sha256"]),
                acknowledge_opinion_boundary=True,
                allow_full_registry_scan=True,
                confirm_clone_target=True,
            )
            inventory = inventory_raw_reports(root, registry_root=Path("/data/local/research_reports"), extensions={".txt"})
            all_report_ids = [row["report_id"] for row in inventory["rows"]]
            client = FakeClient(all_report_ids)
            first = execute_cloned_pilot(
                plan,
                client=client,
                filesystem_root=root,
                api_root="/data/local/research_reports",
                extensions={".txt"},
                citation_char_limit=1200,
                max_text_chars=50000,
                pdf_pages=1,
                pdftotext_timeout=1,
            )
            second = execute_cloned_pilot(
                plan,
                client=client,
                filesystem_root=root,
                api_root="/data/local/research_reports",
                extensions={".txt"},
                citation_char_limit=1200,
                max_text_chars=50000,
                pdf_pages=1,
                pdftotext_timeout=1,
            )

        self.assertEqual(first["selected_report_count"], 5)
        self.assertEqual(second["selected_report_count"], 5)
        self.assertEqual(first["status"], "passed")
        self.assertEqual(first["content_identity_verified_count"], 5)
        self.assertEqual(first["delete_operations"], [])
        self.assertEqual(first["fact_opinion_boundary"], BOUNDARY)
        self.assertTrue(all(method == "POST" for method, _path, _body in client.calls))
        self.assertFalse(any("delete" in path.lower() for _method, path, _body in client.calls))
        ingest_bodies = [body for _method, path, body in client.calls if path.endswith("/ingest")]
        self.assertTrue(all(len(str(body.get("content_sha256") or "")) == 64 for body in ingest_bodies))

    def test_clone_pilot_fails_when_extraction_produces_no_evidence(self) -> None:
        class NoEvidenceClient(FakeClient):
            def request(self, method: str, path: str, body: dict[str, object] | None = None) -> dict[str, object]:
                if path.endswith("/extract"):
                    self.calls.append((method, path, dict(body or {})))
                    return {"status": "needs_text_review", "evidence": [], "manual_review": {"review_id": "mr_1"}}
                return super().request(method, path, body)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._raw_files(root)
            plan = self._plan(root)
            inventory = inventory_raw_reports(root, registry_root=Path("/data/local/research_reports"), extensions={".txt"})
            client = NoEvidenceClient([row["report_id"] for row in inventory["rows"]])
            result = execute_cloned_pilot(
                plan,
                client=client,
                filesystem_root=root,
                api_root="/data/local/research_reports",
                extensions={".txt"},
                citation_char_limit=1200,
                max_text_chars=50000,
                pdf_pages=1,
                pdftotext_timeout=1,
            )

        self.assertEqual(result["status"], "failed_evidence_gate")
        self.assertEqual(result["needs_evidence_count"], 5)
        self.assertEqual(result["evidence_count"], 0)

    def test_default_live_url_is_rejected_before_api_client_construction(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            attestation_path = root / "clone-attestation.json"
            attestation_path.write_text(
                json.dumps(
                    {
                        "schema_version": "research-report-clone-attestation-v1",
                        "status": "passed",
                        "generated_at": datetime.now(timezone.utc).isoformat(),
                        "environment": "cloned_database_pilot",
                        "base_url": "http://127.0.0.1:8000",
                        "database_name": "ai_quant_t608_clone",
                        "restore_verified": True,
                        "source_counts": {"records": 1},
                        "restored_counts": {"records": 1},
                        "collection_counts": {
                            "research_reports": 0,
                            "research_documents": 0,
                            "research_report_citation_evidence": 0,
                        },
                        "restored_collection_counts": {
                            "research_reports": 0,
                            "research_documents": 0,
                            "research_report_citation_evidence": 0,
                        },
                    }
                ),
                encoding="utf-8",
            )
            constructed: list[str] = []

            def unexpected_client(*_args: object, **_kwargs: object) -> object:
                constructed.append("called")
                raise AssertionError("ApiClient must not be constructed for the live/default URL")

            with patch("scripts.recover_watchlist_research_reports.ApiClient", side_effect=unexpected_client):
                with self.assertRaisesRegex(SystemExit, "default_live_url_rejected"):
                    main(
                        [
                            "--execute",
                            "--base-url",
                            "http://127.0.0.1:8000",
                            "--clone-attestation",
                            str(attestation_path),
                            "--backup-manifest",
                            str(root / "not-read-before-rejection.json"),
                        ]
                    )

        self.assertEqual(constructed, [])

    def test_unsafe_runtime_proof_is_rejected_before_api_client_construction(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._raw_files(root)
            plan = self._plan(root)
            attestation = self._clone_attestation(plan)
            attestation["search_backend"] = "opensearch"
            attestation_path = root / "clone-attestation.json"
            attestation_path.write_text(json.dumps(attestation), encoding="utf-8")
            constructed: list[str] = []

            def unexpected_client(*_args: object, **_kwargs: object) -> object:
                constructed.append("called")
                raise AssertionError("ApiClient must not be constructed for unsafe clone runtime proof")

            with patch("scripts.recover_watchlist_research_reports.ApiClient", side_effect=unexpected_client):
                with self.assertRaisesRegex(SystemExit, "clone_search_backend_local"):
                    main(
                        [
                            "--execute",
                            "--base-url",
                            "http://127.0.0.1:18001",
                            "--clone-attestation",
                            str(attestation_path),
                            "--backup-manifest",
                            str(root / "not-read-before-rejection.json"),
                        ]
                    )

        self.assertEqual(constructed, [])

    def test_clone_attestation_must_be_recent_and_non_primary(self) -> None:
        attestation = {
            "schema_version": "research-report-clone-attestation-v1",
            "status": "passed",
            "generated_at": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
            "environment": "cloned_database_pilot",
            "base_url": "http://127.0.0.1:18001",
            "database_name": "ai_quant",
            "restore_verified": True,
            "source_counts": {"records": 1},
            "restored_counts": {"records": 1},
            "collection_counts": {
                "research_reports": 0,
                "research_documents": 0,
                "research_report_citation_evidence": 0,
            },
            "restored_collection_counts": {
                "research_reports": 0,
                "research_documents": 0,
                "research_report_citation_evidence": 0,
            },
        }
        with self.assertRaisesRegex(RecoveryRefused, "clone_attestation_recent"):
            validate_clone_attestation_static(attestation, base_url="http://127.0.0.1:18001")

    def test_clone_attestation_requires_isolated_local_runtime_proof(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._raw_files(root)
            plan = self._plan(root)
        attestation = self._clone_attestation(plan)

        validate_clone_attestation_static(attestation, base_url="http://127.0.0.1:18001")

        cases = {
            "clone_runtime_database_name": ("runtime_database_name", "ai_quant"),
            "clone_object_store_backend_local": ("object_store_backend", "s3"),
            "clone_search_backend_local": ("search_backend", "opensearch"),
            "clone_network_isolation": ("network_isolation", False),
            "clone_raw_mount_read_only": ("raw_mount_read_only", False),
            "clone_primary_service_unreachable": ("primary_service_reachable", True),
            "clone_execution_scope": ("execution_scope", "host_process"),
        }
        for expected_gate, (field, unsafe_value) in cases.items():
            with self.subTest(field=field):
                unsafe = dict(attestation)
                unsafe[field] = unsafe_value
                with self.assertRaisesRegex(RecoveryRefused, expected_gate):
                    validate_clone_attestation_static(unsafe, base_url="http://127.0.0.1:18001")

    def test_clone_attestation_rejects_tampered_or_unstructured_runtime_proof(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._raw_files(root)
            plan = self._plan(root)
        attestation = self._clone_attestation(plan)
        tampered_proof = json.loads(json.dumps(attestation["runtime_proof"]))
        tampered_proof["database_probe"]["current_database"] = "ai_quant"
        tampered = {**attestation, "runtime_proof": tampered_proof}

        with self.assertRaisesRegex(RecoveryRefused, "clone_runtime_proof_hash"):
            validate_clone_attestation_static(tampered, base_url="http://127.0.0.1:18001")

        free_text = {**attestation, "runtime_proof": {"summary": "everything is isolated"}}
        free_text["runtime_proof_sha256"] = hashlib.sha256(
            json.dumps(free_text["runtime_proof"], separators=(",", ":"), sort_keys=True).encode("utf-8")
        ).hexdigest()
        with self.assertRaisesRegex(RecoveryRefused, "clone_runtime_proof_schema"):
            validate_clone_attestation_static(free_text, base_url="http://127.0.0.1:18001")

    def test_company_profile_resolution_requires_one_profile_and_security(self) -> None:
        profiles = {
            "profiles": [
                {
                    "issuer_id": "issuer_aapl",
                    "security_ids": ["security_aapl_us"],
                    "display_name": "Apple Inc.",
                    "identifiers": {"tickers": ["AAPL"]},
                },
                {
                    "issuer_id": "issuer_nvda",
                    "security_ids": ["security_nvda_us", "security_nvda_alt"],
                    "identifiers": {"tickers": ["NVDA"]},
                },
            ]
        }

        identities = identities_from_company_profiles(profiles)

        self.assertEqual(identities["AAPL"]["resolution_status"], "resolved_exact_ticker_profile")
        self.assertEqual(identities["NVDA"]["resolution_status"], "ambiguous_company_profile")
        self.assertEqual(identities["MSFT"]["resolution_status"], "needs_evidence")


if __name__ == "__main__":
    unittest.main()
