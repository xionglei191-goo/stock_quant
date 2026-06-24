from __future__ import annotations

import argparse
import importlib
from pathlib import Path
from http.server import ThreadingHTTPServer
from tempfile import TemporaryDirectory
import hashlib
import json
import os
import re
import struct
import subprocess
import sys
import threading
import time
import unittest
import zipfile
import zlib

from app.api import ApiRouter
import app.services as services_module
from app.connectors import AShareConnector, ConnectorDocument
from app.document_parser import PaddleOCRParser
from app.errors import ConflictError, PermissionDenied
from app.llm_gateway import LLMGateway
from app.models import AlertNotification, CompanyDatabaseBuildRun, DecisionPack, DisclosureEvent, Document, Evidence, ResearchReportAsset, RightsTag, SystemAlert
from app.object_store import LocalObjectStore, S3CompatibleObjectStore
from app.readiness_artifacts import is_external_artifact_uri, is_production_artifact_uri
from app.search import OpenSearchIndex, SearchRecord
from app.services import SystemService
from app.store import PostgreSQLStore, SQLiteStore
from app.tdx_market_data import TDXVipdocAdapter
from scripts.capacity_baseline import run_capacity_baseline
from scripts.download_tdx_vipdoc import download_tdx_vipdoc_archive
from scripts.full_run_acceptance import run_full_acceptance
from scripts.fetch_benchmark_samples import fetch_benchmark_samples
from scripts.local_data_unblock_audit import audit_local_data_unblock
import scripts.backfill_market_data as backfill_market_data_script
import scripts.daily_data_update_pipeline as daily_data_update_pipeline_script
import scripts.audit_daily_update_schedule as audit_daily_update_schedule_script
import scripts.daily_market_insight as daily_market_insight_script
import scripts.import_ashare_eod_baostock as import_ashare_eod_baostock_script
import scripts.import_us_eod_yahoo_chart as import_us_eod_yahoo_chart_script
import scripts.latest_analysis_run as latest_analysis_run_script
import scripts.latency_audit as latency_audit_script
import scripts.scope_ashare_current_baostock_universe as scope_ashare_current_baostock_universe_script
import scripts.scope_us_current_yahoo_universe as scope_us_current_yahoo_universe_script
from scripts.import_tdx_market_data import run_tdx_incremental_import
from scripts.import_tdx_vipdoc_postgres import read_day_rows
from scripts.tdx_batch_import import infer_exchange, normalize_symbol
from scripts.local_ai_capability_acceptance import build_local_ai_capability_acceptance
from scripts.local_benchmark_quality_package import build_local_benchmark_quality_package
from scripts.local_chokepoint_quality_package import build_local_chokepoint_quality_package
from scripts.local_production_audit import build_local_production_audit
import scripts.market_data_storage_audit as market_data_storage_audit_script
from scripts.migrate_sqlite_to_postgres import migrate_sqlite_to_postgres
from scripts.postgres_schema_migrate import BASELINE_VERSION, apply_postgres_schema, mark_last_migration_rolled_back
from scripts.production_closure import validate_production_closure_manifest
from scripts.production_artifact_inventory_check import build_artifact_inventory_from_bundle, build_artifact_inventory_template, collect_required_artifact_uris, validate_artifact_inventory
from scripts.production_closure_manifest_check import load_and_validate_production_closure_manifest
from scripts.production_evidence_plan_check import load_and_validate_evidence_collection_plan, validate_evidence_collection_plan
from scripts.production_evidence_plan_fill import fill_evidence_collection_plan
from scripts.production_evidence_plan_to_manifest import build_manifest_from_evidence_plan
from scripts.production_release_gate import run_production_release_gate
from scripts.production_task_status_finalize import finalize_production_task_statuses
from scripts.project_completion_audit import build_completion_audit
from scripts.production_task_closure_audit import TASKS_WITH_EXTERNAL_EVIDENCE, audit_production_tasks, build_evidence_collection_plan
from scripts.readiness_evidence_package_check import REQUIRED_CHECK_IDS, REQUIRED_EXTERNAL_VALIDATION_SCOPES, validate_readiness_evidence_package
from scripts.security_check import scan_repository
from scripts.staging_acceptance import run_staging_acceptance
from scripts.staging_lineage_registry_acceptance import run_staging_lineage_registry_acceptance
from scripts.staging_security_acceptance import run_staging_security_acceptance
from scripts.ui_cross_browser_matrix_check import validate_cross_browser_matrix
from scripts.ui_static_check import REQUIRED_IDS, REQUIRED_JS_FUNCTIONS, REQUIRED_STATUS_LABELS, validate_ui_html


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
        if normalized.startswith("select count(*) from ai_quant.records where collection"):
            collection = params[0] if params else "market_data"
            self._rows = [(sum(1 for record_collection, _item_id in self.database.records if record_collection == collection),)]
        elif normalized.startswith("select to_regclass('ai_quant.market_data_bars')"):
            self._rows = [(True,)]
        elif normalized.startswith("select to_regclass('ai_quant.schema_migrations')"):
            self._rows = [(self.database.baseline_schema_recorded,)]
        elif normalized.startswith("select 1 from ai_quant.schema_migrations"):
            self._rows = [(1,)] if self.database.baseline_schema_recorded else []
        elif normalized.startswith("select count(*) from ai_quant.market_data_bars"):
            bars = self._filtered_market_data_bars(normalized, params or [])
            self._rows = [(len(bars),)]
        elif normalized.startswith("select data_id, security_id, source_id, market, as_of_date::text") or normalized.startswith("select b.data_id, b.security_id, b.source_id, b.market, b.as_of_date::text"):
            bars = self._filtered_market_data_bars(normalized, params or [])
            descending = "order by as_of_date desc" in normalized or "order by b.as_of_date desc" in normalized
            bars = sorted(bars, key=lambda item: (item["as_of_date"], item["data_id"]), reverse=descending)
            limit = int((params or [50])[-1] or 50)
            self._rows = [
                (
                    item["data_id"],
                    item["security_id"],
                    item["source_id"],
                    item["market"],
                    item["as_of_date"],
                    item["data_type"],
                    item["currency"],
                    item["open"],
                    item["high"],
                    item["low"],
                    item["close"],
                    item["adjusted_close"],
                    item["volume"],
                    item["amount"],
                    item["rights_tag"],
                    item["created_at"],
                )
                for item in bars[:limit]
            ]
        elif normalized.startswith("select collection"):
            rows = []
            for (collection, item_id), record in self.database.records.items():
                if "where collection <> 'market_data'" in normalized and collection == "market_data":
                    continue
                rows.append((collection, item_id, record["payload"], record["position"]))
            self._rows = sorted(rows, key=lambda item: (item[0], item[3] is None, item[3] or 0, item[1]))
        elif normalized.startswith("select payload from ai_quant.audit_log"):
            audit_rows = sorted(self.database.audit.values(), key=lambda item: (item["timestamp"], item["event_id"]))
            self._rows = [(item["payload"],) for item in audit_rows]
        elif normalized.startswith("delete from ai_quant.records where collection = %s and item_id = %s"):
            self.database.records.pop((params[0], params[1]), None)
            self._rows = []
        elif normalized.startswith("delete from ai_quant.records where collection = %s"):
            collection = params[0]
            self.database.records = {key: value for key, value in self.database.records.items() if key[0] != collection}
            self._rows = []
        elif normalized.startswith("delete from ai_quant.records"):
            self.database.records.clear()
            self._rows = []
        elif normalized.startswith("delete from ai_quant.audit_log where event_id = %s"):
            self.database.audit.pop(params[0], None)
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
        elif normalized.startswith("insert into ai_quant.market_data_bars"):
            self._upsert_market_data_bar(params)
            self._rows = []
        elif normalized.startswith("insert into ai_quant.audit_log"):
            self.database.audit[params[0]] = {
                "event_id": params[0],
                "payload": json.loads(params[11]),
                "timestamp": params[12],
            }
            self._rows = []
        elif normalized.startswith("insert into ai_quant.schema_migrations"):
            self.database.baseline_schema_recorded = True
            self._rows = []
        else:
            if "create schema if not exists ai_quant" in normalized:
                self.database.schema_runs += 1
            self._rows = []

    def executemany(self, sql, params_list):
        for params in params_list:
            self.execute(sql, params)

    def _filtered_market_data_bars(self, normalized_sql, params):
        filter_params = list(params)
        if " limit %s" in normalized_sql and filter_params:
            filter_params = filter_params[:-1]
        names = []
        for name in ("security_id", "market", "source_id", "data_type"):
            if f"{name} = %s" in normalized_sql or f"b.{name} = %s" in normalized_sql:
                names.append(name)
        if "as_of_date >= %s::date" in normalized_sql or "b.as_of_date >= %s::date" in normalized_sql:
            names.append("start_date")
        if "as_of_date <= %s::date" in normalized_sql or "b.as_of_date <= %s::date" in normalized_sql:
            names.append("date_lte")
        filters = dict(zip(names, filter_params))
        rows = list(self.database.market_data_bars.values())
        for name in ("security_id", "market", "source_id", "data_type"):
            if name in filters:
                rows = [item for item in rows if item[name] == filters[name]]
        if "start_date" in filters:
            rows = [item for item in rows if item["as_of_date"] >= filters["start_date"]]
        if "date_lte" in filters:
            rows = [item for item in rows if item["as_of_date"] <= filters["date_lte"]]
        return rows

    def _upsert_market_data_bar(self, params):
        (
            security_id,
            source_id,
            data_type,
            as_of_date,
            market,
            currency,
            row_open,
            high,
            low,
            close,
            adjusted_close,
            volume,
            amount,
            data_id,
            rights_tag,
            payload,
            created_at,
        ) = params
        self.database.market_data_bars[(security_id, source_id, data_type, as_of_date)] = {
            "security_id": security_id,
            "source_id": source_id,
            "data_type": data_type,
            "as_of_date": as_of_date,
            "market": market,
            "currency": currency,
            "open": row_open,
            "high": high,
            "low": low,
            "close": close,
            "adjusted_close": adjusted_close,
            "volume": volume,
            "amount": amount,
            "data_id": data_id,
            "rights_tag": json.loads(rights_tag) if isinstance(rights_tag, str) else rights_tag,
            "payload": json.loads(payload) if isinstance(payload, str) else payload,
            "created_at": created_at,
        }

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None


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
        self.market_data_bars = {}
        self.audit = {}
        self.statements = []
        self.schema_runs = 0
        self.dsns = []
        self.baseline_schema_recorded = False

    def connect(self, dsn):
        self.dsns.append(dsn)
        return _FakePostgresConnection(self)


class _FakeSecSingleNameConnectors:
    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.body = (
            "Apple Inc. reported revenue growth while Services resilience, subscription activity, "
            "and installed-base engagement improved the company mix. Gross margin benefited from "
            "the services contribution and disciplined operating expenses.\n\n"
            "Risk factors include regulatory scrutiny, supply-chain concentration, component "
            "availability, foreign exchange volatility, and macro demand changes."
        )

    def fetch_sec_recent_filings(self, cik, *, user_agent, limit=10, document_types=None):
        if self.fail:
            raise RuntimeError("SEC outage")
        document_type = (document_types or ["10-K"])[0]
        return [
            ConnectorDocument(
                source_id="sec_edgar",
                source_type="regulatory",
                document_type=document_type,
                source_uri="https://www.sec.gov/Archives/edgar/data/320193/000032019324000123/a10-k.htm",
                language="en",
                title=f"Apple Inc. {document_type} filing",
                published_at="2026-05-14",
                metadata={
                    "cik": str(cik).lstrip("0") or "0",
                    "accession_no": "0000320193-24-000123",
                    "primary_doc": "a10-k.htm",
                },
            )
        ]

    def fetch_sec_document_body(self, source_uri, *, user_agent, max_bytes=2_000_000):
        if self.fail:
            raise RuntimeError("SEC body outage")
        return self.body[:max_bytes]


class SystemServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        preserved_ai_quant_env = {key: value for key, value in os.environ.items() if key.startswith("AI_QUANT_")}
        for key in list(os.environ):
            if key.startswith("AI_QUANT_"):
                os.environ.pop(key, None)

        def _restore_ai_quant_env() -> None:
            for key in list(os.environ):
                if key.startswith("AI_QUANT_"):
                    os.environ.pop(key, None)
            os.environ.update(preserved_ai_quant_env)

        self.addCleanup(_restore_ai_quant_env)
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

    def _use_temp_object_store(self) -> None:
        temp_dir = TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        self.service.object_store = LocalObjectStore(Path(temp_dir.name))

    def test_company_intelligence_symbol_view_handles_spcx_before_and_after_research(self) -> None:
        empty = self.router.dispatch("GET", "/api/company-intelligence/SPCX", {"limit": 10}, role="analyst")
        self.assertTrue(empty.success, empty.error)
        self.assertEqual(empty.data["symbol"], "SPCX")
        self.assertEqual(empty.data["status"], "not_found")
        self.assertIn("company_profile", empty.data["data_quality"]["missing_sections"])
        self.assertTrue(any(item["action"] == "run_single_name_research" for item in empty.data["next_actions"]))
        self.assertFalse(empty.data["simulation_feedback"]["live_execution_allowed"])

        run = self.router.dispatch(
            "POST",
            "/api/research/tasks/sec-single-name/run",
            {
                "ticker": "SPCX",
                "cik": "0000000000",
                "company_name": "SPCX Research Vehicle",
                "force_fallback": True,
                "fallback_close": 25.5,
                "fallback_volume": 1000,
                "trade_date": "2026-06-24",
                "quantity": 4,
            },
            role="analyst",
        )
        self.assertTrue(run.success, run.error)
        self.assertEqual(run.data["ticker"], "SPCX")
        self.assertFalse(run.data["live_execution_allowed"])
        issuer_id = run.data["ids"]["issuer_id"]
        security_id = run.data["ids"]["security_id"]
        self.service.store.research_reports["rr_spcx_local"] = ResearchReportAsset(
            report_id="rr_spcx_local",
            source_id="local_research_reports",
            broker="Local Broker",
            file_path="/tmp/SPCX-report.pdf",
            file_name="SPCX-report.pdf",
            title="SPCX local research view",
            issuer_id=issuer_id,
            security_id=security_id,
            viewpoint={"rating": "watch", "target_price": 30.0, "boundary": "opinion_only"},
            status="text_indexed",
        )

        view = self.router.dispatch("GET", "/api/company-intelligence/SPCX", {"limit": 20}, role="analyst")

        self.assertTrue(view.success, view.error)
        self.assertEqual(view.data["status"], "available")
        self.assertEqual(view.data["resolution"]["issuer_ids"], [issuer_id])
        self.assertIn(security_id, view.data["resolution"]["security_ids"])
        self.assertEqual(view.data["company_profile"]["primary_security"]["ticker"], "SPCX")
        self.assertEqual(view.data["facts_and_events"]["latest_market_snapshot"]["close"], 25.5)
        self.assertGreaterEqual(view.data["section_counts"]["research_answers"], 1)
        self.assertGreaterEqual(view.data["section_counts"]["theses"], 1)
        self.assertGreaterEqual(view.data["section_counts"]["signals"], 1)
        self.assertEqual(view.data["section_counts"]["research_reports"], 1)
        self.assertGreaterEqual(view.data["section_counts"]["simulated_executions"], 1)
        self.assertFalse(view.data["simulation_feedback"]["live_execution_allowed"])
        self.assertTrue(view.data["data_quality"]["profile_available"])
        self.assertTrue(view.data["data_quality"]["research_results_available"])
        self.assertTrue(view.data["data_quality"]["simulation_feedback_available"])
        self.assertTrue(any(item["report_id"] == "rr_spcx_local" for item in view.data["research_results"]["research_reports"]))
        self.assertTrue(any(item["resource_type"] == "research_report" for item in view.data["research_results"]["search"]["results"]))
        self.assertEqual(view.data["usage_boundary"], "company_intelligence_research_only_simulation_feedback_only_no_broker_execution")

    def test_company_intelligence_first_class_models_are_exposed_and_aggregated(self) -> None:
        profile = self.router.dispatch("POST", "/api/company-profiles", {"issuer_id": "issuer_001", "business_summary": "Demo component supplier"}, role="analyst")
        self.assertTrue(profile.success, profile.error)
        self.assertEqual(profile.data["issuer_id"], "issuer_001")
        self.assertIn("profile_coverage", profile.data["data_quality"])

        event = self.router.dispatch(
            "POST",
            "/api/company-events",
            {
                "event_id": "ce_demo_001",
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "event_type": "order",
                "title": "Large customer order",
                "summary": "Demo Corp received a new customer order.",
                "source_ids": ["source_public"],
                "evidence_ids": ["ev_demo_order"],
                "fact_status": "verified",
                "impact_tags": ["demand"],
            },
            role="analyst",
        )
        self.assertTrue(event.success, event.error)

        relationship = self.router.dispatch(
            "POST",
            "/api/company-relationships",
            {
                "relationship_id": "rel_demo_customer",
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "subject_type": "company",
                "subject_id": "issuer_001",
                "object_type": "customer",
                "object_id": "customer_alpha",
                "relationship_type": "customer",
                "source_ids": ["source_public"],
                "evidence_ids": ["ev_demo_order"],
                "confidence": 0.8,
            },
            role="analyst",
        )
        self.assertTrue(relationship.success, relationship.error)

        analyst = self.router.dispatch(
            "POST",
            "/api/analyst-profiles",
            {
                "analyst_id": "analyst_demo",
                "name": "Demo Analyst",
                "institution_id": "broker_demo",
                "covered_issuer_ids": ["issuer_001"],
            },
            role="analyst",
        )
        self.assertTrue(analyst.success, analyst.error)

        report = self.router.dispatch(
            "POST",
            "/api/research-reports/structured",
            {
                "research_report_id": "srr_demo_001",
                "title": "Demo Corp customer order update",
                "institution_id": "broker_demo",
                "institution_name": "Demo Securities",
                "analyst_ids": ["analyst_demo"],
                "analyst_names": ["Demo Analyst"],
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "report_type": "company_update",
                "rating": "outperform",
                "target_price": 12.5,
                "current_price": 10.0,
                "rights_boundary": "opinion_only_not_fact_source",
            },
            role="analyst",
        )
        self.assertTrue(report.success, report.error)
        self.assertEqual(report.data["rights_boundary"], "opinion_only_not_fact_source")

        viewpoint = self.router.dispatch(
            "POST",
            "/api/research-report-viewpoints",
            {
                "viewpoint_id": "vp_demo_001",
                "research_report_id": "srr_demo_001",
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "viewpoint_type": "target_price",
                "stance": "bullish",
                "statement": "Order visibility supports revenue growth.",
                "rating": "outperform",
                "target_price": 12.5,
                "current_price": 10.0,
                "core_assumptions": ["customer order converts to revenue"],
                "catalysts": ["order delivery"],
                "risks": ["delivery delay"],
                "evidence_ids": ["ev_demo_order"],
            },
            role="analyst",
        )
        self.assertTrue(viewpoint.success, viewpoint.error)

        forecast = self.router.dispatch(
            "POST",
            "/api/research-report-forecasts",
            {
                "forecast_id": "fc_demo_001",
                "research_report_id": "srr_demo_001",
                "viewpoint_id": "vp_demo_001",
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "forecast_type": "target_price",
                "period": "2026H2",
                "forecast_value": 12.5,
                "actual_value": 13.0,
                "realization_status": "realized",
            },
            role="analyst",
        )
        self.assertTrue(forecast.success, forecast.error)

        score = self.router.dispatch("POST", "/api/analyst-reliability-scores", {"analyst_id": "analyst_demo", "issuer_id": "issuer_001", "period": "2026H2"}, role="analyst")
        self.assertTrue(score.success, score.error)
        self.assertEqual(score.data["sample_count"], 1)
        self.assertEqual(score.data["target_price_hit_rate"], 1.0)

        observation = self.router.dispatch(
            "POST",
            "/api/observation-items",
            {
                "observation_id": "obs_demo_001",
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "title": "Track order conversion",
                "question": "Does the order convert into reported revenue?",
                "related_event_ids": ["ce_demo_001"],
                "related_relationship_ids": ["rel_demo_customer"],
                "related_viewpoint_ids": ["vp_demo_001"],
                "priority": "high",
                "status": "open",
            },
            role="analyst",
        )
        self.assertTrue(observation.success, observation.error)

        conclusion = self.router.dispatch(
            "POST",
            "/api/analysis-conclusions",
            {
                "analysis_conclusion_id": "ac_demo_001",
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "title": "Order visibility improves near-term setup",
                "conclusion": "Demo Corp deserves focused observation because order visibility improved.",
                "facts": ["new customer order"],
                "inferences": ["revenue visibility improved"],
                "supporting_evidence_ids": ["ev_demo_order"],
                "related_event_ids": ["ce_demo_001"],
                "related_relationship_ids": ["rel_demo_customer"],
                "related_viewpoint_ids": ["vp_demo_001"],
                "related_observation_ids": ["obs_demo_001"],
                "confidence": 0.7,
                "status": "active",
            },
            role="analyst",
        )
        self.assertTrue(conclusion.success, conclusion.error)

        feedback = self.router.dispatch(
            "POST",
            "/api/simulation-feedback",
            {
                "simulation_feedback_id": "sf_demo_001",
                "analysis_conclusion_id": "ac_demo_001",
                "observation_id": "obs_demo_001",
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "feedback_type": "paper_position",
                "simulated_action": "watch_buy",
                "entry_price": 10.0,
                "exit_price": 11.0,
                "performance": {"absolute_return": 0.1},
            },
            role="analyst",
        )
        self.assertTrue(feedback.success, feedback.error)
        self.assertTrue(feedback.data["paper_only"])
        self.assertFalse(feedback.data["live_execution_allowed"])

        rejected_live = self.router.dispatch(
            "POST",
            "/api/simulation-feedback",
            {
                "analysis_conclusion_id": "ac_demo_001",
                "issuer_id": "issuer_001",
                "live_execution_allowed": True,
            },
            role="analyst",
        )
        self.assertFalse(rejected_live.success)
        self.assertEqual(rejected_live.error["type"], "validation_error")

        aggregated = self.router.dispatch("GET", "/api/company-intelligence/DEMO", {"limit": 20}, role="analyst")
        self.assertTrue(aggregated.success, aggregated.error)
        self.assertEqual(aggregated.data["status"], "available")
        self.assertEqual(aggregated.data["section_counts"]["company_profiles"], 1)
        self.assertEqual(aggregated.data["section_counts"]["company_events"], 1)
        self.assertEqual(aggregated.data["section_counts"]["company_relationships"], 1)
        self.assertEqual(aggregated.data["section_counts"]["structured_research_reports"], 1)
        self.assertEqual(aggregated.data["section_counts"]["report_viewpoints"], 1)
        self.assertEqual(aggregated.data["section_counts"]["observation_items"], 1)
        self.assertEqual(aggregated.data["section_counts"]["analysis_conclusions"], 1)
        self.assertEqual(aggregated.data["section_counts"]["simulation_feedback_records"], 1)
        self.assertEqual(aggregated.data["facts_and_events"]["company_events"][0]["event_id"], "ce_demo_001")
        self.assertEqual(aggregated.data["relationships"]["company_relationships"][0]["relationship_id"], "rel_demo_customer")
        self.assertEqual(aggregated.data["research_results"]["report_viewpoints"][0]["viewpoint_id"], "vp_demo_001")
        self.assertEqual(aggregated.data["analysis_workflow"]["analysis_conclusions"][0]["analysis_conclusion_id"], "ac_demo_001")
        self.assertEqual(aggregated.data["simulation_feedback"]["feedback_records"][0]["simulation_feedback_id"], "sf_demo_001")
        self.assertFalse(aggregated.data["simulation_feedback"]["live_execution_allowed"])

        graph = self.router.dispatch("GET", "/api/graph/query", {"issuer_id": "issuer_001"}, role="analyst")
        self.assertTrue(graph.success, graph.error)
        self.assertTrue(any(item["event_id"] == "ce_demo_001" for item in graph.data["company_events"]))
        self.assertTrue(any(item["relationship_id"] == "rel_demo_customer" for item in graph.data["company_relationships"]))
        self.assertTrue(any(item["viewpoint_id"] == "vp_demo_001" for item in graph.data["report_viewpoints"]))
        self.assertTrue(any(item["simulation_feedback_id"] == "sf_demo_001" for item in graph.data["simulation_feedback"]))
        edge_types = {item["type"] for item in graph.data["edges"]}
        self.assertIn("HAS_COMPANY_EVENT", edge_types)
        self.assertIn("REPORT_HAS_VIEWPOINT", edge_types)
        self.assertIn("FEEDBACK_FOR_CONCLUSION", edge_types)

    def test_company_database_builder_materializes_profiles_and_binds_reports(self) -> None:
        self.service.store.research_reports["rr_demo_unbound"] = ResearchReportAsset(
            report_id="rr_demo_unbound",
            source_id="local_research_reports",
            broker="Local Broker",
            file_path="/tmp/2026-DEMO-target-price-update.pdf",
            file_name="2026-DEMO-target-price-update.pdf",
            title="DEMO target price update 买入 目标价 18 元",
            year="2026",
            month="06",
            issuer_id="",
            security_id="",
            status="text_indexed",
        )

        dry_run = self.router.dispatch(
            "POST",
            "/api/company-database/build",
            {"symbols": ["DEMO"], "report_match_limit": 10, "structure_reports": True},
            actor="data",
            role="data_engineer",
        )
        self.assertTrue(dry_run.success, dry_run.error)
        self.assertEqual(dry_run.data["status"], "dry_run")
        self.assertEqual(dry_run.data["target_count"], 1)
        self.assertEqual(dry_run.data["profiles_planned"], 1)
        self.assertGreaterEqual(dry_run.data["research_reports_matched"], 1)
        self.assertNotIn("issuer_001", self.service.store.company_profiles)
        self.assertEqual(self.service.store.research_reports["rr_demo_unbound"].issuer_id, "")

        executed = self.router.dispatch(
            "POST",
            "/api/company-database/build",
            {
                "symbols": ["DEMO"],
                "report_match_limit": 10,
                "structure_reports": True,
                "structure_report_limit": 5,
                "execute": True,
            },
            actor="data",
            role="data_engineer",
        )
        self.assertTrue(executed.success, executed.error)
        self.assertEqual(executed.data["status"], "executed")
        self.assertEqual(executed.data["profiles_saved"], 1)
        self.assertEqual(executed.data["research_reports_bound"], 1)
        self.assertIn("issuer_001", self.service.store.company_profiles)
        report = self.service.store.research_reports["rr_demo_unbound"]
        self.assertEqual(report.issuer_id, "issuer_001")
        self.assertEqual(report.security_id, "sec_001")
        self.assertEqual(report.asset_binding["matched_by"], "company_database_builder")
        self.assertEqual(executed.data["structure_result"]["structured_count"], 1)
        self.assertIn("rr_demo_unbound", self.service.store.structured_research_reports)
        self.assertTrue(any(item.issuer_id == "issuer_001" for item in self.service.store.report_viewpoints.values()))

    def test_company_database_coverage_audit_reports_missing_sections(self) -> None:
        self.service.register_market_data_point(
            {
                "data_id": "md_demo_coverage_latest",
                "security_id": "sec_001",
                "source_id": "public_eod_market_data",
                "market": "A",
                "as_of_date": "2026-06-24",
                "close": 12.3,
                "volume": 123456,
            },
            actor="data",
        )
        built = self.router.dispatch(
            "POST",
            "/api/company-database/build",
            {"symbols": ["DEMO"], "execute": True},
            actor="data",
            role="data_engineer",
        )
        self.assertTrue(built.success, built.error)
        audit = self.router.dispatch(
            "POST",
            "/api/company-database/coverage/audit",
            {"symbols": ["DEMO"], "limit": 1},
            actor="data",
            role="analyst",
        )
        self.assertTrue(audit.success, audit.error)
        self.assertEqual(audit.data["issuer_count"], 1)
        row = audit.data["companies"][0]
        self.assertEqual(row["issuer_id"], "issuer_001")
        self.assertTrue(row["section_available"]["company_profile"])
        self.assertTrue(row["section_available"]["security"])
        self.assertTrue(row["section_available"]["market_data"])
        self.assertIn("financial_snapshot", row["missing_sections"])
        self.assertGreater(row["coverage_score"], 0.0)

    def test_company_profile_coverage_audit_reports_deep_missing_fields(self) -> None:
        audit = self.router.dispatch(
            "POST",
            "/api/company-profiles/coverage/audit",
            {"symbols": ["DEMO"], "limit": 1},
            actor="data",
            role="analyst",
        )
        self.assertTrue(audit.success, audit.error)
        self.assertEqual(audit.data["schema_id"], "company-profile-deep-field-coverage-v1")
        self.assertEqual(audit.data["issuer_count"], 1)
        row = audit.data["companies"][0]
        self.assertEqual(row["issuer_id"], "issuer_001")
        self.assertTrue(row["fields"]["legal_name"]["present"])
        self.assertTrue(row["fields"]["security_ids"]["present"])
        self.assertFalse(row["fields"]["business_summary"]["present"])
        self.assertIn("business_summary", row["missing_fields"])
        self.assertGreater(audit.data["field_missing_counts"]["business_summary"], 0)
        self.assertTrue(any(task["field"] == "business_summary" for task in row["research_tasks"]))

        alias = self.router.dispatch(
            "POST",
            "/api/company-database/profile-field-coverage/audit",
            {"symbols": ["DEMO"], "required_fields": ["legal_name", "business_summary"]},
            actor="data",
            role="analyst",
        )
        self.assertTrue(alias.success, alias.error)
        self.assertEqual(alias.data["required_fields"], ["legal_name", "business_summary"])

    def test_company_profile_coverage_audit_counts_official_sources_and_evidence(self) -> None:
        issuer = self.service.store.issuers["issuer_001"]
        issuer.region = "East China"
        issuer.sector = "Technology"
        issuer.industry = "Components"
        issuer.company_details = {"business_summary": "Demo supplies advanced components.", "products": ["Demo module"]}
        issuer.fundamentals = {"period": "2026Q1", "revenue": 1200.0, "net_income": 180.0, "gross_margin": 0.42, "cash": 300.0, "debt": 80.0}
        issuer.valuation_metrics = {"pe": 22.0}
        issuer.data_sources = ["src_sec"]
        security = self.service.store.securities["sec_001"]
        security.security_type = "common_stock"
        security.listing_date = "2020-01-02"
        self.service.register_market_data_point(
            {
                "data_id": "md_demo_profile_latest",
                "security_id": "sec_001",
                "source_id": "public_eod_market_data",
                "market": "A",
                "as_of_date": "2026-06-24",
                "close": 12.3,
                "volume": 123456,
                "amount": 1000000,
            },
            actor="data",
        )
        document = Document(
            document_id="doc_demo_annual",
            issuer_id="issuer_001",
            security_id="sec_001",
            document_type="annual_report",
            source_id="src_sec",
            source_type="regulatory",
            source_uri="https://example.test/demo-annual-report",
            rights_tag=RightsTag("public"),
            body="Demo supplies advanced components. Revenue and profit were disclosed.",
            title="Demo annual report",
        )
        self.service.store.documents[document.document_id] = document
        self.service.store.evidence["evi_demo_business"] = Evidence(
            evidence_id="evi_demo_business",
            document_id=document.document_id,
            section="business_overview",
            page_no=1,
            bbox="p1",
            span_text="Demo supplies advanced components.",
            canonical_text="Demo supplies advanced components.",
            confidence=0.95,
            issuer_id="issuer_001",
            security_id="sec_001",
        )

        audit = self.router.dispatch(
            "POST",
            "/api/company-profiles/coverage/audit",
            {"symbols": ["DEMO"], "include_optional": True, "limit": 1},
            actor="data",
            role="analyst",
        )
        self.assertTrue(audit.success, audit.error)
        fields = audit.data["companies"][0]["fields"]
        self.assertTrue(fields["business_summary"]["present"])
        self.assertTrue(fields["products"]["present"])
        self.assertTrue(fields["revenue"]["present"])
        self.assertTrue(fields["net_income"]["present"])
        self.assertTrue(fields["authorized_documents"]["present"])
        self.assertTrue(fields["field_evidence_ids"]["present"])
        self.assertIn("evi_demo_business", fields["evidence_backlinks"]["evidence_ids"])
        self.assertTrue(fields["close"]["present"])
        self.assertTrue(fields["amount"]["present"])

    def test_company_profile_coverage_audit_keeps_research_reports_opinion_only(self) -> None:
        research_document = Document(
            document_id="doc_demo_research",
            issuer_id="issuer_001",
            security_id="sec_001",
            document_type="research_report",
            source_id="local_research_reports",
            source_type="broker_research",
            source_uri="local://demo-research",
            rights_tag=RightsTag("public"),
            body="Demo Corp research view says business momentum is improving.",
            title="Demo research report",
        )
        self.service.store.documents[research_document.document_id] = research_document
        self.service.store.evidence["evi_demo_research"] = Evidence(
            evidence_id="evi_demo_research",
            document_id=research_document.document_id,
            section="research_report_citation",
            page_no=1,
            bbox="research",
            span_text="Research opinion on Demo.",
            canonical_text="Research opinion on Demo.",
            confidence=0.8,
            issuer_id="issuer_001",
            security_id="sec_001",
        )
        self.service.store.research_reports["rr_demo_bound"] = ResearchReportAsset(
            report_id="rr_demo_bound",
            source_id="local_research_reports",
            broker="Local Broker",
            file_path="/tmp/demo.pdf",
            file_name="demo.pdf",
            title="Demo local research",
            document_id=research_document.document_id,
            issuer_id="issuer_001",
            security_id="sec_001",
            status="text_indexed",
        )

        audit = self.router.dispatch(
            "POST",
            "/api/company-profiles/coverage/audit",
            {"symbols": ["DEMO"], "required_fields": ["authorized_documents", "field_evidence_ids", "business_summary", "research_report_count"]},
            actor="data",
            role="analyst",
        )
        self.assertTrue(audit.success, audit.error)
        fields = audit.data["companies"][0]["fields"]
        self.assertTrue(fields["research_report_count"]["present"])
        self.assertEqual(fields["research_report_count"]["source_policy"], "opinion_slot")
        self.assertFalse(fields["authorized_documents"]["present"])
        self.assertFalse(fields["field_evidence_ids"]["present"])
        self.assertFalse(fields["business_summary"]["present"])
        self.assertEqual(fields["business_summary"]["missing_reason"], "research_report_or_local_reference_is_not_fact_source")
        self.assertEqual(audit.data["rules"]["research_reports"], "opinion_and_attention_slots_only_not_fact_source")

    def test_company_database_batch_build_aggregates_batches_and_coverage(self) -> None:
        result = self.router.dispatch(
            "POST",
            "/api/company-database/batch/build",
            {
                "symbols": ["DEMO"],
                "limit": 1,
                "batch_size": 1,
                "build_events": False,
                "build_relationships": False,
                "build_workflow": False,
            },
            actor="data",
            role="data_engineer",
        )
        self.assertTrue(result.success, result.error)
        self.assertEqual(result.data["status"], "dry_run")
        self.assertEqual(result.data["issuer_count"], 1)
        self.assertEqual(result.data["batch_count"], 1)
        self.assertEqual(result.data["totals"]["profiles_planned"], 1)
        self.assertEqual(result.data["coverage_after"]["issuer_count"], 1)

    def test_company_database_batch_build_records_run_history(self) -> None:
        result = self.router.dispatch(
            "POST",
            "/api/company-database/batch/build",
            {
                "symbols": ["DEMO"],
                "limit": 1,
                "batch_size": 1,
                "build_events": False,
                "build_relationships": False,
                "build_workflow": False,
                "execute": True,
            },
            actor="data",
            role="data_engineer",
        )
        self.assertTrue(result.success, result.error)
        self.assertEqual(result.data["status"], "executed")
        self.assertTrue(result.data["run_recorded"])
        run_id = result.data["run_id"]
        self.assertIn(run_id, self.service.store.company_database_build_runs)
        run = self.service.store.company_database_build_runs[run_id]
        self.assertEqual(run.status, "executed")
        self.assertEqual(run.target_issuer_ids, ["issuer_001"])
        self.assertEqual(run.batch_count, 1)
        self.assertEqual(run.totals["profiles_saved"], 1)
        self.assertEqual(run.coverage_before["issuer_count"], 1)
        self.assertEqual(run.coverage_after["issuer_count"], 1)
        self.assertFalse(run.options["build_events"])
        self.assertEqual(result.data["run"]["run_id"], run_id)

        listed = self.router.dispatch(
            "POST",
            "/api/company-database/batch/runs",
            {"issuer_id": "issuer_001", "limit": 5},
            actor="data",
            role="analyst",
        )
        self.assertTrue(listed.success, listed.error)
        self.assertEqual(listed.data["count"], 1)
        self.assertEqual(listed.data["runs"][0]["run_id"], run_id)
        self.assertEqual(listed.data["runs"][0]["usage_boundary"], "company_database_build_run_is_local_research_operations_history_no_live_trading")
        self.assertEqual(listed.data["runs"][0]["batches"], [])
        self.assertTrue(listed.data["runs"][0]["batch_details_omitted"])

        listed_with_batches = self.router.dispatch(
            "POST",
            "/api/company-database/batch/runs",
            {"run_id": run_id, "include_batches": True},
            actor="data",
            role="analyst",
        )
        self.assertTrue(listed_with_batches.success, listed_with_batches.error)
        self.assertTrue(listed_with_batches.data["include_batches"])
        self.assertEqual(len(listed_with_batches.data["runs"][0]["batches"]), 1)

    def test_company_database_batch_build_dry_run_history_is_explicit(self) -> None:
        preview = self.router.dispatch(
            "POST",
            "/api/company-database/batch/build",
            {
                "symbols": ["DEMO"],
                "limit": 1,
                "batch_size": 1,
                "build_events": False,
                "build_relationships": False,
                "build_workflow": False,
            },
            actor="data",
            role="data_engineer",
        )
        self.assertTrue(preview.success, preview.error)
        self.assertFalse(preview.data["run_recorded"])
        self.assertFalse(self.service.store.company_database_build_runs)

        recorded = self.router.dispatch(
            "POST",
            "/api/company-database/batch/build",
            {
                "symbols": ["DEMO"],
                "limit": 1,
                "batch_size": 1,
                "build_events": False,
                "build_relationships": False,
                "build_workflow": False,
                "record_run": True,
            },
            actor="data",
            role="data_engineer",
        )
        self.assertTrue(recorded.success, recorded.error)
        self.assertTrue(recorded.data["run_recorded"])
        run = self.service.store.company_database_build_runs[recorded.data["run_id"]]
        self.assertEqual(run.status, "dry_run")
        self.assertFalse(run.execute)
        self.assertTrue(run.dry_run)
        self.assertEqual(run.totals["profiles_planned"], 1)

    def test_company_database_batch_retry_replays_source_run(self) -> None:
        source = self.router.dispatch(
            "POST",
            "/api/company-database/batch/build",
            {
                "symbols": ["DEMO"],
                "limit": 1,
                "batch_size": 1,
                "build_events": False,
                "build_relationships": False,
                "build_workflow": False,
                "execute": True,
            },
            actor="data",
            role="data_engineer",
        )
        self.assertTrue(source.success, source.error)
        retry = self.router.dispatch(
            "POST",
            f"/api/company-database/batch/runs/{source.data['run_id']}/retry",
            {"record_run": True},
            actor="data",
            role="data_engineer",
        )
        self.assertTrue(retry.success, retry.error)
        self.assertEqual(retry.data["source_run_id"], source.data["run_id"])
        self.assertEqual(retry.data["resume_mode"], "all")
        self.assertEqual(retry.data["attempt"], 2)
        self.assertEqual(retry.data["retry_issuer_ids"], ["issuer_001"])
        retried_run = self.service.store.company_database_build_runs[retry.data["new_run_id"]]
        self.assertEqual(retried_run.retry_of, source.data["run_id"])
        self.assertEqual(retried_run.resume_mode, "all")
        self.assertEqual(retried_run.attempt, 2)
        self.assertEqual(retried_run.target_issuer_ids, ["issuer_001"])
        self.assertFalse(retried_run.options["build_events"])
        self.assertTrue(retried_run.idempotency_key)
        self.assertIn("no_live_trading", retry.data["usage_boundary"])

    def test_company_database_batch_resume_run_id_retries_remaining_issuers(self) -> None:
        self.service.register_issuer(
            {
                "issuer_id": "issuer_002",
                "legal_name": "Other Corp",
                "market": ["U"],
                "country": "US",
            },
            actor="platform",
        )
        self.service.register_security(
            {
                "security_id": "sec_002",
                "issuer_id": "issuer_002",
                "ticker": "OTHER",
                "exchange": "NYSE",
                "currency": "USD",
                "market": "U",
            },
            actor="platform",
        )
        failed_run = CompanyDatabaseBuildRun(
            run_id="cdb_failed_resume",
            actor="data",
            status="partial",
            execute=True,
            dry_run=False,
            target_issuer_ids=["issuer_001", "issuer_002"],
            target_symbols=["DEMO", "OTHER"],
            completed_issuer_ids=["issuer_001"],
            batch_count=1,
            batch_size=1,
            options={
                "batch_size": 1,
                "report_match_limit": 100,
                "structure_reports": False,
                "structure_report_limit": 20,
                "build_events": False,
                "build_relationships": False,
                "build_workflow": False,
                "include_market_data": True,
                "include_research_coverage": True,
                "include_disclosures": True,
                "include_structured_disclosures": True,
                "include_listings": True,
                "include_institution_coverage": True,
                "include_disclosure_candidates": True,
                "event_limit": 100,
                "relationship_limit": 100,
                "workflow_link_limit": 5,
            },
            batches=[{"batch_index": 1, "issuer_ids": ["issuer_001"]}],
            error="simulated failure",
        )
        self.service.store.company_database_build_runs[failed_run.run_id] = failed_run
        resumed = self.router.dispatch(
            "POST",
            "/api/company-database/batch/build",
            {"resume_run_id": failed_run.run_id, "execute": True},
            actor="data",
            role="data_engineer",
        )
        self.assertTrue(resumed.success, resumed.error)
        self.assertEqual(resumed.data["source_run_id"], failed_run.run_id)
        self.assertEqual(resumed.data["resume_mode"], "remaining")
        self.assertEqual(resumed.data["retry_issuer_ids"], ["issuer_002"])
        self.assertEqual(resumed.data["skipped_issuer_ids"], ["issuer_001"])
        new_run = self.service.store.company_database_build_runs[resumed.data["new_run_id"]]
        self.assertEqual(new_run.retry_of, failed_run.run_id)
        self.assertEqual(new_run.resume_of, failed_run.run_id)
        self.assertEqual(new_run.target_issuer_ids, ["issuer_002"])
        self.assertEqual(new_run.skipped_issuer_ids, ["issuer_001"])
        self.assertEqual(new_run.completed_issuer_ids, ["issuer_001", "issuer_002"])

    def test_company_database_batch_records_partial_run_on_failure(self) -> None:
        self.service.register_issuer(
            {
                "issuer_id": "issuer_002",
                "legal_name": "Other Corp",
                "market": ["U"],
                "country": "US",
            },
            actor="platform",
        )
        self.service.register_security(
            {
                "security_id": "sec_002",
                "issuer_id": "issuer_002",
                "ticker": "OTHER",
                "exchange": "NYSE",
                "currency": "USD",
                "market": "U",
            },
            actor="platform",
        )
        original_build_company_events = self.service.build_company_events

        def flaky_build_company_events(payload: dict[str, object], *, actor: str = "system") -> dict[str, object]:
            if payload.get("issuer_ids") == ["issuer_002"]:
                raise RuntimeError("simulated event failure")
            return original_build_company_events(payload, actor=actor)

        self.service.build_company_events = flaky_build_company_events  # type: ignore[method-assign]
        try:
            result = self.router.dispatch(
                "POST",
                "/api/company-database/batch/build",
                {
                    "issuer_ids": ["issuer_001", "issuer_002"],
                    "limit": 2,
                    "batch_size": 1,
                    "build_events": True,
                    "build_relationships": False,
                    "build_workflow": False,
                    "execute": True,
                },
                actor="data",
                role="data_engineer",
            )
        finally:
            self.service.build_company_events = original_build_company_events  # type: ignore[method-assign]
        self.assertFalse(result.success)
        self.assertEqual(result.error["type"], "internal_error")
        partial_runs = [run for run in self.service.store.company_database_build_runs.values() if run.status == "partial"]
        self.assertEqual(len(partial_runs), 1)
        partial_run = partial_runs[0]
        self.assertEqual(partial_run.completed_issuer_ids, ["issuer_001"])
        self.assertEqual(partial_run.target_issuer_ids, ["issuer_001", "issuer_002"])
        self.assertEqual(partial_run.batch_count, 1)
        self.assertIn("simulated event failure", partial_run.error)
        self.assertIn("no_live_trading", partial_run.usage_boundary)

    def test_company_database_coverage_trends_report_and_artifact(self) -> None:
        first = self.router.dispatch(
            "POST",
            "/api/company-database/batch/build",
            {
                "symbols": ["DEMO"],
                "limit": 1,
                "batch_size": 1,
                "build_events": False,
                "build_relationships": False,
                "build_workflow": False,
                "execute": True,
            },
            actor="data",
            role="data_engineer",
        )
        self.assertTrue(first.success, first.error)
        first_run = self.service.store.company_database_build_runs[first.data["run_id"]]
        first_run.coverage_before = {"average_coverage_score": 0.25, "missing_counts": {"company_events": 1, "research_reports": 1}}
        first_run.coverage_after = {"average_coverage_score": 0.5, "missing_counts": {"company_events": 0, "research_reports": 1}}

        second = self.router.dispatch(
            "POST",
            "/api/company-database/batch/build",
            {
                "symbols": ["DEMO"],
                "limit": 1,
                "batch_size": 1,
                "build_events": False,
                "build_relationships": False,
                "build_workflow": False,
                "execute": True,
            },
            actor="data",
            role="data_engineer",
        )
        self.assertTrue(second.success, second.error)
        second_run = self.service.store.company_database_build_runs[second.data["run_id"]]
        second_run.coverage_before = {"average_coverage_score": 0.5, "missing_counts": {"company_events": 0, "research_reports": 1}}
        second_run.coverage_after = {"average_coverage_score": 0.75, "missing_counts": {"company_events": 0, "research_reports": 0}}

        with TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "coverage-trends.json"
            trends = self.router.dispatch(
                "POST",
                "/api/company-database/coverage/trends",
                {"issuer_id": "issuer_001", "limit": 10, "write_artifact": True, "artifact_path": str(artifact_path)},
                actor="data",
                role="analyst",
            )
            self.assertTrue(trends.success, trends.error)
            self.assertEqual(trends.data["run_count"], 2)
            self.assertEqual(trends.data["summary"]["improved_runs"], 2)
            self.assertEqual(trends.data["summary"]["worsened_runs"], 0)
            self.assertAlmostEqual(trends.data["summary"]["cumulative_coverage_delta"], 0.5)
            self.assertEqual(trends.data["summary"]["cumulative_missing_delta"], -2)
            self.assertEqual(trends.data["trend_rows"][0]["missing_delta_by_section"]["company_events"], -1)
            self.assertEqual(trends.data["trend_rows"][1]["missing_delta_by_section"]["research_reports"], -1)
            self.assertEqual(trends.data["artifact"]["classification"], "local-only")
            self.assertFalse(trends.data["artifact"]["acceptable_for_non_local_release_gate"])
            self.assertTrue(artifact_path.exists())
            exported = json.loads(artifact_path.read_text(encoding="utf-8"))
            self.assertEqual(exported["run_count"], 2)
            self.assertEqual(exported["usage_boundary"], "company_database_coverage_trends_are_local_research_operations_history_no_live_trading")

    def test_company_database_coverage_trends_filters_by_issuer_and_status(self) -> None:
        self.service.register_issuer(
            {
                "issuer_id": "issuer_002",
                "legal_name": "Other Corp",
                "market": ["U"],
                "country": "US",
            },
            actor="platform",
        )
        self.service.register_security(
            {
                "security_id": "sec_002",
                "issuer_id": "issuer_002",
                "ticker": "OTHER",
                "exchange": "NYSE",
                "currency": "USD",
                "market": "U",
            },
            actor="platform",
        )
        executed = self.router.dispatch(
            "POST",
            "/api/company-database/batch/build",
            {
                "symbols": ["DEMO"],
                "limit": 1,
                "batch_size": 1,
                "build_events": False,
                "build_relationships": False,
                "build_workflow": False,
                "execute": True,
            },
            actor="data",
            role="data_engineer",
        )
        self.assertTrue(executed.success, executed.error)
        dry_run = self.router.dispatch(
            "POST",
            "/api/company-database/batch/build",
            {
                "symbols": ["OTHER"],
                "limit": 1,
                "batch_size": 1,
                "build_events": False,
                "build_relationships": False,
                "build_workflow": False,
                "record_run": True,
            },
            actor="data",
            role="data_engineer",
        )
        self.assertTrue(dry_run.success, dry_run.error)

        executed_for_demo = self.router.dispatch(
            "POST",
            "/api/company-database/coverage/trends",
            {"issuer_id": "issuer_001", "status": "executed", "limit": 10},
            actor="data",
            role="analyst",
        )
        self.assertTrue(executed_for_demo.success, executed_for_demo.error)
        self.assertEqual(executed_for_demo.data["run_count"], 1)
        self.assertEqual(executed_for_demo.data["trend_rows"][0]["status"], "executed")
        self.assertEqual(executed_for_demo.data["trend_rows"][0]["target_issuer_ids"], ["issuer_001"])

        executed_for_other = self.router.dispatch(
            "POST",
            "/api/company-database/coverage/trends",
            {"issuer_id": "issuer_002", "status": "executed", "limit": 10},
            actor="data",
            role="analyst",
        )
        self.assertTrue(executed_for_other.success, executed_for_other.error)
        self.assertEqual(executed_for_other.data["run_count"], 0)

        dry_runs = self.router.dispatch(
            "POST",
            "/api/company-database/coverage/trends",
            {"status": "dry_run", "limit": 10},
            actor="data",
            role="analyst",
        )
        self.assertTrue(dry_runs.success, dry_runs.error)
        self.assertEqual(dry_runs.data["run_count"], 1)
        self.assertEqual(dry_runs.data["trend_rows"][0]["target_issuer_ids"], ["issuer_002"])

    def test_company_event_builder_creates_market_and_research_attention_events(self) -> None:
        market_point = self.service.register_market_data_point(
            {
                "data_id": "md_demo_latest",
                "security_id": "sec_001",
                "source_id": "public_eod_market_data",
                "market": "A",
                "as_of_date": "2026-06-24",
                "close": 12.3,
                "volume": 123456,
            },
            actor="data",
        )
        self.service.store.research_reports["rr_demo_bound"] = ResearchReportAsset(
            report_id="rr_demo_bound",
            source_id="local_research_reports",
            broker="Local Broker",
            file_path="/tmp/2026-DEMO-coverage.pdf",
            file_name="2026-DEMO-coverage.pdf",
            title="DEMO coverage update",
            year="2026",
            month="06",
            issuer_id="issuer_001",
            security_id="sec_001",
            status="text_indexed",
        )
        self.service.store.disclosure_events["de_demo_001"] = DisclosureEvent(
            event_id="de_demo_001",
            document_id="doc_demo_001",
            issuer_id="issuer_001",
            security_id="sec_001",
            event_type="annual_report",
            item_code="10-K",
            item_title="Annual report",
            severity="medium",
            summary="Demo official filing update.",
            evidence_ids=["ev_demo_001"],
            source_id="src_sec",
        )

        dry_run = self.router.dispatch(
            "POST",
            "/api/company-database/events/build",
            {"symbols": ["DEMO"], "event_limit": 10},
            actor="data",
            role="data_engineer",
        )
        self.assertTrue(dry_run.success, dry_run.error)
        self.assertEqual(dry_run.data["status"], "dry_run")
        self.assertEqual(dry_run.data["events_planned"], 3)
        self.assertFalse(self.service.store.company_events)

        executed = self.router.dispatch(
            "POST",
            "/api/company-database/events/build",
            {"symbols": ["DEMO"], "event_limit": 10, "execute": True},
            actor="data",
            role="data_engineer",
        )
        self.assertTrue(executed.success, executed.error)
        self.assertEqual(executed.data["events_created"], 3)
        event_types = {event.event_type for event in self.service.store.company_events.values()}
        self.assertEqual(event_types, {"market_data", "research_coverage", "official_disclosure"})
        market_event = next(event for event in self.service.store.company_events.values() if event.event_type == "market_data")
        research_event = next(event for event in self.service.store.company_events.values() if event.event_type == "research_coverage")
        disclosure_event = next(event for event in self.service.store.company_events.values() if event.event_type == "official_disclosure")
        self.assertEqual(market_event.metadata["data_id"], market_point.data_id)
        self.assertEqual(market_event.fact_status, "verified")
        self.assertEqual(research_event.fact_status, "opinion_signal")
        self.assertEqual(research_event.metadata["rights_boundary"], "opinion_only_not_fact_source")
        self.assertEqual(disclosure_event.fact_status, "verified")
        self.assertEqual(disclosure_event.document_ids, ["doc_demo_001"])
        self.assertEqual(disclosure_event.evidence_ids, ["ev_demo_001"])
        self.assertEqual(disclosure_event.metadata["source_layer"], "disclosure_event")

        aggregated = self.router.dispatch("GET", "/api/company-intelligence/DEMO", {"limit": 20}, role="analyst")
        self.assertTrue(aggregated.success, aggregated.error)
        self.assertEqual(aggregated.data["section_counts"]["company_events"], 3)
        self.assertTrue(aggregated.data["data_quality"]["event_timeline_available"])

    def test_company_event_builder_extracts_structured_disclosure_events(self) -> None:
        self.service.store.evidence["ev_detail_disclosure"] = Evidence(
            evidence_id="ev_detail_disclosure",
            document_id="doc_detail_disclosure",
            section="official_disclosure",
            page_no=1,
            bbox="p1",
            span_text=(
                "Revenue increased 18% and net income improved. The board appointed a new chief financial officer. "
                "The company signed a supply agreement and expanded production capacity. "
                "Management disclosed an export control policy impact and settled a litigation matter."
            ),
            canonical_text=(
                "Revenue increased, chief financial officer appointed, supply agreement, production capacity, "
                "export control policy impact and litigation settlement."
            ),
            confidence=0.93,
            issuer_id="issuer_001",
            security_id="sec_001",
        )
        self.service.store.disclosure_events["de_detail_disclosure"] = DisclosureEvent(
            event_id="de_detail_disclosure",
            document_id="doc_detail_disclosure",
            issuer_id="issuer_001",
            security_id="sec_001",
            event_type="annual_report",
            item_code="10-K",
            item_title="Annual report detailed operating update",
            severity="medium",
            summary="Annual report contains financial, management, contract, capacity, policy and litigation updates.",
            evidence_ids=["ev_detail_disclosure"],
            source_id="src_sec",
        )

        dry_run = self.router.dispatch(
            "POST",
            "/api/company-database/events/build",
            {
                "symbols": ["DEMO"],
                "event_limit": 10,
                "include_market_data": False,
                "include_research_coverage": False,
            },
            actor="data",
            role="data_engineer",
        )
        self.assertTrue(dry_run.success, dry_run.error)
        self.assertEqual(dry_run.data["status"], "dry_run")
        self.assertEqual(dry_run.data["events_planned"], 7)
        self.assertEqual(dry_run.data["companies"][0]["structured_disclosure_event_count"], 6)
        self.assertFalse(self.service.store.company_events)

        executed = self.router.dispatch(
            "POST",
            "/api/company-database/events/build",
            {
                "symbols": ["DEMO"],
                "event_limit": 10,
                "include_market_data": False,
                "include_research_coverage": False,
                "execute": True,
            },
            actor="data",
            role="data_engineer",
        )
        self.assertTrue(executed.success, executed.error)
        self.assertEqual(executed.data["events_created"], 7)
        event_types = {event.event_type for event in self.service.store.company_events.values()}
        self.assertEqual(
            event_types,
            {
                "official_disclosure",
                "earnings_result",
                "management_change",
                "litigation_regulatory",
                "major_order_contract",
                "capacity_supply_demand",
                "policy_impact",
            },
        )
        detailed_events = [
            event
            for event in self.service.store.company_events.values()
            if event.metadata.get("source_layer") == "official_disclosure_text_classification"
        ]
        self.assertEqual(len(detailed_events), 6)
        for event in detailed_events:
            self.assertEqual(event.fact_status, "verified")
            self.assertEqual(event.review_status, "needs_review")
            self.assertEqual(event.document_ids, ["doc_detail_disclosure"])
            self.assertEqual(event.evidence_ids, ["ev_detail_disclosure"])
            self.assertEqual(event.metadata["classification_status"], "candidate_needs_review")
            self.assertEqual(event.metadata["rights_boundary"], "official_disclosure_fact_with_classification_review")

    def test_company_relationship_builder_creates_listing_and_coverage_links(self) -> None:
        self.service.store.research_reports["rr_demo_bound"] = ResearchReportAsset(
            report_id="rr_demo_bound",
            source_id="local_research_reports",
            broker="Local Broker",
            file_path="/tmp/2026-DEMO-coverage.pdf",
            file_name="2026-DEMO-coverage.pdf",
            title="DEMO coverage update",
            year="2026",
            month="06",
            issuer_id="issuer_001",
            security_id="sec_001",
            status="text_indexed",
        )
        self.service.store.evidence["ev_relationship_demo"] = Evidence(
            evidence_id="ev_relationship_demo",
            document_id="doc_relationship_demo",
            section="official_disclosure",
            page_no=1,
            bbox="p1",
            span_text="The company reported customer Mega Cloud and supplier Wafer Co.",
            canonical_text="customer Mega Cloud and supplier Wafer Co.",
            confidence=0.91,
            issuer_id="issuer_001",
            security_id="sec_001",
        )
        self.service.store.disclosure_events["de_relationship_demo"] = DisclosureEvent(
            event_id="de_relationship_demo",
            document_id="doc_relationship_demo",
            issuer_id="issuer_001",
            security_id="sec_001",
            event_type="annual_report",
            item_code="10-K",
            item_title="Annual report relationship disclosure",
            severity="medium",
            summary="The company reported customer Mega Cloud and supplier Wafer Co.",
            evidence_ids=["ev_relationship_demo"],
            source_id="src_sec",
        )

        dry_run = self.router.dispatch(
            "POST",
            "/api/company-database/relationships/build",
            {"symbols": ["DEMO"], "relationship_limit": 10},
            actor="data",
            role="data_engineer",
        )
        self.assertTrue(dry_run.success, dry_run.error)
        self.assertEqual(dry_run.data["status"], "dry_run")
        self.assertEqual(dry_run.data["relationships_planned"], 4)
        self.assertFalse(self.service.store.company_relationships)

        executed = self.router.dispatch(
            "POST",
            "/api/company-database/relationships/build",
            {"symbols": ["DEMO"], "relationship_limit": 10, "execute": True},
            actor="data",
            role="data_engineer",
        )
        self.assertTrue(executed.success, executed.error)
        self.assertEqual(executed.data["relationships_created"], 4)
        relationship_types = {relationship.relationship_type for relationship in self.service.store.company_relationships.values()}
        self.assertEqual(relationship_types, {"listed_security", "institution_coverage", "customer_candidate", "supplier_candidate"})
        coverage = next(relationship for relationship in self.service.store.company_relationships.values() if relationship.relationship_type == "institution_coverage")
        self.assertEqual(coverage.object_type, "institution")
        self.assertEqual(coverage.review_status, "needs_review")
        self.assertEqual(coverage.metadata["rights_boundary"], "opinion_coverage_relationship_not_company_fact")
        customer = next(relationship for relationship in self.service.store.company_relationships.values() if relationship.relationship_type == "customer_candidate")
        supplier = next(relationship for relationship in self.service.store.company_relationships.values() if relationship.relationship_type == "supplier_candidate")
        self.assertEqual(customer.metadata["entity_name"], "Mega Cloud")
        self.assertEqual(supplier.metadata["entity_name"], "Wafer Co")
        self.assertEqual(customer.review_status, "needs_review")
        self.assertEqual(customer.metadata["source_layer"], "official_disclosure_candidate")
        self.assertEqual(customer.evidence_ids, ["ev_relationship_demo"])

        aggregated = self.router.dispatch("GET", "/api/company-intelligence/DEMO", {"limit": 20}, role="analyst")
        self.assertTrue(aggregated.success, aggregated.error)
        self.assertEqual(aggregated.data["section_counts"]["company_relationships"], 4)
        self.assertTrue(aggregated.data["data_quality"]["relationship_graph_available"])

    def test_company_relationship_review_approves_rejects_and_merges_candidates(self) -> None:
        approved = self.service.register_company_relationship(
            {
                "relationship_id": "rel_candidate_approve",
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "subject_type": "company",
                "subject_id": "issuer_001",
                "object_type": "company",
                "object_id": "external_company_mega_cloud",
                "relationship_type": "customer_candidate",
                "relationship_status": "unknown",
                "review_status": "needs_review",
                "confidence": 0.55,
                "metadata": {"candidate_status": "candidate"},
            },
            actor="data",
        )
        rejected = self.service.register_company_relationship(
            {
                "relationship_id": "rel_candidate_reject",
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "subject_type": "company",
                "subject_id": "issuer_001",
                "object_type": "company",
                "object_id": "external_company_bad",
                "relationship_type": "supplier_candidate",
                "relationship_status": "unknown",
                "review_status": "needs_review",
                "confidence": 0.55,
                "metadata": {"candidate_status": "candidate"},
            },
            actor="data",
        )
        target = self.service.register_company_relationship(
            {
                "relationship_id": "rel_candidate_target",
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "subject_type": "company",
                "subject_id": "issuer_001",
                "object_type": "company",
                "object_id": "external_company_partner",
                "relationship_type": "partner_candidate",
                "relationship_status": "unknown",
                "review_status": "needs_review",
                "confidence": 0.55,
                "evidence_ids": ["ev_target"],
                "metadata": {"candidate_status": "candidate"},
            },
            actor="data",
        )
        source = self.service.register_company_relationship(
            {
                "relationship_id": "rel_candidate_merge",
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "subject_type": "company",
                "subject_id": "issuer_001",
                "object_type": "company",
                "object_id": "external_company_partner_alias",
                "relationship_type": "partner_candidate",
                "relationship_status": "unknown",
                "review_status": "needs_review",
                "confidence": 0.55,
                "evidence_ids": ["ev_source"],
                "metadata": {"candidate_status": "candidate"},
            },
            actor="data",
        )

        approved_response = self.router.dispatch(
            "POST",
            f"/api/company-relationships/{approved.relationship_id}/review",
            {"action": "approve", "reason": "evidence checked"},
            actor="analyst",
            role="analyst",
        )
        self.assertTrue(approved_response.success, approved_response.error)
        self.assertEqual(approved_response.data["review_status"], "approved")
        self.assertEqual(approved_response.data["relationship_status"], "active")
        self.assertGreaterEqual(approved_response.data["confidence"], 0.8)

        rejected_response = self.router.dispatch(
            "POST",
            f"/api/company-relationships/{rejected.relationship_id}/review",
            {"action": "reject", "reason": "false positive"},
            actor="analyst",
            role="analyst",
        )
        self.assertTrue(rejected_response.success, rejected_response.error)
        self.assertEqual(rejected_response.data["review_status"], "rejected")
        self.assertEqual(rejected_response.data["relationship_status"], "inactive")

        merged_response = self.router.dispatch(
            "POST",
            f"/api/company-relationships/{source.relationship_id}/review",
            {"action": "merge", "target_relationship_id": target.relationship_id},
            actor="analyst",
            role="analyst",
        )
        self.assertTrue(merged_response.success, merged_response.error)
        self.assertEqual(merged_response.data["review_status"], "merged")
        self.assertEqual(self.service.store.company_relationships[target.relationship_id].evidence_ids, ["ev_target", "ev_source"])
        self.assertIn(source.relationship_id, self.service.store.company_relationships[target.relationship_id].metadata["merged_from"])

    def test_company_workflow_builder_creates_observation_conclusion_and_paper_feedback(self) -> None:
        self.service.register_market_data_point(
            {
                "data_id": "md_demo_workflow_latest",
                "security_id": "sec_001",
                "source_id": "public_eod_market_data",
                "market": "A",
                "as_of_date": "2026-06-24",
                "close": 12.3,
                "volume": 123456,
            },
            actor="data",
        )
        self.service.store.research_reports["rr_demo_workflow"] = ResearchReportAsset(
            report_id="rr_demo_workflow",
            source_id="local_research_reports",
            broker="Local Broker",
            file_path="/tmp/2026-DEMO-workflow.pdf",
            file_name="2026-DEMO-workflow.pdf",
            title="DEMO 买入 目标价 18 元 demand catalyst risk margin",
            year="2026",
            month="06",
            issuer_id="issuer_001",
            security_id="sec_001",
            status="text_indexed",
        )
        structured = self.router.dispatch(
            "POST",
            "/api/research-reports/structure",
            {"report_ids": ["rr_demo_workflow"], "execute": True},
            actor="data",
            role="analyst",
        )
        self.assertTrue(structured.success, structured.error)
        events = self.router.dispatch(
            "POST",
            "/api/company-database/events/build",
            {"symbols": ["DEMO"], "event_limit": 10, "execute": True},
            actor="data",
            role="data_engineer",
        )
        self.assertTrue(events.success, events.error)
        relationships = self.router.dispatch(
            "POST",
            "/api/company-database/relationships/build",
            {"symbols": ["DEMO"], "relationship_limit": 10, "execute": True},
            actor="data",
            role="data_engineer",
        )
        self.assertTrue(relationships.success, relationships.error)

        dry_run = self.router.dispatch(
            "POST",
            "/api/company-database/workflow/build",
            {"symbols": ["DEMO"], "link_limit": 5},
            actor="data",
            role="data_engineer",
        )
        self.assertTrue(dry_run.success, dry_run.error)
        self.assertEqual(dry_run.data["status"], "dry_run")
        self.assertEqual(dry_run.data["observations_planned"], 1)
        self.assertEqual(dry_run.data["conclusions_planned"], 1)
        self.assertEqual(dry_run.data["feedback_planned"], 1)
        self.assertFalse(self.service.store.observation_items)
        self.assertFalse(self.service.store.analysis_conclusions)
        self.assertFalse(self.service.store.simulation_feedback)

        executed = self.router.dispatch(
            "POST",
            "/api/company-database/workflow/build",
            {"symbols": ["DEMO"], "link_limit": 5, "execute": True},
            actor="data",
            role="data_engineer",
        )
        self.assertTrue(executed.success, executed.error)
        self.assertEqual(executed.data["status"], "executed")
        self.assertEqual(executed.data["observations_created"], 1)
        self.assertEqual(executed.data["conclusions_created"], 1)
        self.assertEqual(executed.data["feedback_created"], 1)
        observation = next(iter(self.service.store.observation_items.values()))
        conclusion = next(iter(self.service.store.analysis_conclusions.values()))
        feedback = next(iter(self.service.store.simulation_feedback.values()))
        self.assertEqual(observation.observation_type, "company_intelligence_follow_up")
        self.assertEqual(conclusion.conclusion_type, "company_intelligence_baseline")
        self.assertEqual(conclusion.status, "draft")
        self.assertTrue(conclusion.related_viewpoint_ids)
        self.assertEqual(feedback.feedback_type, "watch_only")
        self.assertTrue(feedback.paper_only)
        self.assertFalse(feedback.live_execution_allowed)
        self.assertFalse(feedback.broker_connected)

        refreshed = self.router.dispatch(
            "POST",
            "/api/company-database/workflow/build",
            {"symbols": ["DEMO"], "link_limit": 5, "execute": True},
            actor="data",
            role="data_engineer",
        )
        self.assertTrue(refreshed.success, refreshed.error)
        self.assertEqual(refreshed.data["observations_updated"], 1)
        self.assertEqual(refreshed.data["conclusions_updated"], 1)
        self.assertEqual(refreshed.data["feedback_updated"], 1)

        aggregated = self.router.dispatch("GET", "/api/company-intelligence/DEMO", {"limit": 20}, role="analyst")
        self.assertTrue(aggregated.success, aggregated.error)
        self.assertEqual(aggregated.data["section_counts"]["observation_items"], 1)
        self.assertEqual(aggregated.data["section_counts"]["analysis_conclusions"], 1)
        self.assertEqual(aggregated.data["section_counts"]["simulation_feedback_records"], 1)
        self.assertTrue(aggregated.data["data_quality"]["simulation_feedback_available"])

    def test_simulation_feedback_performance_update_uses_latest_market_data(self) -> None:
        self.service.register_market_data_point(
            {
                "data_id": "md_demo_feedback_latest",
                "security_id": "sec_001",
                "source_id": "public_eod_market_data",
                "market": "A",
                "as_of_date": "2026-06-24",
                "close": 12.0,
                "volume": 123456,
            },
            actor="data",
        )
        conclusion = self.service.create_analysis_conclusion(
            {
                "analysis_conclusion_id": "ac_feedback_demo",
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "title": "Demo feedback baseline",
                "conclusion": "Watch only.",
                "status": "draft",
            },
            actor="analyst",
        )
        feedback = self.service.record_simulation_feedback(
            {
                "simulation_feedback_id": "sf_feedback_demo",
                "analysis_conclusion_id": conclusion.analysis_conclusion_id,
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "feedback_type": "watch_only",
                "paper_only": True,
                "live_execution_allowed": False,
                "broker_connected": False,
                "simulated_action": "watch",
                "entry_price": 10.0,
                "start_at": "2026-06-20T00:00:00+00:00",
            },
            actor="analyst",
        )

        dry_run = self.router.dispatch(
            "POST",
            "/api/simulation-feedback/performance/update",
            {"symbols": ["DEMO"]},
            actor="data",
            role="analyst",
        )
        self.assertTrue(dry_run.success, dry_run.error)
        self.assertEqual(dry_run.data["status"], "dry_run")
        self.assertEqual(dry_run.data["feedback_planned"], 1)
        self.assertEqual(self.service.store.simulation_feedback[feedback.simulation_feedback_id].performance, {})

        executed = self.router.dispatch(
            "POST",
            "/api/simulation-feedback/performance/update",
            {"symbols": ["DEMO"], "execute": True},
            actor="data",
            role="analyst",
        )
        self.assertTrue(executed.success, executed.error)
        self.assertEqual(executed.data["feedback_updated"], 1)
        updated = self.service.store.simulation_feedback[feedback.simulation_feedback_id]
        self.assertEqual(updated.performance["latest_market_data_id"], "md_demo_feedback_latest")
        self.assertEqual(updated.performance["return_pct"], 0.2)
        self.assertTrue(updated.validation["paper_only"])
        self.assertFalse(updated.validation["live_execution_allowed"])

    def test_research_report_realization_update_recomputes_target_price_and_analyst_score(self) -> None:
        self.service.register_market_data_point(
            {
                "data_id": "md_demo_realization_latest",
                "security_id": "sec_001",
                "source_id": "public_eod_market_data",
                "market": "A",
                "as_of_date": "2026-06-24",
                "close": 12.0,
                "volume": 123456,
            },
            actor="data",
        )
        self.service.register_analyst_profile(
            {
                "analyst_id": "analyst_realization",
                "name": "Analyst Realization",
                "institution_id": "local_research_reports",
                "covered_issuer_ids": ["issuer_001"],
                "report_count": 1,
            },
            actor="data",
        )
        self.service.register_structured_research_report(
            {
                "research_report_id": "srr_realization",
                "title": "Demo target price report",
                "institution_id": "local_research_reports",
                "institution_name": "Local Broker",
                "analyst_ids": ["analyst_realization"],
                "analyst_names": ["Analyst Realization"],
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "rating": "buy",
                "target_price": 11.0,
                "parser_status": "metadata_only",
            },
            actor="data",
        )
        viewpoint = self.service.register_report_viewpoint(
            {
                "viewpoint_id": "vp_realization",
                "research_report_id": "srr_realization",
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "statement": "Target price should be reached.",
                "target_price": 11.0,
                "rating": "buy",
            },
            actor="data",
        )
        forecast = self.service.register_report_forecast(
            {
                "forecast_id": "fc_realization",
                "research_report_id": "srr_realization",
                "viewpoint_id": viewpoint.viewpoint_id,
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "forecast_type": "target_price",
                "period": "latest",
                "forecast_value": 11.0,
                "currency": "CNY",
            },
            actor="data",
        )

        dry_run = self.router.dispatch(
            "POST",
            "/api/research-reports/realization/update",
            {"symbols": ["DEMO"]},
            actor="data",
            role="analyst",
        )
        self.assertTrue(dry_run.success, dry_run.error)
        self.assertEqual(dry_run.data["forecast_planned"], 1)
        self.assertEqual(self.service.store.report_forecasts[forecast.forecast_id].actual_value, 0.0)

        executed = self.router.dispatch(
            "POST",
            "/api/research-reports/realization/update",
            {"symbols": ["DEMO"], "execute": True},
            actor="data",
            role="analyst",
        )
        self.assertTrue(executed.success, executed.error)
        self.assertEqual(executed.data["forecast_updated"], 1)
        self.assertEqual(executed.data["viewpoint_updated"], 1)
        self.assertEqual(executed.data["analyst_scores_recomputed"], 1)
        updated_forecast = self.service.store.report_forecasts[forecast.forecast_id]
        updated_viewpoint = self.service.store.report_viewpoints[viewpoint.viewpoint_id]
        self.assertEqual(updated_forecast.actual_value, 12.0)
        self.assertEqual(updated_forecast.realization_status, "realized")
        self.assertEqual(updated_viewpoint.realization_status, "realized")
        self.assertTrue(self.service.store.analyst_reliability_scores)

    def test_latest_analysis_api_summarizes_local_artifact_for_ui(self) -> None:
        with TemporaryDirectory() as tmpdir:
            cwd = Path.cwd()
            os.chdir(tmpdir)
            self.addCleanup(os.chdir, cwd)
            artifact_dir = Path("artifacts/latest-analysis-ahu")
            artifact_dir.mkdir(parents=True)
            Path("artifacts/local-business-acceptance-after-us-eod.json").write_text(
                json.dumps({"base_url": "http://127.0.0.1:8000", "check_count": 2, "checks": [{"passed": True}, {"passed": True}]}),
                encoding="utf-8",
            )
            (artifact_dir / "latest-analysis.json").write_text(
                json.dumps(
                    {
                        "status": "passed",
                        "generated_at": "2026-05-18T12:00:00+08:00",
                        "analysis": {
                            "assets": [
                                {"label": "600000", "security_id": "sec_600000", "market": "A", "source_id": "public_eod_market_data"},
                                {"label": "AAPL", "security_id": "security_aapl_us", "market": "U", "source_id": "yahoo_chart_us_eod"},
                            ],
                            "window": {"start_date": "2026-05-01", "end_date": "2026-05-15"},
                            "latest_market_date": "2026-05-15",
                            "returns": {
                                "600000": {"total_return": -0.025, "return_count": 10},
                                "AAPL": {"total_return": 0.1234, "return_count": 10},
                            },
                            "latest_snapshot": [
                                {
                                    "label": "600000",
                                    "security_id": "sec_600000",
                                    "market": "A",
                                    "as_of_date": "2026-05-15",
                                    "close": 9.07,
                                    "source_id": "public_eod_market_data",
                                    "rights_tag": {"license_class": "public_eod_reference"},
                                },
                                {
                                    "label": "AAPL",
                                    "security_id": "security_aapl_us",
                                    "market": "U",
                                    "as_of_date": "2026-05-15",
                                    "close": 300.23,
                                    "source_id": "yahoo_chart_us_eod",
                                    "rights_tag": {"license_class": "candidate_us_eod_reference"},
                                },
                            ],
                            "portfolio_optimizer": {"proposal_id": "pfp_latest", "candidate_weights": {"security_aapl_us": 0.6, "sec_600000": 0.4}},
                            "portfolio_forward": {"simulation_only": True, "review_flags": []},
                            "metrics_counts": {"research_reports": 1000, "research_report_citation_evidence": 3200},
                            "research_evidence": {
                                "status": "passed",
                                "counts": {
                                    "research_reports": 1000,
                                    "research_report_citation_evidence": 3200,
                                    "total_evidence": 3600,
                                },
                                "semantic_recall": {
                                    "status": "passed",
                                    "samples": [
                                        {
                                            "resource_type": "research_report",
                                            "resource_id": "rr_demo",
                                            "title": "AI semiconductor report",
                                            "source_boundary": "local_reference_research_report",
                                            "risk_level": "restricted",
                                        }
                                    ],
                                },
                                "hotspot_recall": {"status": "passed", "samples": []},
                                "training_allowed": False,
                                "fact_source_allowed": False,
                                "live_trade_signal_allowed": False,
                            },
                            "data_quality": {
                                "status": "usable_with_warnings",
                                "decision_readiness": "research_only",
                                "issues": [
                                    {
                                        "severity": "medium",
                                        "issue": "research_is_opinion_only",
                                        "message": "Research evidence is opinion only.",
                                    }
                                ],
                            },
                            "decision_summary": {
                                "status": "research_only",
                                "headline": "AAPL is the current research candidate.",
                                "conclusion": "Research only.",
                                "top_recommendations": [
                                    {
                                        "label": "AAPL",
                                        "security_id": "security_aapl_us",
                                        "stance": "研究候选",
                                        "total_return_pct": 12.34,
                                        "candidate_weight_pct": 60.0,
                                        "reasons": ["区间收益 12.34%"],
                                        "risks": ["观点证据仅作参考"],
                                    }
                                ],
                                "red_flags": ["Research evidence is opinion only."],
                            },
                            "supplemental_market_observations": {
                                "status": "available",
                                "usage_boundary": "manual_reference_or_supplemental_research_only_not_official_eod_not_trade_signal",
                                "observations": [
                                    {
                                        "label": "600000",
                                        "official_as_of_date": "2026-05-15",
                                        "official_close": 9.07,
                                        "supplemental_as_of_date": "2026-05-22",
                                        "supplemental_close": 8.86,
                                        "price_change_since_official_close_pct": -2.32,
                                        "source_boundary": "manual_reference_or_supplemental_research_only",
                                    }
                                ],
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )

            response = self.router.dispatch("GET", "/api/analysis/latest", {}, role="CEO")

        self.assertTrue(response.success)
        self.assertEqual(response.data["latest_market_date"], "2026-05-15")
        self.assertEqual(len(response.data["returns"]), 2)
        self.assertEqual(response.data["returns"][0]["total_return_pct"], -2.5)
        self.assertEqual(response.data["weights"][0]["label"], "AAPL")
        self.assertEqual(response.data["weights"][0]["weight_pct"], 60.0)
        self.assertTrue(response.data["business_acceptance"]["passed"])
        self.assertEqual(response.data["research_evidence"]["counts"]["research_report_citation_evidence"], 3200)
        self.assertFalse(response.data["research_evidence"]["training_allowed"])
        self.assertEqual(response.data["decision_summary"]["headline"], "AAPL is the current research candidate.")
        self.assertEqual(response.data["data_quality"]["decision_readiness"], "research_only")
        self.assertEqual(response.data["supplemental_market_observations"]["observations"][0]["label"], "600000")
        self.assertEqual({item["source_id"] for item in response.data["source_summary"]}, {"public_eod_market_data", "yahoo_chart_us_eod"})

    def test_latest_analysis_api_prefers_daily_update_artifacts_and_exposes_daily_insight(self) -> None:
        with TemporaryDirectory() as tmpdir:
            cwd = Path.cwd()
            os.chdir(tmpdir)
            self.addCleanup(os.chdir, cwd)
            stale_dir = Path("artifacts/latest-analysis")
            stale_dir.mkdir(parents=True)
            stale_dir.joinpath("latest-analysis.json").write_text(
                json.dumps(
                    {
                        "status": "passed",
                        "generated_at": "2026-05-24T00:00:00+00:00",
                        "analysis": {
                            "latest_market_date": "2026-05-22",
                            "decision_summary": {"headline": "stale headline"},
                            "returns": {},
                        },
                    }
                ),
                encoding="utf-8",
            )
            run_dir = Path("artifacts/daily-update-local/runs/2026-05-25-183000")
            latest_dir = run_dir / "latest-analysis-2026-05-25"
            latest_dir.mkdir(parents=True)
            (latest_dir / "latest-analysis.json").write_text(
                json.dumps(
                    {
                        "status": "passed",
                        "generated_at": "2026-05-25T10:30:00+08:00",
                        "analysis": {
                            "latest_market_date": "2026-05-25",
                            "assets": [{"label": "AAPL", "security_id": "security_aapl_us", "market": "U", "source_id": "yahoo_chart_us_eod"}],
                            "returns": {"AAPL": {"total_return": 0.02, "return_count": 2}},
                            "decision_summary": {"headline": "daily latest headline"},
                        },
                    }
                ),
                encoding="utf-8",
            )
            (run_dir / "daily-update-2026-05-25.json").write_text(
                json.dumps({"status": "passed", "run_date": "2026-05-25", "effective_end_dates": {"A": "2026-05-25", "U": "2026-05-25"}}),
                encoding="utf-8",
            )
            (run_dir / "daily-insight-json-2026-05-25.json").write_text(
                json.dumps(
                    {
                        "status": "passed",
                        "as_of_date": "2026-05-25",
                        "generated_at": "2026-05-25T10:35:00+08:00",
                        "market_freshness": [{"market": "U", "latest_date": "2026-05-25"}],
                        "actionable_research_summary": {
                            "headline": "直接研报证据优先: U AAPL AI 算力: 收盘 310，涨跌幅 1.00%，3 份研报/4 条证据",
                            "abnormal_headline": "U 市场首要异动: TEST 涨跌幅 10.00%",
                            "direct_report_evidence_company_count": 1,
                            "direct_report_watch_items": [
                                {
                                    "ticker": "AAPL",
                                    "issuer_name": "Apple",
                                    "market": "U",
                                    "chain": "AI 算力",
                                    "nodes": ["端侧设备"],
                                    "evidence_status": "direct_report_evidence",
                                    "report_count": 3,
                                    "evidence_count": 4,
                                    "research_readout": "AAPL 有直接研报证据",
                                }
                            ],
                        },
                        "quality_gates": {
                            "typed_only_market_data": True,
                            "direct_report_evidence_company_count": 1,
                            "min_direct_evidence_companies": 1,
                        },
                    }
                ),
                encoding="utf-8",
            )
            Path("artifacts/daily-update-local").mkdir(parents=True, exist_ok=True)
            Path("artifacts/daily-update-local/latest-run.json").write_text(
                json.dumps(
                    {
                        "run_date": "2026-05-25",
                        "run_id": "2026-05-25-183000",
                        "output_dir": str(run_dir),
                        "pipeline_output": str(run_dir / "daily-update-2026-05-25.json"),
                    }
                ),
                encoding="utf-8",
            )

            response = self.router.dispatch("GET", "/api/analysis/latest", {}, role="CEO")

        self.assertTrue(response.success)
        self.assertEqual(response.data["artifact_path"], "artifacts/daily-update-local/runs/2026-05-25-183000/latest-analysis-2026-05-25/latest-analysis.json")
        self.assertEqual(response.data["latest_market_date"], "2026-05-25")
        self.assertTrue(response.data["daily_insight"]["actionable_research_summary"]["headline"].startswith("直接研报证据优先:"))
        self.assertEqual(response.data["daily_insight"]["quality_gates"]["direct_report_evidence_company_count"], 1)

    def test_latest_analysis_cross_market_date_mismatch_is_warning_not_blocker(self) -> None:
        analysis = {
            "latest_market_date": "2026-05-25",
            "latest_snapshot": [
                {"label": "000001", "market": "A", "as_of_date": "2026-05-25"},
                {"label": "AAPL", "market": "U", "as_of_date": "2026-05-22"},
            ],
            "returns": {
                "000001": {"return_count": 22},
                "AAPL": {"return_count": 22},
            },
            "research_evidence": {
                "semantic_recall": {
                    "samples": [
                        {"snippet": "We expect revenue growth and margin improvement driven by stronger demand, price discipline, and supply chain recovery across the next reporting period.", "resource_type": "research_report", "resource_id": "rr1"},
                        {"snippet": "Our capex investment thesis is supported by cloud demand growth, stronger orders, positive pricing, and improved supply visibility for core suppliers.", "resource_type": "research_report", "resource_id": "rr2"},
                    ]
                },
                "hotspot_recall": {"samples": [{"snippet": "We see revenue, EPS, demand, and margin risk improving as customers increased orders and inventory pressure decreased materially.", "resource_type": "research_report", "resource_id": "rr3"}]},
                "fact_source_allowed": False,
            },
        }

        quality = latest_analysis_run_script._data_quality_assessment(analysis)  # type: ignore[attr-defined]

        self.assertEqual(quality["decision_readiness"], "research_only")
        self.assertEqual(quality["status"], "usable_with_warnings")
        issue_codes = {item["code"] for item in quality["issues"]}
        self.assertIn("cross_market_date_mismatch", issue_codes)
        self.assertNotIn("stale_within_market", issue_codes)

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
        self.service.seed_default_sources(actor="data")
        for as_of_date, sec_001_close, sec_us_close, sec_h_close in [
            ("2025-05-01", 10.0, 20.0, 30.0),
            ("2025-05-02", 10.5, 19.8, 30.5),
            ("2025-05-03", 10.8, 20.4, 31.0),
        ]:
            self.service.register_market_data_point(
                {
                    "security_id": "sec_001",
                    "source_id": "public_eod_market_data",
                    "as_of_date": as_of_date,
                    "market": "A",
                    "data_type": "eod",
                    "currency": "CNY",
                    "open": sec_001_close - 0.2,
                    "high": sec_001_close + 0.3,
                    "low": sec_001_close - 0.4,
                    "close": sec_001_close,
                    "adjusted_close": sec_001_close,
                    "volume": 1000,
                },
                actor="data",
            )
            self.service.register_market_data_point(
                {
                    "security_id": "sec_us",
                    "source_id": "public_eod_market_data",
                    "as_of_date": as_of_date,
                    "market": "U",
                    "data_type": "eod",
                    "currency": "USD",
                    "open": sec_us_close - 0.2,
                    "high": sec_us_close + 0.3,
                    "low": sec_us_close - 0.4,
                    "close": sec_us_close,
                    "adjusted_close": sec_us_close,
                    "volume": 2000,
                },
                actor="data",
            )
            self.service.register_market_data_point(
                {
                    "security_id": "sec_h",
                    "source_id": "public_eod_market_data",
                    "as_of_date": as_of_date,
                    "market": "H",
                    "data_type": "eod",
                    "currency": "HKD",
                    "open": sec_h_close - 0.2,
                    "high": sec_h_close + 0.3,
                    "low": sec_h_close - 0.4,
                    "close": sec_h_close,
                    "adjusted_close": sec_h_close,
                    "volume": 3000,
                },
                actor="data",
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

        compare = self.router.dispatch(
            "POST",
            "/api/portfolio/optimizer/compare",
            {
                "proposal_id": "pfp_bl",
                "baseline_method": "equal_weight",
                "external_optimizer_weights": {"sec_us": 0.7, "sec_001": 0.3},
            },
            role="CIO",
        )
        self.assertTrue(compare.success, compare.error)
        self.assertTrue(compare.data["simulation_only"])
        self.assertFalse(compare.data["live_execution_allowed"])
        self.assertEqual(compare.data["baseline_method"], "equal_weight")
        self.assertEqual(compare.data["comparisons"][0]["optimizer"], "candidate")
        self.assertEqual(compare.data["comparisons"][0]["reference"], "baseline:equal_weight")
        self.assertIn("restricted_security", compare.data["constraint_report"]["restricted_security_violations"] or ["restricted_security"])
        self.assertIn("market_exposure", compare.data["constraint_report"]["diagnostic_exposure"])
        self.assertEqual(compare.data["external_optimizer"]["status"], "supplied")
        self.assertEqual(compare.data["external_optimizer"]["diagnostics"]["dependency"], "caller_supplied")

        external_probe = self.router.dispatch(
            "POST",
            "/api/portfolio/optimizer/compare",
            {
                "proposal_id": "pfp_bl",
                "baseline_method": "posterior",
                "run_external_optimizer": True,
                "external_optimizer_name": "cvxpy",
            },
            role="CIO",
        )
        self.assertTrue(external_probe.success, external_probe.error)
        self.assertEqual(external_probe.data["external_optimizer"]["optimizer"], "cvxpy")
        self.assertIn(external_probe.data["external_optimizer"]["status"], {"solved", "unavailable", "failed"})
        self.assertFalse(external_probe.data["automation_allowed"])
        if external_probe.data["external_optimizer"]["status"] == "unavailable":
            self.assertEqual(external_probe.data["external_optimizer"]["diagnostics"]["reason"], "cvxpy_not_installed")
            self.assertTrue(external_probe.data["external_optimizer"]["diagnostics"]["paper_compare_continues"])
        elif external_probe.data["external_optimizer"]["status"] == "solved":
            self.assertTrue(external_probe.data["external_optimizer"]["weights"])
            self.assertTrue(any(row["optimizer"] == "cvxpy" for row in external_probe.data["comparisons"]))

        readiness_gap = self.router.dispatch(
            "POST",
            "/api/portfolio/optimizer/readiness-report",
            {"compare_result": external_probe.data},
            actor="cio",
            role="CIO",
        )
        self.assertTrue(readiness_gap.success, readiness_gap.error)
        self.assertFalse(readiness_gap.data["ready_for_production_comparison_archive"])
        self.assertFalse(readiness_gap.data["automation_allowed"])
        self.assertFalse(readiness_gap.data["live_execution_allowed"])
        self.assertIn("solver_version", readiness_gap.data["missing_requirements"])
        self.assertIn("solver_artifact_uri", readiness_gap.data["missing_requirements"])
        self.assertIn("comparison_artifact_uri", readiness_gap.data["missing_requirements"])
        self.assertIn("constraint_report_artifact_uri", readiness_gap.data["missing_requirements"])
        self.assertIn("portfolio_optimizer_readiness_archives_paper_solver_comparison", readiness_gap.data["usage_boundary"])

        readiness_ready = self.router.dispatch(
            "POST",
            "/api/portfolio/optimizer/readiness-report",
            {
                "compare_result": compare.data,
                "solver_version": "cvxpy-1.6.0",
                "solver_parameters": {"objective": "max_posterior_minus_risk", "risk_penalty": 1.0, "max_weight": 0.6},
                "artifact_uris": {
                    "solver_artifact_uri": "s3://ai-quant-evidence/portfolio/cvxpy-solver-result.json",
                    "comparison_artifact_uri": "s3://ai-quant-evidence/portfolio/optimizer-compare.json",
                    "constraint_report_artifact_uri": "s3://ai-quant-evidence/portfolio/constraint-report.json",
                    "parameter_artifact_uri": "s3://ai-quant-evidence/portfolio/solver-params.json",
                },
                "record_readiness": True,
            },
            actor="cio",
            role="CIO",
        )
        self.assertTrue(readiness_ready.success, readiness_ready.error)
        self.assertTrue(readiness_ready.data["ready_for_production_comparison_archive"])
        self.assertEqual(readiness_ready.data["missing_requirements"], [])
        self.assertEqual(readiness_ready.data["solver_version"], "cvxpy-1.6.0")
        self.assertEqual(readiness_ready.data["artifact_uris"]["solver_artifact_uri"], "s3://ai-quant-evidence/portfolio/cvxpy-solver-result.json")
        self.assertEqual(self.service.store.audit_log[-1].action, "portfolio_optimizer_readiness_report")

        forward = self.router.dispatch(
            "POST",
            "/api/portfolio/forward-report",
            {
                "proposal_id": "pfp_bl",
                "benchmark_weights": {"sec_001": 0.5, "sec_us": 0.3, "sec_h": 0.2},
                "start_date": "2025-05-01",
                "end_date": "2025-05-03",
                "max_tracking_error": 1.0,
                "min_common_dates": 1,
            },
            role="CIO",
        )
        self.assertTrue(forward.success, forward.error)
        self.assertTrue(forward.data["simulation_only"])
        self.assertFalse(forward.data["live_execution_allowed"])
        self.assertIn("active_return", forward.data)
        self.assertIn("tracking_error", forward.data)
        self.assertGreaterEqual(forward.data["aligned_date_count"], 1)
        self.assertIn("review_flags", forward.data)

    def test_hotspot_expansion_maps_industry_chain_and_company_position(self) -> None:
        theme = self.router.dispatch(
            "POST",
            "/api/macro-themes",
            {
                "theme_id": "theme_ai_terminal",
                "name": "AI terminal storage and compute",
                "trigger_type": "hotspot",
                "macro_drivers": ["AI endpoint shipment growth"],
                "source_refs": ["manual://hotspot/ai-terminal"],
                "confidence": 0.7,
            },
            role="analyst",
        )
        self.assertTrue(theme.success, theme.error)
        chain = self.router.dispatch(
            "POST",
            "/api/industry-chains",
            {
                "chain_id": "chain_electronics",
                "name": "Electronics component chain",
                "root_theme_id": "theme_ai_terminal",
                "nodes": [
                    {"node_id": "node_memory", "name": "内存条", "level": 1, "category": "memory", "keywords": ["内存", "DRAM"]},
                    {"node_id": "node_gpu", "name": "GPU", "level": 1, "category": "compute", "keywords": ["GPU", "AI"]},
                    {"node_id": "node_packaging", "name": "封装", "level": 2, "category": "packaging", "keywords": ["先进封装"]},
                ],
                "edges": [
                    {"source_node_id": "node_memory", "target_node_id": "node_packaging", "relation_type": "SUPPLIED_TO", "strength": "medium"},
                    {"source_node_id": "node_gpu", "target_node_id": "node_packaging", "relation_type": "PACKAGED_BY", "strength": "high"},
                ],
            },
            role="analyst",
        )
        self.assertTrue(chain.success, chain.error)
        position = self.router.dispatch(
            "POST",
            "/api/industry-chains/chain_electronics/companies",
            {
                "position_id": "pos_demo_gpu",
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "node_ids": ["node_gpu"],
                "role": "GPU module supplier",
                "positioning_summary": "Demo Corp is mapped to the GPU node for hotspot diffusion analysis.",
                "revenue_exposure": {"gpu_related": 0.35},
                "technology_tags": ["AI accelerator"],
                "data_quality": "partial",
            },
            role="analyst",
        )
        self.assertTrue(position.success, position.error)
        lexicon = self.router.dispatch(
            "POST",
            "/api/hotspot-lexicons",
            {
                "lexicon_id": "lex_ai_hardware",
                "name": "AI hardware",
                "terms": ["GPU", "AI accelerator"],
                "synonyms": {"GPU": ["graphics processor", "AI chip"]},
                "related_chain_nodes": [
                    {"node_id": "node_gpu", "name": "GPU", "level": 1, "category": "compute", "keywords": ["GPU", "AI"]},
                    {"node_id": "node_hbm", "name": "HBM", "level": 1, "category": "memory", "keywords": ["HBM", "高带宽内存"]},
                ],
                "default_data_slots": ["revenue_exposure", "profit_exposure", "capacity"],
                "source_refs": ["manual://lexicon/ai-hardware"],
            },
            role="analyst",
        )
        self.assertTrue(lexicon.success, lexicon.error)
        listed_lexicons = self.router.dispatch("GET", "/api/hotspot-lexicons", {"q": "AI chip"}, role="analyst")
        self.assertTrue(listed_lexicons.success, listed_lexicons.error)
        self.assertEqual(listed_lexicons.data["count"], 1)
        self.service.ingest_document(
            {
                "document_id": "doc_gpu_hotspot",
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "source_id": "src_sec",
                "source_type": "regulatory",
                "document_type": "8-K",
                "source_uri": "https://example.invalid/gpu-hotspot",
                "title": "GPU capacity update",
                "body": "GPU accelerator demand increased and capacity expansion is disclosed in this public filing.",
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
        self.service.register_source(
            {
                "source_id": "local_research_reports",
                "source_type": "local_reference",
                "allowed_document_types": ["research"],
                "usage_scope": "local_reference_citation_tracking_only",
                "rights_tag": {
                    "license_class": "local_research_reference",
                    "training_allowed": False,
                    "redistribution_allowed": False,
                    "display_use": "restricted",
                    "non_display_use": "restricted",
                    "derived_data_use": "restricted",
                },
            },
            actor="risk",
        )
        research_doc = self.service.ingest_document(
            {
                "document_id": "doc_gpu_research_opinion",
                "issuer_id": "issuer_001",
                "security_id": "",
                "source_id": "local_research_reports",
                "source_type": "local_reference",
                "document_type": "research",
                "source_uri": "research-report://rr_gpu_demo",
                "title": "GPU AI supply chain research note",
                "body": "Local research opinion says GPU demand is improving, but this is not a public fact source.",
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
        self.service.store.evidence["evi_gpu_research_opinion"] = services_module.Evidence(
            evidence_id="evi_gpu_research_opinion",
            document_id=research_doc.document_id,
            section="research_report_citation",
            page_no=1,
            bbox="research_report://doc_gpu_research_opinion;chunk=0",
            span_text="Local research opinion says GPU demand is improving.",
            canonical_text="Local research opinion says GPU demand is improving.",
            confidence=0.72,
        )

        expanded = self.router.dispatch(
            "POST",
            "/api/hotspots/expand",
            {"query": "GPU", "seed_chain_id": "chain_electronics", "max_depth": 2, "include_restricted": True},
            role="analyst",
        )
        self.assertTrue(expanded.success, expanded.error)
        self.assertFalse(expanded.data["automation_allowed"])
        self.assertEqual(expanded.data["matched_lexicons"][0]["lexicon_id"], "lex_ai_hardware")
        self.assertEqual(expanded.data["company_positions"][0]["issuer_id"], "issuer_001")
        self.assertTrue(expanded.data["retrieval_recall"]["public_facts"])
        self.assertEqual(expanded.data["ranked_candidates"]["ranker"], "local_hotspot_chain_coverage_evidence_score")
        self.assertEqual(expanded.data["ranked_candidates"]["candidate_count"], 1)
        self.assertGreater(expanded.data["ranked_candidates"]["candidates"][0]["rank_score"], 0.0)
        self.assertIn("coverage_score", expanded.data["ranked_candidates"]["candidates"][0]["score_components"])
        self.assertIn("facts", expanded.data["evidence_layers"])
        self.assertIn("opinions", expanded.data["evidence_layers"])
        self.assertIn("inferences", expanded.data["evidence_layers"])
        self.assertIn("needs_verification", expanded.data["evidence_layers"])
        self.assertTrue(expanded.data["evidence_layers"]["facts"])
        self.assertTrue(expanded.data["evidence_layers"]["inferences"])
        self.assertTrue(any(item["resource_id"] == "evi_gpu_research_opinion" for item in expanded.data["evidence_layers"]["opinions"]))
        self.assertFalse(any(item["resource_id"] == "evi_gpu_research_opinion" for item in expanded.data["evidence_layers"]["facts"]))
        self.assertTrue(expanded.data["research_tasks"])
        self.assertEqual(expanded.data["pagination"]["sections"]["chain_nodes"]["total"], 3)
        self.assertFalse(expanded.data["pagination"]["has_more"])
        paged = self.router.dispatch(
            "POST",
            "/api/hotspots/expand",
            {"query": "GPU", "seed_chain_id": "chain_electronics", "max_depth": 2, "page_size": 1},
            role="analyst",
        )
        self.assertTrue(paged.success, paged.error)
        self.assertEqual(len(paged.data["chain_nodes"]), 1)
        self.assertTrue(paged.data["pagination"]["has_more"])
        self.assertEqual(paged.data["pagination"]["next_page_token"], "1")
        self.assertEqual(paged.data["pagination"]["sections"]["research_tasks"]["total"], len(expanded.data["research_tasks"]))
        next_page = self.router.dispatch(
            "POST",
            "/api/hotspots/expand",
            {"query": "GPU", "seed_chain_id": "chain_electronics", "max_depth": 2, "page_size": 1, "page_token": paged.data["pagination"]["next_page_token"]},
            role="analyst",
        )
        self.assertTrue(next_page.success, next_page.error)
        self.assertEqual(next_page.data["pagination"]["page_token"], "1")
        self.assertEqual(len(next_page.data["chain_nodes"]), 1)
        graph = self.router.dispatch("GET", "/api/graph/query", {"chain_id": "chain_electronics"}, role="analyst")
        self.assertTrue(graph.success, graph.error)
        self.assertTrue(graph.data["macro_themes"])
        self.assertTrue(graph.data["chain_nodes"])
        self.assertIn("POSITION_IN_CHAIN_NODE", {edge["type"] for edge in graph.data["edges"]})
        listed_themes = self.router.dispatch("GET", "/api/macro-themes", {"q": "terminal"}, role="analyst")
        self.assertTrue(listed_themes.success, listed_themes.error)
        self.assertEqual(listed_themes.data["count"], 1)
        listed_chains = self.router.dispatch("GET", "/api/industry-chains", {"root_theme_id": "theme_ai_terminal"}, role="analyst")
        self.assertTrue(listed_chains.success, listed_chains.error)
        self.assertEqual(listed_chains.data["count"], 1)
        listed_positions = self.router.dispatch("GET", "/api/company-positions", {"chain_id": "chain_electronics"}, role="analyst")
        self.assertTrue(listed_positions.success, listed_positions.error)
        self.assertEqual(listed_positions.data["count"], 1)
        schema = self.router.dispatch("GET", "/api/company-positions/schema", {}, role="analyst")
        self.assertTrue(schema.success, schema.error)
        self.assertEqual(schema.data["schema_id"], "company-position-v1")
        self.assertIn("revenue_exposure", schema.data["required_data_slots"])
        self.assertIn("verified", schema.data["data_quality_values"])
        coverage = self.router.dispatch(
            "GET",
            "/api/company-positions/coverage-report",
            {"chain_id": "chain_electronics"},
            role="analyst",
        )
        self.assertTrue(coverage.success, coverage.error)
        self.assertEqual(coverage.data["count"], 1)
        self.assertLess(coverage.data["coverage"]["slot_coverage"], 1.0)
        self.assertEqual(coverage.data["coverage"]["evidence_coverage"], 0.0)
        self.assertTrue(coverage.data["issues"])
        self.assertTrue(coverage.data["research_tasks"])
        queued = self.router.dispatch(
            "POST",
            "/api/research/tasks/from-hotspot",
            {"query": "GPU", "seed_chain_id": "chain_electronics", "max_depth": 2, "page_size": 1},
            role="analyst",
        )
        self.assertTrue(queued.success, queued.error)
        self.assertEqual(queued.data["created_count"], len(expanded.data["research_tasks"]))
        self.assertEqual(queued.data["usage_boundary"], "research_task_queue_for_public_analysis_and_simulated_feedback_only")
        open_tasks = self.router.dispatch("GET", "/api/research/tasks", {"chain_id": "chain_electronics", "status": "open"}, role="analyst")
        self.assertTrue(open_tasks.success, open_tasks.error)
        self.assertEqual(open_tasks.data["count"], queued.data["created_count"])
        backfill_tasks = [task for task in open_tasks.data["tasks"] if task["task_type"] == "company_position_backfill"]
        self.assertTrue(backfill_tasks)
        self.assertEqual(backfill_tasks[0]["position_id"], "pos_demo_gpu")
        task_graph = self.router.dispatch("GET", "/api/graph/query", {"chain_id": "chain_electronics"}, role="analyst")
        self.assertTrue(task_graph.success, task_graph.error)
        self.assertEqual(len(task_graph.data["research_tasks"]), open_tasks.data["count"])
        self.assertIn("CHAIN_HAS_RESEARCH_TASK", {edge["type"] for edge in task_graph.data["edges"]})
        self.assertIn("TASK_FOR_COMPANY_POSITION", {edge["type"] for edge in task_graph.data["edges"]})
        repeat_queue = self.router.dispatch(
            "POST",
            "/api/research/tasks/from-hotspot",
            {"query": "GPU", "seed_chain_id": "chain_electronics", "max_depth": 2},
            role="analyst",
        )
        self.assertTrue(repeat_queue.success, repeat_queue.error)
        self.assertEqual(repeat_queue.data["created_count"], 0)
        self.assertEqual(repeat_queue.data["existing_count"], open_tasks.data["count"])
        batch_queue = self.router.dispatch(
            "POST",
            "/api/research/tasks/from-hotspot/batch",
            {"queries": ["GPU", "AI chip"], "seed_chain_id": "chain_electronics", "max_depth": 2, "page_size": 1},
            role="analyst",
        )
        self.assertTrue(batch_queue.success, batch_queue.error)
        self.assertFalse(batch_queue.data["automation_allowed"])
        self.assertEqual(batch_queue.data["query_count"], 2)
        self.assertEqual(batch_queue.data["created_count"], 0)
        self.assertEqual(batch_queue.data["existing_count"], open_tasks.data["count"] * 2)
        self.assertEqual(batch_queue.data["source_research_task_count"], len(expanded.data["research_tasks"]) * 2)
        updated_task = self.router.dispatch(
            "POST",
            f"/api/research/tasks/{backfill_tasks[0]['task_id']}/status",
            {"status": "in_progress", "assignee": "analyst_001"},
            role="analyst",
        )
        self.assertTrue(updated_task.success, updated_task.error)
        self.assertEqual(updated_task.data["status"], "in_progress")
        self.assertEqual(updated_task.data["assignee"], "analyst_001")
        task_search = self.router.dispatch("GET", "/api/search", {"q": "missing evidence GPU", "issuer_id": "issuer_001"}, role="analyst")
        self.assertTrue(task_search.success, task_search.error)
        self.assertTrue(any(item["resource_type"] == "research_task" for item in task_search.data["results"]))

    def test_industry_chain_analysis_summarizes_process_companies_and_segment_share(self) -> None:
        self.service.register_issuer(
            {
                "issuer_id": "issuer_chain_supplier",
                "legal_name": "Chain Supplier A",
                "market": ["A"],
                "country": "CN",
            },
            actor="platform",
        )
        self.service.register_issuer(
            {
                "issuer_id": "issuer_chain_assembler",
                "legal_name": "Chain Assembler B",
                "market": ["A"],
                "country": "CN",
                "fundamentals": {
                    "financial_summary": {
                        "total_operating_income": 800.0,
                        "parent_net_profit": 160.0,
                        "currency": "CNY",
                        "period": "2025",
                    }
                },
            },
            actor="platform",
        )
        chain = self.router.dispatch(
            "POST",
            "/api/industry-chains",
            {
                "chain_id": "chain_process_share",
                "name": "Battery materials to pack chain",
                "nodes": [
                    {
                        "node_id": "node_materials",
                        "name": "正极材料",
                        "level": 1,
                        "flow_order": 1,
                        "process_stage": "upstream",
                        "process_step": "precursor calcination and cathode material processing",
                        "process_description": "Convert precursor, lithium salt, and additives into cathode material.",
                        "inputs": ["precursor", "lithium salt"],
                        "outputs": ["cathode material"],
                        "segment_economics": {"revenue_pool": 1000.0, "profit_pool": 200.0, "currency": "CNY", "period": "2025"},
                    },
                    {
                        "node_id": "node_pack",
                        "name": "电池包组装",
                        "level": 2,
                        "flow_order": 2,
                        "process_stage": "midstream",
                        "process_step": "cell grouping and battery pack integration",
                        "process_description": "Integrate cells, BMS, cooling, and structure into finished battery packs.",
                        "inputs": ["cells", "BMS", "thermal parts"],
                        "outputs": ["battery pack"],
                        "segment_economics": {"revenue_pool": 2000.0, "profit_pool": 400.0, "currency": "CNY", "period": "2025"},
                    },
                ],
                "edges": [
                    {"source_node_id": "node_materials", "target_node_id": "node_pack", "relation_type": "SUPPLIED_TO", "strength": "high"}
                ],
            },
            role="analyst",
        )
        self.assertTrue(chain.success, chain.error)
        downstream_chain = self.router.dispatch(
            "POST",
            "/api/industry-chains",
            {
                "chain_id": "chain_process_share_downstream",
                "name": "Battery charging and service chain",
                "nodes": [
                    {
                        "node_id": "node_charging",
                        "name": "充换电服务",
                        "level": 3,
                        "flow_order": 3,
                        "process_stage": "downstream",
                        "process_step": "charging network operation and after-sales service",
                        "process_description": "Operate charging stations, swap assets, and after-sales battery service touchpoints.",
                        "inputs": ["battery pack", "charging equipment"],
                        "outputs": ["charging service"],
                        "segment_economics": {"revenue_pool": 500.0, "profit_pool": 80.0, "currency": "CNY", "period": "2025"},
                    }
                ],
                "edges": [],
            },
            role="analyst",
        )
        self.assertTrue(downstream_chain.success, downstream_chain.error)
        supplier = self.router.dispatch(
            "POST",
            "/api/industry-chains/chain_process_share/companies",
            {
                "position_id": "pos_chain_supplier",
                "issuer_id": "issuer_chain_supplier",
                "node_ids": ["node_materials"],
                "role": "cathode material supplier",
                "positioning_summary": "Supplier A participates in the cathode material processing step.",
                "revenue_exposure": {"revenue_amount": 120.0},
                "profit_exposure": {"profit_amount": 30.0},
                "customers": ["cell makers"],
                "suppliers": ["lithium salt vendors"],
                "valuation_metrics": {"pe_ttm": 18.0},
                "data_quality": "verified",
            },
            role="analyst",
        )
        self.assertTrue(supplier.success, supplier.error)
        assembler = self.router.dispatch(
            "POST",
            "/api/industry-chains/chain_process_share/companies",
            {
                "position_id": "pos_chain_assembler",
                "issuer_id": "issuer_chain_assembler",
                "node_ids": ["node_pack"],
                "role": "battery pack integrator",
                "positioning_summary": "Assembler B maps to pack integration; exposure ratios derive segment amounts from issuer fundamentals.",
                "revenue_exposure": {"pack_related": 0.25},
                "profit_exposure": {"pack_related": 0.5},
                "customers": ["OEMs"],
                "suppliers": ["cell makers"],
                "valuation_metrics": {"pe_ttm": 22.0},
                "data_quality": "partial",
            },
            role="analyst",
        )
        self.assertTrue(assembler.success, assembler.error)

        analysis = self.router.dispatch("GET", "/api/industry-chains/chain_process_share/analysis", {}, role="analyst")
        self.assertTrue(analysis.success, analysis.error)
        self.assertFalse(analysis.data["automation_allowed"])
        self.assertEqual([step["node_id"] for step in analysis.data["process_flow"]], ["node_materials", "node_pack"])
        self.assertEqual(analysis.data["process_flow"][1]["upstream_node_ids"], ["node_materials"])
        material_segment = next(item for item in analysis.data["segments"] if item["node_id"] == "node_materials")
        pack_segment = next(item for item in analysis.data["segments"] if item["node_id"] == "node_pack")
        self.assertEqual(material_segment["companies"][0]["issuer_name"], "Chain Supplier A")
        self.assertAlmostEqual(material_segment["companies"][0]["revenue_share_of_segment"], 0.12)
        self.assertAlmostEqual(material_segment["companies"][0]["profit_share_of_segment"], 0.15)
        self.assertAlmostEqual(pack_segment["companies"][0]["revenue_amount"], 200.0)
        self.assertAlmostEqual(pack_segment["companies"][0]["profit_amount"], 80.0)
        self.assertAlmostEqual(pack_segment["companies"][0]["revenue_share_of_segment"], 0.1)
        self.assertIn("issuer financial revenue", pack_segment["companies"][0]["revenue_calculation_basis"])
        self.assertEqual(analysis.data["coverage"]["positions_with_revenue_share"], 2)
        self.assertEqual(analysis.data["coverage"]["positions_with_profit_share"], 2)
        self.assertFalse(analysis.data["research_tasks"])

        panorama = self.router.dispatch("GET", "/api/industry-chains/panorama", {"q": "battery"}, role="analyst")
        self.assertTrue(panorama.success, panorama.error)
        self.assertFalse(panorama.data["automation_allowed"])
        self.assertEqual(panorama.data["coverage"]["chain_count"], 2)
        self.assertEqual(panorama.data["coverage"]["process_step_count"], 3)
        self.assertEqual(panorama.data["coverage"]["positions_with_revenue_share"], 2)
        self.assertEqual({stage["process_stage"] for stage in panorama.data["panorama_stages"]}, {"upstream", "midstream", "downstream"})
        self.assertTrue(any(item["issuer_id"] == "issuer_chain_assembler" for item in panorama.data["company_directory"]))
        self.assertTrue(any(task["type"] == "chain_node_company_mapping" and task["node_id"] == "node_charging" for task in panorama.data["research_tasks"]))

    def test_ai_compute_template_candidate_review_publish_and_panorama(self) -> None:
        self.router.dispatch(
            "POST",
            "/api/macro-themes",
            {
                "theme_id": "theme_ai_compute_cloud",
                "name": "AI 算力与云软件",
                "description": "Full AI compute chain from semiconductor inputs to cloud, software, and edge devices.",
                "trigger_type": "hotspot",
                "macro_drivers": ["AI training and inference demand", "cloud capex", "edge AI upgrade"],
                "source_refs": ["manual://theme/ai-compute"],
            },
            role="analyst",
        )
        for issuer_id, security_id, ticker, legal_name in [
            ("issuer_nvda", "security_nvda_us", "NVDA", "NVIDIA Corporation"),
            ("issuer_msft", "security_msft_us", "MSFT", "Microsoft Corporation"),
            ("issuer_aapl", "security_aapl_us", "AAPL", "Apple Inc."),
        ]:
            self.service.register_issuer(
                {
                    "issuer_id": issuer_id,
                    "legal_name": legal_name,
                    "aliases": [ticker],
                    "market": ["U"],
                    "country": "US",
                    "fundamentals": {"total_revenue": 1000.0, "net_profit": 200.0},
                },
                actor="platform",
            )
            self.service.register_security(
                {
                    "security_id": security_id,
                    "issuer_id": issuer_id,
                    "ticker": ticker,
                    "exchange": "NASDAQ",
                    "currency": "USD",
                    "market": "U",
                },
                actor="platform",
            )

        document = self.service.ingest_document(
            {
                "document_id": "doc_ai_compute_template_official",
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "source_id": "src_sec",
                "source_type": "regulatory",
                "document_type": "10-K",
                "source_uri": "https://example.invalid/ai-compute-official-10k",
                "title": "AI compute official disclosure",
                "body": "Official filing describes AI accelerator design, advanced packaging, HBM, AI servers, cloud infrastructure, enterprise AI software, and edge AI devices.",
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
        evidence_id = self.service.extract_evidence(document.document_id, actor="analyst")[0].evidence_id

        candidate = self.router.dispatch(
            "POST",
            "/api/industry-chains/template-candidates",
            {
                "template_id": "ai-compute-chain-v1",
                "official_evidence_ids": [evidence_id],
                "root_theme_id": "theme_ai_compute_cloud",
            },
            role="analyst",
        )
        self.assertTrue(candidate.success, candidate.error)
        self.assertEqual(candidate.data["candidate"]["candidate_id"], "ai-compute-chain-v1")
        self.assertTrue(candidate.data["coverage"]["publishable"])
        self.assertEqual(candidate.data["coverage"]["level_counts"]["L1"], 4)
        self.assertGreaterEqual(candidate.data["coverage"]["level_counts"]["L2"], 10)
        self.assertGreaterEqual(candidate.data["coverage"]["level_counts"]["L3"], 8)
        self.assertTrue(any(task["type"] == "chain_segment_economics_backfill" for task in candidate.data["research_tasks"]))
        listed_candidates = self.router.dispatch("GET", "/api/industry-chains/template-candidates", {"q": "AI", "status": "draft"}, role="analyst")
        self.assertTrue(listed_candidates.success, listed_candidates.error)
        self.assertEqual(listed_candidates.data["count"], 1)
        fetched_candidate = self.router.dispatch("GET", "/api/industry-chains/template-candidates/ai-compute-chain-v1", {}, role="analyst")
        self.assertTrue(fetched_candidate.success, fetched_candidate.error)
        self.assertEqual(fetched_candidate.data["candidate"]["target_chain_id"], "chain_ai_compute_cloud")

        submitted = self.router.dispatch("POST", "/api/industry-chains/template-candidates/ai-compute-chain-v1/submit-review", {}, role="analyst")
        self.assertTrue(submitted.success, submitted.error)
        self.assertEqual(submitted.data["candidate"]["status"], "needs_review")
        reviewed = self.router.dispatch(
            "POST",
            "/api/industry-chains/template-candidates/ai-compute-chain-v1/review",
            {"decision": "approved", "notes": "official evidence covers the process template; economics gaps remain tasks"},
            role="risk_compliance",
        )
        self.assertTrue(reviewed.success, reviewed.error)
        self.assertEqual(reviewed.data["candidate"]["status"], "approved")
        published = self.router.dispatch(
            "POST",
            "/api/industry-chains/template-candidates/ai-compute-chain-v1/publish",
            {},
            role="risk_compliance",
        )
        self.assertTrue(published.success, published.error)
        self.assertEqual(published.data["chain"]["chain_id"], "chain_ai_compute_cloud")
        self.assertEqual(published.data["chain"]["template_status"], "published")
        self.assertEqual(published.data["chain"]["taxonomy_version"], "ai-compute-chain-v1")
        self.assertTrue(any(task["task_type"] == "chain_segment_economics_backfill" for task in published.data["created_research_tasks"]))
        self.assertEqual({item["issuer_id"] for item in published.data["created_company_positions"]}, {"issuer_nvda", "issuer_msft", "issuer_aapl"})

        panorama = self.router.dispatch("GET", "/api/industry-chains/panorama", {"q": "AI"}, role="analyst")
        self.assertTrue(panorama.success, panorama.error)
        self.assertFalse(panorama.data["automation_allowed"])
        self.assertEqual(panorama.data["coverage"]["chain_count"], 1)
        self.assertGreaterEqual(panorama.data["coverage"]["process_step_count"], 20)
        self.assertTrue({"upstream", "midstream", "downstream", "supporting"}.issubset({stage["process_stage"] for stage in panorama.data["panorama_stages"]}))
        self.assertTrue({"issuer_nvda", "issuer_msft", "issuer_aapl"}.issubset({item["issuer_id"] for item in panorama.data["company_directory"]}))
        self.assertTrue(any(task["type"] == "chain_segment_economics_backfill" for task in panorama.data["research_tasks"]))
        self.assertTrue(any(task["type"] == "company_position_attribution_backfill" for task in panorama.data["research_tasks"]))
        readiness = self.router.dispatch(
            "POST",
            "/api/industry-chains/panorama/readiness-report",
            {"q": "AI", "queue_tasks": True},
            role="analyst",
        )
        self.assertTrue(readiness.success, readiness.error)
        self.assertFalse(readiness.data["automation_allowed"])
        self.assertEqual(readiness.data["coverage"]["chain_count"], 1)
        self.assertEqual(readiness.data["coverage"]["official_evidence_coverage"], 1.0)
        self.assertEqual(readiness.data["coverage"]["economic_pool_coverage"], 0.0)
        self.assertLess(readiness.data["coverage"]["readiness_score"], 1.0)
        self.assertGreater(readiness.data["coverage"]["queued_task_count"], 0)
        self.assertTrue(any(task["type"] == "chain_segment_economics_backfill" for task in readiness.data["research_tasks"]))
        self.assertTrue(any(task["type"] == "company_position_attribution_backfill" for task in readiness.data["research_tasks"]))
        self.assertTrue({"upstream", "midstream", "downstream", "supporting"}.issubset({row["process_stage"] for row in readiness.data["by_stage"]}))
        self.assertTrue(any(task_id.startswith("readiness_economics_chain_ai_compute_cloud_") for task_id in self.service.store.research_tasks))

    def test_ai_compute_template_publish_gate_requires_official_evidence(self) -> None:
        candidate = self.router.dispatch(
            "POST",
            "/api/industry-chains/template-candidates",
            {"template_id": "ai-compute-chain-v1", "root_theme_id": ""},
            role="analyst",
        )
        self.assertTrue(candidate.success, candidate.error)
        self.assertFalse(candidate.data["coverage"]["publishable"])
        self.assertGreater(candidate.data["coverage"]["blocking_issue_count"], 0)
        submitted = self.router.dispatch("POST", "/api/industry-chains/template-candidates/ai-compute-chain-v1/submit", {}, role="analyst")
        self.assertTrue(submitted.success, submitted.error)
        blocked_review = self.router.dispatch(
            "POST",
            "/api/industry-chains/template-candidates/ai-compute-chain-v1/review",
            {"decision": "approved"},
            role="risk_compliance",
        )
        self.assertFalse(blocked_review.success)
        self.assertIn("cannot be approved", blocked_review.error["message"])

    def test_ai_compute_seed_template_uses_panorama_nodes_and_segment_exposures(self) -> None:
        from scripts.seed_ahu_basic_info_industry_chain import _ai_compute_seed_template, _position_metric_exposure

        template = _ai_compute_seed_template()
        node_ids = {node["node_id"] for node in template["nodes"]}
        self.assertEqual(template["taxonomy_version"], "ai-compute-chain-v1")
        self.assertGreaterEqual(len(node_ids), 20)
        self.assertIn("gpu_die_design", node_ids)
        self.assertIn("ai_training_inference_cloud", node_ids)
        self.assertTrue(all(node["fact_layer"] == "local_profile_seed_needs_official_review" for node in template["nodes"]))
        exposure = _position_metric_exposure("chain_ai_compute_cloud", ["gpu_die_design", "accelerator_card_assembly"], "revenue", "evi_profile_pos_nvda_ai_compute")
        self.assertEqual(exposure["type"], "node_segments")
        self.assertEqual({segment["node_id"] for segment in exposure["segments"]}, {"gpu_die_design", "accelerator_card_assembly"})
        self.assertTrue(all(segment["needs_review"] for segment in exposure["segments"]))

    def test_hotspot_readiness_report_requires_layer_boundaries_tasks_and_rerank_evidence(self) -> None:
        theme = self.router.dispatch(
            "POST",
            "/api/macro-themes",
            {
                "theme_id": "theme_hotspot_readiness",
                "name": "AI accelerator diffusion",
                "description": "AI accelerator demand diffusion from endpoint compute to packaging and memory.",
                "trigger_type": "hotspot",
                "macro_drivers": ["public AI accelerator demand"],
                "source_refs": ["manual://hotspot-readiness/theme"],
                "confidence": 0.82,
            },
            role="analyst",
        )
        self.assertTrue(theme.success, theme.error)
        chain = self.router.dispatch(
            "POST",
            "/api/industry-chains",
            {
                "chain_id": "chain_hotspot_readiness",
                "name": "AI accelerator hardware chain",
                "root_theme_id": "theme_hotspot_readiness",
                "nodes": [
                    {"node_id": "node_gpu", "name": "GPU", "level": 1, "category": "compute", "keywords": ["GPU", "AI accelerator"]},
                    {"node_id": "node_packaging", "name": "Advanced packaging", "level": 2, "category": "packaging", "keywords": ["CoWoS", "advanced packaging"]},
                    {"node_id": "node_hbm", "name": "HBM", "level": 3, "category": "memory", "keywords": ["HBM", "high bandwidth memory"]},
                ],
                "edges": [
                    {"source_node_id": "node_gpu", "target_node_id": "node_packaging", "relation_type": "PACKAGED_BY", "strength": "high"},
                    {"source_node_id": "node_packaging", "target_node_id": "node_hbm", "relation_type": "USES_MEMORY", "strength": "medium"},
                ],
                "source_refs": ["manual://hotspot-readiness/chain"],
            },
            role="analyst",
        )
        self.assertTrue(chain.success, chain.error)
        self.router.dispatch(
            "POST",
            "/api/hotspot-lexicons",
            {
                "lexicon_id": "lex_hotspot_readiness",
                "name": "AI accelerator",
                "terms": ["GPU", "AI accelerator"],
                "synonyms": {"GPU": ["AI chip", "graphics processor"]},
                "related_chain_nodes": [
                    {"node_id": "node_gpu", "name": "GPU", "level": 1, "category": "compute", "keywords": ["GPU", "AI chip"]},
                    {"node_id": "node_packaging", "name": "Advanced packaging", "level": 2, "category": "packaging", "keywords": ["packaging", "CoWoS"]},
                    {"node_id": "node_hbm", "name": "HBM", "level": 3, "category": "memory", "keywords": ["HBM"]},
                ],
                "default_data_slots": ["revenue_exposure", "profit_exposure", "capacity"],
                "source_refs": ["manual://hotspot-readiness/lexicon"],
            },
            role="analyst",
        )
        document = self.service.ingest_document(
            {
                "document_id": "doc_hotspot_readiness",
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "source_id": "src_sec",
                "source_type": "regulatory",
                "document_type": "8-K",
                "source_uri": "https://example.invalid/hotspot-readiness",
                "title": "AI accelerator capacity update",
                "body": "GPU AI accelerator capacity expanded for advanced packaging and HBM demand.",
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
        evidences = self.service.extract_evidence(document.document_id, actor="analyst")
        position = self.router.dispatch(
            "POST",
            "/api/industry-chains/chain_hotspot_readiness/companies",
            {
                "position_id": "pos_hotspot_readiness",
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "node_ids": ["node_gpu"],
                "role": "AI accelerator module supplier",
                "positioning_summary": "Demo Corp maps to GPU AI accelerator demand with public filing evidence.",
                "revenue_exposure": {"ai_accelerator": 0.42},
                "profit_exposure": {"ai_accelerator": 0.31},
                "capacity": {"advanced_packaging": "expanding"},
                "technology_tags": ["GPU", "AI accelerator"],
                "evidence_ids": [evidences[0].evidence_id],
                "data_quality": "verified",
                "require_evidence_records": True,
            },
            role="analyst",
        )
        self.assertTrue(position.success, position.error)
        thesis = self.service.create_thesis(
            {
                "thesis_id": "thesis_hotspot_readiness",
                "issuer_id": "issuer_001",
                "horizon": "mid",
                "hypothesis": "GPU AI accelerator exposure can improve growth",
                "evidence_ids": [item.evidence_id for item in evidences],
                "risk_factors": ["supply constraints"],
            },
            actor="analyst",
        )
        self.service.run_scoring(
            {
                "signal_id": "sig_hotspot_readiness",
                "thesis_id": thesis.thesis_id,
                "strategy_type": "long",
                "source_model": "rules",
                "model_version": "v1",
                "rationale": "GPU AI accelerator evidence supports a research-only inference.",
            },
            actor="cio",
        )

        gap = self.router.dispatch(
            "POST",
            "/api/hotspots/readiness-report",
            {
                "query": "AI chip",
                "seed_chain_id": "chain_hotspot_readiness",
                "max_depth": 3,
                "min_rerank_top1_accuracy": 0.8,
                "min_rerank_samples": 2,
            },
            role="analyst",
        )
        self.assertTrue(gap.success, gap.error)
        self.assertFalse(gap.data["ready_for_hotspot_research_production"])
        self.assertIn("research_tasks_persisted_or_reviewed", gap.data["missing_requirements"])
        self.assertIn("llm_rerank_eval_samples", gap.data["missing_requirements"])
        self.assertIn("llm_rerank_eval_artifact_uri", gap.data["missing_requirements"])
        self.assertFalse(gap.data["automation_allowed"])
        self.assertGreaterEqual(gap.data["graph_summary"]["max_chain_depth"], 3)
        self.assertEqual(gap.data["coverage_report"]["coverage"]["evidence_coverage"], 1.0)
        self.assertTrue(gap.data["boundary_summary"]["separated_layers"])

        queued = self.router.dispatch(
            "POST",
            "/api/research/tasks/from-hotspot",
            {"query": "AI chip", "seed_chain_id": "chain_hotspot_readiness", "max_depth": 3},
            role="analyst",
        )
        self.assertTrue(queued.success, queued.error)
        self.assertGreaterEqual(queued.data["created_count"], 1)
        ready = self.router.dispatch(
            "POST",
            "/api/hotspots/readiness-report",
            {
                "query": "AI chip",
                "seed_chain_id": "chain_hotspot_readiness",
                "max_depth": 3,
                "min_rerank_top1_accuracy": 0.8,
                "min_rerank_samples": 2,
                "rerank_evaluation": {
                    "benchmark_id": "hotspot_rerank_prod_eval",
                    "valid_samples": 120,
                    "top1_accuracy": 0.91,
                    "coverage_at_k": 0.97,
                    "mrr": 0.94,
                    "fallback_rate": 0.08,
                    "parse_error_rate": 0.0,
                },
                "artifact_uris": {
                    "llm_rerank_eval_uri": "artifact://prod/hotspot/rerank-eval.json",
                    "hotspot_gold_refs_uri": "artifact://prod/hotspot/gold-refs.jsonl",
                    "company_position_review_uri": "artifact://prod/hotspot/company-position-review.json",
                    "chain_taxonomy_review_uri": "artifact://prod/hotspot/chain-taxonomy-review.json",
                },
                "record_readiness": True,
            },
            role="analyst",
            actor="research_lead",
        )
        self.assertTrue(ready.success, ready.error)
        self.assertTrue(ready.data["ready_for_hotspot_research_production"])
        self.assertEqual(ready.data["missing_requirements"], [])
        self.assertEqual(ready.data["layer_summary"]["present_layer_count"], 4)
        self.assertEqual(ready.data["research_queue"]["source_research_task_count"], queued.data["source_research_task_count"])
        self.assertEqual(ready.data["rerank_evaluation"]["valid_samples"], 120)
        self.assertEqual(ready.data["graph_summary"]["edge_metadata_coverage"], 1.0)
        self.assertIn("hotspot_readiness_report_validates_chain_depth", ready.data["usage_boundary"])
        self.assertEqual(self.service.store.audit_log[-1].action, "hotspot_readiness_report")

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

    def test_citation_boundary_readiness_report_requires_reviews_and_policy_artifacts(self) -> None:
        self.service.seed_default_sources(actor="risk")
        public_doc = self.service.ingest_document(
            {
                "document_id": "doc_citation_public",
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "source_id": "company_public_webcast",
                "source_type": "company_ir",
                "document_type": "webcast",
                "source_uri": "https://ir.example.invalid/citation-webcast",
                "body": "Public webcast revenue growth and margin outlook.",
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
        evidence = self.service.extract_evidence(public_doc.document_id, actor="analyst")
        answer = self.service.create_research_answer(
            {
                "answer_id": "ans_citation_boundary",
                "question": "What did the public webcast say about revenue growth?",
                "issuer_id": "issuer_001",
                "evidence_ids": [item.evidence_id for item in evidence],
                "human_review_status": "approved",
                "reviewer": "analyst_lead",
            },
            actor="analyst",
        )
        self.assertEqual(answer.human_review_status, "approved")
        manual_reference = self.router.dispatch(
            "POST",
            "/api/research/manual-references",
            {
                "document_id": "doc_citation_private_meta",
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "document_type": "private_meeting_note",
                "title": "Private meeting note metadata",
                "source_uri": "private://citation/private-meeting",
                "notes": "Metadata only for boundary review.",
            },
            actor="analyst",
            role="analyst",
        )
        self.assertTrue(manual_reference.success, manual_reference.error)

        gap = self.router.dispatch(
            "POST",
            "/api/research/citation-boundary/readiness-report",
            {"issuer_id": "issuer_001"},
            actor="risk",
            role="risk_compliance",
        )
        self.assertTrue(gap.success, gap.error)
        self.assertFalse(gap.data["ready_for_citation_boundary_production"])
        self.assertIn("source_review_coverage", gap.data["missing_requirements"])
        self.assertIn("citation_policy_artifact_uri", gap.data["missing_requirements"])
        self.assertIn("manual_reference_review_artifact_uri", gap.data["missing_requirements"])
        self.assertIn("research_report_governance_artifact_uri", gap.data["missing_requirements"])
        self.assertFalse(gap.data["automation_allowed"])
        self.assertEqual(gap.data["manual_reference_summary"]["manual_reference_body_count"], 0)
        self.assertEqual(gap.data["research_answers"]["source_link_rate"], 1.0)

        for source_id, status, publicness, usage_scope in [
            ("company_public_webcast", "approved", "confirmed_public_or_local", "within_boundary"),
            ("manual_reference_transcripts", "conditional", "manual_reference_only", "manual_reference_only"),
            ("local_research_reports", "conditional", "confirmed_public_or_local", "manual_reference_only"),
        ]:
            reviewed = self.router.dispatch(
                "POST",
                f"/api/governance/sources/{source_id}/reviews",
                {
                    "review_id": f"srrev_{source_id}_citation",
                    "reviewed_at": "2026-05-01T00:00:00+00:00",
                    "status": status,
                    "publicness_status": publicness,
                    "tos_status": "reviewed",
                    "robots_status": "reviewed_or_not_applicable",
                    "usage_scope_status": usage_scope,
                    "next_review_due_at": "2026-08-01T00:00:00+00:00",
                },
                actor="risk",
                role="risk_compliance",
            )
            self.assertTrue(reviewed.success, reviewed.error)

        ready = self.router.dispatch(
            "POST",
            "/api/research/citation-boundary/readiness-report",
            {
                "issuer_id": "issuer_001",
                "artifact_uris": {
                    "citation_policy_uri": "artifact://prod/research/citation-policy.md",
                    "source_review_uri": "artifact://prod/research/source-review.json",
                    "manual_reference_review_uri": "artifact://prod/research/manual-boundary-review.json",
                    "research_report_governance_uri": "artifact://prod/research/report-governance.json",
                },
                "record_readiness": True,
            },
            actor="risk_lead",
            role="risk_compliance",
        )
        self.assertTrue(ready.success, ready.error)
        self.assertTrue(ready.data["ready_for_citation_boundary_production"])
        self.assertEqual(ready.data["missing_requirements"], [])
        self.assertEqual(ready.data["source_summary"]["review_coverage"], 1.0)
        self.assertEqual(ready.data["red_zone_training_records"], 0)
        self.assertIn("citation_boundary_readiness_report_keeps_transcripts", ready.data["usage_boundary"])
        self.assertEqual(self.service.store.audit_log[-1].action, "citation_boundary_readiness_report")

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

    def test_research_report_incremental_schedule_dry_run_budget_and_execute(self) -> None:
        with TemporaryDirectory() as temp_dir:
            report_dir = Path(temp_dir) / "Morgan" / "2026" / "05"
            report_dir.mkdir(parents=True)
            small_path = report_dir / "A small text report.txt"
            small_path.write_text("Revenue catalyst and margin expansion view. " * 12, encoding="utf-8")
            large_path = report_dir / "B deferred large report.txt"
            large_path.write_text("large local reference report\n" * 200, encoding="utf-8")

            dry_run = self.router.dispatch(
                "POST",
                "/api/research-reports/incremental-schedule",
                {
                    "root_path": temp_dir,
                    "extensions": [".txt"],
                    "batch_size": 1,
                    "ocr_budget_mb": 0.001,
                    "dry_run": True,
                },
                actor="data",
                role="data_engineer",
            )
            self.assertTrue(dry_run.success, dry_run.error)
            self.assertTrue(dry_run.data["dry_run"])
            self.assertFalse(dry_run.data["execute"])
            self.assertEqual(dry_run.data["new_count"], 2)
            self.assertEqual(dry_run.data["deferred_count"], 1)
            self.assertEqual(dry_run.data["batch_count"], 1)
            self.assertEqual(dry_run.data["schedule_plan"][0]["batch_size"], 1)
            self.assertEqual(dry_run.data["usage_boundary"], "local_reference_only_not_training_or_fact_source")
            self.assertFalse(self.service.store.research_reports)
            deferred = [item for item in dry_run.data["candidates"] if item["batch"] == "deferred"]
            self.assertEqual(deferred[0]["status"], "ocr_budget_exceeded")
            self.assertEqual(deferred[0]["file_name"], large_path.name)

            executed = self.router.dispatch(
                "POST",
                "/api/research-reports/incremental-schedule",
                {
                    "root_path": temp_dir,
                    "extensions": [".txt"],
                    "batch_size": 1,
                    "ocr_budget_mb": 0.001,
                    "dry_run": False,
                    "execute": True,
                    "citation_char_limit": 180,
                },
                actor="data",
                role="data_engineer",
            )
            self.assertTrue(executed.success, executed.error)
            self.assertFalse(executed.data["dry_run"])
            self.assertTrue(executed.data["execute"])
            self.assertEqual(executed.data["deferred_count"], 1)
            self.assertEqual(len(executed.data["executed_results"]), 1)
            self.assertEqual(executed.data["executed_results"][0]["status"], "text_indexed")
            self.assertEqual(len(self.service.store.research_reports), 1)
            report = next(iter(self.service.store.research_reports.values()))
            self.assertEqual(report.file_name, small_path.name)
            self.assertEqual(report.status, "text_indexed")
            self.assertFalse(report.rights_tag.training_allowed)
            self.assertEqual(report.rights_tag.display_use, "restricted")

    def test_research_report_inbox_script_uses_local_incremental_schedule(self) -> None:
        from scripts.research_report_inbox_ingest import run_inbox_ingest

        with TemporaryDirectory() as temp_dir:
            inbox = Path(temp_dir) / "inbox" / "Morgan" / "2026" / "05"
            inbox.mkdir(parents=True)
            report_path = inbox / "New local note.txt"
            report_path.write_text("AI capex cycle and margin expansion local reference. " * 10, encoding="utf-8")
            output = Path(temp_dir) / "artifact.json"

            class LocalClient:
                def __init__(self, _base_url: str, *, timeout: float = 120.0) -> None:
                    self.timeout = timeout

                def request(self, method: str, path: str, body: dict | None = None) -> dict:
                    response = self_router.dispatch(method, path, body or {}, actor="inbox_test", role="data_engineer")
                    if not response.success:
                        raise RuntimeError(str(response.error))
                    return response.data

            self_router = self.router
            import scripts.research_report_inbox_ingest as inbox_script

            original_client = inbox_script.ApiClient
            try:
                inbox_script.ApiClient = LocalClient
                dry_summary = run_inbox_ingest(
                base_url="local",
                root_path=str(Path(temp_dir) / "inbox"),
                api_root_path=str(Path(temp_dir) / "inbox"),
                output=output,
                    extensions=[".txt"],
                    batch_size=1,
                    scan_limit=10,
                    ocr_budget_mb=10,
                    citation_char_limit=200,
                    execute=False,
                    dry_run=True,
                    timeout=1,
                )
                self.assertEqual(dry_summary["new_count"], 1)
                self.assertEqual(dry_summary["executed_count"], 0)
                self.assertFalse(self.service.store.research_reports)

                exec_summary = run_inbox_ingest(
                base_url="local",
                root_path=str(Path(temp_dir) / "inbox"),
                api_root_path=str(Path(temp_dir) / "inbox"),
                output=output,
                    extensions=[".txt"],
                    batch_size=1,
                    scan_limit=10,
                    ocr_budget_mb=10,
                    citation_char_limit=200,
                    execute=True,
                    dry_run=False,
                    timeout=1,
                )
            finally:
                inbox_script.ApiClient = original_client

            self.assertEqual(exec_summary["status"], "passed")
            self.assertEqual(exec_summary["executed_count"], 1)
            self.assertEqual(exec_summary["failed_count"], 0)
            self.assertIn("no_external_download", exec_summary["usage_boundary"])
            report = next(iter(self.service.store.research_reports.values()))
            self.assertEqual(report.file_name, report_path.name)
            self.assertEqual(report.status, "text_indexed")
            self.assertTrue(any(item.section == "research_report_citation" for item in self.service.store.evidence.values()))

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

    def test_research_report_structure_endpoint_writes_viewpoints_and_forecasts(self) -> None:
        with TemporaryDirectory() as temp_dir:
            report_dir = Path(temp_dir) / "CICC" / "2026" / "06"
            report_dir.mkdir(parents=True)
            report_path = report_dir / "Demo Corp AI芯片公司深度_买入_目标价_盈利预测.txt"
            report_path.write_text(
                "分析师：张三、李四\n"
                "评级：买入，12个月目标价 18.5 元，当前价 10.0 元。\n"
                "核心假设：AI订单落地；毛利率改善。\n"
                "盈利预测：2026 EPS 1.20 元。\n"
                "催化剂：新品放量；政策支持。\n"
                "风险：需求不及预期；竞争加剧。\n"
                "估值方法：PE 25x。\n",
                encoding="utf-8",
            )
            scanned = self.router.dispatch(
                "POST",
                "/api/research-reports/scan",
                {"root_path": temp_dir, "extensions": [".txt"], "limit": 5},
                actor="data",
                role="data_engineer",
            )
            self.assertTrue(scanned.success, scanned.error)
            report = scanned.data["reports"][0]
            ingested = self.router.dispatch(
                "POST",
                f"/api/research-reports/{report['report_id']}/ingest",
                {
                    "issuer_id": "issuer_001",
                    "security_id": "sec_001",
                    "document_id": "doc_structured_research",
                    "industry": "semiconductor",
                },
                actor="analyst",
                role="analyst",
            )
            self.assertTrue(ingested.success, ingested.error)
            extracted = self.router.dispatch(
                "POST",
                f"/api/research-reports/{report['report_id']}/extract",
                {"citation_char_limit": 800},
                actor="analyst",
                role="analyst",
            )
            self.assertTrue(extracted.success, extracted.error)

            structured = self.router.dispatch(
                "POST",
                "/api/research-reports/structure",
                {"report_ids": [report["report_id"]], "execute": True},
                actor="analyst",
                role="analyst",
            )
            self.assertTrue(structured.success, structured.error)
            self.assertEqual(structured.data["structured_count"], 1)
            self.assertEqual(structured.data["viewpoint_count"], 1)
            self.assertGreaterEqual(structured.data["forecast_count"], 2)
            self.assertEqual(structured.data["usage_boundary"], "research_reports_are_viewpoint_signal_only_not_fact_source_or_training_data")
            row = structured.data["reports"][0]
            self.assertEqual(row["report_type"], "update")
            self.assertEqual(row["rating"], "buy")
            self.assertEqual(row["target_price"], 18.5)
            self.assertEqual(row["target_price_currency"], "CNY")
            self.assertEqual(row["issuer_id"], "issuer_001")
            self.assertEqual(row["security_id"], "sec_001")
            self.assertEqual(row["usage_boundary"], "opinion_only_not_fact_source")

            listed_reports = self.router.dispatch(
                "GET",
                "/api/research-reports/structured",
                {"issuer_id": "issuer_001"},
                role="analyst",
            )
            self.assertTrue(listed_reports.success, listed_reports.error)
            self.assertEqual(listed_reports.data["count"], 1)
            structured_report = listed_reports.data["reports"][0]
            self.assertEqual(structured_report["rights_boundary"], "opinion_only_not_fact_source")
            self.assertEqual(structured_report["analyst_names"], ["张三", "李四"])

            viewpoints = self.router.dispatch(
                "GET",
                "/api/research-report-viewpoints",
                {"issuer_id": "issuer_001"},
                role="analyst",
            )
            self.assertTrue(viewpoints.success, viewpoints.error)
            self.assertEqual(viewpoints.data["count"], 1)
            viewpoint = viewpoints.data["viewpoints"][0]
            self.assertEqual(viewpoint["viewpoint_type"], "target_price")
            self.assertEqual(viewpoint["rating"], "buy")
            self.assertIn("AI订单落地", viewpoint["core_assumptions"])
            self.assertIn("需求不及预期", viewpoint["risks"])
            self.assertTrue(viewpoint["evidence_ids"])

            forecasts = self.router.dispatch(
                "GET",
                "/api/research-report-forecasts",
                {"issuer_id": "issuer_001"},
                role="analyst",
            )
            self.assertTrue(forecasts.success, forecasts.error)
            forecast_types = {item["forecast_type"] for item in forecasts.data["forecasts"]}
            self.assertIn("target_price", forecast_types)
            self.assertIn("eps", forecast_types)

            analysts = self.router.dispatch(
                "GET",
                "/api/analyst-profiles",
                {"issuer_id": "issuer_001"},
                role="analyst",
            )
            self.assertTrue(analysts.success, analysts.error)
            self.assertEqual(analysts.data["count"], 2)

            duplicate = self.router.dispatch(
                "POST",
                "/api/research-reports/structure",
                {"report_ids": [report["report_id"]], "execute": True},
                actor="analyst",
                role="analyst",
            )
            self.assertTrue(duplicate.success, duplicate.error)
            self.assertEqual(duplicate.data["structured_count"], 0)
            self.assertEqual(duplicate.data["skipped_count"], 1)
            self.assertEqual(duplicate.data["reports"][0]["status"], "skipped_existing")

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

    def test_paddleocr_document_parsing_retries_transient_failure(self) -> None:
        sent = []
        jsonl = json.dumps({"result": {"layoutParsingResults": [{"markdown": {"text": "Retry page markdown."}}]}}).encode("utf-8")
        job_submissions = {"count": 0}

        def fake_send(request, timeout):
            sent.append({"url": request.full_url, "method": request.get_method(), "timeout": timeout})
            if request.full_url.endswith("/api/v2/ocr/jobs") and request.get_method() == "POST":
                job_submissions["count"] += 1
                if job_submissions["count"] == 1:
                    return b'{"data":{}}'
                return b'{"data":{"jobId":"job_retry_1"}}'
            if request.full_url.endswith("/api/v2/ocr/jobs/job_retry_1"):
                return b'{"data":{"state":"done","resultUrl":{"jsonUrl":"https://result.example/retry.jsonl"}}}'
            if request.full_url == "https://result.example/retry.jsonl":
                return jsonl
            return b"{}"

        self.service.document_parser = PaddleOCRParser(token="ocr-test-token", poll_interval=0, max_polls=2, http_send=fake_send)
        response = self.router.dispatch(
            "POST",
            "/api/document-parsing/paddleocr",
            {"file_url": "https://reports.example/retry.pdf", "retry_attempts": 1, "use_cache": False},
            role="data_engineer",
        )
        self.assertTrue(response.success, response.error)
        self.assertEqual(response.data["job_id"], "job_retry_1")
        self.assertEqual(response.data["attempt_count"], 2)
        self.assertEqual(response.data["retry_attempts"], 1)
        self.assertIn("PaddleOCR job response missing jobId", response.data["retry_errors"][0])
        self.assertEqual(job_submissions["count"], 2)

    def test_extract_evidence_ocr_fallback_retries_before_manual_review(self) -> None:
        jsonl = json.dumps({"result": {"layoutParsingResults": [{"markdown": {"text": "Retried OCR revenue text."}}]}}).encode("utf-8")
        job_submissions = {"count": 0}

        def fake_send(request, timeout):
            if request.full_url.endswith("/api/v2/ocr/jobs") and request.get_method() == "POST":
                job_submissions["count"] += 1
                if job_submissions["count"] == 1:
                    return b'{"data":{}}'
                return b'{"data":{"jobId":"job_retry_extract"}}'
            if request.full_url.endswith("/api/v2/ocr/jobs/job_retry_extract"):
                return b'{"data":{"state":"done","resultUrl":{"jsonUrl":"https://result.example/retry-extract.jsonl"}}}'
            if request.full_url == "https://result.example/retry-extract.jsonl":
                return jsonl
            return b"{}"

        self.service.document_parser = PaddleOCRParser(token="ocr-test-token", poll_interval=0, max_polls=2, http_send=fake_send)
        stored = self.service.object_store.put_bytes("src_sec", "doc_ocr_retry", b"%PDF-1.4\n%%EOF", suffix=".pdf")
        self.addCleanup(lambda: Path(stored.uri).unlink(missing_ok=True))
        self.service.ingest_document(
            {
                "document_id": "doc_ocr_retry",
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "source_id": "src_sec",
                "source_type": "regulatory",
                "document_type": "10-K",
                "source_uri": "https://example.invalid/doc-ocr-retry.pdf",
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

        evidences = self.service.extract_evidence("doc_ocr_retry", actor="analyst", parser_version="pdf-rule-1")
        self.assertEqual(len(evidences), 1)
        self.assertIn("Retried OCR revenue text.", evidences[0].span_text)
        self.assertEqual(job_submissions["count"], 2)
        self.assertEqual(self.service.manual_review_payload({"document_id": "doc_ocr_retry"})["manual_reviews"], [])

    def test_extract_evidence_preserves_ocr_bbox_assets_and_table_cells(self) -> None:
        sent = []
        jsonl = json.dumps(
            {
                "result": {
                    "layoutParsingResults": [
                        {
                            "markdown": {
                                "text": "Revenue table\nRevenue 100\nOperating cash flow 20",
                                "images": {"fig_1": "s3://ocr-assets/fig_1.png"},
                            },
                            "outputImages": {"table_1": "s3://ocr-assets/table_1.png"},
                            "layoutDetections": [
                                {
                                    "type": "table",
                                    "text": "Revenue table Revenue 100 Operating cash flow 20",
                                    "bbox": [10, 20, 210, 120],
                                    "confidence": 0.93,
                                }
                            ],
                            "tables": [
                                {
                                    "bbox": [10, 20, 210, 120],
                                    "cells": [
                                        {"row": 1, "col": 1, "text": "Metric", "bbox": [10, 20, 80, 45]},
                                        {"row": 1, "col": 2, "text": "Value", "bbox": [80, 20, 210, 45]},
                                        {"row": 2, "col": 1, "text": "Revenue", "bbox": [10, 45, 80, 80]},
                                        {"row": 2, "col": 2, "text": "100", "bbox": [80, 45, 210, 80]},
                                    ],
                                }
                            ],
                        }
                    ]
                }
            }
        ).encode("utf-8")

        def fake_send(request, timeout):
            sent.append({"url": request.full_url, "method": request.get_method(), "timeout": timeout})
            if request.full_url.endswith("/api/v2/ocr/jobs") and request.get_method() == "POST":
                return b'{"data":{"jobId":"job_ocr_layout"}}'
            if request.full_url.endswith("/api/v2/ocr/jobs/job_ocr_layout"):
                return b'{"data":{"state":"done","resultUrl":{"jsonUrl":"https://result.example/layout.jsonl"}}}'
            if request.full_url == "https://result.example/layout.jsonl":
                return jsonl
            return b"{}"

        self.service.document_parser = PaddleOCRParser(token="ocr-test-token", poll_interval=0, max_polls=2, http_send=fake_send)
        stored = self.service.object_store.put_bytes("src_sec", "doc_ocr_layout", b"%PDF-1.4\n%%EOF", suffix=".pdf")
        self.addCleanup(lambda: Path(stored.uri).unlink(missing_ok=True))
        self.service.ingest_document(
            {
                "document_id": "doc_ocr_layout",
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "source_id": "src_sec",
                "source_type": "regulatory",
                "document_type": "10-K",
                "source_uri": "https://example.invalid/doc-ocr-layout.pdf",
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

        evidences = self.service.extract_evidence("doc_ocr_layout", actor="analyst", parser_version="pdf-rule-1")
        self.assertEqual(len(evidences), 1)
        evidence = evidences[0]
        self.assertEqual(evidence.locator["scheme"], "ocr_bbox_span_v1")
        self.assertEqual(evidence.locator["bbox"], {"x": 10.0, "y": 20.0, "width": 200.0, "height": 100.0})
        self.assertIn("bbox=10,20,200,100", evidence.bbox)
        self.assertEqual(len(evidence.assets), 2)
        self.assertEqual(evidence.locator["tables"][0]["cells"][0]["bbox"]["width"], 70.0)

        report = self.router.dispatch("GET", "/api/evidence/quality-report", {"issuer_id": "issuer_001"}, role="risk_compliance")
        self.assertTrue(report.success, report.error)
        self.assertEqual(report.data["structured_locator_coverage"], 1.0)
        self.assertEqual(report.data["bbox_coverage"], 1.0)
        self.assertEqual(report.data["table_cell_count"], 4)
        self.assertEqual(report.data["table_cell_bbox_coverage"], 1.0)
        self.assertEqual(report.data["asset_reference_count"], 2)

        bbox_report = self.router.dispatch(
            "POST",
            "/api/evidence/quality-report",
            {
                "issuer_id": "issuer_001",
                "min_bbox_iou": 0.8,
                "bbox_gold_labels": [
                    {
                        "document_id": "doc_ocr_layout",
                        "page_no": 1,
                        "bbox": {"x": 10, "y": 20, "width": 200, "height": 100},
                    },
                    {
                        "document_id": "doc_ocr_layout",
                        "page_no": 1,
                        "bbox": {"x": 300, "y": 300, "width": 20, "height": 20},
                    },
                ],
            },
            role="risk_compliance",
        )
        self.assertTrue(bbox_report.success, bbox_report.error)
        validation = bbox_report.data["bbox_gold_validation"]
        self.assertEqual(validation["label_count"], 2)
        self.assertEqual(validation["matched_count"], 1)
        self.assertEqual(validation["bbox_hit_rate"], 0.5)
        self.assertEqual(validation["labels"][0]["iou"], 1.0)
        self.assertEqual(validation["failures"][0]["issue"], "bbox_iou_below_threshold_or_missing_evidence")

        tables = self.service._extract_tables(evidence.canonical_text, evidence=evidence)
        self.assertEqual(tables[0]["cells"][0]["locator"]["scheme"], "ocr_table_cell_v1")
        self.assertIn("row=1;col=1;bbox=10,20,70,25", tables[0]["cells"][0]["bbox"])

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
        self.assertIn("doc_scanned", report.data["missing_document_ids"])
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

    def test_observability_readiness_report_tracks_external_evidence_and_playbooks(self) -> None:
        self.router.dispatch("POST", "/api/playbooks/seed", {}, role="risk_compliance", actor="risk_owner")
        workflow = self.router.dispatch(
            "POST",
            "/api/orchestration/dags",
            {
                "dag_id": "dag_observability_readiness",
                "name": "Observability readiness",
                "tasks": [{"task_id": "collect", "task_type": "noop"}],
                "owner_role": "平台负责人",
            },
            role="platform",
        )
        self.assertTrue(workflow.success, workflow.error)
        run = self.router.dispatch(
            "POST",
            "/api/orchestration/dags/dag_observability_readiness/run",
            {"run_id": "wfrun_observability_readiness", "status": "failed", "task_statuses": {"collect": "failed"}, "error": "otel gap"},
            role="platform",
        )
        self.assertTrue(run.success, run.error)
        self.service.store.system_alerts["alert_observability_readiness"] = SystemAlert(
            alert_id="alert_observability_readiness",
            rule_id="alert_workflow_failed_runs",
            metric="workflow_failed_runs",
            value=1,
            threshold=0,
            severity="high",
            status="open",
            message="workflow failed for observability readiness",
            owner="平台负责人",
            playbook_id="pb_workflow_sla_breach",
        )
        self.service.store.alert_notifications["aln_external_slack_sent"] = AlertNotification(
            notification_id="aln_external_slack_sent",
            alert_id="alert_observability_readiness",
            channel="slack",
            target="https://hooks.slack.invalid/services/readiness",
            status="sent",
            payload={"delivery_provider": "slack", "delivery_attempts": 1, "delivery_response": {"mode": "slack", "status_code": 200}},
        )

        gap = self.router.dispatch("POST", "/api/observability/readiness-report", {"log_limit": 50}, role="platform")
        self.assertTrue(gap.success, gap.error)
        self.assertFalse(gap.data["ready_for_production_observability"])
        self.assertIn("non_local_collector_configured", gap.data["missing_requirements"])
        self.assertIn("retention_policy", gap.data["missing_requirements"])
        self.assertIn("quarterly_drill_coverage", gap.data["missing_requirements"])
        self.assertIn("external_alert_channel", gap.data["missing_requirements"])
        self.assertEqual(gap.data["playbook_coverage"], 1.0)
        self.assertIn("observability_readiness_report_tracks_external_collector", gap.data["usage_boundary"])

        for schedule in list(self.service.store.drill_schedules.values()):
            result = self.router.dispatch(
                "POST",
                f"/api/drill-schedules/{schedule.schedule_id}/result",
                {
                    "result": "passed",
                    "run_at": "2026-05-01T00:00:00+00:00",
                    "rca_summary": "quarterly drill passed",
                    "action_items": ["verify escalation", "update runbook evidence"],
                },
                role="risk_compliance",
                actor="risk_owner",
            )
            self.assertTrue(result.success, result.error)
        self.router.dispatch(
            "POST",
            "/api/readiness/checklist/otel_collector_drill",
            {
                "status": "passed",
                "owner": "platform_owner",
                "evidence_uri": "artifact://staging/otel-collector-drill.json",
                "metrics": {"logs": 1, "metrics": 1, "traces": 1},
            },
            role="platform",
            actor="platform_owner",
        )

        no_alert_evidence = self.router.dispatch(
            "POST",
            "/api/observability/readiness-report",
            {
                "environment": "staging",
                "collector": {
                    "logs_endpoint": "https://otel.staging.example.com/v1/logs",
                    "metrics_endpoint": "https://otel.staging.example.com/v1/metrics",
                    "traces_endpoint": "https://otel.staging.example.com/v1/traces",
                },
                "retention_policy": {
                    "retention_days": 90,
                    "owner": "platform_owner",
                    "deletion_policy": "delete_after_90_days_with_legal_hold_override",
                    "evidence_uri": "artifact://observability/log-retention-policy.md",
                },
                "artifact_uris": {
                    "collector_evidence_uri": "artifact://staging/otel-collector-drill.json",
                    "logs_backend_uri": "grafana-loki://staging/logs",
                    "query_evidence_uri": "artifact://staging/loki-query-proof.json",
                    "drill_evidence_uri": "artifact://staging/incident-drill-matrix.json",
                },
            },
            role="platform",
            actor="platform_owner",
        )
        self.assertTrue(no_alert_evidence.success, no_alert_evidence.error)
        self.assertFalse(no_alert_evidence.data["ready_for_production_observability"])
        self.assertNotIn("external_alert_delivery_record", no_alert_evidence.data["missing_requirements"])
        self.assertIn("external_alert_channel", no_alert_evidence.data["missing_requirements"])

        ready = self.router.dispatch(
            "POST",
            "/api/observability/readiness-report",
            {
                "environment": "staging",
                "collector": {
                    "logs_endpoint": "https://otel.staging.example.com/v1/logs",
                    "metrics_endpoint": "https://otel.staging.example.com/v1/metrics",
                    "traces_endpoint": "https://otel.staging.example.com/v1/traces",
                },
                "retention_policy": {
                    "retention_days": 90,
                    "owner": "platform_owner",
                    "deletion_policy": "delete_after_90_days_with_legal_hold_override",
                    "evidence_uri": "artifact://observability/log-retention-policy.md",
                },
                "artifact_uris": {
                    "collector_evidence_uri": "artifact://staging/otel-collector-drill.json",
                    "logs_backend_uri": "grafana-loki://staging/logs",
                    "query_evidence_uri": "artifact://staging/loki-query-proof.json",
                    "external_alert_evidence_uri": "artifact://staging/slack-delivery-proof.json",
                    "drill_evidence_uri": "artifact://staging/incident-drill-matrix.json",
                },
                "record_readiness": True,
            },
            role="platform",
            actor="platform_owner",
        )
        self.assertTrue(ready.success, ready.error)
        self.assertTrue(ready.data["ready_for_production_observability"])
        self.assertEqual(ready.data["missing_requirements"], [])
        self.assertTrue(ready.data["collector"]["non_local_configured"])
        self.assertEqual(ready.data["drill_summary"]["coverage"], 1.0)
        self.assertGreaterEqual(ready.data["notifications"]["sent_external_count"], 1)
        self.assertEqual(self.service.store.audit_log[-1].action, "observability_readiness_report")

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

            security_gap = self.router.dispatch("POST", "/api/governance/security-readiness-report", {}, role="risk_compliance")
            self.assertTrue(security_gap.success, security_gap.error)
            self.assertFalse(security_gap.data["ready_for_security_production"])
            self.assertIn("permission_denied_audited", security_gap.data["missing_requirements"])
            self.assertIn("secret_rotation_metadata", security_gap.data["missing_requirements"])
            self.assertIn("secret_manager_evidence_uri", security_gap.data["missing_requirements"])
            self.assertFalse(security_gap.data["automation_allowed"])

            bool_only_red_team = self.router.dispatch(
                "POST",
                "/api/governance/security-readiness-report",
                {"permission_red_team_evidence": True},
                role="risk_compliance",
            )
            self.assertTrue(bool_only_red_team.success, bool_only_red_team.error)
            self.assertFalse(bool_only_red_team.data["ready_for_security_production"])
            self.assertIn("permission_denied_audited", bool_only_red_team.data["missing_requirements"])

            denied = self.router.dispatch("GET", "/api/governance/data-security-report", {}, role="analyst", actor="analyst_denied")
            self.assertFalse(denied.success)
            rotation = self.router.dispatch(
                "POST",
                "/api/governance/secret-rotations",
                {
                    "rotation_id": "secrot_security_ready",
                    "secret_name": "AI_QUANT_POSTGRES_DSN",
                    "provider": "vault",
                    "owner": "platform_security",
                    "status": "rotated",
                    "rotated_at": "2026-05-15T00:00:00+00:00",
                    "next_rotation_due_at": "2026-08-15T00:00:00+00:00",
                    "evidence_uri": "artifact://security/secret-rotation.json",
                },
                role="risk_compliance",
                actor="risk",
            )
            self.assertTrue(rotation.success, rotation.error)
            security_ready = self.router.dispatch(
                "POST",
                "/api/governance/security-readiness-report",
                {
                    "secret_manager_provider": "vault",
                    "api_key_scope": "scoped_read_write_no_admin",
                    "delete_executor": "s3_lifecycle_opensearch_kms_dlp",
                    "permission_red_team_evidence": True,
                    "artifact_uris": {
                        "secret_manager_evidence_uri": "artifact://security/secret-manager.json",
                        "least_privilege_policy_uri": "artifact://security/least-privilege-policy.json",
                        "external_delete_evidence_uri": "artifact://security/cache-delete-evidence.json",
                        "permission_review_uri": "artifact://security/permission-red-team.json",
                        "data_security_scan_uri": "artifact://security/data-security-scan.json",
                        "source_governance_uri": "artifact://security/source-governance.json",
                    },
                    "record_readiness": True,
                },
                role="risk_compliance",
                actor="risk",
            )
            self.assertTrue(security_ready.success, security_ready.error)
            self.assertTrue(security_ready.data["ready_for_security_production"])
            self.assertEqual(security_ready.data["missing_requirements"], [])
            self.assertEqual(security_ready.data["secret_rotation_summary"]["count"], 1)
            self.assertGreaterEqual(security_ready.data["permission"]["permission_denied_events"], 1)
            self.assertEqual(security_ready.data["cache_retention_summary"]["executed_outside_app"], 1)
            self.assertIn("without_secret_values", security_ready.data["usage_boundary"])
            self.assertEqual(self.service.store.audit_log[-1].action, "security_readiness_report")

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

    def test_llm_gateway_endpoint_accepts_request_timeout_without_forwarding_it(self) -> None:
        sent = []

        def fake_send(request, timeout):
            sent.append({"timeout": timeout, "body": json.loads(request.data.decode("utf-8"))})
            return '{"id":"chatcmpl_timeout","choices":[{"message":{"content":"OK"}}]}'.encode("utf-8")

        self.service.llm_gateway = LLMGateway(
            base_url="https://llm.example.test",
            api_key="test-key",
            default_model="qwen3.6-plus",
            timeout=120,
            http_send=fake_send,
        )
        response = self.router.dispatch(
            "POST",
            "/api/llm/openai/chat/completions",
            {"messages": [{"role": "user", "content": "ping"}], "timeout_seconds": 9},
            actor="analyst",
            role="nlp_ml",
        )
        self.assertTrue(response.success, response.error)
        self.assertEqual(sent[0]["timeout"], 9)
        self.assertNotIn("timeout_seconds", sent[0]["body"])
        self.assertEqual(response.data["timeout_seconds"], 9)

    def test_llm_gateway_request_timeout_is_hard_capped(self) -> None:
        def slow_send(request, timeout):
            time.sleep(2)
            return b"{}"

        self.service.llm_gateway = LLMGateway(
            base_url="https://llm.example.test",
            api_key="test-key",
            default_model="qwen3.6-plus",
            timeout=120,
            http_send=slow_send,
        )
        started = time.monotonic()
        response = self.router.dispatch(
            "POST",
            "/api/llm/openai/chat/completions",
            {"messages": [{"role": "user", "content": "ping"}], "timeout_seconds": 1},
            actor="analyst",
            role="nlp_ml",
        )
        elapsed = time.monotonic() - started
        self.assertFalse(response.success)
        self.assertEqual(response.status_code, 422)
        self.assertIn("timed out", response.error["message"])
        self.assertLess(elapsed, 1.7)

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

    def test_chokepoint_research_run_persists_steps_and_verification_tasks(self) -> None:
        def fake_send(request, timeout):
            body = json.loads(request.data.decode("utf-8"))
            prompt = body["messages"][0]["content"]
            if "来源台账" in prompt:
                content = (
                    "事实编号 | 事实陈述 | URL | 发布日期 | 来源类型 | confirmed/inferred/speculative | 置信度 | 下一步验证\n"
                    "1 | DOE HALEU funding supports non-Russian supply chain | https://www.energy.gov/ | 2024-01-01 | government | confirmed | high | verify awards\n"
                    "2 | SWU price remains unknown |  | unknown | unknown | unknown | low | needs_verification"
                )
            else:
                content = "阶段结论：unknown 待验证，不构成投资建议。"
            return json.dumps({"id": "chatcmpl_cp", "choices": [{"message": {"content": content}}]}).encode("utf-8")

        self.service.llm_gateway = LLMGateway(
            base_url="https://llm.example.test",
            api_key="test-key",
            default_model="qwen3.6-plus",
            http_send=fake_send,
        )
        self.service.store.securities["sec_ccj"] = services_module.Security(
            security_id="sec_ccj",
            issuer_id="issuer_ccj",
            ticker="CCJ",
            market="U",
            currency="USD",
        )
        self.service.store.market_data["md_ccj"] = services_module.MarketDataPoint(
            data_id="md_ccj",
            security_id="sec_ccj",
            market="U",
            as_of_date="2026-05-26",
            close=50.0,
            adjusted_close=50.0,
            volume=1000,
            source_id="public_eod_market_data",
            data_type="eod",
            rights_tag=RightsTag("public"),
        )
        self.service.store.documents["doc_nuclear_note"] = services_module.Document(
            document_id="doc_nuclear_note",
            issuer_id="issuer_ccj",
            security_id="sec_ccj",
            source_id="local_research_reports",
            source_type="local_reference",
            document_type="research",
            source_uri="research-report://nuclear-note",
            title="Nuclear fuel chain opinion",
            body="Research opinion only.",
            rights_tag=RightsTag("local_research_reference", display_use="restricted"),
        )
        self.service.store.evidence["evi_nuclear_opinion"] = services_module.Evidence(
            evidence_id="evi_nuclear_opinion",
            document_id="doc_nuclear_note",
            section="research_report_citation",
            page_no=1,
            bbox="research-report://nuclear-note;chunk=0",
            span_text="Opinion: non-Russian SWU may be tight.",
            canonical_text="Opinion: non-Russian SWU may be tight.",
            confidence=0.7,
        )

        created = self.router.dispatch(
            "POST",
            "/api/chokepoint/runs",
            {
                "run_id": "cprun_nuclear",
                "topic": "核能候选池",
                "ticker": "CCJ",
                "theme": "核能 / 核燃料链",
                "chokepoint_node": "非俄转化、浓缩、HALEU",
                "playbook": "nuclear",
            },
            actor="analyst",
            role="analyst",
        )
        self.assertTrue(created.success, created.error)
        self.assertEqual(len(created.data["steps"]), 7)
        self.assertFalse(created.data["automation_allowed"])
        self.assertFalse(created.data["live_execution_allowed"])
        self.assertEqual(created.data["validation_context"]["market_data"]["count"], 1)
        self.assertEqual(created.data["validation_context"]["opinions"]["count"], 1)
        self.assertEqual(created.data["validation_context"]["facts"]["count"], 0)

        step = self.router.dispatch(
            "POST",
            "/api/chokepoint/runs/cprun_nuclear/steps/sourceLedger/run",
            {"role": "分析师", "max_tokens": 500},
            actor="analyst",
            role="analyst",
        )
        self.assertTrue(step.success, step.error)
        self.assertEqual(step.data["steps"][0]["status"], "done")
        self.assertTrue(step.data["steps"][0]["llm_run_id"].startswith("llmrun_cprun_nuclear_sourceLedger"))
        self.assertGreaterEqual(step.data["steps"][0]["evidence_quality"]["url_count"], 1)
        self.assertEqual(self.service.store.llm_task_runs[step.data["steps"][0]["llm_run_id"]].task_type, "chokepoint_research_step")

        tasks = self.router.dispatch(
            "POST",
            "/api/chokepoint/runs/cprun_nuclear/verification-tasks",
            {},
            actor="analyst",
            role="analyst",
        )
        self.assertTrue(tasks.success, tasks.error)
        self.assertGreaterEqual(tasks.data["created_count"], 1)
        self.assertFalse(tasks.data["automation_allowed"])
        again = self.router.dispatch(
            "POST",
            "/api/chokepoint/runs/cprun_nuclear/verification-tasks",
            {},
            actor="analyst",
            role="analyst",
        )
        self.assertTrue(again.success, again.error)
        self.assertEqual(again.data["created_count"], 0)
        self.assertGreaterEqual(again.data["existing_count"], 1)

    def test_chokepoint_source_ledger_without_url_blocks_gate_and_fallback_requires_review(self) -> None:
        def no_url_send(request, timeout):
            return json.dumps({"id": "chatcmpl_cp", "choices": [{"message": {"content": "事实 | 来源\nSWU price unknown | unknown\n买入建议：不应出现"}}]}).encode("utf-8")

        self.service.llm_gateway = LLMGateway(
            base_url="https://llm.example.test",
            api_key="test-key",
            default_model="qwen3.6-plus",
            http_send=no_url_send,
        )
        created = self.router.dispatch(
            "POST",
            "/api/chokepoint/runs",
            {"run_id": "cprun_block", "topic": "核能转化瓶颈", "mode": "strict"},
            actor="analyst",
            role="analyst",
        )
        self.assertTrue(created.success, created.error)
        run = self.router.dispatch("POST", "/api/chokepoint/runs/cprun_block/run", {"step_limit": 1}, actor="analyst", role="analyst")
        self.assertTrue(run.success, run.error)
        self.assertEqual(run.data["status"], "paused")
        self.assertEqual(run.data["current_step"], "sourceLedger")
        self.assertEqual(run.data["steps"][0]["status"], "review")
        messages = [item["message"] for item in run.data["issues"]]
        self.assertTrue(any("来源台账没有可点击 URL" in item for item in messages))
        self.assertTrue(any("投资建议" in item for item in messages))

        self.service.llm_gateway = LLMGateway(api_key="", http_send=lambda _request, _timeout: b"{}")
        fallback_created = self.router.dispatch("POST", "/api/chokepoint/runs", {"run_id": "cprun_fallback", "topic": "核能 HALEU"}, actor="analyst", role="analyst")
        self.assertTrue(fallback_created.success, fallback_created.error)
        fallback = self.router.dispatch("POST", "/api/chokepoint/runs/cprun_fallback/steps/sourceLedger/run", {}, actor="analyst", role="analyst")
        self.assertTrue(fallback.success, fallback.error)
        self.assertEqual(fallback.data["steps"][0]["status"], "review")
        self.assertTrue(fallback.data["steps"][0]["evidence_quality"]["fallback_used"])

    def test_chokepoint_pipeline_runs_all_steps_even_when_review_issues_exist(self) -> None:
        calls: list[str] = []

        def no_url_send(request, timeout):
            body = json.loads(request.data.decode("utf-8"))
            content = body["messages"][-1]["content"]
            marker = "流水线结论" if "流水线结论" in content or "规则结论" in content else "未知步骤"
            if marker == "未知步骤":
                step_match = re.search(r"步骤：([^\n]+)", content)
                if step_match:
                    marker = step_match.group(1).strip()
            calls.append(marker)
            return json.dumps({"id": f"chatcmpl_{len(calls)}", "choices": [{"message": {"content": f"{marker} | unknown | 待验证"}}]}).encode("utf-8")

        self.service.llm_gateway = LLMGateway(
            base_url="https://llm.example.test",
            api_key="test-key",
            default_model="qwen3.6-plus",
            http_send=no_url_send,
        )
        created = self.router.dispatch(
            "POST",
            "/api/chokepoint/runs",
            {"run_id": "cprun_run_all", "topic": "核能转化瓶颈", "mode": "strict"},
            actor="analyst",
            role="analyst",
        )
        self.assertTrue(created.success, created.error)
        run = self.router.dispatch(
            "POST",
            "/api/chokepoint/runs/cprun_run_all/run",
            {"step_limit": 7},
            actor="analyst",
            role="analyst",
        )
        self.assertTrue(run.success, run.error)
        self.assertEqual(calls[:7], ["来源台账", "事实审计", "问题窄化", "价值链映射", "Chokepoint 排名", "Thesis 草稿", "验证与证伪"])
        self.assertEqual(calls[-1], "流水线结论")
        self.assertEqual([step["status"] for step in run.data["steps"]], ["review", "done", "done", "done", "done", "done", "done"])
        self.assertEqual(run.data["status"], "completed")
        self.assertEqual(run.data["conclusion"]["status"], "needs_evidence")
        self.assertGreaterEqual(run.data["conclusion"]["verification_tasks"]["created_count"], 1)

    def test_chokepoint_finalize_fallback_is_idempotent_and_research_only(self) -> None:
        def step_then_conclusion_failure(request, timeout):
            body = json.loads(request.data.decode("utf-8"))
            content = body["messages"][-1]["content"]
            if "流水线结论" in content or "规则结论" in content:
                raise RuntimeError("rate limited")
            return json.dumps(
                {
                    "id": "chatcmpl_cp_step",
                    "choices": [
                        {
                            "message": {
                                "content": "事实 | URL | 分层\n核燃料链 chokepoint 待验证 | https://example.com/source | confirmed\nP0: 核验许可周期 unknown"
                            }
                        }
                    ],
                }
            ).encode("utf-8")

        self.service.llm_gateway = LLMGateway(
            base_url="https://llm.example.test",
            api_key="test-key",
            default_model="qwen3.6-plus",
            http_send=step_then_conclusion_failure,
        )
        created = self.router.dispatch(
            "POST",
            "/api/chokepoint/runs",
            {"run_id": "cprun_finalize", "topic": "核能许可瓶颈", "mode": "strict"},
            actor="analyst",
            role="analyst",
        )
        self.assertTrue(created.success, created.error)
        first = self.router.dispatch(
            "POST",
            "/api/chokepoint/runs/cprun_finalize/run",
            {"step_limit": 7},
            actor="analyst",
            role="analyst",
        )
        self.assertTrue(first.success, first.error)
        self.assertEqual(first.data["conclusion"]["fallback_used"], "rule_summary")
        self.assertIn(first.data["conclusion"]["status"], {"ready_for_review", "needs_evidence"})
        rendered = json.dumps(first.data["conclusion"], ensure_ascii=False)
        for forbidden in ["买入", "卖出", "仓位", "目标价", "投资建议"]:
            self.assertNotIn(forbidden, rendered)

        second = self.router.dispatch(
            "POST",
            "/api/chokepoint/runs/cprun_finalize/finalize",
            {},
            actor="analyst",
            role="analyst",
        )
        self.assertTrue(second.success, second.error)
        self.assertEqual(second.data["conclusion"]["verification_tasks"]["created_count"], 0)
        self.assertGreaterEqual(second.data["conclusion"]["verification_tasks"]["existing_count"], 1)

    def test_chokepoint_step_passes_request_timeout_to_llm_gateway(self) -> None:
        sent = []

        def fake_send(request, timeout):
            sent.append({"timeout": timeout, "body": json.loads(request.data.decode("utf-8"))})
            return json.dumps({"id": "chatcmpl_cp_timeout", "choices": [{"message": {"content": "事实 | URL | 分层\nA | https://example.com | confirmed"}}]}).encode("utf-8")

        self.service.llm_gateway = LLMGateway(
            base_url="https://llm.example.test",
            api_key="test-key",
            default_model="qwen3.6-plus",
            timeout=120,
            http_send=fake_send,
        )
        created = self.router.dispatch("POST", "/api/chokepoint/runs", {"run_id": "cprun_timeout", "topic": "核能 HALEU"}, actor="analyst", role="analyst")
        self.assertTrue(created.success, created.error)
        step = self.router.dispatch(
            "POST",
            "/api/chokepoint/runs/cprun_timeout/steps/sourceLedger/run",
            {"timeout_seconds": 7, "max_tokens": 120},
            actor="analyst",
            role="analyst",
        )
        self.assertTrue(step.success, step.error)
        self.assertEqual(sent[0]["timeout"], 7)
        self.assertNotIn("timeout_seconds", sent[0]["body"])

    def test_local_chokepoint_quality_package_builds_repeatable_local_artifacts(self) -> None:
        with TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "chokepoint-quality"
            package = build_local_chokepoint_quality_package(
                output_dir=output_dir,
                artifact_prefix="artifact://local/test-chokepoint-quality",
            )

            self.assertEqual(package["status"], "generated")
            self.assertEqual(package["sample_count"], 5)
            self.assertEqual(package["run_result_count"], 5)
            self.assertTrue(package["ready_for_local_baseline"])
            self.assertEqual(package["quality_baseline"]["boundary_violation_rate"], 0.0)
            self.assertTrue(package["quality_baseline"]["automation_boundary_ok"])
            self.assertTrue(package["quality_baseline"]["live_execution_boundary_ok"])

            manifest = json.loads((output_dir / "sample-manifest.json").read_text(encoding="utf-8"))
            results = json.loads((output_dir / "run-results.json").read_text(encoding="utf-8"))
            review_seed = json.loads((output_dir / "manual-review-seed.json").read_text(encoding="utf-8"))
            summary = json.loads((output_dir / "quality-summary.json").read_text(encoding="utf-8"))

            self.assertEqual(manifest["sample_count"], 5)
            self.assertEqual(results["run_count"], 5)
            self.assertEqual(review_seed["row_count"], 5)
            self.assertTrue(summary["ready_for_local_baseline"])
            self.assertEqual(summary["quality_baseline"]["manual_review_close_rate"], 0.0)
            self.assertEqual(summary["quality_baseline"]["manual_review_sample_coverage_rate"], 0.0)
            self.assertEqual(summary["quality_baseline"]["manual_review_issue_count"], 0)
            self.assertEqual(summary["manual_review_summary"]["review_status_counts"], {"seed_only": 5})
            self.assertGreater(summary["quality_baseline"]["verification_task_generation_rate"], 0.0)

            first_run = results["runs"][0]
            self.assertFalse(first_run["automation_allowed"])
            self.assertFalse(first_run["live_execution_allowed"])
            self.assertEqual(len(first_run["step_output_digest"]), 7)
            self.assertIn(first_run["conclusion_status"], {"ready_for_review", "needs_evidence"})
            self.assertEqual(first_run["usage_boundary"], "research_only_not_investment_advice")

    def test_local_chokepoint_quality_package_merges_manual_review_metrics(self) -> None:
        with TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "chokepoint-quality"
            manual_reviews = {
                "rows": [
                    {
                        "sample_id": "cpq_nuclear_haleu",
                        "review_status": "completed_manual_review",
                        "reviewer": "pm-agent",
                        "reviewed_at": "2026-05-28T21:00:00+08:00",
                        "review_notes": "Reviewed for closure and issue tagging.",
                        "expected_labels": [
                            {"label_id": "core_supply_constraint", "manual_status": "confirmed", "notes": "supported by source ledger"},
                            {"label_id": "needs_official_award_check", "manual_status": "dismissed", "notes": "left open but triaged out of this baseline"},
                        ],
                        "manual_issues": [
                            {"issue_type": "missing_date", "severity": "warn"},
                            {"issue_type": "classification_dispute", "severity": "warn"},
                        ],
                    },
                    {
                        "sample_id": "cpq_power_grid",
                        "review_status": "partial_manual_review",
                        "reviewer": "pm-agent",
                        "reviewed_at": "2026-05-28T21:05:00+08:00",
                        "expected_labels": [
                            {"label_id": "grid_connection_delay", "manual_status": "confirmed", "notes": "kept as confirmed"},
                            {"label_id": "pricing_misread", "manual_status": "pending_manual_review", "notes": "needs valuation follow-up"},
                        ],
                        "manual_issues": [
                            {"issue_type": "needs_follow_up", "severity": "info"},
                        ],
                    },
                ]
            }
            package = build_local_chokepoint_quality_package(
                output_dir=output_dir,
                artifact_prefix="artifact://local/test-chokepoint-quality",
                manual_review_input=manual_reviews,
            )

            review_seed = json.loads((output_dir / "manual-review-seed.json").read_text(encoding="utf-8"))
            summary = json.loads((output_dir / "quality-summary.json").read_text(encoding="utf-8"))

            self.assertEqual(package["manual_review_summary"]["review_row_count"], 5)
            self.assertEqual(package["manual_review_summary"]["sample_coverage_count"], 2)
            self.assertEqual(package["manual_review_summary"]["closed_label_count"], 3)
            self.assertEqual(package["manual_review_summary"]["issue_counts"]["missing_date"], 1)
            self.assertEqual(package["manual_review_summary"]["issue_counts"]["classification_dispute"], 1)
            self.assertEqual(package["manual_review_summary"]["issue_counts"]["needs_follow_up"], 1)
            self.assertEqual(summary["quality_baseline"]["manual_review_close_rate"], 0.3)
            self.assertEqual(summary["quality_baseline"]["manual_review_sample_coverage_rate"], 0.4)
            self.assertEqual(summary["quality_baseline"]["manual_review_issue_count"], 3)

            first_review = next(row for row in review_seed["rows"] if row["sample_id"] == "cpq_nuclear_haleu")
            second_review = next(row for row in review_seed["rows"] if row["sample_id"] == "cpq_power_grid")
            self.assertEqual(first_review["review_status"], "completed_manual_review")
            self.assertEqual(first_review["closed_label_count"], 2)
            self.assertEqual(first_review["manual_issue_counts"], {"classification_dispute": 1, "missing_date": 1})
            self.assertEqual(second_review["review_status"], "partial_manual_review")
            self.assertEqual(second_review["closed_label_count"], 1)
            self.assertEqual(second_review["label_count"], 2)

    def test_local_chokepoint_quality_package_cli_accepts_manual_review_jsonl(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            manual_review_path = temp_path / "manual-review.jsonl"
            manual_review_path.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "sample_id": "cpq_nuclear_haleu",
                                "review_status": "completed_manual_review",
                                "expected_labels": [
                                    {"label_id": "core_supply_constraint", "manual_status": "confirmed"},
                                    {"label_id": "needs_official_award_check", "manual_status": "dismissed"},
                                ],
                                "manual_issues": [{"issue_type": "missing_url"}],
                            },
                            ensure_ascii=False,
                        ),
                        json.dumps(
                            {
                                "sample_id": "cpq_power_grid",
                                "review_status": "partial_manual_review",
                                "expected_labels": [
                                    {"label_id": "grid_connection_delay", "manual_status": "confirmed"},
                                ],
                            },
                            ensure_ascii=False,
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            cli_output = temp_path / "cli-quality"
            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/local_chokepoint_quality_package.py",
                    "--output-dir",
                    str(cli_output),
                    "--manual-review-input",
                    str(manual_review_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            self.assertIn('"status": "generated"', result.stdout)
            summary = json.loads((cli_output / "quality-summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["manual_review_summary"]["sample_coverage_count"], 2)
            self.assertEqual(summary["manual_review_summary"]["issue_counts"], {"missing_url": 1})
            self.assertEqual(summary["quality_baseline"]["manual_review_close_rate"], 0.3)
            self.assertFalse((cli_output / ".quality-package.json.tmp").exists())

    def test_llm_readiness_report_tracks_prompt_quality_budget_and_challenger_evidence(self) -> None:
        self.router.dispatch("POST", "/api/llm/task-templates/seed", {}, actor="ml", role="nlp_ml")
        self.service.llm_gateway = LLMGateway(api_key="", http_send=lambda _request, _timeout: b"{}")
        document = self.service.ingest_document(
            {
                "document_id": "doc_llm_readiness",
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "source_id": "src_sec",
                "source_type": "regulatory",
                "document_type": "10-K",
                "source_uri": "https://example.invalid/llm-readiness",
                "body": "Revenue rose 12% and risk factors include demand volatility.",
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
        answer = self.service.create_research_answer(
            {
                "answer_id": "ans_llm_ready",
                "question": "What changed?",
                "issuer_id": "issuer_001",
                "evidence_ids": [evidence.evidence_id],
                "source_document_ids": [document.document_id],
                "english_source_text": "Revenue rose 12% and risk factors include demand volatility.",
                "chinese_summary": "收入增长，风险因素包括需求波动。",
                "summary_version": "summary-v1",
                "prompt_version": "pr_llmtpl_filing_qa_v1_baseline",
                "model_version": "qwen3.6-plus",
                "source_publicness": "public",
                "human_review_status": "approved",
            },
            actor="analyst",
        )
        self.assertEqual(answer.answer_id, "ans_llm_ready")
        thesis = self.service.create_thesis(
            {
                "thesis_id": "thesis_llm_ready",
                "issuer_id": "issuer_001",
                "horizon": "mid",
                "hypothesis": "Revenue growth can persist",
                "evidence_ids": [evidence.evidence_id],
                "confidence": 0.4,
                "status": "review",
            },
            actor="analyst",
        )
        gap = self.router.dispatch(
            "POST",
            "/api/llm/readiness-report",
            {"gateway_configured": False},
            actor="ml",
            role="nlp_ml",
        )
        self.assertTrue(gap.success, gap.error)
        self.assertFalse(gap.data["ready_for_llm_production"])
        self.assertIn("llm_gateway_configured", gap.data["missing_requirements"])
        self.assertIn("model_quality_evaluation_uri", gap.data["missing_requirements"])
        self.assertIn("high_risk_challenger_coverage", gap.data["missing_requirements"])
        self.assertIn("budget_sync_outbox_record", gap.data["missing_requirements"])
        self.assertFalse(gap.data["automation_allowed"])
        self.assertIn("llm_readiness_report_tracks_prompt_model", gap.data["usage_boundary"])

        self.service.llm_gateway = LLMGateway(
            base_url="https://llm.staging.example.com",
            api_key="test-key",
            default_model="qwen3.6-plus",
            http_send=lambda _request, _timeout: b'{"id":"ready","choices":[{"message":{"content":"ok"}}]}',
        )
        run = self.router.dispatch(
            "POST",
            "/api/llm/tasks/run",
            {
                "run_id": "llmrun_ready_001",
                "template_id": "llmtpl_filing_qa_v1",
                "role": "分析师",
                "variables": {"question": "What changed?", "source_text": "Revenue rose 12%."},
            },
            actor="analyst",
            role="analyst",
        )
        self.assertTrue(run.success, run.error)
        challenger = self.service.run_challenger(
            {
                "challenger_id": "chg_llm_ready",
                "thesis_id": thesis.thesis_id,
                "source_conflict": 0.1,
                "valuation_gap": 0.1,
                "narrative_divergence": 0.1,
                "policy_risk": 0.1,
            },
            actor="risk",
        )
        self.assertEqual(challenger.thesis_id, thesis.thesis_id)
        no_budget_outbox = self.router.dispatch(
            "POST",
            "/api/llm/readiness-report",
            {
                "gateway_configured": True,
                "artifact_uris": {
                    "production_llm_gateway_evidence_uri": "artifact://llm/gateway-smoke.json",
                    "prompt_inventory_uri": "artifact://llm/approved-prompts.json",
                    "model_quality_evaluation_uri": "artifact://llm/model-quality.json",
                    "fallback_quality_evaluation_uri": "artifact://llm/fallback-quality.json",
                    "budget_sync_evidence_uri": "artifact://llm/budget-sync.json",
                },
            },
            actor="ml",
            role="nlp_ml",
        )
        self.assertTrue(no_budget_outbox.success, no_budget_outbox.error)
        self.assertFalse(no_budget_outbox.data["ready_for_llm_production"])
        self.assertIn("budget_sync_outbox_record", no_budget_outbox.data["missing_requirements"])
        self.assertIn("budget_sync_evidence_uri", no_budget_outbox.data["missing_requirements"])

        approval = self.router.dispatch(
            "POST",
            "/api/llm/budget-approvals",
            {
                "approval_id": "llmbud_ready",
                "allow_manual": True,
                "requested_budget": 100000,
                "requested_by": "ml_owner",
            },
            actor="ml",
            role="nlp_ml",
        )
        self.assertTrue(approval.success, approval.error)
        decided = self.router.dispatch(
            "POST",
            "/api/llm/budget-approvals/llmbud_ready/decide",
            {"status": "approved", "approver_role": "NLP/ML 负责人", "approver": "ml_owner"},
            actor="ml",
            role="nlp_ml",
        )
        self.assertTrue(decided.success, decided.error)
        synced = self.router.dispatch(
            "POST",
            "/api/llm/budget-approvals/llmbud_ready/sync",
            {"target": "budget://finance-cloud/staging", "mark_sent": True},
            actor="ml",
            role="nlp_ml",
        )
        self.assertTrue(synced.success, synced.error)
        ready = self.router.dispatch(
            "POST",
            "/api/llm/readiness-report",
            {
                "gateway_configured": True,
                "artifact_uris": {
                    "production_llm_gateway_evidence_uri": "artifact://llm/gateway-smoke.json",
                    "prompt_inventory_uri": "artifact://llm/approved-prompts.json",
                    "model_quality_evaluation_uri": "artifact://llm/model-quality.json",
                    "fallback_quality_evaluation_uri": "artifact://llm/fallback-quality.json",
                    "budget_sync_evidence_uri": "artifact://llm/budget-sync.json",
                },
                "record_readiness": True,
            },
            actor="ml",
            role="nlp_ml",
        )
        self.assertTrue(ready.success, ready.error)
        self.assertTrue(ready.data["ready_for_llm_production"])
        self.assertEqual(ready.data["missing_requirements"], [])
        self.assertEqual(ready.data["templates"]["approved_count"], len(self.service.store.llm_task_templates))
        self.assertEqual(ready.data["challenger"]["coverage"], 1.0)
        self.assertEqual(ready.data["budget"]["sync"]["sent_count"], 1)
        self.assertEqual(self.service.store.audit_log[-1].action, "llm_readiness_report")

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

        scheduler_handoff = self.router.dispatch(
            "POST",
            "/api/orchestration/scheduler-handoff",
            {"dag_id": "dag_daily_research", "as_of": "2026-05-18T12:00:00+00:00", "backfill_window_days": 5},
            actor="platform",
            role="platform",
        )
        self.assertTrue(scheduler_handoff.success, scheduler_handoff.error)
        self.assertEqual(scheduler_handoff.data["workflow_count"], 1)
        self.assertEqual(scheduler_handoff.data["recommended_orchestrator"]["recommended"], "airflow_or_dagster")
        self.assertEqual(scheduler_handoff.data["external_sensor_count"], 1)
        self.assertEqual(scheduler_handoff.data["external_sensors"][0]["sensor_id"], "missing_external_sensor")
        self.assertTrue(scheduler_handoff.data["external_deployment_required"])
        self.assertFalse(scheduler_handoff.data["automation_allowed"])
        self.assertIn("scheduler_handoff_is_a_planning_contract", scheduler_handoff.data["usage_boundary"])
        daily_handoff = scheduler_handoff.data["workflows"][0]
        self.assertEqual(daily_handoff["adapter_contract"]["airflow_dag_id"], "dag_daily_research")
        self.assertEqual(daily_handoff["adapter_contract"]["cron_schedule"], "0 9 * * *")
        self.assertGreaterEqual(daily_handoff["backfill"]["candidate_count"], 1)
        self.assertIn("large_window_backfill_run_artifact_uri", scheduler_handoff.data["missing_external_evidence"])

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

    def test_orchestration_readiness_report_requires_external_scheduler_lineage_and_registry_evidence(self) -> None:
        workflow = self.router.dispatch(
            "POST",
            "/api/orchestration/dags",
            {
                "dag_id": "dag_orchestration_ready",
                "name": "Orchestration readiness",
                "cadence": "daily",
                "idempotency_key_fields": ["as_of_date"],
                "tasks": [
                    {"task_id": "collect", "task_type": "noop", "queue": "ingestion", "output_refs": ["doc:ready"]},
                    {"task_id": "extract", "task_type": "noop", "queue": "document_ai", "depends_on": ["collect"], "output_refs": ["evidence:ready"]},
                    {"task_id": "publish", "task_type": "noop", "queue": "registry", "depends_on": ["extract", "external_catalog_sensor"], "output_refs": ["registry:ready"]},
                ],
            },
            actor="platform",
            role="platform",
        )
        self.assertTrue(workflow.success, workflow.error)
        run = self.router.dispatch(
            "POST",
            "/api/orchestration/dags/dag_orchestration_ready/run",
            {
                "run_id": "wfrun_orch_ready_001",
                "inputs": {"as_of_date": "2026-05-15"},
                "status": "succeeded",
                "output_refs": ["registry:ready"],
            },
            actor="platform",
            role="platform",
        )
        self.assertTrue(run.success, run.error)
        model = self.router.dispatch(
            "POST",
            "/api/model-versions",
            {
                "model_version_id": "modelv_orch_ready",
                "model_name": "research-summary",
                "version": "2026-05-17",
                "model_type": "llm",
                "artifact_uri": "models:/research-summary/2026-05-17",
                "training_dataset_ids": ["evidence_ready"],
                "prompt_versions": ["pr_llmtpl_research_summary_v1_baseline"],
                "metrics": {"quality": 0.98, "mlflow_run_id": "mlrun_orch_ready"},
                "status": "approved",
            },
            actor="ml",
            role="nlp_ml",
        )
        self.assertTrue(model.success, model.error)
        lineage = self.router.dispatch(
            "POST",
            "/api/lineage/events",
            {
                "lineage_id": "lin_orch_ready",
                "job_run_id": "wfrun_orch_ready_001",
                "dataset": "evidence_ready",
                "input_refs": ["doc:ready"],
                "output_refs": ["registry:ready"],
                "code_version": "test-v1",
                "model_versions": ["modelv_orch_ready"],
                "prompt_versions": ["pr_llmtpl_research_summary_v1_baseline"],
            },
            actor="platform",
            role="platform",
        )
        self.assertTrue(lineage.success, lineage.error)
        self.router.dispatch(
            "POST",
            "/api/orchestration/openlineage/submit",
            {"dag_id": "dag_orchestration_ready", "namespace": "ai_quant_test", "target": "openlineage://local-catalog"},
            actor="platform",
            role="platform",
        )
        self.router.dispatch(
            "POST",
            "/api/model-versions/mlflow/register",
            {"model_name": "research-summary", "target": "mlflow://local-registry"},
            actor="ml",
            role="nlp_ml",
        )

        gap = self.router.dispatch(
            "POST",
            "/api/orchestration/readiness-report",
            {"dag_id": "dag_orchestration_ready", "as_of": "2026-05-18T12:00:00+00:00"},
            actor="platform",
            role="platform",
        )
        self.assertTrue(gap.success, gap.error)
        self.assertFalse(gap.data["ready_for_orchestration_production"])
        self.assertIn("scheduler_deployment_evidence_uri", gap.data["missing_requirements"])
        self.assertIn("external_sensor_evidence_uri", gap.data["missing_requirements"])
        self.assertIn("backfill_drill_evidence_uri", gap.data["missing_requirements"])
        self.assertIn("openlineage_real_delivery", gap.data["missing_requirements"])
        self.assertIn("mlflow_real_registry", gap.data["missing_requirements"])
        self.assertFalse(gap.data["automation_allowed"])
        self.assertTrue(gap.data["external_deployment_required"])
        self.assertIn("orchestration_readiness_report_checks_scheduler", gap.data["usage_boundary"])

        ready = self.router.dispatch(
            "POST",
            "/api/orchestration/readiness-report",
            {
                "dag_id": "dag_orchestration_ready",
                "as_of": "2026-05-18T12:00:00+00:00",
                "scheduler_endpoint": "https://airflow.staging.example.com",
                "openlineage_endpoint": "https://lineage.staging.example.com",
                "mlflow_endpoint": "https://mlflow.staging.example.com",
                "artifact_uris": {
                    "scheduler_deployment_uri": "artifact://orchestration/scheduler-deployment.json",
                    "worker_pool_evidence_uri": "artifact://orchestration/worker-pools.json",
                    "external_sensor_evidence_uri": "artifact://orchestration/external-sensors.json",
                    "backfill_drill_uri": "artifact://orchestration/backfill-drill.json",
                    "openlineage_delivery_evidence_uri": "artifact://orchestration/openlineage-delivery.json",
                    "mlflow_registry_evidence_uri": "artifact://orchestration/mlflow-registry.json",
                    "replay_runbook_uri": "artifact://orchestration/replay-runbook.md",
                },
                "record_readiness": True,
            },
            actor="platform",
            role="platform",
        )
        self.assertTrue(ready.success, ready.error)
        self.assertTrue(ready.data["ready_for_orchestration_production"])
        self.assertEqual(ready.data["missing_requirements"], [])
        self.assertEqual(ready.data["workflow_summary"]["external_sensor_count"], 1)
        self.assertEqual(ready.data["lineage"]["openlineage_export_count"], 1)
        self.assertEqual(ready.data["model_registry"]["approved_artifact_coverage"], 1.0)
        self.assertEqual(self.service.store.audit_log[-1].action, "orchestration_readiness_report")

        simple_workflow = self.router.dispatch(
            "POST",
            "/api/orchestration/dags",
            {
                "dag_id": "dag_orchestration_simple",
                "name": "Single queue reviewed orchestration",
                "cadence": "manual",
                "tasks": [{"task_id": "noop", "task_type": "noop", "queue": "default"}],
            },
            actor="platform",
            role="platform",
        )
        self.assertTrue(simple_workflow.success, simple_workflow.error)
        simple_gap = self.router.dispatch(
            "POST",
            "/api/orchestration/readiness-report",
            {
                "dag_id": "dag_orchestration_simple",
                "scheduler_endpoint": "https://airflow.staging.example.com",
                "openlineage_endpoint": "https://lineage.staging.example.com",
                "mlflow_endpoint": "https://mlflow.staging.example.com",
                "artifact_uris": {
                    "scheduler_deployment_uri": "artifact://orchestration/scheduler-deployment.json",
                    "openlineage_delivery_evidence_uri": "artifact://orchestration/openlineage-delivery.json",
                    "mlflow_registry_evidence_uri": "artifact://orchestration/mlflow-registry.json",
                    "replay_runbook_uri": "artifact://orchestration/replay-runbook.md",
                },
            },
            actor="platform",
            role="platform",
        )
        self.assertTrue(simple_gap.success, simple_gap.error)
        self.assertFalse(simple_gap.data["ready_for_orchestration_production"])
        self.assertIn("worker_pool_evidence_uri", simple_gap.data["missing_requirements"])
        self.assertIn("external_sensor_evidence_uri", simple_gap.data["missing_requirements"])
        self.assertIn("backfill_drill_evidence_uri", simple_gap.data["missing_requirements"])

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

    def test_workflow_backfill_plans_and_records_queue_isolated_runs(self) -> None:
        workflow = self.router.dispatch(
            "POST",
            "/api/orchestration/dags",
            {
                "dag_id": "dag_queue_backfill",
                "name": "Queue isolated backfill",
                "cadence": "business_daily",
                "idempotency_key_fields": ["as_of_date"],
                "tasks": [
                    {"task_id": "collect", "task_type": "noop", "queue": "ingestion", "payload": {"message": "collect"}},
                    {
                        "task_id": "parse",
                        "task_type": "noop",
                        "queue": "document_ai",
                        "depends_on": ["collect"],
                        "payload": {"message": "parse"},
                    },
                    {
                        "task_id": "evaluate",
                        "task_type": "noop",
                        "queue": "evaluation",
                        "depends_on": ["parse"],
                        "payload": {"message": "evaluate"},
                    },
                ],
            },
            actor="platform",
            role="platform",
        )
        self.assertTrue(workflow.success, workflow.error)

        dry_run = self.router.dispatch(
            "POST",
            "/api/orchestration/dags/dag_queue_backfill/backfill",
            {
                "start_date": "2026-05-15",
                "end_date": "2026-05-18",
                "queues": ["document_ai"],
                "inputs": {"market": "A"},
            },
            actor="platform",
            role="platform",
        )
        self.assertTrue(dry_run.success, dry_run.error)
        self.assertTrue(dry_run.data["dry_run"])
        self.assertEqual(dry_run.data["planned_count"], 2)
        self.assertEqual(dry_run.data["created_count"], 0)
        self.assertEqual(dry_run.data["selection"]["queues"], ["document_ai"])
        planned_dates = [item["run_date"] for item in dry_run.data["plan"]]
        self.assertEqual(planned_dates, ["2026-05-15", "2026-05-18"])
        planned_first = dry_run.data["plan"][0]
        self.assertTrue(planned_first["queue_isolation"])
        self.assertTrue(planned_first["partial_execution"])
        self.assertEqual(planned_first["task_statuses"]["parse"], "queued")
        self.assertEqual(planned_first["task_statuses"]["collect"], "skipped")
        self.assertEqual(self.router.dispatch("GET", "/api/orchestration/runs", {"dag_id": "dag_queue_backfill"}, role="platform").data["total"], 0)

        plan_only = self.router.dispatch(
            "POST",
            "/api/orchestration/dags/dag_queue_backfill/backfill",
            {
                "run_dates": ["2026-05-15"],
                "queues": ["document_ai"],
                "dry_run": False,
                "execute": False,
            },
            actor="platform",
            role="platform",
        )
        self.assertTrue(plan_only.success, plan_only.error)
        self.assertFalse(plan_only.data["dry_run"])
        self.assertFalse(plan_only.data["execute"])
        self.assertEqual(plan_only.data["planned_count"], 1)
        self.assertEqual(plan_only.data["created_count"], 0)
        self.assertEqual(self.router.dispatch("GET", "/api/orchestration/runs", {"dag_id": "dag_queue_backfill"}, role="platform").data["total"], 0)

        execute = self.router.dispatch(
            "POST",
            "/api/orchestration/dags/dag_queue_backfill/backfill",
            {
                "run_dates": ["2026-05-15", "2026-05-18"],
                "queues": "document_ai",
                "inputs": {"market": "A"},
                "dry_run": False,
                "execute": True,
                "run_id_prefix": "wfrun_backfill_queue",
            },
            actor="platform",
            role="platform",
        )
        self.assertTrue(execute.success, execute.error)
        self.assertFalse(execute.data["dry_run"])
        self.assertEqual(execute.data["created_count"], 2)
        self.assertEqual(execute.data["reused_count"], 0)
        self.assertIn("built_in_backfill_planner", execute.data["usage_boundary"])
        first_run = execute.data["runs"][0]
        self.assertEqual(first_run["run_id"], "wfrun_backfill_queue_20260515")
        self.assertEqual(first_run["status"], "queued")
        self.assertEqual(first_run["inputs"]["as_of_date"], "2026-05-15")
        self.assertEqual(first_run["inputs"]["market"], "A")
        self.assertEqual(first_run["inputs"]["backfill"]["selection"]["task_ids"], ["parse"])
        self.assertTrue(first_run["inputs"]["backfill"]["queue_isolation"])
        self.assertEqual(first_run["task_statuses"]["parse"], "queued")
        self.assertEqual(first_run["task_statuses"]["collect"], "skipped")
        self.assertEqual(first_run["task_statuses"]["evaluate"], "skipped")

        duplicate = self.router.dispatch(
            "POST",
            "/api/orchestration/dags/dag_queue_backfill/backfill",
            {
                "run_dates": ["2026-05-15", "2026-05-18"],
                "queues": "document_ai",
                "inputs": {"market": "A"},
                "dry_run": False,
                "execute": True,
            },
            actor="platform",
            role="platform",
        )
        self.assertTrue(duplicate.success, duplicate.error)
        self.assertEqual(duplicate.data["created_count"], 0)
        self.assertEqual(duplicate.data["reused_count"], 2)
        self.assertEqual(duplicate.data["skipped_count"], 2)
        self.assertEqual({item["reason"] for item in duplicate.data["skipped"]}, {"idempotent_run_exists"})
        runs = self.router.dispatch("GET", "/api/orchestration/runs", {"dag_id": "dag_queue_backfill"}, role="platform")
        self.assertTrue(runs.success, runs.error)
        self.assertEqual(runs.data["total"], 2)

        handoff = self.router.dispatch(
            "POST",
            "/api/orchestration/scheduler-handoff",
            {
                "dag_id": "dag_queue_backfill",
                "as_of": "2026-05-20T12:00:00+00:00",
                "backfill_window_days": 10,
            },
            actor="platform",
            role="platform",
        )
        self.assertTrue(handoff.success, handoff.error)
        self.assertEqual(handoff.data["recommended_orchestrator"]["recommended"], "airflow_or_dagster")
        self.assertEqual(handoff.data["queue_count"], 3)
        worker_pools = {item["queue"]: item for item in handoff.data["worker_pools"]}
        self.assertTrue({"ingestion", "document_ai", "evaluation"}.issubset(worker_pools))
        self.assertEqual(worker_pools["document_ai"]["worker_pool"], "wf_document_ai_pool")
        workflow_handoff = handoff.data["workflows"][0]
        self.assertTrue(workflow_handoff["queue_isolation_required"])
        self.assertEqual(workflow_handoff["adapter_contract"]["cron_schedule"], "0 9 * * 1-5")
        self.assertIn("/api/orchestration/dags/dag_queue_backfill/backfill", workflow_handoff["adapter_contract"]["backfill_endpoint"])
        self.assertEqual(workflow_handoff["backfill"]["planned_dates"], ["2026-05-19", "2026-05-20"])
        self.assertIn("worker_pool_deployment_and_queue_binding_evidence", handoff.data["missing_external_evidence"])

    def test_astock_connector_registry_tracks_rights_mapping_and_verification(self) -> None:
        seeded = self.router.dispatch("POST", "/api/connectors/astock/seed", {}, actor="data", role="data_engineer")
        self.assertTrue(seeded.success)
        connector_ids = {item["connector_id"] for item in seeded.data["connectors"]}
        self.assertGreaterEqual(len(connector_ids), 17)
        self.assertNotIn("iwencai_optional", connector_ids)
        for expected_id in {
            "efinance_eastmoney_history",
            "efinance_eastmoney_base_info",
            "efinance_eastmoney_board",
            "akshare_em_history",
            "akshare_em_spot",
            "akshare_chip_distribution",
            "akshare_hot_rank",
            "akshare_limit_up_pool",
            "baostock_eod_history",
            "baostock_stock_basic",
        }:
            self.assertIn(expected_id, connector_ids)
            self.assertFalse(self.service.store.astock_connectors[expected_id].requires_key)
            self.assertIn("supplemental_research", self.service.store.astock_connectors[expected_id].allowed_use)
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

        readiness_gap = self.router.dispatch(
            "POST",
            "/api/connectors/astock/verification-readiness",
            {
                "connector_id": "eastmoney_research",
                "sample_rows": {
                    "eastmoney_research": [
                        {"title": "Demo bank sector research", "url": "https://example.invalid/report?id=1", "published_at": "2026-05-15"}
                    ]
                },
            },
            actor="risk",
            role="risk_compliance",
        )
        self.assertTrue(readiness_gap.success, readiness_gap.error)
        self.assertFalse(readiness_gap.data["ready_for_real_acceptance"])
        self.assertFalse(readiness_gap.data["automation_allowed"])
        gap_row = readiness_gap.data["connectors"][0]
        self.assertIn("real_endpoint_artifact_uri", gap_row["missing_requirements"])
        self.assertIn("endpoint_stability_artifact_uri", gap_row["missing_requirements"])
        self.assertIn("rate_limit_verification_artifact_uri", gap_row["missing_requirements"])
        self.assertIn("license_review_artifact_uri", gap_row["missing_requirements"])
        self.assertIn("field_sample_artifact_uri", gap_row["missing_requirements"])
        self.assertEqual(gap_row["sample_row_count"], 1)
        self.assertIn("source_risk_yellow", gap_row["automation_blockers"])
        self.assertEqual(gap_row["usage_boundary"], "astock_connector_readiness_is_manual_reference_acceptance_not_automated_fact_ingestion")

        readiness_ready = self.router.dispatch(
            "POST",
            "/api/connectors/astock/verification-readiness",
            {
                "connector_id": "eastmoney_research",
                "sample_rows": {
                    "eastmoney_research": [
                        {"title": "Demo bank sector research", "url": "https://example.invalid/report?id=1", "published_at": "2026-05-15"}
                    ]
                },
                "artifact_uris": {
                    "eastmoney_research": {
                        "endpoint_artifact_uri": "s3://ai-quant-evidence/astock/eastmoney-endpoint.json",
                        "stability_artifact_uri": "s3://ai-quant-evidence/astock/eastmoney-stability.json",
                        "rate_limit_artifact_uri": "s3://ai-quant-evidence/astock/eastmoney-rate-limit.json",
                        "license_review_uri": "s3://ai-quant-evidence/astock/eastmoney-license.md",
                        "field_sample_uri": "s3://ai-quant-evidence/astock/eastmoney-sample.jsonl",
                    }
                },
                "record_readiness": True,
            },
            actor="risk",
            role="risk_compliance",
        )
        self.assertTrue(readiness_ready.success, readiness_ready.error)
        self.assertTrue(readiness_ready.data["ready_for_real_acceptance"])
        ready_row = readiness_ready.data["connectors"][0]
        self.assertEqual(ready_row["missing_requirements"], [])
        self.assertFalse(ready_row["automation_allowed"])
        self.assertEqual(ready_row["artifact_uris"]["endpoint_artifact_uri"], "s3://ai-quant-evidence/astock/eastmoney-endpoint.json")
        self.assertEqual(self.service.store.audit_log[-1].action, "astock_connector_verification_readiness")

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
        self.assertIn("local://data/local/tdx/vipdoc", source_rows["public_eod_market_data"]["provenance_ref"])
        self.assertIn("baostock://query_history_k_data_plus", source_rows["public_eod_market_data"]["provenance_ref"])
        self.assertEqual(source_rows["public_eod_market_data"]["collection_method"], "local_tdx_vipdoc_plus_baostock_incremental")
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
        self.assertTrue(source_rows["public_eod_market_data"]["automation_ready"])
        self.assertGreaterEqual(after.data["automation_ready"], 1)

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
                "findings": ["local TDX vipdoc provenance remains an internal research input"],
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
        self.assertLess(metrics.data["counts"]["documents"], 250)
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

    def test_storage_readiness_report_requires_external_storage_search_and_restore_evidence(self) -> None:
        gap = self.router.dispatch("POST", "/api/governance/storage-readiness-report", {}, role="platform")
        self.assertTrue(gap.success, gap.error)
        self.assertFalse(gap.data["ready_for_storage_production"])
        self.assertIn("postgres_runtime_or_config", gap.data["missing_requirements"])
        self.assertIn("s3_object_store_config_or_evidence", gap.data["missing_requirements"])
        self.assertIn("opensearch_config_or_evidence", gap.data["missing_requirements"])
        self.assertIn("backup_restore_record", gap.data["missing_requirements"])
        self.assertIn("postgres_smoke_uri", gap.data["missing_requirements"])
        self.assertIn("s3_smoke_uri", gap.data["missing_requirements"])
        self.assertIn("opensearch_smoke_uri", gap.data["missing_requirements"])
        self.assertFalse(gap.data["automation_allowed"])
        self.assertTrue(gap.data["runtime"]["sensitive_values_redacted"])

        for check_id in ["real_data_smoke_test", "capacity_latency_report", "backup_restore_drill"]:
            recorded = self.router.dispatch(
                "POST",
                f"/api/readiness/checklist/{check_id}",
                {
                    "status": "passed",
                    "owner": "platform_owner",
                    "evidence_uri": f"artifact://storage/{check_id}.json",
                    "metrics": {"accepted": True},
                },
                role="platform",
                actor="platform_owner",
            )
            self.assertTrue(recorded.success, recorded.error)

        local_config_only = self.router.dispatch(
            "POST",
            "/api/governance/storage-readiness-report",
            {
                "postgres_configured": True,
                "s3_configured": True,
                "opensearch_configured": True,
                "runtime": {
                    "postgres_endpoint": "postgresql://app:secret@localhost/ai_quant",
                    "s3_endpoint": "http://127.0.0.1:9000",
                    "opensearch_endpoint": "http://localhost:9200",
                },
                "migration": {"dry_run": True, "applied": True, "rollback_recorded": True},
                "s3_smoke": {"status": "passed", "put_ok": True, "get_ok": True, "checksum_ok": True},
                "opensearch_smoke": {"status": "passed", "indexed": 12, "search_hits": 3},
                "artifact_uris": {
                    "least_privilege_policy_uri": "artifact://storage/least-privilege.json",
                    "postgres_migration_uri": "artifact://storage/postgres-migration.json",
                    "capacity_baseline_uri": "artifact://storage/capacity.json",
                    "backup_restore_uri": "artifact://storage/backup-restore.json",
                },
            },
            role="platform",
            actor="platform_owner",
        )
        self.assertTrue(local_config_only.success, local_config_only.error)
        self.assertFalse(local_config_only.data["ready_for_storage_production"])
        self.assertIn("postgres_runtime_or_config", local_config_only.data["missing_requirements"])
        self.assertIn("s3_object_store_config_or_evidence", local_config_only.data["missing_requirements"])
        self.assertIn("opensearch_config_or_evidence", local_config_only.data["missing_requirements"])
        self.assertIn("postgres_smoke_uri", local_config_only.data["missing_requirements"])
        self.assertIn("s3_smoke_uri", local_config_only.data["missing_requirements"])
        self.assertIn("opensearch_smoke_uri", local_config_only.data["missing_requirements"])
        self.assertTrue(local_config_only.data["object_store"]["external_smoke_present"])
        self.assertTrue(local_config_only.data["search_index"]["external_smoke_present"])

        local_artifacts_only = self.router.dispatch(
            "POST",
            "/api/governance/storage-readiness-report",
            {
                "postgres_configured": True,
                "s3_configured": True,
                "opensearch_configured": True,
                "runtime": {
                    "postgres_endpoint": "postgresql://app:secret@postgres.prod.internal/ai_quant",
                    "s3_endpoint": "https://objects.prod.example.test",
                    "opensearch_endpoint": "https://search.prod.example.test",
                },
                "migration": {"dry_run": True, "applied": True, "rollback_recorded": True},
                "s3_smoke": {"status": "passed", "put_ok": True, "get_ok": True, "checksum_ok": True},
                "opensearch_smoke": {"status": "passed", "indexed": 12, "search_hits": 3},
                "artifact_uris": {
                    "postgres_smoke_uri": "file:///tmp/postgres-smoke.json",
                    "s3_smoke_uri": "local://storage/s3-smoke.json",
                    "opensearch_smoke_uri": "/tmp/opensearch-smoke.json",
                    "capacity_baseline_uri": "file:///tmp/capacity.json",
                    "backup_restore_uri": "local://storage/backup-restore.json",
                    "least_privilege_policy_uri": "file:///tmp/least-privilege.json",
                    "postgres_migration_uri": "local://storage/postgres-migration.json",
                },
            },
            role="platform",
            actor="platform_owner",
        )
        self.assertTrue(local_artifacts_only.success, local_artifacts_only.error)
        self.assertFalse(local_artifacts_only.data["ready_for_storage_production"])
        self.assertIn("least_privilege_policy_uri", local_artifacts_only.data["missing_requirements"])
        self.assertIn("postgres_migration_evidence", local_artifacts_only.data["missing_requirements"])
        self.assertIn("postgres_smoke_uri", local_artifacts_only.data["missing_requirements"])
        self.assertIn("s3_smoke_uri", local_artifacts_only.data["missing_requirements"])
        self.assertEqual(local_artifacts_only.data["artifact_uris"]["postgres_smoke_uri"], "")

        service_uri_artifacts = self.router.dispatch(
            "POST",
            "/api/governance/storage-readiness-report",
            {
                "postgres_configured": True,
                "s3_configured": True,
                "opensearch_configured": True,
                "runtime": {
                    "postgres_endpoint": "postgresql://app:secret@postgres.prod.internal/ai_quant",
                    "s3_endpoint": "https://objects.prod.example.test",
                    "opensearch_endpoint": "https://search.prod.example.test",
                },
                "migration": {"dry_run": True, "applied": True, "rollback_recorded": True},
                "s3_smoke": {"status": "passed", "put_ok": True, "get_ok": True, "checksum_ok": True},
                "opensearch_smoke": {"status": "passed", "indexed": 12, "search_hits": 3},
                "artifact_uris": {
                    "postgres_smoke_uri": "postgresql://app:secret@postgres.prod.internal/ai_quant",
                    "s3_smoke_uri": "https://objects.prod.example.test",
                    "opensearch_smoke_uri": "opensearch://search.prod.example.test/ai-quant",
                    "least_privilege_policy_uri": "artifact://storage/least-privilege.json",
                    "postgres_migration_uri": "artifact://storage/postgres-migration.json",
                },
            },
            role="platform",
            actor="platform_owner",
        )
        self.assertTrue(service_uri_artifacts.success, service_uri_artifacts.error)
        self.assertFalse(service_uri_artifacts.data["ready_for_storage_production"])
        self.assertIn("postgres_smoke_uri", service_uri_artifacts.data["missing_requirements"])
        self.assertIn("s3_smoke_uri", service_uri_artifacts.data["missing_requirements"])
        self.assertIn("opensearch_smoke_uri", service_uri_artifacts.data["missing_requirements"])
        self.assertEqual(service_uri_artifacts.data["artifact_uris"]["postgres_smoke_uri"], "")
        self.assertEqual(service_uri_artifacts.data["artifact_uris"]["opensearch_smoke_uri"], "")
        self.assertEqual(service_uri_artifacts.data["artifact_uris"]["s3_smoke_uri"], "")

        ready = self.router.dispatch(
            "POST",
            "/api/governance/storage-readiness-report",
            {
                "postgres_configured": True,
                "s3_configured": True,
                "opensearch_configured": True,
                "runtime": {
                    "postgres_endpoint": "postgresql://app:secret@postgres.prod.internal/ai_quant",
                    "s3_endpoint": "https://objects.prod.example.test",
                    "opensearch_endpoint": "https://search.prod.example.test",
                },
                "migration": {"dry_run": True, "applied": True, "rollback_recorded": True},
                "s3_smoke": {"status": "passed", "put_ok": True, "get_ok": True, "checksum_ok": True},
                "opensearch_smoke": {"status": "passed", "indexed": 12, "search_hits": 3},
                "artifact_uris": {
                    "postgres_smoke_uri": "artifact://storage/postgres-smoke.json",
                    "s3_smoke_uri": "artifact://storage/s3-smoke.json",
                    "opensearch_smoke_uri": "artifact://storage/opensearch-smoke.json",
                    "capacity_baseline_uri": "artifact://storage/capacity.json",
                    "backup_restore_uri": "artifact://storage/backup-restore.json",
                    "least_privilege_policy_uri": "artifact://storage/least-privilege.json",
                    "postgres_migration_uri": "artifact://storage/postgres-migration.json",
                },
                "record_readiness": True,
            },
            role="platform",
            actor="platform_owner",
        )
        self.assertTrue(ready.success, ready.error)
        self.assertTrue(ready.data["ready_for_storage_production"])
        self.assertEqual(ready.data["missing_requirements"], [])
        self.assertTrue(ready.data["runtime"]["postgres_configured"])
        self.assertNotIn("secret", ready.data["runtime"]["postgres_endpoint_redacted"])
        self.assertTrue(ready.data["object_store"]["external_smoke_present"])
        self.assertTrue(ready.data["search_index"]["external_smoke_present"])
        self.assertEqual(self.service.store.audit_log[-1].action, "storage_readiness_report")

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

    def test_portfolio_attribution_readiness_report_tracks_reports_replays_and_ledger(self) -> None:
        self.router.dispatch("POST", "/api/ingestion/sources/seed", {}, role="data_engineer")
        self.service.register_security(
            {
                "security_id": "sec_attr_ready_2",
                "issuer_id": "issuer_001",
                "ticker": "ATTR2",
                "exchange": "SSE",
                "currency": "CNY",
                "market": "A",
            },
            actor="platform",
        )
        for payload in [
            {"data_id": "md_attr_r1_d1", "security_id": "sec_001", "as_of_date": "2026-05-14", "close": 10.0, "adjusted_close": 10.0, "volume": 100},
            {"data_id": "md_attr_r1_d2", "security_id": "sec_001", "as_of_date": "2026-05-15", "close": 11.0, "adjusted_close": 11.0, "volume": 100},
            {"data_id": "md_attr_r2_d1", "security_id": "sec_attr_ready_2", "as_of_date": "2026-05-14", "close": 20.0, "adjusted_close": 20.0, "volume": 100},
            {"data_id": "md_attr_r2_d2", "security_id": "sec_attr_ready_2", "as_of_date": "2026-05-15", "close": 19.0, "adjusted_close": 19.0, "volume": 100},
        ]:
            created = self.router.dispatch("POST", "/api/market-data/points", {"source_id": "public_eod_market_data", "data_type": "eod", **payload}, role="data_engineer")
            self.assertTrue(created.success, created.error)

        report = self.router.dispatch(
            "POST",
            "/api/operating-reports",
            {
                "report_id": "opr_attr_ready",
                "period": "2026-05",
                "portfolio_returns": [0.02, -0.01],
                "benchmark_returns": [0.01, -0.005],
                "red_flags": [{"type": "attribution_review", "owner": "风险/合规", "due": "month_end"}],
            },
            role="CEO",
            actor="ceo_owner",
        )
        self.assertTrue(report.success, report.error)
        gap = self.router.dispatch("POST", "/api/portfolio/attribution/readiness-report", {}, role="CIO")
        self.assertTrue(gap.success, gap.error)
        self.assertFalse(gap.data["ready_for_attribution_production"])
        self.assertIn("attribution_annotation_coverage", gap.data["missing_requirements"])
        self.assertIn("strategy_replay_count", gap.data["missing_requirements"])
        self.assertIn("simulated_ledger_transaction_count", gap.data["missing_requirements"])
        self.assertIn("forward_attribution_evidence", gap.data["missing_requirements"])
        self.assertIn("forward_attribution_artifact_uri", gap.data["missing_requirements"])
        self.assertIn("performance_reconciliation_uri", gap.data["missing_requirements"])
        self.assertIn("ledger_extract_artifact_uri", gap.data["missing_requirements"])
        self.assertIn("strategy_replay_artifact_uri", gap.data["missing_requirements"])
        self.assertIn("board_pack_artifact_uri", gap.data["missing_requirements"])
        self.assertFalse(gap.data["live_execution_allowed"])

        backfill = self.router.dispatch(
            "POST",
            "/api/portfolio/attribution/backfill",
            {
                "holdings": [
                    {"security_id": "sec_001", "weight": 0.6},
                    {"security_id": "sec_attr_ready_2", "weight": 0.4},
                ],
                "start_date": "2026-05-14",
                "end_date": "2026-05-15",
                "target_report_ids": ["opr_attr_ready"],
                "groups": {
                    "sec_001": {"industry": "software", "style": "quality"},
                    "sec_attr_ready_2": {"industry": "hardware", "style": "value"},
                },
            },
            role="CIO",
            actor="pm_owner",
        )
        self.assertTrue(backfill.success, backfill.error)
        self.assertEqual(backfill.data["annotated_count"], 1)
        self.assertIn("portfolio_attribution", self.service.store.operating_reports["opr_attr_ready"].annotations)
        published = self.router.dispatch(
            "POST",
            "/api/operating-reports/opr_attr_ready/publish",
            {"approver_role": "CEO", "user": "ceo_owner", "comment": "attribution reviewed"},
            role="CEO",
            actor="ceo_owner",
        )
        self.assertTrue(published.success, published.error)
        self.service.store.decisions["dec_attr_ready"] = DecisionPack(
            decision_id="dec_attr_ready",
            signal_ids=[],
            risk_checks=["paper_attribution_review"],
            approval_state="approved",
        )
        self.service.create_strategy_replay(
            {
                "replay_id": "replay_attr_ready",
                "decision_id": "dec_attr_ready",
                "expected_outcome": "relative return positive",
                "actual_outcome": "relative return positive",
                "variance_reason": "hardware drag offset software selection",
                "next_action": "keep paper tracking",
                "version": "v1",
            },
            actor="cio",
        )
        imported = self.router.dispatch(
            "POST",
            "/api/portfolio/transactions/import",
            {
                "rows": [
                    {"trade_id": "attr_fill_1", "ticker": "DEMO", "date": "2026-05-14", "signed_qty": 100, "avg_price": 10.0},
                    {"trade_id": "attr_fill_2", "ticker": "ATTR2", "date": "2026-05-14", "signed_qty": 100, "avg_price": 20.0},
                ],
                "security_map": {"DEMO": "sec_001", "ATTR2": "sec_attr_ready_2"},
            },
            role="PM",
            actor="pm_owner",
        )
        self.assertTrue(imported.success, imported.error)
        forward = self.router.dispatch(
            "POST",
            "/api/portfolio/returns",
            {"weights": {"sec_001": 0.6, "sec_attr_ready_2": 0.4}, "source_id": "public_eod_market_data", "data_type": "eod"},
            role="CIO",
        )
        self.assertTrue(forward.success, forward.error)

        exported_board_pack = self.router.dispatch(
            "POST",
            "/api/operating-reports/opr_attr_ready/board-pack",
            {},
            role="CEO",
            actor="ceo_owner",
        )
        self.assertTrue(exported_board_pack.success, exported_board_pack.error)
        local_export_only = self.router.dispatch(
            "POST",
            "/api/portfolio/attribution/readiness-report",
            {
                "forward_report": {
                    "return_count": forward.data["return_count"],
                    "attribution": forward.data["attribution"],
                    "simulation_only": True,
                    "live_execution_allowed": False,
                },
                "artifact_uris": {
                    "performance_reconciliation_uri": "artifact://staging/performance-reconciliation.json",
                    "ledger_extract_uri": "artifact://staging/simulated-ledger.json",
                    "strategy_replay_uri": "artifact://staging/strategy-replay-compare.json",
                },
            },
            role="CIO",
        )
        self.assertTrue(local_export_only.success, local_export_only.error)
        self.assertFalse(local_export_only.data["ready_for_attribution_production"])
        self.assertGreaterEqual(local_export_only.data["operating_reports"]["board_pack_export_count"], 1)
        self.assertIn("board_pack_artifact_uri", local_export_only.data["missing_requirements"])

        ready = self.router.dispatch(
            "POST",
            "/api/portfolio/attribution/readiness-report",
            {
                "record_readiness": True,
                "forward_report": {
                    "return_count": forward.data["return_count"],
                    "attribution": forward.data["attribution"],
                    "simulation_only": True,
                    "live_execution_allowed": False,
                },
                "artifact_uris": {
                    "forward_attribution_uri": "artifact://staging/forward-attribution.json",
                    "performance_reconciliation_uri": "artifact://staging/performance-reconciliation.json",
                    "board_pack_uri": "artifact://staging/opr-attr-ready-board-pack.md",
                    "ledger_extract_uri": "artifact://staging/simulated-ledger.json",
                    "strategy_replay_uri": "artifact://staging/strategy-replay-compare.json",
                },
            },
            role="CIO",
            actor="cio_owner",
        )
        self.assertTrue(ready.success, ready.error)
        self.assertTrue(ready.data["ready_for_attribution_production"])
        self.assertEqual(ready.data["missing_requirements"], [])
        self.assertEqual(ready.data["operating_reports"]["attribution_annotated_count"], 1)
        self.assertFalse(ready.data["ledger"]["live_broker_source_seen"])
        self.assertEqual(self.service.store.audit_log[-1].action, "portfolio_attribution_readiness_report")

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

    def test_portfolio_transaction_import_accepts_backtest_alias_rows(self) -> None:
        self.router.dispatch("POST", "/api/ingestion/sources/seed", {}, role="data_engineer")
        rows = [
            {
                "trade_id": "bt_fill_001",
                "symbol": "DEMO",
                "datetime": "20260514 09:30:00",
                "action": "BUY",
                "shares": 100,
                "fill_price": 10.0,
                "commission": 1.0,
                "portfolio_id": "paper_alias",
                "strategy": "backtest_v1",
            },
            {
                "trade_id": "bt_fill_002",
                "ticker": "DEMO",
                "date": "2026-05-15",
                "signed_qty": -40,
                "avg_price": 11.0,
                "fee": 1.0,
                "portfolio_id": "paper_alias",
                "strategy": "backtest_v1",
            },
        ]
        dry_run = self.router.dispatch(
            "POST",
            "/api/portfolio/transactions/import",
            {"rows": rows, "dry_run": True},
            role="PM",
        )
        self.assertTrue(dry_run.success, dry_run.error)
        self.assertTrue(dry_run.data["dry_run"])
        self.assertEqual(dry_run.data["normalized_count"], 2)
        self.assertEqual(dry_run.data["created_count"], 0)
        self.assertEqual(dry_run.data["normalized"][1]["side"], "sell")
        self.assertEqual(dry_run.data["normalized"][1]["quantity"], 40.0)
        self.assertEqual(dry_run.data["usage_boundary"], "portfolio_transaction_import_accepts_simulated_or_backtest_ledgers_only_no_broker_execution")

        imported = self.router.dispatch(
            "POST",
            "/api/portfolio/transactions/import",
            {"rows": rows},
            actor="pm",
            role="PM",
        )
        self.assertTrue(imported.success, imported.error)
        self.assertFalse(imported.data["dry_run"])
        self.assertEqual(imported.data["source_id"], "simulated_trade_execution")
        self.assertEqual(imported.data["created_count"], 2)
        self.assertEqual(imported.data["failed_count"], 0)
        self.assertTrue(imported.data["simulation_only"])
        self.assertFalse(imported.data["live_execution_allowed"])

        duplicate = self.router.dispatch(
            "POST",
            "/api/portfolio/transactions/import",
            {"rows": rows},
            role="PM",
        )
        self.assertTrue(duplicate.success, duplicate.error)
        self.assertEqual(duplicate.data["created_count"], 0)
        self.assertEqual(duplicate.data["skipped_count"], 2)

        positions = self.router.dispatch(
            "GET",
            "/api/portfolio/positions",
            {"account_id": "paper_alias", "strategy_id": "backtest_v1", "as_of_date": "2026-05-15"},
            role="PM",
        )
        self.assertTrue(positions.success, positions.error)
        self.assertEqual(positions.data["position_count"], 1)
        self.assertEqual(positions.data["positions"][0]["shares"], 60.0)

    def test_tdx_market_data_preview_and_import_use_public_eod_path(self) -> None:
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

            self.service.tdx_market_data = TDXVipdocAdapter(path=vipdoc_root)
            self.service.tdx_vipdoc = self.service.tdx_market_data
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
                {"source_format": "vipdoc", "symbols": ["sh600000"], "start_date": "2026-05-14", "end_date": "2026-05-15", "limit": 10},
                role="data_engineer",
            )
            self.assertTrue(preview.success, preview.error)
            self.assertEqual(preview.data["count"], 2)
            self.assertEqual(preview.data["rows"][0]["symbol"], "600000")

            imported = self.router.dispatch(
                "POST",
                "/api/market-data/tdx/import",
                {"source_format": "vipdoc", "symbols": ["600000"], "start_date": "2026-05-14", "end_date": "2026-05-15", "limit": 10},
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
                {"source_format": "vipdoc", "symbols": ["600000"], "start_date": "2026-05-14", "end_date": "2026-05-15", "limit": 10},
                role="data_engineer",
            )
            self.assertTrue(duplicate.success)
            self.assertEqual(duplicate.data["created_count"], 0)
            self.assertEqual(duplicate.data["skipped_count"], 2)

    def test_market_data_backfill_covers_ashare_tdx_and_baostock_gap(self) -> None:
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
            self.service.tdx_market_data = TDXVipdocAdapter(path=vipdoc_root)
            self.service.tdx_vipdoc = self.service.tdx_market_data
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

            self.service._open_baostock_session = lambda: object()  # type: ignore[method-assign]
            self.service._close_baostock_session = lambda _client: None  # type: ignore[method-assign]
            self.service._discover_ashare_baostock_symbols = lambda _client, **_kwargs: [{"symbol": "600000", "name": "浦发银行", "market": "A"}]  # type: ignore[method-assign]
            self.service._fetch_ashare_baostock_rows = lambda _client, symbol, **_kwargs: [  # type: ignore[method-assign]
                {"as_of_date": "2026-05-16", "open": 11.0, "high": 11.3, "low": 10.9, "close": 11.2, "adjusted_close": 11.2, "volume": 1300.0}
            ]

            dry_run = self.router.dispatch(
                "POST",
                "/api/market-data/backfill",
                {"market": "A", "symbols": ["600000"], "start_date": "2026-05-14", "end_date": "2026-05-16", "dry_run": True},
                role="data_engineer",
            )
            self.assertTrue(dry_run.success, dry_run.error)
            self.assertEqual(dry_run.data["planned_count"], 3)
            self.assertEqual(len(self.service.store.market_data), 0)

            imported = self.router.dispatch(
                "POST",
                "/api/market-data/backfill",
                {"market": "A", "symbols": ["600000"], "start_date": "2026-05-14", "end_date": "2026-05-16"},
                role="data_engineer",
            )
            self.assertTrue(imported.success, imported.error)
            self.assertEqual(imported.data["created_count"], 3)
            self.assertEqual(imported.data["failed_symbol_count"], 0)
            listed = self.router.dispatch("GET", "/api/market-data", {"security_id": "sec_600000", "limit": 5}, role="CEO")
            self.assertEqual([row["as_of_date"] for row in reversed(listed.data["market_data"])], ["2026-05-14", "2026-05-15", "2026-05-16"])

            duplicate = self.router.dispatch(
                "POST",
                "/api/market-data/backfill",
                {"market": "A", "symbols": ["600000"], "start_date": "2026-05-14", "end_date": "2026-05-16"},
                role="data_engineer",
            )
            self.assertTrue(duplicate.success, duplicate.error)
            self.assertEqual(duplicate.data["created_count"], 0)
            self.assertEqual(duplicate.data["skipped_count"], 3)

    def test_market_data_backfill_uses_baostock_when_tdx_file_missing(self) -> None:
        with TemporaryDirectory() as temp_dir:
            self.service.tdx_market_data = TDXVipdocAdapter(path=Path(temp_dir) / "vipdoc")
            self.service.tdx_vipdoc = self.service.tdx_market_data
            self.service.register_security(
                {
                    "security_id": "sec_000001",
                    "issuer_id": "issuer_001",
                    "ticker": "000001",
                    "exchange": "SZSE",
                    "currency": "CNY",
                    "market": "A",
                },
                actor="platform",
            )
            self.service._open_baostock_session = lambda: object()  # type: ignore[method-assign]
            self.service._close_baostock_session = lambda _client: None  # type: ignore[method-assign]
            self.service._fetch_ashare_baostock_rows = lambda _client, symbol, **_kwargs: [  # type: ignore[method-assign]
                {"as_of_date": "2026-05-16", "open": 10.0, "high": 10.4, "low": 9.9, "close": 10.2, "adjusted_close": 10.2, "volume": 1000.0}
            ]
            backfill = self.router.dispatch(
                "POST",
                "/api/market-data/backfill",
                {"market": "A", "symbols": ["000001"], "start_date": "2026-05-16", "end_date": "2026-05-16"},
                role="data_engineer",
            )
            self.assertTrue(backfill.success, backfill.error)
            self.assertEqual(backfill.data["created_count"], 1)
            row = backfill.data["markets"]["A"]["symbol_results"][0]
            self.assertEqual(row["provider_errors"][0]["provider"], "tdx_vipdoc")

    def test_market_data_backfill_covers_us_yahoo_discovery_and_failures(self) -> None:
        self.service.seed_default_sources(actor="data")
        self.service.register_issuer(
            {"issuer_id": "issuer_aapl", "legal_name": "Apple Inc.", "market": ["U"], "country": "US"},
            actor="platform",
        )
        self.service.register_security(
            {
                "security_id": "security_aapl_us",
                "issuer_id": "issuer_aapl",
                "ticker": "AAPL",
                "exchange": "NASDAQ",
                "currency": "USD",
                "market": "U",
            },
            actor="platform",
        )
        self.service._fetch_us_symbol_directory = lambda **_kwargs: [  # type: ignore[method-assign]
            {"symbol": "AAPL", "name": "Apple Inc.", "market": "U", "exchange": "NASDAQ"},
            {"symbol": "MSFT", "name": "Microsoft Corporation", "market": "U", "exchange": "NASDAQ"},
            {"symbol": "BAD", "name": "Broken Corp", "market": "U", "exchange": "NYSE"},
        ]

        def fake_yahoo(symbol: str, **_kwargs):
            if symbol == "BAD":
                raise RuntimeError("chart outage")
            return [{"as_of_date": "2026-05-22", "open": 100.0, "high": 102.0, "low": 99.0, "close": 101.0, "adjusted_close": 101.0, "volume": 1000.0}]

        self.service._fetch_us_yahoo_rows = fake_yahoo  # type: ignore[method-assign]
        backfill = self.router.dispatch(
            "POST",
            "/api/market-data/backfill",
            {"market": "U", "discover_universe": True, "start_date": "2026-05-22", "end_date": "2026-05-22"},
            role="data_engineer",
        )
        self.assertTrue(backfill.success, backfill.error)
        self.assertEqual(backfill.data["status"], "partial")
        self.assertEqual(backfill.data["created_count"], 2)
        self.assertEqual(backfill.data["failed_symbol_count"], 1)
        self.assertIn("security_aapl_us", self.service.store.securities)
        self.assertNotIn("security_us_aapl", self.service.store.securities)
        self.assertIn("security_msft_us", self.service.store.securities)
        coverage = self.router.dispatch("GET", "/api/market-data/backfill/coverage-report", {"market": "U", "as_of_date": "2026-05-24"}, role="CEO")
        self.assertTrue(coverage.success, coverage.error)
        self.assertEqual(coverage.data["markets"]["U"]["covered_count"], 2)

    def test_us_yahoo_fetch_uses_utc_dates_and_symbol_variants(self) -> None:
        calls: list[str] = []

        class FakeResponse:
            def __init__(self, payload: dict):
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return None

            def read(self) -> bytes:
                return json.dumps(self.payload).encode("utf-8")

        def fake_urlopen(request, timeout):
            calls.append(request.full_url)
            if "BF.B" in request.full_url:
                return FakeResponse({"chart": {"result": [{"timestamp": []}], "error": None}})
            return FakeResponse(
                {
                    "chart": {
                        "result": [
                            {
                                "timestamp": [1779408000],
                                "indicators": {
                                    "quote": [
                                        {
                                            "open": [10.0],
                                            "high": [11.0],
                                            "low": [9.0],
                                            "close": [10.5],
                                            "volume": [100.0],
                                        }
                                    ],
                                    "adjclose": [{"adjclose": [10.25]}],
                                },
                            }
                        ],
                        "error": None,
                    }
                }
            )

        original_urlopen = services_module.urlopen
        services_module.urlopen = fake_urlopen  # type: ignore[assignment]
        try:
            rows = self.service._fetch_us_yahoo_rows("BF.B", start_date="2026-05-22", end_date="2026-05-22", user_agent="test", timeout=1.0)
        finally:
            services_module.urlopen = original_urlopen  # type: ignore[assignment]

        self.assertEqual(rows[0]["as_of_date"], "2026-05-22")
        self.assertIn("period1=1779408000", calls[0])
        self.assertIn("period2=1779494400", calls[0])
        self.assertIn("/BF.B?", calls[0])
        self.assertIn("/BF-B?", calls[1])

    def test_workflow_executor_and_cli_can_run_market_data_backfill(self) -> None:
        self.service.seed_default_sources(actor="data")
        self.service.register_issuer(
            {"issuer_id": "issuer_aapl", "legal_name": "Apple Inc.", "market": ["U"], "country": "US"},
            actor="platform",
        )
        self.service.register_security(
            {
                "security_id": "security_aapl_us",
                "issuer_id": "issuer_aapl",
                "ticker": "AAPL",
                "exchange": "NASDAQ",
                "currency": "USD",
                "market": "U",
            },
            actor="platform",
        )
        self.service._fetch_us_yahoo_rows = lambda symbol, **_kwargs: [  # type: ignore[method-assign]
            {"as_of_date": "2026-05-22", "open": 100.0, "high": 102.0, "low": 99.0, "close": 101.0, "adjusted_close": 101.0, "volume": 1000.0}
        ]
        workflow = self.router.dispatch(
            "POST",
            "/api/orchestration/dags",
            {
                "dag_id": "dag_market_data_backfill",
                "name": "Market data backfill",
                "cadence": "business_daily",
                "idempotency_key_fields": ["as_of_date"],
                "tasks": [
                    {
                        "task_id": "backfill_us",
                        "task_type": "market_data_backfill",
                        "dataset": "market_data",
                        "payload": {"market": "U", "symbols": ["AAPL"], "start_date": "2026-05-22", "end_date": "2026-05-22"},
                    }
                ],
            },
            actor="platform",
            role="platform",
        )
        self.assertTrue(workflow.success, workflow.error)
        execute = self.router.dispatch(
            "POST",
            "/api/orchestration/dags/dag_market_data_backfill/execute",
            {"run_id": "wfrun_market_data_backfill", "inputs": {"as_of_date": "2026-05-22"}},
            actor="platform",
            role="platform",
        )
        self.assertTrue(execute.success, execute.error)
        self.assertEqual(execute.data["run"]["task_statuses"]["backfill_us"], "succeeded")
        self.assertIn("market_data_backfill:", execute.data["run"]["output_refs"][0])
        self.assertEqual(execute.data["lineage_events"][0]["dataset"], "market_data")

        original_service = backfill_market_data_script.SystemService
        original_store = backfill_market_data_script.SQLiteStore
        try:
            class FakeStore:
                def __init__(self, path):
                    self.path = path

                def commit(self):
                    return None

            class FakeService:
                def __init__(self, store):
                    self.store = store

                def market_data_backfill(self, payload, *, actor):
                    return {"batch_id": "cli_backfill", "payload": payload, "actor": actor, "status": "passed"}

            backfill_market_data_script.SQLiteStore = FakeStore  # type: ignore[assignment]
            backfill_market_data_script.SystemService = FakeService  # type: ignore[assignment]
            args = type(
                "Args",
                (),
                {
                    "postgres_dsn": "",
                    "state_db": "state.sqlite",
                    "market": "both",
                    "discover_universe": True,
                    "symbols": "",
                    "start_date": "",
                    "end_date": "",
                    "fallback_window_days": 10,
                    "offset": 0,
                    "max_symbols": 25,
                    "dry_run": True,
                    "no_skip_existing": False,
                    "refresh_existing": False,
                    "include_etf": False,
                    "include_b_shares": False,
                    "symbol_prefix": "",
                    "batch_id": "cli_backfill",
                    "actor": "cli_test",
                },
            )()
            cli_result = backfill_market_data_script.run_backfill(args)
        finally:
            backfill_market_data_script.SystemService = original_service  # type: ignore[assignment]
            backfill_market_data_script.SQLiteStore = original_store  # type: ignore[assignment]
        self.assertEqual(cli_result["batch_id"], "cli_backfill")
        self.assertTrue(cli_result["payload"]["dry_run"])

    def test_tdx_batch_import_helpers_normalize_symbol_and_exchange(self) -> None:
        self.assertEqual(normalize_symbol("sh600000"), "600000")
        self.assertEqual(normalize_symbol("000001.SZ"), "000001")
        self.assertEqual(normalize_symbol("600519.XSHG"), "600519")
        self.assertEqual(infer_exchange("600519"), "SSE")
        self.assertEqual(infer_exchange("300750"), "SZSE")
        self.assertEqual(infer_exchange("430047"), "BSE")

    def test_tdx_vipdoc_adapter_reads_symbols_and_summary(self) -> None:
        with TemporaryDirectory() as temp_dir:
            vipdoc_root = Path(temp_dir) / "vipdoc"
            day_dir = vipdoc_root / "sh" / "lday"
            day_dir.mkdir(parents=True)
            (day_dir / "sh600000.day").write_bytes(struct.pack("<IIIIIfII", 20260514, 1000, 1080, 990, 1050, 12600.0, 1200, 0))
            adapter = TDXVipdocAdapter(path=vipdoc_root)
            rows = adapter.query_daily(symbols=["600000.SH"], start_date="2026-05-14", end_date="2026-05-14", limit=10)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["symbol"], "600000")
            self.assertEqual(rows[0]["trade_date"], "2026-05-14")
            self.assertEqual(rows[0]["close"], 10.5)
            self.assertEqual(rows[0]["volume"], 1200.0)
            self.assertEqual(rows[0]["amount"], 12600.0)
            self.assertIsNone(rows[0]["turnover"])
            summary = adapter.summary()
            self.assertEqual(summary["files"], 1)
            self.assertEqual(adapter.symbols(prefix="600", limit=5), ["600000"])

    def test_market_data_schema_coverage_report_maps_tdx_aliases_to_public_eod_fields(self) -> None:
        with TemporaryDirectory() as temp_dir:
            vipdoc_root = Path(temp_dir) / "vipdoc"
            day_dir = vipdoc_root / "sh" / "lday"
            day_dir.mkdir(parents=True)
            (day_dir / "sh600000.day").write_bytes(struct.pack("<IIIIIfII", 20260514, 1000, 1080, 990, 1050, 12600.0, 1200, 0))
            self.service.tdx_market_data = TDXVipdocAdapter(path=vipdoc_root)
            self.service.tdx_vipdoc = self.service.tdx_market_data

            report = self.router.dispatch(
                "GET",
                "/api/market-data/schema-coverage-report",
                {},
                role="data_engineer",
            )
            self.assertTrue(report.success, report.error)
            self.assertEqual(report.data["schema_count"], 1)
            self.assertEqual(report.data["recognized_schema_count"], 1)
            self.assertEqual(report.data["schema_recognition_coverage"], 1.0)
            self.assertEqual(report.data["target_field_coverage"], 1.0)
            self.assertTrue(report.data["automation_ready"])
            self.assertEqual(report.data["automation_blockers"], [])
            table = report.data["tables"][0]
            self.assertTrue(table["table"].endswith("sh600000.day"))
            self.assertEqual(table["target_field_mapping"]["security_id"], "file_name")
            self.assertEqual(table["target_field_mapping"]["as_of_date"], "record.date")
            self.assertEqual(table["target_field_mapping"]["adjusted_close"], "record.close")
            self.assertEqual(report.data["usage_boundary"], "schema_coverage_report_only_validates_public_eod_field_mapping_no_market_data_is_imported")

    def test_market_data_schema_coverage_report_flags_anomaly_samples(self) -> None:
        report = self.router.dispatch(
            "POST",
            "/api/market-data/schema-coverage-report",
            {
                "schema_samples": [
                    {
                        "table": "bad_realtime_ticks",
                        "columns": ["ticker", "last_price", "bid", "ask", "event_time"],
                    }
                ]
            },
            role="data_engineer",
        )
        self.assertTrue(report.success, report.error)
        self.assertEqual(report.data["schema_count"], 1)
        self.assertEqual(report.data["schema_anomaly_count"], 1)
        self.assertFalse(report.data["automation_ready"])
        self.assertIn("unrecognized_schema", report.data["automation_blockers"])

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
                vipdoc_path=vipdoc_root,
                source_format="vipdoc",
                end_date="2026-05-15",
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

    def test_13f_information_table_parse_imports_mapped_holdings_only(self) -> None:
        self.service.register_security(
            {
                "security_id": "sec_us_apple",
                "issuer_id": "issuer_001",
                "ticker": "AAPL",
                "figi": "BBG000B9XRY4",
                "isin": "US0378331005",
                "exchange": "NASDAQ",
                "currency": "USD",
                "market": "U",
            },
            actor="platform",
        )
        self.service.register_entity_mapping(
            {
                "mapping_id": "map_13f_apple",
                "issuer_id": "issuer_001",
                "figi": "BBG000B9XRY4",
                "isin": "US0378331005",
                "ticker": "AAPL",
                "market": "U",
                "confidence": 0.96,
                "source": "manual_cusip_figi_gold",
            },
            actor="data_engineer",
        )
        xml = """<SEC-DOCUMENT>header text</SEC-DOCUMENT>
<XML>
<?xml version="1.0" encoding="UTF-8"?>
<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
  <infoTable>
    <nameOfIssuer>APPLE INC</nameOfIssuer>
    <titleOfClass>COM</titleOfClass>
    <cusip>037833100</cusip>
    <value>150000</value>
    <shrsOrPrnAmt>
      <sshPrnamt>1000000</sshPrnamt>
      <sshPrnamtType>SH</sshPrnamtType>
    </shrsOrPrnAmt>
    <investmentDiscretion>SOLE</investmentDiscretion>
    <votingAuthority><Sole>1000000</Sole><Shared>0</Shared><None>0</None></votingAuthority>
  </infoTable>
  <infoTable>
    <nameOfIssuer>UNMAPPED SEMICONDUCTOR CO</nameOfIssuer>
    <titleOfClass>COM</titleOfClass>
    <cusip>999999999</cusip>
    <value>9000</value>
    <shrsOrPrnAmt><sshPrnamt>25000</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
    <investmentDiscretion>SOLE</investmentDiscretion>
    <votingAuthority><Sole>25000</Sole><Shared>0</Shared><None>0</None></votingAuthority>
  </infoTable>
</informationTable>
</XML>
<XML><metadata>ignored wrapper</metadata></XML>"""
        parsed = self.router.dispatch(
            "POST",
            "/api/13f/filings/parse",
            {
                "information_table_xml": xml,
                "source_uri": "https://www.sec.gov/Archives/edgar/data/1067983/000095012326000001/infotable.xml",
                "filer_cik": "0001067983",
                "filer_name": "Berkshire Hathaway Inc",
                "report_period": "2026-03-31",
                "import_holdings": True,
            },
            role="海外研究负责人",
        )
        self.assertTrue(parsed.success, parsed.error)
        self.assertEqual(parsed.data["row_count"], 2)
        self.assertEqual(parsed.data["created_count"], 1)
        self.assertEqual(parsed.data["unmapped_count"], 1)
        self.assertFalse(parsed.data["automation_allowed"])
        self.assertFalse(parsed.data["live_execution_allowed"])
        self.assertEqual(
            parsed.data["usage_boundary"],
            "13f_information_table_import_is_research_and_crowding_risk_only_not_trade_signal",
        )
        created = parsed.data["created"][0]
        self.assertEqual(created["security_id"], "sec_us_apple")
        self.assertEqual(created["shares"], 1000000.0)
        self.assertEqual(created["value_usd"], 150000000.0)
        self.assertEqual(created["voting_authority"], "sole=1000000;shared=0;none=0")
        self.assertEqual(parsed.data["unmapped"][0]["cusip"], "999999999")

        duplicate = self.router.dispatch(
            "POST",
            "/api/13f/filings/parse",
            {
                "information_table_xml": xml,
                "filer_cik": "0001067983",
                "filer_name": "Berkshire Hathaway Inc",
                "report_period": "2026-03-31",
                "import_holdings": True,
            },
            role="数据工程",
        )
        self.assertTrue(duplicate.success, duplicate.error)
        self.assertEqual(duplicate.data["created_count"], 0)
        self.assertEqual(duplicate.data["skipped_count"], 2)

        crowding = self.router.dispatch(
            "POST",
            "/api/13f/crowding/update",
            {"snapshot_id": "crd_13f_xml", "issuer_id": "issuer_001", "report_period": "2026-03-31"},
            role="CIO",
        )
        self.assertTrue(crowding.success, crowding.error)
        candidates = self.router.dispatch(
            "GET",
            "/api/13f/candidate-pool",
            {"report_period": "2026-03-31"},
            role="CEO",
        )
        self.assertFalse(candidates.data["automation_allowed"])
        self.assertEqual(candidates.data["candidates"][0]["security_id"], "sec_us_apple")

    def test_13f_information_table_parse_fetches_source_uri(self) -> None:
        class FakeSecConnectors:
            def __init__(self, xml: str) -> None:
                self.xml = xml
                self.fetches = []

            def fetch_sec_document_body(self, source_uri, *, user_agent, max_bytes=2_000_000):
                self.fetches.append((source_uri, user_agent, max_bytes))
                return self.xml

        self.service.register_security(
            {
                "security_id": "sec_us_msft",
                "issuer_id": "issuer_001",
                "ticker": "MSFT",
                "figi": "BBG000BPH459",
                "isin": "US5949181045",
                "exchange": "NASDAQ",
                "currency": "USD",
                "market": "U",
            },
            actor="platform",
        )
        xml = """<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
  <infoTable>
    <nameOfIssuer>MICROSOFT CORP</nameOfIssuer>
    <titleOfClass>COM</titleOfClass>
    <cusip>594918104</cusip>
    <value>42000</value>
    <shrsOrPrnAmt><sshPrnamt>210000</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
  </infoTable>
</informationTable>"""
        fake = FakeSecConnectors(xml)
        self.service.connectors = fake
        response = self.router.dispatch(
            "POST",
            "/api/13f/filings/parse",
            {
                "source_uri": "https://www.sec.gov/Archives/edgar/data/1000000/000100000026000001/infotable.xml",
                "filer_cik": "0001000000",
                "report_period": "2026-03-31",
                "user_agent": "unit-test@example.com",
                "import_holdings": True,
                "security_mappings": [
                    {
                        "cusip": "594918104",
                        "issuer_id": "issuer_001",
                        "security_id": "sec_us_msft",
                        "confidence": 0.91,
                    }
                ],
            },
            role="数据工程",
        )
        self.assertTrue(response.success, response.error)
        self.assertEqual(response.data["fetch_status"], "fetched_source_uri")
        self.assertEqual(response.data["created_count"], 1)
        self.assertEqual(response.data["created"][0]["security_id"], "sec_us_msft")
        self.assertEqual(fake.fetches[0][1], "unit-test@example.com")

    def test_13f_information_table_batch_parse_reports_mapping_rate(self) -> None:
        self.service.register_security(
            {
                "security_id": "sec_us_nvda",
                "issuer_id": "issuer_001",
                "ticker": "NVDA",
                "figi": "BBG000BBJQV0",
                "isin": "US67066G1040",
                "exchange": "NASDAQ",
                "currency": "USD",
                "market": "U",
            },
            actor="platform",
        )
        mapped_xml = """<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
  <infoTable><nameOfIssuer>NVIDIA CORP</nameOfIssuer><titleOfClass>COM</titleOfClass><cusip>67066G104</cusip><value>1000</value><shrsOrPrnAmt><sshPrnamt>5000</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt></infoTable>
</informationTable>"""
        unmapped_xml = """<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
  <infoTable><nameOfIssuer>UNKNOWN ADR PLC</nameOfIssuer><titleOfClass>COM</titleOfClass><cusip>111111111</cusip><value>2000</value><shrsOrPrnAmt><sshPrnamt>8000</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt></infoTable>
</informationTable>"""
        batch = self.router.dispatch(
            "POST",
            "/api/13f/filings/batch-parse",
            {
                "batch_id": "13f_batch_unit",
                "import_holdings": True,
                "report_period": "2026-03-31",
                "filer_cik": "0001000000",
                "filings": [
                    {"filing_id": "filing_nvda", "information_table_xml": mapped_xml, "filer_name": "Gamma Fund"},
                    {"filing_id": "filing_unknown", "information_table_xml": unmapped_xml, "filer_name": "Delta Fund"},
                ],
            },
            role="数据工程",
        )
        self.assertTrue(batch.success, batch.error)
        self.assertEqual(batch.data["filing_count"], 2)
        self.assertEqual(batch.data["row_count"], 2)
        self.assertEqual(batch.data["created_count"], 1)
        self.assertEqual(batch.data["unmapped_count"], 1)
        self.assertEqual(batch.data["mapping_rate"], 0.5)
        self.assertFalse(batch.data["automation_allowed"])
        self.assertFalse(batch.data["live_execution_allowed"])
        self.assertEqual(batch.data["usage_boundary"], "13f_batch_import_is_dataset_quality_and_crowding_risk_only_not_trade_signal")

        readiness_gap = self.router.dispatch(
            "POST",
            "/api/13f/filings/mapping-readiness",
            {"batch_result": batch.data},
            actor="data",
            role="数据工程",
        )
        self.assertTrue(readiness_gap.success, readiness_gap.error)
        self.assertFalse(readiness_gap.data["ready_for_real_acceptance"])
        self.assertFalse(readiness_gap.data["automation_allowed"])
        self.assertFalse(readiness_gap.data["live_execution_allowed"])
        self.assertIn("filing_count", readiness_gap.data["missing_requirements"])
        self.assertIn("mapping_rate", readiness_gap.data["missing_requirements"])
        self.assertIn("batch_artifact_uri", readiness_gap.data["missing_requirements"])
        self.assertIn("unmapped_review_queue_uri", readiness_gap.data["missing_requirements"])
        self.assertEqual(readiness_gap.data["mapping_rate"], 0.5)
        self.assertEqual(readiness_gap.data["unmapped_queue_count"], 1)
        self.assertIn("13f_mapping_readiness_tracks_real_batch_artifacts", readiness_gap.data["usage_boundary"])

        no_unmapped_without_review_artifact = self.router.dispatch(
            "POST",
            "/api/13f/filings/mapping-readiness",
            {
                "filing_count": 120,
                "row_count": 2500,
                "unmapped_count": 0,
                "failed_count": 0,
                "mapping_rate": 1.0,
                "artifact_uris": {
                    "batch_artifact_uri": "s3://ai-quant-evidence/13f/batch-2026q1.json",
                    "mapping_gold_uri": "s3://ai-quant-evidence/13f/cusip-figi-gold-2026q1.jsonl",
                },
            },
            actor="data",
            role="数据工程",
        )
        self.assertTrue(no_unmapped_without_review_artifact.success, no_unmapped_without_review_artifact.error)
        self.assertFalse(no_unmapped_without_review_artifact.data["ready_for_real_acceptance"])
        self.assertEqual(no_unmapped_without_review_artifact.data["unmapped_queue_count"], 0)
        self.assertIn("unmapped_review_queue_uri", no_unmapped_without_review_artifact.data["missing_requirements"])

        readiness_ready = self.router.dispatch(
            "POST",
            "/api/13f/filings/mapping-readiness",
            {
                "batch_id": "13f_batch_large_ready",
                "filing_count": 120,
                "row_count": 2500,
                "unmapped_count": 20,
                "failed_count": 0,
                "mapping_rate": 0.992,
                "mapping_counts": {"registry_mapping": 2400, "provided_mapping": 80, "unmapped": 20},
                "artifact_uris": {
                    "batch_artifact_uri": "s3://ai-quant-evidence/13f/batch-2026q1.json",
                    "mapping_gold_uri": "s3://ai-quant-evidence/13f/cusip-figi-gold-2026q1.jsonl",
                    "unmapped_review_queue_uri": "s3://ai-quant-evidence/13f/unmapped-review-2026q1.jsonl",
                },
                "record_readiness": True,
            },
            actor="data",
            role="数据工程",
        )
        self.assertTrue(readiness_ready.success, readiness_ready.error)
        self.assertTrue(readiness_ready.data["ready_for_real_acceptance"])
        self.assertEqual(readiness_ready.data["missing_requirements"], [])
        self.assertEqual(readiness_ready.data["artifact_uris"]["mapping_gold_uri"], "s3://ai-quant-evidence/13f/cusip-figi-gold-2026q1.jsonl")
        self.assertEqual(self.service.store.audit_log[-1].action, "form13f_mapping_readiness_report")

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

        labels = self.router.dispatch(
            "POST",
            "/api/entity-mappings/labels",
            {
                "batch_id": "label_batch",
                "items": [
                    {"label_id": "emlbl_map_a", "mapping_id": "map_a", "issuer_id": "issuer_001", "ticker": "600000", "market": "A"},
                    {"label_id": "emlbl_map_u", "mapping_id": "map_u", "issuer_id": "issuer_001", "ticker": "DEMO", "market": "U"},
                ],
            },
            role="platform",
        )
        self.assertTrue(labels.success, labels.error)
        self.assertEqual(labels.data["created_count"], 2)
        listed_labels = self.router.dispatch("GET", "/api/entity-mappings/labels", {"issuer_id": "issuer_001"}, role="platform")
        self.assertEqual(listed_labels.data["total"], 2)
        persisted_report = self.router.dispatch("GET", "/api/entity-mappings/quality-report", {"issuer_id": "issuer_001"}, role="platform")
        self.assertEqual(persisted_report.data["checked_labels"], 2)
        self.assertEqual(persisted_report.data["accuracy"], 1.0)

    def test_entity_mapping_bitemporal_versions_filter_by_valid_and_recorded_time(self) -> None:
        old_mapping = self.router.dispatch(
            "POST",
            "/api/entity-mappings",
            {
                "mapping_id": "map_demo_old",
                "issuer_id": "issuer_001",
                "cik": "0000001",
                "ticker": "DEMO",
                "market": "U",
                "confidence": 0.72,
                "version": "2025Q4",
                "valid_from": "2025-10-01T00:00:00+00:00",
                "recorded_at": "2025-10-02T00:00:00+00:00",
            },
            role="platform",
        )
        self.assertTrue(old_mapping.success, old_mapping.error)
        new_mapping = self.router.dispatch(
            "POST",
            "/api/entity-mappings",
            {
                "mapping_id": "map_demo_new",
                "issuer_id": "issuer_001",
                "cik": "0000001",
                "figi": "FIGI-DEMO-NEW",
                "ticker": "DEMO",
                "market": "U",
                "confidence": 0.94,
                "version": "2026Q1",
                "valid_from": "2026-01-01T00:00:00+00:00",
                "recorded_at": "2026-01-05T00:00:00+00:00",
                "supersedes_mapping_id": "map_demo_old",
            },
            role="platform",
        )
        self.assertTrue(new_mapping.success, new_mapping.error)
        self.assertEqual(self.service.store.entity_mappings["map_demo_old"].status, "superseded")
        self.assertEqual(
            self.service.store.entity_mappings["map_demo_old"].valid_to.isoformat(),
            "2026-01-01T00:00:00+00:00",
        )

        historical = self.router.dispatch(
            "GET",
            "/api/entity-mappings",
            {"issuer_id": "issuer_001", "ticker": "DEMO", "valid_at": "2025-12-15T00:00:00+00:00"},
            role="platform",
        )
        self.assertTrue(historical.success, historical.error)
        self.assertEqual(historical.data["total"], 1)
        self.assertEqual(historical.data["mappings"][0]["mapping_id"], "map_demo_old")

        current = self.router.dispatch(
            "GET",
            "/api/entity-mappings",
            {
                "issuer_id": "issuer_001",
                "ticker": "DEMO",
                "valid_at": "2026-02-01T00:00:00+00:00",
                "recorded_at": "2026-01-04T00:00:00+00:00",
            },
            role="platform",
        )
        self.assertTrue(current.success, current.error)
        self.assertEqual(current.data["total"], 0)

        current_after_record = self.router.dispatch(
            "GET",
            "/api/entity-mappings",
            {
                "issuer_id": "issuer_001",
                "ticker": "DEMO",
                "valid_at": "2026-02-01T00:00:00+00:00",
                "recorded_at": "2026-01-06T00:00:00+00:00",
            },
            role="platform",
        )
        self.assertEqual(current_after_record.data["total"], 1)
        self.assertEqual(current_after_record.data["mappings"][0]["mapping_id"], "map_demo_new")

        report = self.router.dispatch(
            "GET",
            "/api/entity-mappings/quality-report",
            {"issuer_id": "issuer_001", "valid_at": "2026-02-01T00:00:00+00:00", "low_confidence_threshold": 0.9},
            role="platform",
        )
        self.assertTrue(report.success, report.error)
        self.assertEqual(report.data["mappings"], 1)
        self.assertEqual(report.data["bitemporal_version_coverage"], 1.0)
        self.assertEqual(report.data["active_open_ended_count"], 1)
        self.assertEqual(report.data["temporal_overlap_count"], 0)
        self.assertEqual(report.data["status_counts"]["active"], 1)

    def test_entity_mapping_readiness_report_requires_ahu_graph_and_adapter_evidence(self) -> None:
        self.service.register_issuer(
            {
                "issuer_id": "issuer_ahu",
                "legal_name": "Demo A H U Corp",
                "market": ["A", "H", "U"],
                "lei": "LEI-AHU-001",
                "cik": "0001001",
                "country": "CN",
            },
            actor="platform",
        )
        self.service.register_security(
            {
                "security_id": "sec_ahu",
                "issuer_id": "issuer_ahu",
                "ticker": "AHU",
                "figi": "FIGI-AHU-001",
                "isin": "US000AHU001",
                "exchange": "NASDAQ",
                "currency": "USD",
                "market": "U",
            },
            actor="platform",
        )
        document = self.service.ingest_document(
            {
                "document_id": "doc_entity_readiness",
                "issuer_id": "issuer_ahu",
                "security_id": "sec_ahu",
                "source_id": "src_sec",
                "source_type": "regulatory",
                "document_type": "20-F",
                "source_uri": "https://example.invalid/doc-entity-readiness",
                "body": "Revenue visibility improved.\n\nSupply chain risk remains manageable.",
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
        evidences = self.service.extract_evidence(document.document_id, actor="analyst")
        thesis = self.service.create_thesis(
            {
                "thesis_id": "thesis_entity_readiness",
                "issuer_id": "issuer_ahu",
                "horizon": "mid",
                "hypothesis": "A/H/U mapping supports subject page traceability",
                "evidence_ids": [item.evidence_id for item in evidences],
                "risk_factors": ["identifier drift"],
            },
            actor="analyst",
        )
        self.service.run_scoring(
            {
                "signal_id": "sig_entity_readiness",
                "thesis_id": thesis.thesis_id,
                "strategy_type": "long",
                "source_model": "rules",
                "model_version": "v1",
            },
            actor="cio",
        )
        batch = self.router.dispatch(
            "POST",
            "/api/entity-mappings/batch",
            {
                "batch_id": "entity_readiness_batch",
                "items": [
                    {
                        "mapping_id": "map_ahu_a",
                        "issuer_id": "issuer_ahu",
                        "lei": "LEI-AHU-001",
                        "figi": "FIGI-AHU-A",
                        "isin": "CNAHU000001",
                        "ticker": "600001",
                        "market": "A",
                        "confidence": 0.99,
                        "source": "real_adr_china_mapping_batch",
                        "version": "2026Q1",
                        "valid_from": "2026-01-01T00:00:00+00:00",
                        "recorded_at": "2026-01-02T00:00:00+00:00",
                    },
                    {
                        "mapping_id": "map_ahu_h",
                        "issuer_id": "issuer_ahu",
                        "lei": "LEI-AHU-001",
                        "figi": "FIGI-AHU-H",
                        "isin": "HKAHU000001",
                        "ticker": "00001",
                        "market": "H",
                        "confidence": 0.99,
                        "source": "real_adr_china_mapping_batch",
                        "version": "2026Q1",
                        "valid_from": "2026-01-01T00:00:00+00:00",
                        "recorded_at": "2026-01-02T00:00:00+00:00",
                    },
                    {
                        "mapping_id": "map_ahu_u",
                        "issuer_id": "issuer_ahu",
                        "lei": "LEI-AHU-001",
                        "cik": "0001001",
                        "figi": "FIGI-AHU-U",
                        "isin": "US000AHU001",
                        "ticker": "AHU",
                        "market": "U",
                        "confidence": 0.99,
                        "source": "real_adr_china_mapping_batch",
                        "version": "2026Q1",
                        "valid_from": "2026-01-01T00:00:00+00:00",
                        "recorded_at": "2026-01-02T00:00:00+00:00",
                    },
                ],
            },
            role="platform",
        )
        self.assertTrue(batch.success, batch.error)
        labels = self.router.dispatch(
            "POST",
            "/api/entity-mappings/labels",
            {
                "batch_id": "entity_readiness_labels",
                "items": [
                    {"label_id": "emlbl_map_ahu_a", "mapping_id": "map_ahu_a", "issuer_id": "issuer_ahu", "ticker": "600001", "market": "A"},
                    {"label_id": "emlbl_map_ahu_h", "mapping_id": "map_ahu_h", "issuer_id": "issuer_ahu", "ticker": "00001", "market": "H"},
                    {"label_id": "emlbl_map_ahu_u", "mapping_id": "map_ahu_u", "issuer_id": "issuer_ahu", "ticker": "AHU", "market": "U"},
                ],
            },
            role="platform",
        )
        self.assertTrue(labels.success, labels.error)

        gap = self.router.dispatch(
            "POST",
            "/api/entity-mappings/readiness-report",
            {
                "issuer_id": "issuer_ahu",
                "min_mapping_count": 3,
                "min_label_count": 3,
                "min_vector_point_count": 1,
                "min_traceable_resource_count": 1,
            },
            role="platform",
        )
        self.assertTrue(gap.success, gap.error)
        self.assertFalse(gap.data["ready_for_entity_graph_production"])
        self.assertIn("neo4j_non_local_config", gap.data["missing_requirements"])
        self.assertIn("qdrant_non_local_config", gap.data["missing_requirements"])
        self.assertIn("real_batch_mapping_artifact_uri", gap.data["missing_requirements"])
        self.assertIn("entity_mapping_readiness_report_validates_ahu_accuracy", gap.data["usage_boundary"])
        self.assertFalse(gap.data["automation_allowed"])
        self.assertEqual(gap.data["market_summary"]["coverage"], 1.0)
        self.assertEqual(gap.data["quality_report"]["accuracy"], 1.0)
        self.assertGreaterEqual(gap.data["graph_traceability"]["traceability_rate"], 0.95)

        ready = self.router.dispatch(
            "POST",
            "/api/entity-mappings/readiness-report",
            {
                "issuer_id": "issuer_ahu",
                "min_mapping_count": 3,
                "min_label_count": 3,
                "min_vector_point_count": 1,
                "min_traceable_resource_count": 1,
                "neo4j_endpoint": "neo4j+s://graph.prod.example.com",
                "qdrant_endpoint": "https://qdrant.prod.example.com",
                "artifact_uris": {
                    "real_batch_mapping_artifact_uri": "artifact://prod/entity-mapping/ahu-batch.json",
                    "adr_china_queue_mapping_uri": "artifact://prod/entity-mapping/adr-china-queue.json",
                    "mapping_gold_uri": "artifact://prod/entity-mapping/gold-labels.json",
                    "entity_page_acceptance_uri": "artifact://prod/entity-page/browser-matrix.json",
                    "graph_adapter_evidence_uri": "artifact://prod/graph/neo4j-sync.json",
                    "vector_adapter_evidence_uri": "artifact://prod/vector/qdrant-sync.json",
                },
                "record_readiness": True,
            },
            role="platform",
            actor="platform_owner",
        )
        self.assertTrue(ready.success, ready.error)
        self.assertTrue(ready.data["ready_for_entity_graph_production"])
        self.assertEqual(ready.data["missing_requirements"], [])
        self.assertEqual(ready.data["label_summary"]["coverage"], 1.0)
        self.assertEqual(ready.data["edge_quality"]["edge_metadata_coverage"], 1.0)
        self.assertEqual(ready.data["vector_export"]["rights_filter"], "restricted_excluded")
        self.assertTrue(ready.data["adapters"]["neo4j"]["non_local_configured"])
        self.assertTrue(ready.data["adapters"]["qdrant"]["non_local_configured"])
        self.assertEqual(self.service.store.audit_log[-1].action, "entity_mapping_readiness_report")

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
        mapping_edges = [edge for edge in graph.data["edges"] if edge["type"] == "HAS_MAPPING"]
        self.assertTrue(mapping_edges)
        self.assertIn("valid_from", mapping_edges[0])
        self.assertIn("recorded_at", mapping_edges[0])
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

        readiness_gap = self.router.dispatch(
            "POST",
            "/api/benchmarks/bm_bilingual/readiness-report",
            {},
            actor="ml",
            role="NLP/ML 负责人",
        )
        self.assertTrue(readiness_gap.success, readiness_gap.error)
        self.assertFalse(readiness_gap.data["ready_for_real_acceptance"])
        self.assertFalse(readiness_gap.data["automation_allowed"])
        self.assertTrue(readiness_gap.data["external_artifact_required"])
        self.assertEqual(readiness_gap.data["active_sample_count"], 2)
        self.assertIn("sample_size", readiness_gap.data["missing_requirements"])
        self.assertIn("sample_manifest_artifact", readiness_gap.data["missing_requirements"])
        self.assertIn("chinese_sample_set_artifact", readiness_gap.data["missing_requirements"])
        self.assertIn("english_sample_set_artifact", readiness_gap.data["missing_requirements"])
        self.assertIn("annotation_manual", readiness_gap.data["missing_requirements"])
        self.assertIn("ocr_bbox_gold_labels", readiness_gap.data["missing_requirements"])
        self.assertIn("table_cell_gold_labels", readiness_gap.data["missing_requirements"])
        self.assertIn("summary_quality_samples", readiness_gap.data["missing_requirements"])
        self.assertIn("regression_baseline_artifact", readiness_gap.data["missing_requirements"])
        self.assertEqual(readiness_gap.data["latest_run_id"], "bmrn_bilingual")
        self.assertIn("benchmark_readiness_report_tracks_real_sample", readiness_gap.data["usage_boundary"])

        inline_only = self.router.dispatch(
            "POST",
            "/api/benchmarks/bm_bilingual/readiness-report",
            {
                "target_sample_size": 2,
                "min_chinese_samples": 1,
                "min_english_samples": 1,
                "bbox_gold_labels": [{"document_id": "doc_bench_en", "page_no": 1, "bbox": {"x": 0, "y": 0, "width": 1, "height": 1}}],
                "table_cell_gold_labels": [{"document_id": "doc_bench_en", "row": 1, "col": 1, "bbox": {"x": 0, "y": 0, "width": 1, "height": 1}}],
                "summary_samples": [{"answer_id": "ans_demo", "expected_anchor_terms": ["revenue"]}],
            },
            actor="ml",
            role="NLP/ML 负责人",
        )
        self.assertTrue(inline_only.success, inline_only.error)
        self.assertFalse(inline_only.data["ready_for_real_acceptance"])
        self.assertEqual(inline_only.data["gold_labels"]["bbox_label_count"], 1)
        self.assertEqual(inline_only.data["summary_sample_count"], 1)
        self.assertIn("ocr_bbox_gold_labels", inline_only.data["missing_requirements"])
        self.assertIn("table_cell_gold_labels", inline_only.data["missing_requirements"])
        self.assertIn("summary_quality_samples", inline_only.data["missing_requirements"])

        readiness_ready = self.router.dispatch(
            "POST",
            "/api/benchmarks/bm_bilingual/readiness-report",
            {
                "target_sample_size": 2,
                "min_chinese_samples": 1,
                "min_english_samples": 1,
                "artifact_uris": {
                    "sample_manifest_uri": "s3://ai-quant-evidence/benchmarks/sample-manifest.json",
                    "chinese_sample_set_uri": "s3://ai-quant-evidence/benchmarks/zh-samples.jsonl",
                    "english_sample_set_uri": "s3://ai-quant-evidence/benchmarks/sec-samples.jsonl",
                    "annotation_manual_uri": "s3://ai-quant-evidence/benchmarks/annotation-manual-v1.md",
                    "bbox_gold_uri": "s3://ai-quant-evidence/benchmarks/bbox-gold.jsonl",
                    "table_cell_gold_uri": "s3://ai-quant-evidence/benchmarks/table-cell-gold.jsonl",
                    "summary_quality_uri": "s3://ai-quant-evidence/benchmarks/summary-samples.jsonl",
                    "baseline_report_uri": "s3://ai-quant-evidence/benchmarks/baseline-report.json",
                },
                "bbox_gold_labels": [{"document_id": "doc_bench_en", "page_no": 1, "bbox": {"x": 0, "y": 0, "width": 1, "height": 1}}],
                "table_cell_gold_labels": [{"document_id": "doc_bench_en", "row": 1, "col": 1, "bbox": {"x": 0, "y": 0, "width": 1, "height": 1}}],
                "summary_samples": [{"answer_id": "ans_demo", "expected_anchor_terms": ["revenue"]}],
                "record_readiness": True,
            },
            actor="ml",
            role="NLP/ML 负责人",
        )
        self.assertTrue(readiness_ready.success, readiness_ready.error)
        self.assertTrue(readiness_ready.data["ready_for_real_acceptance"])
        self.assertEqual(readiness_ready.data["missing_requirements"], [])
        self.assertEqual(readiness_ready.data["gold_labels"]["bbox_label_count"], 1)
        self.assertEqual(readiness_ready.data["artifact_uris"]["baseline_report_uri"], "s3://ai-quant-evidence/benchmarks/baseline-report.json")
        self.assertEqual(self.service.store.audit_log[-1].action, "benchmark_readiness_report")

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

    def test_local_benchmark_quality_package_exports_repeatable_large_sample_artifacts(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            inputs = tmp_path / "inputs"
            output = tmp_path / "quality"
            inputs.mkdir()
            (inputs / "en.txt").write_text("FY2026 revenue grew 12%. Operating cash flow improved in 2026.", encoding="utf-8")
            (inputs / "zh.txt").write_text("2026年营业收入增长12%，经营活动现金流改善。", encoding="utf-8")
            (inputs / "skip.txt").write_text("No supported finance terms here.", encoding="utf-8")

            package = build_local_benchmark_quality_package(
                input_paths=[inputs],
                output_dir=output,
                benchmark_id="bm_quality_test",
                target_sample_size=3,
                min_chinese_samples=1,
                min_english_samples=1,
                artifact_prefix="minio://ai-quant-local/benchmark-quality/test",
            )

            self.assertEqual(package["status"], "generated")
            self.assertEqual(package["sample_count"], 2)
            self.assertEqual(package["target_gap"], 1)
            self.assertFalse(package["large_sample_ready"])
            self.assertIn("sample_size", package["readiness_missing_requirements"])
            for artifact_path in package["artifacts"].values():
                self.assertTrue(Path(artifact_path).exists(), artifact_path)
            manifest = json.loads((output / "sample-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["sample_count"], 2)
            self.assertEqual({row["language"] for row in manifest["samples"]}, {"en", "zh"})
            baseline = json.loads((output / "baseline-report.json").read_text(encoding="utf-8"))
            self.assertTrue(baseline["run"]["passed"])
            readiness = json.loads((output / "readiness-report.json").read_text(encoding="utf-8"))
            self.assertFalse(readiness["ready_for_real_acceptance"])
            self.assertEqual(readiness["artifact_uris"]["baseline_report_uri"], "minio://ai-quant-local/benchmark-quality/test/baseline-report.json")

            cli_output = tmp_path / "cli-quality"
            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/local_benchmark_quality_package.py",
                    str(inputs),
                    "--output-dir",
                    str(cli_output),
                    "--benchmark-id",
                    "bm_quality_cli",
                    "--target-sample-size",
                    "2",
                    "--min-chinese-samples",
                    "1",
                    "--min-english-samples",
                    "1",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertIn('"status": "generated"', result.stdout)
            self.assertTrue((cli_output / "quality-package.json").exists())
            self.assertFalse((cli_output / ".quality-package.json.tmp").exists())

    def test_fetch_benchmark_samples_writes_public_connector_inputs_for_quality_package(self) -> None:
        class FakeBenchmarkConnectors:
            def fetch_sec_recent_filings(self, cik, *, user_agent, limit=10, document_types=None):
                self.sec_user_agent = user_agent
                return [
                    ConnectorDocument(
                        source_id="sec_edgar",
                        source_type="regulatory",
                        document_type="10-K",
                        source_uri=f"https://www.sec.gov/Archives/edgar/data/{cik}/sample.htm",
                        language="en",
                        title="10-K filing",
                        published_at="2026-05-01",
                        metadata={"cik": cik, "accession_no": "0000000000-26-000001", "primary_doc": "sample.htm"},
                    )
                ][:limit]

            def fetch_sec_document_body(self, source_uri, *, user_agent, max_bytes=2_000_000):
                return "FY2026 revenue grew 12%. Operating cash flow improved and risk factors changed. Gross margin expanded with services revenue."[:max_bytes]

            def fetch_ashare_recent_filings(self, security_code, *, user_agent, limit=10, begin_date="", end_date="", report_type="ALL", security_type="", exchange="auto"):
                return [
                    ConnectorDocument(
                        source_id="ashare_exchange",
                        source_type="exchange",
                        document_type="annual_report",
                        source_uri=f"https://www.sse.com.cn/{security_code}/annual.pdf",
                        language="zh",
                        title="2026年年度报告 营业收入增长 经营活动现金流改善",
                        body="2026年营业收入增长12%，经营活动现金流改善。",
                        published_at="2026-04-30T00:00:00+00:00",
                        metadata={"security_code": security_code},
                    )
                ][:limit]

        with TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "fetched"
            service = SystemService()
            service.connectors = FakeBenchmarkConnectors()
            manifest = fetch_benchmark_samples(
                output_dir=output,
                sec_ciks=["0000320193"],
                ashare_codes=["600519"],
                limit_per_symbol=1,
                user_agent="test-contact@example.com",
                service=service,
            )

            self.assertEqual(manifest["created_count"], 2)
            self.assertEqual(manifest["error_count"], 0)
            self.assertTrue((output / "fetch-manifest.json").exists())
            written = sorted(output.glob("*.txt"))
            self.assertEqual(len(written), 2)
            combined = "\n".join(path.read_text(encoding="utf-8") for path in written)
            self.assertIn("revenue grew", combined)
            self.assertIn("营业收入增长", combined)
            self.assertFalse((output / ".fetch-manifest.json.tmp").exists())

    def test_fetch_benchmark_samples_can_discover_ashare_codes_from_tdx(self) -> None:
        class FakeAshareOnlyConnectors:
            def __init__(self) -> None:
                self.codes: list[str] = []

            def fetch_ashare_recent_filings(self, security_code, *, user_agent, limit=10, begin_date="", end_date="", report_type="ALL", security_type="", exchange="auto"):
                self.codes.append(security_code)
                return [
                    ConnectorDocument(
                        source_id="ashare_exchange",
                        source_type="exchange",
                        document_type="announcement",
                        source_uri=f"https://www.sse.com.cn/{security_code}/notice.pdf",
                        language="zh",
                        title=f"{security_code} 2026年公告 营业收入增长",
                        body=f"{security_code} 2026年营业收入增长，经营活动现金流改善。",
                        published_at="2026-05-01T00:00:00+00:00",
                    )
                ][:limit]

        with TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "tdx-fetched"
            vipdoc_root = Path(tmpdir) / "vipdoc"
            day_dir = vipdoc_root / "sh" / "lday"
            day_dir.mkdir(parents=True)
            (day_dir / "sh600519.day").write_bytes(struct.pack("<IIIIIfII", 20260501, 100, 100, 100, 100, 1000.0, 100, 0))
            service = SystemService()
            fake = FakeAshareOnlyConnectors()
            service.connectors = fake
            service.tdx_market_data = TDXVipdocAdapter(path=vipdoc_root)
            manifest = fetch_benchmark_samples(
                output_dir=output,
                ashare_codes_from_tdx=True,
                limit_per_symbol=1,
                service=service,
            )

            self.assertEqual(manifest["created_count"], 1)
            self.assertEqual(manifest["input_counts"]["ashare_codes_from_tdx"], 1)
            self.assertEqual(fake.codes, ["600519"])
            self.assertTrue(any(path.name.startswith("ashare_600519") for path in output.glob("*.txt")))

    def test_fetch_benchmark_samples_can_parse_ashare_attachment_text(self) -> None:
        class FakeAshareAttachmentConnectors:
            def __init__(self) -> None:
                self.downloaded: list[str] = []

            def fetch_ashare_recent_filings(self, security_code, *, user_agent, limit=10, begin_date="", end_date="", report_type="ALL", security_type="", exchange="auto"):
                return [
                    ConnectorDocument(
                        source_id="ashare_exchange",
                        source_type="exchange",
                        document_type="annual_report",
                        source_uri=f"https://www.sse.com.cn/{security_code}/annual.html",
                        language="zh",
                        title="2026年年度报告",
                        body="",
                        published_at="2026-04-30T00:00:00+00:00",
                        metadata={"security_code": security_code},
                    )
                ][:limit]

            def fetch_document_binary(self, market, source_uri, *, user_agent, max_bytes=10_000_000):
                self.downloaded.append(source_uri)
                return "<html><body>2026年营业收入增长12%，经营活动现金流改善，毛利率提升。</body></html>".encode("utf-8")[:max_bytes]

        with TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "ashare-attachment"
            service = SystemService()
            fake = FakeAshareAttachmentConnectors()
            service.connectors = fake
            manifest = fetch_benchmark_samples(
                output_dir=output,
                ashare_codes=["600519"],
                limit_per_symbol=1,
                include_ashare_attachment_text=True,
                service=service,
            )

            self.assertEqual(manifest["created_count"], 1)
            self.assertEqual(manifest["skipped_count"], 0)
            self.assertEqual(fake.downloaded, ["https://www.sse.com.cn/600519/annual.html"])
            self.assertTrue(manifest["rows"][0]["attachment_text_used"])
            written = next(output.glob("ashare_600519*.txt"))
            self.assertIn("营业收入增长", written.read_text(encoding="utf-8"))

    def test_local_data_unblock_audit_separates_data_blockers_from_quality_gaps(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            quality = {
                "sample_count": 500,
                "target_gap": 0,
                "language_counts": {"zh": 217, "en": 283},
                "source_counts": {"ashare_exchange": 217, "sec_edgar": 283},
                "readiness_missing_requirements": ["metric_number_recall", "metric_period_recall"],
            }
            sample_manifest = {
                "sample_count": 500,
                "language_counts": {"zh": 217, "en": 283},
                "source_counts": {"ashare_exchange": 217, "sec_edgar": 283},
            }
            sec_fetch = {"status": "completed", "created_count": 4, "error_count": 0}
            ashare_fetch = {
                "status": "completed",
                "created_count": 0,
                "skipped_count": 2,
                "error_count": 0,
                "skipped": [{"attachment_attempted": True}, {"attachment_attempted": True}],
            }
            paths = {
                "quality": root / "quality.json",
                "sample_manifest": root / "sample-manifest.json",
                "sec_fetch": root / "sec-fetch.json",
                "ashare_fetch": root / "ashare-fetch.json",
            }
            paths["quality"].write_text(json.dumps(quality), encoding="utf-8")
            paths["sample_manifest"].write_text(json.dumps(sample_manifest), encoding="utf-8")
            paths["sec_fetch"].write_text(json.dumps(sec_fetch), encoding="utf-8")
            paths["ashare_fetch"].write_text(json.dumps(ashare_fetch), encoding="utf-8")

            result = audit_local_data_unblock(
                quality_package_path=paths["quality"],
                sample_manifest_path=paths["sample_manifest"],
                sec_fetch_manifest_path=paths["sec_fetch"],
                ashare_fetch_manifest_path=paths["ashare_fetch"],
            )

            self.assertTrue(result["passed"])
            self.assertFalse(result["data_blocked"])
            self.assertEqual(result["data_blockers"], [])
            self.assertEqual(result["remaining_quality_gaps"], ["metric_number_recall", "metric_period_recall"])
            self.assertEqual(result["ashare_fetch"]["attachment_attempted_count"], 2)

            quality["readiness_missing_requirements"] = ["chinese_sample_count", "metric_number_recall"]
            paths["quality"].write_text(json.dumps(quality), encoding="utf-8")
            blocked = audit_local_data_unblock(
                quality_package_path=paths["quality"],
                sample_manifest_path=paths["sample_manifest"],
                sec_fetch_manifest_path=paths["sec_fetch"],
                ashare_fetch_manifest_path=paths["ashare_fetch"],
            )
            self.assertFalse(blocked["passed"])
            self.assertEqual(blocked["data_blockers"], ["chinese_sample_count"])

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

    def test_research_answer_readiness_report_requires_model_and_fallback_quality_evidence(self) -> None:
        self.service.ingest_document(
            {
                "document_id": "doc_answer_readiness",
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "source_id": "src_sec",
                "source_type": "regulatory",
                "document_type": "10-K",
                "source_uri": "https://example.invalid/doc-answer-readiness",
                "body": "Revenue grew 12% and risk factors include demand volatility. Services resilience improved.",
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
        evidence = self.service.extract_evidence("doc_answer_readiness", actor="analyst")
        answer = self.service.create_research_answer(
            {
                "answer_id": "ans_readiness",
                "question": "What changed in revenue, services resilience, and key risk factors?",
                "issuer_id": "issuer_001",
                "evidence_ids": [item.evidence_id for item in evidence],
                "summary_version": "summary-prod-v1",
                "prompt_version": "prompt-prod-v1",
                "model_version": "gpt-prod-eval",
                "chinese_summary": "收入增长12%，服务韧性改善，风险因素包括需求波动。",
                "human_review_status": "approved",
                "reviewer": "analyst_lead",
            },
            actor="analyst",
        )
        self.assertEqual(answer.answer_id, "ans_readiness")

        gap = self.router.dispatch(
            "POST",
            "/api/research/answers/readiness-report",
            {"issuer_id": "issuer_001", "min_anchor_coverage": 0.0},
            actor="ml",
            role="NLP/ML 负责人",
        )
        self.assertTrue(gap.success, gap.error)
        self.assertFalse(gap.data["ready_for_research_answer_production"])
        self.assertIn("model_quality_evaluation_uri", gap.data["missing_requirements"])
        self.assertIn("fallback_quality_evaluation_uri", gap.data["missing_requirements"])
        self.assertEqual(gap.data["quality_report"]["source_link_rate"], 1.0)
        self.assertEqual(gap.data["summary_benchmark"]["metrics"]["version_metadata_rate"], 1.0)
        self.assertFalse(gap.data["automation_allowed"])

        ready = self.router.dispatch(
            "POST",
            "/api/research/answers/readiness-report",
            {
                "issuer_id": "issuer_001",
                "min_anchor_coverage": 0.0,
                "artifact_uris": {
                    "model_quality_evaluation_uri": "artifact://prod/research-answer/model-quality.json",
                    "fallback_quality_evaluation_uri": "artifact://prod/research-answer/fallback-quality.json",
                    "summary_review_policy_uri": "artifact://prod/research-answer/summary-rubric.md",
                },
                "record_readiness": True,
            },
            actor="ml_lead",
            role="NLP/ML 负责人",
        )
        self.assertTrue(ready.success, ready.error)
        self.assertTrue(ready.data["ready_for_research_answer_production"])
        self.assertEqual(ready.data["missing_requirements"], [])
        self.assertEqual(ready.data["traceability"]["research_answer_traceability_rate"], 1.0)
        self.assertIn("research_answer_readiness_report_requires_english_evidence", ready.data["usage_boundary"])
        self.assertEqual(self.service.store.audit_log[-1].action, "research_answer_readiness_report")

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

    def test_filing_qa_answer_auto_extracts_original_text_and_records_fallback(self) -> None:
        self.service.seed_default_sources(actor="risk")
        self.service.llm_gateway = LLMGateway(api_key="", http_send=lambda _request, _timeout: b"{}")
        self.service.ingest_document(
            {
                "document_id": "doc_filing_qa",
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "source_id": "sec_edgar",
                "source_type": "regulatory",
                "document_type": "10-Q",
                "source_uri": "https://example.invalid/doc-filing-qa",
                "body": "Revenue grew 12% year over year. Services demand stayed resilient. Risk factors include supply concentration.",
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
            "/api/research/answers/filing-qa",
            {
                "answer_id": "ans_filing_qa_001",
                "document_id": "doc_filing_qa",
                "question": "What changed in revenue and risk factors?",
                "evidence_limit": 3,
            },
            actor="analyst",
            role="analyst",
        )
        self.assertTrue(response.success, response.error)
        self.assertFalse(response.data["automation_allowed"])
        self.assertFalse(response.data["live_execution_allowed"])
        self.assertEqual(response.data["usage_boundary"], "filing_qa_research_only_original_text_required_no_trade_signal")
        self.assertTrue(response.data["preserves_english_source"])
        self.assertEqual(response.data["answer"]["answer_id"], "ans_filing_qa_001")
        self.assertEqual(response.data["answer"]["source_document_ids"], ["doc_filing_qa"])
        self.assertGreaterEqual(len(response.data["answer"]["evidence_ids"]), 1)
        self.assertIn("Revenue grew 12%", response.data["answer"]["english_source_text"])
        self.assertEqual(response.data["llm_run"]["template_id"], "llmtpl_filing_qa_v1")
        self.assertEqual(response.data["model_fallback"]["fallback_used"], "rule_summary")
        self.assertTrue(response.data["model_fallback"]["human_review_required"])
        self.assertEqual(response.data["quality_report"]["total"], 1)
        self.assertEqual(response.data["summary_benchmark"]["total"], 1)
        self.assertIn("pending_human_review", response.data["summary_benchmark"]["answers"][0]["blocking_issues"])
        self.assertEqual(self.service.store.audit_log[-1].action, "create_filing_qa_answer")

    def test_sec_single_name_research_loop_uses_realtime_sec_and_is_traceable(self) -> None:
        self._use_temp_object_store()
        self.service.connectors = _FakeSecSingleNameConnectors()
        response = self.router.dispatch(
            "POST",
            "/api/research/tasks/sec-single-name/run",
            {},
            role="cio",
        )
        self.assertTrue(response.success, response.error)
        data = response.data
        self.assertEqual(data["workflow_status"], "completed")
        self.assertTrue(data["used_realtime_sec"])
        self.assertEqual(data["fallback_reason"], "")
        self.assertTrue(data["simulation_only"])
        self.assertFalse(data["live_execution_allowed"])
        self.assertEqual(data["ticker"], "AAPL")
        self.assertEqual(data["cik"], "0000320193")
        ids = data["ids"]
        for key in [
            "issuer_id",
            "security_id",
            "document_id",
            "answer_id",
            "thesis_id",
            "signal_id",
            "challenger_id",
            "research_card_id",
            "decision_id",
            "intent_id",
            "task_id",
        ]:
            self.assertTrue(ids[key], key)
        self.assertGreaterEqual(len(ids["evidence_ids"]), 1)
        self.assertEqual(ids["issuer_id"], "issuer_aapl")
        self.assertEqual(ids["security_id"], "security_aapl_us")
        self.assertEqual(data["research_answer"]["source_document_ids"], [ids["document_id"]])
        self.assertEqual(set(data["research_answer"]["evidence_ids"]), set(ids["evidence_ids"]))
        self.assertEqual(set(data["thesis"]["evidence_ids"]), set(ids["evidence_ids"]))
        self.assertEqual(data["decision"]["approval_state"], "approved")
        self.assertEqual(data["decision_pack"]["decision_id"], ids["decision_id"])
        self.assertEqual(data["decision_pack"]["approval_state"], "approved")
        self.assertEqual(data["intent"]["status"], "simulated_filled")
        self.assertEqual(data["simulated_execution"]["execution"]["mode"], "simulated")
        self.assertFalse(data["simulated_execution"]["execution"]["live_execution_allowed"])

        graph = self.router.dispatch("GET", "/api/graph/query", {"issuer_id": "issuer_aapl"}, role="analyst")
        self.assertTrue(graph.success, graph.error)
        self.assertIn(ids["document_id"], {item["document_id"] for item in graph.data["documents"]})
        self.assertTrue(set(ids["evidence_ids"]).issubset({item["evidence_id"] for item in graph.data["evidence"]}))
        edge_types = {item["type"] for item in graph.data["edges"]}
        self.assertTrue({"SUPPORTS", "GENERATES_SIGNAL", "CREATES_INTENT"}.issubset(edge_types))

        traceability = self.router.dispatch(
            "GET",
            "/api/graph/traceability-report",
            {"issuer_id": "issuer_aapl"},
            role="analyst",
        )
        self.assertTrue(traceability.success, traceability.error)
        self.assertEqual(traceability.data["traceability_rate"], 1.0)
        self.assertEqual(traceability.data["counts"]["untraceable_theses"], 0)
        self.assertEqual(traceability.data["counts"]["untraceable_decisions"], 0)
        self.assertEqual(traceability.data["counts"]["untraceable_research_answers"], 0)

    def test_sec_single_name_research_loop_falls_back_and_respects_permissions(self) -> None:
        denied = self.router.dispatch(
            "POST",
            "/api/research/tasks/sec-single-name/run",
            {},
            role="guest",
        )
        self.assertFalse(denied.success)
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.error["type"], "permission_denied")

        self._use_temp_object_store()
        self.service.connectors = _FakeSecSingleNameConnectors(fail=True)
        fallback = self.router.dispatch(
            "POST",
            "/api/research/tasks/sec-single-name/run",
            {"fallback_mode": "local_sample"},
            role="analyst",
        )
        self.assertTrue(fallback.success, fallback.error)
        data = fallback.data
        self.assertEqual(data["workflow_status"], "completed_with_fallback")
        self.assertFalse(data["used_realtime_sec"])
        self.assertEqual(data["source_mode"], "local_sec_sample")
        self.assertIn("SEC outage", data["fallback_reason"])
        self.assertEqual(data["document"]["version"], "local_sec_sample")
        self.assertTrue(data["simulation_only"])
        self.assertFalse(data["live_execution_allowed"])
        self.assertEqual(data["decision"]["approval_state"], "approved")
        self.assertEqual(data["task"]["status"], "done")
        self.assertEqual(data["task"]["evidence_ids"], data["ids"]["evidence_ids"])

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

    def test_structured_extraction_merges_cross_page_tables(self) -> None:
        self._use_temp_object_store()
        self.service.ingest_document(
            {
                "document_id": "doc_cross_page_table",
                "issuer_id": "issuer_001",
                "security_id": "sec_001",
                "source_id": "src_sec",
                "source_type": "regulatory",
                "document_type": "annual_report",
                "source_uri": "https://example.invalid/doc-cross-page-table",
                "body": (
                    "Metric | FY2024 | FY2025\n"
                    "--- | --- | ---\n"
                    "Revenue | 9.0 | 10.5\f"
                    "Metric | FY2024 | FY2025\n"
                    "--- | --- | ---\n"
                    "Net profit | 1.1 | 1.4"
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
        first_page_evidence = self.service.extract_evidence("doc_cross_page_table", actor="analyst")[0]
        extraction = self.router.dispatch(
            "POST",
            "/api/extractions/run",
            {
                "extraction_id": "ext_cross_page_table",
                "evidence_id": first_page_evidence.evidence_id,
                "expected_tables": 1,
                "include_adjacent_tables": True,
                "parser_version": "rule-table-cross-page-1",
            },
            role="NLP/ML 负责人",
        )
        self.assertTrue(extraction.success, extraction.error)
        self.assertTrue(extraction.data["passed"])
        self.assertEqual(len(extraction.data["tables"]), 1)
        table = extraction.data["tables"][0]
        self.assertEqual(table["headers"], ["Metric", "FY2024", "FY2025"])
        self.assertEqual(table["row_count"], 2)
        self.assertEqual(table["page_numbers"], [1, 2])
        self.assertEqual(table["merged_from_table_count"], 2)
        self.assertEqual(table["merge_strategy"], "cross_page_same_headers")
        self.assertEqual(table["cells"][3]["source_page_no"], 2)
        self.assertEqual(table["cells"][3]["row"], 2)
        self.assertIn("merged_row=2", table["cells"][3]["bbox"])
        self.assertEqual(extraction.data["metrics"]["table_cell_count"], 6.0)
        self.assertEqual(extraction.data["metrics"]["table_recall"], 1.0)

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
        self.assertEqual(response.data["theme_id"], "theme_demo_ai_supply_chain")
        self.assertEqual(response.data["chain_id"], "chain_demo_electronics")
        self.assertEqual(response.data["position_id"], "pos_demo_gpu")
        self.assertEqual(response.data["lexicon_id"], "lex_demo_ai_hardware")
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
        chain_graph = self.router.dispatch("GET", "/api/graph/query", {"chain_id": "chain_demo_electronics"}, role="CIO")
        self.assertTrue(chain_graph.success)
        self.assertTrue(chain_graph.data["company_positions"])
        demo_lexicons = self.router.dispatch("GET", "/api/hotspot-lexicons", {"q": "AI chip"}, role="CIO")
        self.assertTrue(demo_lexicons.success)
        self.assertEqual(demo_lexicons.data["lexicons"][0]["lexicon_id"], "lex_demo_ai_hardware")
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
        llm_target = reranked.data["results"][-1]
        llm_target_ref = f"{llm_target['resource_type']}:{llm_target['resource_id']}"

        sent_rerank = []

        def fake_rerank_send(request, timeout):
            sent_rerank.append({"url": request.full_url, "body": json.loads(request.data.decode("utf-8")), "timeout": timeout})
            return json.dumps(
                {
                    "id": "chatcmpl_rerank",
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "ordered_resource_ids": [llm_target_ref],
                                        "rationale": "Prefer the most direct evidence row.",
                                        "boundary_notes": ["ordering_only"],
                                    }
                                )
                            }
                        }
                    ],
                }
            ).encode("utf-8")

        self.service.llm_gateway = LLMGateway(
            base_url="https://llm.example.test",
            api_key="test-key",
            default_model="qwen3.6-plus",
            http_send=fake_rerank_send,
        )
        llm_reranked = self.router.dispatch(
            "POST",
            "/api/search/semantic/llm-rerank",
            {
                "q": "resilient services demand",
                "issuer_id": "issuer_demo",
                "limit": 3,
                "candidate_limit": 10,
                "llm_run_id": "llmrun_search_rerank_001",
            },
            role="CEO",
        )
        self.assertTrue(llm_reranked.success, llm_reranked.error)
        self.assertEqual(llm_reranked.data["reranker"], "llm_semantic_rerank_with_local_fallback")
        self.assertFalse(llm_reranked.data["automation_allowed"])
        self.assertFalse(llm_reranked.data["live_execution_allowed"])
        self.assertEqual(llm_reranked.data["fallback_used"], "")
        self.assertEqual(llm_reranked.data["results"][0]["rerank_source"], "llm")
        self.assertEqual(f"{llm_reranked.data['results'][0]['resource_type']}:{llm_reranked.data['results'][0]['resource_id']}", llm_target_ref)
        self.assertEqual(llm_reranked.data["llm_run"]["template_id"], "llmtpl_search_rerank_v1")
        self.assertIn("resource_ref", sent_rerank[0]["body"]["messages"][0]["content"])
        llm_benchmark = self.router.dispatch(
            "POST",
            "/api/search/semantic/llm-rerank/benchmark",
            {
                "benchmark_id": "bm_llm_rerank_demo",
                "samples": [
                    {
                        "q": "resilient services demand",
                        "issuer_id": "issuer_demo",
                        "expected_resource_refs": [llm_target_ref],
                        "candidate_limit": 10,
                        "limit": 3,
                        "llm_run_id": "llmrun_search_rerank_benchmark",
                    }
                ],
            },
            role="CEO",
        )
        self.assertTrue(llm_benchmark.success, llm_benchmark.error)
        self.assertEqual(llm_benchmark.data["valid_samples"], 1)
        self.assertEqual(llm_benchmark.data["top1_accuracy"], 1.0)
        self.assertEqual(llm_benchmark.data["mrr"], 1.0)
        self.assertEqual(llm_benchmark.data["llm_ordering_rate"], 1.0)
        self.assertFalse(llm_benchmark.data["automation_allowed"])
        self.assertEqual(llm_benchmark.data["usage_boundary"], "llm_rerank_benchmark_is_offline_quality_evaluation_not_fact_or_trade_signal")

        self.service.llm_gateway = LLMGateway(api_key="", http_send=lambda _request, _timeout: b"{}")
        fallback_rerank = self.router.dispatch(
            "POST",
            "/api/search/semantic/llm-rerank",
            {
                "q": "resilient services demand",
                "issuer_id": "issuer_demo",
                "limit": 3,
                "candidate_limit": 10,
                "llm_run_id": "llmrun_search_rerank_fallback",
            },
            role="CEO",
        )
        self.assertTrue(fallback_rerank.success, fallback_rerank.error)
        self.assertEqual(fallback_rerank.data["llm_run"]["status"], "fallback")
        self.assertEqual(fallback_rerank.data["fallback_used"], "rule_summary")
        self.assertTrue(fallback_rerank.data["human_review_required"])
        self.assertEqual(fallback_rerank.data["results"][0]["rerank_source"], "local_fallback")
        self.assertEqual(fallback_rerank.data["usage_boundary"], "llm_rerank_is_ordering_assist_only_not_fact_or_trade_signal")
        fallback_benchmark = self.router.dispatch(
            "POST",
            "/api/search/semantic/llm-rerank/benchmark",
            {
                "benchmark_id": "bm_llm_rerank_fallback",
                "samples": [
                    {
                        "q": "resilient services demand",
                        "issuer_id": "issuer_demo",
                        "expected_resource_refs": [f"{fallback_rerank.data['results'][0]['resource_type']}:{fallback_rerank.data['results'][0]['resource_id']}"],
                        "candidate_limit": 10,
                        "limit": 3,
                        "llm_run_id": "llmrun_search_rerank_benchmark_fallback",
                    }
                ],
            },
            role="CEO",
        )
        self.assertTrue(fallback_benchmark.success, fallback_benchmark.error)
        self.assertEqual(fallback_benchmark.data["valid_samples"], 1)
        self.assertEqual(fallback_benchmark.data["top1_accuracy"], 1.0)
        self.assertEqual(fallback_benchmark.data["fallback_rate"], 1.0)
        self.assertEqual(fallback_benchmark.data["results"][0]["rerank_source"], "local_fallback")

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

        readiness_gap = self.router.dispatch(
            "POST",
            "/api/graph-vector/readiness-report",
            {"issuer_id": "issuer_demo", "min_node_count": 1, "min_point_count": 1},
            role="platform",
        )
        self.assertTrue(readiness_gap.success, readiness_gap.error)
        self.assertFalse(readiness_gap.data["ready_for_graph_vector_production"])
        self.assertIn("neo4j_non_local_config", readiness_gap.data["missing_requirements"])
        self.assertIn("qdrant_non_local_config", readiness_gap.data["missing_requirements"])
        self.assertIn("throughput_baseline", readiness_gap.data["missing_requirements"])
        self.assertIn("failure_recovery_evidence", readiness_gap.data["missing_requirements"])
        self.assertFalse(readiness_gap.data["automation_allowed"])
        self.assertIn("graph_vector_readiness_report_requires_external", readiness_gap.data["usage_boundary"])

        readiness_ready = self.router.dispatch(
            "POST",
            "/api/graph-vector/readiness-report",
            {
                "issuer_id": "issuer_demo",
                "neo4j_endpoint": "neo4j+s://graph.prod.example.com",
                "qdrant_endpoint": "https://qdrant.prod.example.com",
                "throughput": {
                    "graph_nodes_per_second": 1200,
                    "vector_points_per_second": 2400,
                    "duration_seconds": 60,
                },
                "retry_result": {"retried_count": retried.data["retried_count"]},
                "artifact_uris": {
                    "neo4j_sync_artifact_uri": "artifact://prod/graph/neo4j-sync.json",
                    "qdrant_sync_artifact_uri": "artifact://prod/vector/qdrant-sync.json",
                    "throughput_baseline_uri": "artifact://prod/graph-vector/throughput.json",
                    "failure_recovery_uri": "artifact://prod/graph-vector/failure-recovery.json",
                    "permission_boundary_uri": "artifact://prod/graph-vector/permissions.json",
                },
                "record_readiness": True,
            },
            role="platform",
            actor="platform_owner",
        )
        self.assertTrue(readiness_ready.success, readiness_ready.error)
        self.assertTrue(readiness_ready.data["ready_for_graph_vector_production"])
        self.assertEqual(readiness_ready.data["missing_requirements"], [])
        self.assertEqual(readiness_ready.data["throughput"]["graph_nodes_per_second"], 1200.0)
        self.assertTrue(readiness_ready.data["adapters"]["neo4j"]["non_local_configured"])
        self.assertTrue(readiness_ready.data["adapters"]["qdrant"]["non_local_configured"])
        self.assertEqual(self.service.store.audit_log[-1].action, "graph_vector_readiness_report")

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
        self.assertIn("otel_collector_drill", gate.data["pending_checklist"])
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
        self.assertEqual(checklist.data["required"], 9)
        self.assertEqual(checklist.data["passed"], 2)
        self.assertEqual(checklist.data["coverage"], 0.2222)

        updated_gate = self.router.dispatch("GET", "/api/readiness/vision-gate", {}, role="CEO")
        self.assertTrue(updated_gate.success)
        self.assertNotIn("production_ui_screenshot_acceptance", updated_gate.data["pending_checklist"])
        self.assertNotIn("capacity_latency_report", updated_gate.data["pending_checklist"])
        self.assertIn("real_data_smoke_test", updated_gate.data["pending_checklist"])
        self.assertIn("otel_collector_drill", updated_gate.data["pending_checklist"])
        self.assertEqual(updated_gate.data["counts"]["readiness_checks"], 2)

        invalid = self.router.dispatch(
            "POST",
            "/api/readiness/checklist/real_data_smoke_test",
            {
                "status": "passed",
                "owner": "platform_owner",
                "evidence_uri": "file:///tmp/real-data-smoke.json",
                "metrics": {"accepted": True},
            },
            actor="platform_owner",
            role="platform",
        )
        self.assertTrue(invalid.success, invalid.error)
        invalid_checklist = self.router.dispatch("GET", "/api/readiness/checklist", {}, role="risk_compliance")
        self.assertTrue(invalid_checklist.success)
        invalid_row = next(item for item in invalid_checklist.data["checks"] if item["check_id"] == "real_data_smoke_test")
        self.assertEqual(invalid_row["effective_status"], "invalid_evidence_uri")
        self.assertIn("real_data_smoke_test", invalid_checklist.data["pending_checklist"])

        for invalid_uri in ["artifact://local-staging/real-data-smoke.json", "s3://ai-quant-prod"]:
            invalid_artifact = self.router.dispatch(
                "POST",
                "/api/readiness/checklist/real_data_smoke_test",
                {
                    "status": "passed",
                    "owner": "platform_owner",
                    "evidence_uri": invalid_uri,
                    "metrics": {"accepted": True},
                },
                actor="platform_owner",
                role="platform",
            )
            self.assertTrue(invalid_artifact.success, invalid_artifact.error)
            invalid_artifact_checklist = self.router.dispatch("GET", "/api/readiness/checklist", {}, role="risk_compliance")
            self.assertTrue(invalid_artifact_checklist.success)
            invalid_artifact_row = next(item for item in invalid_artifact_checklist.data["checks"] if item["check_id"] == "real_data_smoke_test")
            self.assertEqual(invalid_artifact_row["effective_status"], "invalid_evidence_uri")
            self.assertIn("real_data_smoke_test", invalid_artifact_checklist.data["pending_checklist"])

        external_artifact = self.router.dispatch(
            "POST",
            "/api/readiness/checklist/real_data_smoke_test",
            {
                "status": "passed",
                "owner": "platform_owner",
                "evidence_uri": "s3://ai-quant-prod/readiness/real-data-smoke.json",
                "metrics": {"accepted": True},
            },
            actor="platform_owner",
            role="platform",
        )
        self.assertTrue(external_artifact.success, external_artifact.error)
        external_artifact_checklist = self.router.dispatch("GET", "/api/readiness/checklist", {}, role="risk_compliance")
        self.assertTrue(external_artifact_checklist.success)
        external_artifact_row = next(item for item in external_artifact_checklist.data["checks"] if item["check_id"] == "real_data_smoke_test")
        self.assertEqual(external_artifact_row["effective_status"], "passed")

    def test_ui_readiness_report_requires_browser_matrix_and_workflow_evidence(self) -> None:
        gap = self.router.dispatch("GET", "/api/readiness/ui-report", {}, role="CEO")
        self.assertTrue(gap.success, gap.error)
        self.assertFalse(gap.data["ready_for_ui_production"])
        self.assertTrue(gap.data["static_contract"]["passed"])
        self.assertIn("production_ui_screenshot_acceptance_record", gap.data["missing_requirements"])
        self.assertIn("required_text_browser_acceptance", gap.data["missing_requirements"])
        self.assertIn("cross_browser_acceptance_record", gap.data["missing_requirements"])
        self.assertIn("real_data_ui_walkthrough_uri", gap.data["missing_requirements"])
        self.assertIn("ui_data_volume_workflow", gap.data["missing_requirements"])
        self.assertIn("ui_text_no_overlap_review", gap.data["missing_requirements"])
        self.assertIn("ui_permission_state_review", gap.data["missing_requirements"])
        self.assertFalse(gap.data["automation_allowed"])

        ui_browser_metrics = {
            "status": "passed",
            "browser": "/usr/bin/chromium",
            "ui_url": "https://staging.example.test/ui",
            "required_text": ["公司情报与市场综合分析平台", "总览", "风控合规"],
            "missing_text": [],
            "failure_count": 0,
            "screenshots": [
                {"name": "desktop", "width": 1440, "height": 1000, "nonblank": True, "sha256": "d" * 64},
                {"name": "mobile", "width": 390, "height": 844, "nonblank": True, "sha256": "m" * 64},
            ],
            "evidence_uri": "artifact://staging/ui-browser-acceptance.json",
        }
        screenshot = self.router.dispatch(
            "POST",
            "/api/readiness/checklist/production_ui_screenshot_acceptance",
            {
                "status": "passed",
                "owner": "platform_owner",
                "evidence_uri": "artifact://staging/ui-browser-screenshots.json",
                "notes": "desktop and mobile screenshots accepted",
                "metrics": {
                    **ui_browser_metrics,
                    "data_volume_rows": 2500,
                    "pagination_checked": True,
                    "filtering_checked": True,
                    "error_states_checked": True,
                    "real_data_checked": True,
                },
            },
            actor="platform_owner",
            role="platform",
        )
        self.assertTrue(screenshot.success, screenshot.error)
        browser = self.router.dispatch(
            "POST",
            "/api/readiness/checklist/cross_browser_acceptance",
            {
                "status": "passed",
                "owner": "platform_owner",
                "evidence_uri": "artifact://staging/ui-browser-matrix.json",
                "notes": "browser matrix accepted",
                "metrics": {
                    **ui_browser_metrics,
                    "browser_matrix": [
                        {"browser": "chromium", "viewport": "desktop", "status": "passed"},
                        {"browser": "firefox", "viewport": "mobile", "status": "passed"},
                    ],
                    "browsers_checked": ["chromium", "firefox"],
                    "permission_checked": True,
                    "permission_states_checked": True,
                    "text_no_overlap_checked": True,
                    "visual_no_overflow_checked": True,
                    "responsive_layout_checked": True,
                },
            },
            actor="platform_owner",
            role="platform",
        )
        self.assertTrue(browser.success, browser.error)

        uri_only = self.router.dispatch(
            "POST",
            "/api/readiness/ui-report",
            {
                "artifact_uris": {
                    "cross_browser_matrix_uri": "artifact://staging/ui-browser-matrix.json",
                    "real_data_workflow_uri": "artifact://staging/ui-real-data-workflows.json",
                    "visual_overflow_review_uri": "artifact://staging/ui-no-overflow-review.json",
                    "access_control_review_uri": "artifact://staging/ui-permission-review.json",
                },
                "browser_acceptance": {
                    **ui_browser_metrics,
                    "browser_matrix": [{"browser": "chromium", "viewport": "desktop", "status": "passed"}],
                    "browsers_checked": ["chromium"],
                },
            },
            actor="platform_owner",
            role="platform",
        )
        self.assertTrue(uri_only.success, uri_only.error)
        self.assertFalse(uri_only.data["ready_for_ui_production"])
        self.assertIn("cross_browser_matrix_coverage", uri_only.data["missing_requirements"])
        self.assertFalse(uri_only.data["browser_acceptance"]["cross_browser_matrix_ready"])

        ready = self.router.dispatch(
            "POST",
            "/api/readiness/ui-report",
            {
                "record_readiness": True,
                "artifact_uris": {
                    "cross_browser_matrix_uri": "artifact://staging/ui-browser-matrix.json",
                    "real_data_workflow_uri": "artifact://staging/ui-real-data-workflows.json",
                    "visual_overflow_review_uri": "artifact://staging/ui-no-overflow-review.json",
                    "access_control_review_uri": "artifact://staging/ui-permission-review.json",
                },
            },
            actor="platform_owner",
            role="platform",
        )
        self.assertTrue(ready.success, ready.error)
        self.assertTrue(ready.data["ready_for_ui_production"])
        self.assertEqual(ready.data["missing_requirements"], [])
        self.assertTrue(ready.data["browser_acceptance"]["required_viewports_nonblank"])
        self.assertTrue(ready.data["browser_acceptance"]["required_text_present"])
        self.assertTrue(ready.data["browser_acceptance"]["cross_browser_matrix_ready"])
        self.assertEqual(ready.data["browser_acceptance"]["browser_families"], ["chromium", "firefox"])
        self.assertEqual(ready.data["workflow_evidence"]["real_data_flags"]["pagination"], True)
        self.assertEqual(ready.data["workflow_evidence"]["real_data_flags"]["data_volume"], True)
        self.assertEqual(ready.data["workflow_evidence"]["real_data_step_ready"]["data_volume"], True)
        self.assertEqual(ready.data["workflow_evidence"]["visual_step_ready"]["text_no_overlap"], True)
        self.assertEqual(ready.data["workflow_evidence"]["permission_state_ready"], True)
        self.assertEqual(self.service.store.audit_log[-1].action, "ui_readiness_report")

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
        self.assertIn("otel_collector_drill", required_ids)
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

    def test_deployment_report_requires_release_evidence_and_redacts_secret_values(self) -> None:
        blocked = self.router.dispatch(
            "POST",
            "/api/readiness/deployment-report",
            {"secret_value": "should-not-be-recorded"},
            role="platform",
        )
        self.assertFalse(blocked.success)
        self.assertIn("must not include secret values", blocked.error["message"])

        gap = self.router.dispatch("POST", "/api/readiness/deployment-report", {}, role="platform")
        self.assertTrue(gap.success, gap.error)
        self.assertFalse(gap.data["ready_for_production_deployment"])
        self.assertIn("postgres_config_present", gap.data["missing_requirements"])
        self.assertIn("production_parameters_uri", gap.data["missing_requirements"])
        self.assertIn("secret_manager_config_present", gap.data["missing_requirements"])
        self.assertIn("backup_restore_drill_record", gap.data["missing_requirements"])
        self.assertTrue(gap.data["runtime"]["sensitive_values_redacted"])
        self.assertFalse(gap.data["live_execution_allowed"])

        required_checks = [
            "real_data_smoke_test",
            "production_ui_screenshot_acceptance",
            "cross_browser_acceptance",
            "capacity_latency_report",
            "backup_restore_drill",
            "otel_collector_drill",
            "permission_red_team_test",
            "compliance_review_record",
            "launch_checklist",
        ]
        for check_id in required_checks:
            recorded = self.router.dispatch(
                "POST",
                f"/api/readiness/checklist/{check_id}",
                {
                    "status": "passed",
                    "owner": "release_owner",
                    "evidence_uri": f"artifact://prod-readiness/{check_id}.json",
                    "metrics": {"accepted": True},
                },
                role="platform" if check_id not in {"permission_red_team_test", "compliance_review_record", "launch_checklist"} else "risk_compliance",
                actor="release_owner",
            )
            self.assertTrue(recorded.success, recorded.error)
        rotation = self.router.dispatch(
            "POST",
            "/api/governance/secret-rotations",
            {
                "rotation_id": "secrot_prod_release",
                "secret_name": "AI_QUANT_S3_SECRET_KEY",
                "provider": "vault",
                "owner": "platform_owner",
                "status": "rotated",
                "evidence_uri": "artifact://prod-readiness/secret-rotation.json",
            },
            role="risk_compliance",
            actor="risk_owner",
        )
        self.assertTrue(rotation.success, rotation.error)

        plan_fields_only = self.router.dispatch(
            "POST",
            "/api/readiness/deployment-report",
            {
                "environment_name": "prod",
                "postgres_configured": True,
                "s3_configured": True,
                "opensearch_configured": True,
                "secret_manager_provider": "vault",
                "secret_injection_mode": "runtime_env_from_vault_agent",
                "release_plan": {
                    "release_id": "rel_prod_20260517",
                    "owner": "release_owner",
                    "canary_window": "2026-05-17T10:00Z/2026-05-17T12:00Z",
                    "rollback_owner": "platform_owner",
                    "rollback_window": "15m",
                },
                "artifact_uris": {
                    "secret_manager_evidence_uri": "artifact://prod-readiness/secret-manager.json",
                    "backup_restore_evidence_uri": "artifact://prod-readiness/backup-restore.json",
                    "capacity_baseline_uri": "artifact://prod-readiness/capacity.json",
                    "release_checklist_uri": "artifact://prod-readiness/release-checklist.json",
                },
            },
            role="platform",
            actor="release_owner",
        )
        self.assertTrue(plan_fields_only.success, plan_fields_only.error)
        self.assertFalse(plan_fields_only.data["ready_for_production_deployment"])
        self.assertIn("production_parameters_uri", plan_fields_only.data["missing_requirements"])
        self.assertIn("canary_plan_uri", plan_fields_only.data["missing_requirements"])
        self.assertIn("rollback_plan_uri", plan_fields_only.data["missing_requirements"])

        self.router.dispatch(
            "POST",
            "/api/readiness/checklist/capacity_latency_report",
            {"status": "passed", "owner": "release_owner", "evidence_uri": "file:///tmp/capacity.json"},
            role="platform",
            actor="release_owner",
        )
        self.router.dispatch(
            "POST",
            "/api/readiness/checklist/backup_restore_drill",
            {"status": "passed", "owner": "release_owner", "evidence_uri": "local://backup-restore.json"},
            role="platform",
            actor="release_owner",
        )
        local_record_evidence = self.router.dispatch(
            "POST",
            "/api/readiness/deployment-report",
            {
                "environment_name": "prod",
                "postgres_configured": True,
                "s3_configured": True,
                "opensearch_configured": True,
                "secret_manager_provider": "vault",
                "secret_injection_mode": "runtime_env_from_vault_agent",
                "artifact_uris": {
                    "production_parameters_uri": "artifact://prod-readiness/parameters.json",
                    "secret_manager_evidence_uri": "artifact://prod-readiness/secret-manager.json",
                    "release_checklist_uri": "artifact://prod-readiness/release-checklist.json",
                    "canary_plan_uri": "artifact://prod-readiness/canary-plan.md",
                    "rollback_plan_uri": "artifact://prod-readiness/rollback-plan.md",
                },
            },
            role="platform",
            actor="release_owner",
        )
        self.assertTrue(local_record_evidence.success, local_record_evidence.error)
        self.assertFalse(local_record_evidence.data["ready_for_production_deployment"])
        self.assertIn("backup_restore_drill_record", local_record_evidence.data["missing_requirements"])
        self.assertIn("backup_restore_evidence_uri", local_record_evidence.data["missing_requirements"])
        self.assertIn("capacity_baseline_record", local_record_evidence.data["missing_requirements"])
        self.assertIn("capacity_baseline_evidence_uri", local_record_evidence.data["missing_requirements"])

        for check_id in ["capacity_latency_report", "backup_restore_drill"]:
            recorded = self.router.dispatch(
                "POST",
                f"/api/readiness/checklist/{check_id}",
                {
                    "status": "passed",
                    "owner": "release_owner",
                    "evidence_uri": f"artifact://prod-readiness/{check_id}.json",
                    "metrics": {"accepted": True},
                },
                role="platform",
                actor="release_owner",
            )
            self.assertTrue(recorded.success, recorded.error)

        ready = self.router.dispatch(
            "POST",
            "/api/readiness/deployment-report",
            {
                "environment_name": "prod",
                "postgres_configured": True,
                "s3_configured": True,
                "opensearch_configured": True,
                "secret_manager_provider": "vault",
                "secret_injection_mode": "runtime_env_from_vault_agent",
                "release_plan": {
                    "release_id": "rel_prod_20260517",
                    "owner": "release_owner",
                    "canary_window": "2026-05-17T10:00Z/2026-05-17T12:00Z",
                    "rollback_owner": "platform_owner",
                    "rollback_window": "15m",
                },
                "artifact_uris": {
                    "production_parameters_uri": "artifact://prod-readiness/parameters.json",
                    "secret_manager_evidence_uri": "artifact://prod-readiness/secret-manager.json",
                    "backup_restore_evidence_uri": "artifact://prod-readiness/backup-restore.json",
                    "capacity_baseline_uri": "artifact://prod-readiness/capacity.json",
                    "release_checklist_uri": "artifact://prod-readiness/release-checklist.json",
                    "canary_plan_uri": "artifact://prod-readiness/canary-plan.md",
                    "rollback_plan_uri": "artifact://prod-readiness/rollback-plan.md",
                },
                "record_readiness": True,
            },
            role="platform",
            actor="release_owner",
        )
        self.assertTrue(ready.success, ready.error)
        self.assertTrue(ready.data["ready_for_production_deployment"])
        self.assertEqual(ready.data["missing_requirements"], [])
        self.assertEqual(ready.data["runtime"]["environment"], "prod")
        self.assertEqual(ready.data["secret_manager"]["provider"], "vault")
        self.assertEqual(ready.data["secret_rotation_summary"]["count"], 1)
        self.assertEqual(self.service.store.audit_log[-1].action, "readiness_deployment_report")

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
                "sector": "Technology",
                "industry": "Software",
                "company_details": {"country": "United States", "ipo_year": "2020"},
                "fundamentals": {"sector": "Technology", "industry": "Software"},
                "valuation_metrics": {"market_cap": 123456789.0, "currency": "USD"},
                "data_sources": ["nasdaq_screener_sec_company_tickers"],
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
                "security_type": "common_stock",
                "sector": "Technology",
                "industry": "Software",
                "listing_date": "2020",
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
        self.assertEqual(reloaded.store.issuers["issuer_pg"].industry, "Software")
        self.assertEqual(reloaded.store.issuers["issuer_pg"].valuation_metrics["market_cap"], 123456789.0)
        self.assertEqual(reloaded.store.issuers["issuer_pg"].company_details["ipo_year"], "2020")
        self.assertEqual(reloaded.store.securities["security_pg"].security_type, "common_stock")
        self.assertEqual(reloaded.store.securities["security_pg"].industry, "Software")
        self.assertNotIn(market_point.data_id, reloaded.store.market_data)
        self.assertEqual(reloaded.market_data_payload({"security_id": "security_pg"})["market_data"][0]["close"], 45.75)
        self.assertIn(holding.holding_id, reloaded.store.institutional_holdings)
        self.assertEqual(reloaded.institutional_holdings_payload({"issuer_id": "issuer_pg"})["holdings"][0]["value_usd"], 45750.0)
        self.assertEqual(len(reloaded.store.audit_log), audit_count)
        self.assertNotIn(("market_data", "md_pg"), database.records)
        self.assertIn(("security_pg", "public_eod_market_data", "eod", "2026-05-14"), database.market_data_bars)
        self.assertEqual(float(database.market_data_bars[("security_pg", "public_eod_market_data", "eod", "2026-05-14")]["close"]), 45.75)
        self.assertIn("register_market_data_point", {event["payload"]["action"] for event in database.audit.values()})

    def test_postgresql_store_hydrates_research_binding_asset_fields(self) -> None:
        database = _FakePostgresDatabase()
        rights_tag = {
            "license_class": "local_research_reference",
            "training_allowed": False,
            "redistribution_allowed": False,
            "display_use": "restricted",
            "non_display_use": "restricted",
            "derived_data_use": "restricted",
        }
        database.records[("documents", "doc_binding")] = {
            "payload": {
                "document_id": "doc_binding",
                "issuer_id": "issuer_nvda",
                "security_id": "security_nvda_us",
                "document_type": "research_report",
                "source_id": "local_research_reports",
                "source_type": "local_research_report",
                "source_uri": "file:///reports/nvda.pdf",
                "rights_tag": rights_tag,
                "published_at": "2026-05-24T00:00:00+00:00",
                "ingested_at": "2026-05-24T00:00:00+00:00",
                "asset_matches": [{"security_id": "security_nvda_us", "issuer_id": "issuer_nvda"}],
                "chain_id": "chain_ai_compute",
                "node_ids": ["gpu"],
                "future_extra_field": "kept_in_postgres_payload_but_not_model",
            },
            "position": None,
        }
        database.records[("evidence", "evi_binding")] = {
            "payload": {
                "evidence_id": "evi_binding",
                "document_id": "doc_binding",
                "section": "research_report_citation",
                "page_no": 1,
                "bbox": "page=1;chunk=1",
                "span_text": "NVDA demand remains strong.",
                "canonical_text": "NVDA demand remains strong.",
                "confidence": 0.9,
                "locator": {},
                "assets": [{"security_id": "security_nvda_us", "issuer_id": "issuer_nvda"}],
                "security_id": "security_nvda_us",
                "issuer_id": "issuer_nvda",
                "chain_id": "chain_ai_compute",
                "node_ids": ["gpu"],
                "evidence_topics": ["ai_compute"],
                "risk_tags": ["valuation"],
                "financial_metric_tags": ["revenue"],
                "viewpoint": {"sentiment": "positive"},
                "created_at": "2026-05-24T00:00:00+00:00",
                "future_extra_field": "ignored_by_model",
            },
            "position": None,
        }
        database.records[("research_reports", "rr_binding")] = {
            "payload": {
                "report_id": "rr_binding",
                "source_id": "local_research_reports",
                "broker": "Broker",
                "file_path": "/reports/nvda.pdf",
                "file_name": "nvda.pdf",
                "title": "NVDA AI compute report",
                "rights_tag": rights_tag,
                "document_id": "doc_binding",
                "issuer_id": "issuer_nvda",
                "security_id": "security_nvda_us",
                "asset_matches": [{"security_id": "security_nvda_us", "issuer_id": "issuer_nvda"}],
                "asset_binding": {"status": "matched"},
                "chain_id": "chain_ai_compute",
                "node_ids": ["gpu"],
                "evidence_topics": ["ai_compute"],
                "risk_tags": ["valuation"],
                "financial_metric_tags": ["revenue"],
                "viewpoint": {"sentiment": "positive"},
                "indexed_at": "2026-05-24T00:00:00+00:00",
                "future_extra_field": "ignored_by_model",
            },
            "position": None,
        }

        service = SystemService(PostgreSQLStore("postgresql://example.invalid/ai_quant", connect=database.connect))

        document = service.store.documents["doc_binding"]
        evidence = service.store.evidence["evi_binding"]
        report = service.store.research_reports["rr_binding"]
        self.assertEqual(document.chain_id, "chain_ai_compute")
        self.assertEqual(document.asset_matches[0]["security_id"], "security_nvda_us")
        self.assertEqual(evidence.chain_id, "chain_ai_compute")
        self.assertEqual(evidence.evidence_topics, ["ai_compute"])
        self.assertEqual(evidence.viewpoint["sentiment"], "positive")
        self.assertEqual(report.asset_binding["status"], "matched")
        self.assertEqual(report.financial_metric_tags, ["revenue"])

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

    def test_postgres_store_skips_schema_ddl_when_baseline_migration_is_recorded(self) -> None:
        database = _FakePostgresDatabase()
        database.baseline_schema_recorded = True
        store = PostgreSQLStore("postgresql://example.invalid/ai_quant", connect=database.connect)

        self.assertIsInstance(store, PostgreSQLStore)
        self.assertEqual(database.schema_runs, 0)
        self.assertTrue(any("schema_migrations" in statement for statement in database.statements))
        self.assertFalse(any("create schema if not exists ai_quant" in " ".join(statement.split()).lower() for statement in database.statements))

    def test_market_data_storage_audit_requires_typed_only_runtime_storage(self) -> None:
        class FakeAuditCursor:
            def __init__(self, legacy_count):
                self.legacy_count = legacy_count
                self.rows = []

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return None

            def execute(self, sql, params=None):
                normalized = " ".join(sql.split()).lower()
                if "count(*) from ai_quant.records where collection = 'market_data'" in normalized:
                    self.rows = [(self.legacy_count,)]
                elif "pg_stat_user_tables" in normalized and "market_data_bars" in normalized:
                    self.rows = [(3,)]
                elif "select as_of_date::text from ai_quant.market_data_bars order by as_of_date asc" in normalized:
                    self.rows = [("2026-05-20",)]
                elif "select as_of_date::text from ai_quant.market_data_bars order by as_of_date desc" in normalized:
                    self.rows = [("2026-05-22",)]
                elif "from pg_views" in normalized:
                    self.rows = [("market_data",)]
                elif "from pg_indexes" in normalized:
                    self.rows = [
                        ("idx_ai_quant_market_data_bars_as_of_date",),
                        ("idx_ai_quant_market_data_bars_data_id",),
                        ("idx_ai_quant_market_data_bars_market_date",),
                        ("idx_ai_quant_market_data_bars_security_date",),
                        ("idx_ai_quant_market_data_bars_source_date",),
                    ]
                elif "pg_total_relation_size" in normalized:
                    self.rows = [("market_data_bars", "42 GB"), ("records", "306 MB")]
                elif normalized.startswith("explain"):
                    self.rows = [([{"Plan": {"Node Type": "Limit", "Plans": [{"Node Type": "Index Scan", "Index Name": "idx_ai_quant_market_data_bars_as_of_date"}]}}],)]
                else:
                    self.rows = []

            def fetchone(self):
                return self.rows[0] if self.rows else None

            def fetchall(self):
                return list(self.rows)

        class FakeAuditConnection:
            def __init__(self, legacy_count):
                self.legacy_count = legacy_count

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return None

            def cursor(self):
                return FakeAuditCursor(self.legacy_count)

            def close(self):
                return None

        original_connect = market_data_storage_audit_script._connect
        try:
            market_data_storage_audit_script._connect = lambda _dsn: FakeAuditConnection(0)  # type: ignore[assignment]
            passed = market_data_storage_audit_script.build_market_data_storage_audit(
                dsn="postgresql://example.invalid/ai_quant",
                base_url="",
                sample_security_id="sec_000001",
                sample_source_id="public_eod_market_data",
                sample_data_type="eod",
                timeout=1.0,
            )
            self.assertTrue(passed["passed"])
            self.assertEqual(passed["legacy_market_data_records"], 0)

            market_data_storage_audit_script._connect = lambda _dsn: FakeAuditConnection(1)  # type: ignore[assignment]
            failed = market_data_storage_audit_script.build_market_data_storage_audit(
                dsn="postgresql://example.invalid/ai_quant",
                base_url="",
                sample_security_id="sec_000001",
                sample_source_id="public_eod_market_data",
                sample_data_type="eod",
                timeout=1.0,
            )
            self.assertFalse(failed["passed"])
            self.assertEqual(failed["failures"][0]["check"], "legacy_market_data_records")
        finally:
            market_data_storage_audit_script._connect = original_connect  # type: ignore[assignment]

    def test_tdx_vipdoc_postgres_reader_supports_tail_incremental_window(self) -> None:
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "sh600000.day"
            rows = [
                (20260520, 1000, 1100, 900, 1050, 1000.0, 100, 0),
                (20260521, 1050, 1150, 950, 1100, 2000.0, 200, 0),
                (20260522, 1100, 1200, 1000, 1150, 3000.0, 300, 0),
            ]
            path.write_bytes(b"".join(struct.pack("<IIIIIfII", *row) for row in rows))

            incremental = read_day_rows(path, start_date="2026-05-21", end_date="2026-05-24", limit=0)
            self.assertEqual([row["trade_date"] for row in incremental], ["2026-05-21", "2026-05-22"])

            limited = read_day_rows(path, start_date="2026-05-20", end_date="2026-05-24", limit=2)
            self.assertEqual([row["trade_date"] for row in limited], ["2026-05-20", "2026-05-21"])

    def test_ashare_baostock_db_symbols_filter_to_stock_like_codes_and_batch_latest_dates(self) -> None:
        class FakeCursor:
            def __init__(self):
                self.rows = []

            def execute(self, sql, params=None):
                normalized = " ".join(sql.split()).lower()
                if "from ai_quant.records" in normalized and "collection = 'securities'" in normalized:
                    self.rows = [
                        ("000001", "sec_000001", "issuer_000001", "SZSE"),
                        ("159958", "sec_159958", "issuer_159958", "SZSE"),
                        ("600519", "sec_600519", "issuer_600519", "SSE"),
                        ("900901", "sec_900901", "issuer_900901", "SSE"),
                    ]
                elif "from ai_quant.market_data_bars" in normalized and "security_id = any" in normalized:
                    self.rows = [("sec_000001", "2026-05-22"), ("sec_600519", "2026-05-22")]
                else:
                    self.rows = []

            def fetchall(self):
                return list(self.rows)

        cursor = FakeCursor()
        symbols = import_ashare_eod_baostock_script._symbols_from_db(cursor)
        self.assertEqual([item["symbol"] for item in symbols], ["000001", "600519"])
        latest = import_ashare_eod_baostock_script._latest_dates_for_symbols(
            cursor,
            security_ids=[item["security_id"] for item in symbols],
            source_id="public_eod_market_data",
            data_type="eod",
        )
        self.assertEqual(latest["sec_000001"], "2026-05-22")

    def test_ashare_baostock_db_symbols_query_requires_active_in_scope(self) -> None:
        class CaptureCursor:
            def __init__(self):
                self.sql = ""

            def execute(self, sql, params=None):
                self.sql = " ".join(sql.split()).lower()

            def fetchall(self):
                return []

        cursor = CaptureCursor()
        import_ashare_eod_baostock_script._symbols_from_db(cursor)
        self.assertIn("company_universe_scope", cursor.sql)
        self.assertIn("in_scope", cursor.sql)

    def test_scope_ashare_current_baostock_universe_script_exists_and_is_documented(self) -> None:
        script = Path("scripts/scope_ashare_current_baostock_universe.py").read_text(encoding="utf-8")
        self.assertIn("baostock", script)
        self.assertIn("company_universe_scope", script)
        runbook = Path("docs/production-runbook.md").read_text(encoding="utf-8")
        self.assertIn("AI_QUANT_DAILY_RUN_ASHARE_SCOPE_REFRESH=true", runbook)
        self.assertIn("baostock active common-stock universe", runbook)

    def test_ashare_scope_can_seed_missing_active_security_records(self) -> None:
        security_id, security, issuer_id, issuer = scope_ashare_current_baostock_universe_script._seed_row_from_active_symbol(
            "600519",
            {"symbol": "600519", "name": "贵州茅台", "baostock_code": "sh.600519"},
        )
        self.assertEqual(security_id, "sec_600519")
        self.assertEqual(issuer_id, "issuer_600519")
        self.assertEqual(security["ticker"], "600519")
        self.assertEqual(security["market"], "A")
        self.assertEqual(issuer["legal_name"], "贵州茅台")

    def test_us_yahoo_import_can_batch_registered_universe_without_duplicate_ids(self) -> None:
        class FakeCursor:
            def __init__(self):
                self.rows = []
                self.sql = ""

            def execute(self, sql, params=None):
                normalized = " ".join(sql.split()).lower()
                self.sql = normalized
                if "from ai_quant.records as s" in normalized and "s.collection = 'securities'" in normalized:
                    self.rows = [
                        (
                            "security_aapl_us",
                            {"ticker": "AAPL", "market": "U", "status": "active", "security_id": "security_aapl_us", "issuer_id": "issuer_aapl", "currency": "USD"},
                            {"issuer_id": "issuer_aapl", "legal_name": "AAPL"},
                        ),
                        (
                            "security_us_aapl",
                            {"ticker": "AAPL", "market": "U", "status": "active", "security_id": "security_us_aapl", "issuer_id": "issuer_us_aapl", "currency": "USD"},
                            {"issuer_id": "issuer_us_aapl", "legal_name": "Apple Inc."},
                        ),
                        (
                            "security_us_msft",
                            {"ticker": "MSFT", "market": "U", "status": "active", "security_id": "security_us_msft", "issuer_id": "issuer_us_msft", "currency": "USD"},
                            {"issuer_id": "issuer_us_msft", "legal_name": "Microsoft Corporation"},
                        ),
                    ]
                else:
                    self.rows = []

            def fetchall(self):
                return list(self.rows)

        cursor = FakeCursor()
        all_records = import_us_eod_yahoo_chart_script._ticker_records_from_db(cursor)
        self.assertEqual([record["ticker"] for record in all_records], ["AAPL", "MSFT"])
        self.assertEqual(all_records[0]["security_id"], "security_aapl_us")
        self.assertIn("market_data_refresh_scope", cursor.sql)
        self.assertIn("in_scope", cursor.sql)
        batch = import_us_eod_yahoo_chart_script._ticker_records_from_db(cursor, offset=1, max_tickers=1)
        self.assertEqual([(record["ticker"], record["security_id"]) for record in batch], [("MSFT", "security_us_msft")])
        self.assertEqual(import_us_eod_yahoo_chart_script._yahoo_chart_symbol_candidates("BF.B"), ["BF.B", "BF-B"])

    def test_us_yahoo_scope_classifies_reference_and_duplicate_records(self) -> None:
        preferred = scope_us_current_yahoo_universe_script._classify_security("TRTN$G", "Preference Shares", "NYSE")
        self.assertEqual(preferred["scope"], "out_of_scope")
        self.assertEqual(preferred["reason"], "preferred_or_preference_security")
        common = scope_us_current_yahoo_universe_script._classify_security("AAPL", "Apple Inc. Common Stock", "Nasdaq")
        self.assertEqual(common["scope"], "in_scope")
        adr = scope_us_current_yahoo_universe_script._classify_security("API", "Agora Inc. American Depositary Shares", "Nasdaq")
        self.assertEqual(adr["scope"], "in_scope")
        depositary_preferred = scope_us_current_yahoo_universe_script._classify_security("FITBI", "Fifth Third Bancorp Depositary Shares", "Nasdaq")
        self.assertEqual(depositary_preferred["reason"], "preferred_depositary_security")
        script = Path("scripts/scope_us_current_yahoo_universe.py").read_text(encoding="utf-8")
        self.assertIn("market_data_refresh_scope", script)
        self.assertIn("duplicate_ticker_refresh_record", script)

    def test_us_yahoo_scope_can_seed_missing_records_from_existing_bars(self) -> None:
        class FakeCursor:
            def __init__(self):
                self.rows = []

            def execute(self, sql, params=None):
                normalized = " ".join(sql.split()).lower()
                if "from ai_quant.market_data_bars" in normalized:
                    self.rows = [
                        ("security_aapl_us", "2026-05-22"),
                        ("security_us_msft", "2026-05-22"),
                        ("bad id", "2026-05-22"),
                    ]
                else:
                    self.rows = []

            def fetchall(self):
                return list(self.rows)

        rows = scope_us_current_yahoo_universe_script._seed_rows_from_existing_yahoo_bars(FakeCursor(), set())
        self.assertEqual([row["ticker"] for row in rows], ["AAPL", "MSFT"])
        self.assertEqual(rows[0]["security_id"], "security_aapl_us")
        self.assertEqual(rows[0]["security"]["market"], "U")
        self.assertEqual(rows[0]["classification"]["scope"], "in_scope")
        filtered = scope_us_current_yahoo_universe_script._seed_rows_from_existing_yahoo_bars(FakeCursor(), {"MSFT"})
        self.assertEqual([row["ticker"] for row in filtered], ["MSFT"])

    def test_us_yahoo_import_status_fails_when_every_ticker_fails(self) -> None:
        class FakeCursor:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return None

            def execute(self, _sql, _params=None):
                return None

            def fetchall(self):
                return []

        class FakeConnection:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return None

            def cursor(self):
                return FakeCursor()

            def commit(self):
                return None

        original_psycopg = sys.modules.get("psycopg")
        original_fetch_chart = import_us_eod_yahoo_chart_script._fetch_chart
        try:
            import types

            sys.modules["psycopg"] = types.SimpleNamespace(connect=lambda _dsn: FakeConnection())  # type: ignore[assignment]
            import_us_eod_yahoo_chart_script._fetch_chart = lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("outage"))  # type: ignore[assignment]
            result = import_us_eod_yahoo_chart_script.import_us_eod(
                argparse.Namespace(
                    dsn="postgresql://example.invalid/ai_quant",
                    tickers=["BAD"],
                    tickers_from_db=False,
                    ticker_filter="",
                    offset=0,
                    max_tickers=0,
                    start_date="2026-05-22",
                    end_date="2026-05-22",
                    user_agent="test",
                    timeout=1.0,
                )
            )
        finally:
            import_us_eod_yahoo_chart_script._fetch_chart = original_fetch_chart  # type: ignore[assignment]
            if original_psycopg is None:
                sys.modules.pop("psycopg", None)
            else:
                sys.modules["psycopg"] = original_psycopg

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failure_count"], 1)

    def test_us_yahoo_import_skips_current_typed_bars(self) -> None:
        class FakeCursor:
            def __init__(self):
                self.rows = []

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return None

            def execute(self, sql, params=None):
                normalized = " ".join(sql.split()).lower()
                if "select security_id, max(as_of_date)::text" in normalized:
                    self.rows = [("security_aapl_us", "2026-05-22")]
                else:
                    self.rows = []

            def fetchall(self):
                return list(self.rows)

        class FakeConnection:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return None

            def cursor(self):
                return FakeCursor()

            def commit(self):
                return None

        original_psycopg = sys.modules.get("psycopg")
        original_fetch_chart = import_us_eod_yahoo_chart_script._fetch_chart
        try:
            import types

            sys.modules["psycopg"] = types.SimpleNamespace(connect=lambda _dsn: FakeConnection())  # type: ignore[assignment]
            import_us_eod_yahoo_chart_script._fetch_chart = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("should not fetch current ticker"))  # type: ignore[assignment]
            result = import_us_eod_yahoo_chart_script.import_us_eod(
                argparse.Namespace(
                    dsn="postgresql://example.invalid/ai_quant",
                    tickers=["AAPL"],
                    tickers_from_db=False,
                    ticker_filter="",
                    offset=0,
                    max_tickers=0,
                    start_date="2026-05-18",
                    end_date="2026-05-22",
                    user_agent="test",
                    timeout=1.0,
                )
            )
        finally:
            import_us_eod_yahoo_chart_script._fetch_chart = original_fetch_chart  # type: ignore[assignment]
            if original_psycopg is None:
                sys.modules.pop("psycopg", None)
            else:
                sys.modules["psycopg"] = original_psycopg

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["skipped_symbol_count"], 1)
        self.assertEqual(result["tickers"][0]["status"], "skipped_current")

    def test_daily_market_insight_binds_movers_to_chain_reports_and_evidence(self) -> None:
        class FakeInsightCursor:
            def __init__(self):
                self.rows = []

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return None

            def execute(self, sql, params=None):
                normalized = " ".join(sql.split()).lower()
                params = params or ()
                if "count(*) from ai_quant.records where collection = 'market_data'" in normalized:
                    self.rows = [(0,)]
                elif "order by as_of_date desc limit 1" in normalized and "market_data_bars" in normalized:
                    market = params[0]
                    self.rows = [("2026-05-22",)] if market in {"A", "U"} else [("",)]
                elif "from ( select * from ai_quant.market_data_bars" in normalized:
                    market = params[0]
                    source_id = params[1]
                    security_id = "sec_000001" if market == "A" else "security_nvda_us"
                    ticker = "000001" if market == "A" else "NVDA"
                    issuer_id = "issuer_000001" if market == "A" else "issuer_nvda"
                    issuer_name = "平安银行" if market == "A" else "NVIDIA"
                    self.rows = [
                        (
                            security_id,
                            market,
                            source_id,
                            "2026-05-22",
                            10.0,
                            11.0,
                            9.8,
                            11.0,
                            4000.0,
                            8000.0,
                            ticker,
                            issuer_id,
                            issuer_name,
                            "2026-05-21",
                            10.0,
                            1000.0,
                            2000.0,
                            1000.0,
                            2000.0,
                            20,
                        )
                    ]
                elif "collection = 'company_positions'" in normalized:
                    self.rows = [
                        (
                            "pos_000001",
                            {
                                "security_id": "sec_000001",
                                "chain_id": "chain_bank",
                                "node_ids": ["bank_node"],
                                "role": "零售银行",
                                "positioning_summary": "银行产业链核心服务节点",
                            },
                        ),
                        (
                            "pos_nvda",
                            {
                                "security_id": "security_nvda_us",
                                "chain_id": "chain_ai",
                                "node_ids": ["gpu_node"],
                                "role": "GPU 供应商",
                                "positioning_summary": "AI 算力核心节点",
                            },
                        ),
                    ]
                elif "collection = 'industry_chains'" in normalized:
                    self.rows = [
                        ("chain_bank", {"name": "银行产业链", "nodes": [{"node_id": "bank_node", "name": "银行服务"}]}),
                        ("chain_ai", {"name": "AI 算力产业链", "nodes": [{"node_id": "gpu_node", "name": "GPU"}]}),
                    ]
                elif "collection = 'research_reports'" in normalized and "payload->>'security_id'" in normalized:
                    security_id = params[0]
                    self.rows = [
                        (
                            f"rr_{security_id}",
                            {
                                "report_id": f"rr_{security_id}",
                                "title": f"{security_id} growth margin report",
                                "broker": "local",
                                "document_id": f"doc_{security_id}",
                                "indexed_at": "2026-05-22T00:00:00+00:00",
                            },
                        )
                    ]
                elif "collection = 'evidence'" in normalized:
                    self.rows = [
                        (
                            "evi_noise",
                            {
                                "evidence_id": "evi_noise",
                                "document_id": "doc_sec_000001",
                                "confidence": 0.95,
                                "canonical_text": "LLC Analyst +1(212)357 0000 a***@g***.com Goldman Sachs & Co.",
                            },
                        ),
                        (
                            "evi_1",
                            {
                                "evidence_id": "evi_1",
                                "document_id": "doc_sec_000001",
                                "confidence": 0.9,
                                "canonical_text": "收入增长和资产质量改善是当前研究观点的核心证据，管理层指引显示净息差压力缓和，风险加权资产扩张仍然可控。",
                            },
                        )
                    ]
                elif "collection = %s" in normalized:
                    self.rows = []
                else:
                    self.rows = []

            def fetchone(self):
                return self.rows[0] if self.rows else None

            def fetchall(self):
                return list(self.rows)

        class FakeInsightConnection:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return None

            def cursor(self):
                return FakeInsightCursor()

        original_connect = daily_market_insight_script._connect
        try:
            daily_market_insight_script._connect = lambda _dsn: FakeInsightConnection()  # type: ignore[assignment]
            result = daily_market_insight_script.build_daily_market_insight(
                dsn="postgresql://example.invalid/ai_quant",
                as_of_date="2026-05-24",
                source_a="public_eod_market_data",
                source_u="yahoo_chart_us_eod",
                data_type="eod",
                top_limit=4,
                current_row_limit=100,
                history_rows=20,
                recent_days=7,
                min_direct_evidence_companies=1,
            )
        finally:
            daily_market_insight_script._connect = original_connect  # type: ignore[assignment]

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["legacy_market_data_records"], 0)
        self.assertGreaterEqual(result["actionable_research_summary"]["abnormal_company_count"], 1)
        self.assertGreaterEqual(result["actionable_research_summary"]["evidence_bound_company_count"], 1)
        direct_evidence = [
            evidence
            for binding in result["evidence_bindings"]
            for evidence in binding.get("evidence", [])
        ]
        self.assertTrue(direct_evidence)
        self.assertTrue(all(evidence["quality"]["is_useful"] for evidence in direct_evidence))
        self.assertTrue(result["quality_gates"]["typed_only_market_data"])
        self.assertTrue(result["quality_gates"]["has_min_direct_report_evidence"])
        self.assertTrue(result["quality_gates"]["has_company_recent_activity"])
        self.assertGreaterEqual(result["actionable_research_summary"]["company_recent_activity_count"], 1)
        self.assertGreaterEqual(result["quality_gates"]["useful_evidence_sample_count"], 1)
        self.assertTrue(result["actionable_research_summary"]["headline"].startswith("直接研报证据优先:"))
        self.assertIn("A 市场首要异动", result["actionable_research_summary"]["abnormal_headline"])
        self.assertIn("直接研报证据优先", result["actionable_research_summary"]["direct_evidence_headline"])
        self.assertTrue(result["research_and_events"]["company_recent_activity"])
        self.assertIn("movers_by_market", result)

    def test_daily_market_insight_fails_when_direct_research_evidence_gate_is_not_met(self) -> None:
        class FakeInsightCursor:
            def __init__(self):
                self.rows = []

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return None

            def execute(self, sql, params=None):
                normalized = " ".join(sql.split()).lower()
                params = params or ()
                if "count(*) from ai_quant.records where collection = 'market_data'" in normalized:
                    self.rows = [(0,)]
                elif "order by as_of_date desc limit 1" in normalized and "market_data_bars" in normalized:
                    self.rows = [("2026-05-22",)]
                elif "from ( select * from ai_quant.market_data_bars" in normalized:
                    market = params[0]
                    self.rows = [
                        (
                            "sec_000001",
                            market,
                            params[1],
                            "2026-05-22",
                            10.0,
                            11.0,
                            9.8,
                            11.0,
                            4000.0,
                            8000.0,
                            "000001",
                            "issuer_000001",
                            "平安银行",
                            "2026-05-21",
                            10.0,
                            1000.0,
                            2000.0,
                            1000.0,
                            2000.0,
                            20,
                        )
                    ]
                elif "collection = 'company_positions'" in normalized:
                    self.rows = [
                        (
                            "pos_000001",
                            {
                                "security_id": "sec_000001",
                                "chain_id": "chain_bank",
                                "node_ids": ["bank_node"],
                                "role": "零售银行",
                            },
                        )
                    ]
                elif "collection = 'industry_chains'" in normalized:
                    self.rows = [("chain_bank", {"name": "银行产业链", "nodes": [{"node_id": "bank_node", "name": "银行服务"}]})]
                else:
                    self.rows = []

            def fetchone(self):
                return self.rows[0] if self.rows else None

            def fetchall(self):
                return list(self.rows)

        class FakeInsightConnection:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return None

            def cursor(self):
                return FakeInsightCursor()

        original_connect = daily_market_insight_script._connect
        try:
            daily_market_insight_script._connect = lambda _dsn: FakeInsightConnection()  # type: ignore[assignment]
            result = daily_market_insight_script.build_daily_market_insight(
                dsn="postgresql://example.invalid/ai_quant",
                as_of_date="2026-05-24",
                source_a="public_eod_market_data",
                source_u="yahoo_chart_us_eod",
                data_type="eod",
                top_limit=4,
                current_row_limit=100,
                history_rows=20,
                recent_days=7,
                min_direct_evidence_companies=1,
            )
        finally:
            daily_market_insight_script._connect = original_connect  # type: ignore[assignment]

        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["quality_gates"]["has_min_direct_report_evidence"])
        self.assertEqual(result["quality_gates"]["failures"][0]["check"], "direct_report_evidence")

    def test_daily_pipeline_runs_research_binding_before_insight_gate(self) -> None:
        commands = []

        def fake_run_command(name, command, *, timeout, allow_failure=False, artifact_path=None):
            commands.append((name, command, allow_failure))
            return {"name": name, "status": "passed", "returncode": 0}

        def fake_storage_audit(**_kwargs):
            return {"status": "passed", "passed": True, "failure_count": 0}

        def fake_insight(**kwargs):
            self.assertEqual(kwargs["min_direct_evidence_companies"], 2)
            return {
                "status": "passed",
                "passed": True,
                "quality_gates": {
                    "has_min_direct_report_evidence": True,
                    "direct_report_evidence_company_count": 2,
                    "failure_count": 0,
                    "failures": [],
                },
            }

        def fake_latency(*_args, **_kwargs):
            return {"status": "passed", "passed": True, "failure_count": 0}

        original_run = daily_data_update_pipeline_script._run_command
        original_dates = daily_data_update_pipeline_script._latest_db_dates
        original_storage = daily_data_update_pipeline_script.build_market_data_storage_audit
        original_tdx_coverage = daily_data_update_pipeline_script.build_tdx_coverage_report
        original_insight = daily_data_update_pipeline_script.build_daily_market_insight
        original_markdown = daily_data_update_pipeline_script.build_insight_markdown
        original_latency = daily_data_update_pipeline_script._latency_audit
        try:
            daily_data_update_pipeline_script._run_command = fake_run_command  # type: ignore[assignment]
            daily_data_update_pipeline_script._latest_db_dates = lambda _dsn: {"status": "passed", "sources": []}  # type: ignore[assignment]
            daily_data_update_pipeline_script.build_market_data_storage_audit = fake_storage_audit  # type: ignore[assignment]
            daily_data_update_pipeline_script.build_tdx_coverage_report = lambda _args: {"status": "passed", "ready_to_skip_import": True, "recommended_action": "skip_import"}  # type: ignore[assignment]
            daily_data_update_pipeline_script.build_daily_market_insight = fake_insight  # type: ignore[assignment]
            daily_data_update_pipeline_script.build_insight_markdown = lambda _payload: "# ok\n"  # type: ignore[assignment]
            daily_data_update_pipeline_script._latency_audit = fake_latency  # type: ignore[assignment]
            with TemporaryDirectory() as temp_dir:
                args = argparse.Namespace(
                    dsn="postgresql://example.invalid/ai_quant",
                    base_url="http://127.0.0.1:8000",
                    run_date="2026-05-24",
                    end_date="2026-05-22",
                    output_dir=temp_dir,
                    output=str(Path(temp_dir) / "daily.json"),
                    run_ashare_incremental=False,
                    run_ashare_scope_refresh=False,
                    skip_ashare=True,
                    skip_us=True,
                    tdx_incremental=False,
                    vipdoc_path="",
                    tdx_start_date="",
                    tdx_lookback_days=7,
                    tdx_batch_size=5000,
                    skip_tdx_coverage_audit=True,
                    fail_on_tdx_coverage_needs_import=False,
                    tdx_coverage_start_date="",
                    tdx_coverage_lookback_days=30,
                    tdx_coverage_max_symbols=0,
                    tdx_symbol_prefix="",
                    tdx_coverage_sample_limit=20,
                    tdx_coverage_statement_timeout_ms=120000,
                    tdx_coverage_strict_file_scan=False,
                    ashare_start_date="",
                    ashare_offset=0,
                    ashare_batch_size=100,
                    max_ashare_symbols=0,
                    us_tickers="AAPL,MSFT",
                    us_tickers_from_db=False,
                    us_ticker_filter="",
                    us_offset=0,
                    us_batch_size=100,
                    max_us_tickers=0,
                    us_start_date="",
                    us_lookback_days=7,
                    latest_symbols="600000",
                    sample_security_id="sec_000001",
                    sample_source_id="public_eod_market_data",
                    commit_every=200,
                    artifact_symbol_limit=500,
                    allow_import_failure=False,
                    skip_research_binding=False,
                    allow_research_binding_failure=False,
                    research_binding_dry_run=False,
                    research_binding_market="U",
                    research_binding_tickers="AAPL,MSFT",
                    research_binding_limit=100,
                    research_binding_max_matches_per_report=2,
                    research_binding_artifact_limit=10,
                    research_binding_timeout_seconds=99,
                    skip_latest_analysis=True,
                    allow_latest_analysis_failure=False,
                    latest_analysis_semantic_timeout_seconds=3.0,
                    skip_local_production_audit=True,
                    skip_project_completion_audit=True,
                    run_project_completion_audit=False,
                    latency_threshold_ms=5000.0,
                    api_timeout_seconds=1.0,
                    import_timeout_seconds=1,
                    scope_refresh_timeout_seconds=1,
                    analysis_timeout_seconds=1,
                    audit_timeout_seconds=1,
                    insight_top_limit=4,
                    insight_current_row_limit=100,
                    insight_history_rows=20,
                    insight_recent_days=7,
                    min_direct_evidence_companies=2,
                )
                result = daily_data_update_pipeline_script.run_daily_pipeline(args)
        finally:
            daily_data_update_pipeline_script._run_command = original_run  # type: ignore[assignment]
            daily_data_update_pipeline_script._latest_db_dates = original_dates  # type: ignore[assignment]
            daily_data_update_pipeline_script.build_market_data_storage_audit = original_storage  # type: ignore[assignment]
            daily_data_update_pipeline_script.build_tdx_coverage_report = original_tdx_coverage  # type: ignore[assignment]
            daily_data_update_pipeline_script.build_daily_market_insight = original_insight  # type: ignore[assignment]
            daily_data_update_pipeline_script.build_insight_markdown = original_markdown  # type: ignore[assignment]
            daily_data_update_pipeline_script._latency_audit = original_latency  # type: ignore[assignment]

        self.assertTrue(result["passed"])
        self.assertIn("research-report-asset-binding", result["artifacts"])
        self.assertIn("research_report_asset_binding", [name for name, _command, _allow_failure in commands])
        binding_command = next(command for name, command, _allow_failure in commands if name == "research_report_asset_binding")
        self.assertIn("--tickers", binding_command)
        self.assertIn("AAPL,MSFT", binding_command)

    def test_daily_pipeline_emits_operator_summary_and_artifact_manifest(self) -> None:
        def fake_run_command(name, command, *, timeout, allow_failure=False, artifact_path=None):
            return {"name": name, "status": "passed", "returncode": 0}

        db_snapshots = iter(
            [
                {
                    "status": "passed",
                    "sources": [
                        {"market": "A", "source_id": "public_eod_market_data", "rows": 100, "min_date": "2026-01-01", "max_date": "2026-05-22"},
                        {"market": "U", "source_id": "yahoo_chart_us_eod", "rows": 50, "min_date": "2026-01-01", "max_date": "2026-05-22"},
                    ],
                },
                {
                    "status": "passed",
                    "sources": [
                        {"market": "A", "source_id": "public_eod_market_data", "rows": 103, "min_date": "2026-01-01", "max_date": "2026-05-25"},
                        {"market": "U", "source_id": "yahoo_chart_us_eod", "rows": 52, "min_date": "2026-01-01", "max_date": "2026-05-22"},
                    ],
                },
            ]
        )

        def fake_storage_audit(**_kwargs):
            return {
                "status": "passed",
                "passed": True,
                "failure_count": 0,
                "legacy_market_data_records": 0,
                "typed_market_data_bars": {"estimated_count": 155, "max_date": "2026-05-25", "min_date": "2026-01-01"},
            }

        def fake_insight(**_kwargs):
            return {
                "status": "passed",
                "passed": True,
                "actionable_research_summary": {
                    "headline": "直接研报证据优先: A 600519 高端消费链",
                    "abnormal_headline": "A 市场首要异动: 600519 涨跌幅 3.10%",
                    "direct_report_evidence_company_count": 2,
                },
                "quality_gates": {
                    "has_min_direct_report_evidence": True,
                    "direct_report_evidence_company_count": 2,
                    "useful_evidence_sample_count": 5,
                    "failure_count": 0,
                    "failures": [],
                },
            }

        def fake_latency(*_args, **kwargs):
            payload = {
                "status": "passed",
                "passed": True,
                "failure_count": 0,
                "threshold_ms": 5000.0,
                "probes": [
                    {"name": "market_data_latest", "elapsed_ms": 18.0, "success": True},
                    {"name": "dashboard_ceo", "elapsed_ms": 123.0, "success": True},
                ],
            }
            output = kwargs.get("output")
            if output:
                Path(output).write_text(json.dumps(payload), encoding="utf-8")
            return payload

        original_run = daily_data_update_pipeline_script._run_command
        original_dates = daily_data_update_pipeline_script._latest_db_dates
        original_storage = daily_data_update_pipeline_script.build_market_data_storage_audit
        original_insight = daily_data_update_pipeline_script.build_daily_market_insight
        original_markdown = daily_data_update_pipeline_script.build_insight_markdown
        original_latency = daily_data_update_pipeline_script._latency_audit
        try:
            daily_data_update_pipeline_script._run_command = fake_run_command  # type: ignore[assignment]
            daily_data_update_pipeline_script._latest_db_dates = lambda _dsn: next(db_snapshots)  # type: ignore[assignment]
            daily_data_update_pipeline_script.build_market_data_storage_audit = fake_storage_audit  # type: ignore[assignment]
            daily_data_update_pipeline_script.build_daily_market_insight = fake_insight  # type: ignore[assignment]
            daily_data_update_pipeline_script.build_insight_markdown = lambda _payload: "# daily insight\n"  # type: ignore[assignment]
            daily_data_update_pipeline_script._latency_audit = fake_latency  # type: ignore[assignment]
            with TemporaryDirectory() as temp_dir:
                args = argparse.Namespace(
                    dsn="postgresql://example.invalid/ai_quant",
                    base_url="http://127.0.0.1:8000",
                    run_date="2026-05-25",
                    end_date="2026-05-25",
                    output_dir=temp_dir,
                    output=str(Path(temp_dir) / "daily.json"),
                    run_ashare_incremental=False,
                    run_ashare_scope_refresh=False,
                    skip_ashare=True,
                    skip_us=True,
                    tdx_incremental=False,
                    vipdoc_path="",
                    tdx_start_date="",
                    tdx_lookback_days=7,
                    tdx_batch_size=5000,
                    skip_tdx_coverage_audit=True,
                    fail_on_tdx_coverage_needs_import=False,
                    tdx_coverage_start_date="",
                    tdx_coverage_lookback_days=30,
                    tdx_coverage_max_symbols=0,
                    tdx_symbol_prefix="",
                    tdx_coverage_sample_limit=20,
                    tdx_coverage_statement_timeout_ms=120000,
                    tdx_coverage_strict_file_scan=False,
                    ashare_start_date="",
                    ashare_offset=0,
                    ashare_batch_size=100,
                    max_ashare_symbols=0,
                    us_tickers="AAPL,MSFT",
                    us_tickers_from_db=False,
                    us_ticker_filter="",
                    us_offset=0,
                    us_batch_size=100,
                    max_us_tickers=0,
                    us_start_date="",
                    us_lookback_days=7,
                    latest_symbols="600000",
                    sample_security_id="sec_000001",
                    sample_source_id="public_eod_market_data",
                    commit_every=200,
                    artifact_symbol_limit=500,
                    allow_import_failure=False,
                    skip_research_binding=True,
                    allow_research_binding_failure=False,
                    research_binding_dry_run=False,
                    research_binding_market="",
                    research_binding_tickers="AAPL,MSFT",
                    research_binding_limit=100,
                    research_binding_max_matches_per_report=2,
                    research_binding_artifact_limit=10,
                    research_binding_timeout_seconds=99,
                    skip_latest_analysis=True,
                    allow_latest_analysis_failure=False,
                    latest_analysis_semantic_timeout_seconds=2.5,
                    skip_local_production_audit=True,
                    skip_project_completion_audit=True,
                    run_project_completion_audit=False,
                    latency_threshold_ms=5000.0,
                    api_timeout_seconds=1.0,
                    import_timeout_seconds=1,
                    scope_refresh_timeout_seconds=1,
                    analysis_timeout_seconds=1,
                    audit_timeout_seconds=1,
                    insight_top_limit=4,
                    insight_current_row_limit=100,
                    insight_history_rows=20,
                    insight_recent_days=7,
                    min_direct_evidence_companies=1,
                )
                result = daily_data_update_pipeline_script.run_daily_pipeline(args)
        finally:
            daily_data_update_pipeline_script._run_command = original_run  # type: ignore[assignment]
            daily_data_update_pipeline_script._latest_db_dates = original_dates  # type: ignore[assignment]
            daily_data_update_pipeline_script.build_market_data_storage_audit = original_storage  # type: ignore[assignment]
            daily_data_update_pipeline_script.build_daily_market_insight = original_insight  # type: ignore[assignment]
            daily_data_update_pipeline_script.build_insight_markdown = original_markdown  # type: ignore[assignment]
            daily_data_update_pipeline_script._latency_audit = original_latency  # type: ignore[assignment]

        self.assertTrue(result["passed"])
        self.assertEqual(result["summary"]["market_data"]["latest_by_market"]["A"], "2026-05-25")
        self.assertTrue(result["summary"]["market_data"]["typed_storage_only"])
        self.assertEqual(result["summary"]["market_data"]["typed_table_rows_estimate"], 155)
        a_delta = next(item for item in result["summary"]["market_data"]["source_deltas"] if item["market"] == "A")
        self.assertEqual(a_delta["row_delta"], 3)
        self.assertEqual(result["summary"]["actionable_insight"]["direct_report_evidence_company_count"], 2)
        self.assertEqual(result["summary"]["latency"]["slowest_probe"], "dashboard_ceo")
        self.assertIn("artifact_manifest", result)
        manifest_names = {item["name"] for item in result["artifact_manifest"]["artifacts"]}
        self.assertIn("market-data-storage-audit", manifest_names)
        self.assertIn("daily-insight-json", manifest_names)
        self.assertTrue(result["operator_next_actions"][0].startswith("No blocking action required"))

    def test_daily_pipeline_command_timeout_writes_failure_artifact(self) -> None:
        original_run = daily_data_update_pipeline_script.subprocess.run
        try:
            def fake_run(*_args, **_kwargs):
                raise daily_data_update_pipeline_script.subprocess.TimeoutExpired(cmd=["python"], timeout=3, output="partial out", stderr="partial err")

            daily_data_update_pipeline_script.subprocess.run = fake_run  # type: ignore[assignment]
            with TemporaryDirectory() as temp_dir:
                output = Path(temp_dir) / "scope.json"
                result = daily_data_update_pipeline_script._run_command(  # type: ignore[attr-defined]
                    "ashare_current_universe_scope",
                    ["python", "scripts/scope_ashare_current_baostock_universe.py", "--output", str(output)],
                    timeout=3,
                    allow_failure=True,
                )
                artifact = json.loads(output.read_text(encoding="utf-8"))
        finally:
            daily_data_update_pipeline_script.subprocess.run = original_run  # type: ignore[assignment]

        self.assertEqual(result["status"], "allowed_failure")
        self.assertEqual(result["error_type"], "TimeoutExpired")
        self.assertEqual(artifact["status"], "allowed_failure")
        self.assertFalse(artifact["passed"])
        self.assertEqual(artifact["step"], "ashare_current_universe_scope")
        self.assertEqual(artifact["timeout_seconds"], 3)

    def test_daily_pipeline_operator_actions_include_allowed_failures(self) -> None:
        summary = {
            "market_data": {"typed_storage_only": True},
            "actionable_insight": {"status": "passed"},
            "latency": {"status": "passed"},
            "nonblocking_issues": [
                {
                    "name": "ashare_current_universe_scope",
                    "status": "allowed_failure",
                    "artifact": "artifacts/scope.json",
                    "error": "command timed out after 300 seconds",
                }
            ],
        }

        actions = daily_data_update_pipeline_script._operator_next_actions(summary, {"daily-insight-md": "artifacts/insight.md"}, [])  # type: ignore[attr-defined]

        self.assertIn("Review non-blocking step ashare_current_universe_scope", actions[0])
        self.assertIn("artifacts/scope.json", actions[0])

    def test_daily_pipeline_passes_bounded_semantic_timeout_to_latest_analysis(self) -> None:
        commands = []

        def fake_run_command(name, command, *, timeout, allow_failure=False, artifact_path=None):
            commands.append((name, command, allow_failure))
            return {"name": name, "status": "passed", "returncode": 0}

        original_run = daily_data_update_pipeline_script._run_command
        original_dates = daily_data_update_pipeline_script._latest_db_dates
        original_storage = daily_data_update_pipeline_script.build_market_data_storage_audit
        original_tdx_coverage = daily_data_update_pipeline_script.build_tdx_coverage_report
        original_insight = daily_data_update_pipeline_script.build_daily_market_insight
        original_markdown = daily_data_update_pipeline_script.build_insight_markdown
        original_latency = daily_data_update_pipeline_script._latency_audit
        try:
            daily_data_update_pipeline_script._run_command = fake_run_command  # type: ignore[assignment]
            daily_data_update_pipeline_script._latest_db_dates = lambda _dsn: {"status": "passed", "sources": []}  # type: ignore[assignment]
            daily_data_update_pipeline_script.build_market_data_storage_audit = lambda **_kwargs: {"status": "passed", "passed": True, "failure_count": 0}  # type: ignore[assignment]
            daily_data_update_pipeline_script.build_tdx_coverage_report = lambda _args: {"status": "passed", "ready_to_skip_import": True, "recommended_action": "skip_import"}  # type: ignore[assignment]
            daily_data_update_pipeline_script.build_daily_market_insight = lambda **_kwargs: {"status": "passed", "passed": True, "quality_gates": {"failure_count": 0, "failures": []}}  # type: ignore[assignment]
            daily_data_update_pipeline_script.build_insight_markdown = lambda _payload: "# ok\n"  # type: ignore[assignment]
            daily_data_update_pipeline_script._latency_audit = lambda *_args, **_kwargs: {"status": "passed", "passed": True, "failure_count": 0}  # type: ignore[assignment]
            with TemporaryDirectory() as temp_dir:
                args = argparse.Namespace(
                    dsn="postgresql://example.invalid/ai_quant",
                    base_url="http://127.0.0.1:8000",
                    run_date="2026-05-24",
                    end_date="2026-05-22",
                    output_dir=temp_dir,
                    output=str(Path(temp_dir) / "daily.json"),
                    run_ashare_incremental=False,
                    run_ashare_scope_refresh=False,
                    skip_ashare=True,
                    skip_us=True,
                    tdx_incremental=False,
                    vipdoc_path="",
                    tdx_start_date="",
                    tdx_lookback_days=7,
                    tdx_batch_size=5000,
                    skip_tdx_coverage_audit=True,
                    fail_on_tdx_coverage_needs_import=False,
                    tdx_coverage_start_date="",
                    tdx_coverage_lookback_days=30,
                    tdx_coverage_max_symbols=0,
                    tdx_symbol_prefix="",
                    tdx_coverage_sample_limit=20,
                    tdx_coverage_statement_timeout_ms=120000,
                    tdx_coverage_strict_file_scan=False,
                    ashare_start_date="",
                    ashare_offset=0,
                    ashare_batch_size=100,
                    max_ashare_symbols=0,
                    us_tickers="AAPL,MSFT",
                    us_tickers_from_db=False,
                    us_ticker_filter="",
                    us_offset=0,
                    us_batch_size=100,
                    max_us_tickers=0,
                    us_start_date="",
                    us_lookback_days=7,
                    latest_symbols="600000",
                    sample_security_id="sec_000001",
                    sample_source_id="public_eod_market_data",
                    commit_every=200,
                    artifact_symbol_limit=500,
                    allow_import_failure=False,
                    skip_research_binding=True,
                    allow_research_binding_failure=False,
                    research_binding_dry_run=False,
                    research_binding_market="U",
                    research_binding_tickers="AAPL,MSFT",
                    research_binding_limit=100,
                    research_binding_max_matches_per_report=2,
                    research_binding_artifact_limit=10,
                    research_binding_timeout_seconds=99,
                    skip_latest_analysis=False,
                    allow_latest_analysis_failure=False,
                    latest_analysis_semantic_timeout_seconds=2.5,
                    skip_local_production_audit=True,
                    skip_project_completion_audit=True,
                    run_project_completion_audit=False,
                    latency_threshold_ms=5000.0,
                    api_timeout_seconds=1.0,
                    import_timeout_seconds=1,
                    scope_refresh_timeout_seconds=1,
                    analysis_timeout_seconds=1,
                    audit_timeout_seconds=1,
                    insight_top_limit=4,
                    insight_current_row_limit=100,
                    insight_history_rows=20,
                    insight_recent_days=7,
                    min_direct_evidence_companies=1,
                )
                result = daily_data_update_pipeline_script.run_daily_pipeline(args)
        finally:
            daily_data_update_pipeline_script._run_command = original_run  # type: ignore[assignment]
            daily_data_update_pipeline_script._latest_db_dates = original_dates  # type: ignore[assignment]
            daily_data_update_pipeline_script.build_market_data_storage_audit = original_storage  # type: ignore[assignment]
            daily_data_update_pipeline_script.build_tdx_coverage_report = original_tdx_coverage  # type: ignore[assignment]
            daily_data_update_pipeline_script.build_daily_market_insight = original_insight  # type: ignore[assignment]
            daily_data_update_pipeline_script.build_insight_markdown = original_markdown  # type: ignore[assignment]
            daily_data_update_pipeline_script._latency_audit = original_latency  # type: ignore[assignment]

        self.assertTrue(result["passed"])
        latest_command = next(command for name, command, _allow_failure in commands if name == "latest_analysis")
        self.assertIn("--semantic-timeout-seconds", latest_command)
        self.assertEqual(latest_command[latest_command.index("--semantic-timeout-seconds") + 1], "2.5")

    def test_daily_pipeline_market_end_dates_wait_for_market_ready_windows(self) -> None:
        base_args = argparse.Namespace(
            end_date="",
            run_date="2026-05-25",
            ashare_eod_ready_hour_cst=18,
            ashare_eod_ready_minute_cst=0,
            us_eod_ready_hour_ny=18,
            us_eod_ready_minute_ny=0,
        )
        morning = daily_data_update_pipeline_script._effective_market_end_dates(
            base_args,
            now=daily_data_update_pipeline_script.datetime.fromisoformat("2026-05-25T03:35:00+00:00"),
        )
        self.assertEqual(morning["effective_end_dates"]["A"], "2026-05-22")
        self.assertEqual(morning["effective_end_dates"]["TDX"], "2026-05-22")
        self.assertEqual(morning["effective_end_dates"]["U"], "2026-05-22")
        evening = daily_data_update_pipeline_script._effective_market_end_dates(
            base_args,
            now=daily_data_update_pipeline_script.datetime.fromisoformat("2026-05-25T10:45:00+00:00"),
        )
        self.assertEqual(evening["effective_end_dates"]["A"], "2026-05-25")
        self.assertEqual(evening["effective_end_dates"]["TDX"], "2026-05-25")
        self.assertEqual(evening["effective_end_dates"]["U"], "2026-05-22")
        forced_args = argparse.Namespace(**{**vars(base_args), "end_date": "2026-05-25"})
        forced = daily_data_update_pipeline_script._effective_market_end_dates(
            forced_args,
            now=daily_data_update_pipeline_script.datetime.fromisoformat("2026-05-25T03:35:00+00:00"),
        )
        self.assertEqual(forced["effective_end_dates"], {"A": "2026-05-25", "TDX": "2026-05-25", "U": "2026-05-25"})

    def test_daily_update_systemd_audit_requires_scheduler_and_latest_pipeline(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            scripts_dir = root / "scripts"
            scripts_dir.mkdir()
            runner = scripts_dir / "run_daily_data_update.sh"
            runner.write_text("#!/usr/bin/env bash\npython scripts/daily_data_update_pipeline.py\n", encoding="utf-8")
            runner.chmod(0o755)

            unit_dir = root / "systemd-user"
            unit_dir.mkdir()
            (unit_dir / "ai-quant-daily-update.service").write_text(
                "\n".join(
                    [
                        "[Service]",
                        "WorkingDirectory=/tmp/ai-quant",
                        "Environment=AI_QUANT_DAILY_RUNNER=compose",
                        "Environment=AI_QUANT_DAILY_OUTPUT_BASE=artifacts/daily-update-local",
                        "Environment=AI_QUANT_DAILY_RUN_ASHARE_SCOPE_REFRESH=true",
                        "Environment=AI_QUANT_DAILY_RUN_ASHARE_INCREMENTAL=true",
                        "Environment=AI_QUANT_DAILY_RUN_US_SCOPE_REFRESH=true",
                        "Environment=AI_QUANT_DAILY_US_TICKERS_FROM_DB=true",
                        "Environment=AI_QUANT_DAILY_TDX_INCREMENTAL=false",
                        "ExecStart=/usr/bin/env bash /tmp/ai-quant/scripts/run_daily_data_update.sh",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (unit_dir / "ai-quant-daily-update.timer").write_text(
                "\n".join(
                    [
                        "[Timer]",
                        "OnCalendar=Mon..Fri *-*-* 07:00:00",
                        "OnCalendar=Mon..Fri *-*-* 18:30:00",
                        "Persistent=true",
                        "Unit=ai-quant-daily-update.service",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            run_dir = root / "artifacts" / "daily-update-local" / "runs" / "2026-05-25-183000"
            run_dir.mkdir(parents=True)
            (run_dir / "daily-update-2026-05-25.json").write_text(
                json.dumps(
                    {
                        "status": "passed",
                        "summary": {
                            "market_data": {
                                "typed_storage_only": True,
                                "latest_by_market": {"A": "2026-05-25", "U": "2026-05-22"},
                                "typed_table_rows_estimate": 28352527,
                            },
                            "actionable_insight": {
                                "status": "passed",
                                "headline": "直接研报证据优先: ok",
                                "direct_report_evidence_company_count": 1,
                            },
                            "latency": {"status": "passed", "slowest_probe": "dashboard_ceo"},
                        },
                        "artifact_manifest": {"artifact_count": 2, "artifacts": []},
                        "operator_next_actions": ["No blocking action required."],
                        "artifacts": {
                            "latest_analysis": str(run_dir / "latest-analysis-2026-05-25" / "latest-analysis.json"),
                            "daily-insight-json": str(run_dir / "daily-insight-json-2026-05-25.json"),
                        },
                        "steps": [
                            {"name": "market_data_storage_audit", "status": "passed"},
                            {"name": "daily_market_insight", "status": "passed"},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            latest_dir = run_dir / "latest-analysis-2026-05-25"
            latest_dir.mkdir()
            (latest_dir / "latest-analysis.json").write_text(json.dumps({"status": "passed", "analysis": {"latest_market_date": "2026-05-25"}}), encoding="utf-8")
            (run_dir / "daily-insight-json-2026-05-25.json").write_text(json.dumps({"status": "passed", "actionable_research_summary": {"headline": "ok"}}), encoding="utf-8")

            audit = audit_daily_update_schedule_script.build_daily_update_schedule_audit(
                repo_root=root,
                unit_dir=unit_dir,
                output_dir="artifacts/daily-update-local",
                check_systemd=False,
                require_enabled=False,
                require_latest_run=True,
            )

        self.assertTrue(audit["passed"])
        self.assertEqual(audit["failure_count"], 0)
        gates = {item["check"]: item["passed"] for item in audit["gates"]}
        self.assertTrue(gates["service_uses_compose_runner"])
        self.assertTrue(gates["service_uses_user_writable_output_base"])
        self.assertTrue(gates["service_runs_ashare_scope_refresh"])
        self.assertTrue(gates["service_runs_ashare_batches"])
        self.assertTrue(gates["service_runs_us_scope_refresh"])
        self.assertTrue(gates["service_runs_us_batches_from_db"])
        self.assertTrue(gates["service_keeps_tdx_import_optional"])
        self.assertTrue(gates["timer_has_morning_and_evening_runs"])
        self.assertTrue(gates["latest_pipeline_storage_audit"])
        self.assertTrue(gates["latest_pipeline_daily_insight"])
        self.assertTrue(gates["latest_pipeline_operator_summary"])
        self.assertTrue(gates["latest_pipeline_artifact_manifest"])
        self.assertTrue(gates["latest_pipeline_typed_storage_summary"])
        self.assertTrue(gates["latest_pipeline_actionable_insight_summary"])
        self.assertTrue(gates["latest_analysis_artifact_shape"])
        self.assertTrue(gates["daily_insight_artifact_shape"])
        self.assertEqual(audit["latest_pipeline_summary"]["latest_by_market"]["A"], "2026-05-25")
        self.assertEqual(audit["latest_pipeline_summary"]["slowest_probe"], "dashboard_ceo")

    def test_daily_update_runner_records_skipped_current_batches(self) -> None:
        runner = Path("scripts/run_daily_data_update.sh").read_text(encoding="utf-8")
        for fragment in [
            "ashare_typed_rows = int(ashare.get(\"typed_bar_rows\")",
            "ashare_queried_count = int(ashare.get(\"queried_symbol_count\")",
            "\"last_ashare_typed_bar_rows\": ashare_typed_rows",
            "\"last_ashare_queried_symbol_count\": ashare_queried_count",
            "us_typed_rows = int(us.get(\"typed_bar_rows\")",
            "\"last_us_typed_bar_rows\": us_typed_rows",
        ]:
            self.assertIn(fragment, runner)

    def test_latest_analysis_research_evidence_uses_bounded_semantic_timeout(self) -> None:
        calls = []

        class FakeClient:
            def request(self, method, path, body=None, **kwargs):
                calls.append({"method": method, "path": path, "body": body or {}, "timeout": kwargs.get("timeout")})
                if path == "/api/search/semantic":
                    return {"_error": {"type": "TimeoutError"}, "results": []}
                if path == "/api/hotspots/expand":
                    return {"retrieval_recall": {"research_opinions": []}}
                raise AssertionError(path)

        result = latest_analysis_run_script._research_evidence_audit(  # type: ignore[attr-defined]
            FakeClient(),
            {"research_reports": 3, "evidence": 4},
            assets=[{"label": "AAPL", "symbol": "AAPL", "security_id": "security_aapl_us"}],
            semantic_timeout_seconds=2.5,
        )

        semantic_calls = [item for item in calls if item["path"] == "/api/search/semantic"]
        self.assertGreaterEqual(len(semantic_calls), 1)
        self.assertTrue(all(item["timeout"] == 2.5 for item in semantic_calls))
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["semantic_recall"]["status"], "needs_review")

    def test_production_runbook_documents_daily_update_typed_only_scheduler(self) -> None:
        runbook = Path("docs/production-runbook.md").read_text(encoding="utf-8")
        for fragment in [
            "scripts/install_daily_update_systemd_user.sh",
            "scripts/run_daily_data_update.sh",
            "scripts/audit_daily_update_schedule.py",
            "ai-quant-daily-update.timer",
            "工作日 07:00 和 18:30",
            "America/New_York 18:00",
            "artifacts/daily-update-local",
            "ai_quant.market_data_bars",
            "records(collection='market_data')",
            "不会 JSON/数据库双写",
            "AI_QUANT_DAILY_US_TICKERS_FROM_DB=true",
            "AI_QUANT_DAILY_RUN_US_SCOPE_REFRESH=true",
            "AI_QUANT_STACK_REBUILD=true",
            "AI_QUANT_DAILY_TDX_INCREMENTAL=true",
            "AI_QUANT_DAILY_LATEST_ANALYSIS_SEMANTIC_TIMEOUT_SECONDS",
        ]:
            self.assertIn(fragment, runbook)
        compose = Path("docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn("./scripts:/app/scripts:ro", compose)
        staging = Path("scripts/local_staging_stack.sh").read_text(encoding="utf-8")
        self.assertIn("AI_QUANT_STACK_REBUILD", staging)
        self.assertIn("up -d", staging)
        ui = Path("app/static/index.html").read_text(encoding="utf-8")
        self.assertIn("daily_insight", ui)
        self.assertIn("direct_report_watch_items", ui)
        self.assertIn("companyRecentActivityRows", ui)
        self.assertIn("typed-only K线", ui)

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
        self.assertEqual(result["nav_labels"], 8)
        self.assertEqual(result["status_labels"], len(REQUIRED_STATUS_LABELS))
        self.assertEqual(result["required_ids"], len(REQUIRED_IDS))
        self.assertEqual(result["required_functions"], len(REQUIRED_JS_FUNCTIONS))
        self.assertEqual(result["node_check"], "skipped")

    def test_server_import_does_not_auto_load_dotenv(self) -> None:
        import app.server as server_module

        dotenv_path = Path(".env")
        original_content = dotenv_path.read_text(encoding="utf-8") if dotenv_path.exists() else None
        marker_key = f"AI_QUANT_DOTENV_IMPORT_ISOLATION_{int(time.time() * 1000)}"
        marker_value = "from_dotenv_only_when_explicit"
        os.environ.pop(marker_key, None)
        self.addCleanup(lambda: os.environ.pop(marker_key, None))
        try:
            content = (original_content + "\n" if original_content else "") + f"{marker_key}={marker_value}\n"
            dotenv_path.write_text(content, encoding="utf-8")
            reloaded = importlib.reload(server_module)
            self.assertNotIn(marker_key, os.environ)
            reloaded._load_dotenv(dotenv_path)
            self.assertEqual(os.environ.get(marker_key), marker_value)
        finally:
            if original_content is None:
                dotenv_path.unlink(missing_ok=True)
            else:
                dotenv_path.write_text(original_content, encoding="utf-8")

    def test_non_local_deployment_mode_rejects_header_only_auth(self) -> None:
        import app.server as server_module

        original_router = server_module.ROUTER
        server_module.ROUTER = None
        os.environ["AI_QUANT_DEPLOYMENT_MODE"] = "production"
        os.environ["AI_QUANT_AUTH_MODE"] = "x-role-header"
        try:
            with self.assertRaises(RuntimeError):
                server_module.get_router()
        finally:
            server_module.ROUTER = original_router

    def test_gateway_and_parser_tolerate_empty_string_env_values(self) -> None:
        os.environ["AI_QUANT_LLM_TIMEOUT_SECONDS"] = ""
        os.environ["AI_QUANT_PADDLEOCR_TIMEOUT_SECONDS"] = ""
        os.environ["AI_QUANT_PADDLEOCR_POLL_INTERVAL_SECONDS"] = ""
        os.environ["AI_QUANT_PADDLEOCR_MAX_POLLS"] = ""
        gateway = LLMGateway(api_key="token")
        parser = PaddleOCRParser(token="")
        self.assertEqual(gateway.timeout, 120)
        self.assertEqual(parser.timeout, 60)
        self.assertEqual(parser.poll_interval, 5.0)
        self.assertEqual(parser.max_polls, 120)

    def test_ui_cross_browser_matrix_validator_requires_families_viewports_and_text(self) -> None:
        invalid = validate_cross_browser_matrix(
            {
                "browser_matrix": [{"browser": "chromium", "viewport": "desktop", "status": "passed"}],
                "required_text": ["公司情报与市场综合分析平台"],
                "missing_text": [],
                "failure_count": 0,
            }
        )
        self.assertFalse(invalid["passed"])
        failure_checks = {item["check"] for item in invalid["failures"]}
        self.assertIn("browser_family_count", failure_checks)
        self.assertIn("required_viewports", failure_checks)

        valid = validate_cross_browser_matrix(
            {
                "browser_matrix": [
                    {"browser": "chromium", "viewport": "desktop", "status": "passed"},
                    {"browser": "firefox", "viewport": "mobile", "status": "passed"},
                ],
                "required_text": ["公司情报与市场综合分析平台", "总览"],
                "missing_text": [],
                "failure_count": 0,
            }
        )
        self.assertTrue(valid["passed"])
        self.assertEqual(valid["browser_families"], ["chromium", "firefox"])
        self.assertEqual(valid["missing_viewports"], [])

    def test_readiness_evidence_package_validator_requires_ready_external_artifacts(self) -> None:
        self.assertTrue(is_external_artifact_uri("artifact://staging-local/real-data-smoke.json"))
        self.assertFalse(is_production_artifact_uri("artifact://staging-local/real-data-smoke.json"))
        invalid = validate_readiness_evidence_package(
            {
                "package_id": "pkg_invalid",
                "status": "ready",
                "ready_for_launch": True,
                "missing_evidence_count": 0,
                "failed_gate_count": 0,
                "checklist_coverage": 1.0,
                "pending_checklist": [],
                "required_evidence": [
                    {
                        "check_id": "real_data_smoke_test",
                        "status": "passed",
                        "missing_evidence": False,
                        "evidence_uri": "artifact://staging-local/real-data-smoke.json",
                    },
                    {
                        "check_id": "capacity_latency_report",
                        "status": "passed",
                        "missing_evidence": False,
                        "evidence_uri": "s3://ai-quant-prod",
                    }
                ],
                "external_validations": [
                    {
                        "scope": "state_store_object_store_fulltext_search",
                        "check_status": "passed",
                        "ready": True,
                        "evidence_uri": "https://storage.example.test",
                    }
                ],
            }
        )
        self.assertFalse(invalid["passed"])
        self.assertEqual(invalid["failure_count"], len(invalid["failures"]))
        failure_checks = {item["check"] for item in invalid["failures"]}
        self.assertIn("required_evidence_uri", failure_checks)
        self.assertIn("required_evidence_check_ids", failure_checks)
        self.assertIn("external_validation_scopes", failure_checks)
        self.assertIn("external_validation_evidence_uri", failure_checks)

        valid_scopes = [
            "state_store_object_store_fulltext_search",
            "metrics_logs_traces",
            "graph_vector_semantic_search",
            "lineage_model_registry",
            "kms_rotation_cache_retention_external_delete",
            "desktop_mobile_cross_browser",
        ]
        valid_check_ids = [
            "real_data_smoke_test",
            "production_ui_screenshot_acceptance",
            "cross_browser_acceptance",
            "capacity_latency_report",
            "backup_restore_drill",
            "otel_collector_drill",
            "permission_red_team_test",
            "compliance_review_record",
            "launch_checklist",
        ]
        valid = validate_readiness_evidence_package(
            {
                "package_id": "pkg_ready",
                "status": "ready",
                "ready_for_launch": True,
                "missing_evidence_count": 0,
                "failed_gate_count": 0,
                "checklist_coverage": 1.0,
                "pending_checklist": [],
                "required_evidence": [
                    {
                        "check_id": check_id,
                        "status": "passed",
                        "missing_evidence": False,
                        "evidence_uri": f"s3://ai-quant-prod/readiness/{check_id}.json",
                    }
                    for check_id in valid_check_ids
                ],
                "external_validations": [
                    {
                        "scope": scope,
                        "check_status": "passed",
                        "ready": True,
                        "outbox_channels_ready": True,
                        "evidence_uri": f"artifact://prod-readiness/{scope}.json",
                    }
                    for scope in valid_scopes
                ],
            }
        )
        self.assertTrue(valid["passed"])
        self.assertEqual(valid["failure_count"], 0)
        self.assertEqual(valid["missing_scopes"], [])

        template = validate_readiness_evidence_package(
            json.loads(Path("artifacts/readiness-evidence-package.example.json").read_text(encoding="utf-8"))
        )
        self.assertTrue(template["passed"], template["failures"])
        self.assertEqual(template["failure_count"], 0)
        self.assertEqual(template["required_evidence_count"], 9)
        self.assertEqual(template["external_validation_count"], 6)
        with TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "readiness-evidence-package-validation.json"
            subprocess.run(
                [
                    sys.executable,
                    "scripts/readiness_evidence_package_check.py",
                    "artifacts/readiness-evidence-package.example.json",
                    "--output",
                    str(output_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertTrue(output_path.exists())
            self.assertFalse((output_path.parent / f".{output_path.name}.tmp").exists())
            self.assertTrue(json.loads(output_path.read_text(encoding="utf-8"))["passed"])
            self.assertEqual(json.loads(output_path.read_text(encoding="utf-8"))["failure_count"], 0)

    def test_production_closure_manifest_freezes_sources_and_external_evidence(self) -> None:
        base_checks = {
            check_id: {"status": "passed", "evidence_uri": f"s3://ai-quant-prod/readiness/{check_id}.json"}
            for check_id in [
                "real_data_smoke_test",
                "production_ui_screenshot_acceptance",
                "cross_browser_acceptance",
                "capacity_latency_report",
                "backup_restore_drill",
                "otel_collector_drill",
                "permission_red_team_test",
                "compliance_review_record",
                "launch_checklist",
            ]
        }
        astock_connector_ids = [
            "eastmoney_research",
            "cninfo_announcements",
            "tencent_valuation_snapshot",
            "ths_hot_topics",
            "baidu_concepts",
            "dragon_tiger_list",
            "unlock_calendar",
        ]
        astock_artifacts = {
            connector_id: {
                "endpoint_artifact_uri": f"s3://ai-quant-prod/reports/astock/{connector_id}-endpoint.json",
                "stability_artifact_uri": f"s3://ai-quant-prod/reports/astock/{connector_id}-stability.json",
                "rate_limit_artifact_uri": f"s3://ai-quant-prod/reports/astock/{connector_id}-rate-limit.json",
                "license_review_uri": f"s3://ai-quant-prod/reports/astock/{connector_id}-license.json",
                "field_sample_uri": f"s3://ai-quant-prod/reports/astock/{connector_id}-sample.jsonl",
            }
            for connector_id in astock_connector_ids
        }
        astock_manifest = {
            "connector_ids": astock_connector_ids,
            "verify": [{"connector_id": connector_id, "status": "passed"} for connector_id in astock_connector_ids],
            "verification_readiness": {
                "connector_ids": astock_connector_ids,
                "artifact_uris": astock_artifacts,
            },
        }
        reports = {
            name: {"artifact_uris": {f"{name}_uri": f"s3://ai-quant-prod/reports/{name}.json"}}
            for name in ["storage", "security", "observability", "ui", "deployment"]
        }
        evidence_package = {
            "status": "ready",
            "ready_for_launch": True,
            "missing_evidence_count": 0,
            "failed_gate_count": 0,
            "checklist_coverage": 1.0,
            "pending_checklist": [],
            "required_evidence": [
                {
                    "check_id": check_id,
                    "status": "passed",
                    "missing_evidence": False,
                    "evidence_uri": f"s3://ai-quant-prod/readiness/{check_id}.json",
                }
                for check_id in base_checks
            ],
            "external_validations": [
                {
                    "scope": scope,
                    "check_status": "passed",
                    "ready": True,
                    "outbox_channels_ready": True,
                    "evidence_uri": f"s3://ai-quant-prod/validations/{scope}.json",
                }
                for scope in [
                    "state_store_object_store_fulltext_search",
                    "metrics_logs_traces",
                    "graph_vector_semantic_search",
                    "lineage_model_registry",
                    "kms_rotation_cache_retention_external_delete",
                    "desktop_mobile_cross_browser",
                ]
            ],
        }
        invalid = validate_production_closure_manifest(
            {
                "ready_for_launch": True,
                "readiness_checks": {
                    **base_checks,
                    "capacity_latency_report": {"status": "passed", "evidence_uri": "artifact://staging-local/capacity.json"},
                },
                "reports": reports,
                "data_sources": [
                    {"source_id": "paid_terminal", "source_class": "paid_terminal", "requires_paid_license": True}
                ],
                "astock_connectors": {"connector_ids": ["eastmoney_research", "iwencai_optional"]},
                "evidence_package": evidence_package,
            }
        )
        self.assertFalse(invalid["passed"])
        failure_checks = {item["check"] for item in invalid["failures"]}
        self.assertIn("readiness_check_evidence_uri", failure_checks)
        self.assertIn("data_source_class", failure_checks)
        self.assertIn("paid_data_source", failure_checks)
        self.assertIn("astock_connector_scope", failure_checks)
        self.assertIn("astock_connector_verification", failure_checks)
        self.assertIn("astock_connector_readiness_scope", failure_checks)
        self.assertIn("astock_connector_artifact_fields", failure_checks)
        self.assertIn("astock_connector_artifact_uri", failure_checks)

        valid = validate_production_closure_manifest(
            {
                "ready_for_launch": True,
                "readiness_checks": base_checks,
                "reports": reports,
                "data_sources": [
                    {
                        "source_id": "sec_edgar",
                        "source_class": "official_public_disclosure",
                        "rights_tag": {
                            "license_class": "public",
                            "training_allowed": False,
                            "redistribution_allowed": False,
                            "display_use": "allowed",
                            "non_display_use": "restricted",
                            "derived_data_use": "restricted",
                        },
                        "field_whitelist": ["filing_id", "issuer_id", "form_type", "filed_at", "source_uri"],
                        "retention_policy": "retain_public_disclosure_for_research",
                        "cache_ttl_days": 3650,
                        "provenance_ref": "https://www.sec.gov/Archives/",
                        "usage_scope": "public_disclosure_research_only",
                        "collection_method": "official_public_download",
                        "robots_policy": "robots_and_tos_reviewed",
                        "review_cadence": "quarterly",
                        "review_owner": "platform_owner",
                        "review_owner_role": "平台负责人",
                        "source_tos_uri": "https://www.sec.gov/os/accessing-edgar-data",
                        "risk_level": "green",
                        "review_status": "approved",
                        "validation_status": "verified",
                    },
                    {
                        "source_id": "public_eod_market_data",
                        "source_class": "tdx_local",
                        "rights_tag": {
                            "license_class": "public_eod_reference",
                            "training_allowed": False,
                            "redistribution_allowed": False,
                            "display_use": "allowed",
                            "non_display_use": "allowed",
                            "derived_data_use": "restricted",
                        },
                        "field_whitelist": ["security_id", "as_of_date", "open", "high", "low", "close", "adjusted_close", "volume"],
                        "retention_policy": "retain_adjusted_eod_for_research_10y",
                        "cache_ttl_days": 3650,
                        "provenance_ref": "local://data/local/tdx/vipdoc",
                        "usage_scope": "public_eod_internal_research_backtest_risk",
                        "collection_method": "local_file_or_public_api",
                        "robots_policy": "reviewed_public_or_local_source",
                        "review_cadence": "quarterly",
                        "review_owner": "market_data_owner",
                        "review_owner_role": "数据工程",
                        "source_tos_uri": "https://www.tdx.com.cn/",
                        "risk_level": "green",
                        "review_status": "approved",
                        "validation_status": "verified",
                    },
                    {
                        "source_id": "local_research_reports",
                        "source_class": "local_research_reports",
                        "rights_tag": {
                            "license_class": "local_research_reference",
                            "training_allowed": False,
                            "redistribution_allowed": False,
                            "display_use": "restricted",
                            "non_display_use": "restricted",
                            "derived_data_use": "restricted",
                        },
                        "field_whitelist": ["report_id", "broker", "title", "published_at", "source_uri"],
                        "retention_policy": "retain_local_reference_reports_for_citation_tracking",
                        "cache_ttl_days": 3650,
                        "provenance_ref": "local:///home/xionglei/文档/6大投行研报汇总",
                        "usage_scope": "local_reference_citation_tracking_only",
                        "collection_method": "local_file_scan",
                        "robots_policy": "not_applicable_local_filesystem",
                        "review_cadence": "quarterly",
                        "review_owner": "research_owner",
                        "review_owner_role": "分析师",
                        "source_tos_uri": "internal://manual-review/local-research-cache-policy",
                        "risk_level": "yellow",
                        "review_status": "conditional",
                        "validation_status": "reviewed",
                    },
                ],
                "astock_connectors": astock_manifest,
                "evidence_package": evidence_package,
            }
        )
        self.assertTrue(valid["passed"])
        self.assertEqual(valid["required_check_count"], 9)
        self.assertIn("tdx_local", valid["allowed_data_source_classes"])

        template_style = validate_production_closure_manifest(
            {
                "ready_for_launch": False,
                "readiness_checks": base_checks,
                "reports": reports,
                "data_sources": [],
                "astock_connectors": astock_manifest,
            }
        )
        self.assertFalse(template_style["passed"])
        self.assertEqual(template_style["failure_count"], len(template_style["failures"]))
        template_failures = {item["check"] for item in template_style["failures"]}
        self.assertIn("ready_for_launch", template_failures)
        self.assertIn("evidence_package", template_failures)
        template_style_allowed = validate_production_closure_manifest(
            {
                "ready_for_launch": False,
                "readiness_checks": base_checks,
                "reports": reports,
                "data_sources": [],
                "astock_connectors": astock_manifest,
            },
            require_launch_ready=False,
        )
        self.assertTrue(template_style_allowed["passed"], template_style_allowed["failures"])
        self.assertEqual(template_style_allowed["failure_count"], 0)

        template_manifest = json.loads(Path("artifacts/production-closure-manifest.example.json").read_text(encoding="utf-8"))
        template_validation = validate_production_closure_manifest(template_manifest, require_launch_ready=False)
        self.assertTrue(template_validation["passed"], template_validation["failures"])
        self.assertEqual(template_validation["failure_count"], 0)
        self.assertEqual(template_validation["required_check_count"], 9)
        self.assertEqual(template_validation["required_report_count"], 5)
        self.assertEqual(len(template_manifest["astock_connectors"]["verify"]), 7)
        self.assertEqual(len(template_manifest["astock_connectors"]["verification_readiness"]["connector_ids"]), 7)

        manifest_validation = load_and_validate_production_closure_manifest(
            "artifacts/production-closure-manifest.example.json",
            require_launch_ready=False,
        )
        self.assertTrue(manifest_validation["passed"], manifest_validation["failures"])
        self.assertEqual(manifest_validation["failure_count"], 0)
        with TemporaryDirectory() as tmpdir:
            validation_output = Path(tmpdir) / "production-closure-manifest-validation.json"
            subprocess.run(
                [
                    sys.executable,
                    "scripts/production_closure_manifest_check.py",
                    "artifacts/production-closure-manifest.example.json",
                    "--allow-template",
                    "--output",
                    str(validation_output),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertTrue(validation_output.exists())
            self.assertFalse((validation_output.parent / f".{validation_output.name}.tmp").exists())
            self.assertTrue(json.loads(validation_output.read_text(encoding="utf-8"))["passed"])

        with TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "production-closure-result.json"
            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/production_closure.py",
                    "http://127.0.0.1:9",
                    "--manifest",
                    "artifacts/production-closure-manifest.example.json",
                    "--output",
                    str(output_path),
                    "--dry-run",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 1)
            self.assertTrue(output_path.exists())
            self.assertFalse((output_path.parent / f".{output_path.name}.tmp").exists())
            closure_result = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(closure_result["status"], "failed")

    def test_production_task_closure_audit_separates_external_evidence_blockers(self) -> None:
        audit = audit_production_tasks()
        self.assertEqual(audit["status"], "passed")
        self.assertEqual(audit["doing_task_count"], 0)
        self.assertEqual(audit["blocked_task_count"], 17)
        self.assertEqual(audit["open_task_count"], 17)
        self.assertEqual(audit["todo_status_counts"]["doing"], 0)
        self.assertFalse(audit["has_real_closure_evidence"])
        self.assertEqual(audit["counts"].get("needs_code_work", 0), 0)
        self.assertEqual(audit["counts"].get("blocked_external_evidence"), 17)
        self.assertEqual(audit["needs_code_work_count"], 0)
        self.assertEqual(audit["blocked_external_evidence_count"], 17)
        self.assertEqual(audit["done_by_real_evidence_count"], 0)
        self.assertEqual(audit["needs_code_work_task_ids"], [])
        self.assertEqual(len(audit["blocked_external_evidence_task_ids"]), 17)
        self.assertIn("T-416", audit["blocked_external_evidence_task_ids"])
        rows = {item["task_id"]: item for item in audit["tasks"]}
        self.assertIn("T-416", rows)
        self.assertIn("connector endpoint availability artifacts", rows["T-416"]["external_evidence_blockers"])
        self.assertGreater(rows["T-416"]["external_artifact_count_in_manifest"], 0)
        self.assertIn("T-412", rows)
        self.assertIn("production parameter confirmation", rows["T-412"]["external_evidence_blockers"])
        plan = build_evidence_collection_plan(audit)
        self.assertEqual(plan["task_count"], 17)
        plan_rows = {item["task_id"]: item for item in plan["tasks"]}
        self.assertEqual(plan_rows["T-416"]["readiness_endpoint"], "/api/connectors/astock/verification-readiness")
        self.assertIn("field_sample_uri", plan_rows["T-416"]["artifact_fields"])
        self.assertEqual(plan_rows["T-412"]["owner_role"], "平台负责人")
        self.assertIn("production_parameters_uri", plan_rows["T-412"]["artifact_uri_template"])
        plan_validation = validate_evidence_collection_plan(plan)
        self.assertTrue(plan_validation["passed"], plan_validation["failures"])
        self.assertEqual(plan_validation["failure_count"], 0)
        self.assertEqual(plan_validation["expected_task_count"], 17)
        plan_filled_validation = validate_evidence_collection_plan(plan, require_filled_uris=True)
        self.assertFalse(plan_filled_validation["passed"])
        self.assertEqual(plan_filled_validation["failure_count"], len(plan_filled_validation["failures"]))
        self.assertIn("artifact_uri_filled", {item["check"] for item in plan_filled_validation["failures"]})
        loaded_plan_validation = load_and_validate_evidence_collection_plan("artifacts/production-evidence-collection-plan.example.json")
        self.assertTrue(loaded_plan_validation["passed"], loaded_plan_validation["failures"])
        self.assertEqual(loaded_plan_validation["failure_count"], 0)

        with TemporaryDirectory() as tmpdir:
            quality_path = Path(tmpdir) / "quality-package.json"
            data_unblock_path = Path(tmpdir) / "local-data-unblock-audit.json"
            quality_path.write_text(
                json.dumps(
                    {
                        "sample_count": 500,
                        "language_counts": {"zh": 165, "en": 335},
                        "run_passed": True,
                        "large_sample_ready": True,
                        "readiness_missing_requirements": [],
                    }
                ),
                encoding="utf-8",
            )
            data_unblock_path.write_text(
                json.dumps(
                    {
                        "passed": True,
                        "data_blocked": False,
                        "remaining_quality_gaps": [],
                    }
                ),
                encoding="utf-8",
            )
            local_audit = audit_production_tasks(
                local_benchmark_quality_package_path=quality_path,
                local_data_unblock_audit_path=data_unblock_path,
            )
            self.assertTrue(local_audit["local_benchmark_quality_passed"])
            self.assertEqual(local_audit["done_by_real_evidence_count"], 1)
            self.assertIn("T-402", local_audit["done_by_real_evidence_task_ids"])
            self.assertEqual(local_audit["blocked_external_evidence_count"], 16)
            local_rows = {item["task_id"]: item for item in local_audit["tasks"]}
            self.assertTrue(local_rows["T-402"]["local_evidence_passed"])
            self.assertEqual(local_rows["T-402"]["external_evidence_blockers"], [])

        with TemporaryDirectory() as tmpdir:
            output_audit = Path(tmpdir) / "production-task-closure-audit.json"
            output_plan = Path(tmpdir) / "production-evidence-collection-plan.json"
            validation_output = Path(tmpdir) / "production-evidence-plan-validation.json"
            strict_validation_output = Path(tmpdir) / "production-evidence-plan-strict-validation.json"
            subprocess.run(
                [
                    sys.executable,
                    "scripts/production_task_closure_audit.py",
                    "--output",
                    str(output_audit),
                    "--output-plan",
                    str(output_plan),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertTrue(output_audit.exists())
            self.assertFalse((output_audit.parent / f".{output_audit.name}.tmp").exists())
            generated_audit = json.loads(output_audit.read_text(encoding="utf-8"))
            self.assertEqual(generated_audit["blocked_external_evidence_count"], 17)
            self.assertEqual(generated_audit["needs_code_work_task_ids"], [])
            self.assertTrue(output_plan.exists())
            self.assertFalse((output_plan.parent / f".{output_plan.name}.tmp").exists())
            generated_plan = json.loads(output_plan.read_text(encoding="utf-8"))
            self.assertTrue(validate_evidence_collection_plan(generated_plan)["passed"])
            subprocess.run(
                [
                    sys.executable,
                    "scripts/production_evidence_plan_check.py",
                    str(output_plan),
                    "--output",
                    str(validation_output),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertTrue(validation_output.exists())
            self.assertFalse((validation_output.parent / f".{validation_output.name}.tmp").exists())
            self.assertTrue(json.loads(validation_output.read_text(encoding="utf-8"))["passed"])
            self.assertEqual(json.loads(validation_output.read_text(encoding="utf-8"))["failure_count"], 0)
            strict_result = subprocess.run(
                [
                    sys.executable,
                    "scripts/production_evidence_plan_check.py",
                    str(output_plan),
                    "--require-filled-uris",
                    "--output",
                    str(strict_validation_output),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(strict_result.returncode, 1)
            self.assertTrue(strict_validation_output.exists())
            self.assertFalse((strict_validation_output.parent / f".{strict_validation_output.name}.tmp").exists())
            self.assertFalse(json.loads(strict_validation_output.read_text(encoding="utf-8"))["passed"])
            strict_output = json.loads(strict_validation_output.read_text(encoding="utf-8"))
            self.assertEqual(strict_output["failure_count"], len(strict_output["failures"]))

    def test_production_evidence_plan_fill_replaces_placeholders_with_strict_prefix(self) -> None:
        audit = audit_production_tasks()
        plan = build_evidence_collection_plan(audit)
        filled = fill_evidence_collection_plan(
            plan,
            artifact_prefix="s3://ai-quant-prod/evidence/release-20260518",
        )
        validation = validate_evidence_collection_plan(filled, require_filled_uris=True)
        self.assertTrue(validation["passed"], validation["failures"])
        first_row = filled["tasks"][0]
        self.assertTrue(first_row["artifact_uri_template"]["sample_manifest_uri"].startswith("s3://ai-quant-prod/evidence/release-20260518/T-402/"))
        self.assertNotIn("<production-evidence-bucket>", json.dumps(filled, ensure_ascii=False))

        with self.assertRaises(AssertionError):
            fill_evidence_collection_plan(plan, artifact_prefix="artifact://staging-local/release-20260518")

        with TemporaryDirectory() as tmpdir:
            plan_path = Path(tmpdir) / "plan.json"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/production_evidence_plan_fill.py",
                    str(plan_path),
                    "--artifact-prefix",
                    "s3://ai-quant-prod/evidence/release-20260518",
                    "--output",
                    str(plan_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertIn("filled_artifact_prefix", result.stdout)
            self.assertFalse((plan_path.parent / f".{plan_path.name}.tmp").exists())
            loaded = json.loads(plan_path.read_text(encoding="utf-8"))
            self.assertTrue(validate_evidence_collection_plan(loaded, require_filled_uris=True)["passed"])

    def test_project_completion_audit_maps_objective_to_real_evidence(self) -> None:
        completion = build_completion_audit()
        self.assertFalse(completion["achieved"])
        self.assertEqual(completion["status"], "not_achieved")
        self.assertEqual(completion["summary"]["doing_task_count"], 0)
        self.assertEqual(completion["summary"]["needs_code_work_count"], 0)
        self.assertEqual(completion["summary"]["blocked_external_evidence_count"], 17)
        self.assertFalse(completion["summary"]["has_real_closure_evidence"])
        self.assertEqual(completion["doing_task_count"], completion["summary"]["doing_task_count"])
        self.assertEqual(completion["needs_code_work_count"], completion["summary"]["needs_code_work_count"])
        self.assertEqual(completion["blocked_external_evidence_count"], completion["summary"]["blocked_external_evidence_count"])
        self.assertEqual(completion["open_task_count"], completion["summary"]["open_task_count"])
        self.assertIs(completion["has_real_closure_evidence"], completion["summary"]["has_real_closure_evidence"])
        self.assertEqual(completion["summary"]["target_mode"], "non_local_organizational_release")
        self.assertFalse(completion["summary"]["local_production_ready"])
        self.assertEqual(completion["blocked_requirement_ids"], ["R3", "R6"])
        self.assertEqual(completion["open_requirement_ids"], ["R3", "R6"])
        self.assertEqual(completion["failed_requirement_ids"], [])
        self.assertEqual([item["requirement_id"] for item in completion["blocked_requirements"]], ["R3", "R6"])
        checklist = {item["requirement_id"]: item for item in completion["prompt_to_artifact_checklist"]}
        self.assertEqual(checklist["R1"]["status"], "passed")
        self.assertEqual(checklist["R2"]["status"], "passed")
        self.assertEqual(checklist["R3"]["status"], "blocked")
        self.assertEqual(checklist["R6"]["status"], "blocked")
        self.assertIn("真实 staging/production artifact URI", checklist["R3"]["gap"])
        self.assertIsNone(completion["production_release_gate"])

        with TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "project-completion-audit.json"
            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/project_completion_audit.py",
                    "--output",
                    str(output_path),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 2)
            self.assertTrue(output_path.exists())
            self.assertFalse((output_path.parent / f".{output_path.name}.tmp").exists())
            output = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(output["status"], "not_achieved")
            self.assertEqual(output["blocked_external_evidence_count"], 17)
            self.assertFalse(output["has_real_closure_evidence"])
            self.assertEqual(output["blocked_requirement_ids"], ["R3", "R6"])

    def test_project_completion_audit_accepts_explicit_local_personal_production_evidence(self) -> None:
        local_audit = {
            "status": "passed",
            "passed": True,
            "deployment_target": "local_only_personal_production",
            "ready_for_launch": True,
            "failure_count": 0,
            "warning_count": 2,
            "strict_production_gate_unchanged": True,
        }
        ai_acceptance = {
            "status": "passed",
            "passed": True,
            "deployment_target": "local_only_personal_production",
            "failure_count": 0,
        }
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            local_path = tmp_path / "local-production-audit.json"
            ai_path = tmp_path / "local-ai-capability-acceptance.json"
            output_path = tmp_path / "project-completion-audit.json"
            local_path.write_text(json.dumps(local_audit), encoding="utf-8")
            ai_path.write_text(json.dumps(ai_acceptance), encoding="utf-8")

            completion = build_completion_audit(
                local_production_audit_path=local_path,
                local_ai_acceptance_path=ai_path,
            )
            self.assertTrue(completion["achieved"], completion["blocked_requirements"])
            self.assertEqual(completion["status"], "achieved")
            self.assertEqual(completion["summary"]["target_mode"], "local_only_personal_production")
            self.assertTrue(completion["summary"]["local_production_ready"])
            self.assertEqual(completion["blocked_requirement_ids"], [])
            self.assertEqual(completion["open_requirement_ids"], [])
            self.assertEqual(completion["local_production_evidence"]["warning_count"], 2)
            self.assertTrue(completion["local_production_evidence"]["strict_production_gate_unchanged"])

            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/project_completion_audit.py",
                    "--local-production-audit",
                    str(local_path),
                    "--local-ai-acceptance",
                    str(ai_path),
                    "--output",
                    str(output_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertIn('"status": "achieved"', result.stdout)
            self.assertTrue(output_path.exists())
            self.assertFalse((output_path.parent / f".{output_path.name}.tmp").exists())
            output = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertTrue(output["achieved"])
            self.assertEqual(output["local_production_evidence"]["target_mode"], "local_only_personal_production")

    def test_project_completion_audit_requires_release_gate_even_when_tasks_are_done(self) -> None:
        with TemporaryDirectory() as tmpdir:
            todo_path = Path(tmpdir) / "todo_done.md"
            todo_path.write_text("- `DONE` T-402 example\n- `DONE` T-404 example\n", encoding="utf-8")
            completion = build_completion_audit(todo_path=todo_path)
        self.assertFalse(completion["achieved"])
        self.assertEqual(completion["summary"]["open_task_count"], 0)
        checklist = {item["requirement_id"]: item for item in completion["prompt_to_artifact_checklist"]}
        self.assertEqual(checklist["R1"]["status"], "passed")
        self.assertEqual(checklist["R6"]["status"], "blocked")
        self.assertIn("release gate", checklist["R6"]["gap"])

    def test_project_completion_audit_can_enforce_release_bundle_hashes(self) -> None:
        audit = audit_production_tasks()
        plan = build_evidence_collection_plan(audit)
        for row in plan["tasks"]:
            task_id = row["task_id"]
            row["status"] = "blocked_external_evidence"
            row["artifact_uri_template"] = {
                field: f"s3://ai-quant-prod/evidence/completion-bundle/{task_id}/{field}.json"
                for field in row["artifact_fields"]
            }
        base_manifest = json.loads(Path("artifacts/production-closure-manifest.example.json").read_text(encoding="utf-8"))
        package = json.loads(Path("artifacts/readiness-evidence-package.example.json").read_text(encoding="utf-8"))
        manifest = build_manifest_from_evidence_plan(
            plan,
            base_manifest=base_manifest,
            evidence_package=package,
            release_ready=True,
        )
        inventory = self._production_artifact_inventory_for_contexts(plan, package, manifest)
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            plan_path = tmp_path / "plan.json"
            package_path = tmp_path / "package.json"
            inventory_path = tmp_path / "inventory.json"
            manifest_path = tmp_path / "manifest.json"
            todo_path = tmp_path / "todo_done.md"
            bundle_root = tmp_path / "bundle"
            todo_path.write_text("\n".join(f"- `DONE` {task_id} example" for task_id in TASKS_WITH_EXTERNAL_EVIDENCE) + "\n", encoding="utf-8")
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            package_path.write_text(json.dumps(package), encoding="utf-8")
            inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
            manifest_path.write_text(json.dumps(base_manifest), encoding="utf-8")

            completion = build_completion_audit(
                todo_path=todo_path,
                manifest_path=manifest_path,
                evidence_plan_path=plan_path,
                evidence_package_path=package_path,
                artifact_inventory_path=inventory_path,
                artifact_bundle_root=bundle_root,
            )
            self.assertFalse(completion["achieved"])
            self.assertEqual(completion["production_release_gate"]["failed_stage"], "artifact_inventory_validation")
            checks = {item["check"] for item in completion["production_release_gate"]["artifact_inventory_validation"]["failures"]}
            self.assertIn("bundle_file_exists", checks)

    def test_local_production_audit_accepts_local_only_readiness_without_relaxing_strict_gate(self) -> None:
        health = {
            "success": True,
            "data": {
                "status": "ok",
                "store": "PostgreSQLStore",
                "object_store": {"backend": "s3", "root": "s3://ai-quant-local/raw"},
                "search_index": {"backend": "opensearch"},
                "tdx_market_data": {"configured": True},
            },
        }
        vision_gate = {
            "success": True,
            "data": {
                "status": "ready",
                "gates": [{"name": "evidence_coverage", "passed": True}],
            },
        }
        package = {
            "success": True,
            "data": {
                "status": "ready",
                "ready_for_launch": True,
                "missing_evidence_count": 0,
                "failed_gate_count": 0,
                "checklist_coverage": 1.0,
                "required_evidence": [
                    {
                        "check_id": check_id,
                        "status": "passed",
                        "missing_evidence": False,
                        "evidence_uri": f"artifact://staging-local/{check_id}.json",
                    }
                    for check_id in sorted(REQUIRED_CHECK_IDS)
                ],
                "external_validations": [
                    {
                        "scope": scope,
                        "check_status": "passed",
                        "ready": scope != "graph_vector_semantic_search",
                        "evidence_uri": f"artifact://staging-local/{scope}.json",
                    }
                    for scope in sorted(REQUIRED_EXTERNAL_VALIDATION_SCOPES)
                ],
            },
        }
        metrics = {
            "success": True,
            "data": {
                "pending_prompt_changes": 0,
                "sensitive_findings": 0,
                "source_review_overdue": 0,
                "workflow_failed_runs": 1,
                "open_alerts": 1,
            },
        }

        audit = build_local_production_audit(
            health=health,
            vision_gate=vision_gate,
            evidence_package=package,
            metrics=metrics,
        )

        self.assertTrue(audit["passed"], audit["failures"])
        self.assertEqual(audit["deployment_target"], "local_only_personal_production")
        self.assertTrue(audit["strict_production_gate_unchanged"])
        self.assertGreaterEqual(audit["warning_count"], 1)
        self.assertIn("not valid as non-local organizational release evidence", audit["production_boundary"])
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            health_path = tmp_path / "health.json"
            vision_path = tmp_path / "vision.json"
            package_path = tmp_path / "package.json"
            metrics_path = tmp_path / "metrics.json"
            output_path = tmp_path / "local-production-audit.json"
            health_path.write_text(json.dumps(health), encoding="utf-8")
            vision_path.write_text(json.dumps(vision_gate), encoding="utf-8")
            package_path.write_text(json.dumps(package), encoding="utf-8")
            metrics_path.write_text(json.dumps(metrics), encoding="utf-8")
            subprocess.run(
                [
                    sys.executable,
                    "scripts/local_production_audit.py",
                    "--health-json",
                    str(health_path),
                    "--vision-gate-json",
                    str(vision_path),
                    "--evidence-package-json",
                    str(package_path),
                    "--metrics-json",
                    str(metrics_path),
                    "--output",
                    str(output_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertTrue(output_path.exists())
            self.assertFalse((output_path.parent / f".{output_path.name}.tmp").exists())

    def test_local_production_audit_rejects_missing_or_demo_evidence(self) -> None:
        health = {
            "status": "ok",
            "store": "SQLiteStore",
            "object_store": {"backend": "local"},
            "search_index": {"backend": "local"},
            "tdx_market_data": {"configured": False},
        }
        vision_gate = {"status": "not_ready", "gates": [{"name": "evidence_coverage", "passed": False}]}
        package = {
            "status": "ready",
            "ready_for_launch": True,
            "missing_evidence_count": 0,
            "failed_gate_count": 0,
            "checklist_coverage": 1.0,
            "required_evidence": [
                {
                    "check_id": check_id,
                    "status": "passed",
                    "missing_evidence": False,
                    "evidence_uri": "artifact://demo/local.json",
                }
                for check_id in sorted(REQUIRED_CHECK_IDS)
            ],
            "external_validations": [
                {"scope": scope, "check_status": "passed", "ready": True}
                for scope in sorted(REQUIRED_EXTERNAL_VALIDATION_SCOPES)
            ],
        }

        audit = build_local_production_audit(health=health, vision_gate=vision_gate, evidence_package=package)

        self.assertFalse(audit["passed"])
        failure_checks = {item["check"] for item in audit["failures"]}
        self.assertIn("state_store", failure_checks)
        self.assertIn("vision_gate_status", failure_checks)
        self.assertIn("required_evidence_uri", failure_checks)

    def test_local_production_audit_writes_failure_artifact_when_input_fetch_fails(self) -> None:
        with TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "local-production-audit.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    "scripts/local_production_audit.py",
                    "--base-url",
                    "http://127.0.0.1:9",
                    "--timeout",
                    "0.01",
                    "--output",
                    str(output_path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertNotEqual(completed.returncode, 0)
            self.assertTrue(output_path.exists())
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "failed")
            self.assertFalse(payload["ready_for_launch"])
            self.assertEqual(payload["failure_count"], 1)
            self.assertEqual(payload["failures"][0]["check"], "local_production_audit_input")

    def test_local_ai_capability_acceptance_summarizes_real_smokes_without_secret_payloads(self) -> None:
        from http.server import BaseHTTPRequestHandler

        health = {
            "success": True,
            "data": {
                "status": "ok",
                "store": "PostgreSQLStore",
                "object_store": {"backend": "s3"},
                "search_index": {"backend": "opensearch"},
                "tdx_market_data": {"configured": True},
                "llm_gateway": {"configured": True, "default_model": "qwen3.6-plus"},
                "document_parser": {"configured": True, "model": "PaddleOCR-VL-1.5"},
            },
        }
        llm_response = {
            "success": True,
            "data": {
                "provider": "openai",
                "model": "qwen3.6-plus",
                "response": {"choices": [{"message": {"content": "ok"}}]},
            },
        }
        ocr_response = {
            "success": True,
            "data": {
                "provider": "paddleocr",
                "model": "PaddleOCR-VL-1.5",
                "job_id": "job_1",
                "state": "done",
                "page_count": 1,
                "attempt_count": 1,
                "retry_attempts": 0,
                "cache_hit": False,
                "elapsed_ms": 1530,
                "result_url": "https://signed.example.invalid/secret-jsonl",
                "text": "Dummy PDF file",
            },
        }

        audit = build_local_ai_capability_acceptance(
            health=health,
            llm_response=llm_response,
            llm_wall_ms=500,
            ocr_response=ocr_response,
            ocr_wall_ms=1600,
        )

        self.assertTrue(audit["passed"], audit["failures"])
        self.assertTrue(audit["llm_gateway"]["smoke_passed"])
        self.assertTrue(audit["paddleocr"]["smoke_passed"])
        rendered = json.dumps(audit)
        self.assertNotIn("secret-jsonl", rendered)
        self.assertNotIn("result_url", rendered)

        class _LocalAiHandler(BaseHTTPRequestHandler):
            def _send_json(self, payload: dict) -> None:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:
                if self.path == "/api/health":
                    self._send_json(health)
                else:
                    self.send_error(404)

            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", "0") or 0)
                if length:
                    self.rfile.read(length)
                if self.path == "/api/llm/openai/chat/completions":
                    self._send_json(llm_response)
                elif self.path == "/api/document-parsing/paddleocr":
                    self._send_json(ocr_response)
                else:
                    self.send_error(404)

            def log_message(self, format: str, *args) -> None:
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), _LocalAiHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with TemporaryDirectory() as tmpdir:
                output_path = Path(tmpdir) / "local-ai-capability.json"
                subprocess.run(
                    [
                        sys.executable,
                        "scripts/local_ai_capability_acceptance.py",
                        "--base-url",
                        f"http://127.0.0.1:{server.server_port}",
                        "--ocr-file-url",
                        "https://example.invalid/local-ai-cli-test.pdf",
                        "--timeout",
                        "5",
                        "--output",
                        str(output_path),
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                self.assertTrue(output_path.exists())
                self.assertFalse((output_path.parent / f".{output_path.name}.tmp").exists())
                cli_audit = json.loads(output_path.read_text(encoding="utf-8"))
                self.assertEqual(cli_audit["status"], "passed")
                self.assertTrue(cli_audit["llm_gateway"]["smoke_passed"])
                self.assertTrue(cli_audit["paddleocr"]["smoke_passed"])
                self.assertNotIn("secret-jsonl", json.dumps(cli_audit))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_local_ai_capability_acceptance_rejects_unconfigured_or_empty_smokes(self) -> None:
        audit = build_local_ai_capability_acceptance(
            health={
                "status": "ok",
                "llm_gateway": {"configured": False},
                "document_parser": {"configured": False},
            },
            llm_response={"success": True, "response": {"choices": [{"message": {"content": "nope"}}]}},
            ocr_response={"success": True, "state": "done", "page_count": 0, "text": ""},
        )

        self.assertFalse(audit["passed"])
        failure_checks = {item["check"] for item in audit["failures"]}
        self.assertIn("llm_configured", failure_checks)
        self.assertIn("paddleocr_configured", failure_checks)
        self.assertIn("llm_smoke", failure_checks)
        self.assertIn("paddleocr_smoke", failure_checks)

    def test_production_evidence_plan_to_manifest_maps_filled_uris_without_marking_release_ready(self) -> None:
        audit = audit_production_tasks()
        plan = build_evidence_collection_plan(audit)
        for row in plan["tasks"]:
            task_id = row["task_id"]
            row["status"] = "blocked_external_evidence"
            row["artifact_uri_template"] = {
                field: f"s3://ai-quant-prod/evidence/2026Q2/{task_id}/{field}.json"
                for field in row["artifact_fields"]
            }
        base_manifest = json.loads(Path("artifacts/production-closure-manifest.example.json").read_text(encoding="utf-8"))
        manifest = build_manifest_from_evidence_plan(plan, base_manifest=base_manifest)

        self.assertFalse(manifest["ready_for_launch"])
        self.assertEqual(len(manifest["task_evidence"]), 17)
        self.assertEqual(
            manifest["readiness_checks"]["cross_browser_acceptance"]["evidence_uri"],
            "s3://ai-quant-prod/evidence/2026Q2/T-407/cross_browser_matrix_uri.json",
        )
        self.assertEqual(
            manifest["readiness_checks"]["launch_checklist"]["evidence_uri"],
            "s3://ai-quant-prod/evidence/2026Q2/T-412/release_checklist_uri.json",
        )
        self.assertEqual(
            manifest["reports"]["storage"]["artifact_uris"]["postgres_smoke_uri"],
            "s3://ai-quant-prod/evidence/2026Q2/T-404/postgres_smoke_uri.json",
        )
        self.assertEqual(
            manifest["reports"]["security"]["artifact_uris"]["permission_review_uri"],
            "s3://ai-quant-prod/evidence/2026Q2/T-421/permission_review_uri.json",
        )
        for connector_id in manifest["astock_connectors"]["verification_readiness"]["connector_ids"]:
            self.assertEqual(
                manifest["astock_connectors"]["verification_readiness"]["artifact_uris"][connector_id]["license_review_uri"],
                "s3://ai-quant-prod/evidence/2026Q2/T-416/license_review_uri.json",
            )
        generation = manifest["manifest_generation"]
        self.assertTrue(generation["filled_uri_validation"]["passed"])
        self.assertEqual(generation["mapped_readiness_check_count"], len(generation["mapped_readiness_checks"]))
        self.assertEqual(
            generation["mapped_external_validation_scope_count"],
            len(generation["mapped_external_validation_scopes"]),
        )
        self.assertIn("launch_checklist", generation["mapped_readiness_checks"])
        self.assertIn("desktop_mobile_cross_browser", generation["mapped_external_validation_scopes"])
        self.assertEqual(generation["missing_readiness_check_count"], 0)
        self.assertEqual(generation["missing_readiness_checks_from_plan"], [])
        self.assertEqual(generation["missing_external_validation_scope_count"], 0)
        self.assertEqual(generation["missing_external_validation_scopes_from_plan"], [])
        self.assertEqual(generation["skipped_mapping_count"], len(generation["skipped_mappings"]))
        self.assertFalse(generation["release_validation"]["passed"])
        self.assertIn("ready_for_launch", {item["check"] for item in generation["release_validation"]["failures"]})

        draft_validation = validate_production_closure_manifest(manifest, require_launch_ready=False)
        self.assertTrue(draft_validation["passed"], draft_validation["failures"])
        strict_validation = validate_production_closure_manifest(manifest)
        self.assertFalse(strict_validation["passed"])
        self.assertIn("ready_for_launch", {item["check"] for item in strict_validation["failures"]})

        with TemporaryDirectory() as tmpdir:
            plan_path = Path(tmpdir) / "filled-plan.json"
            output_path = Path(tmpdir) / "production-closure-manifest.json"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            subprocess.run(
                [
                    sys.executable,
                    "scripts/production_evidence_plan_to_manifest.py",
                    "--plan",
                    str(plan_path),
                    "--base",
                    "artifacts/production-closure-manifest.example.json",
                    "--output",
                    str(output_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertTrue(output_path.exists())
            self.assertFalse((output_path.parent / f".{output_path.name}.tmp").exists())
            self.assertEqual(json.loads(output_path.read_text(encoding="utf-8"))["task_evidence"]["T-407"]["artifact_uris"]["cross_browser_matrix_uri"], "s3://ai-quant-prod/evidence/2026Q2/T-407/cross_browser_matrix_uri.json")

    def test_production_evidence_plan_to_manifest_rejects_placeholders_by_default(self) -> None:
        audit = audit_production_tasks()
        plan = build_evidence_collection_plan(audit)
        base_manifest = json.loads(Path("artifacts/production-closure-manifest.example.json").read_text(encoding="utf-8"))
        with self.assertRaises(AssertionError):
            build_manifest_from_evidence_plan(plan, base_manifest=base_manifest)

        manifest = build_manifest_from_evidence_plan(plan, base_manifest=base_manifest, allow_placeholders=True)
        self.assertFalse(manifest["manifest_generation"]["release_field_mapping_enabled"])
        self.assertGreater(len(manifest["manifest_generation"]["skipped_mappings"]), 0)
        self.assertEqual(
            manifest["manifest_generation"]["skipped_mapping_count"],
            len(manifest["manifest_generation"]["skipped_mappings"]),
        )
        self.assertGreater(manifest["manifest_generation"]["missing_readiness_check_count"], 0)
        self.assertGreater(manifest["manifest_generation"]["missing_external_validation_scope_count"], 0)
        self.assertEqual(
            manifest["readiness_checks"]["cross_browser_acceptance"]["evidence_uri"],
            base_manifest["readiness_checks"]["cross_browser_acceptance"]["evidence_uri"],
        )

    def test_production_evidence_plan_to_manifest_can_build_release_manifest_with_real_package(self) -> None:
        audit = audit_production_tasks()
        plan = build_evidence_collection_plan(audit)
        for row in plan["tasks"]:
            task_id = row["task_id"]
            row["status"] = "blocked_external_evidence"
            row["artifact_uri_template"] = {
                field: f"s3://ai-quant-prod/evidence/release-20260517/{task_id}/{field}.json"
                for field in row["artifact_fields"]
            }
        base_manifest = json.loads(Path("artifacts/production-closure-manifest.example.json").read_text(encoding="utf-8"))
        package = json.loads(Path("artifacts/readiness-evidence-package.example.json").read_text(encoding="utf-8"))

        manifest = build_manifest_from_evidence_plan(
            plan,
            base_manifest=base_manifest,
            evidence_package=package,
            release_ready=True,
        )

        self.assertTrue(manifest["ready_for_launch"])
        strict_validation = validate_production_closure_manifest(manifest)
        self.assertTrue(strict_validation["passed"], strict_validation["failures"])
        self.assertTrue(manifest["manifest_generation"]["release_validation"]["passed"])
        self.assertEqual(manifest["manifest_generation"]["missing_readiness_check_count"], 0)
        self.assertEqual(manifest["manifest_generation"]["missing_external_validation_scope_count"], 0)
        self.assertEqual(
            manifest["manifest_generation"]["mapped_readiness_check_count"],
            len(manifest["manifest_generation"]["mapped_readiness_checks"]),
        )
        self.assertEqual(manifest["evidence_package"]["package_id"], "readiness_pkg_example")

    def _production_artifact_inventory_for_contexts(self, *contexts):
        uris = sorted({row["uri"] for row in collect_required_artifact_uris(*contexts)})
        return {
            "inventory_id": "release-inventory-test",
            "environment": "staging",
            "storage_backend": "s3",
            "generated_at": "2026-05-17T00:00:00Z",
            "artifact_count": len(uris),
            "artifacts": [
                {
                    "uri": uri,
                    "sha256": f"{idx + 1:064x}",
                    "size_bytes": 1024 + idx,
                    "environment": "staging",
                    "storage_backend": "s3",
                    "created_at": "2026-05-17T00:00:00Z",
                    "producer": "staging_acceptance",
                    "owner_role": "平台负责人",
                    "content_type": "application/json",
                    "retention_policy": "retain_release_evidence_7y",
                    "immutable": True,
                }
                for idx, uri in enumerate(uris)
            ],
        }

    def _write_artifact_inventory_bundle(self, inventory, bundle_root: Path) -> None:
        for idx, row in enumerate(inventory["artifacts"]):
            bundle_path = Path(row.get("bundle_path", f"release-artifacts/{idx:04d}.json"))
            row["bundle_path"] = str(bundle_path)
            content = json.dumps({"uri": row["uri"], "index": idx}, sort_keys=True).encode("utf-8")
            target = bundle_root / bundle_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            row["sha256"] = hashlib.sha256(content).hexdigest()
            row["size_bytes"] = len(content)

    def test_production_artifact_inventory_covers_release_evidence_uris(self) -> None:
        audit = audit_production_tasks()
        plan = build_evidence_collection_plan(audit)
        for row in plan["tasks"]:
            task_id = row["task_id"]
            row["status"] = "blocked_external_evidence"
            row["artifact_uri_template"] = {
                field: f"s3://ai-quant-prod/evidence/inventory/{task_id}/{field}.json"
                for field in row["artifact_fields"]
            }
        base_manifest = json.loads(Path("artifacts/production-closure-manifest.example.json").read_text(encoding="utf-8"))
        package = json.loads(Path("artifacts/readiness-evidence-package.example.json").read_text(encoding="utf-8"))
        manifest = build_manifest_from_evidence_plan(
            plan,
            base_manifest=base_manifest,
            evidence_package=package,
            release_ready=True,
        )
        invalid = validate_artifact_inventory(
            {
                "inventory_id": "bad",
                "environment": "local",
                "storage_backend": "s3",
                "generated_at": "2026-05-17T00:00:00Z",
                "artifacts": [
                    {
                        "uri": "artifact://local/foo.json",
                        "sha256": "abc",
                        "size_bytes": 0,
                    }
                ],
            },
            required_contexts=[plan, package, manifest],
        )
        self.assertFalse(invalid["passed"])
        failure_checks = {item["check"] for item in invalid["failures"]}
        self.assertIn("inventory_environment", failure_checks)
        self.assertIn("inventory_artifact_uri", failure_checks)
        self.assertIn("required_artifact_inventory_coverage", failure_checks)

        placeholder_inventory = {
            "inventory_id": "placeholder",
            "environment": "staging",
            "storage_backend": "s3",
            "generated_at": "2026-05-17T00:00:00Z",
            "artifact_count": 1,
            "artifacts": [
                {
                    "uri": "s3://<production-evidence-bucket>/<release-id>/T-402/sample_manifest_uri",
                    "sha256": "1" * 64,
                    "size_bytes": 1024,
                    "environment": "staging",
                    "storage_backend": "s3",
                    "created_at": "2026-05-17T00:00:00Z",
                    "producer": "staging_acceptance",
                    "owner_role": "平台负责人",
                    "content_type": "application/json",
                    "retention_policy": "retain_release_evidence_7y",
                    "immutable": True,
                }
            ],
        }
        placeholder_validation = validate_artifact_inventory(placeholder_inventory)
        self.assertFalse(placeholder_validation["passed"])
        self.assertEqual(placeholder_validation["failure_count"], len(placeholder_validation["failures"]))
        self.assertIn("inventory_artifact_uri_filled", {item["check"] for item in placeholder_validation["failures"]})

        placeholder_context_validation = validate_artifact_inventory(
            self._production_artifact_inventory_for_contexts({"artifact_uris": {"ok": "s3://ai-quant-prod/evidence/ok.json"}}),
            required_contexts=[
                {"artifact_uris": {"leftover": "s3://<production-evidence-bucket>/<release-id>/leftover.json"}}
            ],
        )
        self.assertFalse(placeholder_context_validation["passed"])
        self.assertEqual(placeholder_context_validation["failure_count"], len(placeholder_context_validation["failures"]))
        self.assertIn("required_artifact_uri_filled", {item["check"] for item in placeholder_context_validation["failures"]})

        inventory = self._production_artifact_inventory_for_contexts(plan, package, manifest)
        valid = validate_artifact_inventory(inventory, required_contexts=[plan, package, manifest])
        self.assertTrue(valid["passed"], valid["failures"])
        self.assertEqual(valid["failure_count"], 0)
        self.assertGreater(valid["required_uri_count"], 0)

        template = build_artifact_inventory_template(plan, package, manifest)
        self.assertEqual(template["artifact_count"], valid["required_uri_count"])
        self.assertGreater(len(template["artifacts"][0]["source_paths"]), 0)
        template_validation = validate_artifact_inventory(template, required_contexts=[plan, package, manifest])
        self.assertFalse(template_validation["passed"])
        self.assertEqual(template_validation["failure_count"], len(template_validation["failures"]))
        template_failure_checks = {item["check"] for item in template_validation["failures"]}
        self.assertIn("inventory_sha256", template_failure_checks)
        self.assertIn("inventory_generated_at", template_failure_checks)
        self.assertIn("inventory_producer", template_failure_checks)

    def test_production_artifact_inventory_can_verify_local_bundle_hashes(self) -> None:
        with TemporaryDirectory() as tmpdir:
            bundle_root = Path(tmpdir)
            content = b'{"status":"passed"}\n'
            bundle_path = bundle_root / "prod-readiness" / "real-data-smoke-test.json"
            bundle_path.parent.mkdir(parents=True)
            bundle_path.write_bytes(content)
            digest = hashlib.sha256(content).hexdigest()
            inventory = {
                "inventory_id": "bundle-inventory",
                "environment": "staging",
                "storage_backend": "s3",
                "generated_at": "2026-05-17T00:00:00Z",
                "artifact_count": 1,
                "artifacts": [
                    {
                        "uri": "artifact://prod-readiness/real-data-smoke-test.json",
                        "bundle_path": "prod-readiness/real-data-smoke-test.json",
                        "sha256": digest,
                        "size_bytes": len(content),
                        "environment": "staging",
                        "storage_backend": "s3",
                        "created_at": "2026-05-17T00:00:00Z",
                        "producer": "staging_acceptance",
                        "owner_role": "平台负责人",
                        "content_type": "application/json",
                        "retention_policy": "retain_release_evidence_7y",
                        "immutable": True,
                    }
                ],
            }
            valid = validate_artifact_inventory(inventory, bundle_root=bundle_root)
            self.assertTrue(valid["passed"], valid["failures"])
            self.assertEqual(valid["failure_count"], 0)
            self.assertEqual(valid["bundle_check_count"], 1)

            inventory["artifacts"][0]["sha256"] = "0" * 64
            invalid = validate_artifact_inventory(inventory, bundle_root=bundle_root)
            self.assertFalse(invalid["passed"])
            self.assertEqual(invalid["failure_count"], len(invalid["failures"]))
            self.assertIn("bundle_sha256", {item["check"] for item in invalid["failures"]})

    def test_production_artifact_inventory_can_be_generated_from_bundle(self) -> None:
        package = json.loads(Path("artifacts/readiness-evidence-package.example.json").read_text(encoding="utf-8"))
        template = build_artifact_inventory_template(package)
        with TemporaryDirectory() as tmpdir:
            bundle_root = Path(tmpdir)
            for idx, row in enumerate(template["artifacts"]):
                target = bundle_root / row["bundle_path"]
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(json.dumps({"uri": row["uri"], "idx": idx}), encoding="utf-8")
            inventory = build_artifact_inventory_from_bundle(
                package,
                bundle_root=bundle_root,
                producer="staging_acceptance",
                owner_role="平台负责人",
            )
            self.assertEqual(inventory["missing_bundle_file_count"], 0)
            self.assertEqual(inventory["artifact_count"], template["artifact_count"])
            self.assertRegex(inventory["generated_at"], r"^\d{4}-\d{2}-\d{2}T")
            validation = validate_artifact_inventory(inventory, required_contexts=[package], bundle_root=bundle_root)
            self.assertTrue(validation["passed"], validation["failures"])
            self.assertEqual(validation["failure_count"], 0)
            self.assertEqual(validation["bundle_check_count"], template["artifact_count"])

            missing = build_artifact_inventory_from_bundle(
                {"artifact_uris": {"missing": "artifact://prod-readiness/missing.json"}},
                bundle_root=bundle_root,
                generated_at="2026-05-17T00:00:00Z",
            )
            self.assertEqual(missing["artifact_count"], 0)
            self.assertEqual(missing["missing_bundle_file_count"], 1)

            template_path = bundle_root / "inventory-template.json"
            subprocess.run(
                [
                    sys.executable,
                    "scripts/production_artifact_inventory_check.py",
                    "--evidence-package",
                    "artifacts/readiness-evidence-package.example.json",
                    "--output-template",
                    str(template_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertTrue(template_path.exists())
            self.assertFalse((template_path.parent / f".{template_path.name}.tmp").exists())

            inventory_path = bundle_root / "inventory.json"
            subprocess.run(
                [
                    sys.executable,
                    "scripts/production_artifact_inventory_check.py",
                    "--evidence-package",
                    "artifacts/readiness-evidence-package.example.json",
                    "--from-bundle-root",
                    str(bundle_root),
                    "--output",
                    str(inventory_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertTrue(inventory_path.exists())
            self.assertFalse((inventory_path.parent / f".{inventory_path.name}.tmp").exists())

            validation_path = bundle_root / "inventory-validation.json"
            subprocess.run(
                [
                    sys.executable,
                    "scripts/production_artifact_inventory_check.py",
                    str(inventory_path),
                    "--evidence-package",
                    "artifacts/readiness-evidence-package.example.json",
                    "--bundle-root",
                    str(bundle_root),
                    "--output",
                    str(validation_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertTrue(validation_path.exists())
            self.assertFalse((validation_path.parent / f".{validation_path.name}.tmp").exists())

    def test_production_release_gate_requires_real_package_and_can_pass_strict_plan(self) -> None:
        audit = audit_production_tasks()
        plan = build_evidence_collection_plan(audit)
        base_manifest = json.loads(Path("artifacts/production-closure-manifest.example.json").read_text(encoding="utf-8"))
        draft = run_production_release_gate(plan=plan, base_manifest=base_manifest, draft=True)
        self.assertEqual(draft["status"], "draft")
        self.assertFalse(draft["manifest_ready_for_launch"])
        self.assertEqual(draft["failed_stage_count"], 0)
        self.assertGreaterEqual(draft["passed_stage_count"], 2)

        for row in plan["tasks"]:
            task_id = row["task_id"]
            row["status"] = "blocked_external_evidence"
            row["artifact_uri_template"] = {
                field: f"s3://ai-quant-prod/evidence/release-gate/{task_id}/{field}.json"
                for field in row["artifact_fields"]
            }

        missing_package = run_production_release_gate(plan=plan, base_manifest=base_manifest)
        self.assertEqual(missing_package["status"], "failed")
        self.assertEqual(missing_package["failed_stage"], "evidence_package_required")
        self.assertEqual(missing_package["failed_stage_count"], 1)
        self.assertEqual(missing_package["failed_stage_names"], ["evidence_package_required"])

        package = json.loads(Path("artifacts/readiness-evidence-package.example.json").read_text(encoding="utf-8"))
        missing_inventory = run_production_release_gate(
            plan=plan,
            base_manifest=base_manifest,
            evidence_package=package,
        )
        self.assertEqual(missing_inventory["status"], "failed")
        self.assertEqual(missing_inventory["failed_stage"], "artifact_inventory_required")
        self.assertEqual(missing_inventory["failed_stage_count"], 1)
        self.assertEqual(missing_inventory["failed_stage_names"], ["artifact_inventory_required"])
        preview_manifest = build_manifest_from_evidence_plan(
            plan,
            base_manifest=base_manifest,
            evidence_package=package,
            release_ready=True,
        )
        inventory = self._production_artifact_inventory_for_contexts(plan, package, preview_manifest)
        strict = run_production_release_gate(
            plan=plan,
            base_manifest=base_manifest,
            evidence_package=package,
            artifact_inventory=inventory,
        )
        self.assertEqual(strict["status"], "passed")
        self.assertTrue(strict["manifest_ready_for_launch"])
        self.assertTrue(strict["manifest_validation"]["passed"])
        self.assertTrue(strict["artifact_inventory_validation"]["passed"])
        self.assertEqual(strict["failed_stage_count"], 0)
        self.assertEqual(strict["stage_count"], strict["passed_stage_count"])

        with TemporaryDirectory() as tmpdir:
            bundle_inventory = self._production_artifact_inventory_for_contexts(plan, package, preview_manifest)
            self._write_artifact_inventory_bundle(bundle_inventory, Path(tmpdir))
            bundle_strict = run_production_release_gate(
                plan=plan,
                base_manifest=base_manifest,
                evidence_package=package,
                artifact_inventory=bundle_inventory,
                artifact_bundle_root=tmpdir,
            )
            self.assertEqual(bundle_strict["status"], "passed")
            self.assertEqual(
                bundle_strict["artifact_inventory_validation"]["bundle_check_count"],
                len(bundle_inventory["artifacts"]),
            )

        with TemporaryDirectory() as tmpdir:
            manifest_output = Path(tmpdir) / "production-closure-manifest.json"
            bad_inventory = self._production_artifact_inventory_for_contexts(plan, package, preview_manifest)
            bad_inventory["artifacts"][0]["sha256"] = "not-a-sha"
            failed = run_production_release_gate(
                plan=plan,
                base_manifest=base_manifest,
                evidence_package=package,
                artifact_inventory=bad_inventory,
                manifest_output=manifest_output,
            )
            self.assertEqual(failed["status"], "failed")
            self.assertEqual(failed["failed_stage"], "artifact_inventory_validation")
            self.assertEqual(failed["failed_stage_count"], 1)
            self.assertEqual(failed["failed_stage_names"], ["artifact_inventory_validation"])
            self.assertFalse(manifest_output.exists())
            self.assertFalse((manifest_output.parent / f".{manifest_output.name}.tmp").exists())

            passed_manifest_output = Path(tmpdir) / "production-closure-manifest-passed.json"
            passed = run_production_release_gate(
                plan=plan,
                base_manifest=base_manifest,
                evidence_package=package,
                artifact_inventory=inventory,
                manifest_output=passed_manifest_output,
            )
            self.assertEqual(passed["status"], "passed")
            self.assertEqual(passed["failed_stage_count"], 0)
            self.assertTrue(passed_manifest_output.exists())
            self.assertFalse((passed_manifest_output.parent / f".{passed_manifest_output.name}.tmp").exists())

            plan_path = Path(tmpdir) / "evidence-plan.json"
            package_path = Path(tmpdir) / "readiness-package.json"
            inventory_path = Path(tmpdir) / "artifact-inventory.json"
            result_path = Path(tmpdir) / "release-gate-result.json"
            cli_manifest_output = Path(tmpdir) / "production-closure-manifest-cli.json"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            package_path.write_text(json.dumps(package), encoding="utf-8")
            inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
            subprocess.run(
                [
                    sys.executable,
                    "scripts/production_release_gate.py",
                    "--plan",
                    str(plan_path),
                    "--evidence-package",
                    str(package_path),
                    "--artifact-inventory",
                    str(inventory_path),
                    "--manifest-output",
                    str(cli_manifest_output),
                    "--output",
                    str(result_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertTrue(result_path.exists())
            self.assertTrue(cli_manifest_output.exists())
            self.assertFalse((result_path.parent / f".{result_path.name}.tmp").exists())
            self.assertFalse((cli_manifest_output.parent / f".{cli_manifest_output.name}.tmp").exists())
            release_gate_result = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertEqual(release_gate_result["failed_stage_count"], 0)
            self.assertEqual(release_gate_result["stage_count"], release_gate_result["passed_stage_count"])

    def test_production_task_status_finalize_requires_strict_release_gate(self) -> None:
        audit = audit_production_tasks()
        plan = build_evidence_collection_plan(audit)
        base_manifest = json.loads(Path("artifacts/production-closure-manifest.example.json").read_text(encoding="utf-8"))
        package = json.loads(Path("artifacts/readiness-evidence-package.example.json").read_text(encoding="utf-8"))
        placeholder_inventory = self._production_artifact_inventory_for_contexts(package)
        with TemporaryDirectory() as tmpdir:
            todo_path = Path(tmpdir) / "todo.md"
            todo_path.write_text("- `BLOCKED` T-402 大样本中英双语 benchmark 执行\n  - 待做：真实 artifact URI 归档\n", encoding="utf-8")
            blocked = finalize_production_task_statuses(
                todo_path=todo_path,
                plan=plan,
                base_manifest=base_manifest,
                evidence_package=package,
                artifact_inventory=placeholder_inventory,
                task_ids=["T-402"],
                dry_run=True,
            )
            self.assertEqual(blocked["status"], "failed")
            self.assertEqual(blocked["failed_stage"], "production_release_gate")
            self.assertIn("`BLOCKED` T-402", todo_path.read_text(encoding="utf-8"))

            for row in plan["tasks"]:
                task_id = row["task_id"]
                row["status"] = "blocked_external_evidence"
                row["artifact_uri_template"] = {
                    field: f"s3://ai-quant-prod/evidence/finalize/{task_id}/{field}.json"
                    for field in row["artifact_fields"]
                }
            preview_manifest = build_manifest_from_evidence_plan(
                plan,
                base_manifest=base_manifest,
                evidence_package=package,
                release_ready=True,
            )
            inventory = self._production_artifact_inventory_for_contexts(plan, package, preview_manifest)
            passed = finalize_production_task_statuses(
                todo_path=todo_path,
                plan=plan,
                base_manifest=base_manifest,
                evidence_package=package,
                artifact_inventory=inventory,
                task_ids=["T-402"],
                dry_run=True,
            )
            self.assertEqual(passed["status"], "passed")
            self.assertEqual(passed["updated_task_ids"], ["T-402"])
            self.assertIn("`BLOCKED` T-402", todo_path.read_text(encoding="utf-8"))

            applied = finalize_production_task_statuses(
                todo_path=todo_path,
                plan=plan,
                base_manifest=base_manifest,
                evidence_package=package,
                artifact_inventory=inventory,
                task_ids=["T-402"],
            )
            self.assertEqual(applied["status"], "passed")
            updated = todo_path.read_text(encoding="utf-8")
            self.assertIn("`DONE` T-402", updated)
            self.assertIn("release gate 已通过", updated)
            self.assertFalse((todo_path.parent / f".{todo_path.name}.tmp").exists())

            cli_todo_path = Path(tmpdir) / "todo-cli.md"
            cli_todo_path.write_text("- `BLOCKED` T-402 大样本中英双语 benchmark 执行\n", encoding="utf-8")
            plan_path = Path(tmpdir) / "finalize-plan.json"
            package_path = Path(tmpdir) / "finalize-package.json"
            inventory_path = Path(tmpdir) / "finalize-inventory.json"
            result_path = Path(tmpdir) / "finalize-result.json"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            package_path.write_text(json.dumps(package), encoding="utf-8")
            inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
            subprocess.run(
                [
                    sys.executable,
                    "scripts/production_task_status_finalize.py",
                    "--todo",
                    str(cli_todo_path),
                    "--plan",
                    str(plan_path),
                    "--evidence-package",
                    str(package_path),
                    "--artifact-inventory",
                    str(inventory_path),
                    "--task-id",
                    "T-402",
                    "--dry-run",
                    "--output",
                    str(result_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertTrue(result_path.exists())
            self.assertIn("`BLOCKED` T-402", cli_todo_path.read_text(encoding="utf-8"))
            self.assertFalse((result_path.parent / f".{result_path.name}.tmp").exists())

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
            "AI_QUANT_STAGING_CAPACITY_SIMULATE_THRESHOLD_MS",
            "AI_QUANT_LOCAL_PRODUCTION_SKIP_AI_ACCEPTANCE",
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
            "scripts/local_production_stack.sh",
            "scripts/staging_security_acceptance.py",
            "scripts/capacity_baseline.py",
            "scripts/ui_static_check.py",
            "scripts/ui_cross_browser_matrix_check.py",
            "scripts/readiness_evidence_package_check.py",
            "scripts/production_artifact_inventory_check.py",
            "scripts/production_closure_manifest_check.py",
            "scripts/production_evidence_plan_check.py",
            "scripts/production_evidence_plan_to_manifest.py",
            "scripts/production_release_gate.py",
            "scripts/production_closure.py",
            "scripts/project_completion_audit.py",
            "scripts/local_production_audit.py",
            "artifacts/production-task-closure-audit.json",
            "failed_requirement_ids",
            "blocked_requirement_ids",
            "blocked_external_evidence_task_ids",
            "stage_count",
            "failed_stage_count",
            "failed_stage_names",
            "skipped_mapping_count",
            "missing_readiness_check_count",
            "readiness-evidence-package-validation.json",
            "production-closure-manifest-validation.json",
            "production-evidence-plan-validation.json",
        ]:
            self.assertIn(fragment, runbook)
        readme = Path("README.md").read_text(encoding="utf-8")
        api_contracts = Path("docs/api-contracts.md").read_text(encoding="utf-8")
        for fragment in [
            "failed_requirement_ids",
            "blocked_requirement_ids",
            "open_requirement_ids",
            "needs_code_work_count",
            "blocked_external_evidence_count",
            "blocked_external_evidence_task_ids",
            "stage_count",
            "failed_stage_count",
            "failed_stage_names",
            "skipped_mapping_count",
            "missing_readiness_check_count",
            "artifacts/production-task-closure-audit.json",
            "readiness-evidence-package-validation.json",
            "production-closure-manifest-validation.json",
            "production-evidence-plan-validation.json",
        ]:
            self.assertIn(fragment, readme)
            if fragment not in {"artifacts/production-task-closure-audit.json", "production-evidence-plan-validation.json"}:
                self.assertIn(fragment, api_contracts)
        local_staging_stack = Path("scripts/local_staging_stack.sh").read_text(encoding="utf-8")
        for fragment in [
            "--capacity-simulate-threshold-ms",
            "AI_QUANT_HOST=\"${AI_QUANT_APP_HOST:-0.0.0.0}\"",
            "AI_QUANT_OBJECT_STORE_BACKEND=\"${AI_QUANT_APP_OBJECT_STORE_BACKEND:-s3}\"",
            "AI_QUANT_SEARCH_BACKEND=\"${AI_QUANT_APP_SEARCH_BACKEND:-opensearch}\"",
            "AI_QUANT_TDX_VIPDOC_PATH=\"${AI_QUANT_APP_TDX_VIPDOC_PATH:-/data/local/tdx/vipdoc}\"",
        ]:
            self.assertIn(fragment, local_staging_stack)
        local_production_stack = Path("scripts/local_production_stack.sh").read_text(encoding="utf-8")
        for fragment in [
            "AI_QUANT_STAGING_CAPACITY_DEFAULT_THRESHOLD_MS=\"${AI_QUANT_STAGING_CAPACITY_DEFAULT_THRESHOLD_MS:-5000}\"",
            "AI_QUANT_STAGING_CAPACITY_SIMULATE_THRESHOLD_MS=\"${AI_QUANT_STAGING_CAPACITY_SIMULATE_THRESHOLD_MS:-5000}\"",
            "AI_QUANT_S3_HOST_PORT=\"${AI_QUANT_S3_HOST_PORT:-19000}\"",
            "scripts/local_production_audit.py",
            "scripts/local_ai_capability_acceptance.py",
        ]:
            self.assertIn(fragment, local_production_stack)
        dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
        self.assertIn("COPY scripts ./scripts", dockerfile)
        self.assertIn("pip install", dockerfile)
        self.assertIn(".[postgres,market-data]", dockerfile)
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

    def test_latency_audit_script_wraps_daily_pipeline_http_probes(self) -> None:
        captured = {}

        def fake_latency(base_url, *, output, threshold_ms, timeout):
            captured.update(
                {
                    "base_url": base_url,
                    "output": Path(output),
                    "threshold_ms": threshold_ms,
                    "timeout": timeout,
                }
            )
            Path(output).write_text(json.dumps({"status": "passed", "passed": True}), encoding="utf-8")
            return {"status": "passed", "passed": True, "failure_count": 0}

        original_latency = latency_audit_script._latency_audit
        try:
            latency_audit_script._latency_audit = fake_latency  # type: ignore[assignment]
            with TemporaryDirectory() as tmpdir:
                output_path = Path(tmpdir) / "latency.json"
                result = latency_audit_script.run_latency_audit(
                    base_url="http://127.0.0.1:8000",
                    output=output_path,
                    max_ms=7000.0,
                    timeout=3.0,
                )
        finally:
            latency_audit_script._latency_audit = original_latency  # type: ignore[assignment]

        self.assertTrue(result["passed"])
        self.assertEqual(captured["base_url"], "http://127.0.0.1:8000")
        self.assertEqual(captured["threshold_ms"], 7000.0)
        self.assertEqual(captured["timeout"], 3.0)
        self.assertEqual(captured["output"].name, "latency.json")

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
        self.assertTrue(checks["ui_browser_acceptance"]["passed"])
        self.assertEqual(checks["ui_browser_acceptance"]["evidence"]["status"], "passed")
        self.assertTrue(all(item["nonblank"] for item in checks["ui_browser_acceptance"]["evidence"]["screenshots"]))
        self.assertGreaterEqual(len(result["readiness_records"]), 3)
        readiness_ids = {item["check_id"] for item in result["readiness_records"] if "check_id" in item}
        self.assertIn("real_data_smoke_test", readiness_ids)
        self.assertIn("production_ui_screenshot_acceptance", readiness_ids)
        self.assertNotIn("cross_browser_acceptance", readiness_ids)
        self.assertIsNotNone(result["notifications"])
        self.assertIsNotNone(result["evidence_package_validation"])
        self.assertFalse(result["evidence_package_validation"]["passed"])
        validation_checks = {item["check"] for item in result["evidence_package_validation"]["failures"]}
        self.assertIn("package_status", validation_checks)
        self.assertIn("external_validation_ready", validation_checks)
        self.assertIn("required_evidence_uri", validation_checks)
        self.assertEqual(result["production_boundary"], "does_not_enable_live_broker_or_automatic_order_execution")

    def test_staging_acceptance_records_cross_browser_only_with_external_matrix(self) -> None:
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
                notify_missing=False,
                timeout=5,
                cross_browser_matrix={
                    "status": "passed",
                    "evidence_uri": "artifact://staging-test/ui-browser-matrix.json",
                    "browser_matrix": [
                        {"browser": "chromium", "viewport": "desktop", "status": "passed"},
                        {"browser": "firefox", "viewport": "mobile", "status": "passed"},
                    ],
                    "browsers_checked": ["chromium", "firefox"],
                    "viewports_checked": ["desktop", "mobile"],
                    "failure_count": 0,
                },
                env={
                    "AI_QUANT_POSTGRES_DSN": f"postgresql://app:secret@127.0.0.1:{server.server_port}/ai_quant",
                    "AI_QUANT_S3_BUCKET": "ai-quant-staging",
                    "AI_QUANT_S3_ENDPOINT": local_url,
                    "AI_QUANT_OPENSEARCH_URL": local_url,
                },
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
        self.assertEqual(result["status"], "passed")
        checks = {item["check"]: item for item in result["checks"]}
        self.assertTrue(checks["cross_browser_matrix_record"]["passed"])
        self.assertTrue(checks["cross_browser_matrix_record"]["evidence"]["metrics"]["validation"]["passed"])
        readiness_ids = {item["check_id"] for item in result["readiness_records"] if "check_id" in item}
        self.assertIn("cross_browser_acceptance", readiness_ids)

    def test_staging_lineage_registry_acceptance_posts_to_local_sinks(self) -> None:
        import app.server as server_module

        server_module.ROUTER = ApiRouter(SystemService())
        app_server = ThreadingHTTPServer(("127.0.0.1", 0), server_module.Handler)
        app_thread = threading.Thread(target=app_server.serve_forever, daemon=True)
        app_thread.start()

        class _SinkServer(ThreadingHTTPServer):
            pass

        from scripts.local_http_sink import make_handler, SinkStore
        openlineage_store = SinkStore(name="openlineage")
        mlflow_store = SinkStore(name="mlflow")
        openlineage_server = _SinkServer(("127.0.0.1", 0), make_handler(openlineage_store))
        mlflow_server = _SinkServer(("127.0.0.1", 0), make_handler(mlflow_store))
        openlineage_thread = threading.Thread(target=openlineage_server.serve_forever, daemon=True)
        mlflow_thread = threading.Thread(target=mlflow_server.serve_forever, daemon=True)
        openlineage_thread.start()
        mlflow_thread.start()
        try:
            result = run_staging_lineage_registry_acceptance(
                base_url=f"http://127.0.0.1:{app_server.server_port}",
                openlineage_target=f"http://127.0.0.1:{openlineage_server.server_port}/openlineage",
                mlflow_target=f"http://127.0.0.1:{mlflow_server.server_port}/mlflow",
                artifact_prefix="artifact://staging-test",
                timeout=5,
            )
        finally:
            openlineage_server.shutdown()
            mlflow_server.shutdown()
            app_server.shutdown()
            openlineage_server.server_close()
            mlflow_server.server_close()
            app_server.server_close()
            openlineage_thread.join(timeout=5)
            mlflow_thread.join(timeout=5)
            app_thread.join(timeout=5)
        self.assertEqual(result["status"], "passed")
        checks = {item["check"]: item for item in result["checks"]}
        self.assertTrue(checks["lineage_model_seed"]["passed"])
        self.assertTrue(checks["openlineage_failed_delivery_recorded"]["passed"])
        self.assertTrue(checks["openlineage_webhook_sender"]["passed"])
        self.assertTrue(checks["mlflow_failed_delivery_recorded"]["passed"])
        self.assertTrue(checks["mlflow_webhook_sender"]["passed"])
        self.assertGreaterEqual(len(openlineage_store.records), 1)
        self.assertGreaterEqual(len(mlflow_store.records), 1)
        self.assertEqual(openlineage_store.records[0]["service"], "openlineage")
        self.assertEqual(mlflow_store.records[0]["service"], "mlflow")

    def test_staging_security_acceptance_records_kms_and_lifecycle_evidence(self) -> None:
        import app.server as server_module

        server_module.ROUTER = ApiRouter(SystemService())
        server = ThreadingHTTPServer(("127.0.0.1", 0), server_module.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            result = run_staging_security_acceptance(
                base_url=f"http://127.0.0.1:{server.server_port}",
                artifact_prefix="artifact://staging-test",
                secret_manager_provider="local-development-metadata-only",
                timeout=5,
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
        self.assertEqual(result["status"], "passed")
        checks = {item["check"]: item for item in result["checks"]}
        self.assertTrue(checks["secret_rotation_metadata_only"]["passed"])
        self.assertTrue(checks["source_provenance_ledger"]["passed"])
        self.assertTrue(checks["least_privilege_storage_policy"]["passed"])
        self.assertTrue(checks["cache_retention_external_delete_evidence"]["passed"])
        self.assertEqual(checks["cache_retention_external_delete_evidence"]["evidence"]["evidence"]["status"], "executed_outside_app")
        self.assertTrue(checks["audit_completeness"]["passed"])
        self.assertTrue(checks["data_security_no_findings"]["passed"])

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
            "research, evidence, simulated portfolio, and human review workflow only",
        ]:
            self.assertIn(fragment, memo)

    # ------------------------------------------------------------------
    # T-403: TDX symbol/market/date schema enhancement tests
    # ------------------------------------------------------------------

    def test_tdx_symbol_schema_normalization(self) -> None:
        """T-403: _normalize_tdx_symbol handles all real-world A-share symbol formats."""
        svc = SystemService()

        cases = [
            # (raw_input, expected_normalized)
            ("600000", "600000"),
            ("sh600000", "600000"),
            ("SH600000", "600000"),
            ("600000.SH", "600000"),
            ("600000.SS", "600000"),      # Reuters/Refinitiv
            ("600000.XSHG", "600000"),    # ISO MIC
            ("000001", "000001"),
            ("sz000001", "000001"),
            ("000001.SZ", "000001"),
            ("000001.SZE", "000001"),
            ("000001.XSHE", "000001"),
            ("430047.BJ", "430047"),
            ("bj430047", "430047"),
            # ISIN-style
            ("CN0000000001", "000001"),
            ("CN0006000007", "000007"),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                normalized = svc._normalize_tdx_symbol(raw)
                self.assertEqual(normalized, expected, f"normalize_tdx_symbol({raw!r}) expected {expected!r}, got {normalized!r}")

    def test_tdx_market_from_symbol_inference(self) -> None:
        """T-403: _tdx_market_from_symbol correctly infers 'A' market for A-share formats."""
        svc = SystemService()
        a_share_cases = [
            "sh600000", "sz000001", "bj430047",
            "600000.SH", "000001.SZ", "430047.BJ",
            "600000.SS", "600000.XSHG", "000001.XSHE",
            "600000",  # bare 6-digit
        ]
        for sym in a_share_cases:
            with self.subTest(sym=sym):
                self.assertEqual(svc._tdx_market_from_symbol(sym), "A")

        # Non-A-share patterns should return empty string
        non_a = ["AAPL", "0700.HK", "US12345678", ""]
        for sym in non_a:
            with self.subTest(sym=sym):
                market = svc._tdx_market_from_symbol(sym)
                self.assertNotEqual(market, "A", f"Expected non-A for {sym!r}, got {market!r}")

    def test_resolve_tdx_security_supports_multiple_schemas(self) -> None:
        """T-403: _resolve_tdx_security resolves security via ticker, ISIN, and explicit map."""
        svc = SystemService()
        svc.seed_default_sources()
        # Register an issuer and security
        issuer = svc.register_issuer({"issuer_id": "test_issuer_tdx", "legal_name": "TDX Test Co", "country": "CN"})
        security = svc.register_security({
            "issuer_id": issuer.issuer_id,
            "security_id": "000001",
            "ticker": "000001",
            "isin": "CNE000000001",
            "market": "A",
            "currency": "CNY",
            "security_type": "equity",
        })
        # Resolve via bare ticker
        resolved = svc._resolve_tdx_security("000001", {})
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.security_id, "000001")
        # Resolve via sz-prefixed format
        resolved2 = svc._resolve_tdx_security("sz000001", {})
        self.assertIsNotNone(resolved2)
        self.assertEqual(resolved2.security_id, "000001")
        # Resolve via explicit security_map
        resolved3 = svc._resolve_tdx_security("sh000001", {"sh000001": "000001"})
        self.assertIsNotNone(resolved3)
        self.assertEqual(resolved3.security_id, "000001")
        # Unknown symbol returns None
        resolved4 = svc._resolve_tdx_security("999999", {})
        self.assertIsNone(resolved4)

    # ------------------------------------------------------------------
    # T-416: A-share supplemental connector registry tests
    # ------------------------------------------------------------------

    def test_astock_supplemental_connector_registry_and_fetch(self) -> None:
        """T-416: AStockSupplementalRegistry lists connectors and service dispatches correctly."""
        from app.connectors import AStockSupplementalRegistry
        registry = AStockSupplementalRegistry()

        # All frozen free/public supplemental connectors must be present
        connector_ids = registry.list_ids()
        for expected_id in [
            "eastmoney_research",
            "cninfo_announcements",
            "tencent_valuation_snapshot",
            "ths_hot_topics",
            "baidu_concepts",
            "dragon_tiger_list",
            "unlock_calendar",
        ]:
            self.assertIn(expected_id, connector_ids)

        # Each connector exposes source_id and source_type
        for cid in connector_ids:
            connector = registry.get(cid)
            self.assertIsNotNone(connector)
            self.assertTrue(hasattr(connector, "source_id"))
            self.assertEqual(connector.source_type, "third_party_connector")

        # Service method validates missing connector_id
        svc = SystemService()
        from app.errors import ValidationError
        with self.assertRaises(ValidationError):
            svc.fetch_astock_supplemental_samples({})

        # Service method raises NotFoundError for unknown connector
        from app.errors import NotFoundError
        with self.assertRaises(NotFoundError):
            svc.fetch_astock_supplemental_samples({"connector_id": "unknown_connector_xyz"})

        # Tencent connector: empty symbols list returns empty (no HTTP call)
        tencent = registry.get("tencent_valuation_snapshot")
        results = tencent.fetch_samples(user_agent="test/1.0", limit=5, symbols=[])
        self.assertEqual(results, [])

        # Newly registered connectors should normalize supplied sample rows without network calls.
        sample_cases = {
            "ths_hot_topics": (
                {"sample_rows": [{"title": "AI 热点扩散", "topic": "AI", "reason": "资金关注", "published_at": "2026-05-15"}]},
                "hot_topic",
            ),
            "baidu_concepts": (
                {"sample_rows": [{"name": "AI 产业链", "block_type": "concept", "desc": "概念板块", "published_at": "2026-05-15"}]},
                "concept_block",
            ),
            "dragon_tiger_list": (
                {"sample_rows": [{"security_code": "600000", "security_name": "浦发银行", "trade_date": "2026-05-15", "reason": "龙虎榜上榜"}]},
                "dragon_tiger_record",
            ),
            "unlock_calendar": (
                {"sample_rows": [{"security_code": "600000", "security_name": "浦发银行", "event_date": "2026-05-15", "unlock_shares": 1000000}]},
                "unlock_calendar",
            ),
        }
        for connector_id, (kwargs, document_type) in sample_cases.items():
            with self.subTest(connector_id=connector_id):
                connector = registry.get(connector_id)
                self.assertIsNotNone(connector)
                rows = connector.fetch_samples(user_agent="test/1.0", limit=5, **kwargs)
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0].document_type, document_type)
                self.assertFalse(rows[0].metadata["automation_allowed"])
                self.assertIn("manual_reference", rows[0].metadata["source_boundary"])

        for connector_id, sample_rows in {
            "eastmoney_research": [{"title": "Demo eastmoney research", "url": "https://example.invalid/eastmoney?token=secret", "published_at": "2026-05-15"}],
            "cninfo_announcements": [{"announcementTitle": "Demo cninfo announcement", "announcementId": "001", "adjunctUrl": "https://example.invalid/cninfo?api_key=secret"}],
            "tencent_valuation_snapshot": [{"symbol": "sz000001", "security_name": "平安银行", "close": 10.2, "pe_ttm": 12.3, "pb": 1.2}],
        }.items():
            with self.subTest(sample_connector=connector_id):
                connector = registry.get(connector_id)
                self.assertIsNotNone(connector)
                rows = connector.fetch_samples(user_agent="test/1.0", limit=5, sample_rows=sample_rows)
                self.assertEqual(len(rows), 1)
                self.assertFalse(rows[0].metadata["automation_allowed"])
                self.assertIn("manual_reference", rows[0].metadata["source_boundary"])

        supplemental = self.router.dispatch(
            "POST",
            "/api/connectors/astock/supplemental/fetch",
            {
                "connector_id": "dragon_tiger_list",
                "sample_rows": [
                    {
                        "security_code": "600000",
                        "security_name": "浦发银行",
                        "trade_date": "2026-05-15",
                        "reason": "龙虎榜上榜",
                        "source_uri": "https://example.invalid/dragon?t=1&token=secret",
                    }
                ],
            },
            actor="data",
            role="data_engineer",
        )
        self.assertTrue(supplemental.success, supplemental.error)
        self.assertEqual(supplemental.data["count"], 1)
        supplemental_doc = supplemental.data["documents"][0]
        self.assertEqual(supplemental_doc["document_type"], "dragon_tiger_record")
        self.assertEqual(supplemental_doc["source_id"], "dragon_tiger_list")
        self.assertFalse(supplemental_doc["metadata"]["automation_allowed"])
        self.assertEqual(supplemental_doc["source_uri"], "https://example.invalid/dragon?t=1")
        self.assertIn("manual_reference", supplemental_doc["metadata"]["source_boundary"])

    def test_astock_supplemental_connector_documents_are_manual_reference(self) -> None:
        """T-416: All supplemental connector documents carry automation_allowed=False and source_boundary."""
        from app.connectors import EastMoneyResearchConnector
        connector = EastMoneyResearchConnector()
        # Simulate normalize with a fake raw row
        doc = connector.normalize({
            "infoCode": "test001",
            "title": "测试研报",
            "publishDate": "2025-01-01",
            "orgName": "某券商",
            "stockCode": "600000",
        })
        self.assertEqual(doc.document_type, "research")
        self.assertEqual(doc.source_id, "eastmoney_research")
        self.assertFalse(doc.metadata["automation_allowed"])
        self.assertIn("manual_reference", doc.metadata["source_boundary"])
        self.assertEqual(doc.metadata["allowed_use"], ["manual_reference", "supplemental_research"])

    # ------------------------------------------------------------------
    # T-408: Portfolio attribution backfill tests
    # ------------------------------------------------------------------

    def test_portfolio_attribution_backfill_dry_run(self) -> None:
        """T-408: portfolio_attribution_backfill dry_run returns attribution without mutating reports."""
        svc = SystemService()
        svc.seed_default_sources()
        issuer = svc.register_issuer({"issuer_id": "issuer_attr_1", "legal_name": "Attr Co 1", "country": "CN"})
        sec1 = svc.register_security({
            "issuer_id": issuer.issuer_id, "security_id": "sec_attr_1",
            "ticker": "ATTR1", "market": "A", "currency": "CNY", "security_type": "equity",
        })
        sec2 = svc.register_security({
            "issuer_id": issuer.issuer_id, "security_id": "sec_attr_2",
            "ticker": "ATTR2", "market": "A", "currency": "CNY", "security_type": "equity",
        })
        # Register market data points
        for security_id, close_val in [("sec_attr_1", 10.0), ("sec_attr_2", 20.0)]:
            svc.register_market_data_point({
                "security_id": security_id,
                "source_id": "public_eod_market_data",
                "as_of_date": "2025-01-02",
                "market": "A",
                "data_type": "eod",
                "currency": "CNY",
                "open": close_val, "high": close_val * 1.01,
                "low": close_val * 0.99, "close": close_val,
                "adjusted_close": close_val, "volume": 100000.0,
            })
            svc.register_market_data_point({
                "security_id": security_id,
                "source_id": "public_eod_market_data",
                "as_of_date": "2025-01-03",
                "market": "A",
                "data_type": "eod",
                "currency": "CNY",
                "open": close_val * 1.02, "high": close_val * 1.03,
                "low": close_val * 1.01, "close": close_val * 1.02,
                "adjusted_close": close_val * 1.02, "volume": 100000.0,
            })
        holdings = [
            {"security_id": "sec_attr_1", "weight": 0.6},
            {"security_id": "sec_attr_2", "weight": 0.4},
        ]
        result = svc.portfolio_attribution_backfill({
            "holdings": holdings,
            "start_date": "2025-01-01",
            "end_date": "2025-01-31",
            "dry_run": True,
        })
        # dry_run should compute attribution but not annotate any reports
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["annotated_count"], 0)
        self.assertTrue(result["simulation_only"])
        self.assertFalse(result["live_execution_allowed"])
        self.assertIn("attribution", result)

    # ------------------------------------------------------------------
    # T-409: Portfolio simulated feedback / investment committee tests
    # ------------------------------------------------------------------

    def test_portfolio_simulated_feedback_committee_decision(self) -> None:
        """T-409: portfolio_simulated_feedback records committee decision and stays simulation-only."""
        svc = SystemService()
        svc.seed_default_sources()
        issuer = svc.register_issuer({"issuer_id": "issuer_ic_1", "legal_name": "IC Test Co", "country": "CN"})
        sec = svc.register_security({
            "issuer_id": issuer.issuer_id, "security_id": "sec_ic_1",
            "ticker": "IC1", "market": "A", "currency": "CNY", "security_type": "equity",
        })
        svc.register_market_data_point({
            "security_id": "sec_ic_1",
            "source_id": "public_eod_market_data",
            "as_of_date": "2025-06-01",
            "market": "A", "data_type": "eod", "currency": "CNY",
            "open": 15.0, "high": 15.5, "low": 14.8, "close": 15.2,
            "adjusted_close": 15.2, "volume": 200000.0,
        })
        # Create a portfolio proposal
        proposal = svc.run_portfolio_optimizer({
            "securities": [{"security_id": "sec_ic_1", "market_weight": 1.0, "volatility": 0.2}],
            "views": [{"security_id": "sec_ic_1", "expected_return": 0.12, "confidence": 0.8, "evidence_ids": []}],
            "risk_budget": {"max_position": 1.0},
        })
        # Investment committee review
        feedback = svc.portfolio_simulated_feedback({
            "proposal_id": proposal.proposal_id,
            "decision": "approved",
            "rationale": "Strong evidence, fits risk budget.",
            "committee_member": "cio",
            "include_valuation": False,
        })
        self.assertEqual(feedback["decision"], "approved")
        self.assertEqual(feedback["proposal_status"], "paper")
        self.assertTrue(feedback["simulation_only"])
        self.assertFalse(feedback["live_execution_allowed"])
        self.assertFalse(feedback["automation_allowed"])
        self.assertIn("paper_portfolio_simulation", feedback["usage_boundary"])

        # Reject scenario
        proposal2 = svc.run_portfolio_optimizer({
            "securities": [{"security_id": "sec_ic_1", "market_weight": 1.0, "volatility": 0.3}],
            "views": [{"security_id": "sec_ic_1", "expected_return": 0.05, "confidence": 0.5, "evidence_ids": []}],
        })
        feedback2 = svc.portfolio_simulated_feedback({
            "proposal_id": proposal2.proposal_id,
            "decision": "rejected",
            "rationale": "Insufficient evidence.",
            "committee_member": "risk_officer",
        })
        self.assertEqual(feedback2["decision"], "rejected")
        self.assertEqual(feedback2["proposal_status"], "rejected")

        # Validation: missing proposal_id raises
        from app.errors import ValidationError
        with self.assertRaises(ValidationError):
            svc.portfolio_simulated_feedback({})

        # Validation: unknown proposal raises
        from app.errors import NotFoundError
        with self.assertRaises(NotFoundError):
            svc.portfolio_simulated_feedback({"proposal_id": "nonexistent_proposal_xxx"})


if __name__ == "__main__":
    unittest.main()
