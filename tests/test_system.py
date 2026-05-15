from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import hashlib
import json
import unittest
import zlib

from app.api import ApiRouter
from app.connectors import AShareConnector, ConnectorDocument
from app.document_parser import PaddleOCRParser
from app.errors import ConflictError, PermissionDenied
from app.llm_gateway import LLMGateway
from app.object_store import S3CompatibleObjectStore
from app.search import OpenSearchIndex, SearchRecord
from app.services import SystemService
from app.store import PostgreSQLStore, SQLiteStore
from scripts.capacity_baseline import run_capacity_baseline
from scripts.migrate_sqlite_to_postgres import migrate_sqlite_to_postgres
from scripts.postgres_schema_migrate import BASELINE_VERSION, apply_postgres_schema, mark_last_migration_rolled_back
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
        self.assertEqual(dashboard["counts"]["sources"], 1)
        self.assertEqual(dashboard["counts"]["documents"], 1)
        self.assertEqual(dashboard["counts"]["reviews"], 1)
        self.assertEqual(dashboard["counts"]["open_exceptions"], 1)
        self.assertEqual(dashboard["counts"]["execution_intents"], 1)
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

        resolved_flag = self.router.dispatch(
            "POST",
            f"/api/operating-reports/opr_perf/red-flags/{red_flag_id}/resolve",
            {"resolution": "data source mapped to authorized EOD feed", "resolved_by": "risk_owner"},
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
        filtered = self.router.dispatch(
            "GET",
            "/api/strategy-replays",
            {"decision_id": "dec_demo", "version": "v2"},
            role="CIO",
        )
        self.assertTrue(filtered.success, filtered.error)
        self.assertEqual(filtered.data["count"], 1)
        self.assertEqual(filtered.data["replays"][0]["replay_id"], "replay_perf_v2")

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
        self.assertIn("stress_report", diagnostics)
        self.assertEqual(diagnostics["walk_forward"]["period_count"], 3)
        self.assertEqual(len(self.service.store.execution_intents), 0)

        fetched = self.router.dispatch("GET", "/api/portfolio/proposals/pfp_bl", {}, role="CIO")
        self.assertTrue(fetched.success, fetched.error)
        self.assertEqual(fetched.data["proposal_id"], "pfp_bl")
        listed = self.router.dispatch("GET", "/api/portfolio/proposals", {"status": "candidate"}, role="CIO")
        self.assertEqual(listed.data["count"], 1)
        graph = self.router.dispatch("GET", "/api/graph/query", {"security_id": "sec_us"}, role="CIO")
        self.assertTrue(graph.success, graph.error)
        self.assertEqual(graph.data["portfolio_proposals"][0]["proposal_id"], "pfp_bl")

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

    def test_transcript_and_research_sources_preserve_citation_boundaries(self) -> None:
        sources = {source.source_id: source for source in self.service.seed_default_sources(actor="risk")}
        self.assertIn("company_public_webcast", sources)
        self.assertIn("authorized_transcript_vendor", sources)
        self.assertIn("authorized_research_vendor", sources)
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
                    "document_id": "doc_vendor_transcript_bad",
                    "issuer_id": "issuer_001",
                    "security_id": "sec_001",
                    "source_id": "authorized_transcript_vendor",
                    "source_type": "vendor",
                    "document_type": "transcript",
                    "source_uri": "vendor://transcripts/demo",
                    "body": "Vendor transcript text.",
                    "rights_tag": {
                        "license_class": "authorized_transcript_internal",
                        "training_allowed": True,
                        "redistribution_allowed": False,
                        "display_use": "restricted",
                        "non_display_use": "restricted",
                        "derived_data_use": "restricted",
                    },
                },
                actor="data",
            )
        policy = Path("docs/transcript-research-citation-policy.md").read_text(encoding="utf-8")
        for fragment in ["company_public_webcast", "authorized_transcript_vendor", "No transcript or research text enters training", "Reg FD"]:
            self.assertIn(fragment, policy)

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
        self.assertGreaterEqual(len(seeded.data["rules"]), 4)

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

        for item in self.service.store.manual_reviews.values():
            item.status = "closed"
        resolved = self.router.dispatch("POST", "/api/alerts/evaluate", {}, role="risk_compliance")
        self.assertTrue(resolved.success)
        self.assertIn("alert_open_manual_reviews", {item["rule_id"] for item in resolved.data["resolved"]})

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

    def test_authorized_market_data_respects_rights_and_dashboard(self) -> None:
        seeded = self.router.dispatch("POST", "/api/ingestion/sources/seed", {}, role="data_engineer")
        self.assertTrue(seeded.success)
        self.assertIn("authorized_eod_market_data", {item["source_id"] for item in seeded.data["sources"]})

        point = self.router.dispatch(
            "POST",
            "/api/market-data/points",
            {
                "data_id": "md_001",
                "security_id": "sec_001",
                "source_id": "authorized_eod_market_data",
                "as_of_date": "2026-05-14",
                "data_type": "eod",
                "close": 12.34,
                "adjusted_close": 12.34,
                "volume": 1000000,
            },
            role="data_engineer",
        )
        self.assertTrue(point.success)
        self.assertEqual(point.data["rights_tag"]["license_class"], "authorized_eod_research")
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
                        "source_id": "authorized_eod_market_data",
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

        action = self.router.dispatch(
            "POST",
            "/api/corporate-actions",
            {
                "action_id": "ca_split",
                "security_id": "sec_001",
                "source_id": "authorized_eod_market_data",
                "action_type": "split",
                "ex_date": "2026-05-16",
                "ratio": 2.0,
                "description": "2-for-1 split for adjusted close chain",
            },
            role="data_engineer",
        )
        self.assertTrue(action.success, action.error)
        corporate_actions = self.router.dispatch("GET", "/api/corporate-actions", {"security_id": "sec_001"}, role="CEO")
        self.assertEqual(corporate_actions.data["corporate_actions"][0]["action_id"], "ca_split")
        refreshed_dashboard = self.router.dispatch("GET", "/api/dashboard/ceo", {}, role="CEO")
        self.assertEqual(refreshed_dashboard.data["counts"]["market_data"], 2)
        self.assertEqual(refreshed_dashboard.data["counts"]["corporate_actions"], 1)

        blocked_realtime = self.router.dispatch(
            "POST",
            "/api/market-data/points",
            {
                "data_id": "md_realtime",
                "security_id": "sec_001",
                "source_id": "authorized_eod_market_data",
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

    def test_13f_holdings_generate_crowding_snapshot(self) -> None:
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
        self.assertEqual(len(listed.data["holdings"]), 2)

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

        dashboard = self.router.dispatch("GET", "/api/dashboard/ceo", {}, role="CEO")
        self.assertEqual(dashboard.data["counts"]["institutional_holdings"], 2)
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
        self.service.ingest_document(
            {
                "document_id": "doc_8k_event",
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "source_id": "src_sec",
                "source_type": "regulatory",
                "document_type": "8-K",
                "source_uri": "https://example.invalid/doc-8k-event",
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
            },
            role="platform",
        )
        self.assertTrue(report.success, report.error)
        self.assertEqual(report.data["mappings"], 2)
        self.assertEqual(report.data["market_counts"]["A"], 1)
        self.assertEqual(report.data["accuracy"], 0.5)
        self.assertEqual(report.data["mismatches"][0]["mapping_id"], "map_u")

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
                "source_id": "authorized_eod_market_data",
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
        self.assertIn("中文摘要", answer.data["chinese_summary"])
        self.assertIn(evidence.evidence_id, answer.data["evidence_ids"])

        loaded = self.router.dispatch("GET", "/api/research/answers/ans_001", {}, role="analyst")
        self.assertTrue(loaded.success)
        self.assertEqual(loaded.data["source_document_ids"], ["doc_answer"])
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
        self.assertGreaterEqual(len(self.service.thesis_payload("thesis_demo")["evidence"]), 1)

        second = self.router.dispatch("POST", "/api/demo/full-flow", {}, actor="platform_owner", role="platform")
        self.assertTrue(second.success)
        self.assertEqual(second.data["dashboard"]["counts"]["execution_intents"], 1)

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
                    "source_id": "authorized_eod_market_data",
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
                "source_id": "authorized_eod_market_data",
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
        self.assertEqual(result["required_ids"], 21)
        self.assertEqual(result["node_check"], "skipped")

    def test_production_runbook_and_env_template_cover_required_operations(self) -> None:
        env_template = Path(".env.example").read_text(encoding="utf-8")
        for key in [
            "AI_QUANT_DB",
            "AI_QUANT_POSTGRES_DSN",
            "AI_QUANT_OBJECT_STORE_BACKEND",
            "AI_QUANT_S3_ENDPOINT",
            "AI_QUANT_SEARCH_BACKEND",
            "AI_QUANT_OPENSEARCH_URL",
            "AI_QUANT_SEC_USER_AGENT",
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
            "scripts/capacity_baseline.py",
            "scripts/ui_static_check.py",
        ]:
            self.assertIn(fragment, runbook)

    def test_capacity_baseline_script_reports_core_latency_metrics(self) -> None:
        result = run_capacity_baseline(records=3)
        self.assertEqual(result["records"], 3)
        self.assertEqual(result["documents"], 3)
        self.assertGreaterEqual(result["evidence"], 3)
        self.assertIn("ingest_ms", result["avg_ms"])
        self.assertIn("search_ms", result["max_ms"])

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
