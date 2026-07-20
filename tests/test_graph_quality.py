from __future__ import annotations

import json
import os
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

from app.models import (
    CompanyPosition,
    CompanyRelationship,
    DecisionPack,
    DisclosureEvent,
    Document,
    Evidence,
    IndustryChain,
    ResearchAnswer,
    ResearchSignal,
    RightsTag,
    ThesisCard,
)
from app.service_modules.graph_traceability import GraphTraceabilityReporting
from app.service_modules.graph_density_capacity import build_density_capacity_audit, renderer_recommendation
import scripts.backfill_full_knowledge_graph as backfill_full_knowledge_graph_script
import scripts.graph_enrichment_runner as graph_enrichment_runner_script
import scripts.graph_quality_center as graph_quality_center_script
from tests.support import SystemServiceTestBase


class GraphQualityTests(SystemServiceTestBase):
    def test_graph_density_capacity_audit_is_read_only_and_separates_fixture_data(self) -> None:
        temp_dir = TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        state_db = Path(temp_dir.name) / "density.sqlite"
        connection = sqlite3.connect(state_db)
        connection.execute(
            "CREATE TABLE records (collection TEXT NOT NULL, item_id TEXT NOT NULL, payload TEXT NOT NULL, position INTEGER, PRIMARY KEY (collection, item_id))"
        )

        def insert(collection: str, item_id: str, payload: dict[str, object]) -> None:
            connection.execute(
                "INSERT INTO records (collection, item_id, payload, position) VALUES (?, ?, ?, ?)",
                (collection, item_id, json.dumps(payload), 0),
            )

        insert("issuers", "issuer_real", {"issuer_id": "issuer_real", "legal_name": "Real Public Co"})
        insert("securities", "sec_real", {"security_id": "sec_real", "issuer_id": "issuer_real", "ticker": "REAL"})
        insert(
            "documents",
            "doc_real",
            {
                "document_id": "doc_real",
                "issuer_id": "issuer_real",
                "security_id": "sec_real",
                "source_id": "sec_edgar",
                "source_uri": "https://www.sec.gov/Archives/real.htm",
                "rights_tag": {"license_class": "public"},
            },
        )
        insert(
            "evidence",
            "ev_real",
            {"evidence_id": "ev_real", "document_id": "doc_real", "issuer_id": "issuer_real", "security_id": "sec_real"},
        )
        insert(
            "company_events",
            "event_real",
            {
                "event_id": "event_real",
                "issuer_id": "issuer_real",
                "security_id": "sec_real",
                "document_ids": ["doc_real"],
                "evidence_ids": ["ev_real"],
            },
        )
        insert("issuers", "issuer_demo", {"issuer_id": "issuer_demo", "legal_name": "Demo Corp"})
        insert("securities", "security_demo", {"security_id": "security_demo", "issuer_id": "issuer_demo", "ticker": "DEMO"})
        insert(
            "documents",
            "doc_demo",
            {
                "document_id": "doc_demo",
                "issuer_id": "issuer_demo",
                "security_id": "security_demo",
                "source_uri": "https://example.invalid/demo",
                "rights_tag": {"license_class": "public"},
            },
        )
        connection.commit()
        connection.close()
        before = state_db.read_bytes()

        report = build_density_capacity_audit([state_db])

        self.assertEqual(state_db.read_bytes(), before)
        self.assertFalse(report["data_writes_performed"])
        self.assertEqual(report["subject_count"], 2)
        self.assertEqual(report["governed_subject_count"], 1)
        by_issuer = {row["issuer_id"]: row for row in report["subjects"]}
        self.assertEqual(by_issuer["issuer_real"]["provenance_class"], "governed")
        self.assertEqual(by_issuer["issuer_demo"]["provenance_class"], "seed_fixture")
        self.assertEqual(by_issuer["issuer_real"]["governed_layer_coverage"]["covered"], 3)
        self.assertEqual(by_issuer["issuer_real"]["cross_links"]["document_evidence"]["ratio"], 1.0)
        self.assertEqual(by_issuer["issuer_real"]["cross_links"]["event_document"]["ratio"], 1.0)
        self.assertEqual(by_issuer["issuer_real"]["cross_links"]["event_evidence"]["ratio"], 1.0)
        self.assertEqual(renderer_recommendation(250, 500), "svg")
        self.assertEqual(renderer_recommendation(251, 500), "svg_virtualized")
        self.assertEqual(renderer_recommendation(751, 1500), "canvas")
        self.assertEqual(renderer_recommendation(3001, 6000), "webgl")
        self.assertFalse(report["renderer_decision"]["canvas_or_webgl_migration_approved"])

    def test_graph_traceability_store_module_matches_facade(self) -> None:
        self.service.store.documents["doc_traceability"] = Document(
            document_id="doc_traceability",
            issuer_id="issuer_001",
            security_id="sec_001",
            document_type="annual_report",
            source_id="src_sec",
            source_type="regulatory",
            source_uri="https://example.invalid/traceability",
            rights_tag=RightsTag("public"),
        )
        self.service.store.evidence["ev_traceability"] = Evidence(
            evidence_id="ev_traceability",
            document_id="doc_traceability",
            section="business",
            page_no=1,
            bbox="p1",
            span_text="Public evidence for traceability.",
            canonical_text="public evidence for traceability",
            confidence=0.95,
            issuer_id="issuer_001",
            security_id="sec_001",
        )
        self.service.store.theses["thesis_traceability"] = ThesisCard(
            thesis_id="thesis_traceability",
            issuer_id="issuer_001",
            horizon="mid",
            hypothesis="Traceable hypothesis",
            evidence_ids=["ev_traceability"],
        )
        self.service.store.theses["thesis_traceability_broken"] = ThesisCard(
            thesis_id="thesis_traceability_broken",
            issuer_id="issuer_other",
            horizon="mid",
            hypothesis="Untraceable hypothesis",
            evidence_ids=["ev_missing"],
        )
        self.service.store.signals["sig_traceability"] = ResearchSignal(
            signal_id="sig_traceability",
            thesis_id="thesis_traceability",
            signal_type="research",
            direction="positive",
            score=0.8,
            source_model="rules",
            model_version="v1",
        )
        self.service.store.decisions["dec_traceability"] = DecisionPack(
            decision_id="dec_traceability",
            signal_ids=["sig_traceability"],
            approval_state="approved",
        )
        self.service.store.research_answers["answer_traceability"] = ResearchAnswer(
            answer_id="answer_traceability",
            question="What supports the thesis?",
            issuer_id="issuer_001",
            evidence_ids=["ev_traceability"],
            source_document_ids=["doc_traceability"],
            english_source_text="Public evidence for traceability.",
        )
        reporting = GraphTraceabilityReporting(self.service.store)

        for filters in [
            {},
            {"issuer_id": "issuer_001"},
            {"issuer_id": "issuer_001", "include_details": "false"},
            {"limit": "1"},
        ]:
            with self.subTest(filters=filters):
                self.assertEqual(
                    self.service.graph_traceability_report(filters),
                    reporting.graph_traceability_report(filters),
                )

        issuer_report = reporting.graph_traceability_report({"issuer_id": "issuer_001"})
        self.assertEqual(issuer_report["traceability_rate"], 1.0)
        self.assertEqual(issuer_report["counts"]["theses"], 1)
        self.assertEqual(issuer_report["counts"]["decisions"], 1)
        self.assertEqual(issuer_report["counts"]["research_answers"], 1)
        self.assertEqual(reporting.graph_traceability_report({})["counts"]["untraceable_theses"], 1)

    def test_full_knowledge_graph_bulk_dry_run_does_not_write(self) -> None:
        result = self.service.backfill_full_knowledge_graph({"market": "A", "limit": 1, "batch_size": 1}, actor="test")

        self.assertEqual(result["status"], "dry_run")
        self.assertEqual(result["universe_count"], 1)
        self.assertEqual(result["processed_count"], 1)
        self.assertEqual(len(self.service.store.company_relationships), 0)
        self.assertEqual(len(self.service.store.company_positions), 0)
        item = result["items"][0]
        self.assertEqual(item["issuer_id"], "issuer_001")
        self.assertTrue(any(action["action"] == "create_listed_security_relationship" for action in item["actions"]))
        self.assertTrue(any(action["action"] == "create_company_position" for action in item["actions"]))

    def test_full_knowledge_graph_bulk_execute_is_idempotent(self) -> None:
        first = self.service.backfill_full_knowledge_graph({"market": "A", "limit": 1, "batch_size": 1, "execute": True}, actor="test")
        second = self.service.backfill_full_knowledge_graph({"market": "A", "limit": 1, "batch_size": 1, "execute": True}, actor="test")

        self.assertEqual(first["status"], "executed")
        self.assertEqual(second["status"], "executed")
        self.assertEqual(len(self.service.store.company_relationships), 1)
        self.assertEqual(len(self.service.store.company_positions), 1)
        relationship = next(iter(self.service.store.company_relationships.values()))
        self.assertEqual(relationship.relationship_type, "listed_security")
        self.assertEqual(relationship.review_status, "auto_generated")
        position = next(iter(self.service.store.company_positions.values()))
        self.assertEqual(position.data_quality, "needs_review")
        self.assertIn(second["items"][0]["status"], {"ready", "needs_data"})

    def test_query_graph_scopes_company_positions_to_focus_issuer(self) -> None:
        self.service.register_issuer({"issuer_id": "issuer_002", "legal_name": "Other Corp", "market": ["A"]}, actor="test")
        self.service.register_security(
            {"security_id": "sec_002", "issuer_id": "issuer_002", "ticker": "OTHR", "market": "A"},
            actor="test",
        )
        self.service.store.industry_chains["chain_scope"] = IndustryChain(
            chain_id="chain_scope",
            name="Scope Chain",
            nodes=[
                {"node_id": "focus_node", "name": "Focus"},
                {"node_id": "other_node", "name": "Other"},
            ],
        )
        self.service.store.company_positions["pos_focus_scope"] = CompanyPosition(
            position_id="pos_focus_scope",
            issuer_id="issuer_001",
            security_id="sec_001",
            chain_id="chain_scope",
            node_ids=["focus_node"],
        )
        self.service.store.company_positions["pos_other_scope"] = CompanyPosition(
            position_id="pos_other_scope",
            issuer_id="issuer_002",
            security_id="sec_002",
            chain_id="chain_scope",
            node_ids=["other_node"],
        )
        self.service.store.company_positions["pos_full_graph_peer_needs_review_scope"] = CompanyPosition(
            position_id="pos_full_graph_peer_needs_review_scope",
            issuer_id="issuer_002",
            security_id="sec_002",
            chain_id="chain_scope",
            node_ids=["focus_node"],
            role="生产 universe 基础产业定位",
            positioning_summary="OTHR production-universe graph position generated from security industry metadata.",
            data_quality="needs_review",
        )

        graph = self.service.query_graph({"issuer_id": "issuer_001", "security_id": "sec_001"})

        self.assertEqual({item["position_id"] for item in graph["company_positions"]}, {"pos_focus_scope"})
        self.assertEqual({item["node_id"] for item in graph["chain_nodes"]}, {"focus_node"})
        self.assertNotIn("pos_other_scope", {edge.get("from") for edge in graph["edges"]} | {edge.get("to") for edge in graph["edges"]})
        self.assertNotIn("pos_full_graph_peer_needs_review_scope", {item["position_id"] for item in graph["company_positions"]})

        peer_graph = self.service.query_graph({"issuer_id": "issuer_001", "security_id": "sec_001", "relationship_type": "industry_peer"})
        self.assertIn("pos_full_graph_peer_needs_review_scope", {item["position_id"] for item in peer_graph["company_positions"]})
        self.assertEqual({item["node_id"] for item in peer_graph["chain_nodes"]}, {"focus_node"})
        self.assertTrue(any(edge.get("relationship_type") == "industry_peer" for edge in peer_graph["edges"]))

    def test_full_knowledge_graph_universe_excludes_out_of_scope_and_reports_hk_gap(self) -> None:
        self.service.register_issuer({"issuer_id": "issuer_old", "legal_name": "Old Co", "market": ["A"]}, actor="test")
        self.service.register_security(
            {
                "security_id": "sec_old",
                "issuer_id": "issuer_old",
                "ticker": "OLD",
                "market": "A",
                "status": "active",
                "company_universe_scope": "out_of_scope",
            },
            actor="test",
        )
        result = self.service.backfill_full_knowledge_graph({"market": "A,HK", "limit": 10, "batch_size": 10, "audit_only": True}, actor="test")

        self.assertEqual(result["status"], "audit_only")
        self.assertEqual(result["universe_count"], 1)
        self.assertTrue(result["universe"]["hk_universe_missing"])
        self.assertEqual(result["items"][0]["issuer_id"], "issuer_001")

    def test_graph_quality_center_excludes_local_acceptance_fixture_securities(self) -> None:
        self.service.register_issuer({"issuer_id": "issuer_graph_aapl_downstream", "legal_name": "AAPL Graph Downstream Co", "market": ["U"]}, actor="test")
        self.service.register_security(
            {
                "security_id": "security_graph_aapl_downstream",
                "issuer_id": "issuer_graph_aapl_downstream",
                "ticker": "AAPL-D",
                "market": "U",
                "status": "active",
                "company_universe_scope": "out_of_scope",
                "company_universe_reason": "local_graph_acceptance_fixture_only",
            },
            actor="test",
        )

        result = self.service.graph_quality_center({"market": "A,U", "limit": 10}, actor="test")

        symbols = {item["symbol"] for item in result["items"]}
        self.assertIn("DEMO", symbols)
        self.assertNotIn("AAPL-D", symbols)
        self.assertEqual(result["universe"]["skipped_by_market"].get("U"), 1)

    def test_full_knowledge_graph_script_writes_artifacts(self) -> None:
        temp_dir = TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        output = Path(temp_dir.name) / "run.json"
        state = Path(temp_dir.name) / "state.json"
        previous_db = os.environ.get("AI_QUANT_DB")
        previous_pg = os.environ.get("AI_QUANT_POSTGRES_DSN")
        previous_db_url = os.environ.get("AI_QUANT_DATABASE_URL")
        db_path = Path(temp_dir.name) / "graph.sqlite"
        os.environ["AI_QUANT_POSTGRES_DSN"] = ""
        os.environ["AI_QUANT_DATABASE_URL"] = ""
        os.environ["AI_QUANT_DB"] = str(db_path)
        try:
            exit_code = backfill_full_knowledge_graph_script.main([
                "--audit-only",
                "--market",
                "A,U",
                "--limit",
                "0",
                "--batch-size",
                "2",
                "--output",
                str(output),
                "--resume-state",
                str(state),
            ])
        finally:
            if previous_db is None:
                os.environ.pop("AI_QUANT_DB", None)
            else:
                os.environ["AI_QUANT_DB"] = previous_db
            if previous_pg is not None:
                os.environ["AI_QUANT_POSTGRES_DSN"] = previous_pg
            else:
                os.environ.pop("AI_QUANT_POSTGRES_DSN", None)
            if previous_db_url is not None:
                os.environ["AI_QUANT_DATABASE_URL"] = previous_db_url
            else:
                os.environ.pop("AI_QUANT_DATABASE_URL", None)
        self.assertEqual(exit_code, 0)
        self.assertTrue(output.exists())
        self.assertTrue(state.exists())
        payload = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(payload["status"], "audit_only")
        self.assertIn("state_summary", payload)

    def test_graph_quality_center_reports_gaps_and_actions(self) -> None:
        result = self.router.dispatch(
            "POST",
            "/api/graph/quality-center",
            {"market": "A", "limit": 1, "min_edges": 1, "min_communities": 1, "min_layers": 9},
            actor="analyst",
            role="analyst",
        )

        self.assertTrue(result.success, result.error)
        self.assertEqual(result.data["schema_id"], "graph-quality-center-v1")
        self.assertEqual(result.data["processed_count"], 1)
        row = result.data["items"][0]
        self.assertEqual(row["symbol"], "DEMO")
        self.assertIn("document", row["readiness"]["missing_layers"])
        self.assertIn("quality_gate", row)
        action_names = {item["action"] for item in row["enhancement_actions"]}
        self.assertIn("build_company_events", action_names)
        self.assertIn("build_company_relationships", action_names)
        self.assertIn("ingest_source_documents", action_names)
        self.assertIn("extract_and_link_evidence", action_names)
        self.assertIn("structure_research_reports", action_names)
        remediation_actions = {item["action"]: item for item in row["quality_gate"]["remediation_actions"]}
        self.assertIn("preview_graph_source_input_queue", remediation_actions)
        self.assertEqual(remediation_actions["preview_graph_source_input_queue"]["endpoint"], "/api/graph/enrichment-runner")
        self.assertFalse(remediation_actions["preview_graph_source_input_queue"]["default_execute"])
        self.assertFalse(result.data["live_execution_allowed"])

    def test_graph_quality_center_actions_follow_remaining_missing_layers(self) -> None:
        self.router.dispatch("POST", "/api/company-events", {"event_id": "ce_graph_action", "issuer_id": "issuer_001", "security_id": "sec_001", "event_type": "market", "title": "Graph action event"}, role="analyst")
        relationship = self.router.dispatch(
            "POST",
            "/api/company-relationships",
            {
                "relationship_id": "rel_graph_action_listing",
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "subject_type": "company",
                "subject_id": "issuer_001",
                "object_type": "security",
                "object_id": "sec_001",
                "relationship_type": "listed_security",
                "relationship_status": "active",
                "review_status": "auto_generated",
            },
            role="analyst",
        )
        self.assertTrue(relationship.success, relationship.error)
        result = self.router.dispatch(
            "POST",
            "/api/graph/quality-center",
            {"market": "A", "limit": 1, "min_edges": 1, "min_communities": 1, "min_layers": 1},
            actor="analyst",
            role="analyst",
        )

        self.assertTrue(result.success, result.error)
        row = result.data["items"][0]
        action_names = {item["action"] for item in row["enhancement_actions"]}
        self.assertNotIn("build_company_events", action_names)
        self.assertNotIn("build_company_relationships", action_names)
        self.assertIn("import_13f_holdings", action_names)
        self.assertIn("ingest_source_documents", action_names)
        self.assertIn("extract_and_link_evidence", action_names)
        self.assertIn("structure_research_reports", action_names)
        self.assertIn("structure_or_register_viewpoints", action_names)
        self.assertTrue(
            all(item.get("usage_boundary") == "local_public_or_provided_data_only_no_broker_no_trade_execution" for item in row["enhancement_actions"])
        )

    def test_graph_source_actions_are_shared_by_quality_center_and_runner(self) -> None:
        from app.service_modules import graph_source_actions

        quality = self.service.graph_quality_center(
            {"market": "A", "limit": 1, "min_edges": 1, "min_communities": 1, "min_layers": 1},
            actor="test",
        )
        runner = self.service.graph_enrichment_runner(
            {
                "market": "A",
                "limit": 1,
                "batch_size": 1,
                "priority_layers": "document,evidence,shareholder_holding,research_report,viewpoint",
                "include_events": False,
                "include_relationships": False,
            },
            actor="test",
        )

        quality_by_layer = {item["layer"]: item for item in quality["items"][0]["enhancement_actions"]}
        runner_by_layer = {item["layer"]: item for item in runner["items"][0]["layer_action_plan"]}
        for layer in graph_source_actions.SOURCE_BACKED_LAYERS:
            self.assertEqual(quality_by_layer[layer]["action"], runner_by_layer[layer]["action"])
            self.assertEqual(quality_by_layer[layer]["endpoint"], runner_by_layer[layer]["endpoint"])
            self.assertEqual(
                quality_by_layer[layer]["required_source_fields"],
                graph_source_actions.REQUIRED_SOURCE_FIELDS[layer],
            )
            self.assertEqual(
                runner_by_layer[layer]["required_source_fields"],
                graph_source_actions.REQUIRED_SOURCE_FIELDS[layer],
            )

    def test_graph_quality_gate_remediation_routes_duplicate_edges_to_reconcile(self) -> None:
        duplicate_relationship = {
            "issuer_id": "issuer_001",
            "security_id": "sec_001",
            "subject_type": "company",
            "subject_id": "issuer_001",
            "object_type": "security",
            "object_id": "sec_001",
            "relationship_type": "listed_security",
            "relationship_status": "active",
            "review_status": "auto_generated",
        }
        for relationship_id in ["rel_quality_duplicate_listing_a", "rel_quality_duplicate_listing_b"]:
            response = self.router.dispatch(
                "POST",
                "/api/company-relationships",
                {"relationship_id": relationship_id, **duplicate_relationship},
                role="analyst",
            )
            self.assertTrue(response.success, response.error)

        result = self.service.graph_quality_center(
            {"market": "A", "limit": 1, "min_edges": 0, "min_communities": 1, "min_layers": 1},
            actor="test",
        )

        quality_gate = result["items"][0]["quality_gate"]
        self.assertIn("display_duplicate_edges", {failure["check"] for failure in quality_gate["failures"]})
        remediation_by_action = {item["action"]: item for item in quality_gate["remediation_actions"]}
        reconcile = remediation_by_action["preview_company_database_quality_reconcile"]
        self.assertEqual(reconcile["endpoint"], "/api/company-database/quality/reconcile")
        self.assertEqual(reconcile["payload"]["symbols"], ["DEMO"])
        self.assertFalse(reconcile["payload"]["merge_duplicates"])
        self.assertFalse(reconcile["default_execute"])

    def test_graph_quality_center_get_route_uses_query_thresholds(self) -> None:
        result = self.router.dispatch(
            "GET",
            "/api/graph/quality-center",
            {"market": "A", "limit": "1", "min_edges": "1", "min_communities": "1", "min_layers": "1", "max_duplicate_labels": "2", "max_raw_label_leaks": "3"},
            actor="analyst",
            role="analyst",
        )

        self.assertTrue(result.success, result.error)
        self.assertEqual(result.data["schema_id"], "graph-quality-center-v1")
        quality_gate = result.data["items"][0]["quality_gate"]
        self.assertEqual(quality_gate["thresholds"]["max_duplicate_labels"], 2)
        self.assertEqual(quality_gate["thresholds"]["max_raw_label_leaks"], 3)
        self.assertFalse(result.data["automation_allowed"])
        self.assertFalse(result.data["live_execution_allowed"])

    def test_graph_quality_center_thresholds_preserve_explicit_zero_values(self) -> None:
        result = self.router.dispatch(
            "GET",
            "/api/graph/quality-center",
            {
                "market": "A",
                "limit": "1",
                "min_edges": "0",
                "min_communities": "0",
                "min_layers": "0",
                "min_structural_nodes": "0",
                "max_duplicate_edges": "0",
                "max_duplicate_labels": "0",
                "max_raw_label_leaks": "0",
                "max_hub_edge_share": "0",
                "max_leaf_ratio": "0",
                "min_largest_component_ratio": "0",
                "max_community_node_share": "0",
            },
            actor="analyst",
            role="analyst",
        )

        self.assertTrue(result.success, result.error)
        thresholds = result.data["items"][0]["quality_gate"]["thresholds"]
        self.assertEqual(thresholds["min_edges"], 0)
        self.assertEqual(thresholds["min_communities"], 0)
        self.assertEqual(thresholds["min_layers"], 0)
        self.assertEqual(thresholds["min_structural_nodes"], 0)
        self.assertEqual(thresholds["max_duplicate_edges"], 0)
        self.assertEqual(thresholds["max_duplicate_labels"], 0)
        self.assertEqual(thresholds["max_raw_label_leaks"], 0)
        self.assertEqual(thresholds["max_hub_edge_share"], 0.0)
        self.assertEqual(thresholds["max_leaf_ratio"], 0.0)
        self.assertEqual(thresholds["min_largest_component_ratio"], 0.0)
        self.assertEqual(thresholds["max_community_node_share"], 0.0)

    def test_graph_quality_center_no_targets_is_not_passed(self) -> None:
        result = self.service.graph_quality_center({"market": "HK", "limit": 1}, actor="test")

        self.assertEqual(result["status"], "no_targets")
        self.assertEqual(result["processed_count"], 0)
        self.assertEqual(result["needs_attention_count"], 1)
        self.assertEqual(result["global_failures"][0]["check"], "target_universe")

    def test_graph_quality_center_does_not_flag_market_data_ids_as_raw_labels(self) -> None:
        self.service.register_market_data_point(
            {
                "data_id": "md_public_eod_market_data_sec_001_2026-06-29_eod",
                "security_id": "sec_001",
                "source_id": "public_eod_market_data",
                "market": "A",
                "as_of_date": "2026-06-29",
                "data_type": "eod",
                "open": 10.0,
                "high": 10.5,
                "low": 9.8,
                "close": 10.2,
                "volume": 1000,
            },
            actor="test",
        )

        result = self.service.graph_quality_center(
            {"market": "A", "limit": 1, "min_edges": 1, "min_communities": 1, "min_layers": 1, "max_raw_label_leaks": 0},
            actor="test",
        )

        leaks = result["items"][0]["quality_gate"]["raw_label_leaks"]
        self.assertNotIn("md_public_eod_market_data_sec_001_2026-06-29_eod", leaks)

    def test_graph_quality_center_cleans_generic_research_ids(self) -> None:
        from app.service_modules import graph_quality_center as graph_quality_center_module

        graph = {
            "structured_research_reports": [{"research_report_id": "srr_eb9bae6c61ec8eb6"}],
            "report_viewpoints": [{"viewpoint_id": "vp_rr_eb9bae6c61ec8eb6_main"}],
            "edges": [{"from": "srr_eb9bae6c61ec8eb6", "to": "vp_rr_eb9bae6c61ec8eb6_main", "type": "REPORT_HAS_VIEWPOINT"}],
        }
        readiness = {"visible_communities": ["research"], "present_layers": ["research_report", "viewpoint"]}

        snapshot = graph_quality_center_module._graph_quality_snapshot(
            graph,
            readiness,
            {"min_edges": 1, "min_communities": 1, "min_layers": 1, "max_raw_label_leaks": 0},
        )

        self.assertEqual(snapshot["raw_label_leaks"], [])
        self.assertEqual(snapshot["status"], "passed")

    def test_graph_quality_center_structure_links_structured_report_viewpoints(self) -> None:
        from app.service_modules import graph_quality_center as graph_quality_center_module

        graph = {
            "issuers": [{"issuer_id": "issuer_001", "ticker": "DEMO"}],
            "structured_research_reports": [
                {"research_report_id": "srr_demo_001", "issuer_id": "issuer_001", "title": "Demo report"}
            ],
            "report_viewpoints": [
                {"viewpoint_id": "vp_demo_001", "research_report_id": "srr_demo_001", "issuer_id": "issuer_001", "topic": "Growth"}
            ],
            "edges": [
                {"from": "issuer_001", "to": "srr_demo_001", "type": "COVERED_BY_REPORT"},
                {"from": "srr_demo_001", "to": "vp_demo_001", "type": "REPORT_HAS_VIEWPOINT"},
                {"from": "vp_demo_001", "to": "issuer_001", "type": "VIEWPOINT_ON_COMPANY"},
            ],
        }
        readiness = {
            "visible_communities": ["company", "research", "evidence"],
            "present_layers": ["company_profile", "industry_position", "company_relationship", "research_report", "viewpoint"],
        }

        snapshot = graph_quality_center_module._graph_quality_snapshot(
            graph,
            readiness,
            {"min_edges": 1, "min_communities": 1, "min_layers": 1, "max_hub_edge_share": 1.0, "max_leaf_ratio": 1.0},
        )

        self.assertEqual(snapshot["structure"]["node_count"], 3)
        self.assertEqual(snapshot["structure"]["valid_edge_count"], 3)
        self.assertIn(("REPORT_HAS_VIEWPOINT", 1), [tuple(item) for item in snapshot["structure"]["edge_type_counts"]])
        self.assertEqual(snapshot["status"], "passed")

    def test_graph_quality_center_uses_relationship_display_labels(self) -> None:
        from app.service_modules import graph_quality_center as graph_quality_center_module

        graph = {
            "issuers": [{"issuer_id": "issuer_001", "ticker": "DEMO"}],
            "securities": [{"security_id": "sec_001", "ticker": "DEMO", "issuer_id": "issuer_001"}],
            "company_relationships": [
                {
                    "relationship_id": "rel_listing_demo",
                    "issuer_id": "issuer_001",
                    "subject_id": "issuer_001",
                    "object_id": "sec_001",
                    "relationship_type": "listed_security",
                },
                {
                    "relationship_id": "rel_customer_candidate_demo",
                    "issuer_id": "issuer_001",
                    "subject_id": "issuer_001",
                    "object_id": "external_customer",
                    "relationship_type": "customer_candidate",
                },
            ],
            "edges": [
                {"from": "issuer_001", "to": "sec_001", "type": "HAS_COMPANY_RELATIONSHIP", "relationship_type": "listed_security"},
                {"from": "issuer_001", "to": "external_customer", "type": "HAS_COMPANY_RELATIONSHIP", "relationship_type": "customer_candidate"},
            ],
        }
        readiness = {
            "visible_communities": ["company", "relationship", "evidence"],
            "present_layers": ["company_profile", "industry_position", "company_relationship", "document", "evidence"],
        }

        snapshot = graph_quality_center_module._graph_quality_snapshot(
            graph,
            readiness,
            {"min_edges": 1, "min_communities": 1, "min_layers": 1, "max_raw_label_leaks": 0},
        )

        labels = {
            graph_quality_center_module._node_label("company_relationships", row)
            for row in graph["company_relationships"]
        }
        self.assertEqual(labels, {"上市证券", "客户候选"})
        self.assertEqual(snapshot["raw_label_leaks"], [])
        self.assertEqual(snapshot["status"], "passed")

    def test_graph_quality_center_structure_uses_direct_relationship_display_edges(self) -> None:
        from app.service_modules import graph_quality_center as graph_quality_center_module

        graph = {
            "issuers": [
                {"issuer_id": "issuer_001", "ticker": "DEMO"},
                {"issuer_id": "issuer_customer", "ticker": "CUST"},
            ],
            "company_relationships": [
                {
                    "relationship_id": "rel_customer_candidate_demo",
                    "issuer_id": "issuer_001",
                    "subject_id": "issuer_001",
                    "object_id": "issuer_customer",
                    "relationship_type": "customer_candidate",
                }
            ],
            "edges": [
                {"from": "issuer_001", "to": "rel_customer_candidate_demo", "type": "HAS_COMPANY_RELATIONSHIP", "relationship_type": "customer_candidate"},
                {"from": "rel_customer_candidate_demo", "to": "issuer_001", "type": "RELATIONSHIP_SUBJECT", "relationship_type": "customer_candidate"},
                {"from": "rel_customer_candidate_demo", "to": "issuer_customer", "type": "RELATIONSHIP_OBJECT", "relationship_type": "customer_candidate"},
            ],
        }
        readiness = {
            "visible_communities": ["company", "relationship", "evidence"],
            "present_layers": ["company_profile", "industry_position", "company_relationship", "document", "evidence"],
        }

        snapshot = graph_quality_center_module._graph_quality_snapshot(
            graph,
            readiness,
            {"min_edges": 1, "min_communities": 1, "min_layers": 1},
        )

        self.assertEqual(snapshot["structure"]["valid_edge_count"], 1)
        self.assertEqual(snapshot["structure"]["edge_type_counts"][0], ("customer_candidate", 1))
        self.assertEqual(snapshot["raw_structure"]["valid_edge_count"], 3)

    def test_graph_quality_center_default_gate_rejects_display_duplicate_edges(self) -> None:
        from app.service_modules import graph_quality_center as graph_quality_center_module

        graph = {
            "issuers": [
                {"issuer_id": "issuer_001", "ticker": "DEMO"},
                {"issuer_id": "issuer_customer", "ticker": "CUST"},
            ],
            "company_relationships": [
                {
                    "relationship_id": "rel_customer_1",
                    "issuer_id": "issuer_001",
                    "subject_id": "issuer_001",
                    "object_id": "issuer_customer",
                    "relationship_type": "customer_candidate",
                },
                {
                    "relationship_id": "rel_customer_2",
                    "issuer_id": "issuer_001",
                    "subject_id": "issuer_001",
                    "object_id": "issuer_customer",
                    "relationship_type": "customer_candidate",
                },
            ],
            "edges": [],
        }
        readiness = {
            "visible_communities": ["company", "relationship", "evidence"],
            "present_layers": ["company_profile", "industry_position", "company_relationship", "document", "evidence"],
        }

        strict_snapshot = graph_quality_center_module._graph_quality_snapshot(
            graph,
            readiness,
            {"min_edges": 0, "min_communities": 1, "min_layers": 1},
        )
        relaxed_snapshot = graph_quality_center_module._graph_quality_snapshot(
            graph,
            readiness,
            {"min_edges": 0, "min_communities": 1, "min_layers": 1, "max_display_duplicate_edges": 1},
        )

        self.assertEqual(strict_snapshot["thresholds"]["max_display_duplicate_edges"], 0)
        self.assertEqual(strict_snapshot["structure"]["duplicate_edge_count"], 1)
        self.assertEqual(strict_snapshot["status"], "needs_attention")
        self.assertIn("display_duplicate_edges", {failure["check"] for failure in strict_snapshot["failures"]})
        self.assertEqual(relaxed_snapshot["status"], "passed")

    def test_graph_quality_center_disambiguates_same_holder_labels(self) -> None:
        from app.service_modules import graph_quality_center as graph_quality_center_module

        graph = {
            "securities": [
                {"security_id": "security_aapl_us", "ticker": "AAPL", "market": "U"},
                {"security_id": "security_nvda_us", "ticker": "NVDA", "market": "U"},
            ],
            "institutional_holdings": [
                {
                    "holding_id": "hold_vanguard_aapl",
                    "issuer_id": "issuer_aapl",
                    "security_id": "security_aapl_us",
                    "filer_name": "Vanguard Group Inc.",
                    "filer_cik": "0000102909",
                    "report_period": "2026-03-31",
                },
                {
                    "holding_id": "hold_vanguard_nvda",
                    "issuer_id": "issuer_nvda",
                    "security_id": "security_nvda_us",
                    "filer_name": "Vanguard Group Inc.",
                    "filer_cik": "0000102909",
                    "report_period": "2026-03-31",
                },
            ],
            "edges": [
                {"from": "security_aapl_us", "to": "hold_vanguard_aapl", "type": "HAS_13F_HOLDING"},
                {"from": "security_nvda_us", "to": "hold_vanguard_nvda", "type": "HAS_13F_HOLDING"},
            ],
        }
        readiness = {
            "visible_communities": ["company", "portfolio", "relationship"],
            "present_layers": ["company_profile", "industry_position", "company_relationship", "shareholder_holding", "document"],
        }

        snapshot = graph_quality_center_module._graph_quality_snapshot(
            graph,
            readiness,
            {"min_edges": 1, "min_communities": 1, "min_layers": 1},
        )

        labels = [
            graph_quality_center_module._node_label("institutional_holdings", row)
            for row in graph["institutional_holdings"]
        ]
        self.assertEqual(len(set(labels)), 2)
        self.assertTrue(all(label.startswith("13F 持仓 · Vanguard Group Inc.") for label in labels))
        self.assertEqual(snapshot["duplicate_labels"], [])

    def test_graph_quality_center_disambiguates_issuer_and_security_labels(self) -> None:
        from app.service_modules import graph_quality_center as graph_quality_center_module

        graph = {
            "issuers": [{"issuer_id": "issuer_aapl", "legal_name": "Apple Inc.", "aliases": ["AAPL"]}],
            "securities": [{"security_id": "security_aapl_us", "issuer_id": "issuer_aapl", "ticker": "AAPL", "market": "U"}],
            "company_positions": [{"position_id": "pos_aapl", "issuer_id": "issuer_aapl", "security_id": "security_aapl_us"}],
            "report_viewpoints": [{"viewpoint_id": "vp_aapl", "issuer_id": "issuer_aapl", "security_id": "security_aapl_us"}],
            "edges": [{"from": "issuer_aapl", "to": "security_aapl_us", "type": "HAS_SECURITY"}],
        }
        readiness = {
            "visible_communities": ["company"],
            "present_layers": ["company_profile", "industry_position", "company_relationship"],
        }

        snapshot = graph_quality_center_module._graph_quality_snapshot(
            graph,
            readiness,
            {"min_edges": 1, "min_communities": 1, "min_layers": 1},
        )

        labels = [
            graph_quality_center_module._node_label("issuers", graph["issuers"][0]),
            graph_quality_center_module._node_label("securities", graph["securities"][0]),
        ]
        self.assertEqual(labels, ["AAPL · 公司", "AAPL · U"])
        self.assertEqual(snapshot["duplicate_labels"], [])

    def test_graph_quality_center_default_gate_rejects_any_duplicate_or_raw_label(self) -> None:
        from app.service_modules import graph_quality_center as graph_quality_center_module

        readiness = {
            "visible_communities": ["company", "relationship", "evidence"],
            "present_layers": ["company_profile", "industry_position", "company_relationship", "document", "evidence"],
        }
        duplicate_graph = {
            "issuers": [
                {"issuer_id": "issuer_dup_a", "ticker": "DUP"},
                {"issuer_id": "issuer_dup_b", "ticker": "DUP"},
            ],
            "edges": [{"from": "issuer_dup_a", "to": "issuer_dup_b", "type": "RELATED"}],
        }
        duplicate_snapshot = graph_quality_center_module._graph_quality_snapshot(
            duplicate_graph,
            readiness,
            {"min_edges": 1, "min_communities": 1, "min_layers": 1},
        )

        self.assertEqual(duplicate_snapshot["thresholds"]["max_duplicate_labels"], 0)
        self.assertEqual(duplicate_snapshot["status"], "needs_attention")
        self.assertIn("duplicate_labels", {failure["check"] for failure in duplicate_snapshot["failures"]})

        raw_label_graph = {
            "documents": [{"document_id": "doc_raw_without_semantic_name", "label": "relationship_raw_without_semantic_name"}],
            "edges": [{"from": "doc_raw_without_semantic_name", "to": "issuer_demo", "type": "DOCUMENT_FOR"}],
        }
        raw_label_snapshot = graph_quality_center_module._graph_quality_snapshot(
            raw_label_graph,
            readiness,
            {"min_edges": 1, "min_communities": 1, "min_layers": 1},
        )

        self.assertEqual(raw_label_snapshot["thresholds"]["max_raw_label_leaks"], 0)
        self.assertEqual(raw_label_snapshot["status"], "needs_attention")
        self.assertIn("raw_label_leaks", {failure["check"] for failure in raw_label_snapshot["failures"]})

    def test_graph_quality_center_flags_star_shaped_graphs(self) -> None:
        from app.service_modules import graph_quality_center as graph_quality_center_module

        leaves = [{"entity_id": f"leaf_{index}", "label": f"节点 {index}"} for index in range(10)]
        graph = {
            "issuers": [{"issuer_id": "issuer_star", "ticker": "STAR"}],
            "company_relationships": leaves,
            "edges": [{"from": "issuer_star", "to": f"leaf_{index}", "type": "RELATED"} for index in range(10)],
        }
        readiness = {
            "visible_communities": ["company", "relationship", "evidence"],
            "present_layers": ["company_profile", "company_relationship", "document", "evidence", "company_event"],
        }

        snapshot = graph_quality_center_module._graph_quality_snapshot(
            graph,
            readiness,
            {"min_edges": 1, "min_communities": 1, "min_layers": 1, "max_hub_edge_share": 0.7, "max_leaf_ratio": 0.8},
        )

        failure_checks = {failure["check"] for failure in snapshot["failures"]}
        self.assertEqual(snapshot["status"], "needs_attention")
        self.assertIn("hub_dominance", failure_checks)
        self.assertIn("leaf_ratio", failure_checks)
        self.assertGreater(snapshot["structure"]["hub_edge_share"], 0.7)

    def test_graph_quality_center_flags_community_imbalance(self) -> None:
        from app.service_modules import graph_quality_center as graph_quality_center_module

        graph = {
            "issuers": [{"issuer_id": f"issuer_{index}", "ticker": f"C{index}"} for index in range(9)],
            "chain_nodes": [{"chain_id": "chain_demo", "node_id": "industry", "name": "Industry"}],
            "structured_research_reports": [{"research_report_id": "srr_demo", "title": "Demo research"}],
            "company_events": [{"event_id": "event_demo", "title": "Demo event"}],
            "edges": [{"from": "issuer_0", "to": f"issuer_{index}", "type": "RELATED"} for index in range(1, 9)]
            + [
                {"from": "issuer_0", "to": "chain_demo:industry", "type": "POSITION_IN_CHAIN_NODE"},
                {"from": "issuer_0", "to": "srr_demo", "type": "COVERED_BY_REPORT"},
                {"from": "issuer_0", "to": "event_demo", "type": "HAS_COMPANY_EVENT"},
            ],
        }
        readiness = {
            "visible_communities": ["company", "industry", "research", "evidence"],
            "present_layers": ["company_profile", "industry_position", "company_relationship", "document", "evidence"],
        }

        snapshot = graph_quality_center_module._graph_quality_snapshot(
            graph,
            readiness,
            {
                "min_edges": 1,
                "min_communities": 3,
                "min_layers": 1,
                "max_hub_edge_share": 1.0,
                "max_leaf_ratio": 1.0,
                "max_community_node_share": 0.7,
            },
        )

        failure_checks = {failure["check"] for failure in snapshot["failures"]}
        self.assertEqual(snapshot["status"], "needs_attention")
        self.assertIn("community_balance", failure_checks)
        self.assertGreater(snapshot["structure"]["max_community_node_share"], 0.7)
        self.assertIn(("company", 9), [tuple(item) for item in snapshot["structure"]["community_counts"]])

    def test_graph_quality_center_structure_uses_display_market_data_model(self) -> None:
        from app.service_modules import graph_quality_center as graph_quality_center_module

        market_rows = [
            {
                "data_id": f"md_public_eod_market_data_sec_001_2026-06-{day:02d}_eod",
                "security_id": "sec_001",
                "as_of_date": f"2026-06-{day:02d}",
            }
            for day in range(1, 11)
        ]
        graph = {
            "issuers": [{"issuer_id": "issuer_001", "ticker": "DEMO"}],
            "securities": [{"security_id": "sec_001", "ticker": "DEMO", "issuer_id": "issuer_001"}],
            "market_data": market_rows,
            "edges": [{"from": "issuer_001", "to": "sec_001", "type": "ISSUES"}]
            + [{"from": "sec_001", "to": row["data_id"], "type": "HAS_MARKET_DATA"} for row in market_rows],
        }
        readiness = {
            "visible_communities": ["company", "market", "evidence"],
            "present_layers": ["company_profile", "industry_position", "company_relationship", "document", "evidence"],
        }

        snapshot = graph_quality_center_module._graph_quality_snapshot(
            graph,
            readiness,
            {"min_edges": 1, "min_communities": 1, "min_layers": 1, "max_hub_edge_share": 0.72, "max_leaf_ratio": 0.86},
        )

        failure_checks = {failure["check"] for failure in snapshot["failures"]}
        self.assertNotIn("hub_dominance", failure_checks)
        self.assertNotIn("leaf_ratio", failure_checks)
        self.assertEqual(snapshot["structure"]["valid_edge_count"], 2)
        self.assertEqual(snapshot["structure"]["duplicate_edge_count"], 0)
        self.assertEqual(snapshot["raw_structure"]["valid_edge_count"], 11)

    def test_graph_quality_center_structure_uses_canonical_chain_node_ids(self) -> None:
        from app.service_modules import graph_quality_center as graph_quality_center_module

        graph = {
            "issuers": [{"issuer_id": "issuer_001", "ticker": "DEMO"}],
            "industry_chains": [{"chain_id": "chain_scope", "name": "Scope Chain"}],
            "chain_nodes": [{"chain_id": "chain_scope", "node_id": "focus_node", "name": "Focus"}],
            "company_positions": [
                {
                    "position_id": "pos_focus_scope",
                    "issuer_id": "issuer_001",
                    "chain_id": "chain_scope",
                    "node_ids": ["focus_node"],
                }
            ],
            "edges": [
                {"from": "chain_scope", "to": "chain_scope:focus_node", "type": "HAS_CHAIN_NODE"},
                {"from": "pos_focus_scope", "to": "chain_scope:focus_node", "type": "POSITION_IN_CHAIN_NODE"},
            ],
        }
        readiness = {
            "visible_communities": ["company", "industry", "evidence"],
            "present_layers": ["company_profile", "industry_position", "company_relationship", "document", "evidence"],
        }

        snapshot = graph_quality_center_module._graph_quality_snapshot(
            graph,
            readiness,
            {"min_edges": 1, "min_communities": 1, "min_layers": 1, "max_hub_edge_share": 1.0, "max_leaf_ratio": 1.0},
        )

        self.assertEqual(snapshot["structure"]["valid_edge_count"], 2)
        self.assertEqual(snapshot["structure"]["node_count"], 4)
        self.assertEqual(snapshot["structure"]["component_count"], 2)
        self.assertEqual(snapshot["raw_structure"]["node_count"], 4)

    def test_graph_quality_center_enrichment_dry_run_does_not_write(self) -> None:
        self.service.store.evidence["ev_graph_quality"] = Evidence(
            evidence_id="ev_graph_quality",
            document_id="doc_graph_quality",
            section="official_disclosure",
            page_no=1,
            bbox="p1",
            span_text="The company reported customer Mega Cloud and supplier Wafer Co.",
            canonical_text="customer Mega Cloud supplier Wafer Co",
            confidence=0.9,
            issuer_id="issuer_001",
            security_id="sec_001",
        )
        self.service.store.disclosure_events["de_graph_quality"] = DisclosureEvent(
            event_id="de_graph_quality",
            document_id="doc_graph_quality",
            issuer_id="issuer_001",
            security_id="sec_001",
            event_type="annual_report",
            item_code="10-K",
            item_title="Annual report relationship disclosure",
            severity="medium",
            summary="The company reported customer Mega Cloud and supplier Wafer Co.",
            evidence_ids=["ev_graph_quality"],
            source_id="src_sec",
        )

        result = self.service.graph_quality_center(
            {"market": "A", "limit": 1, "run_enrichment": True, "execute": False},
            actor="test",
        )

        self.assertTrue(result["run_enrichment"])
        self.assertTrue(result["enrichment_runs"])
        self.assertTrue(all(item["status"] == "dry_run" for item in result["enrichment_runs"]))
        self.assertFalse(self.service.store.company_events)
        self.assertFalse(self.service.store.company_relationships)

    def test_graph_quality_center_script_writes_artifact(self) -> None:
        captured_payloads: list[dict[str, object]] = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(handler_self):  # noqa: N802
                length = int(handler_self.headers.get("Content-Length", "0"))
                captured_payloads.append(json.loads(handler_self.rfile.read(length).decode("utf-8")))
                payload = {
                    "success": True,
                    "trace_id": "trace_graph_quality",
                    "data": {
                        "schema_id": "graph-quality-center-v1",
                        "status": "passed",
                        "processed_count": 1,
                        "items": [{"symbol": "DEMO"}],
                        "live_execution_allowed": False,
                    },
                }
                body = json.dumps(payload).encode("utf-8")
                handler_self.send_response(200)
                handler_self.send_header("Content-Type", "application/json")
                handler_self.send_header("Content-Length", str(len(body)))
                handler_self.end_headers()
                handler_self.wfile.write(body)

            def log_message(self, format, *args):  # noqa: A003
                return

        temp_dir = TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        output = Path(temp_dir.name) / "quality.json"
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.shutdown)
        self.addCleanup(server.server_close)

        result = graph_quality_center_script.run_graph_quality_center(
            f"http://127.0.0.1:{server.server_port}",
            output=output,
            markets="A",
            limit=1,
            timeout=5,
            max_duplicate_labels=2,
            max_raw_label_leaks=3,
            max_community_node_share=0.91,
        )

        self.assertEqual(result["schema_id"], "graph-quality-center-v1")
        self.assertTrue(output.exists())
        self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["processed_count"], 1)
        self.assertEqual(captured_payloads[0]["max_duplicate_labels"], 2)
        self.assertEqual(captured_payloads[0]["max_raw_label_leaks"], 3)
        self.assertEqual(captured_payloads[0]["max_community_node_share"], 0.91)

    def test_graph_quality_center_api_contract_documents_strict_display_gate(self) -> None:
        api_contracts = Path("docs/api-contracts.md").read_text(encoding="utf-8")

        for fragment in [
            "GET|POST /api/graph/quality-center",
            "graph-quality-center-v1",
            "max_duplicate_labels",
            "max_raw_label_leaks",
            "max_display_duplicate_edges",
            "默认 `0`",
            "max_duplicate_edges",
            "默认 `4`",
            "max_community_node_share",
            "community_balance",
            "community_counts",
            "quality_gate",
            "remediation_actions",
            "/api/graph/enrichment-runner",
            "/api/company-database/quality/reconcile",
            "structure",
            "raw_structure",
            "automation_allowed=false",
            "live_execution_allowed=false",
            "usage_boundary",
        ]:
            self.assertIn(fragment, api_contracts)

    def _add_graph_enrichment_fixture(self) -> None:
        self.service.store.evidence["ev_graph_enrich"] = Evidence(
            evidence_id="ev_graph_enrich",
            document_id="doc_graph_enrich",
            section="official_disclosure",
            page_no=1,
            bbox="p1",
            span_text="Revenue increased. The company reported customer Mega Cloud and supplier Wafer Co.",
            canonical_text="revenue increased customer Mega Cloud supplier Wafer Co",
            confidence=0.9,
            issuer_id="issuer_001",
            security_id="sec_001",
        )
        self.service.store.disclosure_events["de_graph_enrich"] = DisclosureEvent(
            event_id="de_graph_enrich",
            document_id="doc_graph_enrich",
            issuer_id="issuer_001",
            security_id="sec_001",
            event_type="annual_report",
            item_code="10-K",
            item_title="Annual report operating and relationship disclosure",
            severity="medium",
            summary="Revenue increased. The company reported customer Mega Cloud and supplier Wafer Co.",
            evidence_ids=["ev_graph_enrich"],
            source_id="src_sec",
        )

    def test_graph_enrichment_runner_dry_run_plans_candidates(self) -> None:
        self._add_graph_enrichment_fixture()

        result = self.service.graph_enrichment_runner(
            {
                "market": "A",
                "limit": 1,
                "batch_size": 1,
                "priority_layers": "company_event,company_relationship",
            },
            actor="test",
        )

        self.assertEqual(result["schema_id"], "graph-enrichment-runner-v1")
        self.assertEqual(result["status"], "dry_run")
        self.assertEqual(result["processed_count"], 1)
        row = result["items"][0]
        self.assertEqual(row["event_result"]["events_planned"], 2)
        self.assertGreaterEqual(row["relationship_result"]["relationships_planned"], 3)
        self.assertFalse(self.service.store.company_events)
        self.assertFalse(self.service.store.company_relationships)

    def test_graph_enrichment_runner_execute_writes_review_gated_candidates(self) -> None:
        self._add_graph_enrichment_fixture()

        result = self.service.graph_enrichment_runner(
            {
                "market": "A",
                "limit": 1,
                "batch_size": 1,
                "priority_layers": "company_event,company_relationship",
                "execute": True,
            },
            actor="test",
        )

        self.assertEqual(result["status"], "executed")
        self.assertGreaterEqual(result["event_totals"]["created"], 2)
        self.assertGreaterEqual(result["relationship_totals"]["created"], 3)
        relationship_types = {item.relationship_type for item in self.service.store.company_relationships.values()}
        self.assertIn("customer_candidate", relationship_types)
        self.assertIn("supplier_candidate", relationship_types)
        customer = next(item for item in self.service.store.company_relationships.values() if item.relationship_type == "customer_candidate")
        self.assertEqual(customer.review_status, "needs_review")
        self.assertEqual(customer.relationship_status, "unknown")
        detailed_events = [item for item in self.service.store.company_events.values() if item.event_type == "earnings_result"]
        self.assertTrue(detailed_events)
        self.assertEqual(detailed_events[0].review_status, "needs_review")

    def test_graph_enrichment_runner_respects_skip_issuer_ids(self) -> None:
        self._add_graph_enrichment_fixture()

        result = self.service.graph_enrichment_runner(
            {
                "market": "A",
                "limit": 1,
                "batch_size": 1,
                "skip_issuer_ids": ["issuer_001"],
            },
            actor="test",
        )

        self.assertEqual(result["processed_count"], 0)
        self.assertEqual(result["resume_skipped_count"], 1)
        self.assertEqual(result["skipped_items"][0]["reason"], "resume_completed")
        self.assertFalse(self.service.store.company_events)
        self.assertFalse(self.service.store.company_relationships)

    def test_graph_enrichment_runner_no_targets_is_not_success(self) -> None:
        result = self.service.graph_enrichment_runner({"market": "HK", "limit": 1}, actor="test")

        self.assertEqual(result["status"], "no_targets")
        self.assertEqual(result["processed_count"], 0)
        self.assertEqual(result["global_failures"][0]["check"], "target_universe")

    def test_graph_enrichment_runner_marks_no_candidate_sources(self) -> None:
        result = self.service.graph_enrichment_runner(
            {
                "market": "A",
                "limit": 1,
                "batch_size": 1,
                "priority_layers": "company_event",
                "include_relationships": False,
                "include_market_data": False,
                "include_research_coverage": False,
                "include_disclosures": False,
            },
            actor="test",
        )

        self.assertEqual(result["status"], "dry_run")
        self.assertEqual(result["processed_count"], 1)
        row = result["items"][0]
        self.assertEqual(row["status"], "no_candidate_sources")
        self.assertEqual(row["candidate_activity"]["events_planned"], 0)
        self.assertIn("补充公告", row["next_action"])

    def test_graph_enrichment_runner_skips_relationship_builder_when_layer_present(self) -> None:
        self.service.store.company_relationships["rel_listing_demo"] = CompanyRelationship(
            relationship_id="rel_listing_demo",
            issuer_id="issuer_001",
            security_id="sec_001",
            subject_type="company",
            subject_id="issuer_001",
            object_type="security",
            object_id="sec_001",
            relationship_type="listed_security",
            confidence=0.95,
            relationship_status="active",
            review_status="auto_generated",
        )

        result = self.service.graph_enrichment_runner(
            {
                "market": "A",
                "limit": 1,
                "batch_size": 1,
                "priority_layers": "company_event,company_relationship",
                "include_events": False,
                "include_relationships": True,
            },
            actor="test",
        )

        row = result["items"][0]
        self.assertEqual(row["relationship_result"]["status"], "skipped_no_company_relationship_gap")
        self.assertEqual(row["candidate_activity"]["relationships_planned"], 0)
        self.assertEqual(row["status"], "no_candidate_sources")

    def test_graph_enrichment_runner_plans_manual_input_layers(self) -> None:
        result = self.service.graph_enrichment_runner(
            {
                "market": "A",
                "limit": 1,
                "batch_size": 1,
                "priority_layers": "document,evidence,shareholder_holding,research_report,viewpoint",
                "include_events": False,
                "include_relationships": False,
            },
            actor="test",
        )

        self.assertEqual(result["status"], "dry_run")
        self.assertEqual(result["processed_count"], 1)
        self.assertEqual(result["manual_input_required_count"], 1)
        self.assertEqual(
            set(result["manual_input_required_layers"]),
            {"document", "evidence", "research_report", "shareholder_holding", "viewpoint"},
        )
        self.assertEqual(result["source_input_queue"]["schema_id"], "graph-source-input-queue-v1")
        self.assertEqual(result["source_input_queue"]["status"], "needs_source_inputs")
        self.assertEqual(result["source_input_queue"]["layer_count"], 5)
        self.assertEqual(result["source_input_queue"]["target_count"], 5)
        self.assertEqual(result["source_input_queue"]["unique_target_count"], 1)
        queue_by_layer = {item["layer"]: item for item in result["source_input_queue"]["layers"]}
        self.assertEqual(queue_by_layer["document"]["target_count"], 1)
        self.assertEqual(queue_by_layer["document"]["targets"][0]["issuer_id"], "issuer_001")
        document_action = next(item for item in result["items"][0]["layer_action_plan"] if item["layer"] == "document")
        self.assertIn("source URI or local path", document_action["required_source_fields"])
        self.assertIn("source URI or local path", queue_by_layer["document"]["required_source_fields"])
        self.assertEqual(queue_by_layer["shareholder_holding"]["endpoint"], "/api/13f/filings/parse")
        self.assertEqual(
            result["source_input_queue"]["usage_boundary"],
            "local_public_or_provided_source_input_queue_no_auto_fact_promotion_no_broker_no_trade_execution",
        )
        row = result["items"][0]
        self.assertEqual(row["status"], "waiting_for_source_inputs")
        self.assertEqual(
            set(row["manual_input_required_layers"]),
            {"document", "evidence", "research_report", "shareholder_holding", "viewpoint"},
        )
        action_names = {item["action"] for item in row["layer_action_plan"]}
        self.assertIn("ingest_source_documents", action_names)
        self.assertIn("extract_and_link_evidence", action_names)
        self.assertIn("import_13f_holdings", action_names)
        self.assertIn("structure_research_reports", action_names)
        self.assertIn("structure_or_register_viewpoints", action_names)
        self.assertTrue(all(item["required_source_fields"] for item in row["layer_action_plan"]))
        self.assertFalse(any(item["action"] == "build_company_events" for item in row["layer_action_plan"]))
        self.assertFalse(any(item["action"] == "build_company_relationships" for item in row["layer_action_plan"]))

    def test_graph_enrichment_runner_script_dry_run_does_not_mark_completed_state(self) -> None:
        class Handler(BaseHTTPRequestHandler):
            def do_POST(handler_self):  # noqa: N802
                length = int(handler_self.headers.get("Content-Length", "0"))
                json.loads(handler_self.rfile.read(length).decode("utf-8"))
                payload = {
                    "success": True,
                    "trace_id": "trace_graph_enrichment",
                    "data": {
                        "schema_id": "graph-enrichment-runner-v1",
                        "status": "dry_run",
                        "processed_count": 1,
                        "failed_count": 0,
                        "items": [{"issuer_id": "issuer_001", "status": "dry_run"}],
                    },
                }
                body = json.dumps(payload).encode("utf-8")
                handler_self.send_response(200)
                handler_self.send_header("Content-Type", "application/json")
                handler_self.send_header("Content-Length", str(len(body)))
                handler_self.end_headers()
                handler_self.wfile.write(body)

            def log_message(self, format, *args):  # noqa: A003
                return

        temp_dir = TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        output = Path(temp_dir.name) / "enrichment.json"
        state = Path(temp_dir.name) / "state.json"
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.shutdown)
        self.addCleanup(server.server_close)

        result = graph_enrichment_runner_script.run_graph_enrichment_runner(
            f"http://127.0.0.1:{server.server_port}",
            output=output,
            markets="A",
            limit=1,
            batch_size=1,
            resume_state=state,
            timeout=5,
        )

        self.assertEqual(result["schema_id"], "graph-enrichment-runner-v1")
        self.assertTrue(output.exists())
        self.assertTrue(state.exists())
        state_payload = json.loads(state.read_text(encoding="utf-8"))
        self.assertEqual(state_payload["completed_issuer_ids"], [])
        self.assertEqual(state_payload["dry_run_items_not_completed"], 1)

    def test_graph_enrichment_runner_script_execute_marks_completed_state(self) -> None:
        class Handler(BaseHTTPRequestHandler):
            def do_POST(handler_self):  # noqa: N802
                length = int(handler_self.headers.get("Content-Length", "0"))
                json.loads(handler_self.rfile.read(length).decode("utf-8"))
                payload = {
                    "success": True,
                    "trace_id": "trace_graph_enrichment_execute",
                    "data": {
                        "schema_id": "graph-enrichment-runner-v1",
                        "status": "executed",
                        "execute": True,
                        "processed_count": 1,
                        "failed_count": 0,
                        "items": [{"issuer_id": "issuer_001", "status": "executed"}],
                    },
                }
                body = json.dumps(payload).encode("utf-8")
                handler_self.send_response(200)
                handler_self.send_header("Content-Type", "application/json")
                handler_self.send_header("Content-Length", str(len(body)))
                handler_self.end_headers()
                handler_self.wfile.write(body)

            def log_message(self, format, *args):  # noqa: A003
                return

        temp_dir = TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        output = Path(temp_dir.name) / "enrichment-execute.json"
        state = Path(temp_dir.name) / "state.json"
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.shutdown)
        self.addCleanup(server.server_close)

        result = graph_enrichment_runner_script.run_graph_enrichment_runner(
            f"http://127.0.0.1:{server.server_port}",
            output=output,
            markets="A",
            limit=1,
            batch_size=1,
            resume_state=state,
            execute=True,
            timeout=5,
        )

        self.assertEqual(result["schema_id"], "graph-enrichment-runner-v1")
        state_payload = json.loads(state.read_text(encoding="utf-8"))
        self.assertEqual(state_payload["completed_issuer_ids"], ["issuer_001"])
        self.assertEqual(state_payload["dry_run_items_not_completed"], 0)

    def test_graph_enrichment_runner_script_execute_does_not_complete_no_candidate_sources(self) -> None:
        class Handler(BaseHTTPRequestHandler):
            def do_POST(handler_self):  # noqa: N802
                length = int(handler_self.headers.get("Content-Length", "0"))
                json.loads(handler_self.rfile.read(length).decode("utf-8"))
                payload = {
                    "success": True,
                    "trace_id": "trace_graph_enrichment_no_sources",
                    "data": {
                        "schema_id": "graph-enrichment-runner-v1",
                        "status": "executed",
                        "execute": True,
                        "processed_count": 1,
                        "failed_count": 0,
                        "items": [{"issuer_id": "issuer_001", "status": "no_candidate_sources"}],
                    },
                }
                body = json.dumps(payload).encode("utf-8")
                handler_self.send_response(200)
                handler_self.send_header("Content-Type", "application/json")
                handler_self.send_header("Content-Length", str(len(body)))
                handler_self.end_headers()
                handler_self.wfile.write(body)

            def log_message(self, format, *args):  # noqa: A003
                return

        temp_dir = TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        output = Path(temp_dir.name) / "enrichment-no-sources.json"
        state = Path(temp_dir.name) / "state.json"
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.shutdown)
        self.addCleanup(server.server_close)

        result = graph_enrichment_runner_script.run_graph_enrichment_runner(
            f"http://127.0.0.1:{server.server_port}",
            output=output,
            markets="A",
            limit=1,
            batch_size=1,
            resume_state=state,
            execute=True,
            timeout=5,
        )

        self.assertEqual(result["schema_id"], "graph-enrichment-runner-v1")
        state_payload = json.loads(state.read_text(encoding="utf-8"))
        self.assertEqual(state_payload["completed_issuer_ids"], [])
        self.assertEqual(state_payload["dry_run_items_not_completed"], 1)
