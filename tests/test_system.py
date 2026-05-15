from __future__ import annotations

from pathlib import Path
from http.server import ThreadingHTTPServer
from tempfile import TemporaryDirectory
import hashlib
import json
import os
import sqlite3
import struct
import threading
import unittest
import zipfile
import zlib

from app.api import ApiRouter
import app.services as services_module
from app.connectors import AShareConnector, ConnectorDocument
from app.document_parser import PaddleOCRParser
from app.errors import ConflictError, PermissionDenied
from app.llm_gateway import LLMGateway
from app.models import AlertNotification, SystemAlert
from app.object_store import LocalObjectStore, S3CompatibleObjectStore
from app.search import OpenSearchIndex, SearchRecord
from app.services import SystemService
from app.store import PostgreSQLStore, SQLiteStore
from app.tdx_market_data import TDXMarketDataAdapter, TDXVipdocAdapter
from scripts.capacity_baseline import run_capacity_baseline
from scripts.download_tdx_vipdoc import download_tdx_vipdoc_archive
from scripts.full_run_acceptance import run_full_acceptance
from scripts.import_tdx_market_data import run_tdx_incremental_import
from scripts.migrate_sqlite_to_postgres import migrate_sqlite_to_postgres
from scripts.postgres_schema_migrate import BASELINE_VERSION, apply_postgres_schema, mark_last_migration_rolled_back
from scripts.security_check import scan_repository
from scripts.staging_acceptance import run_staging_acceptance
from scripts.ui_static_check import validate_ui_html


class _FakePostgresCursor:
    def __init__(self, database):
        self.database = database
        self._rows = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return None

    def execute(self, sql, params=None):
        normalized = " ".join(sql.split()).lower()
        self.database.statements.append(sql)
        if normalized.startswith("select collection"):
            rows = []
            for (collection, item_id), record in self.database.records.items():
                rows.append((collection, item_id, record["payload"], record["position"]))
            self._rows = sorted(rows, key=lambda item: (item[0], item[3] is None, item[3] or 0, item[1]))
        elif normalized.startswith("select payload from ai_quant.audit_log"):
            audit_rows = sorted(self.database.audit.values(), key=lambda item: (item["timestamp"], item["event_id"]))
            self._rows = [(item["payload"],) for item in audit_rows]
        elif normalized.startswith("delete from ai_quant.records"):
            self.database.records.clear()
            self._rows = []
        elif normalized.startswith("delete from ai_quant.audit_log"):
            self.database.audit.clear()
            self._rows = []
        elif normalized.startswith("insert into ai_quant.records"):
            collection, item_id, payload, position = params
            self.database.records[(collection, item_id)] = {
                "payload": json.loads(payload),
                "position": position,
            }
            self._rows = []
        elif normalized.startswith("insert into ai_quant.audit_log"):
            self.database.audit[params[0]] = {
                "event_id": params[0],
                "payload": json.loads(params[11]),
                "timestamp": params[12],
            }
            self._rows = []
        else:
            if "create schema if not exists ai_quant" in normalized:
                self.database.schema_runs += 1
            self._rows = []

    def fetchall(self):
        return list(self._rows)


class _FakePostgresConnection:
    def __init__(self, database):
        self.database = database
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return None

    def cursor(self):
        return _FakePostgresCursor(self.database)

    def close(self):
        self.closed = True


class _FakePostgresDatabase:
    def __init__(self):
        self.records = {}
        self.audit = {}
        self.statements = []
        self.schema_runs = 0
        self.dsns = []

    def connect(self, dsn):
        self.dsns.append(dsn)
        return _FakePostgresConnection(self)


class SystemServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = SystemService()
        self.service.document_parser = PaddleOCRParser(token="")
        self.router = ApiRouter(self.service)
        self.service.register_source(
            {
                "source_id": "src_sec",
                "source_type": "regulatory",
                "allowed_document_types": ["annual_report", "10-K", "10-Q", "8-K", "20-F", "6-K"],
                "rights_tag": {
                    "license_class": "public",
                    "training_allowed": False,
                    "redistribution_allowed": False,
                    "display_use": "allowed",
                    "non_display_use": "restricted",
                    "derived_data_use": "restricted",
                },
            },
            actor="risk",
        )
        self.service.register_issuer(
            {
                "issuer_id": "issuer_001",
                "legal_name": "Demo Corp",
                "market": ["A", "U"],
                "lei": "LEI-DEMO-001",
                "cik": "0000001",
                "country": "CN",
            },
            actor="platform",
        )
        self.service.register_security(
            {
                "security_id": "sec_001",
                "issuer_id": "issuer_001",
                "ticker": "DEMO",
                "figi": "FIGI-DEMO-001",
                "isin": "ISIN-DEMO-001",
                "exchange": "SSE",
                "currency": "CNY",
                "market": "A",
            },
            actor="platform",
        )

    def test_ingest_extract_score_and_decision_flow(self) -> None:
        doc = self.service.ingest_document(
            {
                "document_id": "doc_001",
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "source_id": "src_sec",
                "source_type": "regulatory",
                "document_type": "annual_report",
                "source_uri": "https://example.invalid/doc-001",
                "body": "First paragraph. It contains revenue growth.\n\nSecond paragraph. It contains risk factors.",
                "rights_tag": {
                    "license_class": "public",
                    "training_allowed": False,
                    "redistribution_allowed": False,
                    "display_use": "allowed",
                    "non_display_use": "restricted",
                    "derived_data_use": "restricted",
                },
            },
            actor="data",
        )
        self.assertTrue(Path(doc.object_uri).exists())
        self.assertEqual(doc.content_sha256, hashlib.sha256(doc.body.encode("utf-8")).hexdigest())
        evidences = self.service.extract_evidence("doc_001", actor="analyst")
        self.assertGreaterEqual(len(evidences), 2)

        thesis = self.service.create_thesis(
            {
                "thesis_id": "thesis_001",
                "issuer_id": "issuer_001",
                "horizon": "mid",
                "hypothesis": "Revenue growth can continue",
                "evidence_ids": [evidence.evidence_id for evidence in evidences],
                "falsifiers": [],
                "risk_factors": ["macro slowdown"],
                "owner": "analyst",
            },
            actor="analyst",
        )
        self.assertEqual(thesis.thesis_id, "thesis_001")

        signal = self.service.run_scoring(
            {
                "thesis_id": "thesis_001",
                "strategy_type": "long",
                "source_model": "rules",
                "model_version": "v1",
            },
            actor="cio",
        )
        self.assertIn(signal.direction, {"long", "neutral"})
        self.assertGreaterEqual(signal.score, 0.0)
        self.assertLessEqual(signal.score, 1.0)

        pack = self.service.build_decision_pack(
            {
                "signal_ids": [signal.signal_id],
                "risk_checks": ["reg_fd"],
                "red_team_note": "Need human review",
            },
            actor="cio",
        )
        self.assertEqual(pack.approval_state, "pending")
        blocked_intent = self.router.dispatch(
            "POST",
            "/api/execution-intents",
            {
                "decision_id": pack.decision_id,
                "security_id": "sec_001",
                "action": "buy",
                "target_weight": 0.05,
            },
            role="PM",
        )
        self.assertFalse(blocked_intent.success)
        self.assertEqual(blocked_intent.status_code, 423)

        pack = self.service.sign_decision(pack.decision_id, {"role": "风险/合规", "user": "risk_owner"}, actor="risk")
        self.assertEqual(pack.approval_state, "pending")
        pack = self.service.sign_decision(pack.decision_id, {"role": "CEO", "user": "ceo_owner"}, actor="ceo")
        self.assertEqual(pack.approval_state, "approved")
        intent = self.router.dispatch(
            "POST",
            "/api/execution-intents",
            {
                "intent_id": "intent_001",
                "decision_id": pack.decision_id,
                "security_id": "sec_001",
                "action": "buy",
                "target_weight": 0.05,
                "rationale": "approved committee pack",
            },
            role="PM",
        )
        self.assertTrue(intent.success)
        self.assertEqual(intent.data["decision_id"], pack.decision_id)
        live_blocked = self.router.dispatch(
            "POST",
            "/api/execution-intents/intent_001/simulate",
            {"mode": "live", "quantity": 100, "fill_price": 10.0},
            role="PM",
        )
        self.assertFalse(live_blocked.success)
        self.assertEqual(live_blocked.status_code, 423)
        simulated = self.router.dispatch(
            "POST",
            "/api/execution-intents/intent_001/simulate",
            {
                "execution_id": "simexec_001",
                "transaction_id": "ptxn_simexec_001",
                "quantity": 100,
                "fill_price": 10.0,
                "fees": 1.25,
                "account_id": "paper_acct",
            },
            role="PM",
        )
        self.assertTrue(simulated.success, simulated.error)
        self.assertEqual(simulated.data["mode"], "simulated")
        self.assertFalse(simulated.data["live_execution_allowed"])
        self.assertEqual(simulated.data["execution"]["notional"], 1000.0)
        self.assertEqual(simulated.data["transaction"]["source_id"], "simulated_trade_execution")
        self.assertEqual(simulated.data["intent"]["status"], "simulated_filled")
        listed_sim = self.router.dispatch("GET", "/api/simulated-executions", {"intent_id": "intent_001"}, role="PM")
        self.assertTrue(listed_sim.success, listed_sim.error)
        self.assertEqual(listed_sim.data["total"], 1)
        listed_txn = self.router.dispatch("GET", "/api/portfolio/transactions", {"account_id": "paper_acct"}, role="PM")
        self.assertEqual(listed_txn.data["total"], 1)

        exception = self.service.create_exception(
            {
                "decision_id": pack.decision_id,
                "reason": "manual override requested",
                "severity": "high",
            },
            actor="risk",
        )
        self.assertEqual(exception["status"], "open")

        review = self.service.create_review(
            {
                "decision_id": pack.decision_id,
                "realized_outcome": "positive",
                "attribution": "thesis held",
                "lesson": "keep monitoring",
                "next_action": "retest in one month",
            },
            actor="cio",
        )
        self.assertEqual(review.decision_id, pack.decision_id)

        dashboard = self.service.dashboard()
        self.assertGreaterEqual(dashboard["counts"]["sources"], 1)
        self.assertIn("simulated_trade_execution", self.service.store.sources)
        self.assertEqual(dashboard["counts"]["documents"], 1)
        self.assertEqual(dashboard["counts"]["reviews"], 1)
        self.assertEqual(dashboard["counts"]["open_exceptions"], 1)
        self.assertEqual(dashboard["counts"]["execution_intents"], 1)
        self.assertEqual(dashboard["counts"]["simulated_executions"], 1)
        self.assertEqual(dashboard["counts"]["portfolio_transactions"], 1)
        review_payload = self.service.review_payload(review.review_id)
        self.assertEqual(review_payload["decision_id"], pack.decision_id)
        self.assertGreaterEqual(len(self.service.store.audit_log), 1)

    def test_operating_report_computes_performance_and_publish_approval(self) -> None:
        response = self.router.dispatch(
            "POST",
            "/api/operating-reports",
            {
                "report_id": "opr_perf",
                "period": "2026-05",
                "owner": "ceo",
                "metrics": {"gross_exposure": 0.8},
                "portfolio_returns": [0.02, -0.01, 0.015],
                "benchmark_returns": [0.01, -0.005, 0.01],
                "turnover": 0.23,
                "attribution": {"selection": 0.012, "allocation": -0.003},
                "red_flags": [{"type": "data_gap", "owner": "风险/合规", "due": "committee"}],
            },
            actor="ceo",
            role="CEO",
        )
        self.assertTrue(response.success, response.error)
        self.assertEqual(response.data["status"], "draft")
        self.assertIsNone(response.data["published_at"])
        metrics = response.data["metrics"]
        self.assertEqual(metrics["gross_exposure"], 0.8)
        self.assertAlmostEqual(metrics["twr"], 0.0249)
        self.assertAlmostEqual(metrics["total_return"], 0.0249)
        self.assertAlmostEqual(metrics["max_drawdown"], 0.01)
        self.assertAlmostEqual(metrics["turnover"], 0.23)
        self.assertIn("information_ratio", metrics)
        self.assertEqual(metrics["attribution"]["selection"], 0.012)
        self.assertIn("evidence_coverage", metrics)
        red_flag_id = response.data["red_flags"][0]["red_flag_id"]
        self.assertEqual(response.data["red_flags"][0]["status"], "open")
        self.assertEqual(response.data["red_flags"][0]["owner_role"], "风险/合规")
        self.assertEqual(response.data["red_flags"][0]["due_date"], "2026-05-31")

        reminders = self.router.dispatch(
            "GET",
            "/api/operating-reports/red-flag-reminders",
            {"as_of_date": "2026-06-02", "owner": "风险/合规"},
            role="risk_compliance",
        )
        self.assertTrue(reminders.success, reminders.error)
        self.assertGreaterEqual(reminders.data["overdue"], 1)
        self.assertEqual(reminders.data["reminders"][0]["red_flag_id"], red_flag_id)

        published = self.router.dispatch(
            "POST",
            "/api/operating-reports/opr_perf/publish",
            {"approver_role": "CEO", "user": "ceo_owner", "comment": "ready for board pack"},
            actor="ceo_owner",
            role="CEO",
        )
        self.assertTrue(published.success, published.error)
        self.assertEqual(published.data["status"], "published")
        self.assertIsNotNone(published.data["published_at"])
        self.assertEqual(published.data["approvals"][0]["role"], "CEO")
        self.assertIn("signed_at", published.data["approvals"][0])
        latest_audit = self.service.store.audit_log[-1]
        self.assertEqual(latest_audit.action, "publish_operating_report")
        self.assertEqual(latest_audit.approval_state, "published")

        with TemporaryDirectory() as temp_dir:
            self.service.object_store = LocalObjectStore(temp_dir)
            board_pack = self.router.dispatch(
                "POST",
                "/api/operating-reports/opr_perf/board-pack",
                {},
                actor="ceo_owner",
                role="CEO",
            )
            self.assertTrue(board_pack.success, board_pack.error)
            self.assertTrue(Path(board_pack.data["object_uri"]).exists())
            self.assertIn("Board Pack: Operating Report 2026-05", board_pack.data["content"])
            self.assertIn("gross_exposure", board_pack.data["content"])
            self.assertEqual(self.service.store.audit_log[-1].action, "export_operating_report_board_pack")
            pdf_pack = self.router.dispatch(
                "POST",
                "/api/operating-reports/opr_perf/board-pack",
                {"format": "pdf", "object_id": "opr_perf_board_pack_pdf", "include_content": False},
                actor="ceo_owner",
                role="CEO",
            )
            self.assertTrue(pdf_pack.success, pdf_pack.error)
            self.assertEqual(pdf_pack.data["format"], "pdf")
            self.assertEqual(pdf_pack.data["content_type"], "application/pdf")
            self.assertEqual(pdf_pack.data["content"], "")
            self.assertTrue(Path(pdf_pack.data["object_uri"]).read_bytes().startswith(b"%PDF-1.4"))

        resolved_flag = self.router.dispatch(
            "POST",
            f"/api/operating-reports/opr_perf/red-flags/{red_flag_id}/resolve",
            {"resolution": "data source mapped to public EOD feed", "resolved_by": "risk_owner"},
            actor="risk_owner",
            role="risk_compliance",
        )
        self.assertTrue(resolved_flag.success, resolved_flag.error)
        self.assertEqual(resolved_flag.data["red_flags"][0]["status"], "resolved")
        self.assertEqual(self.service.store.audit_log[-1].action, "resolve_operating_report_red_flag")

        duplicate = self.router.dispatch(
            "POST",
            "/api/operating-reports/opr_perf/publish",
            {"approver_role": "CEO", "user": "ceo_owner"},
            role="CEO",
        )
        self.assertFalse(duplicate.success)
        self.assertEqual(duplicate.status_code, 409)

        demo = self.router.dispatch("POST", "/api/demo/full-flow", {}, actor="platform_owner", role="platform")
        self.assertTrue(demo.success, demo.error)
        self.service.create_strategy_replay(
            {
                "replay_id": "replay_perf_v2",
                "decision_id": "dec_demo",
                "expected_outcome": "alpha holds after filing refresh",
                "actual_outcome": "positive alpha",
                "variance_reason": "services margin was stronger than base case",
                "next_action": "keep in v2 watchlist",
                "version": "v2",
            },
            actor="cio",
        )
        self.service.create_strategy_replay(
            {
                "replay_id": "replay_perf_v3",
                "decision_id": "dec_demo",
                "expected_outcome": "alpha remains positive after risk review",
                "actual_outcome": "watchlist only",
                "variance_reason": "macro exposure offset services margin",
                "next_action": "retest risk budget before adding",
                "version": "v3",
            },
            actor="cio",
        )
        filtered = self.router.dispatch(
            "GET",
            "/api/strategy-replays",
            {"decision_id": "dec_demo", "version": "v2"},
            role="CIO",
        )
        self.assertTrue(filtered.success, filtered.error)
        self.assertEqual(filtered.data["count"], 1)
        self.assertEqual(filtered.data["replays"][0]["replay_id"], "replay_perf_v2")

        compared = self.router.dispatch(
            "GET",
            "/api/strategy-replays/compare",
            {"decision_id": "dec_demo", "limit": 5},
            role="CIO",
        )
        self.assertTrue(compared.success, compared.error)
        self.assertEqual(compared.data["count"], 3)
        self.assertEqual(compared.data["variance_count"], 3)
        self.assertEqual(compared.data["latest_replay_id"], "replay_perf_v3")
        self.assertEqual(compared.data["version_counts"]["v2"], 1)
        self.assertIn("review_again", compared.data["action_counts"])
        replay_rows = {item["replay_id"]: item for item in compared.data["replays"]}
        self.assertEqual(replay_rows["replay_perf_v2"]["action_bucket"], "continue_or_expand")
        self.assertEqual(replay_rows["replay_perf_v3"]["action_bucket"], "review_again")
        self.assertEqual(compared.data["usage_boundary"], "strategy_replay_compare_is_post_decision_review_only")

    def test_portfolio_optimizer_respects_bl_constraints_and_stays_paper_only(self) -> None:
        for security_id, ticker, market in [
            ("sec_us", "DEMOUS", "U"),
            ("sec_h", "DEMOHK", "H"),
            ("sec_blocked", "DEMOBLK", "U"),
        ]:
            self.service.register_security(
                {
                    "security_id": security_id,
                    "issuer_id": "issuer_001",
                    "ticker": ticker,
                    "exchange": "TEST",
                    "currency": "USD" if market == "U" else "HKD",
                    "market": market,
                },
                actor="platform",
            )
        response = self.router.dispatch(
            "POST",
            "/api/portfolio/optimize",
            {
                "proposal_id": "pfp_bl",
                "risk_aversion": 2.5,
                "tau": 0.05,
                "securities": [
                    {"security_id": "sec_001", "market_weight": 0.35, "volatility": 0.22, "market": "A", "industry": "Tech"},
                    {"security_id": "sec_us", "market_weight": 0.35, "volatility": 0.28, "market": "U", "industry": "Tech"},
                    {"security_id": "sec_h", "market_weight": 0.20, "volatility": 0.24, "market": "H", "industry": "Consumer"},
                    {"security_id": "sec_blocked", "market_weight": 0.10, "volatility": 0.30, "market": "U", "industry": "Tech"},
                ],
                "views": [
                    {"security_id": "sec_us", "expected_return": 0.12, "confidence": 0.8},
                    {"security_id": "sec_001", "expected_return": 0.06, "confidence": 0.5},
                    {"security_id": "sec_blocked", "expected_return": 0.5, "confidence": 0.99},
                ],
                "constraints": {
                    "max_weight": 0.6,
                    "restricted_securities": ["sec_blocked"],
                    "market_budget": {"U": 0.7},
                    "industry_budget": {"Tech": 0.75},
                    "current_weights": {"sec_001": 0.3, "sec_us": 0.2, "sec_h": 0.1},
                },
                "risk_budget": {"market": {"A": 0.6, "H": 0.5, "U": 0.7}},
                "stress_scenarios": [
                    {"name": "dollar_liquidity_shock", "shocks": {"sec_001": -0.05, "sec_us": -0.10, "sec_h": 0.02}}
                ],
                "return_history": {
                    "sec_001": [0.01, -0.02, 0.015],
                    "sec_us": [0.02, -0.03, 0.01],
                    "sec_h": [0.005, -0.01, 0.02],
                },
                "covariance_shrinkage": 0.4,
            },
            actor="cio",
            role="CIO",
        )
        self.assertTrue(response.success, response.error)
        weights = response.data["candidate_weights"]
        diagnostics = response.data["diagnostics"]
        self.assertEqual(response.data["constraints"]["paper_only"], True)
        self.assertEqual(weights["sec_blocked"], 0.0)
        self.assertLessEqual(max(weights.values()), 0.600001)
        self.assertLessEqual(diagnostics["market_exposure"]["U"], 0.700001)
        self.assertLessEqual(diagnostics["industry_exposure"]["Tech"], 0.750001)
        self.assertGreater(diagnostics["view_diagnostics"][0]["omega"], 0.0)
        shadow_constraints = {item["constraint"] for item in diagnostics["constraint_shadow_prices"]}
        self.assertIn("restricted_security", shadow_constraints)
        self.assertTrue(any(item["constraint"] == "industry_budget" and item["binding"] for item in diagnostics["constraint_shadow_prices"]))
        self.assertIn("stress_report", diagnostics)
        self.assertEqual(diagnostics["walk_forward"]["period_count"], 3)
        covariance = diagnostics["covariance"]
        self.assertEqual(covariance["method"], "sample_covariance_with_diagonal_shrinkage")
        self.assertEqual(covariance["period_count"], 3)
        self.assertEqual(covariance["shrinkage"], 0.4)
        self.assertIn("sec_us", covariance["sample_covariance"])
        self.assertIn("sec_001", covariance["shrunk_covariance"]["sec_us"])
        self.assertLess(abs(covariance["shrunk_covariance"]["sec_us"]["sec_001"]), abs(covariance["sample_covariance"]["sec_us"]["sec_001"]))
        self.assertAlmostEqual(covariance["correlation"]["sec_us"]["sec_us"], 1.0)
        self.assertEqual(len(self.service.store.execution_intents), 0)

        fetched = self.router.dispatch("GET", "/api/portfolio/proposals/pfp_bl", {}, role="CIO")
        self.assertTrue(fetched.success, fetched.error)
        self.assertEqual(fetched.data["proposal_id"], "pfp_bl")
        listed = self.router.dispatch("GET", "/api/portfolio/proposals", {"status": "candidate"}, role="CIO")
        self.assertEqual(listed.data["count"], 1)
        graph = self.router.dispatch("GET", "/api/graph/query", {"security_id": "sec_us"}, role="CIO")
        self.assertTrue(graph.success, graph.error)
        self.assertEqual(graph.data["portfolio_proposals"][0]["proposal_id"], "pfp_bl")

    def test_portfolio_optimizer_requires_benchmark_passed_evidence_when_configured(self) -> None:
        document = self.service.ingest_document(
            {
                "document_id": "doc_portfolio_view",
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "source_id": "src_sec",
                "source_type": "regulatory",
                "document_type": "10-K",
                "source_uri": "https://example.invalid/doc-portfolio-view",
                "body": "Revenue growth improved in the public filing.",
                "rights_tag": {
                    "license_class": "public",
                    "training_allowed": False,
                    "redistribution_allowed": False,
                    "display_use": "allowed",
                    "non_display_use": "restricted",
                    "derived_data_use": "restricted",
                },
                "language": "en",
            },
            actor="data",
        )
        evidence = self.service.extract_evidence(document.document_id, actor="analyst")[0]
        self.service.register_benchmark(
            {
                "benchmark_id": "bm_view_pass",
                "language": "en",
                "task_type": "term_extraction",
                "threshold": {"term_f1": 1.0},
            },
            actor="ml",
        )
        self.service.extract_structured_facts(
            {
                "extraction_id": "ext_view_pass",
                "evidence_id": evidence.evidence_id,
                "benchmark_id": "bm_view_pass",
                "expected_terms": ["revenue"],
            },
            actor="ml",
        )

        passed = self.router.dispatch(
            "POST",
            "/api/portfolio/optimize",
            {
                "proposal_id": "pfp_bench_pass",
                "require_benchmark_passed_evidence": True,
                "benchmark_id": "bm_view_pass",
                "securities": [{"security_id": "sec_001", "market_weight": 1.0, "volatility": 0.2, "market": "A"}],
                "views": [{"security_id": "sec_001", "expected_return": 0.08, "confidence": 0.7, "evidence_ids": [evidence.evidence_id]}],
            },
            actor="cio",
            role="CIO",
        )
        self.assertTrue(passed.success, passed.error)
        self.assertTrue(passed.data["diagnostics"]["view_diagnostics"][0]["benchmark_evidence"]["passed"])

        self.service.register_benchmark(
            {
                "benchmark_id": "bm_view_fail",
                "language": "en",
                "task_type": "term_extraction",
                "threshold": {"term_f1": 1.0},
            },
            actor="ml",
        )
        self.service.extract_structured_facts(
            {
                "extraction_id": "ext_view_fail",
                "evidence_id": evidence.evidence_id,
                "benchmark_id": "bm_view_fail",
                "expected_terms": ["gross_margin"],
            },
            actor="ml",
        )
        blocked = self.router.dispatch(
            "POST",
            "/api/portfolio/optimize",
            {
                "proposal_id": "pfp_bench_blocked",
                "require_benchmark_passed_evidence": True,
                "benchmark_id": "bm_view_fail",
                "securities": [{"security_id": "sec_001", "market_weight": 1.0, "volatility": 0.2, "market": "A"}],
                "views": [{"security_id": "sec_001", "expected_return": 0.08, "confidence": 0.7, "evidence_ids": [evidence.evidence_id]}],
            },
            actor="cio",
            role="CIO",
        )
        self.assertFalse(blocked.success)
        self.assertEqual(blocked.status_code, 423)

    def test_rejects_more_permissive_document_rights(self) -> None:
        with self.assertRaises(PermissionDenied):
            self.service.ingest_document(
                {
                    "document_id": "doc_002",
                    "issuer_id": "issuer_001",
                    "security_id": "sec_001",
                    "source_id": "src_sec",
                    "source_type": "regulatory",
                    "document_type": "annual_report",
                    "source_uri": "https://example.invalid/doc-002",
                    "body": "Any content.",
                    "rights_tag": {
                        "license_class": "public",
                        "training_allowed": True,
                        "redistribution_allowed": False,
                        "display_use": "allowed",
                        "non_display_use": "restricted",
                        "derived_data_use": "restricted",
                    },
                },
                actor="data",
            )

    def test_ingest_document_sanitizes_sensitive_source_uri(self) -> None:
        doc = self.service.ingest_document(
            {
                "document_id": "doc_sanitized_uri",
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "source_id": "src_sec",
                "source_type": "regulatory",
                "document_type": "annual_report",
                "source_uri": "https://example.invalid/report.pdf?token=secret&lang=en&api_key=abc#frag",
                "body": "Public filing body.",
                "rights_tag": {
                    "license_class": "public",
                    "training_allowed": False,
                    "redistribution_allowed": False,
                    "display_use": "allowed",
                    "non_display_use": "restricted",
                    "derived_data_use": "restricted",
                },
            },
            actor="data",
        )
        self.addCleanup(lambda: Path(doc.object_uri).unlink(missing_ok=True))
        self.assertEqual(doc.source_uri, "https://example.invalid/report.pdf?token=REDACTED&lang=en&api_key=REDACTED")
        self.assertNotIn("secret", doc.source_uri)
        self.assertNotIn("#frag", doc.source_uri)

    def test_transcript_and_research_sources_preserve_citation_boundaries(self) -> None:
        sources = {source.source_id: source for source in self.service.seed_default_sources(actor="risk")}
        self.assertIn("company_public_webcast", sources)
        self.assertIn("manual_reference_transcripts", sources)
        self.assertIn("local_research_reports", sources)
        public_doc = self.service.ingest_document(
            {
                "document_id": "doc_webcast",
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "source_id": "company_public_webcast",
                "source_type": "company_ir",
                "document_type": "webcast",
                "source_uri": "https://ir.example.invalid/webcast",
                "body": "Public webcast transcript mentions revenue growth.",
                "rights_tag": {
                    "license_class": "public_company_ir_reference",
                    "training_allowed": False,
                    "redistribution_allowed": False,
                    "display_use": "allowed",
                    "non_display_use": "restricted",
                    "derived_data_use": "restricted",
                },
                "language": "en",
            },
            actor="data",
        )
        self.assertEqual(public_doc.source_id, "company_public_webcast")
        with self.assertRaises(PermissionDenied):
            self.service.ingest_document(
                {
                    "document_id": "doc_manual_transcript_bad",
                    "issuer_id": "issuer_001",
                    "security_id": "sec_001",
                    "source_id": "manual_reference_transcripts",
                    "source_type": "manual_reference",
                    "document_type": "transcript",
                    "source_uri": "private://transcripts/demo",
                    "body": "Private transcript text.",
                    "rights_tag": {
                        "license_class": "manual_transcript_reference",
                        "training_allowed": True,
                        "redistribution_allowed": False,
                        "display_use": "restricted",
                        "non_display_use": "restricted",
                        "derived_data_use": "restricted",
                    },
                },
                actor="data",
            )
        blocked_text = self.router.dispatch(
            "POST",
            "/api/research/manual-references",
            {
                "document_id": "doc_private_note_text",
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "document_type": "private_meeting_note",
                "title": "Private meeting note",
                "source_uri": "private://meetings/demo",
                "body": "Do not store this private note text.",
            },
            actor="analyst",
            role="analyst",
        )
        self.assertFalse(blocked_text.success)
        self.assertEqual(blocked_text.status_code, 422)

        manual_reference = self.router.dispatch(
            "POST",
            "/api/research/manual-references",
            {
                "document_id": "doc_private_note_meta",
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "document_type": "private_meeting_note",
                "title": "Private meeting note metadata",
                "source_uri": "private://meetings/demo",
                "notes": "Metadata only; compliance must confirm Reg FD boundary.",
            },
            actor="analyst",
            role="analyst",
        )
        self.assertTrue(manual_reference.success, manual_reference.error)
        self.assertEqual(manual_reference.data["document"]["source_id"], "manual_reference_transcripts")
        self.assertEqual(manual_reference.data["document"]["body"], "")
        self.assertEqual(manual_reference.data["manual_review"]["issue_type"], "manual_reference_boundary_review")

        manual_reviews = self.router.dispatch(
            "GET",
            "/api/evidence/manual-reviews",
            {"issue_type": "manual_reference_boundary_review"},
            role="risk_compliance",
        )
        self.assertTrue(manual_reviews.success)
        self.assertEqual(manual_reviews.data["manual_reviews"][0]["document_id"], "doc_private_note_meta")
        policy = Path("docs/transcript-research-citation-policy.md").read_text(encoding="utf-8")
        for fragment in ["company_public_webcast", "manual_reference_transcripts", "No transcript or research text enters training", "Reg FD"]:
            self.assertIn(fragment, policy)

    def test_research_report_manifest_scan_list_and_ingest(self) -> None:
        with TemporaryDirectory() as temp_dir:
            report_dir = Path(temp_dir) / "Goldman" / "2026" / "05"
            report_dir.mkdir(parents=True)
            report_path = report_dir / "Demo Corp outlook.pdf"
            report_path.write_bytes(b"%PDF-1.4\nresearch report\n%%EOF")

            scanned = self.router.dispatch(
                "POST",
                "/api/research-reports/scan",
                {"root_path": temp_dir, "extensions": [".pdf", ".txt"], "limit": 10},
                actor="data",
                role="data_engineer",
            )
            self.assertTrue(scanned.success, scanned.error)
            self.assertEqual(scanned.data["indexed_count"], 1)
            report = scanned.data["reports"][0]
            self.assertEqual(report["broker"], "Goldman")
            self.assertEqual(report["year"], "2026")
            self.assertEqual(report["month"], "05")
            self.assertFalse(report["rights_tag"]["training_allowed"])
            self.assertEqual(report["rights_tag"]["display_use"], "restricted")
            self.assertIn(report["source_id"], self.service.store.sources)

            listed = self.router.dispatch("GET", "/api/research-reports", {"broker": "goldman"}, role="analyst")
            self.assertTrue(listed.success)
            self.assertEqual(listed.data["count"], 1)

            ingested = self.router.dispatch(
                "POST",
                f"/api/research-reports/{report['report_id']}/ingest",
                {"issuer_id": "issuer_001", "security_id": "sec_001", "document_id": "doc_research_goldman"},
                actor="analyst",
                role="analyst",
            )
            self.assertTrue(ingested.success, ingested.error)
            self.assertTrue(ingested.data["created"])
            self.assertEqual(ingested.data["document"]["document_type"], "research")
            self.assertEqual(ingested.data["document"]["object_uri"], str(report_path))
            self.assertEqual(ingested.data["report"]["status"], "ingested")

            search = self.router.dispatch("GET", "/api/search", {"q": "Goldman outlook"}, role="analyst")
            self.assertTrue(search.success)
            self.assertIn("research_report", {item["resource_type"] for item in search.data["results"]})

    def test_research_report_text_extraction_indexes_citations_and_manual_review(self) -> None:
        with TemporaryDirectory() as temp_dir:
            report_dir = Path(temp_dir) / "Morgan" / "2026" / "05"
            report_dir.mkdir(parents=True)
            text_path = report_dir / "Demo citation note.txt"
            text_path.write_text("Revenue catalyst and margin expansion view. " * 20, encoding="utf-8")
            pdf_path = report_dir / "Scanned local research.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\n%%EOF")

            scanned = self.router.dispatch(
                "POST",
                "/api/research-reports/scan",
                {"root_path": temp_dir, "extensions": [".pdf", ".txt"], "limit": 10},
                actor="data",
                role="data_engineer",
            )
            self.assertTrue(scanned.success, scanned.error)
            reports = {item["file_name"]: item for item in scanned.data["reports"]}
            text_report = reports["Demo citation note.txt"]
            pdf_report = reports["Scanned local research.pdf"]

            self.router.dispatch(
                "POST",
                f"/api/research-reports/{text_report['report_id']}/ingest",
                {"issuer_id": "issuer_001", "security_id": "sec_001", "document_id": "doc_research_text"},
                actor="analyst",
                role="analyst",
            )
            extracted = self.router.dispatch(
                "POST",
                f"/api/research-reports/{text_report['report_id']}/extract",
                {"citation_char_limit": 160},
                actor="analyst",
                role="analyst",
            )
            self.assertTrue(extracted.success, extracted.error)
            self.assertEqual(extracted.data["status"], "text_indexed")
            self.assertTrue(extracted.data["citation_truncated"])
            self.assertGreaterEqual(len(extracted.data["evidence"]), 1)
            self.assertEqual(extracted.data["evidence"][0]["section"], "research_report_citation")
            self.assertEqual(extracted.data["document"]["rights_tag"]["display_use"], "restricted")

            search = self.router.dispatch("GET", "/api/search", {"q": "margin expansion"}, role="analyst")
            self.assertTrue(search.success)
            self.assertIn("evidence", {item["resource_type"] for item in search.data["results"]})

            self.router.dispatch(
                "POST",
                f"/api/research-reports/{pdf_report['report_id']}/ingest",
                {"issuer_id": "issuer_001", "security_id": "sec_001", "document_id": "doc_research_scanned"},
                actor="analyst",
                role="analyst",
            )
            queue = self.router.dispatch(
                "POST",
                "/api/research-reports/extraction-queue",
                {"file_type": "pdf", "execute": False, "limit": 10, "raw_text_cache_ttl_days": 30},
                actor="analyst",
                role="analyst",
            )
            self.assertTrue(queue.success, queue.error)
            queued_pdf = {item["report_id"]: item for item in queue.data["items"]}
            self.assertEqual(queued_pdf[pdf_report["report_id"]]["action"], "ocr_required")
            self.assertEqual(queue.data["cache_policy"]["raw_text_cache_ttl_days"], 30)

            batch = self.router.dispatch(
                "POST",
                "/api/research-reports/extraction-queue",
                {"file_type": "pdf", "execute": True, "limit": 10},
                actor="analyst",
                role="analyst",
            )
            self.assertTrue(batch.success, batch.error)
            self.assertEqual(batch.data["counters"]["executed"], 1)
            self.assertEqual(batch.data["counters"]["manual_review"], 1)
            pdf_row = {item["report_id"]: item for item in batch.data["items"]}[pdf_report["report_id"]]
            self.assertEqual(pdf_row["result_status"], "needs_text_review")
            review = self.service.store.manual_reviews[pdf_row["manual_review_id"]]
            self.assertEqual(review.issue_type, "research_report_text_extraction_required")

    def test_research_report_governance_report_flags_stale_and_single_source_bias(self) -> None:
        with TemporaryDirectory() as temp_dir:
            files = [
                Path(temp_dir) / "Goldman" / "2025" / "01" / "Demo old A.pdf",
                Path(temp_dir) / "Goldman" / "2025" / "02" / "Demo old B.pdf",
                Path(temp_dir) / "Morgan" / "2026" / "05" / "Demo fresh.pdf",
            ]
            for path in files:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"%PDF-1.4\nresearch\n%%EOF")

            scanned = self.router.dispatch(
                "POST",
                "/api/research-reports/scan",
                {"root_path": temp_dir, "extensions": [".pdf"], "limit": 10},
                actor="data",
                role="data_engineer",
            )
            self.assertTrue(scanned.success, scanned.error)
            for index, report in enumerate(scanned.data["reports"]):
                ingest_payload = {"issuer_id": "issuer_001", "security_id": "sec_001", "document_id": f"doc_research_gov_{index}"}
                if index == 0:
                    ingest_payload.update({"industry": "software", "event_ids": ["de_guidance_demo"]})
                ingested = self.router.dispatch(
                    "POST",
                    f"/api/research-reports/{report['report_id']}/ingest",
                    ingest_payload,
                    actor="analyst",
                    role="analyst",
                )
                self.assertTrue(ingested.success, ingested.error)
                document = self.service.store.documents[f"doc_research_gov_{index}"]
                if report["broker"] == "Goldman":
                    document.body = "Revenue guidance positive upgrade, margin beat and target price raised."
                else:
                    document.body = "Revenue guidance negative downgrade with margin headwind and valuation risk."

            event = self.service.create_disclosure_event(
                {
                    "event_id": "de_research_candidate",
                    "document_id": "doc_research_gov_1",
                    "issuer_id": "issuer_001",
                    "security_id": "sec_001",
                    "event_type": "guidance_update",
                    "summary": "Guidance update used as a candidate research mapping.",
                },
                actor="analyst",
            )
            self.assertEqual(event.event_id, "de_research_candidate")

            governance = self.router.dispatch(
                "GET",
                "/api/research-reports/governance-report",
                {
                    "issuer_id": "issuer_001",
                    "as_of": "2026-05-15T00:00:00+00:00",
                    "stale_after_days": 180,
                    "max_single_source_share": 0.6,
                },
                role="analyst",
            )
            self.assertTrue(governance.success, governance.error)
            self.assertEqual(governance.data["count"], 3)
            self.assertEqual(governance.data["stale_count"], 2)
            self.assertEqual(governance.data["missing_document_count"], 0)
            self.assertEqual(governance.data["top_broker"], "Goldman")
            self.assertAlmostEqual(governance.data["top_broker_share"], 0.6667)
            self.assertIn("single_broker_concentration_breach", governance.data["concentration_issues"])
            self.assertFalse(governance.data["automation_allowed"])
            stale_rows = [row for row in governance.data["reports"] if row["stale"]]
            self.assertTrue(all("stale_research_report" in row["issues"] for row in stale_rows))

            mapping = self.router.dispatch(
                "GET",
                "/api/research-reports/mapping-report",
                {"issuer_id": "issuer_001", "industry": "software", "limit": 5},
                role="analyst",
            )
            self.assertTrue(mapping.success, mapping.error)
            self.assertEqual(mapping.data["count"], 1)
            self.assertEqual(mapping.data["mapped_issuer_count"], 1)
            self.assertEqual(mapping.data["mapped_security_count"], 1)
            self.assertEqual(mapping.data["industry_counts"], {"software": 1})
            mapped_report = mapping.data["reports"][0]
            self.assertEqual(mapped_report["issuer_id"], "issuer_001")
            self.assertEqual(mapped_report["security_id"], "sec_001")
            self.assertEqual(mapped_report["industry"], "software")
            self.assertIn("de_guidance_demo", mapped_report["event_ids"])
            self.assertIn("de_research_candidate", mapped_report["candidate_event_ids"])
            self.assertEqual(mapped_report["source_boundary"], "local_reference_research_report")
            self.assertFalse(mapping.data["automation_allowed"])

            rescanned = self.router.dispatch(
                "POST",
                "/api/research-reports/scan",
                {"root_path": temp_dir, "extensions": [".pdf"], "limit": 10},
                actor="data",
                role="data_engineer",
            )
            self.assertTrue(rescanned.success, rescanned.error)
            preserved = next(item for item in rescanned.data["reports"] if item["event_ids"])
            self.assertEqual(preserved["industry"], "software")
            self.assertIn("de_guidance_demo", preserved["event_ids"])

            viewpoints = self.router.dispatch(
                "GET",
                "/api/research-reports/viewpoint-report",
                {"issuer_id": "issuer_001", "topic": "guidance", "max_single_broker_share": 0.6},
                role="analyst",
            )
            self.assertTrue(viewpoints.success, viewpoints.error)
            self.assertEqual(viewpoints.data["count"], 3)
            self.assertFalse(viewpoints.data["automation_allowed"])
            guidance_topic = next(item for item in viewpoints.data["topics"] if item["topic"] == "guidance")
            self.assertEqual(guidance_topic["count"], 3)
            self.assertEqual(guidance_topic["broker_counts"]["Goldman"], 2)
            self.assertIn("broker_concentration_bias", guidance_topic["issues"])
            self.assertIn("positive", guidance_topic["sentiment_counts"])
            self.assertIn("negative", guidance_topic["sentiment_counts"])
            self.assertGreaterEqual(viewpoints.data["bias_alert_count"], 1)
            self.assertEqual(viewpoints.data["usage_boundary"], "research_report_viewpoints_are_local_reference_only_not_fact_source_or_training_data")

    def test_extract_evidence_strips_html_and_ignored_tags(self) -> None:
        self.service.ingest_document(
            {
                "document_id": "doc_html",
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "source_id": "src_sec",
                "source_type": "regulatory",
                "document_type": "10-K",
                "source_uri": "https://example.invalid/doc-html",
                "body": "<html><body><p>Revenue grew 12%.</p><script>ignore()</script><p>Risk factors remain.</p></body></html>",
                "rights_tag": {
                    "license_class": "public",
                    "training_allowed": False,
                    "redistribution_allowed": False,
                    "display_use": "allowed",
                    "non_display_use": "restricted",
                    "derived_data_use": "restricted",
                },
                "language": "en",
            },
            actor="data",
        )
        evidences = self.service.extract_evidence("doc_html", actor="analyst")
        evidence_text = "\n".join(item.span_text for item in evidences)
        self.assertIn("Revenue grew 12%.", evidence_text)
        self.assertIn("Risk factors remain.", evidence_text)
        self.assertNotIn("<p>", evidence_text)
        self.assertNotIn("ignore()", evidence_text)

    def test_extract_evidence_tracks_form_feed_pages(self) -> None:
        self.service.ingest_document(
            {
                "document_id": "doc_pages",
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "source_id": "src_sec",
                "source_type": "regulatory",
                "document_type": "10-K",
                "source_uri": "https://example.invalid/doc-pages",
                "body": "Page one revenue.\fPage two risk.\n\nPage two liquidity.",
                "rights_tag": {
                    "license_class": "public",
                    "training_allowed": False,
                    "redistribution_allowed": False,
                    "display_use": "allowed",
                    "non_display_use": "restricted",
                    "derived_data_use": "restricted",
                },
                "language": "en",
            },
            actor="data",
        )
        evidences = self.service.extract_evidence("doc_pages", actor="analyst")
        self.assertEqual([item.page_no for item in evidences], [1, 2, 2])
        self.assertEqual(evidences[1].section, "page_2_paragraph_1")
        self.assertEqual(evidences[2].bbox, "page=2;chunk=2")

    def test_extract_evidence_reads_pdf_object_when_body_is_empty(self) -> None:
        pdf_stream = zlib.compress(b"BT /F1 12 Tf 72 720 Td (PDF revenue grew 12%.) Tj ET")
        pdf_bytes = b"%PDF-1.4\n1 0 obj\n<< /Length " + str(len(pdf_stream)).encode("ascii") + b" /Filter /FlateDecode >>\nstream\n" + pdf_stream + b"\nendstream\nendobj\n%%EOF"
        stored = self.service.object_store.put_bytes("src_sec", "doc_pdf", pdf_bytes, suffix=".pdf")
        self.service.ingest_document(
            {
                "document_id": "doc_pdf",
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "source_id": "src_sec",
                "source_type": "regulatory",
                "document_type": "10-K",
                "source_uri": "https://example.invalid/doc-pdf.pdf",
                "object_uri": stored.uri,
                "content_sha256": stored.sha256,
                "body": "",
                "rights_tag": {
                    "license_class": "public",
                    "training_allowed": False,
                    "redistribution_allowed": False,
                    "display_use": "allowed",
                    "non_display_use": "restricted",
                    "derived_data_use": "restricted",
                },
                "language": "en",
            },
            actor="data",
        )
        evidences = self.service.extract_evidence("doc_pdf", actor="analyst", parser_version="pdf-rule-1")
        self.assertEqual(len(evidences), 1)
        self.assertIn("PDF revenue grew 12%.", evidences[0].span_text)
        self.assertEqual(evidences[0].bbox, "page=1;chunk=1")

    def test_extract_evidence_uses_paddleocr_fallback_for_scanned_pdf_object(self) -> None:
        sent = []
        jsonl = json.dumps(
            {
                "result": {
                    "layoutParsingResults": [
                        {"markdown": {"text": "OCR revenue grew 15%."}},
                        {"markdown": {"text": "OCR risk factors stayed manageable."}},
                    ]
                }
            }
        ).encode("utf-8")

        def fake_send(request, timeout):
            sent.append(
                {
                    "url": request.full_url,
                    "method": request.get_method(),
                    "timeout": timeout,
                    "headers": {key.lower(): value for key, value in request.header_items()},
                    "body": request.data or b"",
                }
            )
            if request.full_url.endswith("/api/v2/ocr/jobs") and request.get_method() == "POST":
                return b'{"data":{"jobId":"job_ocr_1"}}'
            if request.full_url.endswith("/api/v2/ocr/jobs/job_ocr_1"):
                return b'{"data":{"state":"done","resultUrl":{"jsonUrl":"https://result.example/doc.jsonl"}}}'
            if request.full_url == "https://result.example/doc.jsonl":
                return jsonl
            return b"{}"

        self.service.document_parser = PaddleOCRParser(token="ocr-test-token", poll_interval=0, max_polls=2, http_send=fake_send)
        stored = self.service.object_store.put_bytes("src_sec", "doc_ocr", b"%PDF-1.4\n%%EOF", suffix=".pdf")
        self.addCleanup(lambda: Path(stored.uri).unlink(missing_ok=True))
        self.service.ingest_document(
            {
                "document_id": "doc_ocr",
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "source_id": "src_sec",
                "source_type": "regulatory",
                "document_type": "10-K",
                "source_uri": "https://example.invalid/doc-ocr.pdf",
                "object_uri": stored.uri,
                "content_sha256": stored.sha256,
                "body": "",
                "rights_tag": {
                    "license_class": "public",
                    "training_allowed": False,
                    "redistribution_allowed": False,
                    "display_use": "allowed",
                    "non_display_use": "restricted",
                    "derived_data_use": "restricted",
                },
                "language": "en",
            },
            actor="data",
        )

        evidences = self.service.extract_evidence("doc_ocr", actor="analyst", parser_version="pdf-rule-1")
        self.assertEqual(len(evidences), 2)
        self.assertIn("OCR revenue grew 15%.", evidences[0].span_text)
        self.assertIn(b'name="file"; filename="doc_ocr.pdf"', sent[0]["body"])
        self.assertEqual(sent[0]["headers"]["authorization"], "bearer ocr-test-token")
        self.assertEqual(self.service.manual_review_payload({"document_id": "doc_ocr"})["manual_reviews"], [])
        self.assertEqual(self.service.store.audit_log[-2].action, "parse_document_with_paddleocr")
        sent_count = len(sent)
        cached = self.router.dispatch("POST", "/api/document-parsing/paddleocr", {"document_id": "doc_ocr"}, role="data_engineer")
        self.assertTrue(cached.success, cached.error)
        self.assertTrue(cached.data["cache_hit"])
        self.assertEqual(cached.data["page_count"], 2)
        self.assertIn("elapsed_ms", cached.data)
        self.assertIn("estimated_cost", cached.data)
        self.assertEqual(len(sent), sent_count)

    def test_extract_evidence_routes_empty_or_scanned_document_to_manual_review(self) -> None:
        self.service.ingest_document(
            {
                "document_id": "doc_scanned",
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "source_id": "src_sec",
                "source_type": "regulatory",
                "document_type": "10-K",
                "source_uri": "https://example.invalid/scanned.pdf",
                "body": "",
                "rights_tag": {
                    "license_class": "public",
                    "training_allowed": False,
                    "redistribution_allowed": False,
                    "display_use": "allowed",
                    "non_display_use": "restricted",
                    "derived_data_use": "restricted",
                },
                "language": "en",
            },
            actor="data",
        )
        response = self.router.dispatch(
            "POST",
            "/api/evidence/extract",
            {"document_id": "doc_scanned", "parser_version": "pdf-rule-1"},
            role="analyst",
        )
        self.assertFalse(response.success)
        self.assertEqual(response.status_code, 422)

        reviews = self.router.dispatch("GET", "/api/evidence/manual-reviews", {"document_id": "doc_scanned"}, role="risk_compliance")
        self.assertTrue(reviews.success)
        self.assertEqual(reviews.data["manual_reviews"][0]["issue_type"], "empty_or_scanned_document")
        self.assertEqual(reviews.data["manual_reviews"][0]["status"], "open")

        report = self.router.dispatch("GET", "/api/evidence/quality-report", {"issuer_id": "issuer_001"}, role="risk_compliance")
        self.assertTrue(report.success)
        self.assertEqual(report.data["open_manual_reviews"], 1)
        self.assertEqual(report.data["issue_counts"]["empty_or_scanned_document"], 1)
        self.assertGreater(report.data["parse_failure_rate"], 0)

    def test_alert_rules_evaluate_metrics_and_resolve(self) -> None:
        self.service.ingest_document(
            {
                "document_id": "doc_alert_scanned",
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "source_id": "src_sec",
                "source_type": "regulatory",
                "document_type": "10-K",
                "source_uri": "https://example.invalid/alert-scanned.pdf",
                "body": "",
                "rights_tag": {
                    "license_class": "public",
                    "training_allowed": False,
                    "redistribution_allowed": False,
                    "display_use": "allowed",
                    "non_display_use": "restricted",
                    "derived_data_use": "restricted",
                },
                "language": "en",
            },
            actor="data",
        )
        self.router.dispatch(
            "POST",
            "/api/evidence/extract",
            {"document_id": "doc_alert_scanned", "parser_version": "pdf-rule-1"},
            role="analyst",
        )

        seeded = self.router.dispatch("POST", "/api/alerts/rules/seed", {}, role="risk_compliance")
        self.assertTrue(seeded.success)
        self.assertGreaterEqual(len(seeded.data["rules"]), 5)
        self.assertIn("alert_source_review_overdue", {item["rule_id"] for item in seeded.data["rules"]})

        evaluated = self.router.dispatch("POST", "/api/alerts/evaluate", {}, role="risk_compliance")
        self.assertTrue(evaluated.success)
        open_rule_ids = {item["rule_id"] for item in evaluated.data["alerts"]}
        self.assertIn("alert_open_manual_reviews", open_rule_ids)

        listed = self.router.dispatch("GET", "/api/alerts", {"status": "open"}, role="risk_compliance")
        self.assertTrue(listed.success)
        self.assertIn("alert_open_manual_reviews", {item["rule_id"] for item in listed.data["alerts"]})

        dashboard = self.router.dispatch("GET", "/api/dashboard/risk", {}, role="risk_compliance")
        self.assertTrue(dashboard.success)
        self.assertGreaterEqual(dashboard.data["counts"]["open_alerts"], 1)

        notified = self.router.dispatch(
            "POST",
            "/api/alerts/notify",
            {"channel": "webhook", "target": "risk-desk"},
            role="risk_compliance",
        )
        self.assertTrue(notified.success, notified.error)
        self.assertGreaterEqual(notified.data["count"], 1)
        notifications = self.router.dispatch("GET", "/api/alerts/notifications", {"channel": "webhook"}, role="risk_compliance")
        self.assertEqual(notifications.data["notifications"][0]["status"], "sent")
        self.assertEqual(self.service.dashboard()["counts"]["alert_notifications"], notified.data["count"])

        pending = self.router.dispatch(
            "POST",
            "/api/alerts/notify",
            {"channel": "webhook", "target": "risk-desk", "mark_sent": False},
            role="risk_compliance",
        )
        self.assertTrue(pending.success, pending.error)
        delivery_preview = self.router.dispatch(
            "POST",
            "/api/alerts/notifications/deliver",
            {"channel": "webhook", "execute": False},
            role="risk_compliance",
        )
        self.assertTrue(delivery_preview.success, delivery_preview.error)
        self.assertGreaterEqual(delivery_preview.data["count"], 1)
        self.assertEqual(delivery_preview.data["notifications"][0]["delivery_status"], "dry_run")
        delivery = self.router.dispatch(
            "POST",
            "/api/alerts/notifications/deliver",
            {"channel": "webhook", "execute": True, "provider": "dry-run-webhook"},
            role="risk_compliance",
        )
        self.assertTrue(delivery.success, delivery.error)
        self.assertGreaterEqual(delivery.data["delivered_count"], 1)
        delivered_notification = self.service.store.alert_notifications[pending.data["notifications"][0]["notification_id"]]
        self.assertEqual(delivered_notification.status, "sent")
        self.assertEqual(delivered_notification.payload["delivery_provider"], "dry-run-webhook")

        for item in self.service.store.manual_reviews.values():
            item.status = "closed"
        resolved = self.router.dispatch("POST", "/api/alerts/evaluate", {}, role="risk_compliance")
        self.assertTrue(resolved.success)
        self.assertIn("alert_open_manual_reviews", {item["rule_id"] for item in resolved.data["resolved"]})

    def test_alert_notify_routes_failures_to_dedicated_channels(self) -> None:
        alerts = [
            SystemAlert(
                alert_id="alert_failure_ocr",
                rule_id="alert_open_manual_reviews",
                metric="counts.open_manual_reviews",
                value=1,
                threshold=0,
                severity="high",
                status="open",
                message="OCR parser failure requires review",
                owner="NLP/ML 负责人",
                playbook_id="pb_document_parser_failure",
            ),
            SystemAlert(
                alert_id="alert_failure_ingestion",
                rule_id="alert_data_ingestion_failure",
                metric="ingestion_jobs.failed",
                value=1,
                threshold=0,
                severity="high",
                status="open",
                message="ingestion connector failed",
                owner="数据工程",
                playbook_id="pb_data_ingestion_failure",
            ),
            SystemAlert(
                alert_id="alert_failure_search",
                rule_id="alert_search_degradation",
                metric="search.recall_drop",
                value=1,
                threshold=0,
                severity="medium",
                status="open",
                message="semantic search degraded",
                owner="平台负责人",
                playbook_id="pb_search_degradation",
            ),
            SystemAlert(
                alert_id="alert_failure_llm",
                rule_id="alert_llm_error_rate",
                metric="llm_tasks.error_rate",
                value=0.5,
                threshold=0.2,
                severity="medium",
                status="open",
                message="LLM gateway failure",
                owner="NLP/ML 负责人",
                playbook_id="pb_llm_gateway_failure",
            ),
        ]
        for alert in alerts:
            self.service.store.system_alerts[alert.alert_id] = alert

        notified = self.router.dispatch(
            "POST",
            "/api/alerts/notify",
            {
                "route_failures": True,
                "mark_sent": False,
                "failure_routes": {
                    "ingestion": {"channel": "email", "target": "data-oncall@example.invalid", "provider": "email", "max_attempts": 4},
                    "search": {"channel": "slack", "target": "https://hooks.slack.example.invalid/search", "provider": "slack"},
                    "llm": {"channel": "webhook", "target": "https://ops.example.invalid/llm", "provider": "webhook"},
                    "ocr": {"channel": "email", "target": "ocr-oncall@example.invalid", "provider": "email"},
                },
            },
            role="risk_compliance",
        )
        self.assertTrue(notified.success, notified.error)
        rows = {item["alert_id"]: item for item in notified.data["notifications"]}
        self.assertEqual(rows["alert_failure_ocr"]["channel"], "email")
        self.assertEqual(rows["alert_failure_ocr"]["payload"]["route_key"], "ocr")
        self.assertEqual(rows["alert_failure_ingestion"]["target"], "data-oncall@example.invalid")
        self.assertEqual(rows["alert_failure_ingestion"]["payload"]["delivery_policy"]["provider"], "email")
        self.assertEqual(rows["alert_failure_ingestion"]["payload"]["delivery_policy"]["max_attempts"], 4)
        self.assertEqual(rows["alert_failure_search"]["channel"], "slack")
        self.assertEqual(rows["alert_failure_llm"]["payload"]["route_key"], "llm")

        delivered = self.router.dispatch(
            "POST",
            "/api/alerts/notifications/deliver",
            {"notification_ids": [rows["alert_failure_ingestion"]["notification_id"]], "execute": True},
            role="risk_compliance",
        )
        self.assertTrue(delivered.success, delivered.error)
        self.assertEqual(delivered.data["notifications"][0]["delivery_provider"], "email")
        self.assertEqual(delivered.data["notifications"][0]["delivery_status"], "failed")
        self.assertEqual(delivered.data["notifications"][0]["error"], "smtp_host_required")

    def test_alert_notification_webhook_sender_posts_payload_and_records_response(self) -> None:
        self.service.store.alert_notifications["aln_webhook_success"] = AlertNotification(
            notification_id="aln_webhook_success",
            alert_id="alert_webhook_success",
            channel="webhook",
            target="https://alerts.example.invalid/hook",
            status="pending",
            payload={"message": "review source governance"},
        )
        self.service.store.alert_notifications["aln_webhook_bad_target"] = AlertNotification(
            notification_id="aln_webhook_bad_target",
            alert_id="alert_webhook_bad_target",
            channel="webhook",
            target="slack://risk-channel",
            status="pending",
            payload={"message": "invalid webhook target"},
        )

        calls = []

        class FakeResponse:
            status = 202

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self, limit=-1):
                return b'{"queued":true}'

        original_urlopen = services_module.urlopen

        def fake_urlopen(request, timeout=0):
            calls.append((request, timeout))
            return FakeResponse()

        services_module.urlopen = fake_urlopen
        try:
            delivered = self.router.dispatch(
                "POST",
                "/api/alerts/notifications/deliver",
                {
                    "notification_ids": ["aln_webhook_success"],
                    "execute": True,
                    "provider": "webhook",
                    "timeout_ms": 2500,
                    "headers": {"X-Delivery-Test": "yes"},
                },
                role="risk_compliance",
            )
        finally:
            services_module.urlopen = original_urlopen

        self.assertTrue(delivered.success, delivered.error)
        self.assertEqual(delivered.data["delivered_count"], 1)
        self.assertEqual(delivered.data["failed_count"], 0)
        self.assertEqual(len(calls), 1)
        request, timeout = calls[0]
        self.assertEqual(timeout, 2.5)
        request_body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(request_body["notification_id"], "aln_webhook_success")
        self.assertEqual(request_body["payload"]["message"], "review source governance")
        sent_notification = self.service.store.alert_notifications["aln_webhook_success"]
        self.assertEqual(sent_notification.status, "sent")
        self.assertEqual(sent_notification.payload["delivery_response"]["status_code"], 202)
        self.assertIn("queued", sent_notification.payload["delivery_response"]["body"])

        failed = self.router.dispatch(
            "POST",
            "/api/alerts/notifications/deliver",
            {"notification_ids": ["aln_webhook_bad_target"], "execute": True, "provider": "webhook"},
            role="risk_compliance",
        )
        self.assertTrue(failed.success, failed.error)
        self.assertEqual(failed.data["delivered_count"], 0)
        self.assertEqual(failed.data["failed_count"], 1)
        bad_target = self.service.store.alert_notifications["aln_webhook_bad_target"]
        self.assertEqual(bad_target.status, "failed")
        self.assertEqual(bad_target.payload["delivery_error"], "webhook_target_must_be_http_or_https")

    def test_alert_notification_email_and_slack_senders_execute(self) -> None:
        self.service.store.alert_notifications["aln_email_success"] = AlertNotification(
            notification_id="aln_email_success",
            alert_id="alert_email_success",
            channel="email",
            target="risk@example.invalid;ops@example.invalid",
            status="pending",
            payload={"message": "review budget approval", "severity": "high", "owner": "risk"},
        )
        self.service.store.alert_notifications["aln_slack_success"] = AlertNotification(
            notification_id="aln_slack_success",
            alert_id="alert_slack_success",
            channel="slack",
            target="https://hooks.slack.example.invalid/services/test",
            status="pending",
            payload={"message": "LLM budget critical", "severity": "critical"},
        )
        smtp_calls = []

        class FakeSMTP:
            def __init__(self, host, port, timeout=0):
                self.host = host
                self.port = port
                self.timeout = timeout
                smtp_calls.append({"event": "connect", "host": host, "port": port, "timeout": timeout})

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def starttls(self):
                smtp_calls.append({"event": "starttls"})

            def login(self, username, password):
                smtp_calls.append({"event": "login", "username": username, "password": password})

            def send_message(self, message):
                smtp_calls.append({"event": "send_message", "subject": message["Subject"], "to": message["To"], "body": message.get_content()})

        original_smtp = services_module.SMTP
        services_module.SMTP = FakeSMTP
        try:
            email_delivery = self.router.dispatch(
                "POST",
                "/api/alerts/notifications/deliver",
                {
                    "notification_ids": ["aln_email_success"],
                    "execute": True,
                    "provider": "email",
                    "smtp_host": "smtp.example.invalid",
                    "smtp_port": 2525,
                    "smtp_ssl": False,
                    "smtp_starttls": True,
                    "smtp_username": "alerts@example.invalid",
                    "smtp_password": "not-real",
                    "from_address": "alerts@example.invalid",
                    "subject": "Budget approval required",
                    "timeout_ms": 3000,
                },
                role="risk_compliance",
            )
        finally:
            services_module.SMTP = original_smtp
        self.assertTrue(email_delivery.success, email_delivery.error)
        self.assertEqual(email_delivery.data["delivered_count"], 1)
        self.assertEqual(self.service.store.alert_notifications["aln_email_success"].status, "sent")
        self.assertEqual(self.service.store.alert_notifications["aln_email_success"].payload["delivery_response"]["recipient_count"], 2)
        self.assertEqual(smtp_calls[0]["host"], "smtp.example.invalid")
        self.assertEqual(smtp_calls[0]["timeout"], 3.0)
        self.assertIn({"event": "starttls"}, smtp_calls)
        sent_messages = [item for item in smtp_calls if item["event"] == "send_message"]
        self.assertTrue(sent_messages)
        self.assertIn("risk@example.invalid", sent_messages[0]["to"])
        self.assertIn("review budget approval", sent_messages[0]["body"])

        slack_calls = []

        class FakeSlackResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self, limit=-1):
                return b"ok"

        original_urlopen = services_module.urlopen

        def fake_slack_urlopen(request, timeout=0):
            slack_calls.append((request, timeout))
            return FakeSlackResponse()

        services_module.urlopen = fake_slack_urlopen
        try:
            slack_delivery = self.router.dispatch(
                "POST",
                "/api/alerts/notifications/deliver",
                {"notification_ids": ["aln_slack_success"], "execute": True, "provider": "slack", "timeout_ms": 1500},
                role="risk_compliance",
            )
        finally:
            services_module.urlopen = original_urlopen
        self.assertTrue(slack_delivery.success, slack_delivery.error)
        self.assertEqual(slack_delivery.data["delivered_count"], 1)
        self.assertEqual(len(slack_calls), 1)
        slack_request, slack_timeout = slack_calls[0]
        self.assertEqual(slack_timeout, 1.5)
        slack_body = json.loads(slack_request.data.decode("utf-8"))
        self.assertIn("LLM budget critical", slack_body["text"])
        self.assertEqual(slack_body["metadata"]["event_payload"]["notification_id"], "aln_slack_success")
        self.assertEqual(self.service.store.alert_notifications["aln_slack_success"].payload["delivery_response"]["mode"], "slack")

    def test_observability_exports_structured_and_opentelemetry_logs(self) -> None:
        workflow = self.router.dispatch(
            "POST",
            "/api/orchestration/dags",
            {
                "dag_id": "dag_observability",
                "name": "Observability smoke",
                "tasks": [{"task_id": "collect", "task_type": "noop"}],
                "owner_role": "平台负责人",
            },
            role="platform",
        )
        self.assertTrue(workflow.success, workflow.error)
        workflow_run = self.router.dispatch(
            "POST",
            "/api/orchestration/dags/dag_observability/run",
            {
                "run_id": "wfrun_observability_001",
                "status": "failed",
                "task_statuses": {"collect": "failed"},
                "error": "collector unavailable",
            },
            role="platform",
        )
        self.assertTrue(workflow_run.success, workflow_run.error)
        self.service.store.system_alerts["alert_otel_failure"] = SystemAlert(
            alert_id="alert_otel_failure",
            rule_id="alert_workflow_failure",
            metric="workflow.failed_runs",
            value=1,
            threshold=0,
            severity="high",
            status="open",
            message="workflow collector failed",
            owner="平台负责人",
            playbook_id="pb_data_ingestion_failure",
        )
        self.service.store.alert_notifications["aln_observability_pending"] = AlertNotification(
            notification_id="aln_observability_pending",
            alert_id="alert_otel_failure",
            channel="ops",
            target="ops-desk",
            status="pending",
            payload={"delivery_provider": "dry-run-sender", "delivery_attempts": 0},
        )

        logs = self.router.dispatch(
            "POST",
            "/api/observability/logs/export",
            {"sources": "audit alerts workflow notifications", "limit": 50, "record_export": True},
            role="platform",
        )
        self.assertTrue(logs.success, logs.error)
        self.assertEqual(logs.data["adapter"]["format"], "structured_json_logs")
        self.assertEqual(logs.data["adapter"]["schema_version"], "ai_quant.observability.logs.v1")
        self.assertGreaterEqual(logs.data["count"], 4)
        events = {item["event"] for item in logs.data["logs"]}
        self.assertIn("workflow_run", events)
        self.assertIn("system_alert", events)
        self.assertIn("alert_notification", events)
        self.assertIn("run_workflow_definition", events)
        self.assertTrue(logs.data["content_sha256"])
        self.assertEqual(self.service.store.audit_log[-1].action, "export_structured_logs")

        otel = self.router.dispatch(
            "POST",
            "/api/observability/otel/export",
            {"sources": ["alerts", "workflow"], "service_name": "ai-quant-test", "environment": "test", "record_export": True},
            role="platform",
        )
        self.assertTrue(otel.success, otel.error)
        self.assertEqual(otel.data["adapter"]["format"], "otlp_logs_json")
        self.assertGreaterEqual(otel.data["log_count"], 2)
        resource = otel.data["resourceLogs"][0]["resource"]["attributes"]
        self.assertIn({"key": "service.name", "value": {"stringValue": "ai-quant-test"}}, resource)
        self.assertIn({"key": "deployment.environment", "value": {"stringValue": "test"}}, resource)
        log_records = otel.data["resourceLogs"][0]["scopeLogs"][0]["logRecords"]
        self.assertIn("ERROR", {item["severityText"] for item in log_records})
        flattened_attributes = {
            attribute["key"]: attribute["value"]
            for record in log_records
            for attribute in record["attributes"]
        }
        self.assertIn("ai_quant.status", flattened_attributes)
        self.assertEqual(self.service.store.audit_log[-1].action, "export_opentelemetry_logs")

        submitted = self.router.dispatch(
            "POST",
            "/api/observability/otel/submit",
            {
                "sources": ["alerts", "workflow"],
                "target": "https://otel.example.invalid/v1/logs",
                "provider": "webhook",
                "max_delivery_attempts": 2,
            },
            role="platform",
        )
        self.assertTrue(submitted.success, submitted.error)
        self.assertEqual(submitted.data["count"], 1)
        notification = submitted.data["notifications"][0]
        self.assertEqual(notification["channel"], "opentelemetry_logs_outbox")
        self.assertEqual(notification["payload"]["type"], "opentelemetry_logs_submission")
        self.assertEqual(notification["payload"]["delivery_policy"]["provider"], "webhook")
        self.assertEqual(notification["payload"]["delivery_policy"]["max_attempts"], 2)

        duplicate = self.router.dispatch(
            "POST",
            "/api/observability/otel/submit",
            {"sources": ["alerts", "workflow"], "target": "https://otel.example.invalid/v1/logs", "provider": "webhook"},
            role="platform",
        )
        self.assertTrue(duplicate.success, duplicate.error)
        self.assertEqual(duplicate.data["skipped_count"], 1)

        delivered = self.router.dispatch(
            "POST",
            "/api/alerts/notifications/deliver",
            {"notification_ids": [notification["notification_id"]], "execute": True, "provider": "dry-run-otel"},
            role="platform",
        )
        self.assertTrue(delivered.success, delivered.error)
        self.assertEqual(delivered.data["delivered_count"], 1)
        stored = self.service.store.alert_notifications[notification["notification_id"]]
        self.assertEqual(stored.status, "sent")
        self.assertEqual(stored.payload["delivery_provider"], "dry-run-otel")

    def test_secret_rotation_records_are_metadata_only_and_alert_overdue(self) -> None:
        rotation = self.router.dispatch(
            "POST",
            "/api/governance/secret-rotations",
            {
                "rotation_id": "secrot_llm_2026q1",
                "secret_name": "AI_QUANT_LLM_API_KEY",
                "provider": "vault",
                "owner": "platform_owner",
                "status": "rotated",
                "rotated_at": "2026-01-01T00:00:00+00:00",
                "next_rotation_due_at": "2020-04-01T00:00:00+00:00",
                "evidence_uri": "vault://rotation/llm/2026q1",
            },
            actor="platform_owner",
            role="platform",
        )
        self.assertTrue(rotation.success, rotation.error)
        self.assertEqual(rotation.data["secret_name"], "AI_QUANT_LLM_API_KEY")

        blocked = self.router.dispatch(
            "POST",
            "/api/governance/secret-rotations",
            {
                "rotation_id": "secrot_bad",
                "secret_name": "bad",
                "provider": "vault",
                "owner": "platform_owner",
                "api_key": "placeholder-key-should-not-be-stored",
            },
            actor="platform_owner",
            role="platform",
        )
        self.assertFalse(blocked.success)
        self.assertEqual(blocked.status_code, 422)

        listed = self.router.dispatch("GET", "/api/governance/secret-rotations", {"as_of": "2026-05-15T00:00:00+00:00"}, role="risk_compliance")
        self.assertTrue(listed.success, listed.error)
        self.assertEqual(listed.data["overdue"], 1)
        self.assertTrue(listed.data["rotations"][0]["overdue"])

        self.router.dispatch("POST", "/api/alerts/rules/seed", {}, role="risk_compliance")
        alerts = self.router.dispatch("POST", "/api/alerts/evaluate", {}, role="risk_compliance")
        self.assertIn("alert_secret_rotation_overdue", {item["rule_id"] for item in alerts.data["alerts"]})

    def test_cache_retention_report_records_delete_policy_review(self) -> None:
        self.router.dispatch("POST", "/api/ingestion/sources/seed", {}, actor="data", role="data_engineer")
        sec_policy = self.router.dispatch(
            "POST",
            "/api/governance/sources/src_sec",
            {
                "retention_policy": "retain_public_filings_short_cache_for_test",
                "cache_ttl_days": 1,
                "provenance_ref": "https://www.sec.gov/Archives/demo",
                "source_tos_uri": "https://www.sec.gov/os/accessing-edgar-data",
                "usage_scope": "public_filings_internal_research",
                "collection_method": "official_public_endpoint",
                "robots_policy": "robots_and_tos_reviewed_2026q2",
                "last_reviewed_at": "2026-05-01T00:00:00+00:00",
            },
            actor="risk",
            role="risk_compliance",
        )
        self.assertTrue(sec_policy.success, sec_policy.error)
        self.assertEqual(sec_policy.data["cache_ttl_days"], 1)

        local_policy = self.router.dispatch(
            "POST",
            "/api/governance/sources/local_research_reports",
            {
                "retention_policy": "manual_reference_only_no_cache",
                "cache_ttl_days": 0,
                "provenance_ref": "local://research-reports/cache-policy-test",
                "source_tos_uri": "internal://manual-review/local-research-cache-policy",
                "usage_scope": "manual_reference_metadata_only",
                "collection_method": "local_filesystem",
                "robots_policy": "not_applicable_local_filesystem",
                "last_reviewed_at": "2026-05-01T00:00:00+00:00",
            },
            actor="risk",
            role="risk_compliance",
        )
        self.assertTrue(local_policy.success, local_policy.error)
        self.assertEqual(local_policy.data["cache_ttl_days"], 0)

        expired_doc = self.service.ingest_document(
            {
                "document_id": "doc_cache_expired",
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "source_id": "src_sec",
                "source_type": "regulatory",
                "document_type": "annual_report",
                "title": "Expired public filing cache",
                "source_uri": "https://www.sec.gov/Archives/demo/doc-cache-expired",
                "published_at": "2026-05-01T00:00:00+00:00",
                "ingested_at": "2026-05-01T00:00:00+00:00",
                "body": "Public annual report body cached for retention policy validation.",
                "rights_tag": {
                    "license_class": "public",
                    "training_allowed": False,
                    "redistribution_allowed": False,
                    "display_use": "allowed",
                    "non_display_use": "restricted",
                    "derived_data_use": "restricted",
                },
            },
            actor="data",
        )
        self.assertTrue(Path(expired_doc.object_uri).exists())

        with TemporaryDirectory() as temp_dir:
            report_dir = Path(temp_dir) / "Goldman" / "2026" / "05"
            report_dir.mkdir(parents=True)
            report_path = report_dir / "Cache policy note.txt"
            report_path.write_text("Local broker note retained as metadata-only reference.", encoding="utf-8")
            scanned = self.router.dispatch(
                "POST",
                "/api/research-reports/scan",
                {"root_path": temp_dir, "extensions": [".txt"], "hash_files": True, "per_broker_sources": False, "limit": 10},
                actor="data",
                role="data_engineer",
            )
            self.assertTrue(scanned.success, scanned.error)
            report_id = scanned.data["reports"][0]["report_id"]

            self.service.document_parse_cache["runtime_cache_old"] = {
                "cached_at": "2026-05-01T00:00:00+00:00",
                "model": "paddleocr-vl",
                "job_id": "job_cache_old",
                "page_count": 1,
            }

            report = self.router.dispatch(
                "POST",
                "/api/governance/cache-retention-report",
                {
                    "as_of": "2026-05-15T00:00:00+00:00",
                    "include_retained": False,
                    "record_run": True,
                    "execute": True,
                    "run_id": "crun_cache_policy_2026q2",
                    "limit": 20,
                },
                actor="risk",
                role="risk_compliance",
            )
            self.assertTrue(report.success, report.error)
            self.assertTrue(report.data["dry_run"])
            self.assertTrue(report.data["execute_requested"])
            self.assertEqual(report.data["status"], "approval_required")
            self.assertEqual(report.data["run"]["run_id"], "crun_cache_policy_2026q2")
            self.assertIn("governance_evidence", report.data["usage_boundary"])
            self.assertGreaterEqual(report.data["deletion_required_count"], 3)
            self.assertGreaterEqual(report.data["expired_count"], 2)
            self.assertGreaterEqual(report.data["no_cache_count"], 1)
            self.assertTrue(report.data["external_execution_required"])

            rows = {item["resource_id"]: item for item in report.data["records"]}
            self.assertEqual(rows["doc_cache_expired"]["action"], "delete_cache")
            self.assertEqual(rows["doc_cache_expired"]["source_id"], "src_sec")
            self.assertEqual(rows[report_id]["action"], "metadata_only_or_delete_cache")
            self.assertEqual(rows[report_id]["source_id"], "local_research_reports")
            self.assertEqual(rows["runtime_cache_old"]["action"], "delete_runtime_cache")
            self.assertEqual(rows["runtime_cache_old"]["resource_type"], "document_parse_cache")

            self.assertIn("crun_cache_policy_2026q2", self.service.store.cache_retention_runs)
            self.assertEqual(self.service.store.cache_retention_runs["crun_cache_policy_2026q2"].status, "approval_required")
            self.assertIn("runtime_cache_old", self.service.document_parse_cache)
            self.assertIn(report_id, self.service.store.research_reports)
            self.assertTrue(Path(expired_doc.object_uri).exists())
            self.assertIn("record_cache_retention_run", {item.action for item in self.service.store.audit_log})

            executed = self.router.dispatch(
                "POST",
                "/api/governance/cache-retention-runs/crun_cache_policy_2026q2/execute",
                {
                    "execute": True,
                    "provider": "local_runtime_cache_retention_executor",
                    "executed_at": "2026-05-15T00:30:00+00:00",
                    "notes": "Evict runtime cache; hand off object/search deletion to external lifecycle tools.",
                },
                actor="platform",
                role="platform",
            )
            self.assertTrue(executed.success, executed.error)
            self.assertEqual(executed.data["runtime_deleted_count"], 1)
            self.assertGreaterEqual(executed.data["external_handoff_count"], 2)
            self.assertTrue(executed.data["requires_external_handoff"])
            self.assertNotIn("runtime_cache_old", self.service.document_parse_cache)
            self.assertEqual(self.service.store.cache_retention_runs["crun_cache_policy_2026q2"].status, "approval_required")
            self.assertTrue(Path(expired_doc.object_uri).exists())
            self.assertIn(report_id, self.service.store.research_reports)
            self.assertIn("execute_cache_retention_run", {item.action for item in self.service.store.audit_log})

            execution_evidence = self.router.dispatch(
                "POST",
                "/api/governance/cache-retention-runs/crun_cache_policy_2026q2/execution-evidence",
                {
                    "evidence_uri": "s3://governance-evidence/cache-retention/2026q2.json",
                    "provider": "s3_lifecycle_and_runtime_cache_executor",
                    "deleted_count": report.data["deletion_required_count"],
                    "executed_at": "2026-05-15T01:00:00+00:00",
                    "notes": "External lifecycle job completed; app retained metadata and evidence only.",
                },
                actor="platform",
                role="platform",
            )
            self.assertTrue(execution_evidence.success, execution_evidence.error)
            self.assertEqual(execution_evidence.data["status"], "executed_outside_app")
            self.assertFalse(execution_evidence.data["dry_run"])
            self.assertEqual(execution_evidence.data["external_deleted_count"], report.data["deletion_required_count"])
            self.assertEqual(execution_evidence.data["execution_provider"], "s3_lifecycle_and_runtime_cache_executor")

            listed_runs = self.router.dispatch(
                "GET",
                "/api/governance/cache-retention-runs",
                {"status": "executed_outside_app"},
                role="risk_compliance",
            )
            self.assertTrue(listed_runs.success, listed_runs.error)
            self.assertEqual(listed_runs.data["executed_outside_app"], 1)
            self.assertEqual(listed_runs.data["runs"][0]["run_id"], "crun_cache_policy_2026q2")

    def test_alerts_create_incident_reports_from_playbooks(self) -> None:
        seeded_playbooks = self.router.dispatch("POST", "/api/playbooks/seed", {}, actor="risk", role="risk_compliance")
        self.assertTrue(seeded_playbooks.success, seeded_playbooks.error)
        self.assertGreaterEqual(len(seeded_playbooks.data["playbooks"]), 5)
        self.assertIn("pb_document_parser_failure", {item["playbook_id"] for item in seeded_playbooks.data["playbooks"]})
        self.assertGreaterEqual(len(seeded_playbooks.data["schedules"]), 5)
        schedule_id = seeded_playbooks.data["schedules"][0]["schedule_id"]
        drill_result = self.router.dispatch(
            "POST",
            f"/api/drill-schedules/{schedule_id}/result",
            {
                "result": "partial",
                "run_at": "2026-05-15T00:00:00+00:00",
                "rca_summary": "Fallback handoff was slower than expected.",
                "action_items": ["tighten escalation owner", "rerun drill next quarter"],
            },
            actor="risk",
            role="risk_compliance",
        )
        self.assertTrue(drill_result.success, drill_result.error)
        self.assertEqual(drill_result.data["last_result"], "partial")
        self.assertEqual(drill_result.data["next_run_at"], "2026-08-13T00:00:00+00:00")
        self.assertIn("tighten escalation owner", drill_result.data["action_items"])

        self.service.ingest_document(
            {
                "document_id": "doc_incident_scanned",
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "source_id": "src_sec",
                "source_type": "regulatory",
                "document_type": "10-K",
                "source_uri": "https://example.invalid/incident-scanned.pdf",
                "body": "",
                "rights_tag": {
                    "license_class": "public",
                    "training_allowed": False,
                    "redistribution_allowed": False,
                    "display_use": "allowed",
                    "non_display_use": "restricted",
                    "derived_data_use": "restricted",
                },
                "language": "en",
            },
            actor="data",
        )
        self.router.dispatch(
            "POST",
            "/api/evidence/extract",
            {"document_id": "doc_incident_scanned", "parser_version": "pdf-rule-1"},
            role="analyst",
        )
        rule = self.router.dispatch(
            "POST",
            "/api/alerts/rules",
            {
                "rule_id": "alert_parser_incident",
                "metric": "counts.open_manual_reviews",
                "operator": ">",
                "threshold": 0,
                "severity": "high",
                "owner": "NLP/ML 负责人",
                "playbook_id": "pb_document_parser_failure",
            },
            role="risk_compliance",
        )
        self.assertTrue(rule.success, rule.error)

        evaluated = self.router.dispatch("POST", "/api/alerts/evaluate", {}, role="risk_compliance")
        alert = next(item for item in evaluated.data["alerts"] if item["rule_id"] == "alert_parser_incident")
        created = self.router.dispatch(
            "POST",
            "/api/alerts/incidents/create",
            {"alert_ids": [alert["alert_id"]]},
            actor="risk",
            role="risk_compliance",
        )
        self.assertTrue(created.success, created.error)
        self.assertEqual(created.data["count"], 1)
        self.assertEqual(created.data["created"][0]["incident_type"], "document_parser_failure")

        linked_alert = self.service.store.system_alerts[alert["alert_id"]]
        self.assertTrue(linked_alert.incident_report_id.startswith("ir_"))
        calendar = self.router.dispatch("GET", "/api/incidents/calendar", {}, role="risk_compliance")
        self.assertEqual(len(calendar.data["reports"]), 1)
        calendar_schedule = next(item for item in calendar.data["schedules"] if item["schedule_id"] == schedule_id)
        self.assertEqual(calendar_schedule["last_result"], "partial")

    def test_source_review_overdue_alert_and_notification_outbox(self) -> None:
        self.router.dispatch("POST", "/api/ingestion/sources/seed", {}, actor="data", role="data_engineer")
        review = self.router.dispatch(
            "POST",
            "/api/governance/sources/local_research_reports/reviews",
            {
                "review_id": "srrev_local_research_alert",
                "reviewed_at": "2026-01-01T00:00:00+00:00",
                "status": "conditional",
                "publicness_status": "manual_reference_only",
                "tos_status": "needs_review",
                "robots_status": "reviewed_or_not_applicable",
                "usage_scope_status": "manual_reference_only",
                "next_review_due_at": "2026-05-01T00:00:00+00:00",
            },
            actor="risk",
            role="risk_compliance",
        )
        self.assertTrue(review.success, review.error)
        metrics = self.service.metrics()
        self.assertGreaterEqual(metrics["source_review_overdue"], 1)
        self.assertGreaterEqual(metrics["counts"]["source_review_overdue"], 1)

        self.router.dispatch("POST", "/api/alerts/rules/seed", {}, role="risk_compliance")
        evaluated = self.router.dispatch("POST", "/api/alerts/evaluate", {}, role="risk_compliance")
        self.assertTrue(evaluated.success, evaluated.error)
        review_alerts = [item for item in evaluated.data["alerts"] if item["rule_id"] == "alert_source_review_overdue"]
        self.assertEqual(len(review_alerts), 1)
        self.assertEqual(review_alerts[0]["owner"], "风险/合规")

        notified = self.router.dispatch(
            "POST",
            "/api/alerts/notify",
            {
                "channel": "source_review_outbox",
                "target": "risk-compliance-source-review",
                "alert_ids": [review_alerts[0]["alert_id"]],
            },
            role="risk_compliance",
        )
        self.assertTrue(notified.success, notified.error)
        self.assertEqual(notified.data["count"], 1)
        self.assertEqual(notified.data["notifications"][0]["channel"], "source_review_outbox")
        self.assertEqual(notified.data["notifications"][0]["payload"]["metric"], "source_review_overdue")

    def test_source_review_sla_escalations_notify_outbox(self) -> None:
        self.router.dispatch("POST", "/api/ingestion/sources/seed", {}, actor="data", role="data_engineer")
        self.router.dispatch(
            "POST",
            "/api/governance/sources/local_research_reports/reviews",
            {
                "review_id": "srrev_local_research_sla",
                "reviewed_at": "2026-01-01T00:00:00+00:00",
                "status": "conditional",
                "publicness_status": "manual_reference_only",
                "tos_status": "needs_review",
                "robots_status": "reviewed_or_not_applicable",
                "usage_scope_status": "manual_reference_only",
                "next_review_due_at": "2026-04-01T00:00:00+00:00",
            },
            actor="risk",
            role="risk_compliance",
        )
        escalation = self.router.dispatch(
            "GET",
            "/api/governance/source-review-escalations",
            {
                "as_of": "2026-05-15T00:00:00+00:00",
                "due_within_days": 30,
                "owner_role": "风险/合规",
                "min_severity": "medium",
                "channels": {"critical": "source_review_outbox", "high": "source_review_outbox"},
                "targets": {"critical": "risk-source-sla", "high": "risk-source-sla"},
            },
            role="risk_compliance",
        )
        self.assertTrue(escalation.success, escalation.error)
        self.assertGreaterEqual(escalation.data["escalation_count"], 1)
        self.assertTrue(escalation.data["external_delivery_ready"])
        self.assertIn("source_review_sla_escalations_are_outbox_records", escalation.data["usage_boundary"])
        local_escalations = [item for item in escalation.data["escalations"] if item["source_id"] == "local_research_reports"]
        self.assertTrue(local_escalations)
        self.assertEqual(local_escalations[0]["severity"], "critical")
        self.assertEqual(local_escalations[0]["channel"], "source_review_outbox")
        self.assertEqual(local_escalations[0]["target"], "risk-source-sla")
        self.assertIn("latest_source_tos_needs_review", local_escalations[0]["blocked_reasons"])
        self.assertEqual(local_escalations[0]["days_overdue"], 44)

        notified = self.router.dispatch(
            "POST",
            "/api/governance/source-review-escalations/notify",
            {
                "as_of": "2026-05-15T00:00:00+00:00",
                "due_within_days": 30,
                "owner_role": "风险/合规",
                "min_severity": "medium",
                "channels": {"critical": "source_review_outbox", "high": "source_review_outbox"},
                "targets": {"critical": "risk-source-sla", "high": "risk-source-sla"},
                "max_delivery_attempts": 2,
            },
            actor="risk",
            role="risk_compliance",
        )
        self.assertTrue(notified.success, notified.error)
        self.assertGreaterEqual(notified.data["count"], 1)
        source_notifications = [item for item in notified.data["notifications"] if item["payload"]["source_id"] == "local_research_reports"]
        self.assertTrue(source_notifications)
        self.assertEqual(source_notifications[0]["payload"]["type"], "source_review_sla_escalation")
        self.assertEqual(source_notifications[0]["payload"]["severity"], "critical")
        self.assertEqual(source_notifications[0]["payload"]["delivery_policy"]["retry_policy"]["max_attempts"], 2)

    def test_llm_cost_budget_alert_uses_task_metrics(self) -> None:
        original_budget = os.environ.get("AI_QUANT_LLM_COST_BUDGET")
        os.environ["AI_QUANT_LLM_COST_BUDGET"] = "0.001"
        self.addCleanup(lambda: os.environ.pop("AI_QUANT_LLM_COST_BUDGET", None) if original_budget is None else os.environ.__setitem__("AI_QUANT_LLM_COST_BUDGET", original_budget))
        self.service.llm_gateway = LLMGateway(
            api_key="test-key",
            http_send=lambda _request, _timeout: b'{"choices":[{"message":{"content":"ok"}}]}',
        )
        self.service.create_prompt_change(
            {
                "request_id": "pr_cost_template",
                "prompt_name": "cost-check",
                "change_level": "baseline",
                "requested_by": "ml",
                "content": "Summarize {{source_text}}",
            },
            actor="ml",
        )
        self.service.approve_prompt_change("pr_cost_template", actor="risk", approved=True)
        self.service.register_llm_task_template(
            {
                "template_id": "llmtpl_cost_check",
                "task_type": "research_summary",
                "prompt_name": "cost-check",
                "content": "Summarize {{source_text}}",
                "status": "approved",
                "approved_prompt_change_id": "pr_cost_template",
                "allowed_roles": ["分析师"],
                "estimated_cost_per_1k_tokens": 1.0,
            },
            actor="ml",
        )
        run = self.router.dispatch(
            "POST",
            "/api/llm/tasks/run",
            {
                "run_id": "llmrun_cost_alert",
                "template_id": "llmtpl_cost_check",
                "role": "分析师",
                "variables": {"source_text": "cost budget " * 500},
            },
            role="analyst",
        )
        self.assertTrue(run.success, run.error)
        metrics = self.router.dispatch("GET", "/api/llm/tasks/metrics", {}, role="nlp_ml")
        self.assertGreaterEqual(metrics.data["cost_budget_used"], 1.0)

        self.router.dispatch("POST", "/api/alerts/rules/seed", {}, role="risk_compliance")
        evaluated = self.router.dispatch("POST", "/api/alerts/evaluate", {}, role="risk_compliance")
        self.assertTrue(evaluated.success, evaluated.error)
        self.assertIn("alert_llm_cost_budget", {item["rule_id"] for item in evaluated.data["alerts"]})

    def test_llm_budget_approval_flow_raises_effective_budget(self) -> None:
        original_budget = os.environ.get("AI_QUANT_LLM_COST_BUDGET")
        os.environ["AI_QUANT_LLM_COST_BUDGET"] = "0.001"
        self.addCleanup(lambda: os.environ.pop("AI_QUANT_LLM_COST_BUDGET", None) if original_budget is None else os.environ.__setitem__("AI_QUANT_LLM_COST_BUDGET", original_budget))
        self.service.llm_gateway = LLMGateway(
            api_key="test-key",
            http_send=lambda _request, _timeout: b'{"choices":[{"message":{"content":"ok"}}]}',
        )
        self.service.create_prompt_change(
            {
                "request_id": "pr_budget_approval",
                "prompt_name": "budget-approval",
                "change_level": "baseline",
                "requested_by": "ml",
                "content": "Summarize {{source_text}}",
            },
            actor="ml",
        )
        self.service.approve_prompt_change("pr_budget_approval", actor="risk", approved=True)
        self.service.register_llm_task_template(
            {
                "template_id": "llmtpl_budget_approval",
                "task_type": "research_summary",
                "prompt_name": "budget-approval",
                "content": "Summarize {{source_text}}",
                "status": "approved",
                "approved_prompt_change_id": "pr_budget_approval",
                "allowed_roles": ["分析师"],
                "estimated_cost_per_1k_tokens": 1.0,
            },
            actor="ml",
        )
        run = self.router.dispatch(
            "POST",
            "/api/llm/tasks/run",
            {
                "run_id": "llmrun_budget_approval",
                "template_id": "llmtpl_budget_approval",
                "role": "分析师",
                "variables": {"source_text": "budget approval " * 500},
            },
            role="analyst",
        )
        self.assertTrue(run.success, run.error)
        before = self.router.dispatch("GET", "/api/llm/tasks/metrics", {}, role="nlp_ml")
        self.assertTrue(before.success, before.error)
        self.assertEqual(before.data["cost_budget"], 0.001)
        self.assertGreaterEqual(before.data["cost_budget_used"], 1.0)

        escalation = self.router.dispatch(
            "GET",
            "/api/llm/tasks/escalations",
            {"budget_critical_threshold": 1.0, "review_backlog_threshold": 100},
            role="nlp_ml",
        )
        self.assertTrue(escalation.success, escalation.error)
        budget_escalations = [item for item in escalation.data["escalations"] if item["reason"] == "cost_budget_critical"]
        self.assertTrue(budget_escalations)

        requested = self.router.dispatch(
            "POST",
            "/api/llm/budget-approvals",
            {
                "escalation_id": budget_escalations[0]["escalation_id"],
                "budget_critical_threshold": 1.0,
                "review_backlog_threshold": 100,
                "requested_budget": 1.0,
                "requested_by": "ml",
                "reason": "temporary production budget raise",
            },
            actor="ml",
            role="nlp_ml",
        )
        self.assertTrue(requested.success, requested.error)
        self.assertEqual(requested.data["status"], "pending")
        self.assertEqual(requested.data["current_budget"], 0.001)
        self.assertEqual(requested.data["requested_budget"], 1.0)

        approvals = self.router.dispatch("GET", "/api/llm/budget-approvals", {"status": "pending"}, role="nlp_ml")
        self.assertTrue(approvals.success, approvals.error)
        self.assertEqual(approvals.data["total"], 1)
        self.assertEqual(approvals.data["approvals"][0]["approval_id"], requested.data["approval_id"])

        decided = self.router.dispatch(
            "POST",
            f"/api/llm/budget-approvals/{requested.data['approval_id']}/decide",
            {"status": "approved", "approver_role": "CIO", "approver": "cio_owner", "comment": "approved for controlled run window"},
            actor="cio_owner",
            role="cio",
        )
        self.assertTrue(decided.success, decided.error)
        self.assertEqual(decided.data["status"], "approved")
        self.assertEqual(decided.data["approvers"][0]["role"], "CIO")

        after = self.router.dispatch("GET", "/api/llm/tasks/metrics", {}, role="nlp_ml")
        self.assertTrue(after.success, after.error)
        self.assertEqual(after.data["configured_cost_budget"], 0.001)
        self.assertEqual(after.data["cost_budget"], 1.0)
        self.assertTrue(after.data["approved_budget_active"])
        self.assertLess(after.data["cost_budget_used"], before.data["cost_budget_used"])

        synced = self.router.dispatch(
            "POST",
            f"/api/llm/budget-approvals/{requested.data['approval_id']}/sync",
            {
                "external_system": "cloud_budget",
                "channel": "webhook",
                "target": "https://budget.example.invalid/sync",
                "max_delivery_attempts": 2,
                "metadata": {"cost_center": "llm-prod"},
            },
            actor="cio_owner",
            role="cio",
        )
        self.assertTrue(synced.success, synced.error)
        self.assertTrue(synced.data["created"])
        self.assertEqual(synced.data["approval"]["linked_notification_ids"], [synced.data["notification"]["notification_id"]])
        self.assertEqual(synced.data["notification"]["status"], "pending")
        self.assertEqual(synced.data["notification"]["channel"], "webhook")
        self.assertEqual(synced.data["notification"]["payload"]["type"], "llm_budget_external_sync")
        self.assertEqual(synced.data["notification"]["payload"]["external_system"], "cloud_budget")
        self.assertEqual(synced.data["notification"]["payload"]["requested_budget"], 1.0)
        self.assertEqual(synced.data["notification"]["payload"]["delivery_policy"]["max_attempts"], 2)

    def test_router_dispatch(self) -> None:
        seeded_sources = self.router.dispatch("POST", "/api/ingestion/sources/seed", {}, role="data_engineer")
        self.assertTrue(seeded_sources.success)
        self.assertGreaterEqual(len(seeded_sources.data["sources"]), 3)

        response = self.router.dispatch(
            "POST",
            "/api/ingestion/documents",
            {
                "document_id": "doc_003",
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "source_id": "src_sec",
                "source_type": "regulatory",
                "document_type": "annual_report",
                "source_uri": "https://example.invalid/doc-003",
                "body": "Sentence one. Sentence two.",
                "rights_tag": {
                    "license_class": "public",
                    "training_allowed": False,
                    "redistribution_allowed": False,
                    "display_use": "allowed",
                    "non_display_use": "restricted",
                    "derived_data_use": "restricted",
                },
            },
            role="数据工程",
        )
        self.assertTrue(response.success)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["document_id"], "doc_003")
        self.assertTrue(response.trace_id.startswith("trace_"))
        self.assertEqual(self.service.store.audit_log[-1].trace_id, response.trace_id)

        evidence_response = self.router.dispatch(
            "POST",
            "/api/evidence/extract",
            {"document_id": "doc_003", "parser_version": "rule-1", "model_version": "rule-1"},
            role="分析师",
        )
        self.assertTrue(evidence_response.success)
        self.assertGreaterEqual(len(evidence_response.data["evidence"]), 1)

        thesis_response = self.router.dispatch(
            "POST",
            "/api/thesis/create",
            {
                "issuer_id": "issuer_001",
                "hypothesis": "Test thesis",
                "evidence_ids": [item["evidence_id"] for item in evidence_response.data["evidence"]],
                "falsifiers": [],
                "owner": "analyst",
            },
            role="分析师",
        )
        self.assertTrue(thesis_response.success)

        dashboard = self.router.dispatch("GET", "/api/dashboard/ceo", {}, role="CEO")
        self.assertTrue(dashboard.success)
        self.assertIn("counts", dashboard.data)

        preview = self.router.dispatch(
            "POST",
            "/api/connectors/preview",
            {
                "market": "U",
                "raw": {
                    "cik": "0000320193",
                    "accession_no": "0000320193-24-000123",
                    "primary_doc": "a10-k2024.htm",
                    "document_type": "10-K",
                    "title": "10-K Filing",
                    "body": "Apple filing body",
                },
            },
            role="数据工程",
        )
        self.assertTrue(preview.success)
        self.assertIn("sec.gov/Archives/edgar/data", preview.data["source_uri"])

    def test_router_blocks_unauthorized_ingestion_role(self) -> None:
        response = self.router.dispatch(
            "POST",
            "/api/ingestion/documents",
            {
                "document_id": "doc_forbidden",
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "source_id": "src_sec",
                "source_type": "regulatory",
                "document_type": "annual_report",
                "source_uri": "https://example.invalid/doc-forbidden",
                "body": "Analyst should not ingest directly.",
                "rights_tag": {
                    "license_class": "public",
                    "training_allowed": False,
                    "redistribution_allowed": False,
                    "display_use": "allowed",
                    "non_display_use": "restricted",
                    "derived_data_use": "restricted",
                },
            },
            role="分析师",
        )
        self.assertFalse(response.success)
        self.assertEqual(response.status_code, 403)
        self.assertTrue(response.trace_id.startswith("trace_"))

    def test_paddleocr_document_parsing_api_submits_url_and_collects_markdown(self) -> None:
        sent = []
        jsonl = (
            json.dumps({"result": {"layoutParsingResults": [{"markdown": {"text": "Page one markdown."}}]}})
            + "\n"
            + json.dumps({"result": {"layoutParsingResults": [{"markdown": {"text": "Page two markdown."}}]}})
        ).encode("utf-8")

        def fake_send(request, timeout):
            sent.append(
                {
                    "url": request.full_url,
                    "method": request.get_method(),
                    "timeout": timeout,
                    "headers": {key.lower(): value for key, value in request.header_items()},
                    "body": json.loads(request.data.decode("utf-8")) if request.data else {},
                }
            )
            if request.full_url.endswith("/api/v2/ocr/jobs") and request.get_method() == "POST":
                return b'{"data":{"jobId":"job_url_1"}}'
            if request.full_url.endswith("/api/v2/ocr/jobs/job_url_1"):
                return b'{"data":{"state":"done","resultUrl":{"jsonUrl":"https://result.example/url.jsonl"}}}'
            if request.full_url == "https://result.example/url.jsonl":
                return jsonl
            return b"{}"

        self.service.document_parser = PaddleOCRParser(
            token="ocr-test-token",
            model="PaddleOCR-VL-1.5",
            timeout=9,
            poll_interval=0,
            max_polls=2,
            http_send=fake_send,
        )
        response = self.router.dispatch(
            "POST",
            "/api/document-parsing/paddleocr",
            {
                "file_url": "https://reports.example/demo.pdf",
                "optional_payload": {"useChartRecognition": True},
            },
            actor="data",
            role="data_engineer",
        )
        self.assertTrue(response.success, response.error)
        self.assertEqual(response.data["job_id"], "job_url_1")
        self.assertEqual(response.data["page_count"], 2)
        self.assertIn("Page two markdown.", response.data["text"])
        self.assertEqual(sent[0]["url"], "https://paddleocr.aistudio-app.com/api/v2/ocr/jobs")
        self.assertEqual(sent[0]["headers"]["authorization"], "bearer ocr-test-token")
        self.assertEqual(sent[0]["body"]["fileUrl"], "https://reports.example/demo.pdf")
        self.assertTrue(sent[0]["body"]["optionalPayload"]["useChartRecognition"])
        self.assertEqual(self.service.store.audit_log[-1].action, "parse_document_with_paddleocr")

    def test_llm_gateway_routes_forward_openai_and_anthropic_payloads(self) -> None:
        sent = []

        def fake_send(request, timeout):
            sent.append(
                {
                    "url": request.full_url,
                    "timeout": timeout,
                    "headers": {key.lower(): value for key, value in request.header_items()},
                    "body": json.loads(request.data.decode("utf-8")),
                }
            )
            if request.full_url.endswith("/v1/messages"):
                return b'{"id":"msg_1","content":[{"type":"text","text":"pong"}]}'
            return b'{"id":"chatcmpl_1","choices":[{"message":{"content":"pong"}}]}'

        self.service.llm_gateway = LLMGateway(
            base_url="https://llm.example.test",
            api_key="test-key",
            default_model="qwen3.6-plus",
            timeout=12,
            http_send=fake_send,
        )

        openai_response = self.router.dispatch(
            "POST",
            "/api/llm/openai/chat/completions",
            {"messages": [{"role": "user", "content": "ping"}]},
            actor="analyst",
            role="analyst",
        )
        self.assertTrue(openai_response.success)
        self.assertEqual(openai_response.data["model"], "qwen3.6-plus")
        self.assertEqual(openai_response.data["response"]["id"], "chatcmpl_1")
        self.assertEqual(sent[0]["url"], "https://llm.example.test/v1/chat/completions")
        self.assertEqual(sent[0]["body"]["model"], "qwen3.6-plus")
        self.assertEqual(sent[0]["headers"]["authorization"], "Bearer test-key")

        anthropic_response = self.router.dispatch(
            "POST",
            "/api/llm/anthropic/messages",
            {"max_tokens": 256, "messages": [{"role": "user", "content": "ping"}]},
            actor="analyst",
            role="analyst",
        )
        self.assertTrue(anthropic_response.success)
        self.assertEqual(anthropic_response.data["response"]["id"], "msg_1")
        self.assertEqual(sent[1]["url"], "https://llm.example.test/v1/messages")
        self.assertEqual(sent[1]["headers"]["authorization"], "Bearer test-key")
        self.assertEqual(sent[1]["headers"]["x-api-key"], "test-key")
        self.assertEqual(sent[1]["headers"]["anthropic-version"], "2023-06-01")
        self.assertEqual(self.service.store.audit_log[-1].action, "llm_anthropic_messages")

    def test_llm_gateway_requires_api_key(self) -> None:
        self.service.llm_gateway = LLMGateway(api_key="", http_send=lambda _request, _timeout: b"{}")
        response = self.router.dispatch(
            "POST",
            "/api/llm/openai/chat/completions",
            {"messages": [{"role": "user", "content": "ping"}]},
            actor="analyst",
            role="analyst",
        )
        self.assertFalse(response.success)
        self.assertEqual(response.status_code, 422)
        self.assertIn("AI_QUANT_LLM_API_KEY", response.error["message"])

    def test_llm_task_templates_run_with_audited_cost_and_latency(self) -> None:
        sent = []

        def fake_send(request, timeout):
            sent.append({"url": request.full_url, "body": json.loads(request.data.decode("utf-8")), "timeout": timeout})
            return '{"id":"chatcmpl_task","choices":[{"message":{"content":"中文摘要：Revenue rose."}}]}'.encode("utf-8")

        self.service.llm_gateway = LLMGateway(
            base_url="https://llm.example.test",
            api_key="test-key",
            default_model="qwen3.6-plus",
            http_send=fake_send,
        )
        seeded = self.router.dispatch("POST", "/api/llm/task-templates/seed", {}, actor="ml", role="nlp_ml")
        self.assertTrue(seeded.success)
        self.assertGreaterEqual(len(seeded.data["templates"]), 6)
        self.assertEqual(self.service.store.llm_task_templates["llmtpl_filing_qa_v1"].status, "approved")
        self.assertEqual(self.service.store.llm_task_templates["llmtpl_red_team_v1"].risk_level, "critical")
        self.assertIn("acceptance_thresholds", self.service.store.llm_task_templates["llmtpl_research_report_summary_v1"].output_schema)

        run = self.router.dispatch(
            "POST",
            "/api/llm/tasks/run",
            {
                "run_id": "llmrun_filing_001",
                "template_id": "llmtpl_filing_qa_v1",
                "role": "分析师",
                "variables": {"question": "What changed?", "source_text": "Revenue rose 12% year over year."},
                "temperature": 0.1,
            },
            actor="analyst",
            role="analyst",
        )
        self.assertTrue(run.success)
        self.assertEqual(run.data["status"], "succeeded")
        self.assertEqual(run.data["model"], "qwen3.6-plus")
        self.assertEqual(run.data["prompt_version"], "pr_llmtpl_filing_qa_v1_baseline")
        self.assertFalse(run.data["human_review_required"])
        self.assertEqual(sent[0]["url"], "https://llm.example.test/v1/chat/completions")
        self.assertIn("Revenue rose 12%", sent[0]["body"]["messages"][0]["content"])
        self.assertGreaterEqual(run.data["estimated_input_tokens"], 1)
        self.assertEqual(self.service.store.audit_log[-1].action, "run_llm_task")

        metrics = self.router.dispatch("GET", "/api/llm/tasks/metrics", {}, role="nlp_ml")
        self.assertTrue(metrics.success)
        self.assertEqual(metrics.data["runs"], 1)
        self.assertEqual(metrics.data["failed_runs"], 0)

    def test_llm_task_falls_back_to_rule_summary_when_gateway_unavailable(self) -> None:
        self.service.llm_gateway = LLMGateway(api_key="", http_send=lambda _request, _timeout: b"{}")
        self.router.dispatch("POST", "/api/llm/task-templates/seed", {}, actor="ml", role="nlp_ml")
        run = self.router.dispatch(
            "POST",
            "/api/llm/tasks/run",
            {
                "run_id": "llmrun_fallback_001",
                "template_id": "llmtpl_research_summary_v1",
                "role": "分析师",
                "variables": {"source_text": "Authorized evidence says revenue improved and margin expanded."},
            },
            actor="analyst",
            role="analyst",
        )
        self.assertTrue(run.success)
        self.assertEqual(run.data["status"], "fallback")
        self.assertEqual(run.data["fallback_used"], "rule_summary")
        self.assertTrue(run.data["human_review_required"])
        self.assertIn("AI_QUANT_LLM_API_KEY", run.data["error"])

        queue = self.router.dispatch("GET", "/api/llm/tasks/review-queue", {"reason": "fallback_rule_summary"}, role="nlp_ml")
        self.assertTrue(queue.success, queue.error)
        self.assertEqual(queue.data["pending_review"], 1)
        self.assertEqual(queue.data["runs"][0]["run_id"], "llmrun_fallback_001")
        self.assertIn("upstream_error", queue.data["runs"][0]["reasons"])
        self.assertEqual(queue.data["runs"][0]["review_severity"], "medium")
        self.assertIn("fallback_rule_summary", queue.data["reason_counts"])

        escalation = self.router.dispatch(
            "GET",
            "/api/llm/tasks/escalations",
            {
                "fallback_rate_threshold": 0.0,
                "review_backlog_threshold": 0,
                "channels": {"medium": "llm_review_outbox"},
                "targets": {"medium": "llm-review-owner"},
            },
            role="nlp_ml",
        )
        self.assertTrue(escalation.success, escalation.error)
        self.assertGreaterEqual(escalation.data["escalation_count"], 1)
        self.assertTrue(escalation.data["external_delivery_ready"])
        self.assertIn("llm_sla_escalations_are_outbox_records", escalation.data["usage_boundary"])
        run_escalations = [item for item in escalation.data["escalations"] if item.get("run_id") == "llmrun_fallback_001"]
        self.assertTrue(run_escalations)
        self.assertEqual(run_escalations[0]["channel"], "llm_review_outbox")
        self.assertEqual(run_escalations[0]["target"], "llm-review-owner")

        notified = self.router.dispatch(
            "POST",
            "/api/llm/tasks/escalations/notify",
            {
                "fallback_rate_threshold": 0.0,
                "review_backlog_threshold": 0,
                "channels": {"medium": "llm_review_outbox"},
                "targets": {"medium": "llm-review-owner"},
            },
            role="nlp_ml",
        )
        self.assertTrue(notified.success, notified.error)
        self.assertGreaterEqual(notified.data["count"], 1)
        llm_review_notifications = [item for item in notified.data["notifications"] if item["channel"] == "llm_review_outbox"]
        self.assertTrue(llm_review_notifications)
        self.assertEqual(llm_review_notifications[0]["status"], "pending")
        self.assertEqual(llm_review_notifications[0]["payload"]["type"], "llm_task_escalation")

    def test_workflow_lineage_and_model_version_records_are_idempotent(self) -> None:
        workflow = self.router.dispatch(
            "POST",
            "/api/orchestration/dags",
            {
                "dag_id": "dag_daily_research",
                "name": "Daily research pipeline",
                "cadence": "daily",
                "idempotency_key_fields": ["as_of_date"],
                "tasks": [
                    {"task_id": "collect_filings", "owner": "数据工程", "sla_minutes": 30},
                    {
                        "task_id": "extract_evidence",
                        "owner": "NLP/ML 负责人",
                        "sla_minutes": 15,
                        "depends_on": ["collect_filings"],
                        "input_refs": ["doc:doc_demo"],
                        "output_refs": ["dataset:evidence_chunks"],
                    },
                    {
                        "task_id": "index_evidence",
                        "owner": "平台负责人",
                        "sla_minutes": 20,
                        "depends_on": "extract_evidence missing_external_sensor",
                    },
                ],
            },
            actor="platform",
            role="platform",
        )
        self.assertTrue(workflow.success)

        first_run = self.router.dispatch(
            "POST",
            "/api/orchestration/dags/dag_daily_research/run",
            {
                "run_id": "wfrun_daily_001",
                "inputs": {"as_of_date": "2026-05-15", "market": "A"},
                "started_at": "2026-05-15T09:00:00+00:00",
                "completed_at": "2026-05-15T09:05:00+00:00",
            },
            actor="platform",
            role="platform",
        )
        self.assertTrue(first_run.success)
        self.assertEqual(first_run.data["status"], "succeeded")
        self.assertEqual(first_run.data["task_statuses"]["collect_filings"], "succeeded")

        second_run = self.router.dispatch(
            "POST",
            "/api/orchestration/dags/dag_daily_research/run",
            {"run_id": "wfrun_daily_duplicate", "inputs": {"as_of_date": "2026-05-15", "market": "U"}},
            actor="platform",
            role="platform",
        )
        self.assertTrue(second_run.success)
        self.assertEqual(second_run.data["run_id"], "wfrun_daily_001")

        schedule_calendar = self.router.dispatch(
            "GET",
            "/api/orchestration/schedule-calendar",
            {"as_of": "2026-05-15T12:00:00+00:00", "horizon_days": 3},
            role="platform",
        )
        self.assertTrue(schedule_calendar.success, schedule_calendar.error)
        daily_schedule = next(item for item in schedule_calendar.data["workflows"] if item["dag_id"] == "dag_daily_research")
        self.assertEqual(daily_schedule["next_run_at"], "2026-05-16T09:00:00+00:00")
        self.assertEqual(len(daily_schedule["upcoming_runs"]), 3)
        self.assertEqual(schedule_calendar.data["adapter_recommendation"]["current_phase"], "lightweight_scheduler")

        model_version = self.router.dispatch(
            "POST",
            "/api/model-versions",
            {
                "model_version_id": "modelv_summary_001",
                "model_name": "research-summary",
                "version": "2026-05-15",
                "model_type": "llm",
                "artifact_uri": "models:/research-summary/2026-05-15",
                "training_dataset_ids": ["evidence_chunks"],
                "prompt_versions": ["pr_llmtpl_research_summary_v1_baseline"],
                "metrics": {"coverage": 0.96, "mlflow_run_id": "mlrun_summary_001"},
                "status": "approved",
            },
            actor="ml",
            role="nlp_ml",
        )
        self.assertTrue(model_version.success)

        lineage = self.router.dispatch(
            "POST",
            "/api/lineage/events",
            {
                "lineage_id": "lin_daily_001",
                "job_run_id": "wfrun_daily_001",
                "dataset": "evidence_chunks",
                "input_refs": ["doc:doc_demo"],
                "output_refs": ["evidence:evi_demo"],
                "code_version": "local-test",
                "model_versions": ["modelv_summary_001"],
                "prompt_versions": ["pr_llmtpl_research_summary_v1_baseline"],
            },
            actor="platform",
            role="platform",
        )
        self.assertTrue(lineage.success)
        self.assertEqual(lineage.data["dataset"], "evidence_chunks")
        self.assertEqual(self.service.store.audit_log[-1].action, "record_lineage_event")

        dependency_graph = self.router.dispatch(
            "POST",
            "/api/orchestration/dependency-graph",
            {"dag_id": "dag_daily_research"},
            role="platform",
        )
        self.assertTrue(dependency_graph.success, dependency_graph.error)
        self.assertEqual(dependency_graph.data["workflow_count"], 1)
        self.assertEqual(dependency_graph.data["task_count"], 3)
        self.assertEqual(dependency_graph.data["edge_count"], 3)
        self.assertEqual(dependency_graph.data["unresolved_dependency_count"], 1)
        self.assertIn("dependency_graph_is_visualization", dependency_graph.data["usage_boundary"])
        graph = dependency_graph.data["graphs"][0]
        self.assertEqual(graph["topological_order"][:3], ["collect_filings", "extract_evidence", "index_evidence"])
        self.assertEqual(graph["latest_run_id"], "wfrun_daily_001")
        self.assertEqual(graph["lineage"]["event_count"], 1)
        self.assertEqual(graph["lineage"]["datasets"]["evidence_chunks"], 1)
        self.assertEqual(graph["ready_task_ids"], ["collect_filings", "extract_evidence"])
        self.assertEqual(graph["blocked_task_ids"], ["index_evidence"])
        unresolved = graph["unresolved_dependencies"][0]
        self.assertEqual(unresolved["task_id"], "index_evidence")
        self.assertEqual(unresolved["missing_dependency"], "missing_external_sensor")
        node_by_id = {item["task_id"]: item for item in graph["nodes"]}
        self.assertEqual(node_by_id["extract_evidence"]["dependents"], ["index_evidence"])
        self.assertEqual(node_by_id["index_evidence"]["depends_on"], ["extract_evidence", "missing_external_sensor"])

        openlineage_export = self.router.dispatch(
            "POST",
            "/api/orchestration/openlineage/export",
            {"dag_id": "dag_daily_research", "namespace": "ai_quant_test", "record_export": True},
            actor="platform",
            role="platform",
        )
        self.assertTrue(openlineage_export.success, openlineage_export.error)
        self.assertEqual(openlineage_export.data["adapter"]["format"], "openlineage_compatible")
        self.assertTrue(openlineage_export.data["adapter"]["external_submission_required"])
        self.assertEqual(openlineage_export.data["count"], 1)
        self.assertEqual(openlineage_export.data["lineage_event_count"], 1)
        openlineage_event = openlineage_export.data["events"][0]
        self.assertEqual(openlineage_event["eventType"], "COMPLETE")
        self.assertEqual(openlineage_event["job"]["namespace"], "ai_quant_test")
        self.assertEqual(openlineage_event["job"]["name"], "dag_daily_research")
        self.assertEqual(openlineage_event["run"]["runId"], "wfrun_daily_001")
        self.assertIn("doc:doc_demo", {item["name"] for item in openlineage_event["inputs"]})
        self.assertIn("evidence_chunks", {item["name"] for item in openlineage_event["outputs"]})
        self.assertEqual(openlineage_event["run"]["facets"]["ai_quant_run"]["taskStatuses"]["collect_filings"], "succeeded")
        self.assertEqual(openlineage_event["run"]["facets"]["ai_quant_lineage"]["modelVersions"], ["modelv_summary_001"])
        self.assertEqual(openlineage_event["run"]["facets"]["ai_quant_models"]["models"][0]["model_name"], "research-summary")
        self.assertEqual(self.service.store.audit_log[-1].action, "export_openlineage_payload")

        openlineage_submit = self.router.dispatch(
            "POST",
            "/api/orchestration/openlineage/submit",
            {
                "dag_id": "dag_daily_research",
                "namespace": "ai_quant_test",
                "channel": "openlineage_submission_outbox",
                "target": "openlineage://local-catalog",
            },
            actor="platform",
            role="platform",
        )
        self.assertTrue(openlineage_submit.success, openlineage_submit.error)
        self.assertEqual(openlineage_submit.data["count"], 1)
        self.assertIn("openlineage_submissions_are_outbox_records", openlineage_submit.data["usage_boundary"])
        openlineage_notification = openlineage_submit.data["notifications"][0]
        self.assertEqual(openlineage_notification["channel"], "openlineage_submission_outbox")
        self.assertEqual(openlineage_notification["status"], "pending")
        self.assertEqual(openlineage_notification["payload"]["type"], "openlineage_submission")
        self.assertEqual(openlineage_notification["payload"]["run_id"], "wfrun_daily_001")
        self.assertTrue(openlineage_notification["payload"]["content_sha256"])
        duplicate_openlineage_submit = self.router.dispatch(
            "POST",
            "/api/orchestration/openlineage/submit",
            {"dag_id": "dag_daily_research", "namespace": "ai_quant_test"},
            actor="platform",
            role="platform",
        )
        self.assertTrue(duplicate_openlineage_submit.success, duplicate_openlineage_submit.error)
        self.assertEqual(duplicate_openlineage_submit.data["count"], 0)
        self.assertEqual(duplicate_openlineage_submit.data["skipped_count"], 1)

        mlflow_export = self.router.dispatch(
            "POST",
            "/api/model-versions/mlflow/export",
            {"model_name": "research-summary", "registered_model_prefix": "ai_quant", "record_export": True},
            actor="ml",
            role="nlp_ml",
        )
        self.assertTrue(mlflow_export.success, mlflow_export.error)
        self.assertEqual(mlflow_export.data["adapter"]["format"], "mlflow_model_registry_compatible")
        self.assertTrue(mlflow_export.data["adapter"]["external_registration_required"])
        self.assertEqual(mlflow_export.data["count"], 1)
        mlflow_model = mlflow_export.data["models"][0]
        self.assertEqual(mlflow_model["registered_model"], "ai_quant.research-summary")
        self.assertEqual(mlflow_model["source"], "models:/research-summary/2026-05-15")
        self.assertEqual(mlflow_model["run_id"], "mlrun_summary_001")
        self.assertEqual(mlflow_model["stage"], "Production")
        self.assertEqual(mlflow_model["metrics"]["coverage"], 0.96)
        self.assertEqual(mlflow_model["lineage"]["lineage_event_ids"], ["lin_daily_001"])
        self.assertEqual(mlflow_model["lineage"]["datasets"], ["evidence_chunks"])
        self.assertIn("production", mlflow_model["aliases"])
        self.assertIn("ai_quant_prompt_versions", mlflow_model["tags"])
        self.assertEqual(self.service.store.audit_log[-1].action, "export_mlflow_model_registry_payload")

        mlflow_submit = self.router.dispatch(
            "POST",
            "/api/model-versions/mlflow/register",
            {
                "model_name": "research-summary",
                "registered_model_prefix": "ai_quant",
                "channel": "mlflow_registry_outbox",
                "target": "mlflow://local-registry",
            },
            actor="ml",
            role="nlp_ml",
        )
        self.assertTrue(mlflow_submit.success, mlflow_submit.error)
        self.assertEqual(mlflow_submit.data["count"], 1)
        self.assertIn("mlflow_registrations_are_outbox_records", mlflow_submit.data["usage_boundary"])
        mlflow_notification = mlflow_submit.data["notifications"][0]
        self.assertEqual(mlflow_notification["payload"]["type"], "mlflow_model_registration")
        self.assertEqual(mlflow_notification["payload"]["model_version_id"], "modelv_summary_001")
        self.assertEqual(mlflow_notification["payload"]["registered_model"], "ai_quant.research-summary")
        self.assertEqual(mlflow_notification["payload"]["stage"], "Production")
        self.assertTrue(mlflow_notification["payload"]["content_sha256"])
        adapter_delivery = self.router.dispatch(
            "POST",
            "/api/alerts/notifications/deliver",
            {"channel": "openlineage_submission_outbox", "execute": True, "provider": "dry-run-openlineage"},
            actor="platform",
            role="platform",
        )
        self.assertTrue(adapter_delivery.success, adapter_delivery.error)
        self.assertEqual(adapter_delivery.data["delivered_count"], 1)
        delivered_openlineage = self.service.store.alert_notifications[openlineage_notification["notification_id"]]
        self.assertEqual(delivered_openlineage.status, "sent")
        self.assertEqual(delivered_openlineage.payload["delivery_provider"], "dry-run-openlineage")

        runs = self.router.dispatch("GET", "/api/orchestration/runs", {}, role="platform")
        self.assertTrue(runs.success)
        self.assertEqual(runs.data["total"], 1)
        metrics = self.router.dispatch("GET", "/api/metrics", {}, role="platform")
        self.assertEqual(metrics.data["counts"]["workflow_runs"], 1)
        self.assertEqual(metrics.data["counts"]["lineage_events"], 1)
        self.assertEqual(metrics.data["counts"]["model_versions"], 1)

        failed_run = self.router.dispatch(
            "POST",
            "/api/orchestration/dags/dag_daily_research/run",
            {
                "run_id": "wfrun_daily_failed",
                "inputs": {"as_of_date": "2026-05-16", "market": "A"},
                "status": "failed",
                "error": "extract_evidence timeout",
                "task_statuses": {"extract_evidence": "failed"},
            },
            actor="platform",
            role="platform",
        )
        self.assertTrue(failed_run.success, failed_run.error)
        self.assertEqual(failed_run.data["task_statuses"]["extract_evidence"], "failed")
        failed_metrics = self.router.dispatch("GET", "/api/metrics", {}, role="platform")
        self.assertEqual(failed_metrics.data["workflow_failed_runs"], 1)

        retry = self.router.dispatch(
            "POST",
            "/api/orchestration/runs/wfrun_daily_failed/retry",
            {"run_id": "wfrun_daily_retry", "status": "succeeded"},
            actor="platform",
            role="platform",
        )
        self.assertTrue(retry.success, retry.error)
        self.assertEqual(retry.data["inputs"]["retry_of"], "wfrun_daily_failed")
        self.assertEqual(retry.data["status"], "succeeded")

        running_run = self.router.dispatch(
            "POST",
            "/api/orchestration/dags/dag_daily_research/run",
            {
                "run_id": "wfrun_daily_running",
                "inputs": {"as_of_date": "2026-05-17", "market": "A"},
                "status": "running",
                "started_at": "2026-05-15T00:00:00+00:00",
            },
            actor="platform",
            role="platform",
        )
        self.assertTrue(running_run.success, running_run.error)
        sla_report = self.router.dispatch(
            "GET",
            "/api/orchestration/sla-report",
            {"as_of": "2026-05-15T01:00:00+00:00"},
            role="platform",
        )
        self.assertTrue(sla_report.success, sla_report.error)
        self.assertEqual(sla_report.data["breach_count"], 2)
        breaches = {row["run_id"]: row for row in sla_report.data["runs"]}
        self.assertEqual(breaches["wfrun_daily_failed"]["breach_type"], "failed_run")
        self.assertEqual(breaches["wfrun_daily_failed"]["owner"], "NLP/ML 负责人")
        self.assertEqual(breaches["wfrun_daily_running"]["breach_type"], "runtime_sla_breach")
        incidents = self.router.dispatch(
            "POST",
            "/api/orchestration/incidents/create",
            {"as_of": "2026-05-15T01:00:00+00:00"},
            actor="platform",
            role="platform",
        )
        self.assertTrue(incidents.success, incidents.error)
        self.assertEqual(incidents.data["created_count"], 2)
        self.assertIn("ir_workflow_wfrun_daily_failed", self.service.store.incident_reports)

        self.router.dispatch("POST", "/api/alerts/rules/seed", {}, role="risk_compliance")
        workflow_alerts = self.router.dispatch("POST", "/api/alerts/evaluate", {}, role="risk_compliance")
        self.assertIn("alert_workflow_failed_runs", {item["rule_id"] for item in workflow_alerts.data["alerts"]})
        self.assertIn("alert_workflow_sla_breaches", {item["rule_id"] for item in workflow_alerts.data["alerts"]})

    def test_workflow_builtin_executor_runs_fact_pipeline_tasks(self) -> None:
        benchmark = self.router.dispatch(
            "POST",
            "/api/benchmarks",
            {
                "benchmark_id": "bm_executor_fact",
                "language": "en",
                "task_type": "term_extraction",
                "sample_size": 0,
                "threshold": {
                    "term_f1": 1.0,
                    "number_recall": 1.0,
                    "period_recall": 1.0,
                    "page_hit_rate": 1.0,
                    "avg_confidence": 0.8,
                },
            },
            actor="ml",
            role="nlp_ml",
        )
        self.assertTrue(benchmark.success, benchmark.error)
        workflow = self.router.dispatch(
            "POST",
            "/api/orchestration/dags",
            {
                "dag_id": "dag_builtin_fact_pipeline",
                "name": "Built-in fact pipeline",
                "cadence": "manual",
                "idempotency_key_fields": ["as_of_date"],
                "tasks": [
                    {
                        "task_id": "ingest_doc",
                        "task_type": "ingest_document",
                        "dataset": "documents",
                        "payload": {
                            "document_id": "doc_executor_001",
                            "issuer_id": "issuer_001",
                            "security_id": "sec_001",
                            "source_id": "src_sec",
                            "source_type": "regulatory",
                            "document_type": "10-K",
                            "source_uri": "https://example.invalid/doc-executor-001",
                            "body": "FY2026 revenue grew 12% to RMB 100 million. Operating cash flow improved in 2026.",
                            "rights_tag": {
                                "license_class": "public",
                                "training_allowed": False,
                                "redistribution_allowed": False,
                                "display_use": "allowed",
                                "non_display_use": "restricted",
                                "derived_data_use": "restricted",
                            },
                            "language": "en",
                        },
                    },
                    {
                        "task_id": "extract_evidence",
                        "task_type": "extract_evidence",
                        "dataset": "evidence_chunks",
                        "depends_on": ["ingest_doc"],
                        "payload": {
                            "document_id": "${ingest_doc.output_ids.0}",
                            "parser_version": "workflow-executor",
                            "model_version": "rule-baseline",
                        },
                    },
                    {
                        "task_id": "extract_facts",
                        "task_type": "structured_extraction",
                        "dataset": "structured_facts",
                        "depends_on": ["extract_evidence"],
                        "payload": {
                            "extraction_id": "ext_executor_fact",
                            "evidence_id": "${extract_evidence.output_ids.0}",
                            "benchmark_id": "bm_executor_fact",
                            "expected_terms": ["revenue", "operating_cash_flow"],
                            "expected_numbers": 1,
                            "expected_periods": 1,
                            "parser_version": "workflow-executor",
                        },
                    },
                    {
                        "task_id": "rebuild_search",
                        "task_type": "search_rebuild",
                        "dataset": "search_index",
                        "depends_on": ["extract_facts"],
                        "payload": {"targets": ["keyword", "semantic"], "include_restricted": True},
                    },
                    {
                        "task_id": "register_sample",
                        "task_type": "benchmark_sample_register",
                        "dataset": "benchmark_samples",
                        "depends_on": ["ingest_doc"],
                        "payload": {
                            "benchmark_id": "bm_executor_fact",
                            "sample_id": "bms_executor_fact",
                            "document_id": "${ingest_doc.output_ids.0}",
                            "language": "en",
                            "expected_terms": ["revenue", "operating_cash_flow"],
                            "expected_numbers": 1,
                            "expected_periods": 1,
                            "expected_pages": [1],
                        },
                    },
                    {
                        "task_id": "run_benchmark",
                        "task_type": "benchmark_run",
                        "dataset": "benchmark_runs",
                        "depends_on": ["register_sample", "extract_evidence"],
                        "payload": {
                            "benchmark_id": "bm_executor_fact",
                            "run_id": "bmrn_executor_fact",
                            "sample_ids": ["${register_sample.output_ids.0}"],
                            "min_confidence": 0.8,
                        },
                    },
                ],
            },
            actor="platform",
            role="platform",
        )
        self.assertTrue(workflow.success, workflow.error)

        execute = self.router.dispatch(
            "POST",
            "/api/orchestration/dags/dag_builtin_fact_pipeline/execute",
            {
                "run_id": "wfrun_builtin_fact_001",
                "inputs": {"as_of_date": "2026-05-15"},
                "code_version": "test-executor-v1",
            },
            actor="platform",
            role="platform",
        )
        self.assertTrue(execute.success, execute.error)
        self.assertFalse(execute.data["existing"])
        run = execute.data["run"]
        self.assertEqual(run["status"], "succeeded")
        self.assertEqual(set(run["task_statuses"].values()), {"succeeded"})
        task_results = execute.data["task_results"]
        evidence_id = task_results["extract_evidence"]["output_ids"][0]
        self.assertEqual(task_results["extract_facts"]["payload"]["evidence_id"], evidence_id)
        self.assertEqual(task_results["run_benchmark"]["result"]["passed"], True)
        self.assertIn("document:doc_executor_001", run["output_refs"])
        self.assertIn(f"evidence:{evidence_id}", run["output_refs"])
        self.assertIn("extraction:ext_executor_fact", run["output_refs"])
        self.assertIn("search_index:keyword", run["output_refs"])
        self.assertIn("benchmark_sample:bms_executor_fact", run["output_refs"])
        self.assertIn("benchmark_run:bmrn_executor_fact", run["output_refs"])
        self.assertEqual(len(execute.data["lineage_events"]), 6)
        self.assertEqual({item["dataset"] for item in execute.data["lineage_events"]}, {"documents", "evidence_chunks", "structured_facts", "search_index", "benchmark_samples", "benchmark_runs"})
        self.assertEqual(self.service.store.audit_log[-1].action, "execute_workflow_definition")

        duplicate = self.router.dispatch(
            "POST",
            "/api/orchestration/dags/dag_builtin_fact_pipeline/execute",
            {"inputs": {"as_of_date": "2026-05-15"}},
            actor="platform",
            role="platform",
        )
        self.assertTrue(duplicate.success, duplicate.error)
        self.assertTrue(duplicate.data["existing"])
        self.assertEqual(duplicate.data["run"]["run_id"], "wfrun_builtin_fact_001")

        graph = self.router.dispatch(
            "POST",
            "/api/orchestration/dependency-graph",
            {"dag_id": "dag_builtin_fact_pipeline"},
            role="platform",
        )
        self.assertTrue(graph.success, graph.error)
        self.assertEqual(graph.data["graphs"][0]["latest_run_id"], "wfrun_builtin_fact_001")
        self.assertEqual(graph.data["graphs"][0]["lineage"]["latest_run_event_count"], 6)
        self.assertEqual(graph.data["graphs"][0]["lineage"]["datasets"]["benchmark_runs"], 1)

        openlineage = self.router.dispatch(
            "POST",
            "/api/orchestration/openlineage/export",
            {"run_id": "wfrun_builtin_fact_001", "namespace": "ai_quant_test"},
            actor="platform",
            role="platform",
        )
        self.assertTrue(openlineage.success, openlineage.error)
        self.assertEqual(openlineage.data["lineage_event_count"], 6)
        exported = openlineage.data["events"][0]
        self.assertEqual(exported["eventType"], "COMPLETE")
        self.assertIn("benchmark_run:bmrn_executor_fact", {item["name"] for item in exported["outputs"]})

    def test_astock_connector_registry_tracks_rights_mapping_and_verification(self) -> None:
        seeded = self.router.dispatch("POST", "/api/connectors/astock/seed", {}, actor="data", role="data_engineer")
        self.assertTrue(seeded.success)
        self.assertGreaterEqual(len(seeded.data["connectors"]), 8)
        eastmoney = self.service.store.astock_connectors["eastmoney_research"]
        self.assertEqual(eastmoney.rights_tag.display_use, "restricted")
        self.assertIn("title", eastmoney.field_mapping)
        self.assertIn(eastmoney.source_id, self.service.store.sources)

        verify = self.router.dispatch(
            "POST",
            "/api/connectors/astock/verify",
            {"connector_id": "eastmoney_research", "status": "passed"},
            actor="data",
            role="data_engineer",
        )
        self.assertTrue(verify.success)
        self.assertEqual(verify.data["updated"][0]["status"], "verified")
        self.assertEqual(verify.data["updated"][0]["last_check_status"], "passed")

        filtered = self.router.dispatch(
            "POST",
            "/api/connectors/astock/query",
            {"status": "verified"},
            role="data_engineer",
        )
        self.assertTrue(filtered.success)
        self.assertEqual(filtered.data["total"], 1)
        self.assertEqual(filtered.data["connectors"][0]["connector_id"], "eastmoney_research")

        sample = self.router.dispatch(
            "POST",
            "/api/connectors/astock/fetch",
            {
                "connector_id": "eastmoney_research",
                "sample_rows": [
                    {
                        "title": "Demo bank sector research",
                        "url": "https://example.invalid/report?id=1&token=secret#section",
                        "published_at": "2026-05-15",
                    }
                ],
            },
            actor="data",
            role="data_engineer",
        )
        self.assertTrue(sample.success, sample.error)
        self.assertEqual(sample.data["created_count"], 1)
        self.assertEqual(sample.data["normalized_rows"][0]["source_uri"], "https://example.invalid/report?id=1&token=REDACTED")
        self.assertEqual(sample.data["normalized_rows"][0]["title"], "Demo bank sector research")
        self.assertFalse(sample.data["automation_allowed"])
        self.assertIn("source_risk_yellow", sample.data["automation_blockers"])
        self.assertIn("restricted_rights_manual_reference_only", sample.data["automation_blockers"])

        blocked = self.router.dispatch(
            "POST",
            "/api/connectors/astock/verify",
            {"connector_id": "eastmoney_research", "status": "blocked", "error": "TOS boundary unclear"},
            actor="risk",
            role="risk_compliance",
        )
        self.assertTrue(blocked.success)
        blocked_fetch = self.router.dispatch(
            "POST",
            "/api/connectors/astock/fetch",
            {"connector_id": "eastmoney_research", "sample_rows": [{"title": "blocked"}]},
            actor="data",
            role="data_engineer",
        )
        self.assertFalse(blocked_fetch.success)
        self.assertEqual(blocked_fetch.status_code, 423)

    def test_source_governance_report_tracks_public_provenance_and_audit_completeness(self) -> None:
        self.router.dispatch("POST", "/api/ingestion/sources/seed", {}, actor="data", role="data_engineer")
        before = self.router.dispatch("POST", "/api/governance/sources/report", {"source_type": "public_market_data"}, role="risk_compliance")
        self.assertTrue(before.success)
        source_rows = {item["source_id"]: item for item in before.data["sources"]}
        self.assertIn("public_eod_market_data", source_rows)
        self.assertEqual(source_rows["public_eod_market_data"]["gaps"], [])
        self.assertIn("close", source_rows["public_eod_market_data"]["field_whitelist"])
        self.assertEqual(source_rows["public_eod_market_data"]["provenance_ref"], "local://data/local/tdx/market_data.duckdb")
        self.assertEqual(source_rows["public_eod_market_data"]["collection_method"], "local_file_or_public_api")
        self.assertEqual(source_rows["public_eod_market_data"]["robots_policy"], "reviewed_public_or_local_source")
        self.assertEqual(source_rows["public_eod_market_data"]["review_owner_role"], "数据工程")
        self.assertTrue(source_rows["public_eod_market_data"]["automation_ready"])

        full_report = self.router.dispatch("GET", "/api/governance/sources/report", {}, role="risk_compliance")
        full_rows = {item["source_id"]: item for item in full_report.data["sources"]}
        self.assertFalse(full_rows["manual_reference_transcripts"]["automation_ready"])
        self.assertIn("red_source_manual_reference_only", full_rows["manual_reference_transcripts"]["blocked_reasons"])

        updated = self.router.dispatch(
            "POST",
            "/api/governance/sources/authorized_eod_market_data",
            {
                "provenance_ref": "public-api://tdx/vipdoc",
                "retention_policy": "retain_adjusted_eod_for_research_10y",
                "cache_ttl_days": 3650,
                "usage_scope": "public_eod_internal_research_backtest_risk",
                "collection_method": "official_public_download",
                "robots_policy": "robots_and_tos_reviewed_2026q2",
                "last_reviewed_at": "2026-05-15T00:00:00+00:00",
                "review_owner": "market_data_owner",
                "review_owner_role": "数据工程",
                "field_whitelist": ["security_id", "as_of_date", "open", "high", "low", "close", "adjusted_close", "volume"],
            },
            actor="risk",
            role="risk_compliance",
        )
        self.assertTrue(updated.success)
        self.assertEqual(updated.data["source_id"], "public_eod_market_data")
        self.assertEqual(updated.data["provenance_ref"], "public-api://tdx/vipdoc")
        self.assertEqual(updated.data["collection_method"], "official_public_download")
        self.assertEqual(updated.data["review_owner"], "market_data_owner")

        after = self.router.dispatch("POST", "/api/governance/sources/report", {"source_type": "public_market_data"}, role="risk_compliance")
        self.assertTrue(after.success)
        source_rows = {item["source_id"]: item for item in after.data["sources"]}
        self.assertEqual(source_rows["public_eod_market_data"]["usage_scope"], "public_eod_internal_research_backtest_risk")
        self.assertEqual(source_rows["public_eod_market_data"]["robots_policy"], "robots_and_tos_reviewed_2026q2")
        self.assertEqual(after.data["automation_ready"], 1)

        review = self.router.dispatch(
            "POST",
            "/api/governance/sources/public_eod_market_data/reviews",
            {
                "review_id": "srrev_public_eod_2026q2",
                "reviewed_at": "2026-05-15T00:00:00+00:00",
                "review_period": "2026Q2",
                "status": "approved",
                "publicness_status": "confirmed_public_or_local",
                "tos_status": "reviewed",
                "robots_status": "reviewed_or_not_applicable",
                "usage_scope_status": "within_boundary",
                "next_review_due_at": "2099-01-01T00:00:00+00:00",
                "findings": ["local DuckDB provenance and TDX vipdoc fallback remain internal research inputs"],
            },
            actor="risk",
            role="risk_compliance",
        )
        self.assertTrue(review.success, review.error)
        self.assertEqual(review.data["source_id"], "public_eod_market_data")
        self.assertEqual(review.data["review_period"], "2026Q2")

        reviews = self.router.dispatch("GET", "/api/governance/source-reviews", {"source_id": "authorized_eod_market_data"}, role="risk_compliance")
        self.assertTrue(reviews.success)
        self.assertEqual(reviews.data["total"], 1)
        self.assertEqual(reviews.data["reviews"][0]["review_id"], "srrev_public_eod_2026q2")

        reviewed_report = self.router.dispatch("GET", "/api/governance/sources/report", {"source_type": "public_market_data"}, role="risk_compliance")
        reviewed_source = reviewed_report.data["sources"][0]
        self.assertEqual(reviewed_report.data["reviewed_sources"], 1)
        self.assertEqual(reviewed_source["latest_review"]["status"], "approved")
        self.assertFalse(reviewed_source["review_overdue"])
        self.assertTrue(reviewed_source["automation_ready"])

        local_review = self.router.dispatch(
            "POST",
            "/api/governance/sources/local_research_reports/reviews",
            {
                "review_id": "srrev_local_research_expired",
                "reviewed_at": "2026-01-01T00:00:00+00:00",
                "status": "conditional",
                "publicness_status": "manual_reference_only",
                "tos_status": "needs_review",
                "robots_status": "reviewed_or_not_applicable",
                "usage_scope_status": "manual_reference_only",
                "next_review_due_at": "2026-05-01T00:00:00+00:00",
            },
            actor="risk",
            role="risk_compliance",
        )
        self.assertTrue(local_review.success, local_review.error)

        reminders = self.router.dispatch(
            "GET",
            "/api/governance/source-review-reminders",
            {"as_of": "2026-05-15T00:00:00+00:00", "due_within_days": 30, "owner_role": "风险/合规"},
            role="risk_compliance",
        )
        self.assertTrue(reminders.success, reminders.error)
        reminder_rows = {item["source_id"]: item for item in reminders.data["reminders"]}
        self.assertIn("local_research_reports", reminder_rows)
        self.assertIn("manual_reference_transcripts", reminder_rows)
        self.assertNotIn("public_eod_market_data", reminder_rows)
        self.assertEqual(reminder_rows["local_research_reports"]["status"], "overdue")
        self.assertIn("latest_source_tos_needs_review", reminder_rows["local_research_reports"]["blocked_reasons"])
        self.assertTrue(reminder_rows["manual_reference_transcripts"]["missing_review"])
        owner_rows = {item["owner_role"]: item for item in reminders.data["owner_board"]}
        self.assertGreaterEqual(owner_rows["风险/合规"]["overdue"], 1)
        self.assertGreaterEqual(owner_rows["风险/合规"]["missing_review"], 1)

        audit_report = self.router.dispatch("GET", "/api/governance/audit-report", {}, role="risk_compliance")
        self.assertTrue(audit_report.success)
        self.assertGreaterEqual(audit_report.data["coverage"], 0.99)
        self.assertEqual(audit_report.data["field_coverage"]["actor"], 1.0)

    def test_health_and_metrics_endpoints(self) -> None:
        health = self.router.dispatch("GET", "/api/health", {}, role="unknown")
        self.assertTrue(health.success)
        self.assertEqual(health.data["status"], "ok")
        self.assertIn("uptime_seconds", health.data)
        self.assertIn("object_store", health.data)
        self.assertEqual(health.data["object_store"]["backend"], "local")
        self.assertEqual(health.data["search_index"]["backend"], "local")

        metrics = self.router.dispatch("GET", "/api/metrics", {}, role="unknown")
        self.assertTrue(metrics.success)
        self.assertIn("counts", metrics.data)
        self.assertIn("audit_events", metrics.data)
        self.assertEqual(metrics.data["object_store"]["backend"], "local")
        self.assertEqual(metrics.data["search_index"]["backend"], "local")
        self.assertEqual(metrics.data["counts"]["sources"], 1)

    def test_security_check_flags_tracked_env_and_literal_secrets(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "safe.env.example").write_text("AI_QUANT_LLM_API_KEY=\n", encoding="utf-8")
            (root / ".env").write_text("AI_QUANT_LLM_API_KEY=" + "sk-" + "realshouldnotbehere123456\n", encoding="utf-8")
            (root / "settings.py").write_text('TOKEN = "' + "0123456789abcdef0123456789abcdef" + '"\n', encoding="utf-8")
            result = scan_repository(root)
        self.assertFalse(result["ok"])
        finding_types = {item["type"] for item in result["findings"]}
        self.assertIn("tracked_env_file", finding_types)
        self.assertIn("assigned_secret", finding_types)

    def test_data_security_report_flags_sensitive_text_and_permission_alerts(self) -> None:
        self.service.ingest_document(
            {
                "document_id": "doc_sensitive",
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "source_id": "src_sec",
                "source_type": "regulatory",
                "document_type": "10-K",
                "source_uri": "https://example.invalid/sensitive",
                "body": (
                    "Contact alpha.owner@example.invalid or 13812345678. "
                    "ID 11010519491231002X should not be indexed. "
                    'api_key="' + "sk-" + 'prod-secret-value-123456" must be rotated.'
                ),
                "rights_tag": {
                    "license_class": "public",
                    "training_allowed": False,
                    "redistribution_allowed": False,
                    "display_use": "allowed",
                    "non_display_use": "restricted",
                    "derived_data_use": "restricted",
                },
                "language": "en",
            },
            actor="data",
        )

        report = self.router.dispatch("GET", "/api/governance/data-security-report", {}, role="risk_compliance")
        self.assertTrue(report.success, report.error)
        self.assertGreaterEqual(report.data["total"], 4)
        self.assertGreaterEqual(report.data["by_type"]["email"], 1)
        self.assertGreaterEqual(report.data["by_type"]["cn_mobile"], 1)
        self.assertGreaterEqual(report.data["by_type"]["cn_id"], 1)
        self.assertGreaterEqual(report.data["by_type"]["secret_literal"], 1)
        snippets = " ".join(item["snippet"] for item in report.data["findings"])
        self.assertNotIn("alpha.owner@example.invalid", snippets)
        self.assertNotIn("13812345678", snippets)
        self.assertNotIn("11010519491231002X", snippets)
        self.assertNotIn("sk-" + "prod-secret-value-123456", snippets)
        self.assertIn("***REDACTED***", snippets)

        metrics = self.router.dispatch("GET", "/api/metrics", {}, role="unknown")
        self.assertGreaterEqual(metrics.data["sensitive_findings"], 4)
        seeded = self.router.dispatch("POST", "/api/alerts/rules/seed", {}, role="risk_compliance")
        self.assertIn("alert_sensitive_findings", {item["rule_id"] for item in seeded.data["rules"]})
        evaluated = self.router.dispatch("POST", "/api/alerts/evaluate", {}, role="risk_compliance")
        self.assertIn("alert_sensitive_findings", {item["rule_id"] for item in evaluated.data["alerts"]})

        blocked = self.router.dispatch("POST", "/api/ingestion/documents", {}, actor="analyst", role="analyst")
        self.assertFalse(blocked.success)
        self.assertEqual(blocked.status_code, 403)
        self.assertEqual(self.service.store.audit_log[-1].action, "permission_denied")

        metrics_after_denied = self.router.dispatch("GET", "/api/metrics", {}, role="unknown")
        self.assertEqual(metrics_after_denied.data["permission_denied_events"], 1)
        evaluated_after_denied = self.router.dispatch("POST", "/api/alerts/evaluate", {}, role="risk_compliance")
        self.assertIn("alert_permission_denied_events", {item["rule_id"] for item in evaluated_after_denied.data["alerts"]})

    def test_permission_matrix_reports_role_domain_action_rules(self) -> None:
        report = self.router.dispatch("GET", "/api/governance/permission-matrix", {"role": "analyst"}, role="risk_compliance")
        self.assertTrue(report.success, report.error)
        self.assertIn("分析师", report.data["roles"])
        self.assertGreaterEqual(report.data["coverage"]["data_domains"], 10)
        ingestion_write = next(item for item in report.data["rules"] if item["rule_id"] == "data_ingestion" and item["method"] == "POST")
        self.assertIn("数据工程", ingestion_write["allowed_roles"])
        self.assertNotIn("分析师", ingestion_write["allowed_roles"])
        analyst_ingestion = [
            item
            for item in report.data["role_matrix"]
            if item["role"] == "分析师" and item["data_domain"] == "ingestion" and item["action"] == "write"
        ]
        self.assertEqual(len(analyst_ingestion), 1)
        self.assertFalse(analyst_ingestion[0]["allowed"])

        llm_execute = self.router.dispatch(
            "POST",
            "/api/governance/permission-matrix",
            {"data_domain": "llm_gateway", "action": "execute"},
            role="risk_compliance",
        )
        self.assertTrue(llm_execute.success, llm_execute.error)
        self.assertEqual({item["rule_id"] for item in llm_execute.data["rules"]}, {"llm_gateway"})
        self.assertIn("NLP/ML 负责人", llm_execute.data["rules"][0]["allowed_roles"])

        public_health = next(item for item in report.data["rules"] if item["rule_id"] == "system_health")
        self.assertTrue(public_health["public"])
        self.assertEqual(public_health["allowed_roles"], ["*"])

    def test_storage_policy_templates_are_scoped_and_lifecycle_ready(self) -> None:
        response = self.router.dispatch(
            "POST",
            "/api/governance/storage-policy-templates",
            {
                "environment": "prod",
                "bucket": "ai-quant-prod-objects",
                "prefix": "tenant-a/objects",
                "opensearch_index": "ai-quant-prod-search-*",
                "postgres_schema": "ai_quant",
            },
            role="risk_compliance",
        )
        self.assertTrue(response.success, response.error)
        templates = response.data["templates"]
        s3_actions = {
            action
            for statement in templates["s3_iam_policy"]["Statement"]
            for action in statement["Action"]
        }
        self.assertIn("s3:GetObject", s3_actions)
        self.assertIn("s3:PutObject", s3_actions)
        self.assertNotIn("s3:*", s3_actions)
        self.assertNotIn("s3:DeleteObject", s3_actions)
        self.assertEqual(templates["s3_lifecycle_policy"]["Rules"][0]["Filter"]["Prefix"], "tenant-a/objects/")
        self.assertGreater(templates["s3_lifecycle_policy"]["Rules"][0]["Expiration"]["Days"], 365)
        self.assertIn("风险/合规", templates["ddl_rollback_approval"]["required_approver_roles"])
        self.assertTrue(response.data["checks"]["postgres_no_drop_grant_for_app_role"])

    def test_public_market_data_respects_rights_and_dashboard(self) -> None:
        seeded = self.router.dispatch("POST", "/api/ingestion/sources/seed", {}, role="data_engineer")
        self.assertTrue(seeded.success)
        self.assertIn("public_eod_market_data", {item["source_id"] for item in seeded.data["sources"]})

        point = self.router.dispatch(
            "POST",
            "/api/market-data/points",
            {
                "data_id": "md_001",
                "security_id": "sec_001",
                "source_id": "public_eod_market_data",
                "as_of_date": "2026-05-14",
                "data_type": "eod",
                "close": 12.34,
                "adjusted_close": 12.34,
                "volume": 1000000,
            },
            role="data_engineer",
        )
        self.assertTrue(point.success)
        self.assertEqual(point.data["rights_tag"]["license_class"], "public_eod_reference")
        self.assertEqual(point.data["rights_tag"]["non_display_use"], "allowed")

        listed = self.router.dispatch("GET", "/api/market-data", {"security_id": "sec_001"}, role="CEO")
        self.assertTrue(listed.success)
        self.assertEqual(listed.data["market_data"][0]["data_id"], "md_001")

        dashboard = self.router.dispatch("GET", "/api/dashboard/ceo", {}, role="CEO")
        self.assertTrue(dashboard.success)
        self.assertEqual(dashboard.data["counts"]["market_data"], 1)
        self.assertEqual(dashboard.data["market_data_summary"][0]["security_id"], "sec_001")

        batch = self.router.dispatch(
            "POST",
            "/api/market-data/batch",
            {
                "batch_id": "batch_001",
                "items": [
                    {
                        "data_id": "md_002",
                        "security_id": "sec_001",
                        "source_id": "public_eod_market_data",
                        "as_of_date": "2026-05-15",
                        "data_type": "delayed",
                        "close": 12.56,
                        "volume": 1200000,
                    },
                    {
                        "data_id": "md_bad",
                        "security_id": "missing_security",
                        "as_of_date": "2026-05-15",
                        "close": 1,
                    },
                ],
            },
            role="data_engineer",
        )
        self.assertTrue(batch.success)
        self.assertEqual(batch.data["created_count"], 1)
        self.assertEqual(batch.data["failed_count"], 1)

        eod_next = self.router.dispatch(
            "POST",
            "/api/market-data/points",
            {
                "data_id": "md_003_eod",
                "security_id": "sec_001",
                "source_id": "public_eod_market_data",
                "as_of_date": "2026-05-15",
                "data_type": "eod",
                "close": 12.56,
                "adjusted_close": 12.56,
                "volume": 1200000,
            },
            role="data_engineer",
        )
        self.assertTrue(eod_next.success, eod_next.error)

        action = self.router.dispatch(
            "POST",
            "/api/corporate-actions",
            {
                "action_id": "ca_split",
                "security_id": "sec_001",
                "source_id": "public_eod_market_data",
                "action_type": "split",
                "ex_date": "2026-05-16",
                "ratio": 2.0,
                "description": "2-for-1 split for adjusted close chain",
            },
            role="data_engineer",
        )
        self.assertTrue(action.success, action.error)
        dividend = self.router.dispatch(
            "POST",
            "/api/corporate-actions",
            {
                "action_id": "ca_cash_dividend",
                "security_id": "sec_001",
                "source_id": "public_eod_market_data",
                "action_type": "cash_dividend",
                "ex_date": "2026-05-15",
                "cash_amount": 0.2,
                "currency": "CNY",
                "description": "cash dividend for total-return chain",
            },
            role="data_engineer",
        )
        self.assertTrue(dividend.success, dividend.error)
        corporate_actions = self.router.dispatch("GET", "/api/corporate-actions", {"security_id": "sec_001"}, role="CEO")
        self.assertEqual(corporate_actions.data["count"], 2)
        adjusted = self.router.dispatch(
            "GET",
            "/api/market-data/adjusted",
            {"security_id": "sec_001", "source_id": "public_eod_market_data", "data_type": "eod", "adjustment_mode": "backward"},
            role="CEO",
        )
        self.assertTrue(adjusted.success, adjusted.error)
        self.assertEqual(adjusted.data["adjustment_mode"], "backward")
        self.assertEqual(adjusted.data["market_data"][0]["corporate_action_ids"], ["ca_split"])
        self.assertAlmostEqual(adjusted.data["market_data"][0]["computed_adjusted_close"], 6.17)
        self.assertEqual(adjusted.data["market_data"][1]["cash_dividend"], 0.2)
        self.assertEqual(adjusted.data["market_data"][1]["computed_adjusted_cash_dividend"], 0.1)
        self.assertIn("cash_dividends", adjusted.data["adjustment_policy"])

        forward = self.router.dispatch(
            "GET",
            "/api/market-data/adjusted",
            {"security_id": "sec_001", "source_id": "public_eod_market_data", "data_type": "eod", "adjustment_mode": "forward"},
            role="CEO",
        )
        self.assertTrue(forward.success, forward.error)
        self.assertEqual(forward.data["market_data"][0]["computed_adjusted_close"], 12.34)

        returns = self.router.dispatch(
            "GET",
            "/api/market-data/returns",
            {"security_id": "sec_001", "source_id": "public_eod_market_data", "data_type": "eod", "adjustment_mode": "backward"},
            role="CEO",
        )
        self.assertTrue(returns.success, returns.error)
        self.assertEqual(returns.data["price_count"], 2)
        self.assertEqual(returns.data["return_count"], 1)
        self.assertEqual(returns.data["total_return_method"], "price_only")
        self.assertAlmostEqual(returns.data["returns"][0]["return"], 6.28 / 6.17 - 1.0)
        self.assertEqual(returns.data["adjustment_mode"], "backward")
        total_returns = self.router.dispatch(
            "GET",
            "/api/market-data/returns",
            {
                "security_id": "sec_001",
                "source_id": "public_eod_market_data",
                "data_type": "eod",
                "adjustment_mode": "backward",
                "total_return_method": "cash_dividend_reinvested",
            },
            role="CEO",
        )
        self.assertTrue(total_returns.success, total_returns.error)
        self.assertEqual(total_returns.data["returns"][0]["cash_dividend"], 0.1)
        self.assertGreater(total_returns.data["returns"][0]["return"], returns.data["returns"][0]["return"])

        refreshed_dashboard = self.router.dispatch("GET", "/api/dashboard/ceo", {}, role="CEO")
        self.assertEqual(refreshed_dashboard.data["counts"]["market_data"], 3)
        self.assertEqual(refreshed_dashboard.data["counts"]["corporate_actions"], 2)

        blocked_realtime = self.router.dispatch(
            "POST",
            "/api/market-data/points",
            {
                "data_id": "md_realtime",
                "security_id": "sec_001",
                "source_id": "public_eod_market_data",
                "as_of_date": "2026-05-14",
                "data_type": "realtime",
                "close": 12.34,
            },
            role="data_engineer",
        )
        self.assertFalse(blocked_realtime.success)
        self.assertEqual(blocked_realtime.status_code, 422)

        blocked_rights = self.router.dispatch(
            "POST",
            "/api/market-data/points",
            {
                "data_id": "md_blocked_rights",
                "security_id": "sec_001",
                "source_id": "src_sec",
                "as_of_date": "2026-05-14",
                "data_type": "eod",
                "close": 12.34,
                "rights_tag": {
                    "license_class": "public",
                    "training_allowed": False,
                    "redistribution_allowed": False,
                    "display_use": "allowed",
                    "non_display_use": "allowed",
                    "derived_data_use": "restricted",
                },
            },
            role="data_engineer",
        )
        self.assertFalse(blocked_rights.success)
        self.assertEqual(blocked_rights.status_code, 403)

        blocked_field = self.router.dispatch(
            "POST",
            "/api/market-data/points",
            {
                "data_id": "md_blocked_field",
                "security_id": "sec_001",
                "source_id": "public_eod_market_data",
                "as_of_date": "2026-05-14",
                "data_type": "eod",
                "close": 12.34,
                "volume": 100,
                "real_time_bid": 12.35,
            },
            role="data_engineer",
        )
        self.assertFalse(blocked_field.success)
        self.assertEqual(blocked_field.status_code, 422)
        self.assertIn("field", blocked_field.error["message"])

    def test_market_data_quality_report_flags_ohlc_governance_and_date_gaps(self) -> None:
        self.router.dispatch("POST", "/api/ingestion/sources/seed", {}, role="data_engineer")
        for payload in [
            {
                "data_id": "md_quality_001",
                "security_id": "sec_001",
                "source_id": "public_eod_market_data",
                "as_of_date": "2026-05-14",
                "data_type": "eod",
                "open": 10.0,
                "high": 10.5,
                "low": 9.8,
                "close": 10.2,
                "volume": 1000,
            },
            {
                "data_id": "md_quality_bad_ohlc",
                "security_id": "sec_001",
                "source_id": "public_eod_market_data",
                "as_of_date": "2026-05-20",
                "data_type": "eod",
                "open": 10.0,
                "high": 9.5,
                "low": 9.0,
                "close": 11.0,
                "volume": 1000,
            },
        ]:
            created = self.router.dispatch("POST", "/api/market-data/points", payload, role="data_engineer")
            self.assertTrue(created.success, created.error)

        report = self.router.dispatch(
            "GET",
            "/api/market-data/quality-report",
            {"security_id": "sec_001", "max_gap_days": 1},
            role="CEO",
        )
        self.assertTrue(report.success, report.error)
        self.assertEqual(report.data["total_points"], 2)
        self.assertEqual(report.data["invalid_ohlc"][0]["data_id"], "md_quality_bad_ohlc")
        self.assertEqual(report.data["date_gaps"][0]["gap_days"], 5)
        source_gap_rows = {item["source_id"]: item for item in report.data["source_governance_gaps"]}
        self.assertNotIn("public_eod_market_data", source_gap_rows)
        self.assertEqual(report.data["source_rights_gaps"], [])
        self.assertLess(report.data["quality_score"], 1.0)

    def test_portfolio_returns_consumes_public_adjusted_market_data(self) -> None:
        self.router.dispatch("POST", "/api/ingestion/sources/seed", {}, role="data_engineer")
        self.service.register_security(
            {
                "security_id": "sec_002",
                "issuer_id": "issuer_001",
                "ticker": "DEMO2",
                "exchange": "SSE",
                "currency": "CNY",
                "market": "A",
            },
            actor="platform",
        )
        for payload in [
            {"data_id": "md_p1_d1", "security_id": "sec_001", "as_of_date": "2026-05-14", "close": 10.0, "adjusted_close": 10.0, "volume": 100},
            {"data_id": "md_p1_d2", "security_id": "sec_001", "as_of_date": "2026-05-15", "close": 11.0, "adjusted_close": 11.0, "volume": 100},
            {"data_id": "md_p2_d1", "security_id": "sec_002", "as_of_date": "2026-05-14", "close": 20.0, "adjusted_close": 20.0, "volume": 100},
            {"data_id": "md_p2_d2", "security_id": "sec_002", "as_of_date": "2026-05-15", "close": 19.0, "adjusted_close": 19.0, "volume": 100},
        ]:
            created = self.router.dispatch("POST", "/api/market-data/points", {"source_id": "public_eod_market_data", "data_type": "eod", **payload}, role="data_engineer")
            self.assertTrue(created.success, created.error)

        portfolio = self.router.dispatch(
            "POST",
            "/api/portfolio/returns",
            {
                "weights": {"sec_001": 0.6, "sec_002": 0.4},
                "groups": {
                    "sec_001": {"industry": "software", "style": "quality"},
                    "sec_002": {"industry": "hardware", "style": "value"},
                },
                "source_id": "public_eod_market_data",
                "data_type": "eod",
                "adjustment_mode": "backward",
                "total_return_method": "price_only",
            },
            role="CIO",
        )
        self.assertTrue(portfolio.success, portfolio.error)
        self.assertEqual(portfolio.data["return_count"], 1)
        expected = 0.6 * 0.1 + 0.4 * (-0.05)
        self.assertAlmostEqual(portfolio.data["returns"][0]["return"], expected)
        self.assertEqual(portfolio.data["coverage"]["component_count"], 2)
        self.assertEqual(portfolio.data["weights"]["sec_001"], 0.6)
        self.assertAlmostEqual(portfolio.data["attribution"]["industry"]["software"]["period_contribution"], 0.06)
        self.assertAlmostEqual(portfolio.data["attribution"]["industry"]["hardware"]["period_contribution"], -0.02)
        self.assertEqual(portfolio.data["attribution"]["style"]["quality"]["weight"], 0.6)

    def test_portfolio_valuation_uses_latest_public_market_prices(self) -> None:
        self.router.dispatch("POST", "/api/ingestion/sources/seed", {}, role="data_engineer")
        self.service.register_security(
            {
                "security_id": "sec_val_002",
                "issuer_id": "issuer_001",
                "ticker": "VAL2",
                "exchange": "SSE",
                "currency": "USD",
                "market": "U",
            },
            actor="platform",
        )
        for payload in [
            {"data_id": "md_val_1", "security_id": "sec_001", "as_of_date": "2026-05-14", "close": 10.0, "adjusted_close": 10.0, "volume": 100},
            {"data_id": "md_val_2", "security_id": "sec_val_002", "as_of_date": "2026-05-13", "close": 20.0, "adjusted_close": 20.0, "volume": 100},
        ]:
            created = self.router.dispatch("POST", "/api/market-data/points", {"source_id": "public_eod_market_data", "data_type": "eod", **payload}, role="data_engineer")
            self.assertTrue(created.success, created.error)

        valuation = self.router.dispatch(
            "POST",
            "/api/portfolio/valuation",
            {
                "as_of_date": "2026-05-14",
                "cash": 100.0,
                "holdings": [
                    {"security_id": "sec_001", "shares": 10},
                    {"security_id": "sec_val_002", "shares": 5},
                ],
                "groups": {
                    "sec_001": {"industry": "software", "style": "quality"},
                    "sec_val_002": {"industry": "hardware", "style": "value"},
                },
            },
            role="CIO",
        )
        self.assertTrue(valuation.success, valuation.error)
        self.assertEqual(valuation.data["gross_market_value"], 200.0)
        self.assertEqual(valuation.data["total_market_value"], 300.0)
        self.assertEqual(valuation.data["cash_weight"], round(100 / 300, 8))
        self.assertEqual(valuation.data["positions"][1]["price_date"], "2026-05-13")
        self.assertEqual(valuation.data["missing_price_count"], 0)
        risk = valuation.data["risk_decomposition"]
        self.assertEqual(valuation.data["positions"][1]["currency"], "USD")
        self.assertAlmostEqual(risk["by_industry"]["software"]["weight"], round(100 / 300, 8))
        self.assertAlmostEqual(risk["by_style"]["value"]["weight"], round(100 / 300, 8))
        self.assertAlmostEqual(risk["by_currency"]["USD"]["weight"], round(100 / 300, 8))
        self.assertAlmostEqual(risk["foreign_currency_weight"], round(100 / 300, 8))
        self.assertEqual(risk["concentration"]["position_count"], 2)

    def test_portfolio_transactions_derive_asof_positions(self) -> None:
        self.router.dispatch("POST", "/api/ingestion/sources/seed", {}, role="data_engineer")
        for payload in [
            {
                "transaction_id": "ptxn_buy",
                "security_id": "sec_001",
                "trade_date": "2026-05-14",
                "side": "buy",
                "quantity": 100,
                "price": 10.0,
                "fees": 1.0,
                "account_id": "acct_001",
                "strategy_id": "strat_core",
            },
            {
                "transaction_id": "ptxn_sell",
                "security_id": "sec_001",
                "trade_date": "2026-05-15",
                "side": "sell",
                "quantity": 40,
                "price": 11.0,
                "fees": 1.0,
                "account_id": "acct_001",
                "strategy_id": "strat_core",
            },
        ]:
            created = self.router.dispatch("POST", "/api/portfolio/transactions", payload, role="PM")
            self.assertTrue(created.success, created.error)

        listed = self.router.dispatch("GET", "/api/portfolio/transactions", {"account_id": "acct_001"}, role="PM")
        self.assertTrue(listed.success)
        self.assertEqual(listed.data["total"], 2)

        positions = self.router.dispatch("GET", "/api/portfolio/positions", {"account_id": "acct_001", "as_of_date": "2026-05-15"}, role="PM")
        self.assertTrue(positions.success, positions.error)
        self.assertEqual(positions.data["position_count"], 1)
        self.assertEqual(positions.data["positions"][0]["shares"], 60.0)
        self.assertEqual(positions.data["transaction_count"], 2)

    def test_tdx_market_data_preview_and_import_use_public_eod_path(self) -> None:
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "market_data.duckdb"
            connection = sqlite3.connect(db_path)
            connection.execute(
                """
                CREATE TABLE daily_kline (
                    symbol TEXT,
                    trade_date TEXT,
                    open REAL,
                    close REAL,
                    high REAL,
                    low REAL,
                    volume REAL,
                    amount REAL,
                    turnover REAL
                )
                """
            )
            connection.executemany(
                "INSERT INTO daily_kline VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    ("600000", "2026-05-14", 10.0, 10.5, 10.8, 9.9, 1000.0, 10500.0, None),
                    ("600000", "2026-05-15", 10.5, 11.0, 11.2, 10.3, 1200.0, 13200.0, None),
                ],
            )
            connection.commit()
            connection.close()

            self.service.tdx_market_data = TDXMarketDataAdapter(path=db_path, connect=lambda path, _read_only: sqlite3.connect(path))
            self.service.register_security(
                {
                    "security_id": "sec_600000",
                    "issuer_id": "issuer_001",
                    "ticker": "600000",
                    "exchange": "SSE",
                    "currency": "CNY",
                    "market": "A",
                },
                actor="platform",
            )

            preview = self.router.dispatch(
                "POST",
                "/api/market-data/tdx/preview",
                {"symbols": ["sh600000"], "start_date": "2026-05-14", "end_date": "2026-05-15", "limit": 10},
                role="data_engineer",
            )
            self.assertTrue(preview.success, preview.error)
            self.assertEqual(preview.data["count"], 2)
            self.assertEqual(preview.data["rows"][0]["symbol"], "600000")

            imported = self.router.dispatch(
                "POST",
                "/api/market-data/tdx/import",
                {"symbols": ["600000"], "start_date": "2026-05-14", "end_date": "2026-05-15", "limit": 10},
                actor="data",
                role="data_engineer",
            )
            self.assertTrue(imported.success, imported.error)
            self.assertEqual(imported.data["created_count"], 2)
            self.assertEqual(imported.data["failed_count"], 0)
            listed = self.router.dispatch("GET", "/api/market-data", {"security_id": "sec_600000"}, role="CEO")
            self.assertEqual(len(listed.data["market_data"]), 2)
            self.assertEqual(listed.data["market_data"][0]["source_id"], "public_eod_market_data")

            duplicate = self.router.dispatch(
                "POST",
                "/api/market-data/tdx/import",
                {"symbols": ["600000"], "start_date": "2026-05-14", "end_date": "2026-05-15", "limit": 10},
                role="data_engineer",
            )
            self.assertTrue(duplicate.success)
            self.assertEqual(duplicate.data["created_count"], 0)
            self.assertEqual(duplicate.data["skipped_count"], 2)

    def test_tdx_vipdoc_preview_and_import_fallback(self) -> None:
        with TemporaryDirectory() as temp_dir:
            vipdoc_root = Path(temp_dir) / "vipdoc"
            day_dir = vipdoc_root / "sh" / "lday"
            day_dir.mkdir(parents=True)
            (day_dir / "sh600000.day").write_bytes(
                b"".join(
                    [
                        struct.pack("<IIIIIfII", 20260514, 1000, 1080, 990, 1050, 10500.0, 1000, 0),
                        struct.pack("<IIIIIfII", 20260515, 1050, 1120, 1030, 1100, 13200.0, 1200, 0),
                    ]
                )
            )
            self.service.tdx_vipdoc = TDXVipdocAdapter(path=vipdoc_root)
            self.service.register_security(
                {
                    "security_id": "sec_vip_600000",
                    "issuer_id": "issuer_001",
                    "ticker": "600000",
                    "exchange": "SSE",
                    "currency": "CNY",
                    "market": "A",
                },
                actor="platform",
            )

            preview = self.router.dispatch(
                "POST",
                "/api/market-data/tdx/preview",
                {"source_format": "vipdoc", "symbols": ["600000"], "start_date": "2026-05-14", "end_date": "2026-05-15", "limit": 10},
                role="data_engineer",
            )
            self.assertTrue(preview.success, preview.error)
            self.assertEqual(preview.data["adapter"]["provider"], "tdx_vipdoc")
            self.assertEqual(preview.data["count"], 2)
            self.assertEqual(preview.data["rows"][0]["open"], 10.0)
            self.assertEqual(preview.data["rows"][1]["close"], 11.0)

            imported = self.router.dispatch(
                "POST",
                "/api/market-data/tdx/import",
                {"source_format": "vipdoc", "symbols": ["sh600000"], "start_date": "2026-05-14", "end_date": "2026-05-15", "limit": 10},
                actor="data",
                role="data_engineer",
            )
            self.assertTrue(imported.success, imported.error)
            self.assertEqual(imported.data["adapter"]["provider"], "tdx_vipdoc")
            self.assertEqual(imported.data["created_count"], 2)
            self.assertEqual(imported.data["failed_count"], 0)
            listed = self.router.dispatch("GET", "/api/market-data", {"security_id": "sec_vip_600000"}, role="CEO")
            self.assertEqual(len(listed.data["market_data"]), 2)
            self.assertEqual(listed.data["market_data"][0]["source_id"], "public_eod_market_data")

    def test_tdx_incremental_import_script_starts_after_existing_date(self) -> None:
        with TemporaryDirectory() as temp_dir:
            state_db = Path(temp_dir) / "state.db"
            tdx_db = Path(temp_dir) / "market_data.duckdb"
            connection = sqlite3.connect(tdx_db)
            connection.execute(
                """
                CREATE TABLE daily_kline (
                    symbol TEXT,
                    trade_date TEXT,
                    open REAL,
                    close REAL,
                    high REAL,
                    low REAL,
                    volume REAL,
                    amount REAL,
                    turnover REAL
                )
                """
            )
            connection.executemany(
                "INSERT INTO daily_kline VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    ("600000", "2026-05-14", 10.0, 10.5, 10.8, 9.9, 1000.0, 10500.0, None),
                    ("600000", "2026-05-15", 10.5, 11.0, 11.2, 10.3, 1200.0, 13200.0, None),
                ],
            )
            connection.commit()
            connection.close()

            state_service = SystemService(SQLiteStore(state_db))
            state_service.seed_default_sources(actor="data")
            state_service.register_issuer({"issuer_id": "issuer_script", "legal_name": "Script Corp", "market": ["A"]}, actor="platform")
            state_service.register_security(
                {
                    "security_id": "sec_600000",
                    "issuer_id": "issuer_script",
                    "ticker": "600000",
                    "exchange": "SSE",
                    "currency": "CNY",
                    "market": "A",
                },
                actor="platform",
            )
            state_service.register_market_data_point(
                {
                    "security_id": "sec_600000",
                    "source_id": "public_eod_market_data",
                    "as_of_date": "2026-05-14",
                    "data_type": "eod",
                    "open": 10.0,
                    "high": 10.8,
                    "low": 9.9,
                    "close": 10.5,
                    "volume": 1000.0,
                },
                actor="data",
            )

            summary = run_tdx_incremental_import(
                state_db,
                symbols=["600000"],
                security_map={"600000": "sec_600000"},
                tdx_duckdb_path=tdx_db,
                end_date="2026-05-15",
                duckdb_connect=lambda path, _read_only: sqlite3.connect(path),
            )
            self.assertEqual(summary["created_count"], 1)
            self.assertEqual(summary["results"][0]["start_date"], "2026-05-15")
            reloaded = SystemService(SQLiteStore(state_db))
            points = sorted(reloaded.store.market_data.values(), key=lambda item: item.as_of_date)
            self.assertEqual([point.as_of_date for point in points], ["2026-05-14", "2026-05-15"])

    def test_tdx_vipdoc_download_script_verifies_and_extracts_archive(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive_path = root / "vipdoc.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("sh/lday/sh600000.day", b"demo-day-bytes")
            expected_sha256 = hashlib.sha256(archive_path.read_bytes()).hexdigest()
            target_dir = root / "target"

            result = download_tdx_vipdoc_archive(str(archive_path), target_dir, expected_sha256=expected_sha256)
            self.assertEqual(result["sha256"], expected_sha256)
            self.assertEqual(result["extracted_count"], 1)
            self.assertTrue((target_dir / "sh" / "lday" / "sh600000.day").exists())

            with self.assertRaises(Exception):
                download_tdx_vipdoc_archive(str(archive_path), root / "bad", expected_sha256="0" * 64)

    def test_13f_holdings_generate_crowding_snapshot(self) -> None:
        previous = self.router.dispatch(
            "POST",
            "/api/13f/holdings",
            {
                "holding_id": "hold_001_prev",
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "source_id": "sec_edgar",
                "filer_cik": "0001000001",
                "filer_name": "Alpha Fund",
                "report_period": "2025-12-31",
                "shares": 700,
                "value_usd": 70000,
            },
            role="data_engineer",
        )
        self.assertTrue(previous.success)
        first = self.router.dispatch(
            "POST",
            "/api/13f/holdings",
            {
                "holding_id": "hold_001",
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "source_id": "sec_edgar",
                "filer_cik": "0001000001",
                "filer_name": "Alpha Fund",
                "report_period": "2026-03-31",
                "shares": 1000,
                "value_usd": 100000,
            },
            role="data_engineer",
        )
        self.assertTrue(first.success)
        second = self.router.dispatch(
            "POST",
            "/api/13f/holdings",
            {
                "holding_id": "hold_002",
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "source_id": "sec_edgar",
                "filer_cik": "0001000002",
                "filer_name": "Beta Fund",
                "report_period": "2026-03-31",
                "shares": 400,
                "value_usd": 40000,
            },
            role="data_engineer",
        )
        self.assertTrue(second.success)

        listed = self.router.dispatch("GET", "/api/13f/holdings", {"issuer_id": "issuer_001"}, role="CEO")
        self.assertTrue(listed.success)
        self.assertEqual(len(listed.data["holdings"]), 3)

        changes = self.router.dispatch(
            "GET",
            "/api/13f/holdings/changes",
            {"issuer_id": "issuer_001", "report_period": "2026-03-31"},
            role="CEO",
        )
        self.assertTrue(changes.success, changes.error)
        change_rows = {(item["filer_key"], item["change_type"]): item for item in changes.data["changes"]}
        self.assertEqual(changes.data["action_counts"]["increased"], 1)
        self.assertEqual(changes.data["action_counts"]["new_position"], 1)
        self.assertEqual(change_rows[("0001000001", "increased")]["shares_delta"], 300)
        self.assertEqual(change_rows[("0001000002", "new_position")]["value_usd_delta"], 40000)

        crowding = self.router.dispatch(
            "POST",
            "/api/13f/crowding/update",
            {"snapshot_id": "crd_13f_test", "issuer_id": "issuer_001", "report_period": "2026-03-31"},
            role="CIO",
        )
        self.assertTrue(crowding.success)
        self.assertEqual(crowding.data["source"], "13F")
        self.assertGreater(crowding.data["score"], 0.0)
        self.assertLessEqual(crowding.data["score"], 1.0)
        self.service.store.crowding["crd_13f_test"].score = 0.9

        mapping = self.router.dispatch(
            "POST",
            "/api/entity-mappings",
            {
                "mapping_id": "map_13f_candidate",
                "issuer_id": "issuer_001",
                "figi": "FIGI-DEMO-001",
                "ticker": "DEMO",
                "market": "U",
                "confidence": 0.93,
            },
            role="data_engineer",
        )
        self.assertTrue(mapping.success, mapping.error)

        candidates = self.router.dispatch(
            "GET",
            "/api/13f/candidate-pool",
            {"report_period": "2026-03-31", "max_crowding_score": 0.5},
            role="CEO",
        )
        self.assertTrue(candidates.success, candidates.error)
        self.assertEqual(candidates.data["count"], 1)
        self.assertFalse(candidates.data["automation_allowed"])
        self.assertEqual(candidates.data["usage_boundary"], "13f_candidate_pool_is_research_and_crowding_risk_only_not_trade_signal")
        candidate = candidates.data["candidates"][0]
        self.assertEqual(candidate["issuer_id"], "issuer_001")
        self.assertEqual(candidate["figi"], "FIGI-DEMO-001")
        self.assertEqual(candidate["mapping_confidence"], 0.93)
        self.assertEqual(candidate["filer_count"], 2)
        self.assertEqual(candidate["net_value_usd_delta"], 70000)
        self.assertIn("crowding_above_threshold", candidate["risk_tags"])
        self.assertIn("mapping_score", candidate["score_components"])

        dashboard = self.router.dispatch("GET", "/api/dashboard/ceo", {}, role="CEO")
        self.assertEqual(dashboard.data["counts"]["institutional_holdings"], 3)
        self.assertEqual(dashboard.data["institutional_holding_summary"][0]["issuer_id"], "issuer_001")

        blocked_negative = self.router.dispatch(
            "POST",
            "/api/13f/holdings",
            {
                "holding_id": "hold_negative",
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "source_id": "sec_edgar",
                "filer_cik": "0001000003",
                "report_period": "2026-03-31",
                "shares": -1,
                "value_usd": 100,
            },
            role="data_engineer",
        )
        self.assertFalse(blocked_negative.success)
        self.assertEqual(blocked_negative.status_code, 422)

    def test_disclosure_event_classifier_builds_8k_event_wall_and_graph(self) -> None:
        self.service.seed_default_sources(actor="data")
        self.service.ingest_document(
            {
                "document_id": "doc_8k_event",
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "source_id": "src_sec",
                "source_type": "regulatory",
                "document_type": "8-K",
                "source_uri": "https://example.invalid/doc-8k-event",
                "published_at": "2026-05-15T00:00:00+00:00",
                "body": "Item 5.02 The CFO resigned and the company appointed an interim chief financial officer.",
                "rights_tag": {
                    "license_class": "public",
                    "training_allowed": False,
                    "redistribution_allowed": False,
                    "display_use": "allowed",
                    "non_display_use": "restricted",
                    "derived_data_use": "restricted",
                },
                "language": "en",
            },
            actor="data",
        )
        event = self.router.dispatch(
            "POST",
            "/api/disclosure-events/classify",
            {"document_id": "doc_8k_event"},
            actor="analyst",
            role="overseas_research",
        )
        self.assertTrue(event.success, event.error)
        self.assertEqual(event.data["event_type"], "management_change")
        self.assertEqual(event.data["item_code"], "5.02")
        self.assertIn("Departure", event.data["item_title"])
        self.assertEqual(event.data["severity"], "high")
        self.assertGreaterEqual(len(event.data["evidence_ids"]), 1)
        listed = self.router.dispatch("GET", "/api/disclosure-events", {"severity": "high"}, role="CIO")
        self.assertEqual(listed.data["count"], 1)
        dashboard = self.service.dashboard()
        self.assertEqual(dashboard["counts"]["disclosure_events"], 1)
        self.assertEqual(dashboard["disclosure_event_wall"][0]["event_id"], event.data["event_id"])
        graph = self.router.dispatch("GET", "/api/graph/query", {"issuer_id": "issuer_001"}, role="CIO")
        self.assertTrue(graph.success, graph.error)
        self.assertEqual(graph.data["disclosure_events"][0]["event_id"], event.data["event_id"])
        self.assertIn("HAS_DISCLOSURE_EVENT", {edge["type"] for edge in graph.data["edges"]})

        self.service.register_issuer({"issuer_id": "issuer_bench", "legal_name": "Benchmark Index", "market": ["A"]}, actor="platform")
        self.service.register_security(
            {
                "security_id": "sec_bench",
                "issuer_id": "issuer_bench",
                "ticker": "BENCH",
                "exchange": "SSE",
                "currency": "CNY",
                "market": "A",
            },
            actor="platform",
        )
        for security_id, prices in {
            "sec_001": [("2026-05-15", 100.0), ("2026-05-16", 105.0), ("2026-05-20", 110.0)],
            "sec_bench": [("2026-05-15", 200.0), ("2026-05-16", 202.0), ("2026-05-20", 204.0)],
        }.items():
            for as_of_date, close in prices:
                self.service.register_market_data_point(
                    {
                        "security_id": security_id,
                        "source_id": "public_eod_market_data",
                        "as_of_date": as_of_date,
                        "data_type": "eod",
                        "open": close,
                        "high": close,
                        "low": close,
                        "close": close,
                    },
                    actor="data",
                )
        performance = self.router.dispatch(
            "POST",
            "/api/disclosure-events/performance",
            {"event_id": event.data["event_id"], "windows": [1, 5], "benchmark_security_id": "sec_bench"},
            actor="analyst",
            role="overseas_research",
        )
        self.assertTrue(performance.success, performance.error)
        self.assertEqual(performance.data["updated_count"], 1)
        one_day = performance.data["events"][0]["windows"][0]
        self.assertEqual(one_day["status"], "computed")
        self.assertAlmostEqual(one_day["return"], 0.05)
        self.assertAlmostEqual(one_day["benchmark_return"], 0.01)
        self.assertAlmostEqual(one_day["abnormal_return"], 0.04)
        listed_with_performance = self.router.dispatch("GET", "/api/disclosure-events", {"event_id": event.data["event_id"]}, role="CIO")
        self.assertEqual(listed_with_performance.data["events"][0]["post_event_performance"]["status"], "computed")
        self.assertEqual(len(listed_with_performance.data["events"][0]["post_event_performance"]["windows"]), 2)

    def test_entity_mapping_batch_and_quality_report(self) -> None:
        batch = self.router.dispatch(
            "POST",
            "/api/entity-mappings/batch",
            {
                "batch_id": "map_batch",
                "items": [
                    {"mapping_id": "map_a", "issuer_id": "issuer_001", "lei": "LEI-DEMO-001", "ticker": "600000", "market": "A"},
                    {"mapping_id": "map_u", "issuer_id": "issuer_001", "cik": "0000001", "ticker": "DEMO", "market": "U"},
                    {"mapping_id": "map_bad", "issuer_id": "missing", "ticker": "BAD", "market": "U"},
                ],
            },
            role="platform",
        )
        self.assertTrue(batch.success, batch.error)
        self.assertEqual(batch.data["created_count"], 2)
        self.assertEqual(batch.data["failed_count"], 1)
        report = self.router.dispatch(
            "GET",
            "/api/entity-mappings/quality-report",
            {
                "issuer_id": "issuer_001",
                "labels": [
                    {"mapping_id": "map_a", "issuer_id": "issuer_001", "ticker": "600000", "market": "A"},
                    {"mapping_id": "map_u", "issuer_id": "issuer_001", "ticker": "WRONG", "market": "U"},
                ],
                "low_confidence_threshold": 0.8,
            },
            role="platform",
        )
        self.assertTrue(report.success, report.error)
        self.assertEqual(report.data["mappings"], 2)
        self.assertEqual(report.data["market_counts"]["A"], 1)
        self.assertEqual(report.data["accuracy"], 0.5)
        self.assertEqual(report.data["mismatches"][0]["mapping_id"], "map_u")
        self.assertGreaterEqual(report.data["average_confidence"], 0.7)
        self.assertEqual(report.data["low_confidence_count"], 1)
        self.assertEqual(report.data["low_confidence_mappings"][0]["mapping_id"], "map_u")

    def test_compliance_gate_blocks_private_or_non_display_decision_pack(self) -> None:
        self.service.ingest_document(
            {
                "document_id": "doc_005",
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "source_id": "src_sec",
                "source_type": "regulatory",
                "document_type": "annual_report",
                "source_uri": "https://example.invalid/doc-005",
                "body": "Public facts only.",
                "rights_tag": {
                    "license_class": "public",
                    "training_allowed": False,
                    "redistribution_allowed": False,
                    "display_use": "allowed",
                    "non_display_use": "restricted",
                    "derived_data_use": "restricted",
                },
            },
            actor="data",
        )
        evidence = self.service.extract_evidence("doc_005", actor="analyst")
        thesis = self.service.create_thesis(
            {
                "thesis_id": "thesis_005",
                "issuer_id": "issuer_001",
                "hypothesis": "A public thesis",
                "evidence_ids": [item.evidence_id for item in evidence],
                "owner": "analyst",
            },
            actor="analyst",
        )
        signal = self.service.run_scoring(
            {"thesis_id": thesis.thesis_id, "strategy_type": "long"},
            actor="cio",
        )
        blocked = self.router.dispatch(
            "POST",
            "/api/decision-packs/build",
            {
                "signal_ids": [signal.signal_id],
                "risk_checks": ["reg_fd"],
                "source_labels": ["private"],
            },
            role="CIO",
        )
        self.assertFalse(blocked.success)
        self.assertEqual(blocked.status_code, 423)

        blocked_non_display = self.router.dispatch(
            "POST",
            "/api/decision-packs/build",
            {
                "signal_ids": [signal.signal_id],
                "risk_checks": ["non_display"],
                "non_display_requested": True,
                "non_display_approved": False,
            },
            role="CIO",
        )
        self.assertFalse(blocked_non_display.success)
        self.assertEqual(blocked_non_display.status_code, 423)

    def test_benchmark_prompt_crowding_challenger_and_playbook(self) -> None:
        seeded = self.router.dispatch("POST", "/api/templates/seed", {}, role="CIO")
        self.assertTrue(seeded.success)
        self.assertGreaterEqual(len(seeded.data["templates"]), 2)
        self.assertEqual(seeded.data["templates"][0]["template_id"], "tpl_company_default")

        mapping = self.router.dispatch(
            "POST",
            "/api/entity-mappings",
            {
                "mapping_id": "map_001",
                "issuer_id": "issuer_001",
                "lei": "LEI-DEMO-001",
                "cik": "0000001",
                "figi": "FIGI-DEMO-001",
                "isin": "ISIN-DEMO-001",
                "ticker": "DEMO",
                "market": "A",
            },
            role="平台负责人",
        )
        self.assertTrue(mapping.success)
        self.assertEqual(mapping.data["mapping_id"], "map_001")

        benchmark = self.router.dispatch(
            "POST",
            "/api/benchmarks",
            {
                "benchmark_id": "bm_001",
                "language": "zh",
                "task_type": "term_extraction",
                "sample_size": 300,
                "metrics": {"f1": 0.91},
                "threshold": {"f1": 0.9},
            },
            role="NLP/ML 负责人",
        )
        self.assertTrue(benchmark.success)
        self.assertEqual(benchmark.data["benchmark_id"], "bm_001")

        benchmark_result = self.router.dispatch(
            "POST",
            "/api/benchmarks/bm_001/evaluate",
            {"metrics": {"f1": 0.91}},
            role="NLP/ML 负责人",
        )
        self.assertTrue(benchmark_result.success)
        self.assertTrue(benchmark_result.data["passed"])

        prompt = self.router.dispatch(
            "POST",
            "/api/prompts/changes",
            {
                "request_id": "pr_001",
                "prompt_name": "research-summary",
                "change_level": "high",
                "requested_by": "ml_owner",
                "content": "update extraction prompt",
            },
            role="NLP/ML 负责人",
        )
        self.assertTrue(prompt.success)
        self.assertEqual(prompt.data["status"], "pending")

        prompt_list = self.router.dispatch("GET", "/api/prompts/changes", {"status": "pending"}, role="NLP/ML 负责人")
        self.assertTrue(prompt_list.success)
        self.assertEqual(prompt_list.data["total"], 1)
        self.assertEqual(prompt_list.data["changes"][0]["request_id"], "pr_001")

        approved = self.router.dispatch(
            "POST",
            "/api/prompts/changes/pr_001/approve",
            {"approved": True},
            role="风险/合规",
        )
        self.assertTrue(approved.success)
        self.assertEqual(approved.data["status"], "approved")

        template = self.router.dispatch(
            "POST",
            "/api/templates",
            {
                "template_id": "tpl_company",
                "template_type": "company",
                "name": "Company Research Card",
                "fields": ["summary", "valuation", "risk", "evidence"],
            },
            role="CIO",
        )
        self.assertTrue(template.success)
        self.assertEqual(template.data["template_type"], "company")

        scorecard = self.router.dispatch(
            "POST",
            "/api/scorecards",
            {
                "profile_id": "score_001",
                "strategy_type": "long",
                "name": "Long Scorecard",
                "weights": {"quality": 0.4, "valuation": 0.3, "catalyst": 0.3},
                "threshold_long": 0.6,
            },
            role="CIO",
        )
        self.assertTrue(scorecard.success)
        self.assertEqual(scorecard.data["profile_id"], "score_001")

        crowding = self.router.dispatch(
            "POST",
            "/api/crowding/snapshots",
            {
                "snapshot_id": "crd_001",
                "issuer_id": "issuer_001",
                "score": 0.72,
                "source": "13F",
                "rationale": "crowded long",
            },
            role="PM",
        )
        self.assertTrue(crowding.success)
        self.assertEqual(crowding.data["score"], 0.72)

        self.service.ingest_document(
            {
                "document_id": "doc_004",
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "source_id": "src_sec",
                "source_type": "regulatory",
                "document_type": "annual_report",
                "source_uri": "https://example.invalid/doc-004",
                "body": "Revenue grew. Margin compressed.",
                "rights_tag": {
                    "license_class": "public",
                    "training_allowed": False,
                    "redistribution_allowed": False,
                    "display_use": "allowed",
                    "non_display_use": "restricted",
                    "derived_data_use": "restricted",
                },
            },
            actor="data",
        )
        evidences = self.service.extract_evidence("doc_004", actor="analyst")
        thesis = self.service.create_thesis(
            {
                "thesis_id": "thesis_004",
                "issuer_id": "issuer_001",
                "horizon": "mid",
                "hypothesis": "Growth remains resilient",
                "evidence_ids": [e.evidence_id for e in evidences],
                "owner": "analyst",
            },
            actor="analyst",
        )
        challenger = self.router.dispatch(
            "POST",
            "/api/challenger/run",
            {
                "thesis_id": thesis.thesis_id,
                "source_conflict": 0.8,
                "valuation_gap": 0.6,
                "narrative_divergence": 0.7,
                "policy_risk": 0.2,
                "note": "multiple counter-signals",
            },
            role="风险/合规",
        )
        self.assertTrue(challenger.success)
        self.assertIn(challenger.data["verdict"], {"block", "review", "pass"})

        card = self.router.dispatch(
            "POST",
            "/api/research-cards",
            {
                "card_id": "card_001",
                "template_id": "tpl_company",
                "thesis_id": thesis.thesis_id,
                "title": "Demo company card",
                "fields": {
                    "summary": "Resilient growth",
                    "valuation": "reasonable",
                    "risk": "margin pressure",
                    "evidence": "doc_004",
                },
            },
            role="分析师",
        )
        self.assertTrue(card.success)
        self.assertEqual(card.data["template_type"], "company")

        scored_with_profile = self.router.dispatch(
            "POST",
            "/api/scoring/run",
            {
                "thesis_id": thesis.thesis_id,
                "strategy_type": "long",
                "profile_id": "score_001",
                "factor_scores": {"quality": 0.8, "valuation": 0.7, "catalyst": 0.6},
                "source_model": "scorecard",
                "model_version": "v2",
            },
            role="CIO",
        )
        self.assertTrue(scored_with_profile.success)
        self.assertEqual(scored_with_profile.data["profile_id"], "score_001")
        self.assertEqual(scored_with_profile.data["direction"], "long")

        playbook = self.router.dispatch(
            "POST",
            "/api/playbooks",
            {
                "playbook_id": "pb_001",
                "incident_type": "model_hallucination",
                "detection_rule": "missing evidence",
                "auto_action": "reject output",
                "manual_action": "review parser and prompt",
                "owner_role": "CRO",
            },
            role="风险/合规",
        )
        self.assertTrue(playbook.success)
        self.assertEqual(playbook.data["incident_type"], "model_hallucination")

        schedule = self.router.dispatch(
            "POST",
            "/api/drill-schedules",
            {
                "schedule_id": "drill_001",
                "incident_type": "model_hallucination",
                "cadence": "monthly",
                "owner": "CRO",
                "notes": "monthly tabletop exercise",
            },
            role="风险/合规",
        )
        self.assertTrue(schedule.success)
        self.assertEqual(schedule.data["schedule_id"], "drill_001")

        report = self.router.dispatch(
            "POST",
            "/api/incident-reports",
            {
                "report_id": "ir_001",
                "playbook_id": "pb_001",
                "root_cause": "missing retrieval grounding",
                "impact": "wrong recommendation delayed",
                "action_items": ["tighten evidence validation", "rerun benchmark"],
                "owner": "CRO",
            },
            role="风险/合规",
        )
        self.assertTrue(report.success)
        self.assertEqual(report.data["incident_type"], "model_hallucination")

        calendar = self.router.dispatch("GET", "/api/incidents/calendar", {}, role="风险/合规")
        self.assertTrue(calendar.success)
        self.assertEqual(len(calendar.data["playbooks"]), 1)
        self.assertEqual(len(calendar.data["reports"]), 1)
        self.assertEqual(len(calendar.data["schedules"]), 1)

        graph = self.router.dispatch("GET", "/api/graph/query", {"issuer_id": "issuer_001"}, role="CEO")
        self.assertTrue(graph.success)
        self.assertGreaterEqual(len(graph.data["entity_mappings"]), 1)
        self.assertGreaterEqual(len(graph.data["research_cards"]), 1)
        self.assertGreaterEqual(len(graph.data["edges"]), 1)
        self.assertTrue(all("source" in edge and "timestamp" in edge and "version" in edge and "confidence" in edge for edge in graph.data["edges"]))
        edge_quality = self.router.dispatch("GET", "/api/graph/edge-quality-report", {"issuer_id": "issuer_001"}, role="CEO")
        self.assertTrue(edge_quality.success, edge_quality.error)
        self.assertEqual(edge_quality.data["edge_metadata_coverage"], 1.0)

        dashboard = self.router.dispatch("GET", "/api/dashboard/ceo", {}, role="CEO")
        self.assertTrue(dashboard.success)
        self.assertGreaterEqual(len(dashboard.data["crowding_heatmap"]), 1)
        self.assertGreaterEqual(len(dashboard.data["filings_timeline"]), 1)

    def test_graph_query_links_evidence_portfolio_market_data_and_13f(self) -> None:
        doc = self.service.ingest_document(
            {
                "document_id": "doc_graph",
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "source_id": "src_sec",
                "source_type": "regulatory",
                "document_type": "10-K",
                "source_uri": "https://example.invalid/doc-graph",
                "body": "Revenue growth has improved.\n\nRisk factors include customer concentration.",
                "rights_tag": {
                    "license_class": "public",
                    "training_allowed": False,
                    "redistribution_allowed": False,
                    "display_use": "allowed",
                    "non_display_use": "restricted",
                    "derived_data_use": "restricted",
                },
                "language": "en",
            },
            actor="data",
        )
        evidences = self.service.extract_evidence(doc.document_id, actor="analyst")
        thesis = self.service.create_thesis(
            {
                "thesis_id": "thesis_graph",
                "issuer_id": "issuer_001",
                "horizon": "mid",
                "hypothesis": "Revenue growth can support earnings quality",
                "evidence_ids": [evidence.evidence_id for evidence in evidences],
                "falsifiers": ["margin compression"],
                "risk_factors": ["customer concentration"],
            },
            actor="analyst",
        )
        signal = self.service.run_scoring(
            {
                "signal_id": "sig_graph",
                "thesis_id": thesis.thesis_id,
                "strategy_type": "long",
                "source_model": "rules",
                "model_version": "v1",
            },
            actor="cio",
        )
        decision = self.service.build_decision_pack(
            {
                "decision_id": "dec_graph",
                "signal_ids": [signal.signal_id],
                "risk_checks": ["reg_fd", "non_display"],
            },
            actor="cio",
        )
        self.service.sign_decision(decision.decision_id, {"role": "风险/合规", "user": "risk"}, actor="risk")
        self.service.sign_decision(decision.decision_id, {"role": "CEO", "user": "ceo"}, actor="ceo")
        self.service.create_execution_intent(
            {
                "intent_id": "intent_graph",
                "decision_id": decision.decision_id,
                "security_id": "sec_001",
                "action": "buy",
                "target_weight": 0.04,
            },
            actor="pm",
        )
        self.service.register_market_data_point(
            {
                "data_id": "md_graph",
                "security_id": "sec_001",
                "source_id": "public_eod_market_data",
                "as_of_date": "2026-05-14",
                "data_type": "eod",
                "close": 88.5,
                "volume": 1200000,
            },
            actor="data",
        )
        self.service.register_13f_holding(
            {
                "holding_id": "hold_graph",
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "source_id": "src_sec",
                "filer_cik": "0001234567",
                "filer_name": "Graph Capital",
                "report_period": "2026-03-31",
                "shares": 200000,
                "value_usd": 17700000,
            },
            actor="data",
        )
        self.service.update_crowding_from_13f({"snapshot_id": "crd_graph", "issuer_id": "issuer_001"}, actor="risk")

        graph = self.router.dispatch("GET", "/api/graph/query", {"issuer_id": "issuer_001"}, role="CEO")
        self.assertTrue(graph.success)
        self.assertIn("md_graph", {item["data_id"] for item in graph.data["market_data"]})
        self.assertIn("hold_graph", {item["holding_id"] for item in graph.data["institutional_holdings"]})
        self.assertIn("intent_graph", {item["intent_id"] for item in graph.data["execution_intents"]})
        self.assertEqual(graph.data["portfolio_positions"][0]["security_id"], "sec_001")
        self.assertEqual(graph.data["portfolio_positions"][0]["approval_state"], "approved")
        edge_types = {edge["type"] for edge in graph.data["edges"]}
        self.assertTrue(
            {
                "ISSUES",
                "HAS_MARKET_DATA",
                "DISCLOSES",
                "HAS_EVIDENCE",
                "SUPPORTS",
                "GENERATES_SIGNAL",
                "INCLUDED_IN_DECISION",
                "CREATES_INTENT",
                "INTENT_ON",
                "HAS_13F_HOLDING",
                "HAS_CROWDING",
            }.issubset(edge_types)
        )
        traceability = self.router.dispatch("GET", "/api/graph/traceability-report", {"issuer_id": "issuer_001"}, role="CEO")
        self.assertTrue(traceability.success, traceability.error)
        self.assertEqual(traceability.data["thesis_traceability_rate"], 1.0)
        self.assertEqual(traceability.data["decision_traceability_rate"], 1.0)
        self.assertEqual(traceability.data["counts"]["untraceable_theses"], 0)
        thesis_trace = traceability.data["details"]["theses"][0]
        self.assertEqual(thesis_trace["resource_id"], "thesis_graph")
        self.assertEqual(set(thesis_trace["document_ids"]), {"doc_graph"})

        del self.service.store.evidence[evidences[0].evidence_id]
        broken_traceability = self.router.dispatch("GET", "/api/graph/traceability-report", {"issuer_id": "issuer_001"}, role="CEO")
        self.assertEqual(broken_traceability.data["counts"]["untraceable_theses"], 1)
        self.assertIn("missing_evidence_records", broken_traceability.data["details"]["theses"][0]["issues"])

    def test_structured_extraction_runs_benchmark_and_persists(self) -> None:
        self.service.ingest_document(
            {
                "document_id": "doc_extract",
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "source_id": "src_sec",
                "source_type": "regulatory",
                "document_type": "annual_report",
                "source_uri": "https://example.invalid/doc-extract",
                "body": "FY2025 revenue grew 12% to RMB 10.5 billion. Risk factors remain disclosed.",
                "rights_tag": {
                    "license_class": "public",
                    "training_allowed": False,
                    "redistribution_allowed": False,
                    "display_use": "allowed",
                    "non_display_use": "restricted",
                    "derived_data_use": "restricted",
                },
                "language": "en",
            },
            actor="data",
        )
        evidence = self.service.extract_evidence("doc_extract", actor="analyst")[0]
        benchmark = self.router.dispatch(
            "POST",
            "/api/benchmarks",
            {
                "benchmark_id": "bm_extract",
                "language": "en",
                "task_type": "term_extraction",
                "sample_size": 1,
                "threshold": {"term_f1": 0.99, "number_recall": 1.0, "period_recall": 1.0, "evidence_locator_rate": 1.0},
            },
            role="NLP/ML 负责人",
        )
        self.assertTrue(benchmark.success)

        extraction = self.router.dispatch(
            "POST",
            "/api/extractions/run",
            {
                "extraction_id": "ext_001",
                "evidence_id": evidence.evidence_id,
                "benchmark_id": "bm_extract",
                "expected_terms": ["revenue"],
                "expected_numbers": 2,
                "expected_periods": 1,
                "parser_version": "rule-finance-1",
            },
            role="NLP/ML 负责人",
        )
        self.assertTrue(extraction.success)
        self.assertTrue(extraction.data["passed"])
        self.assertEqual(extraction.data["metrics"]["term_f1"], 1.0)
        self.assertEqual(extraction.data["metrics"]["number_recall"], 1.0)
        self.assertEqual(extraction.data["metrics"]["period_recall"], 1.0)
        self.assertEqual(extraction.data["metrics"]["evidence_locator_rate"], 1.0)
        self.assertEqual({item["canonical"] for item in extraction.data["terms"]}, {"revenue"})
        self.assertGreaterEqual(len(extraction.data["numbers"]), 2)
        self.assertEqual(extraction.data["periods"][0]["raw"], "FY2025")

        fetched = self.router.dispatch("GET", "/api/extractions/ext_001", {}, role="分析师")
        self.assertTrue(fetched.success)
        self.assertEqual(fetched.data["benchmark_id"], "bm_extract")
        self.assertEqual(self.service.store.benchmarks["bm_extract"].status, "passed")
        self.assertEqual(self.service.dashboard()["counts"]["extraction_results"], 1)

    def test_bilingual_benchmark_suite_runs_samples_and_intercepts_low_confidence(self) -> None:
        for document_id, language, body in [
            ("doc_bench_en", "en", "FY2025 revenue grew 12% to RMB 10.5 billion. Operating cash flow improved."),
            ("doc_bench_zh", "zh", "2025年营业收入增长12%，经营活动现金流改善。"),
            ("doc_bench_low", "en", "FY2025 revenue grew 3%."),
        ]:
            self.service.ingest_document(
                {
                    "document_id": document_id,
                    "issuer_id": "issuer_001",
                    "security_id": "sec_001",
                    "source_id": "src_sec",
                    "source_type": "regulatory",
                    "document_type": "annual_report",
                    "source_uri": f"https://example.invalid/{document_id}",
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
                actor="data",
            )
        benchmark = self.router.dispatch(
            "POST",
            "/api/benchmarks",
            {
                "benchmark_id": "bm_bilingual",
                "language": "mixed",
                "task_type": "term_extraction",
                "sample_size": 0,
                "threshold": {
                    "term_f1": 1.0,
                    "number_recall": 1.0,
                    "period_recall": 1.0,
                    "page_hit_rate": 1.0,
                    "evidence_locator_rate": 1.0,
                    "avg_confidence": 0.8,
                },
            },
            role="NLP/ML 负责人",
        )
        self.assertTrue(benchmark.success, benchmark.error)
        for sample_id, document_id, language, terms in [
            ("bms_en", "doc_bench_en", "en", ["revenue", "operating_cash_flow"]),
            ("bms_zh", "doc_bench_zh", "zh", ["revenue", "operating_cash_flow"]),
        ]:
            sample = self.router.dispatch(
                "POST",
                "/api/benchmarks/bm_bilingual/samples",
                {
                    "sample_id": sample_id,
                    "document_id": document_id,
                    "language": language,
                    "expected_terms": terms,
                    "expected_numbers": 1,
                    "expected_periods": 1,
                    "expected_pages": [1],
                },
                role="NLP/ML 负责人",
            )
            self.assertTrue(sample.success, sample.error)
        run = self.router.dispatch(
            "POST",
            "/api/benchmarks/bm_bilingual/run",
            {"run_id": "bmrn_bilingual", "sample_ids": ["bms_en", "bms_zh"], "min_confidence": 0.8},
            role="NLP/ML 负责人",
        )
        self.assertTrue(run.success, run.error)
        self.assertTrue(run.data["passed"])
        self.assertEqual(run.data["metrics"]["sample_count"], 2)
        self.assertEqual(run.data["metrics"]["failed_sample_count"], 0)
        self.assertEqual(run.data["metrics"]["language_metrics"]["en"]["term_f1"], 1.0)
        self.assertEqual(run.data["metrics"]["language_metrics"]["zh"]["page_hit_rate"], 1.0)

        low_evidence = self.service.extract_evidence("doc_bench_low", actor="analyst")[0]
        low_evidence.confidence = 0.4
        low_sample = self.router.dispatch(
            "POST",
            "/api/benchmarks/bm_bilingual/samples",
            {
                "sample_id": "bms_low",
                "document_id": "doc_bench_low",
                "language": "en",
                "expected_terms": ["revenue"],
                "expected_numbers": 1,
                "expected_periods": 1,
                "expected_pages": [1],
            },
            role="NLP/ML 负责人",
        )
        self.assertTrue(low_sample.success, low_sample.error)
        low_run = self.router.dispatch(
            "POST",
            "/api/benchmarks/bm_bilingual/run",
            {"run_id": "bmrn_low_confidence", "sample_ids": ["bms_low"], "min_confidence": 0.8},
            role="NLP/ML 负责人",
        )
        self.assertTrue(low_run.success, low_run.error)
        self.assertFalse(low_run.data["passed"])
        self.assertEqual(low_run.data["metrics"]["low_confidence_intercept_rate"], 1.0)
        self.assertIn("bms_low", low_run.data["regression_examples"])
        listed = self.router.dispatch("GET", "/api/benchmarks/bm_bilingual/samples", {"language": "zh"}, role="NLP/ML 负责人")
        self.assertEqual(listed.data["count"], 1)
        dashboard = self.service.dashboard()
        self.assertEqual(dashboard["counts"]["benchmark_samples"], 3)
        self.assertEqual(dashboard["counts"]["benchmark_runs"], 2)

    def test_research_answer_keeps_english_evidence_and_summary_audit(self) -> None:
        self.service.ingest_document(
            {
                "document_id": "doc_answer",
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "source_id": "src_sec",
                "source_type": "regulatory",
                "document_type": "10-K",
                "source_uri": "https://example.invalid/doc-answer",
                "body": "Revenue resilience improved in the public filing. Risk factors remain disclosed.",
                "rights_tag": {
                    "license_class": "public",
                    "training_allowed": False,
                    "redistribution_allowed": False,
                    "display_use": "allowed",
                    "non_display_use": "restricted",
                    "derived_data_use": "restricted",
                },
                "language": "en",
            },
            actor="data",
        )
        evidence = self.service.extract_evidence("doc_answer", actor="analyst")[0]
        answer = self.router.dispatch(
            "POST",
            "/api/research/answers",
            {
                "answer_id": "ans_001",
                "issuer_id": "issuer_001",
                "question": "What does the filing say about revenue resilience?",
                "evidence_ids": [evidence.evidence_id],
                "summary_version": "summary-v2",
                "prompt_version": "research-answer-v2",
                "model_version": "gpt-audit-v1",
                "human_review_status": "pending",
            },
            role="overseas_research",
        )
        self.assertTrue(answer.success)
        self.assertEqual(answer.data["source_publicness"], "public")
        self.assertEqual(answer.data["summary_version"], "summary-v2")
        self.assertEqual(answer.data["prompt_version"], "research-answer-v2")
        self.assertEqual(answer.data["model_version"], "gpt-audit-v1")
        self.assertFalse(answer.data["citation_truncated"])
        self.assertEqual(answer.data["citation_char_limit"], 0)
        self.assertIn("中文摘要", answer.data["chinese_summary"])
        self.assertIn(evidence.evidence_id, answer.data["evidence_ids"])
        self.assertEqual(answer.data["citations"][0]["evidence_id"], evidence.evidence_id)
        self.assertIn("10-K:doc_answer", answer.data["citations"][0]["format"])

        loaded = self.router.dispatch("GET", "/api/research/answers/ans_001", {}, role="analyst")
        self.assertTrue(loaded.success)
        self.assertEqual(loaded.data["source_document_ids"], ["doc_answer"])
        self.assertEqual(loaded.data["citations"][0]["source_uri"], "https://example.invalid/doc-answer")
        quality = self.router.dispatch("GET", "/api/research/answers/quality-report", {"issuer_id": "issuer_001"}, role="risk_compliance")
        self.assertTrue(quality.success, quality.error)
        self.assertEqual(quality.data["pending_review"], 1)
        self.assertEqual(quality.data["source_link_rate"], 1.0)
        self.assertIn("pending_human_review", quality.data["answers"][0]["issues"])
        benchmark = self.router.dispatch("GET", "/api/research/answers/summary-benchmark", {"issuer_id": "issuer_001"}, role="risk_compliance")
        self.assertTrue(benchmark.success, benchmark.error)
        self.assertEqual(benchmark.data["failed"], 1)
        self.assertIn("pending_human_review", benchmark.data["answers"][0]["blocking_issues"])
        self.assertTrue(benchmark.data["answers"][0]["source_linked"])
        self.assertGreaterEqual(benchmark.data["answers"][0]["english_anchor_coverage"], 0.2)
        metrics = self.router.dispatch("GET", "/api/metrics", {}, role="unknown")
        self.assertEqual(metrics.data["research_answer_pending_reviews"], 1)

        reviewed = self.router.dispatch(
            "POST",
            "/api/research/answers/ans_001/review",
            {"status": "approved", "reviewer": "lead_analyst"},
            actor="lead_analyst",
            role="overseas_research",
        )
        self.assertTrue(reviewed.success, reviewed.error)
        self.assertEqual(reviewed.data["human_review_status"], "approved")
        self.assertEqual(reviewed.data["reviewer"], "lead_analyst")
        latest_audit = self.service.store.audit_log[-1]
        self.assertEqual(latest_audit.action, "review_research_answer")
        self.assertEqual(latest_audit.resource_type, "research_answer")
        self.assertEqual(latest_audit.prompt_version, "research-answer-v2")
        self.assertEqual(latest_audit.model_version, "gpt-audit-v1")
        self.assertEqual(latest_audit.approval_state, "approved")
        reviewed_quality = self.router.dispatch("GET", "/api/research/answers/quality-report", {"issuer_id": "issuer_001"}, role="risk_compliance")
        self.assertEqual(reviewed_quality.data["pending_review"], 0)
        self.assertEqual(reviewed_quality.data["review_coverage"], 1.0)
        reviewed_benchmark = self.router.dispatch("POST", "/api/research/answers/summary-benchmark", {"issuer_id": "issuer_001"}, role="risk_compliance")
        self.assertEqual(reviewed_benchmark.data["passed"], 1)
        self.assertEqual(reviewed_benchmark.data["pass_rate"], 1.0)

    def test_research_answer_limits_non_public_citation_snippets(self) -> None:
        self.service.seed_default_sources(actor="risk")
        body = "Margin pressure and channel checks remain analyst reference material " * 20
        doc = self.service.ingest_document(
            {
                "document_id": "doc_local_research_answer",
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "source_id": "local_research_reports",
                "source_type": "local_reference",
                "document_type": "research",
                "source_uri": "local://research-reports/demo.pdf",
                "body": body,
                "rights_tag": {
                    "license_class": "local_research_reference",
                    "training_allowed": False,
                    "redistribution_allowed": False,
                    "display_use": "restricted",
                    "non_display_use": "restricted",
                    "derived_data_use": "restricted",
                },
                "language": "en",
            },
            actor="data",
        )
        self.addCleanup(lambda: Path(doc.object_uri).unlink(missing_ok=True))
        evidence = self.service.extract_evidence("doc_local_research_answer", actor="analyst")[0]
        answer = self.router.dispatch(
            "POST",
            "/api/research/answers",
            {
                "answer_id": "ans_limited_citation",
                "issuer_id": "issuer_001",
                "question": "What does the research say about margin pressure?",
                "evidence_ids": [evidence.evidence_id],
                "citation_char_limit": 120,
            },
            role="overseas_research",
        )
        self.assertTrue(answer.success, answer.error)
        self.assertEqual(answer.data["source_publicness"], "local_research_reference")
        self.assertTrue(answer.data["citation_truncated"])
        self.assertEqual(answer.data["citation_char_limit"], 120)
        self.assertLessEqual(len(answer.data["english_source_text"]), 160)
        self.assertIn("[TRUNCATED_FOR_CITATION_BOUNDARY]", answer.data["english_source_text"])

    def test_structured_extraction_reads_markdown_tables(self) -> None:
        self.service.ingest_document(
            {
                "document_id": "doc_table",
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "source_id": "src_sec",
                "source_type": "regulatory",
                "document_type": "annual_report",
                "source_uri": "https://example.invalid/doc-table",
                "body": "Metric | FY2024 | FY2025\n--- | --- | ---\nRevenue | 9.0 | 10.5\nNet profit | 1.1 | 1.4",
                "rights_tag": {
                    "license_class": "public",
                    "training_allowed": False,
                    "redistribution_allowed": False,
                    "display_use": "allowed",
                    "non_display_use": "restricted",
                    "derived_data_use": "restricted",
                },
                "language": "en",
            },
            actor="data",
        )
        evidence = self.service.extract_evidence("doc_table", actor="analyst")[0]
        self.service.register_benchmark(
            {
                "benchmark_id": "bm_table",
                "language": "en",
                "task_type": "table_reading",
                "sample_size": 1,
                "threshold": {"table_recall": 1.0, "table_locator_rate": 1.0},
            },
            actor="ml",
        )
        extraction = self.router.dispatch(
            "POST",
            "/api/extractions/run",
            {
                "extraction_id": "ext_table",
                "evidence_id": evidence.evidence_id,
                "benchmark_id": "bm_table",
                "expected_tables": 1,
                "parser_version": "rule-table-1",
            },
            role="NLP/ML 负责人",
        )
        self.assertTrue(extraction.success)
        self.assertTrue(extraction.data["passed"])
        table = extraction.data["tables"][0]
        self.assertEqual(table["headers"], ["Metric", "FY2024", "FY2025"])
        self.assertEqual(table["row_count"], 2)
        self.assertEqual(table["column_count"], 3)
        self.assertEqual(table["cells"][2]["value"], "10.5")
        self.assertEqual(extraction.data["metrics"]["table_cell_count"], 6.0)
        self.assertEqual(extraction.data["metrics"]["table_locator_rate"], 1.0)

    def test_disallows_unexpected_document_type_for_source(self) -> None:
        bad = self.router.dispatch(
            "POST",
            "/api/ingestion/documents",
            {
                "document_id": "doc_bad",
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "source_id": "src_sec",
                "source_type": "regulatory",
                "document_type": "transcript",
                "source_uri": "https://example.invalid/doc-bad",
                "body": "This should fail.",
                "rights_tag": {
                    "license_class": "public",
                    "training_allowed": False,
                    "redistribution_allowed": False,
                    "display_use": "allowed",
                    "non_display_use": "restricted",
                    "derived_data_use": "restricted",
                },
            },
            role="数据工程",
        )
        self.assertFalse(bad.success)
        self.assertEqual(bad.status_code, 422)

    def test_ingests_sec_recent_filings_from_connector(self) -> None:
        class FakeSecConnectors:
            def __init__(self) -> None:
                self.body_fetches = 0

            def fetch_sec_recent_filings(self, cik, *, user_agent, limit=10, document_types=None):
                self.last_user_agent = user_agent
                return [
                    ConnectorDocument(
                        source_id="sec_edgar",
                        source_type="regulatory",
                        document_type="10-K",
                        source_uri="https://www.sec.gov/Archives/edgar/data/320193/000032019324000123/a10-k.htm",
                        language="en",
                        title="10-K filing 0000320193-24-000123",
                        published_at="2024-11-01",
                        metadata={
                            "cik": "0000320193",
                            "accession_no": "0000320193-24-000123",
                            "primary_doc": "a10-k.htm",
                        },
                    )
                ][:limit]

            def fetch_sec_document_body(self, source_uri, *, user_agent, max_bytes=2_000_000):
                self.body_fetches += 1
                return "Annual report body with revenue and risk evidence."

        fake = FakeSecConnectors()
        self.service.connectors = fake
        response = self.router.dispatch(
            "POST",
            "/api/ingestion/sec/recent",
            {
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "cik": "0000320193",
                "document_types": ["10-K"],
                "include_body": True,
                "user_agent": "test-contact@example.com",
                "limit": 1,
            },
            role="数据工程",
        )
        self.assertTrue(response.success)
        self.assertEqual(len(response.data["created"]), 1)
        created = response.data["created"][0]
        self.assertEqual(created["document_type"], "10-K")
        self.assertEqual(created["body"], "Annual report body with revenue and risk evidence.")
        self.assertEqual(fake.body_fetches, 1)
        self.assertEqual(fake.last_user_agent, "test-contact@example.com")

        duplicate = self.router.dispatch(
            "POST",
            "/api/ingestion/sec/recent",
            {
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "cik": "0000320193",
                "document_types": ["10-K"],
                "include_body": True,
                "user_agent": "test-contact@example.com",
                "limit": 1,
            },
            role="数据工程",
        )
        self.assertTrue(duplicate.success)
        self.assertEqual(duplicate.data["created"], [])
        self.assertEqual(duplicate.data["skipped"][0]["reason"], "already_exists")

    def test_ingests_hkex_recent_filings_from_connector(self) -> None:
        class FakeHkexConnectors:
            def __init__(self) -> None:
                self.last_user_agent = ""
                self.last_query = ""
                self.last_file_type = ""
                self.last_language = ""

            def fetch_hkex_recent_filings(self, query, *, user_agent, limit=10, file_type="pdf", language="en-UK"):
                self.last_user_agent = user_agent
                self.last_query = query
                self.last_file_type = file_type
                self.last_language = language
                return [
                    ConnectorDocument(
                        source_id="hkexnews",
                        source_type="exchange",
                        document_type="annual_report",
                        source_uri="https://www1.hkexnews.hk/listedco/listconews/sehk/2026/0514/2026051400954.pdf",
                        language="en",
                        title="2025 Annual Report",
                        body="Annual report highlight with revenue and risk points.",
                        published_at="2026-05-14",
                        metadata={"file_type": file_type},
                    )
                ][:limit]

            def fetch_document_binary(self, market, source_uri, *, user_agent, max_bytes=10_000_000):
                return b"%PDF-hkex"

        fake = FakeHkexConnectors()
        self.service.connectors = fake
        preview = self.router.dispatch(
            "POST",
            "/api/connectors/hkex/recent",
            {
                "query": "annual",
                "file_type": "pdf",
                "language": "en-UK",
                "limit": 1,
                "user_agent": "test-hkex@example.com",
            },
            role="data_engineer",
        )
        self.assertTrue(preview.success)
        self.assertEqual(len(preview.data["filings"]), 1)
        self.assertEqual(preview.data["filings"][0]["document_type"], "annual_report")
        self.assertEqual(fake.last_query, "annual")
        self.assertEqual(fake.last_user_agent, "test-hkex@example.com")
        self.assertEqual(fake.last_file_type, "pdf")
        self.assertEqual(fake.last_language, "en-UK")

        response = self.router.dispatch(
            "POST",
            "/api/ingestion/hkex/recent",
            {
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "query": "annual",
                "file_type": "pdf",
                "language": "en-UK",
                "limit": 1,
                "include_attachment": True,
                "user_agent": "test-hkex@example.com",
            },
            role="数据工程",
        )
        self.assertTrue(response.success)
        self.assertEqual(len(response.data["created"]), 1)
        created = response.data["created"][0]
        self.assertEqual(created["source_id"], "hkexnews")
        self.assertEqual(created["document_type"], "annual_report")
        self.assertEqual(created["title"], "2025 Annual Report")
        self.assertEqual(created["language"], "en")
        self.assertTrue(Path(created["object_uri"]).exists())
        self.assertEqual(Path(created["object_uri"]).suffix, ".pdf")
        self.assertEqual(created["content_sha256"], hashlib.sha256(b"%PDF-hkex").hexdigest())

        duplicate = self.router.dispatch(
            "POST",
            "/api/ingestion/hkex/recent",
            {
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "query": "annual",
                "file_type": "pdf",
                "language": "en-UK",
                "limit": 1,
                "user_agent": "test-hkex@example.com",
            },
            role="data_engineer",
        )
        self.assertTrue(duplicate.success)
        self.assertEqual(duplicate.data["created"], [])
        self.assertEqual(duplicate.data["skipped"][0]["reason"], "already_exists")

    def test_ingests_ashare_recent_filings_from_connector(self) -> None:
        class FakeAshareConnectors:
            def __init__(self) -> None:
                self.last_user_agent = ""
                self.last_security_code = ""
                self.last_begin_date = ""
                self.last_end_date = ""
                self.last_report_type = ""
                self.last_security_type = ""
                self.last_exchange = ""

            def fetch_ashare_recent_filings(self, security_code, *, user_agent, limit=10, begin_date="", end_date="", report_type="ALL", security_type="0101,120100,020100,020200,120200", exchange="auto"):
                self.last_security_code = security_code
                self.last_user_agent = user_agent
                self.last_begin_date = begin_date
                self.last_end_date = end_date
                self.last_report_type = report_type
                self.last_security_type = security_type
                self.last_exchange = exchange
                return [
                    ConnectorDocument(
                        source_id="ashare_exchange",
                        source_type="exchange",
                        document_type="annual_report",
                        source_uri="https://www.sse.com.cn/disclosure/listedinfo/announcement/c/new/2026-04-30/600000_20260430_7IXW.pdf",
                        language="zh",
                        title="上海浦东发展银行股份有限公司董事会2026年第五次会议决议公告",
                        body="临时公告",
                        published_at="2026-04-30",
                        metadata={"security_code": security_code},
                    )
                ][:limit]

            def fetch_document_binary(self, market, source_uri, *, user_agent, max_bytes=10_000_000):
                return b"%PDF-ashare"

        fake = FakeAshareConnectors()
        self.service.connectors = fake
        preview = self.router.dispatch(
            "POST",
            "/api/connectors/ashare/recent",
            {
                "security_code": "600000",
                "begin_date": "2026-04-01",
                "end_date": "2026-05-14",
                "limit": 1,
                "exchange": "sse",
                "user_agent": "test-ashare@example.com",
            },
            role="data_engineer",
        )
        self.assertTrue(preview.success)
        self.assertEqual(len(preview.data["filings"]), 1)
        self.assertEqual(preview.data["filings"][0]["document_type"], "annual_report")
        self.assertEqual(fake.last_security_code, "600000")
        self.assertEqual(fake.last_user_agent, "test-ashare@example.com")
        self.assertEqual(fake.last_begin_date, "2026-04-01")
        self.assertEqual(fake.last_end_date, "2026-05-14")
        self.assertEqual(fake.last_exchange, "sse")

        response = self.router.dispatch(
            "POST",
            "/api/ingestion/ashare/recent",
            {
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "security_code": "600000",
                "begin_date": "2026-04-01",
                "end_date": "2026-05-14",
                "limit": 1,
                "exchange": "sse",
                "include_attachment": True,
                "user_agent": "test-ashare@example.com",
            },
            role="数据工程",
        )
        self.assertTrue(response.success)
        self.assertEqual(len(response.data["created"]), 1)
        created = response.data["created"][0]
        self.assertEqual(created["source_id"], "ashare_exchange")
        self.assertEqual(created["document_type"], "annual_report")
        self.assertTrue(Path(created["object_uri"]).exists())
        self.assertEqual(Path(created["object_uri"]).suffix, ".pdf")
        self.assertEqual(created["content_sha256"], hashlib.sha256(b"%PDF-ashare").hexdigest())

        duplicate = self.router.dispatch(
            "POST",
            "/api/ingestion/ashare/recent",
            {
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "security_code": "600000",
                "begin_date": "2026-04-01",
                "end_date": "2026-05-14",
                "limit": 1,
                "user_agent": "test-ashare@example.com",
            },
            role="数据工程",
        )
        self.assertTrue(duplicate.success)
        self.assertEqual(duplicate.data["created"], [])
        self.assertEqual(duplicate.data["skipped"][0]["reason"], "already_exists")

    def test_ashare_connector_parses_szse_announcements(self) -> None:
        class FakeSzseConnector(AShareConnector):
            def _post_json(self, url, body, *, user_agent):
                self.last_body = body
                return {
                    "announceCount": 2,
                    "data": [
                        {
                            "annId": 1225307590,
                            "title": "捷安高科：2025年年度股东会决议公告",
                            "publishTime": "2026-05-14 19:20:07",
                            "attachPath": "/disc/disk03/finalpage/2026-05-14/f2cc9e00.PDF",
                            "attachFormat": "PDF",
                            "attachSize": 137,
                            "secCode": ["300845"],
                            "secName": ["捷安高科"],
                        }
                    ],
                }

        connector = FakeSzseConnector()
        documents = connector.fetch_recent_filings(
            security_code="300845",
            user_agent="test-ashare@example.com",
            limit=1,
            begin_date="2026-05-14",
            end_date="2026-05-14",
            exchange="szse",
        )
        self.assertEqual(connector.last_body["stock"], ["300845"])
        self.assertEqual(connector.last_body["seDate"], ["2026-05-14", "2026-05-14"])
        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0].metadata["exchange"], "szse")
        self.assertEqual(documents[0].metadata["security_code"], "300845")
        self.assertEqual(documents[0].source_uri, "https://www.szse.cn/disc/disk03/finalpage/2026-05-14/f2cc9e00.PDF")

    def test_ingestion_job_normalizes_deduplicates_and_records_errors(self) -> None:
        payload = {
            "job_id": "job_001",
            "items": [
                {
                    "market": "A",
                    "issuer_id": "issuer_001",
                    "security_id": "sec_001",
                    "raw": {
                        "code": "600000",
                        "announcement_id": "ann001",
                        "document_type": "annual_report",
                        "title": "Demo annual report",
                        "body": "A-share annual report body.",
                        "published_at": "2025-03-31",
                    },
                },
                {
                    "market": "A",
                    "issuer_id": "missing_issuer",
                    "raw": {
                        "code": "600001",
                        "announcement_id": "ann002",
                        "document_type": "annual_report",
                        "title": "Bad annual report",
                        "body": "Bad body.",
                    },
                },
            ],
        }
        response = self.router.dispatch("POST", "/api/ingestion/jobs", payload, role="data_engineer")
        self.assertTrue(response.success)
        self.assertEqual(response.data["status"], "partial")
        self.assertEqual(response.data["created"], 1)
        self.assertEqual(response.data["failed"], 1)
        document_id = response.data["created_document_ids"][0]
        self.assertIn(document_id, self.service.store.documents)
        self.assertTrue(Path(self.service.store.documents[document_id].object_uri).exists())

        job = self.router.dispatch("GET", "/api/ingestion/jobs/job_001", {}, role="data_engineer")
        self.assertTrue(job.success)
        self.assertEqual(job.data["failed"], 1)

        duplicate = self.router.dispatch(
            "POST",
            "/api/ingestion/jobs",
            {**payload, "job_id": "job_002", "items": payload["items"][:1]},
            role="data_engineer",
        )
        self.assertTrue(duplicate.success)
        self.assertEqual(duplicate.data["created"], 0)
        self.assertEqual(duplicate.data["skipped"], 1)

    def test_ingestion_schedule_runs_and_retries_failed_payloads(self) -> None:
        schedule = self.router.dispatch(
            "POST",
            "/api/ingestion/schedules",
            {
                "schedule_id": "sched_001",
                "name": "A-share daily ingest",
                "cadence": "manual",
                "retry_limit": 1,
                "payload": {
                    "job_id": "scheduled_job",
                    "items": [
                        {
                            "market": "A",
                            "issuer_id": "issuer_001",
                            "security_id": "sec_001",
                            "raw": {
                                "code": "600000",
                                "announcement_id": "sched001",
                                "document_type": "annual_report",
                                "title": "Scheduled annual report",
                                "body": "Scheduled body.",
                                "published_at": "2026-05-14",
                            },
                        }
                    ],
                },
            },
            role="data_engineer",
        )
        self.assertTrue(schedule.success)
        run = self.router.dispatch("POST", "/api/ingestion/schedules/run", {"schedule_ids": ["sched_001"]}, role="data_engineer")
        self.assertTrue(run.success)
        self.assertEqual(len(run.data["ran"]), 1)
        self.assertEqual(run.data["ran"][0]["job"]["created"], 1)
        self.assertEqual(run.data["ran"][0]["status"], "active")
        fetched = self.router.dispatch("GET", "/api/ingestion/schedules/sched_001", {}, role="data_engineer")
        self.assertTrue(fetched.success)
        self.assertEqual(fetched.data["retry_count"], 0)
        self.assertEqual(fetched.data["last_status"], "completed")

        failing = self.router.dispatch(
            "POST",
            "/api/ingestion/schedules",
            {
                "schedule_id": "sched_bad",
                "name": "bad ingest",
                "retry_limit": 1,
                "payload": {
                    "job_id": "scheduled_bad",
                    "items": [
                        {
                            "market": "A",
                            "issuer_id": "missing_issuer",
                            "raw": {
                                "code": "600001",
                                "announcement_id": "sched_bad",
                                "document_type": "annual_report",
                                "title": "Bad scheduled report",
                            },
                        }
                    ],
                },
            },
            role="data_engineer",
        )
        self.assertTrue(failing.success)
        first_retry = self.router.dispatch("POST", "/api/ingestion/schedules/run", {"schedule_ids": ["sched_bad"]}, role="data_engineer")
        self.assertTrue(first_retry.success)
        self.assertEqual(first_retry.data["ran"][0]["status"], "retrying")
        second_retry = self.router.dispatch("POST", "/api/ingestion/schedules/run", {"schedule_ids": ["sched_bad"]}, role="data_engineer")
        self.assertTrue(second_retry.success)
        self.assertEqual(second_retry.data["ran"][0]["status"], "failed")
        self.assertEqual(self.service.store.ingestion_schedules["sched_bad"].retry_count, 2)

    def test_demo_full_flow_seeds_dashboard_ready_state(self) -> None:
        response = self.router.dispatch("POST", "/api/demo/full-flow", {}, actor="platform_owner", role="platform")
        self.assertTrue(response.success)
        self.assertEqual(response.data["decision_id"], "dec_demo")
        self.assertEqual(response.data["intent_id"], "intent_demo")
        self.assertEqual(response.data["replay_id"], "replay_demo")
        self.assertTrue(response.data["report_id"].startswith("opr_"))
        self.assertEqual(response.data["dashboard"]["counts"]["documents"], 1)
        self.assertEqual(response.data["dashboard"]["counts"]["execution_intents"], 1)
        self.assertEqual(response.data["dashboard"]["counts"]["strategy_replays"], 1)
        self.assertEqual(response.data["dashboard"]["counts"]["operating_reports"], 1)
        self.assertEqual(self.service.decision_payload("dec_demo")["approval_state"], "approved")
        self.assertEqual(self.service.execution_intent_payload("intent_demo")["action"], "buy")
        decision = self.router.dispatch("GET", "/api/decision-packs/dec_demo", {}, role="CIO")
        self.assertTrue(decision.success)
        self.assertEqual(decision.data["approval_state"], "approved")
        report = self.router.dispatch("GET", f"/api/operating-reports/{response.data['report_id']}", {}, role="CEO")
        self.assertTrue(report.success)
        self.assertIn("evidence_coverage", report.data["metrics"])
        replay = self.router.dispatch("GET", "/api/strategy-replays/replay_demo", {}, role="CIO")
        self.assertTrue(replay.success)
        self.assertEqual(replay.data["decision_id"], "dec_demo")
        search = self.router.dispatch("GET", "/api/search", {"q": "services resilience", "issuer_id": "issuer_demo"}, role="CEO")
        self.assertTrue(search.success)
        self.assertGreaterEqual(len(search.data["results"]), 1)
        self.assertIn(search.data["results"][0]["resource_type"], {"document", "evidence", "thesis", "research_card"})
        self.assertFalse(any("<html>" in item["snippet"] for item in search.data["results"]))
        semantic = self.router.dispatch("POST", "/api/search/semantic", {"q": "resilient services demand", "issuer_id": "issuer_demo"}, role="CEO")
        self.assertTrue(semantic.success)
        self.assertEqual(semantic.data["backend"], "local-semantic")
        self.assertGreaterEqual(len(semantic.data["results"]), 1)
        self.assertIn("source_boundary", semantic.data["results"][0])
        self.assertEqual(semantic.data["payload_filter"]["include_restricted"], False)
        reranked = self.router.dispatch(
            "POST",
            "/api/search/semantic/rerank",
            {"q": "resilient services demand", "issuer_id": "issuer_demo", "limit": 3, "candidate_limit": 10},
            role="CEO",
        )
        self.assertTrue(reranked.success, reranked.error)
        self.assertEqual(reranked.data["reranker"], "local_term_coverage_weighted_score")
        self.assertGreaterEqual(reranked.data["candidate_count"], 1)
        self.assertGreaterEqual(reranked.data["results"][0]["rerank_score"], reranked.data["results"][-1]["rerank_score"])
        self.assertIn("term_coverage", reranked.data["results"][0]["score_components"])
        self.assertIn("vector_adapter_trigger", reranked.data["adapter_recommendation"])

        restricted_doc = self.service.ingest_document(
            {
                "document_id": "doc_semantic_restricted",
                "issuer_id": "issuer_demo",
                "security_id": "security_demo_us",
                "source_id": "local_research_reports",
                "source_type": "local_reference",
                "document_type": "research",
                "source_uri": "local://research/semantic",
                "body": "restricted alpha catalyst",
                "rights_tag": {
                    "license_class": "local_research_reference",
                    "training_allowed": False,
                    "redistribution_allowed": False,
                    "display_use": "restricted",
                    "non_display_use": "restricted",
                    "derived_data_use": "restricted",
                },
                "language": "en",
            },
            actor="data",
        )
        restricted_default = self.router.dispatch("POST", "/api/search/semantic", {"q": "restricted alpha catalyst", "issuer_id": "issuer_demo"}, role="CEO")
        self.assertNotIn(restricted_doc.document_id, {item["resource_id"] for item in restricted_default.data["results"]})
        restricted_included = self.router.dispatch("POST", "/api/search/semantic", {"q": "restricted alpha catalyst", "issuer_id": "issuer_demo", "include_restricted": True, "resource_types": ["document"]}, role="CEO")
        self.assertIn(restricted_doc.document_id, {item["resource_id"] for item in restricted_included.data["results"]})
        self.assertEqual(restricted_included.data["results"][0]["risk_level"], "restricted")
        restricted_reranked = self.router.dispatch(
            "POST",
            "/api/search/semantic/rerank",
            {
                "q": "restricted alpha catalyst",
                "issuer_id": "issuer_demo",
                "include_restricted": True,
                "resource_types": ["document"],
            },
            role="CEO",
        )
        self.assertTrue(restricted_reranked.success, restricted_reranked.error)
        restricted_rows = [item for item in restricted_reranked.data["results"] if item["resource_id"] == restricted_doc.document_id]
        self.assertTrue(restricted_rows)
        self.assertTrue(restricted_rows[0]["requires_manual_boundary_review"])
        self.assertGreater(restricted_rows[0]["score_components"]["boundary_penalty"], 0.0)

        benchmark = self.router.dispatch(
            "POST",
            "/api/search/semantic/benchmark",
            {"samples": [{"q": "restricted alpha catalyst", "issuer_id": "issuer_demo", "resource_types": ["document"], "include_restricted": True, "expected_resource_ids": [restricted_doc.document_id]}]},
            role="CEO",
        )
        self.assertTrue(benchmark.success, benchmark.error)
        self.assertEqual(benchmark.data["recall_at_k"], 1.0)
        self.assertGreaterEqual(len(self.service.thesis_payload("thesis_demo")["evidence"]), 1)

        neo4j_export = self.router.dispatch("GET", "/api/graph/neo4j/export", {"issuer_id": "issuer_demo"}, role="CEO")
        self.assertTrue(neo4j_export.success, neo4j_export.error)
        self.assertEqual(neo4j_export.data["adapter"]["format"], "neo4j_bulk_upsert_compatible")
        self.assertGreaterEqual(neo4j_export.data["node_count"], 1)
        self.assertGreaterEqual(neo4j_export.data["relationship_count"], 1)
        self.assertIn("AIQuant", neo4j_export.data["nodes"][0]["labels"])
        self.assertIn("source_ref", neo4j_export.data["relationships"][0]["properties"])
        neo4j_sync = self.router.dispatch(
            "POST",
            "/api/graph/neo4j/sync",
            {"issuer_id": "issuer_demo", "target": "https://graph.example.invalid/neo4j", "channel": "webhook", "provider": "webhook", "max_delivery_attempts": 2},
            role="platform",
        )
        self.assertTrue(neo4j_sync.success, neo4j_sync.error)
        self.assertEqual(neo4j_sync.data["count"], 1)
        self.assertEqual(neo4j_sync.data["notifications"][0]["payload"]["type"], "graph_neo4j_sync")
        self.assertEqual(neo4j_sync.data["notifications"][0]["payload"]["delivery_policy"]["provider"], "webhook")

        qdrant_export = self.router.dispatch(
            "POST",
            "/api/search/qdrant/export",
            {"issuer_id": "issuer_demo", "resource_types": ["thesis", "research_card"], "include_restricted": False},
            role="CEO",
        )
        self.assertTrue(qdrant_export.success, qdrant_export.error)
        self.assertEqual(qdrant_export.data["adapter"]["format"], "qdrant_points_upsert_compatible")
        self.assertGreaterEqual(qdrant_export.data["point_count"], 1)
        first_point = qdrant_export.data["points"][0]
        self.assertEqual(len(first_point["vector"]["text_tf_hash"]), 64)
        self.assertIn("rights_tag", first_point["payload"])
        qdrant_sync = self.router.dispatch(
            "POST",
            "/api/search/qdrant/sync",
            {"issuer_id": "issuer_demo", "target": "https://vector.example.invalid/qdrant", "channel": "webhook", "provider": "webhook"},
            role="platform",
        )
        self.assertTrue(qdrant_sync.success, qdrant_sync.error)
        self.assertEqual(qdrant_sync.data["notifications"][0]["payload"]["type"], "qdrant_vector_sync")
        failed_delivery = self.router.dispatch(
            "POST",
            "/api/alerts/notifications/deliver",
            {"channel": "webhook", "execute": True, "provider": "webhook", "timeout_ms": 100},
            role="platform",
        )
        self.assertTrue(failed_delivery.success, failed_delivery.error)
        self.assertGreaterEqual(failed_delivery.data["failed_count"], 2)
        retry_dry_run = self.router.dispatch(
            "GET",
            "/api/search/adapter-sync/retry",
            {"channels": ["webhook"], "status": "failed"},
            role="platform",
        )
        self.assertTrue(retry_dry_run.success, retry_dry_run.error)
        self.assertGreaterEqual(retry_dry_run.data["candidate_count"], 2)
        self.assertEqual(retry_dry_run.data["retried_count"], 0)
        self.assertIn("adapter_sync_retry_drill", retry_dry_run.data["usage_boundary"])
        retried = self.router.dispatch(
            "POST",
            "/api/search/adapter-sync/retry",
            {"channels": ["webhook"], "status": "failed", "execute": True, "provider": "dry-run-sender"},
            role="platform",
        )
        self.assertTrue(retried.success, retried.error)
        self.assertGreaterEqual(retried.data["retried_count"], 2)
        self.assertTrue(all(item["status"] == "sent" for item in retried.data["retry_results"]))

        second = self.router.dispatch("POST", "/api/demo/full-flow", {}, actor="platform_owner", role="platform")
        self.assertTrue(second.success)
        self.assertEqual(second.data["dashboard"]["counts"]["execution_intents"], 1)

    def test_vision_acceptance_gate_reports_real_readiness_gaps(self) -> None:
        self.router.dispatch("POST", "/api/demo/full-flow", {}, actor="platform_owner", role="platform")
        gate = self.router.dispatch("GET", "/api/readiness/vision-gate", {}, role="CEO")
        self.assertTrue(gate.success)
        self.assertEqual(gate.data["status"], "not_ready")
        gate_names = {item["name"] for item in gate.data["gates"]}
        self.assertIn("evidence_coverage", gate_names)
        self.assertIn("pending_prompt_changes", gate_names)
        self.assertIn("high_risk_challenger_coverage", gate_names)
        self.assertIn("source_governance_coverage", gate_names)
        self.assertIn("audit_completeness", gate_names)
        self.assertIn("graph_traceability_rate", gate_names)
        self.assertIn("quarterly_incident_drill_coverage", gate_names)
        self.assertIn("readiness_checklist_coverage", gate_names)
        self.assertIn("real_data_smoke_test", gate.data["pending_checklist"])
        self.assertIn("production_ui_screenshot_acceptance", gate.data["pending_checklist"])
        self.assertEqual(gate.data["counts"]["readiness_checks"], 0)
        remediation = self.router.dispatch("GET", "/api/readiness/remediation-report", {}, role="risk_compliance")
        self.assertTrue(remediation.success, remediation.error)
        action_ids = {item["resource_id"] for item in remediation.data["actions"]}
        self.assertIn("real_data_smoke_test", action_ids)
        self.assertIn("readiness_checklist_coverage", action_ids)
        self.assertGreaterEqual(remediation.data["total_actions"], len(gate.data["pending_checklist"]))

        recorded = self.router.dispatch(
            "POST",
            "/api/readiness/checklist/production_ui_screenshot_acceptance",
            {
                "status": "passed",
                "owner": "platform_owner",
                "evidence_uri": "artifact://ui-screenshots/2026-05-15",
                "notes": "desktop and mobile screenshots accepted",
                "metrics": {"desktop": 1, "mobile": 1},
                "measured_at": "2026-05-15T00:00:00+00:00",
            },
            actor="platform_owner",
            role="platform",
        )
        self.assertTrue(recorded.success, recorded.error)
        self.assertEqual(recorded.data["check_id"], "production_ui_screenshot_acceptance")

        capacity = self.router.dispatch(
            "POST",
            "/api/readiness/capacity-baseline",
            {
                "result": {
                    "records": 3,
                    "documents": 3,
                    "evidence": 3,
                    "avg_ms": {"ingest_ms": 1.0, "extract_ms": 2.0, "search_ms": 3.0, "dashboard_ms": 4.0},
                    "max_ms": {"ingest_ms": 5.0, "extract_ms": 6.0, "search_ms": 7.0, "dashboard_ms": 8.0},
                },
                "thresholds": {"ingest_ms": 10, "extract_ms": 10, "search_ms": 10, "dashboard_ms": 10},
                "evidence_uri": "artifact://capacity/baseline-2026-05-15.json",
                "measured_at": "2026-05-15T00:00:00+00:00",
            },
            actor="platform_owner",
            role="platform",
        )
        self.assertTrue(capacity.success, capacity.error)
        self.assertTrue(capacity.data["passed"])
        self.assertEqual(capacity.data["check"]["check_id"], "capacity_latency_report")
        self.assertEqual(capacity.data["check"]["metrics"]["baseline"]["records"], 3)

        checklist = self.router.dispatch("GET", "/api/readiness/checklist", {}, role="risk_compliance")
        self.assertTrue(checklist.success)
        self.assertEqual(checklist.data["required"], 8)
        self.assertEqual(checklist.data["passed"], 2)
        self.assertEqual(checklist.data["coverage"], 0.25)

        updated_gate = self.router.dispatch("GET", "/api/readiness/vision-gate", {}, role="CEO")
        self.assertTrue(updated_gate.success)
        self.assertNotIn("production_ui_screenshot_acceptance", updated_gate.data["pending_checklist"])
        self.assertNotIn("capacity_latency_report", updated_gate.data["pending_checklist"])
        self.assertIn("real_data_smoke_test", updated_gate.data["pending_checklist"])
        self.assertEqual(updated_gate.data["counts"]["readiness_checks"], 2)

    def test_readiness_evidence_package_tracks_external_validation_and_outbox(self) -> None:
        self.router.dispatch("POST", "/api/demo/full-flow", {}, actor="platform_owner", role="platform")
        package = self.router.dispatch(
            "POST",
            "/api/readiness/evidence-package",
            {"record_export": True, "include_passed": False},
            role="CEO",
            actor="ceo_owner",
        )
        self.assertTrue(package.success, package.error)
        self.assertEqual(package.data["status"], "not_ready")
        self.assertFalse(package.data["ready_for_launch"])
        self.assertIn("readiness_evidence_package_is_audit_manifest", package.data["usage_boundary"])
        self.assertGreaterEqual(package.data["required_evidence_count"], 8)
        required_ids = {item["check_id"] for item in package.data["required_evidence"]}
        self.assertIn("real_data_smoke_test", required_ids)
        self.assertIn("permission_red_team_test", required_ids)
        adapter_scopes = {item["scope"] for item in package.data["external_validations"]}
        self.assertIn("lineage_model_registry", adapter_scopes)
        self.assertIn("graph_vector_semantic_search", adapter_scopes)
        self.assertEqual(self.service.store.audit_log[-1].action, "export_readiness_evidence_package")

        notified = self.router.dispatch(
            "POST",
            "/api/readiness/evidence-package/notify",
            {
                "owner_targets": {"平台负责人": "platform-oncall", "风险/合规": "risk-oncall", "CEO": "ceo-office"},
                "owner_channels": {"平台负责人": "readiness_platform_outbox", "风险/合规": "readiness_risk_outbox"},
            },
            role="risk_compliance",
            actor="risk_owner",
        )
        self.assertTrue(notified.success, notified.error)
        self.assertEqual(notified.data["candidate_count"], package.data["missing_evidence_count"])
        self.assertGreaterEqual(notified.data["notification_count"], 8)
        notifications = notified.data["notifications"]
        smoke = next(item for item in notifications if item["payload"]["check_id"] == "real_data_smoke_test")
        self.assertEqual(smoke["channel"], "readiness_platform_outbox")
        self.assertEqual(smoke["target"], "platform-oncall")
        self.assertEqual(smoke["payload"]["type"], "readiness_evidence_required")
        self.assertIn("until_real_artifacts_are_attached", notified.data["usage_boundary"])

    def test_search_falls_back_when_external_backend_fails(self) -> None:
        class FailingSearchIndex:
            backend = "opensearch"

            def sync(self, records):
                raise RuntimeError("opensearch unavailable")

            def search(self, records, *, query, issuer_id="", limit=20):
                raise RuntimeError("opensearch unavailable")

            def describe(self):
                return {"backend": self.backend}

        self.service.ingest_document(
            {
                "document_id": "doc_search_fallback",
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "source_id": "src_sec",
                "source_type": "regulatory",
                "document_type": "annual_report",
                "source_uri": "https://example.invalid/doc-search-fallback",
                "body": "Services resilience remained visible in public filing evidence.",
                "rights_tag": {
                    "license_class": "public",
                    "training_allowed": False,
                    "redistribution_allowed": False,
                    "display_use": "allowed",
                    "non_display_use": "restricted",
                    "derived_data_use": "restricted",
                },
            },
            actor="data",
        )
        self.service.search_index = FailingSearchIndex()
        response = self.router.dispatch("GET", "/api/search", {"q": "services resilience", "issuer_id": "issuer_001"}, role="CEO")
        self.assertTrue(response.success)
        self.assertEqual(response.data["backend"], "local")
        self.assertEqual(response.data["fallback_from"], "opensearch")
        self.assertGreaterEqual(len(response.data["results"]), 1)

    def test_search_rebuild_indexes_records_and_falls_back(self) -> None:
        class FailingSearchIndex:
            backend = "opensearch"

            def sync(self, records):
                raise RuntimeError("opensearch unavailable")

            def search(self, records, *, query, issuer_id="", limit=20):
                raise RuntimeError("opensearch unavailable")

            def describe(self):
                return {"backend": self.backend}

        self.service.ingest_document(
            {
                "document_id": "doc_search_rebuild",
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "source_id": "src_sec",
                "source_type": "regulatory",
                "document_type": "10-K",
                "source_uri": "https://example.invalid/doc-search-rebuild",
                "body": "Search rebuild should index public filing evidence.",
                "rights_tag": {
                    "license_class": "public",
                    "training_allowed": False,
                    "redistribution_allowed": False,
                    "display_use": "allowed",
                    "non_display_use": "restricted",
                    "derived_data_use": "restricted",
                },
                "language": "en",
            },
            actor="data",
        )
        self.service.search_index = FailingSearchIndex()
        rebuilt = self.router.dispatch(
            "POST",
            "/api/search/rebuild",
            {"issuer_id": "issuer_001", "targets": ["keyword", "semantic"], "include_restricted": True},
            actor="platform",
            role="platform",
        )
        self.assertTrue(rebuilt.success, rebuilt.error)
        self.assertEqual(rebuilt.data["status"], "ok")
        self.assertGreaterEqual(rebuilt.data["record_count"], 1)
        self.assertEqual(rebuilt.data["sync"]["keyword"]["fallback_from"], "opensearch")
        self.assertEqual(rebuilt.data["sync"]["semantic"]["backend"], "local-semantic")
        self.assertIn("document", rebuilt.data["resource_counts"])
        self.assertEqual(self.service.store.audit_log[-1].action, "rebuild_search_indexes")

    def test_duplicate_ids_raise_conflict(self) -> None:
        duplicate = self.router.dispatch(
            "POST",
            "/api/ingestion/sources",
            {
                "source_id": "src_sec",
                "source_type": "regulatory",
                "rights_tag": {
                    "license_class": "public",
                    "training_allowed": False,
                    "redistribution_allowed": False,
                    "display_use": "allowed",
                    "non_display_use": "restricted",
                    "derived_data_use": "restricted",
                },
            },
            role="风险/合规",
        )
        self.assertFalse(duplicate.success)
        self.assertEqual(duplicate.status_code, 409)
        with self.assertRaises(ConflictError):
            self.service.register_source(
                {
                    "source_id": "src_sec",
                    "source_type": "regulatory",
                    "rights_tag": {
                        "license_class": "public",
                        "training_allowed": False,
                        "redistribution_allowed": False,
                        "display_use": "allowed",
                        "non_display_use": "restricted",
                        "derived_data_use": "restricted",
                    },
                },
                actor="risk",
            )

    def test_sqlite_store_persists_core_workflow(self) -> None:
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "state.db"
            service = SystemService(SQLiteStore(db_path))
            service.register_source(
                {
                    "source_id": "src_persist",
                    "source_type": "regulatory",
                    "allowed_document_types": ["10-K"],
                    "rights_tag": {
                        "license_class": "public",
                        "training_allowed": False,
                        "redistribution_allowed": False,
                        "display_use": "allowed",
                        "non_display_use": "restricted",
                        "derived_data_use": "restricted",
                    },
                },
                actor="risk",
            )
            service.register_issuer(
                {
                    "issuer_id": "issuer_persist",
                    "legal_name": "Persist Corp",
                    "market": ["U"],
                    "lei": "LEI-PERSIST-001",
                    "cik": "0000999",
                    "country": "US",
                },
                actor="platform",
            )
            service.register_security(
                {
                    "security_id": "security_persist",
                    "issuer_id": "issuer_persist",
                    "ticker": "PERS",
                    "figi": "FIGI-PERSIST-001",
                    "exchange": "NASDAQ",
                    "currency": "USD",
                    "market": "U",
                },
                actor="platform",
            )
            service.seed_default_sources(actor="risk")
            market_point = service.register_market_data_point(
                {
                    "data_id": "md_persist",
                    "security_id": "security_persist",
                    "source_id": "public_eod_market_data",
                    "as_of_date": "2026-05-14",
                    "data_type": "eod",
                    "close": 101.25,
                    "adjusted_close": 101.25,
                    "volume": 250000,
                },
                actor="data",
            )
            holding = service.register_13f_holding(
                {
                    "holding_id": "hold_persist",
                    "issuer_id": "issuer_persist",
                    "security_id": "security_persist",
                    "source_id": "sec_edgar",
                    "filer_cik": "0001999999",
                    "filer_name": "Persist Fund",
                    "report_period": "2026-03-31",
                    "shares": 500,
                    "value_usd": 50625,
                },
                actor="data",
            )
            service.ingest_document(
                {
                    "document_id": "doc_persist",
                    "issuer_id": "issuer_persist",
                    "security_id": "security_persist",
                    "source_id": "src_persist",
                    "source_type": "regulatory",
                    "document_type": "10-K",
                    "source_uri": "https://www.sec.gov/Archives/edgar/data/999/0000999/a10-k.htm",
                    "body": "Revenue expanded. Risks remain disclosed.",
                    "rights_tag": {
                        "license_class": "public",
                        "training_allowed": False,
                        "redistribution_allowed": False,
                        "display_use": "allowed",
                        "non_display_use": "restricted",
                        "derived_data_use": "restricted",
                    },
                    "language": "en",
                },
                actor="data",
            )
            evidence = service.extract_evidence("doc_persist", actor="analyst")
            benchmark = service.register_benchmark(
                {
                    "benchmark_id": "bm_persist",
                    "language": "en",
                    "task_type": "term_extraction",
                    "sample_size": 1,
                    "threshold": {"term_f1": 1.0, "evidence_locator_rate": 1.0},
                },
                actor="ml",
            )
            extraction = service.extract_structured_facts(
                {
                    "extraction_id": "ext_persist",
                    "evidence_id": evidence[0].evidence_id,
                    "benchmark_id": benchmark.benchmark_id,
                    "expected_terms": ["revenue"],
                },
                actor="ml",
            )
            table_doc = service.ingest_document(
                {
                    "document_id": "doc_table_persist",
                    "issuer_id": "issuer_persist",
                    "security_id": "security_persist",
                    "source_id": "src_persist",
                    "source_type": "regulatory",
                    "document_type": "10-K",
                    "source_uri": "https://example.invalid/doc-table-persist",
                    "body": "Metric | FY2025\n--- | ---\nRevenue | 10.5",
                    "rights_tag": {
                        "license_class": "public",
                        "training_allowed": False,
                        "redistribution_allowed": False,
                        "display_use": "allowed",
                        "non_display_use": "restricted",
                        "derived_data_use": "restricted",
                    },
                    "language": "en",
                },
                actor="data",
            )
            table_evidence = service.extract_evidence(table_doc.document_id, actor="analyst")[0]
            table_extraction = service.extract_structured_facts(
                {
                    "extraction_id": "ext_table_persist",
                    "evidence_id": table_evidence.evidence_id,
                    "expected_tables": 1,
                },
                actor="ml",
            )
            thesis = service.create_thesis(
                {
                    "thesis_id": "thesis_persist",
                    "issuer_id": "issuer_persist",
                    "hypothesis": "Persistence keeps evidence-backed research available",
                    "evidence_ids": [item.evidence_id for item in evidence],
                    "owner": "analyst",
                },
                actor="analyst",
            )
            signal = service.run_scoring({"thesis_id": thesis.thesis_id, "strategy_type": "long"}, actor="cio")
            pack = service.build_decision_pack({"signal_ids": [signal.signal_id], "risk_checks": ["reg_fd"]}, actor="cio")
            service.sign_decision(pack.decision_id, {"role": "风险/合规", "user": "risk_owner"}, actor="risk")
            approved = service.sign_decision(pack.decision_id, {"role": "CEO", "user": "ceo_owner"}, actor="ceo")
            intent = service.create_execution_intent(
                {
                    "intent_id": "intent_persist",
                    "decision_id": approved.decision_id,
                    "security_id": "security_persist",
                    "action": "buy",
                    "target_weight": 0.03,
                },
                actor="pm",
            )
            simulated = service.simulate_execution_intent(
                intent.intent_id,
                {
                    "execution_id": "simexec_persist",
                    "transaction_id": "ptxn_simexec_persist",
                    "quantity": 12,
                    "fill_price": 101.25,
                    "account_id": "paper_persist",
                },
                actor="pm",
            )
            replay = service.create_strategy_replay(
                {
                    "replay_id": "replay_persist",
                    "decision_id": approved.decision_id,
                    "expected_outcome": "positive alpha",
                    "actual_outcome": "pending",
                    "variance_reason": "not realized",
                    "next_action": "review later",
                },
                actor="cio",
            )
            schedule = service.register_ingestion_schedule(
                {
                    "schedule_id": "sched_persist",
                    "name": "Persisted ingest",
                    "cadence": "daily",
                    "payload": {"job_id": "persist_sched_job", "items": []},
                    "retry_limit": 3,
                },
                actor="data",
            )
            report = service.generate_operating_report({"report_id": "opr_persist", "period": "2026-05"}, actor="ceo")
            audit_count = len(service.store.audit_log)

            reloaded = SystemService(SQLiteStore(db_path))
            self.assertIn("src_persist", reloaded.store.sources)
            self.assertIn("issuer_persist", reloaded.store.issuers)
            self.assertIn(market_point.data_id, reloaded.store.market_data)
            self.assertEqual(reloaded.market_data_payload({"security_id": "security_persist"})["market_data"][0]["close"], 101.25)
            self.assertIn(holding.holding_id, reloaded.store.institutional_holdings)
            self.assertEqual(reloaded.institutional_holdings_payload({"issuer_id": "issuer_persist"})["holdings"][0]["value_usd"], 50625.0)
            self.assertIn("doc_persist", reloaded.store.documents)
            self.assertTrue(Path(reloaded.store.documents["doc_persist"].object_uri).exists())
            self.assertTrue(reloaded.store.documents["doc_persist"].content_sha256)
            self.assertIn(thesis.thesis_id, reloaded.store.theses)
            self.assertIn(signal.signal_id, reloaded.store.signals)
            self.assertIn(extraction.extraction_id, reloaded.store.extraction_results)
            self.assertEqual(reloaded.extraction_payload(extraction.extraction_id)["benchmark_id"], benchmark.benchmark_id)
            self.assertTrue(reloaded.extraction_payload(extraction.extraction_id)["passed"])
            self.assertEqual(reloaded.extraction_payload(table_extraction.extraction_id)["tables"][0]["row_count"], 1)
            self.assertEqual(reloaded.decision_payload(approved.decision_id)["approval_state"], "approved")
            self.assertEqual(len(reloaded.decision_payload(approved.decision_id)["signatures"]), 2)
            self.assertEqual(reloaded.execution_intent_payload(intent.intent_id)["decision_id"], approved.decision_id)
            self.assertEqual(reloaded.simulated_executions_payload({"intent_id": intent.intent_id})["executions"][0]["transaction_id"], simulated["execution"]["transaction_id"])
            self.assertEqual(reloaded.strategy_replay_payload(replay.replay_id)["decision_id"], approved.decision_id)
            self.assertEqual(reloaded.ingestion_schedule_payload(schedule.schedule_id)["cadence"], "daily")
            self.assertEqual(reloaded.operating_report_payload(report.report_id)["period"], "2026-05")
            self.assertEqual(len(reloaded.thesis_payload(thesis.thesis_id)["evidence"]), len(evidence))
            self.assertEqual(len(reloaded.store.audit_log), audit_count)

    def test_postgresql_store_runtime_persists_records_and_audit_with_driver(self) -> None:
        database = _FakePostgresDatabase()
        dsn = "postgresql://example.invalid/ai_quant"
        service = SystemService(PostgreSQLStore(dsn, connect=database.connect))
        self.assertGreaterEqual(database.schema_runs, 1)
        self.assertEqual(database.dsns[0], dsn)

        service.register_source(
            {
                "source_id": "src_pg",
                "source_type": "regulatory",
                "allowed_document_types": ["10-K"],
                "rights_tag": {
                    "license_class": "public",
                    "training_allowed": False,
                    "redistribution_allowed": False,
                    "display_use": "allowed",
                    "non_display_use": "restricted",
                    "derived_data_use": "restricted",
                },
            },
            actor="risk",
        )
        service.register_issuer(
            {
                "issuer_id": "issuer_pg",
                "legal_name": "Postgres Corp",
                "market": ["U"],
                "lei": "LEI-PG-001",
                "cik": "0001888888",
                "country": "US",
            },
            actor="platform",
        )
        service.register_security(
            {
                "security_id": "security_pg",
                "issuer_id": "issuer_pg",
                "ticker": "PGSQL",
                "figi": "FIGI-PG-001",
                "exchange": "NASDAQ",
                "currency": "USD",
                "market": "U",
            },
            actor="platform",
        )
        service.seed_default_sources(actor="risk")
        market_point = service.register_market_data_point(
            {
                "data_id": "md_pg",
                "security_id": "security_pg",
                "source_id": "public_eod_market_data",
                "as_of_date": "2026-05-14",
                "data_type": "eod",
                "close": 45.75,
                "volume": 125000,
            },
            actor="data",
        )
        holding = service.register_13f_holding(
            {
                "holding_id": "hold_pg",
                "issuer_id": "issuer_pg",
                "security_id": "security_pg",
                "source_id": "sec_edgar",
                "filer_cik": "0001777777",
                "filer_name": "Postgres Fund",
                "report_period": "2026-03-31",
                "shares": 1000,
                "value_usd": 45750,
            },
            actor="data",
        )
        audit_count = len(service.store.audit_log)

        reloaded = SystemService(PostgreSQLStore(dsn, connect=database.connect))
        self.assertIn("src_pg", reloaded.store.sources)
        self.assertIn("issuer_pg", reloaded.store.issuers)
        self.assertIn("security_pg", reloaded.store.securities)
        self.assertIn(market_point.data_id, reloaded.store.market_data)
        self.assertEqual(reloaded.market_data_payload({"security_id": "security_pg"})["market_data"][0]["close"], 45.75)
        self.assertIn(holding.holding_id, reloaded.store.institutional_holdings)
        self.assertEqual(reloaded.institutional_holdings_payload({"issuer_id": "issuer_pg"})["holdings"][0]["value_usd"], 45750.0)
        self.assertEqual(len(reloaded.store.audit_log), audit_count)
        self.assertIn(("market_data", "md_pg"), database.records)
        self.assertIn("register_market_data_point", {event["payload"]["action"] for event in database.audit.values()})

    def test_sqlite_to_postgres_migration_rewrites_target_with_counts(self) -> None:
        with TemporaryDirectory() as tmpdir:
            sqlite_path = Path(tmpdir) / "state.db"
            sqlite_service = SystemService(SQLiteStore(sqlite_path))
            sqlite_service.register_source(
                {
                    "source_id": "src_migrate",
                    "source_type": "regulatory",
                    "allowed_document_types": ["10-K"],
                    "rights_tag": {
                        "license_class": "public",
                        "training_allowed": False,
                        "redistribution_allowed": False,
                        "display_use": "allowed",
                        "non_display_use": "restricted",
                        "derived_data_use": "restricted",
                    },
                },
                actor="risk",
            )
            sqlite_service.register_issuer(
                {
                    "issuer_id": "issuer_migrate",
                    "legal_name": "Migrate Corp",
                    "market": ["U"],
                    "country": "US",
                },
                actor="platform",
            )
            sqlite_service.register_security(
                {
                    "security_id": "security_migrate",
                    "issuer_id": "issuer_migrate",
                    "ticker": "MIGR",
                    "exchange": "NYSE",
                    "currency": "USD",
                    "market": "U",
                },
                actor="platform",
            )
            database = _FakePostgresDatabase()
            dsn = "postgresql://user:secret@example.invalid/ai_quant"

            with self.assertRaises(ValueError):
                migrate_sqlite_to_postgres(sqlite_path, dsn, connect=database.connect)

            summary = migrate_sqlite_to_postgres(sqlite_path, dsn, replace=True, connect=database.connect)
            self.assertEqual(summary["postgres_dsn"], "postgresql://user:***@example.invalid/ai_quant")
            self.assertEqual(summary["counts"]["sources"], 1)
            self.assertEqual(summary["counts"]["issuers"], 1)
            self.assertEqual(summary["counts"]["securities"], 1)
            self.assertEqual(summary["counts"]["audit_log"], len(sqlite_service.store.audit_log))

            reloaded = SystemService(PostgreSQLStore(dsn, connect=database.connect))
            self.assertIn("src_migrate", reloaded.store.sources)
            self.assertIn("issuer_migrate", reloaded.store.issuers)
            self.assertIn("security_migrate", reloaded.store.securities)
            self.assertEqual(len(reloaded.store.audit_log), len(sqlite_service.store.audit_log))

    def test_postgres_schema_migration_script_dry_run_apply_and_rollback_record(self) -> None:
        database = _FakePostgresDatabase()
        dsn = "postgresql://example.invalid/ai_quant"
        dry_run = apply_postgres_schema(dsn, dry_run=True)
        self.assertEqual(dry_run["version"], BASELINE_VERSION)
        self.assertTrue(dry_run["dry_run"])
        applied = apply_postgres_schema(dsn, connect=database.connect)
        self.assertTrue(applied["applied"])
        self.assertTrue(any("schema_migrations" in statement for statement in database.statements))
        rolled_back = mark_last_migration_rolled_back(dsn, connect=database.connect)
        self.assertTrue(rolled_back["rolled_back_record"])
        migration_doc = Path("docs/postgresql-migrations.md").read_text(encoding="utf-8")
        self.assertIn("--dry-run", migration_doc)
        self.assertIn("--rollback-last", migration_doc)

    def test_s3_compatible_object_store_builds_signed_put_and_get(self) -> None:
        requests = []

        def fake_send(request):
            requests.append(request)
            if request.get_method() == "GET":
                return b"stored-object"
            return b""

        store = S3CompatibleObjectStore(
            endpoint_url="https://objects.example.test",
            bucket="ai-quant",
            access_key="access",
            secret_key="secret",
            region="us-east-1",
            prefix="raw",
            http_send=fake_send,
        )
        stored = store.put_bytes("src_sec", "doc_prod", b"payload", suffix=".pdf")
        self.assertEqual(stored.uri, "s3://ai-quant/raw/src_sec/doc_prod.pdf")
        self.assertEqual(stored.sha256, hashlib.sha256(b"payload").hexdigest())
        self.assertEqual(requests[0].get_method(), "PUT")
        self.assertIn("/ai-quant/raw/src_sec/doc_prod.pdf", requests[0].full_url)
        self.assertIn("Authorization", requests[0].headers)

        data = store.read_bytes(stored.uri)
        self.assertEqual(data, b"stored-object")
        self.assertEqual(requests[1].get_method(), "GET")

    def test_opensearch_index_syncs_and_maps_search_hits(self) -> None:
        requests = []

        def fake_send(request):
            requests.append(request)
            if request.full_url.endswith("/_bulk"):
                return b'{"errors":false}'
            return (
                b'{"hits":{"hits":[{"_score":3.5,"_source":{"resource_type":"document",'
                b'"resource_id":"doc_os","issuer_id":"issuer_001","title":"Annual",'
                b'"body":"Services resilience evidence"}}]}}'
            )

        index = OpenSearchIndex(endpoint_url="https://search.example.test", index_name="ai_quant", http_send=fake_send)
        sync = index.sync(
            [
                SearchRecord(
                    resource_type="document",
                    resource_id="doc_os",
                    issuer_id="issuer_001",
                    title="Annual",
                    body="Services resilience evidence",
                )
            ]
        )
        self.assertEqual(sync["backend"], "opensearch")
        self.assertEqual(sync["indexed"], 1)
        self.assertEqual(requests[0].get_method(), "POST")
        self.assertTrue(requests[0].full_url.endswith("/_bulk"))

        results = index.search([], query="services", issuer_id="issuer_001", limit=5)
        self.assertEqual(results[0]["resource_type"], "document")
        self.assertEqual(results[0]["score"], 3.5)
        self.assertTrue(requests[1].full_url.endswith("/ai_quant/_search"))

    def test_postgresql_schema_baseline_is_documented(self) -> None:
        schema = Path("docs/postgresql-schema.sql").read_text(encoding="utf-8")
        required = [
            "CREATE TABLE IF NOT EXISTS ai_quant.records",
            "CREATE TABLE IF NOT EXISTS ai_quant.schema_migrations",
            "payload JSONB NOT NULL",
            "CREATE TABLE IF NOT EXISTS ai_quant.audit_log",
            "CREATE OR REPLACE VIEW ai_quant.documents",
            "CREATE INDEX IF NOT EXISTS idx_ai_quant_records_payload_gin",
            "CREATE INDEX IF NOT EXISTS idx_ai_quant_system_alerts_status",
            "CREATE OR REPLACE VIEW ai_quant.system_alerts",
            "CREATE INDEX IF NOT EXISTS idx_ai_quant_research_answers_issuer",
            "CREATE OR REPLACE VIEW ai_quant.research_answers",
            "CREATE INDEX IF NOT EXISTS idx_ai_quant_operating_reports_status",
            "CREATE OR REPLACE VIEW ai_quant.operating_reports",
            "CREATE INDEX IF NOT EXISTS idx_ai_quant_strategy_replays_filter",
            "CREATE OR REPLACE VIEW ai_quant.strategy_replays",
            "CREATE INDEX IF NOT EXISTS idx_ai_quant_portfolio_proposals_status",
            "CREATE OR REPLACE VIEW ai_quant.portfolio_proposals",
            "CREATE INDEX IF NOT EXISTS idx_ai_quant_simulated_executions_intent",
            "CREATE OR REPLACE VIEW ai_quant.simulated_executions",
            "CREATE INDEX IF NOT EXISTS idx_ai_quant_portfolio_transactions_filter",
            "CREATE OR REPLACE VIEW ai_quant.portfolio_transactions",
            "CREATE INDEX IF NOT EXISTS idx_ai_quant_benchmark_samples_benchmark",
            "CREATE OR REPLACE VIEW ai_quant.benchmark_samples",
            "CREATE INDEX IF NOT EXISTS idx_ai_quant_benchmark_runs_benchmark",
            "CREATE OR REPLACE VIEW ai_quant.benchmark_runs",
            "CREATE INDEX IF NOT EXISTS idx_ai_quant_disclosure_events_issuer",
            "CREATE OR REPLACE VIEW ai_quant.disclosure_events",
            "CREATE INDEX IF NOT EXISTS idx_ai_quant_corporate_actions_security",
            "CREATE OR REPLACE VIEW ai_quant.corporate_actions",
            "CREATE INDEX IF NOT EXISTS idx_ai_quant_alert_notifications_status",
            "CREATE OR REPLACE VIEW ai_quant.alert_notifications",
        ]
        for fragment in required:
            self.assertIn(fragment, schema)

    def test_ui_static_contract_matches_target_information_architecture(self) -> None:
        result = validate_ui_html(run_node=False)
        self.assertEqual(result["nav_labels"], 10)
        self.assertEqual(result["status_labels"], 7)
        self.assertEqual(result["required_ids"], 42)
        self.assertEqual(result["required_functions"], 24)
        self.assertEqual(result["node_check"], "skipped")

    def test_production_runbook_and_env_template_cover_required_operations(self) -> None:
        env_template = Path(".env.example").read_text(encoding="utf-8")
        for key in [
            "AI_QUANT_DB",
            "AI_QUANT_HOST",
            "AI_QUANT_POSTGRES_DSN",
            "AI_QUANT_OBJECT_STORE_BACKEND",
            "AI_QUANT_S3_ENDPOINT",
            "AI_QUANT_SEARCH_BACKEND",
            "AI_QUANT_OPENSEARCH_URL",
            "AI_QUANT_SEC_USER_AGENT",
            "AI_QUANT_STAGING_URL",
            "AI_QUANT_STAGING_ARTIFACT_PREFIX",
            "AI_QUANT_OTEL_EXPORTER_OTLP_ENDPOINT",
            "AI_QUANT_NEO4J_SYNC_TARGET",
            "AI_QUANT_QDRANT_SYNC_TARGET",
            "AI_QUANT_SECRET_MANAGER_PROVIDER",
        ]:
            self.assertIn(key, env_template)
        runbook = Path("docs/production-runbook.md").read_text(encoding="utf-8")
        for fragment in [
            "上线前检查",
            "备份与恢复",
            "回滚步骤",
            "月度运维检查",
            "scripts/migrate_sqlite_to_postgres.py",
            "scripts/smoke_test.py",
            "scripts/staging_acceptance.py",
            "scripts/local_staging_stack.sh",
            "scripts/capacity_baseline.py",
            "scripts/ui_static_check.py",
        ]:
            self.assertIn(fragment, runbook)
        dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
        self.assertIn("COPY scripts ./scripts", dockerfile)
        self.assertIn("psycopg[binary]", dockerfile)
        compose = Path("docker-compose.yml").read_text(encoding="utf-8")
        for fragment in ["postgres:", "minio:", "opensearch:", "neo4j:", "qdrant:", "otel-collector:"]:
            self.assertIn(fragment, compose)
        self.assertIn("AI_QUANT_HOST: ${AI_QUANT_HOST:-0.0.0.0}", compose)

    def test_capacity_baseline_script_reports_core_latency_metrics(self) -> None:
        result = run_capacity_baseline(records=3)
        self.assertEqual(result["records"], 3)
        self.assertEqual(result["documents"], 3)
        self.assertGreaterEqual(result["evidence"], 3)
        self.assertIn("ingest_ms", result["avg_ms"])
        self.assertIn("search_ms", result["max_ms"])

    def test_full_run_acceptance_covers_simulated_trading_and_core_runtime(self) -> None:
        result = run_full_acceptance(capacity_records=2)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["trading_mode"], "simulated")
        self.assertEqual(result["failed_count"], 0)
        checks = {item["check"]: item for item in result["checks"]}
        for name in [
            "health",
            "demo_full_flow",
            "simulated_trade_execution",
            "portfolio_ledger_positions",
            "keyword_search",
            "semantic_search",
            "graph_traceability",
            "alerts",
            "capacity_baseline",
            "readiness_checklist_records",
            "metrics_observability",
        ]:
            self.assertIn(name, checks)
            self.assertTrue(checks[name]["passed"], name)
        self.assertFalse(checks["simulated_trade_execution"]["evidence"]["live_execution_allowed"])
        self.assertEqual(checks["metrics_observability"]["evidence"]["simulated_executions"], 1)

    def test_staging_acceptance_runs_against_http_server_and_records_readiness(self) -> None:
        import app.server as server_module

        server_module.ROUTER = ApiRouter(SystemService())
        server = ThreadingHTTPServer(("127.0.0.1", 0), server_module.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            local_url = f"http://127.0.0.1:{server.server_port}"
            result = run_staging_acceptance(
                base_url=local_url,
                artifact_prefix="artifact://staging-test",
                record_readiness=True,
                notify_missing=True,
                timeout=5,
                env={
                    "AI_QUANT_POSTGRES_DSN": f"postgresql://app:secret@127.0.0.1:{server.server_port}/ai_quant",
                    "AI_QUANT_S3_BUCKET": "ai-quant-staging",
                    "AI_QUANT_S3_ENDPOINT": local_url,
                    "AI_QUANT_OPENSEARCH_URL": local_url,
                    "AI_QUANT_OTEL_EXPORTER_OTLP_ENDPOINT": f"{local_url}/v1/logs",
                    "AI_QUANT_NEO4J_SYNC_TARGET": local_url,
                    "AI_QUANT_NEO4J_HTTP_URL": local_url,
                    "AI_QUANT_QDRANT_SYNC_TARGET": local_url,
                    "AI_QUANT_OPENLINEAGE_TARGET": local_url,
                    "AI_QUANT_MLFLOW_TRACKING_URI": local_url,
                    "AI_QUANT_SECRET_MANAGER_PROVIDER": "aws_secrets_manager",
                },
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["trading_mode"], "simulated_only")
        checks = {item["check"]: item for item in result["checks"]}
        self.assertTrue(checks["external_configuration"]["passed"])
        self.assertTrue(checks["external_reachability"]["passed"])
        self.assertTrue(checks["neo4j_sync_outbox"]["passed"])
        self.assertTrue(checks["qdrant_sync_outbox"]["passed"])
        self.assertTrue(checks["otel_submit_outbox"]["passed"])
        self.assertTrue(checks["lineage_model_registry_outbox"]["passed"])
        self.assertGreaterEqual(len(result["readiness_records"]), 2)
        self.assertIn("real_data_smoke_test", {item["check_id"] for item in result["readiness_records"] if "check_id" in item})
        self.assertIsNotNone(result["notifications"])
        self.assertEqual(result["production_boundary"], "does_not_enable_live_broker_or_automatic_order_execution")

    def test_feast_kafka_decision_memo_documents_triggers_and_costs(self) -> None:
        memo = Path("docs/feast-kafka-decision-memo.md").read_text(encoding="utf-8")
        for fragment in [
            "Do not introduce Feast or Kafka",
            "Trigger Thresholds",
            "Migration Draft",
            "PoC Cost",
            "outbox",
            "point-in-time",
            "10k+ events/day",
        ]:
            self.assertIn(fragment, memo)

    def test_us_compliance_open_questions_cover_live_execution_blockers(self) -> None:
        memo = Path("docs/us-compliance-open-questions.md").read_text(encoding="utf-8")
        for fragment in [
            "Reg FD",
            "Nasdaq / NYSE Non-Display",
            "Investment Adviser",
            "Broker Interfaces",
            "Derivatives And Cross-Border",
            "research, evidence, paper portfolio, and human committee workflow only",
        ]:
            self.assertIn(fragment, memo)


if __name__ == "__main__":
    unittest.main()
