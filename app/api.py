from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
import json
import re

from .errors import AppError, ComplianceGateError, ConflictError, NotFoundError, PermissionDenied, ValidationError
from .services import SystemService
from .utils import new_id, to_plain


ROLE_ALIASES = {
    "ceo": "CEO",
    "cio": "CIO",
    "pm": "PM",
    "risk_compliance": "风险/合规",
    "compliance": "风险/合规",
    "platform": "平台负责人",
    "analyst": "分析师",
    "data_engineer": "数据工程",
    "data": "数据工程",
    "nlp_ml": "NLP/ML 负责人",
    "overseas_research": "海外研究负责人",
}

CANONICAL_ROLES = [
    "system",
    "CEO",
    "CIO",
    "PM",
    "风险/合规",
    "平台负责人",
    "分析师",
    "数据工程",
    "NLP/ML 负责人",
    "海外研究负责人",
]

PERMISSION_POLICY_CATALOG: list[dict[str, Any]] = [
    {
        "rule_id": "system_health",
        "path_prefixes": ["/api/health", "/api/metrics"],
        "sample_paths": {"GET": "/api/health"},
        "methods": ["GET"],
        "actions": {"GET": "read"},
        "data_domains": ["system_health", "ops_metrics"],
        "sensitivity": "green",
    },
    {
        "rule_id": "observability",
        "path_prefixes": ["/api/observability"],
        "sample_paths": {"GET": "/api/observability/logs/export", "POST": "/api/observability/otel/submit"},
        "methods": ["GET", "POST"],
        "actions": {"GET": "read", "POST": "execute"},
        "data_domains": ["observability", "ops_logs", "telemetry"],
        "sensitivity": "yellow",
    },
    {
        "rule_id": "dashboard",
        "path_prefixes": ["/api/dashboard"],
        "sample_paths": {"GET": "/api/dashboard/ceo"},
        "methods": ["GET"],
        "actions": {"GET": "read"},
        "data_domains": ["dashboard", "risk_dashboard"],
        "sensitivity": "yellow",
    },
    {
        "rule_id": "readiness",
        "path_prefixes": ["/api/readiness"],
        "sample_paths": {"GET": "/api/readiness/checklist", "POST": "/api/readiness/checklist"},
        "methods": ["GET", "POST"],
        "actions": {"GET": "read", "POST": "write"},
        "data_domains": ["readiness", "production_governance"],
        "sensitivity": "yellow",
    },
    {
        "rule_id": "governance_security",
        "path_prefixes": ["/api/governance"],
        "sample_paths": {"GET": "/api/governance/data-security-report", "POST": "/api/governance/secret-rotations"},
        "methods": ["GET", "POST"],
        "actions": {"GET": "read", "POST": "write"},
        "data_domains": ["source_governance", "audit", "security", "secrets"],
        "sensitivity": "red",
    },
    {
        "rule_id": "demo_seed",
        "path_prefixes": ["/api/demo"],
        "sample_paths": {"POST": "/api/demo/full-flow"},
        "methods": ["POST"],
        "actions": {"POST": "execute"},
        "data_domains": ["demo"],
        "sensitivity": "yellow",
    },
    {
        "rule_id": "market_data",
        "path_prefixes": ["/api/market-data"],
        "sample_paths": {"GET": "/api/market-data", "POST": "/api/market-data/points"},
        "methods": ["GET", "POST"],
        "actions": {"GET": "read", "POST": "write"},
        "data_domains": ["public_market_data"],
        "sensitivity": "yellow",
    },
    {
        "rule_id": "corporate_actions",
        "path_prefixes": ["/api/corporate-actions"],
        "sample_paths": {"GET": "/api/corporate-actions", "POST": "/api/corporate-actions"},
        "methods": ["GET", "POST"],
        "actions": {"GET": "read", "POST": "write"},
        "data_domains": ["corporate_actions"],
        "sensitivity": "yellow",
    },
    {
        "rule_id": "institutional_holdings",
        "path_prefixes": ["/api/13f"],
        "sample_paths": {"GET": "/api/13f/holdings", "POST": "/api/13f/holdings"},
        "methods": ["GET", "POST"],
        "actions": {"GET": "read", "POST": "write"},
        "data_domains": ["institutional_holdings"],
        "sensitivity": "yellow",
    },
    {
        "rule_id": "disclosure_events",
        "path_prefixes": ["/api/disclosure-events"],
        "sample_paths": {"GET": "/api/disclosure-events", "POST": "/api/disclosure-events"},
        "methods": ["GET", "POST"],
        "actions": {"GET": "read", "POST": "write"},
        "data_domains": ["public_disclosures", "event_wall"],
        "sensitivity": "yellow",
    },
    {
        "rule_id": "data_ingestion",
        "path_prefixes": ["/api/ingestion", "/api/entity-mappings", "/api/connectors"],
        "sample_paths": {"POST": "/api/ingestion/documents"},
        "methods": ["POST"],
        "actions": {"POST": "write"},
        "data_domains": ["ingestion", "source_registry", "entity_mapping", "connectors"],
        "sensitivity": "red",
    },
    {
        "rule_id": "benchmark_prompt_governance",
        "path_prefixes": ["/api/benchmarks", "/api/prompts/changes", "/api/scorecards"],
        "sample_paths": {"GET": "/api/benchmarks/bm_default/samples", "POST": "/api/benchmarks"},
        "methods": ["GET", "POST"],
        "actions": {"GET": "read", "POST": "write"},
        "data_domains": ["benchmark", "prompt_governance", "scoring"],
        "sensitivity": "yellow",
    },
    {
        "rule_id": "research_workbench",
        "path_prefixes": [
            "/api/templates",
            "/api/research-cards",
            "/api/research-reports",
            "/api/research/manual-references",
            "/api/research/answers",
            "/api/research/tasks",
            "/api/macro-themes",
            "/api/industry-chains",
            "/api/company-profiles",
            "/api/company-financial-metrics",
            "/api/company-events",
            "/api/company-relationships",
            "/api/research-report-viewpoints",
            "/api/research-report-forecasts",
            "/api/analyst-profiles",
            "/api/analyst-reliability-scores",
            "/api/observation-items",
            "/api/analysis-conclusions",
            "/api/simulation-feedback",
            "/api/hotspot-lexicons",
            "/api/hotspots",
            "/api/crowding",
            "/api/challenger",
            "/api/playbooks",
            "/api/incident-reports",
            "/api/drill-schedules",
            "/api/alerts",
        ],
        "sample_paths": {"GET": "/api/research-reports", "POST": "/api/research/answers"},
        "methods": ["GET", "POST"],
        "actions": {"GET": "read", "POST": "write"},
        "data_domains": ["research", "macro_themes", "industry_chain", "manual_reference", "alerts", "incidents"],
        "sensitivity": "yellow",
    },
    {
        "rule_id": "llm_gateway",
        "path_prefixes": ["/api/llm"],
        "sample_paths": {"GET": "/api/llm/tasks/runs", "POST": "/api/llm/tasks/run"},
        "methods": ["GET", "POST"],
        "actions": {"GET": "read", "POST": "execute"},
        "data_domains": ["llm_gateway", "prompt_templates", "model_usage"],
        "sensitivity": "red",
    },
    {
        "rule_id": "orchestration_lineage_models",
        "path_prefixes": ["/api/orchestration", "/api/lineage", "/api/model-versions"],
        "sample_paths": {"GET": "/api/orchestration/runs", "POST": "/api/orchestration/dags"},
        "methods": ["GET", "POST"],
        "actions": {"GET": "read", "POST": "execute"},
        "data_domains": ["orchestration", "lineage", "model_registry"],
        "sensitivity": "yellow",
    },
    {
        "rule_id": "document_parsing",
        "path_prefixes": ["/api/document-parsing"],
        "sample_paths": {"POST": "/api/document-parsing/paddleocr"},
        "methods": ["POST"],
        "actions": {"POST": "execute"},
        "data_domains": ["document_parsing", "ocr"],
        "sensitivity": "yellow",
    },
    {
        "rule_id": "evidence_research_facts",
        "path_prefixes": ["/api/evidence", "/api/extractions", "/api/thesis", "/api/scoring"],
        "sample_paths": {"GET": "/api/evidence/manual-reviews", "POST": "/api/evidence/extract"},
        "methods": ["GET", "POST"],
        "actions": {"GET": "read", "POST": "write"},
        "data_domains": ["evidence", "structured_extraction", "thesis"],
        "sensitivity": "yellow",
    },
    {
        "rule_id": "investment_committee",
        "path_prefixes": ["/api/decision-packs", "/api/approvals", "/api/exceptions"],
        "sample_paths": {"GET": "/api/decision-packs/dec_sample", "POST": "/api/decision-packs/build"},
        "methods": ["GET", "POST"],
        "actions": {"GET": "read", "POST": "approve"},
        "data_domains": ["investment_decisions", "approvals", "exceptions"],
        "sensitivity": "red",
    },
    {
        "rule_id": "execution_intents",
        "path_prefixes": ["/api/execution-intents", "/api/simulated-executions"],
        "sample_paths": {"GET": "/api/execution-intents/intent_sample", "POST": "/api/execution-intents"},
        "methods": ["GET", "POST"],
        "actions": {"GET": "read", "POST": "approve"},
        "data_domains": ["execution_intent", "simulated_execution"],
        "sensitivity": "red",
    },
    {
        "rule_id": "portfolio_research",
        "path_prefixes": ["/api/portfolio"],
        "sample_paths": {"GET": "/api/portfolio/proposals", "POST": "/api/portfolio/optimize"},
        "methods": ["GET", "POST"],
        "actions": {"GET": "read", "POST": "write"},
        "data_domains": ["portfolio_research", "paper_portfolio", "risk_budget"],
        "sensitivity": "yellow",
    },
    {
        "rule_id": "operating_reviews_graph_search",
        "path_prefixes": ["/api/reviews", "/api/operating-reports", "/api/strategy-replays", "/api/graph", "/api/search", "/api/company-intelligence", "/api/company-database"],
        "sample_paths": {"GET": "/api/graph/query", "POST": "/api/operating-reports"},
        "methods": ["GET", "POST"],
        "actions": {"GET": "read", "POST": "write"},
        "data_domains": ["operating_reports", "strategy_replay", "knowledge_graph", "search"],
        "sensitivity": "yellow",
    },
]


@dataclass(slots=True)
class ApiResponse:
    success: bool
    data: Any = None
    error: dict[str, Any] | None = None
    status_code: int = 200
    trace_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return to_plain(
            {
                "success": self.success,
                "data": self.data,
                "error": self.error,
                "trace_id": self.trace_id,
            }
        )


class ApiRouter:
    def __init__(self, service: SystemService | None = None):
        self.service = service or SystemService()

    def dispatch(self, method: str, path: str, body: dict[str, Any] | None = None, *, actor: str = "system", role: str = "system") -> ApiResponse:
        body = body or {}
        trace_id = new_id("trace")
        role = self._normalize_role(role)
        self.service.set_trace_id(trace_id)
        try:
            handler = self._resolve(method.upper(), path)
            if handler is None:
                raise NotFoundError(f"route not found: {method} {path}")
            if not self._authorize(method.upper(), path, role):
                self.service.record_permission_denied(method.upper(), path, role=role, actor=actor)
                raise PermissionDenied(f"role {role} is not allowed for {method} {path}")
            data = handler(path, body, actor=actor)
            return ApiResponse(success=True, data=data, error=None, status_code=200, trace_id=trace_id)
        except ValidationError as exc:
            return self._error(422, "validation_error", str(exc), trace_id)
        except PermissionDenied as exc:
            return self._error(403, "permission_denied", str(exc), trace_id)
        except ComplianceGateError as exc:
            return self._error(423, "compliance_gate", str(exc), trace_id)
        except ConflictError as exc:
            return self._error(409, "conflict", str(exc), trace_id)
        except NotFoundError as exc:
            return self._error(404, "not_found", str(exc), trace_id)
        except AppError as exc:
            return self._error(400, "app_error", str(exc), trace_id)
        except Exception as exc:  # pragma: no cover - safe fallback
            return self._error(500, "internal_error", str(exc), trace_id)
        finally:
            self.service.set_trace_id("")

    def _error(self, status_code: int, kind: str, message: str, trace_id: str) -> ApiResponse:
        return ApiResponse(success=False, data=None, error={"type": kind, "message": message}, status_code=status_code, trace_id=trace_id)

    def _normalize_role(self, role: str) -> str:
        return ROLE_ALIASES.get(str(role).strip().lower(), role)

    def _resolve(self, method: str, path: str) -> Callable[..., Any] | None:
        routes: list[tuple[str, str, Callable[..., Any]]] = [
            ("POST", r"^/api/ingestion/sources$", self._register_source),
            ("POST", r"^/api/ingestion/sources/seed$", self._seed_default_sources),
            ("GET", r"^/api/governance/sources/report$", self._source_governance_report),
            ("POST", r"^/api/governance/sources/report$", self._source_governance_report),
            ("GET", r"^/api/governance/audit-report$", self._audit_completeness_report),
            ("POST", r"^/api/governance/audit-report$", self._audit_completeness_report),
            ("GET", r"^/api/governance/data-security-report$", self._data_security_report),
            ("POST", r"^/api/governance/data-security-report$", self._data_security_report),
            ("GET", r"^/api/governance/security-readiness-report$", self._security_readiness_report),
            ("POST", r"^/api/governance/security-readiness-report$", self._security_readiness_report),
            ("GET", r"^/api/governance/permission-matrix$", self._permission_matrix),
            ("POST", r"^/api/governance/permission-matrix$", self._permission_matrix),
            ("GET", r"^/api/governance/storage-policy-templates$", self._storage_policy_templates),
            ("POST", r"^/api/governance/storage-policy-templates$", self._storage_policy_templates),
            ("GET", r"^/api/governance/storage-readiness-report$", self._storage_readiness_report),
            ("POST", r"^/api/governance/storage-readiness-report$", self._storage_readiness_report),
            ("GET", r"^/api/governance/secret-rotations$", self._secret_rotations),
            ("POST", r"^/api/governance/secret-rotations$", self._record_secret_rotation),
            ("GET", r"^/api/governance/cache-retention-report$", self._cache_retention_report),
            ("POST", r"^/api/governance/cache-retention-report$", self._cache_retention_report),
            ("GET", r"^/api/governance/cache-retention-runs$", self._cache_retention_runs),
            ("POST", r"^/api/governance/cache-retention-runs/(?P<run_id>[^/]+)/execute$", self._execute_cache_retention_run),
            ("POST", r"^/api/governance/cache-retention-runs/(?P<run_id>[^/]+)/execution-evidence$", self._record_cache_retention_execution_evidence),
            ("POST", r"^/api/governance/sources/(?P<source_id>[^/]+)$", self._update_source_governance),
            ("POST", r"^/api/governance/sources/(?P<source_id>[^/]+)/reviews$", self._record_source_review),
            ("GET", r"^/api/governance/source-reviews$", self._list_source_reviews),
            ("POST", r"^/api/governance/source-reviews$", self._list_source_reviews),
            ("GET", r"^/api/governance/source-review-reminders$", self._source_review_reminders),
            ("POST", r"^/api/governance/source-review-reminders$", self._source_review_reminders),
            ("GET", r"^/api/governance/source-review-escalations$", self._source_review_sla_escalations),
            ("POST", r"^/api/governance/source-review-escalations$", self._source_review_sla_escalations),
            ("POST", r"^/api/governance/source-review-escalations/notify$", self._notify_source_review_escalations),
            ("POST", r"^/api/demo/full-flow$", self._seed_demo_full_flow),
            ("GET", r"^/api/health$", self._health),
            ("GET", r"^/api/metrics$", self._metrics),
            ("GET", r"^/api/analysis/latest$", self._latest_analysis),
            ("GET", r"^/api/observability/logs/export$", self._structured_logs_export),
            ("POST", r"^/api/observability/logs/export$", self._structured_logs_export),
            ("GET", r"^/api/observability/otel/export$", self._opentelemetry_logs_export),
            ("POST", r"^/api/observability/otel/export$", self._opentelemetry_logs_export),
            ("POST", r"^/api/observability/otel/submit$", self._submit_opentelemetry_logs),
            ("GET", r"^/api/observability/readiness-report$", self._observability_readiness_report),
            ("POST", r"^/api/observability/readiness-report$", self._observability_readiness_report),
            ("POST", r"^/api/issuers$", self._register_issuer),
            ("POST", r"^/api/securities$", self._register_security),
            ("POST", r"^/api/market-data/points$", self._register_market_data_point),
            ("POST", r"^/api/market-data/batch$", self._register_market_data_batch),
            ("POST", r"^/api/market-data/tdx/preview$", self._tdx_market_data_preview),
            ("POST", r"^/api/market-data/tdx/import$", self._import_tdx_market_data),
            ("POST", r"^/api/market-data/backfill$", self._market_data_backfill),
            ("GET", r"^/api/market-data/backfill/coverage-report$", self._market_data_backfill_coverage_report),
            ("POST", r"^/api/market-data/backfill/coverage-report$", self._market_data_backfill_coverage_report),
            ("GET", r"^/api/market-data/schema-coverage-report$", self._market_data_schema_coverage_report),
            ("POST", r"^/api/market-data/schema-coverage-report$", self._market_data_schema_coverage_report),
            ("GET", r"^/api/market-data/quality-report$", self._market_data_quality_report),
            ("POST", r"^/api/market-data/quality-report$", self._market_data_quality_report),
            ("GET", r"^/api/market-data/adjusted$", self._adjusted_market_data),
            ("POST", r"^/api/market-data/adjusted$", self._adjusted_market_data),
            ("GET", r"^/api/market-data/returns$", self._market_data_returns),
            ("POST", r"^/api/market-data/returns$", self._market_data_returns),
            ("GET", r"^/api/market-data$", self._list_market_data),
            ("POST", r"^/api/corporate-actions$", self._register_corporate_action),
            ("GET", r"^/api/corporate-actions$", self._list_corporate_actions),
            ("POST", r"^/api/13f/filings/batch-parse$", self._parse_13f_information_table_batch),
            ("POST", r"^/api/13f/filings/parse$", self._parse_13f_information_table),
            ("GET", r"^/api/13f/filings/mapping-readiness$", self._13f_mapping_readiness_report),
            ("POST", r"^/api/13f/filings/mapping-readiness$", self._13f_mapping_readiness_report),
            ("POST", r"^/api/13f/holdings$", self._register_13f_holding),
            ("GET", r"^/api/13f/holdings/changes$", self._institutional_holding_changes),
            ("POST", r"^/api/13f/holdings/changes$", self._institutional_holding_changes),
            ("GET", r"^/api/13f/candidate-pool$", self._institutional_candidate_pool),
            ("POST", r"^/api/13f/candidate-pool$", self._institutional_candidate_pool),
            ("GET", r"^/api/13f/holdings$", self._list_13f_holdings),
            ("POST", r"^/api/13f/crowding/update$", self._update_crowding_from_13f),
            ("POST", r"^/api/disclosure-events$", self._create_disclosure_event),
            ("GET", r"^/api/disclosure-events/performance$", self._disclosure_event_performance_report),
            ("POST", r"^/api/disclosure-events/performance$", self._disclosure_event_performance_writeback),
            ("GET", r"^/api/disclosure-events$", self._list_disclosure_events),
            ("POST", r"^/api/disclosure-events/classify$", self._classify_disclosure_event),
            ("POST", r"^/api/entity-mappings$", self._register_entity_mapping),
            ("POST", r"^/api/entity-mappings/batch$", self._register_entity_mapping_batch),
            ("POST", r"^/api/entity-mappings/labels$", self._record_entity_mapping_label_batch),
            ("GET", r"^/api/entity-mappings/labels$", self._entity_mapping_labels),
            ("GET", r"^/api/entity-mappings/quality-report$", self._entity_mapping_quality_report),
            ("GET", r"^/api/entity-mappings/readiness-report$", self._entity_mapping_readiness_report),
            ("POST", r"^/api/entity-mappings/readiness-report$", self._entity_mapping_readiness_report),
            ("GET", r"^/api/entity-mappings$", self._list_entity_mappings),
            ("POST", r"^/api/connectors/astock/seed$", self._seed_astock_connectors),
            ("POST", r"^/api/connectors/astock$", self._register_astock_connector),
            ("GET", r"^/api/connectors/astock$", self._list_astock_connectors),
            ("POST", r"^/api/connectors/astock/query$", self._list_astock_connectors),
            ("POST", r"^/api/connectors/astock/verify$", self._verify_astock_connectors),
            ("GET", r"^/api/connectors/astock/verification-readiness$", self._astock_connector_verification_readiness),
            ("POST", r"^/api/connectors/astock/verification-readiness$", self._astock_connector_verification_readiness),
            ("POST", r"^/api/connectors/astock/fetch$", self._fetch_astock_connector_sample),
            ("POST", r"^/api/connectors/astock/supplemental/fetch$", self._fetch_astock_supplemental_samples),
            ("POST", r"^/api/connectors/preview$", self._preview_connector_document),
            ("POST", r"^/api/connectors/ashare/recent$", self._fetch_ashare_recent_filings),
            ("POST", r"^/api/connectors/sec/recent$", self._fetch_sec_recent_filings),
            ("POST", r"^/api/connectors/hkex/recent$", self._fetch_hkex_recent_filings),
            ("POST", r"^/api/ingestion/ashare/recent$", self._ingest_ashare_recent_filings),
            ("POST", r"^/api/ingestion/sec/recent$", self._ingest_sec_recent_filings),
            ("POST", r"^/api/ingestion/hkex/recent$", self._ingest_hkex_recent_filings),
            ("POST", r"^/api/ingestion/jobs$", self._run_ingestion_job),
            ("GET", r"^/api/ingestion/jobs/(?P<job_id>[^/]+)$", self._get_ingestion_job),
            ("POST", r"^/api/ingestion/schedules$", self._register_ingestion_schedule),
            ("POST", r"^/api/ingestion/schedules/run$", self._run_ingestion_schedules),
            ("GET", r"^/api/ingestion/schedules/(?P<schedule_id>[^/]+)$", self._get_ingestion_schedule),
            ("POST", r"^/api/ingestion/documents$", self._ingest_document),
            ("GET", r"^/api/ingestion/documents/(?P<document_id>[^/]+)$", self._get_document),
            ("POST", r"^/api/benchmarks$", self._register_benchmark),
            ("POST", r"^/api/benchmarks/(?P<benchmark_id>[^/]+)/samples$", self._register_benchmark_sample),
            ("GET", r"^/api/benchmarks/(?P<benchmark_id>[^/]+)/samples$", self._list_benchmark_samples),
            ("POST", r"^/api/benchmarks/(?P<benchmark_id>[^/]+)/run$", self._run_benchmark_suite),
            ("GET", r"^/api/benchmarks/(?P<benchmark_id>[^/]+)/readiness-report$", self._benchmark_readiness_report),
            ("POST", r"^/api/benchmarks/(?P<benchmark_id>[^/]+)/readiness-report$", self._benchmark_readiness_report),
            ("POST", r"^/api/benchmarks/(?P<benchmark_id>[^/]+)/evaluate$", self._evaluate_benchmark),
            ("GET", r"^/api/prompts/changes$", self._list_prompt_changes),
            ("POST", r"^/api/prompts/changes/query$", self._list_prompt_changes),
            ("POST", r"^/api/prompts/changes$", self._create_prompt_change),
            ("POST", r"^/api/prompts/changes/(?P<request_id>[^/]+)/approve$", self._approve_prompt_change),
            ("POST", r"^/api/templates$", self._register_template),
            ("POST", r"^/api/templates/seed$", self._seed_default_templates),
            ("POST", r"^/api/scorecards$", self._register_scorecard),
            ("POST", r"^/api/research-cards$", self._create_research_card),
            ("POST", r"^/api/research-reports/scan$", self._scan_research_reports),
            ("GET", r"^/api/research-reports/extraction-queue$", self._research_report_extraction_queue),
            ("POST", r"^/api/research-reports/extraction-queue$", self._research_report_extraction_queue),
            ("POST", r"^/api/research-reports/incremental-schedule$", self._research_report_incremental_schedule),
            ("GET", r"^/api/research-reports/governance-report$", self._research_report_governance_report),
            ("POST", r"^/api/research-reports/governance-report$", self._research_report_governance_report),
            ("GET", r"^/api/research-reports/mapping-report$", self._research_report_mapping_report),
            ("POST", r"^/api/research-reports/mapping-report$", self._research_report_mapping_report),
            ("GET", r"^/api/research-reports/viewpoint-report$", self._research_report_viewpoint_report),
            ("POST", r"^/api/research-reports/viewpoint-report$", self._research_report_viewpoint_report),
            ("POST", r"^/api/research-reports/structure$", self._structure_research_reports),
            ("POST", r"^/api/research-reports/realization/update$", self._update_research_report_realization),
            ("GET", r"^/api/research-reports$", self._list_research_reports),
            ("POST", r"^/api/research-reports$", self._list_research_reports),
            ("POST", r"^/api/research-reports/(?P<report_id>[^/]+)/ingest$", self._ingest_research_report),
            ("POST", r"^/api/research-reports/(?P<report_id>[^/]+)/extract$", self._extract_research_report),
            ("POST", r"^/api/research/manual-references$", self._create_manual_reference),
            ("GET", r"^/api/research/citation-boundary/readiness-report$", self._citation_boundary_readiness_report),
            ("POST", r"^/api/research/citation-boundary/readiness-report$", self._citation_boundary_readiness_report),
            ("POST", r"^/api/research/answers/filing-qa$", self._create_filing_qa_answer),
            ("POST", r"^/api/research/answers$", self._create_research_answer),
            ("GET", r"^/api/research/answers/quality-report$", self._research_answer_quality_report),
            ("POST", r"^/api/research/answers/quality-report$", self._research_answer_quality_report),
            ("GET", r"^/api/research/answers/summary-benchmark$", self._research_answer_summary_benchmark),
            ("POST", r"^/api/research/answers/summary-benchmark$", self._research_answer_summary_benchmark),
            ("GET", r"^/api/research/answers/readiness-report$", self._research_answer_readiness_report),
            ("POST", r"^/api/research/answers/readiness-report$", self._research_answer_readiness_report),
            ("POST", r"^/api/research/answers/(?P<answer_id>[^/]+)/review$", self._review_research_answer),
            ("GET", r"^/api/research/answers/(?P<answer_id>[^/]+)$", self._get_research_answer),
            ("POST", r"^/api/research/tasks/sec-single-name/run$", self._run_sec_single_name_research),
            ("GET", r"^/api/research/tasks$", self._list_research_tasks),
            ("POST", r"^/api/research/tasks$", self._register_research_task),
            ("POST", r"^/api/research/tasks/from-hotspot/batch$", self._create_research_tasks_from_hotspot_batch),
            ("POST", r"^/api/research/tasks/from-hotspot$", self._create_research_tasks_from_hotspot),
            ("POST", r"^/api/research/tasks/(?P<task_id>[^/]+)/status$", self._update_research_task_status),
            ("GET", r"^/api/chokepoint/readiness-report$", self._chokepoint_readiness_report),
            ("POST", r"^/api/chokepoint/readiness-report$", self._chokepoint_readiness_report),
            ("POST", r"^/api/chokepoint/runs$", self._create_chokepoint_research_run),
            ("GET", r"^/api/chokepoint/runs$", self._list_chokepoint_research_runs),
            ("POST", r"^/api/chokepoint/runs/query$", self._list_chokepoint_research_runs),
            ("GET", r"^/api/chokepoint/runs/(?P<run_id>[^/]+)$", self._get_chokepoint_research_run),
            ("POST", r"^/api/chokepoint/runs/(?P<run_id>[^/]+)/steps/(?P<step_id>[^/]+)/run$", self._run_chokepoint_research_step),
            ("POST", r"^/api/chokepoint/runs/(?P<run_id>[^/]+)/run$", self._run_chokepoint_research_pipeline),
            ("POST", r"^/api/chokepoint/runs/(?P<run_id>[^/]+)/finalize$", self._finalize_chokepoint_research_run),
            ("POST", r"^/api/chokepoint/runs/(?P<run_id>[^/]+)/review$", self._review_chokepoint_research_run),
            ("POST", r"^/api/chokepoint/runs/(?P<run_id>[^/]+)/verification-tasks$", self._create_chokepoint_verification_tasks),
            ("POST", r"^/api/extractions/run$", self._extract_structured_facts),
            ("GET", r"^/api/extractions/(?P<extraction_id>[^/]+)$", self._get_extraction_result),
            ("POST", r"^/api/evidence/extract$", self._extract_evidence),
            ("POST", r"^/api/document-parsing/paddleocr$", self._parse_document_with_paddleocr),
            ("GET", r"^/api/evidence/manual-reviews$", self._list_manual_reviews),
            ("GET", r"^/api/evidence/quality-report$", self._evidence_quality_report),
            ("POST", r"^/api/evidence/quality-report$", self._evidence_quality_report),
            ("POST", r"^/api/thesis/create$", self._create_thesis),
            ("GET", r"^/api/thesis/(?P<thesis_id>[^/]+)$", self._get_thesis),
            ("POST", r"^/api/scoring/run$", self._run_scoring),
            ("POST", r"^/api/crowding/snapshots$", self._register_crowding_snapshot),
            ("POST", r"^/api/challenger/run$", self._run_challenger),
            ("POST", r"^/api/playbooks/seed$", self._seed_default_playbooks),
            ("POST", r"^/api/playbooks$", self._register_playbook),
            ("POST", r"^/api/drill-schedules$", self._register_drill_schedule),
            ("POST", r"^/api/drill-schedules/(?P<schedule_id>[^/]+)/result$", self._record_drill_result),
            ("POST", r"^/api/incident-reports$", self._create_incident_report),
            ("POST", r"^/api/alerts/rules$", self._register_alert_rule),
            ("POST", r"^/api/alerts/rules/seed$", self._seed_default_alert_rules),
            ("POST", r"^/api/alerts/evaluate$", self._evaluate_alerts),
            ("POST", r"^/api/alerts/incidents/create$", self._create_incidents_from_alerts),
            ("POST", r"^/api/alerts/notify$", self._notify_alerts),
            ("POST", r"^/api/alerts/notifications/deliver$", self._deliver_alert_notifications),
            ("GET", r"^/api/alerts/notifications$", self._list_alert_notifications),
            ("GET", r"^/api/alerts$", self._list_alerts),
            ("POST", r"^/api/llm/task-templates/seed$", self._seed_llm_task_templates),
            ("POST", r"^/api/llm/task-templates$", self._register_llm_task_template),
            ("GET", r"^/api/llm/task-templates$", self._list_llm_task_templates),
            ("POST", r"^/api/llm/task-templates/query$", self._list_llm_task_templates),
            ("POST", r"^/api/llm/tasks/run$", self._run_llm_task),
            ("GET", r"^/api/llm/tasks/review-queue$", self._llm_task_review_queue),
            ("POST", r"^/api/llm/tasks/review-queue$", self._llm_task_review_queue),
            ("GET", r"^/api/llm/tasks/escalations$", self._llm_task_escalation_report),
            ("POST", r"^/api/llm/tasks/escalations$", self._llm_task_escalation_report),
            ("POST", r"^/api/llm/tasks/escalations/notify$", self._notify_llm_task_escalations),
            ("GET", r"^/api/llm/budget-approvals$", self._llm_budget_approvals),
            ("POST", r"^/api/llm/budget-approvals$", self._request_llm_budget_approval),
            ("POST", r"^/api/llm/budget-approvals/(?P<approval_id>[^/]+)/decide$", self._decide_llm_budget_approval),
            ("POST", r"^/api/llm/budget-approvals/(?P<approval_id>[^/]+)/sync$", self._sync_llm_budget_approval),
            ("GET", r"^/api/llm/readiness-report$", self._llm_readiness_report),
            ("POST", r"^/api/llm/readiness-report$", self._llm_readiness_report),
            ("GET", r"^/api/llm/tasks/runs$", self._list_llm_task_runs),
            ("POST", r"^/api/llm/tasks/runs$", self._list_llm_task_runs),
            ("GET", r"^/api/llm/tasks/metrics$", self._llm_task_metrics),
            ("POST", r"^/api/llm/openai/chat/completions$", self._llm_openai_chat_completions),
            ("POST", r"^/api/llm/anthropic/messages$", self._llm_anthropic_messages),
            ("POST", r"^/api/orchestration/dags$", self._register_workflow_definition),
            ("GET", r"^/api/orchestration/dags$", self._list_workflow_definitions),
            ("POST", r"^/api/orchestration/dags/query$", self._list_workflow_definitions),
            ("POST", r"^/api/orchestration/dags/(?P<dag_id>[^/]+)/backfill$", self._backfill_workflow_definition),
            ("POST", r"^/api/orchestration/dags/(?P<dag_id>[^/]+)/execute$", self._execute_workflow_definition),
            ("POST", r"^/api/orchestration/dags/(?P<dag_id>[^/]+)/run$", self._run_workflow_definition),
            ("POST", r"^/api/orchestration/runs/(?P<run_id>[^/]+)/retry$", self._retry_workflow_run),
            ("GET", r"^/api/orchestration/sla-report$", self._workflow_sla_report),
            ("POST", r"^/api/orchestration/sla-report$", self._workflow_sla_report),
            ("POST", r"^/api/orchestration/incidents/create$", self._create_workflow_incidents),
            ("GET", r"^/api/orchestration/schedule-calendar$", self._workflow_schedule_calendar),
            ("POST", r"^/api/orchestration/schedule-calendar$", self._workflow_schedule_calendar),
            ("GET", r"^/api/orchestration/scheduler-handoff$", self._workflow_scheduler_handoff),
            ("POST", r"^/api/orchestration/scheduler-handoff$", self._workflow_scheduler_handoff),
            ("GET", r"^/api/orchestration/readiness-report$", self._orchestration_readiness_report),
            ("POST", r"^/api/orchestration/readiness-report$", self._orchestration_readiness_report),
            ("GET", r"^/api/orchestration/dependency-graph$", self._workflow_dependency_graph),
            ("POST", r"^/api/orchestration/dependency-graph$", self._workflow_dependency_graph),
            ("GET", r"^/api/orchestration/openlineage/export$", self._workflow_openlineage_export),
            ("POST", r"^/api/orchestration/openlineage/export$", self._workflow_openlineage_export),
            ("POST", r"^/api/orchestration/openlineage/submit$", self._submit_openlineage_export),
            ("GET", r"^/api/orchestration/runs$", self._list_workflow_runs),
            ("POST", r"^/api/orchestration/runs$", self._list_workflow_runs),
            ("POST", r"^/api/lineage/events$", self._record_lineage_event),
            ("GET", r"^/api/lineage/events$", self._list_lineage_events),
            ("POST", r"^/api/lineage/events/query$", self._list_lineage_events),
            ("GET", r"^/api/model-versions/mlflow/export$", self._mlflow_model_registry_export),
            ("POST", r"^/api/model-versions/mlflow/export$", self._mlflow_model_registry_export),
            ("POST", r"^/api/model-versions/mlflow/register$", self._submit_mlflow_model_registry_export),
            ("POST", r"^/api/model-versions$", self._register_model_version),
            ("GET", r"^/api/model-versions$", self._list_model_versions),
            ("POST", r"^/api/model-versions/query$", self._list_model_versions),
            ("GET", r"^/api/signals/(?P<signal_id>[^/]+)$", self._get_signal),
            ("POST", r"^/api/decision-packs/build$", self._build_decision_pack),
            ("GET", r"^/api/decision-packs/(?P<decision_id>[^/]+)$", self._get_decision_pack),
            ("POST", r"^/api/approvals/(?P<decision_id>[^/]+)/sign$", self._sign_decision),
            ("POST", r"^/api/execution-intents$", self._create_execution_intent),
            ("GET", r"^/api/execution-intents/(?P<intent_id>[^/]+)$", self._get_execution_intent),
            ("POST", r"^/api/execution-intents/(?P<intent_id>[^/]+)/simulate$", self._simulate_execution_intent),
            ("GET", r"^/api/simulated-executions$", self._list_simulated_executions),
            ("POST", r"^/api/simulated-executions/query$", self._list_simulated_executions),
            ("POST", r"^/api/exceptions$", self._create_exception),
            ("POST", r"^/api/reviews/create$", self._create_review),
            ("GET", r"^/api/reviews/(?P<review_id>[^/]+)$", self._get_review),
            ("POST", r"^/api/operating-reports$", self._generate_operating_report),
            ("GET", r"^/api/operating-reports/red-flag-reminders$", self._operating_report_red_flag_reminders),
            ("POST", r"^/api/operating-reports/red-flag-reminders$", self._operating_report_red_flag_reminders),
            ("POST", r"^/api/operating-reports/(?P<report_id>[^/]+)/publish$", self._publish_operating_report),
            ("POST", r"^/api/operating-reports/(?P<report_id>[^/]+)/board-pack$", self._export_operating_report_board_pack),
            ("POST", r"^/api/operating-reports/(?P<report_id>[^/]+)/red-flags/(?P<red_flag_id>[^/]+)/resolve$", self._resolve_operating_report_red_flag),
            ("GET", r"^/api/operating-reports/(?P<report_id>[^/]+)$", self._get_operating_report),
            ("POST", r"^/api/strategy-replays$", self._create_strategy_replay),
            ("GET", r"^/api/strategy-replays/compare$", self._compare_strategy_replays),
            ("POST", r"^/api/strategy-replays/compare$", self._compare_strategy_replays),
            ("GET", r"^/api/strategy-replays$", self._list_strategy_replays),
            ("GET", r"^/api/strategy-replays/(?P<replay_id>[^/]+)$", self._get_strategy_replay),
            ("POST", r"^/api/portfolio/optimize$", self._run_portfolio_optimizer),
            ("POST", r"^/api/portfolio/optimizer/compare$", self._portfolio_optimizer_compare_report),
            ("GET", r"^/api/portfolio/optimizer/readiness-report$", self._portfolio_optimizer_readiness_report),
            ("POST", r"^/api/portfolio/optimizer/readiness-report$", self._portfolio_optimizer_readiness_report),
            ("POST", r"^/api/portfolio/forward-report$", self._portfolio_forward_report),
            ("GET", r"^/api/portfolio/attribution/readiness-report$", self._portfolio_attribution_readiness_report),
            ("POST", r"^/api/portfolio/attribution/readiness-report$", self._portfolio_attribution_readiness_report),
            ("POST", r"^/api/portfolio/returns$", self._portfolio_returns),
            ("POST", r"^/api/portfolio/valuation$", self._portfolio_valuation),
            ("POST", r"^/api/portfolio/transactions$", self._register_portfolio_transaction),
            ("POST", r"^/api/portfolio/transactions/import$", self._import_portfolio_transactions),
            ("GET", r"^/api/portfolio/transactions$", self._list_portfolio_transactions),
            ("POST", r"^/api/portfolio/transactions/query$", self._list_portfolio_transactions),
            ("GET", r"^/api/portfolio/positions$", self._portfolio_positions_from_transactions),
            ("POST", r"^/api/portfolio/positions$", self._portfolio_positions_from_transactions),
            ("GET", r"^/api/portfolio/proposals$", self._list_portfolio_proposals),
            ("GET", r"^/api/portfolio/proposals/(?P<proposal_id>[^/]+)$", self._get_portfolio_proposal),
            ("POST", r"^/api/portfolio/attribution/backfill$", self._portfolio_attribution_backfill),
            ("POST", r"^/api/portfolio/simulated-feedback$", self._portfolio_simulated_feedback),
            ("GET", r"^/api/macro-themes$", self._list_macro_themes),
            ("POST", r"^/api/macro-themes$", self._register_macro_theme),
            ("GET", r"^/api/industry-chains$", self._list_industry_chains),
            ("POST", r"^/api/industry-chains$", self._register_industry_chain),
            ("GET", r"^/api/industry-chains/template-candidates$", self._list_industry_chain_template_candidates),
            ("POST", r"^/api/industry-chains/template-candidates$", self._create_industry_chain_template_candidate),
            ("GET", r"^/api/industry-chains/template-candidates/(?P<candidate_id>[^/]+)$", self._get_industry_chain_template_candidate),
            ("POST", r"^/api/industry-chains/template-candidates/(?P<candidate_id>[^/]+)/submit$", self._submit_industry_chain_template_candidate),
            ("POST", r"^/api/industry-chains/template-candidates/(?P<candidate_id>[^/]+)/submit-review$", self._submit_industry_chain_template_candidate),
            ("POST", r"^/api/industry-chains/template-candidates/(?P<candidate_id>[^/]+)/review$", self._review_industry_chain_template_candidate),
            ("POST", r"^/api/industry-chains/template-candidates/(?P<candidate_id>[^/]+)/publish$", self._publish_industry_chain_template_candidate),
            ("GET", r"^/api/industry-chains/panorama$", self._industry_chain_panorama),
            ("POST", r"^/api/industry-chains/panorama$", self._industry_chain_panorama),
            ("GET", r"^/api/industry-chains/panorama/readiness-report$", self._industry_chain_panorama_readiness_report),
            ("POST", r"^/api/industry-chains/panorama/readiness-report$", self._industry_chain_panorama_readiness_report),
            ("GET", r"^/api/industry-chains/(?P<chain_id>[^/]+)/analysis$", self._industry_chain_analysis),
            ("POST", r"^/api/industry-chains/(?P<chain_id>[^/]+)/analysis$", self._industry_chain_analysis),
            ("GET", r"^/api/company-positions$", self._list_company_positions),
            ("GET", r"^/api/company-positions/schema$", self._company_positions_schema),
            ("GET", r"^/api/company-positions/coverage-report$", self._company_positions_coverage_report),
            ("POST", r"^/api/company-positions/coverage-report$", self._company_positions_coverage_report),
            ("GET", r"^/api/company-profiles$", self._list_company_profiles),
            ("POST", r"^/api/company-profiles$", self._register_company_profile),
            ("POST", r"^/api/company-profiles/fields/extract$", self._extract_company_profile_fields),
            ("GET", r"^/api/company-profiles/field-assertions$", self._company_profile_field_assertions),
            ("POST", r"^/api/company-profiles/field-assertions$", self._company_profile_field_assertions),
            ("POST", r"^/api/company-profiles/field-assertions/review$", self._review_company_profile_field_assertion),
            ("GET", r"^/api/company-profiles/coverage/audit$", self._company_profile_coverage_audit),
            ("POST", r"^/api/company-profiles/coverage/audit$", self._company_profile_coverage_audit),
            ("GET", r"^/api/company-profiles/schema$", self._company_profile_schema),
            ("GET", r"^/api/company-financial-metrics$", self._list_financial_metrics),
            ("POST", r"^/api/company-financial-metrics$", self._register_financial_metric),
            ("POST", r"^/api/company-database/bootstrap$", self._bootstrap_company_database),
            ("POST", r"^/api/company-database/package/import$", self._import_company_watchlist),
            ("POST", r"^/api/company-database/watchlist/import$", self._import_company_watchlist),
            ("GET", r"^/api/company-database/package/import/runs$", self._company_package_import_runs),
            ("POST", r"^/api/company-database/package/import/runs$", self._company_package_import_runs),
            ("GET", r"^/api/company-database/watchlist/import/runs$", self._company_package_import_runs),
            ("POST", r"^/api/company-database/watchlist/import/runs$", self._company_package_import_runs),
            ("POST", r"^/api/company-database/package/import/runs/(?P<run_id>[^/]+)/material-manifests$", self._company_package_import_material_manifests),
            ("POST", r"^/api/company-database/watchlist/import/runs/(?P<run_id>[^/]+)/material-manifests$", self._company_package_import_material_manifests),
            ("GET", r"^/api/company-database/material-inbox/pending$", self._company_material_inbox_pending),
            ("POST", r"^/api/company-database/material-inbox/pending$", self._company_material_inbox_pending),
            ("POST", r"^/api/company-database/build$", self._build_company_database),
            ("POST", r"^/api/company-database/batch/build$", self._build_company_database_batch),
            ("POST", r"^/api/company-database/batch/runs/(?P<run_id>[^/]+)/retry$", self._retry_company_database_build_run),
            ("GET", r"^/api/company-database/batch/runs$", self._company_database_build_runs),
            ("POST", r"^/api/company-database/batch/runs$", self._company_database_build_runs),
            ("GET", r"^/api/company-database/coverage/trends$", self._company_database_coverage_trends),
            ("POST", r"^/api/company-database/coverage/trends$", self._company_database_coverage_trends),
            ("GET", r"^/api/company-database/coverage/audit$", self._company_database_coverage_audit),
            ("POST", r"^/api/company-database/coverage/audit$", self._company_database_coverage_audit),
            ("POST", r"^/api/company-database/quality/reconcile$", self._reconcile_company_database_quality),
            ("GET", r"^/api/data-health/runs/summary$", self._data_health_runs_summary),
            ("POST", r"^/api/data-health/runs/summary$", self._data_health_runs_summary),
            ("GET", r"^/api/data-health/summary$", self._data_health_summary),
            ("POST", r"^/api/data-health/summary$", self._data_health_summary),
            ("POST", r"^/api/company-database/material-inbox/ingest$", self._company_material_inbox_ingest),
            ("GET", r"^/api/company-database/profile-field-coverage/audit$", self._company_profile_coverage_audit),
            ("POST", r"^/api/company-database/profile-field-coverage/audit$", self._company_profile_coverage_audit),
            ("GET", r"^/api/company-database/profile-field-assertions$", self._company_profile_field_assertions),
            ("POST", r"^/api/company-database/profile-field-assertions$", self._company_profile_field_assertions),
            ("POST", r"^/api/company-database/profile-field-assertions/review$", self._review_company_profile_field_assertion),
            ("POST", r"^/api/company-database/profile-fields/extract$", self._extract_company_profile_fields),
            ("POST", r"^/api/company-database/events/build$", self._build_company_events),
            ("POST", r"^/api/company-database/events/review$", self._review_company_events),
            ("POST", r"^/api/company-database/relationships/build$", self._build_company_relationships),
            ("POST", r"^/api/company-database/relationships/review$", self._review_company_relationships),
            ("POST", r"^/api/company-database/workflow/build$", self._build_company_workflow),
            ("GET", r"^/api/company-events$", self._list_company_events),
            ("POST", r"^/api/company-events$", self._register_company_event),
            ("POST", r"^/api/company-events/review$", self._review_company_events),
            ("POST", r"^/api/company-events/(?P<event_id>[^/]+)/review$", self._review_company_event),
            ("GET", r"^/api/company-relationships$", self._list_company_relationships),
            ("POST", r"^/api/company-relationships$", self._register_company_relationship),
            ("POST", r"^/api/company-relationships/review$", self._review_company_relationships),
            ("POST", r"^/api/company-relationships/(?P<relationship_id>[^/]+)/review$", self._review_company_relationship),
            ("GET", r"^/api/research-reports/structured$", self._list_structured_research_reports),
            ("POST", r"^/api/research-reports/structured$", self._register_structured_research_report),
            ("GET", r"^/api/research-report-viewpoints$", self._list_report_viewpoints),
            ("POST", r"^/api/research-report-viewpoints$", self._register_report_viewpoint),
            ("GET", r"^/api/research-report-forecasts$", self._list_report_forecasts),
            ("POST", r"^/api/research-report-forecasts$", self._register_report_forecast),
            ("GET", r"^/api/analyst-profiles$", self._list_analyst_profiles),
            ("POST", r"^/api/analyst-profiles$", self._register_analyst_profile),
            ("GET", r"^/api/analyst-reliability-scores$", self._list_analyst_reliability_scores),
            ("POST", r"^/api/analyst-reliability-scores$", self._compute_analyst_reliability_score),
            ("GET", r"^/api/observation-items$", self._list_observation_items),
            ("POST", r"^/api/observation-items$", self._register_observation_item),
            ("GET", r"^/api/analysis-conclusions$", self._list_analysis_conclusions),
            ("POST", r"^/api/analysis-conclusions$", self._create_analysis_conclusion),
            ("GET", r"^/api/simulation-feedback$", self._list_simulation_feedback),
            ("POST", r"^/api/simulation-feedback$", self._record_simulation_feedback),
            ("POST", r"^/api/simulation-feedback/performance/update$", self._update_simulation_feedback_performance),
            ("GET", r"^/api/hotspot-lexicons$", self._list_hotspot_lexicons),
            ("POST", r"^/api/hotspot-lexicons$", self._register_hotspot_lexicon),
            ("POST", r"^/api/industry-chains/(?P<chain_id>[^/]+)/companies$", self._register_company_position),
            ("GET", r"^/api/hotspots/readiness-report$", self._hotspot_readiness_report),
            ("POST", r"^/api/hotspots/readiness-report$", self._hotspot_readiness_report),
            ("POST", r"^/api/hotspots/expand$", self._hotspot_expansion),
            ("GET", r"^/api/graph/traceability-report$", self._graph_traceability_report),
            ("POST", r"^/api/graph/traceability-report$", self._graph_traceability_report),
            ("GET", r"^/api/graph/edge-quality-report$", self._graph_edge_quality_report),
            ("POST", r"^/api/graph/edge-quality-report$", self._graph_edge_quality_report),
            ("GET", r"^/api/graph/neo4j/export$", self._graph_neo4j_export),
            ("POST", r"^/api/graph/neo4j/export$", self._graph_neo4j_export),
            ("POST", r"^/api/graph/neo4j/sync$", self._sync_graph_neo4j),
            ("GET", r"^/api/graph-vector/readiness-report$", self._graph_vector_readiness_report),
            ("POST", r"^/api/graph-vector/readiness-report$", self._graph_vector_readiness_report),
            ("POST", r"^/api/company-intelligence/(?P<symbol>[^/]+)/cycle/run$", self._run_company_intelligence_cycle),
            ("GET", r"^/api/company-intelligence/cycle/runs$", self._company_intelligence_cycle_runs),
            ("POST", r"^/api/company-intelligence/cycle/runs$", self._company_intelligence_cycle_runs),
            ("GET", r"^/api/company-intelligence/(?P<symbol>[^/]+)$", self._company_intelligence_by_symbol),
            ("POST", r"^/api/company-intelligence/(?P<symbol>[^/]+)$", self._company_intelligence_by_symbol),
            ("GET", r"^/api/graph/query$", self._query_graph),
            ("GET", r"^/api/search/qdrant/export$", self._qdrant_vector_export),
            ("POST", r"^/api/search/qdrant/export$", self._qdrant_vector_export),
            ("POST", r"^/api/search/qdrant/sync$", self._sync_qdrant_vectors),
            ("GET", r"^/api/search/adapter-sync/retry$", self._adapter_sync_retry_drill),
            ("POST", r"^/api/search/adapter-sync/retry$", self._adapter_sync_retry_drill),
            ("POST", r"^/api/search/rebuild$", self._rebuild_search_indexes),
            ("POST", r"^/api/search/semantic/llm-rerank/benchmark$", self._semantic_llm_rerank_benchmark),
            ("GET", r"^/api/search/semantic/rerank$", self._semantic_rerank),
            ("POST", r"^/api/search/semantic/rerank$", self._semantic_rerank),
            ("GET", r"^/api/search/semantic/llm-rerank$", self._semantic_llm_rerank),
            ("POST", r"^/api/search/semantic/llm-rerank$", self._semantic_llm_rerank),
            ("GET", r"^/api/search/semantic$", self._semantic_search),
            ("POST", r"^/api/search/semantic$", self._semantic_search),
            ("POST", r"^/api/search/semantic/benchmark$", self._semantic_search_benchmark),
            ("GET", r"^/api/search$", self._search),
            ("POST", r"^/api/search$", self._search),
            ("GET", r"^/api/dashboard/ceo$", self._dashboard_ceo),
            ("GET", r"^/api/dashboard/risk$", self._dashboard_risk),
            ("GET", r"^/api/readiness/checklist$", self._readiness_checklist),
            ("POST", r"^/api/readiness/capacity-baseline$", self._record_capacity_baseline),
            ("POST", r"^/api/readiness/checklist$", self._record_readiness_check),
            ("POST", r"^/api/readiness/checklist/(?P<check_id>[^/]+)$", self._record_readiness_check),
            ("GET", r"^/api/readiness/deployment-report$", self._readiness_deployment_report),
            ("POST", r"^/api/readiness/deployment-report$", self._readiness_deployment_report),
            ("GET", r"^/api/readiness/ui-report$", self._readiness_ui_report),
            ("POST", r"^/api/readiness/ui-report$", self._readiness_ui_report),
            ("GET", r"^/api/readiness/evidence-package$", self._readiness_evidence_package),
            ("POST", r"^/api/readiness/evidence-package$", self._readiness_evidence_package),
            ("POST", r"^/api/readiness/evidence-package/notify$", self._notify_readiness_evidence_package),
            ("GET", r"^/api/readiness/remediation-report$", self._readiness_remediation_report),
            ("POST", r"^/api/readiness/remediation-report$", self._readiness_remediation_report),
            ("GET", r"^/api/readiness/vision-gate$", self._vision_acceptance_report),
            ("GET", r"^/api/incidents/calendar$", self._incident_calendar),
        ]
        for route_method, pattern, handler in routes:
            if route_method == method and re.fullmatch(pattern, path):
                return handler
        return None

    def _authorize(self, method: str, path: str, role: str) -> bool:
        if path.startswith("/api/health") or path.startswith("/api/metrics") or path.startswith("/api/analysis/latest"):
            return True
        safe_roles = {"system", "CEO", "CIO", "PM", "风险/合规", "平台负责人", "分析师", "数据工程", "NLP/ML 负责人", "海外研究负责人"}
        if role not in safe_roles:
            return False
        if path.startswith("/api/observability"):
            return role in {"system", "CEO", "CIO", "风险/合规", "平台负责人", "数据工程", "NLP/ML 负责人"}
        if path.startswith("/api/dashboard"):
            return True
        if path.startswith("/api/readiness"):
            return role in {"system", "CEO", "CIO", "风险/合规", "平台负责人"}
        if path.startswith("/api/governance"):
            return role in {"system", "CEO", "CIO", "风险/合规", "平台负责人", "数据工程"}
        if path.startswith("/api/demo"):
            return role in {"system", "CEO", "CIO", "平台负责人"}
        if path.startswith("/api/market-data"):
            return method == "GET" or role in {"system", "风险/合规", "平台负责人", "数据工程"}
        if path.startswith("/api/corporate-actions"):
            return method == "GET" or role in {"system", "风险/合规", "平台负责人", "数据工程"}
        if path.startswith("/api/13f"):
            return method == "GET" or role in {"system", "风险/合规", "平台负责人", "数据工程", "CIO", "分析师", "海外研究负责人"}
        if path.startswith("/api/disclosure-events"):
            return method == "GET" or role in {"system", "风险/合规", "平台负责人", "数据工程", "CIO", "分析师", "海外研究负责人"}
        if path.startswith("/api/ingestion/sources") or path.startswith("/api/ingestion/documents") or path.startswith("/api/ingestion/sec") or path.startswith("/api/ingestion/ashare") or path.startswith("/api/ingestion/hkex") or path.startswith("/api/ingestion/jobs") or path.startswith("/api/ingestion/schedules") or path.startswith("/api/entity-mappings") or path.startswith("/api/connectors/preview") or path.startswith("/api/connectors/sec") or path.startswith("/api/connectors/ashare") or path.startswith("/api/connectors/hkex") or path.startswith("/api/connectors/astock"):
            return role in {"system", "风险/合规", "平台负责人", "数据工程"}
        if path.startswith("/api/benchmarks") or path.startswith("/api/prompts/changes") or path.startswith("/api/scorecards"):
            return role in {"system", "NLP/ML 负责人", "风险/合规", "平台负责人", "CIO"}
        if path.startswith("/api/templates") or path.startswith("/api/research-cards") or path.startswith("/api/research-reports") or path.startswith("/api/research/manual-references") or path.startswith("/api/research/answers") or path.startswith("/api/research/tasks") or path.startswith("/api/macro-themes") or path.startswith("/api/industry-chains") or path.startswith("/api/company-database") or path.startswith("/api/data-health") or path.startswith("/api/company-profiles") or path.startswith("/api/company-financial-metrics") or path.startswith("/api/company-events") or path.startswith("/api/company-relationships") or path.startswith("/api/research-report-viewpoints") or path.startswith("/api/research-report-forecasts") or path.startswith("/api/analyst-profiles") or path.startswith("/api/analyst-reliability-scores") or path.startswith("/api/observation-items") or path.startswith("/api/analysis-conclusions") or path.startswith("/api/simulation-feedback") or path.startswith("/api/hotspot-lexicons") or path.startswith("/api/hotspots") or path.startswith("/api/crowding") or path.startswith("/api/challenger") or path.startswith("/api/playbooks") or path.startswith("/api/incident-reports") or path.startswith("/api/drill-schedules") or path.startswith("/api/alerts"):
            return role in {"system", "NLP/ML 负责人", "风险/合规", "平台负责人", "CIO", "PM", "分析师", "海外研究负责人", "数据工程"}
        if path.startswith("/api/llm"):
            return role in {"system", "CEO", "CIO", "风险/合规", "平台负责人", "分析师", "NLP/ML 负责人", "海外研究负责人"}
        if path.startswith("/api/orchestration") or path.startswith("/api/lineage") or path.startswith("/api/model-versions"):
            return role in {"system", "CEO", "CIO", "风险/合规", "平台负责人", "数据工程", "NLP/ML 负责人"}
        if path.startswith("/api/document-parsing"):
            return role in {"system", "风险/合规", "平台负责人", "分析师", "数据工程", "NLP/ML 负责人", "海外研究负责人"}
        if path.startswith("/api/evidence") or path.startswith("/api/extractions") or path.startswith("/api/thesis") or path.startswith("/api/scoring"):
            return role in {"system", "分析师", "海外研究负责人", "CIO", "PM", "平台负责人", "NLP/ML 负责人", "风险/合规"}
        if path.startswith("/api/decision-packs") or path.startswith("/api/approvals") or path.startswith("/api/exceptions"):
            return role in {"system", "CEO", "CIO", "风险/合规"}
        if path.startswith("/api/execution-intents") or path.startswith("/api/simulated-executions"):
            return role in {"system", "CEO", "CIO", "PM", "风险/合规"}
        if path.startswith("/api/portfolio"):
            return role in {"system", "CEO", "CIO", "PM", "风险/合规", "分析师", "平台负责人"}
        if path.startswith("/api/reviews") or path.startswith("/api/operating-reports") or path.startswith("/api/strategy-replays") or path.startswith("/api/graph") or path.startswith("/api/search"):
            return True
        return True

    def _register_source(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.register_source(body, actor=actor))

    def _seed_default_sources(self, _path: str, _body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return {"sources": [to_plain(item) for item in self.service.seed_default_sources(actor=actor)]}

    def _update_source_governance(self, path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        match = re.fullmatch(r"^/api/governance/sources/(?P<source_id>[^/]+)$", path)
        return to_plain(self.service.update_source_governance(match["source_id"], body, actor=actor))

    def _source_governance_report(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.source_governance_report(body)

    def _record_source_review(self, path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        match = re.fullmatch(r"^/api/governance/sources/(?P<source_id>[^/]+)/reviews$", path)
        return to_plain(self.service.record_source_review(match["source_id"], body, actor=actor))

    def _list_source_reviews(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.source_reviews_payload(body)

    def _source_review_reminders(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.source_review_reminders_payload(body)

    def _source_review_sla_escalations(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.source_review_sla_escalation_report(body)

    def _notify_source_review_escalations(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.create_source_review_escalation_notifications(body, actor=actor)

    def _audit_completeness_report(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.audit_completeness_report(body)

    def _data_security_report(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.data_security_report(body)

    def _security_readiness_report(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        matrix = self.permission_matrix_payload({"include_role_matrix": False})
        return self.service.security_readiness_report(body, permission_matrix=matrix, actor=actor)

    def _record_secret_rotation(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.record_secret_rotation(body, actor=actor))

    def _secret_rotations(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.secret_rotations_payload(body)

    def _permission_matrix(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        _ = actor
        return self.permission_matrix_payload(body)

    def _storage_policy_templates(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        _ = actor
        return self.service.storage_policy_templates_payload(body)

    def _storage_readiness_report(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.storage_readiness_report(body, actor=actor)

    def _cache_retention_report(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.cache_retention_report(body, actor=actor)

    def _cache_retention_runs(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        _ = actor
        return self.service.cache_retention_runs_payload(body)

    def _record_cache_retention_execution_evidence(self, path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        match = re.fullmatch(r"^/api/governance/cache-retention-runs/(?P<run_id>[^/]+)/execution-evidence$", path)
        return to_plain(self.service.record_cache_retention_execution_evidence(match["run_id"], body, actor=actor))

    def _execute_cache_retention_run(self, path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        match = re.fullmatch(r"^/api/governance/cache-retention-runs/(?P<run_id>[^/]+)/execute$", path)
        return self.service.execute_cache_retention_run(match["run_id"], body, actor=actor)

    def permission_matrix_payload(self, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        filters = filters or {}
        role_filter = self._normalize_role(str(filters.get("role", "")).strip()) if filters.get("role") else ""
        domain_filter = str(filters.get("data_domain", "")).strip()
        action_filter = str(filters.get("action", "")).strip()
        method_filter = str(filters.get("method", "")).strip().upper()
        include_role_matrix = bool(filters.get("include_role_matrix", True))
        roles = list(CANONICAL_ROLES)
        if role_filter and role_filter not in roles:
            roles.append(role_filter)
        rules: list[dict[str, Any]] = []
        role_matrix: list[dict[str, Any]] = []
        summary_by_role = {
            role: {"role": role, "allowed": 0, "denied": 0, "public_allowed": 0, "red_allowed": 0}
            for role in roles
        }
        for rule in PERMISSION_POLICY_CATALOG:
            data_domains = [str(item) for item in rule["data_domains"]]
            if domain_filter and domain_filter not in data_domains:
                continue
            for method in rule["methods"]:
                method = str(method).upper()
                if method_filter and method_filter != method:
                    continue
                action = str(rule.get("actions", {}).get(method, "execute"))
                if action_filter and action_filter != action:
                    continue
                sample_path = str(rule.get("sample_paths", {}).get(method, rule["path_prefixes"][0]))
                public = self._authorize(method, sample_path, "__unauthenticated__")
                allowed_roles = ["*"] if public else [role for role in CANONICAL_ROLES if self._authorize(method, sample_path, role)]
                denied_roles = [] if public else [role for role in CANONICAL_ROLES if role not in allowed_roles]
                if role_filter and not public and role_filter not in allowed_roles and role_filter not in denied_roles:
                    denied_roles.append(role_filter)
                if role_filter:
                    role_allowed = public or self._authorize(method, sample_path, role_filter)
                    if not role_allowed and not filters.get("include_denied", True):
                        continue
                rules.append(
                    {
                        "rule_id": rule["rule_id"],
                        "method": method,
                        "action": action,
                        "data_domains": data_domains,
                        "path_prefixes": [str(item) for item in rule["path_prefixes"]],
                        "sample_path": sample_path,
                        "allowed_roles": allowed_roles,
                        "denied_roles": denied_roles,
                        "public": public,
                        "sensitivity": rule.get("sensitivity", "yellow"),
                    }
                )
                for role in roles:
                    allowed = public or self._authorize(method, sample_path, role)
                    summary_by_role[role]["allowed" if allowed else "denied"] += 1
                    if public and allowed:
                        summary_by_role[role]["public_allowed"] += 1
                    if allowed and rule.get("sensitivity") == "red":
                        summary_by_role[role]["red_allowed"] += 1
                    if not include_role_matrix:
                        continue
                    if role_filter and role != role_filter:
                        continue
                    for data_domain in data_domains:
                        role_matrix.append(
                            {
                                "role": role,
                                "data_domain": data_domain,
                                "method": method,
                                "action": action,
                                "rule_id": rule["rule_id"],
                                "sample_path": sample_path,
                                "allowed": allowed,
                                "sensitivity": rule.get("sensitivity", "yellow"),
                            }
                        )
        summary_rows = list(summary_by_role.values())
        if role_filter:
            summary_rows = [row for row in summary_rows if row["role"] == role_filter]
        return {
            "roles": roles,
            "role_aliases": ROLE_ALIASES,
            "rules": rules,
            "role_matrix": role_matrix,
            "summary_by_role": summary_rows,
            "coverage": {
                "rules": len(rules),
                "role_decisions": len(role_matrix),
                "data_domains": len({domain for rule in rules for domain in rule["data_domains"]}),
                "public_rules": sum(1 for rule in rules if rule["public"]),
                "source": "api_gateway_authorization_rules",
            },
        }

    def _seed_demo_full_flow(self, _path: str, _body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.seed_demo_full_flow(actor=actor)

    def _health(self, _path: str, _body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.health()

    def _metrics(self, _path: str, _body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.metrics()

    def _latest_analysis(self, _path: str, _body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        daily_pointer = Path("artifacts/daily-update-local/latest-run.json")
        daily_run = {}
        if daily_pointer.exists():
            try:
                pointer = json.loads(daily_pointer.read_text(encoding="utf-8"))
                pipeline_output = Path(str(pointer.get("pipeline_output") or ""))
                output_dir = Path(str(pointer.get("output_dir") or pipeline_output.parent))
                run_date = str(pointer.get("run_date") or "")
                latest_analysis_path = output_dir / f"latest-analysis-{run_date}" / "latest-analysis.json" if run_date else Path()
                daily_insight_path = output_dir / f"daily-insight-json-{run_date}.json" if run_date else Path()
                personal_intelligence_path = output_dir / f"personal-intelligence-refresh-{run_date}.json" if run_date else Path()
                if pipeline_output.exists():
                    daily_run["pipeline"] = json.loads(pipeline_output.read_text(encoding="utf-8"))
                if latest_analysis_path.exists():
                    daily_run["latest_analysis_path"] = latest_analysis_path
                if daily_insight_path.exists():
                    daily_run["daily_insight_path"] = daily_insight_path
                    daily_run["daily_insight"] = json.loads(daily_insight_path.read_text(encoding="utf-8"))
                if personal_intelligence_path.exists():
                    daily_run["personal_intelligence_path"] = personal_intelligence_path
                    daily_run["personal_intelligence"] = json.loads(personal_intelligence_path.read_text(encoding="utf-8"))
                daily_run["pointer"] = pointer
            except Exception:
                daily_run = {}
        if not daily_run.get("personal_intelligence"):
            personal_fallback = Path("artifacts/personal-intelligence/latest.json")
            if personal_fallback.exists():
                try:
                    daily_run["personal_intelligence_path"] = personal_fallback
                    daily_run["personal_intelligence"] = json.loads(personal_fallback.read_text(encoding="utf-8"))
                except Exception:
                    pass
        candidates = [
            daily_run.get("latest_analysis_path") if isinstance(daily_run.get("latest_analysis_path"), Path) else None,
            Path("artifacts/latest-analysis/latest-analysis.json"),
            Path("artifacts/latest-analysis-ahu/latest-analysis.json"),
        ]
        artifact_path = next((path for path in candidates if isinstance(path, Path) and path.exists()), None)
        if artifact_path is None:
            return {
                "status": "missing",
                "artifact_path": "",
                "message": "latest analysis artifact is not available; run scripts/latest_analysis_run.py first",
                "assets": [],
                "returns": [],
                "weights": [],
                "snapshots": [],
                "source_summary": [],
                "counts": {},
            }

        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
        analysis = payload.get("analysis", {}) if isinstance(payload, dict) else {}
        assets = analysis.get("assets") or []
        asset_by_security = {
            str(asset.get("security_id")): asset
            for asset in assets
            if isinstance(asset, dict) and asset.get("security_id")
        }
        asset_by_label = {
            str(asset.get("label") or asset.get("symbol")): asset
            for asset in assets
            if isinstance(asset, dict) and (asset.get("label") or asset.get("symbol"))
        }

        returns = []
        returns_payload = analysis.get("returns") or {}
        if isinstance(returns_payload, dict):
            for label, item in returns_payload.items():
                if not isinstance(item, dict):
                    continue
                asset = asset_by_label.get(str(label), {})
                total_return = item.get("total_return")
                returns.append(
                    {
                        "label": label,
                        "security_id": asset.get("security_id") or item.get("security_id") or "",
                        "market": asset.get("market") or "",
                        "source_id": asset.get("source_id") or item.get("source_id") or "",
                        "start_date": item.get("start_date") or analysis.get("window", {}).get("start_date"),
                        "end_date": item.get("end_date") or analysis.get("window", {}).get("end_date"),
                        "total_return": total_return,
                        "total_return_pct": round(float(total_return) * 100, 2) if isinstance(total_return, int | float) else None,
                        "observation_count": item.get("return_count") or item.get("observation_count") or 0,
                    }
                )
        returns.sort(key=lambda item: (item.get("market") or "", item.get("label") or ""))

        weights = []
        optimizer = analysis.get("portfolio_optimizer") or {}
        candidate_weights = optimizer.get("candidate_weights") or {}
        if isinstance(candidate_weights, dict):
            for security_id, weight in candidate_weights.items():
                asset = asset_by_security.get(str(security_id), {})
                weights.append(
                    {
                        "security_id": security_id,
                        "label": asset.get("label") or asset.get("symbol") or security_id,
                        "market": asset.get("market") or "",
                        "source_id": asset.get("source_id") or "",
                        "weight": weight,
                        "weight_pct": round(float(weight) * 100, 2) if isinstance(weight, int | float) else None,
                    }
                )
        weights.sort(key=lambda item: item.get("weight") if isinstance(item.get("weight"), int | float) else -1, reverse=True)

        snapshots = []
        for item in analysis.get("latest_snapshot") or []:
            if not isinstance(item, dict):
                continue
            snapshots.append(
                {
                    "label": item.get("label") or item.get("symbol") or item.get("security_id"),
                    "security_id": item.get("security_id"),
                    "market": item.get("market"),
                    "as_of_date": item.get("as_of_date"),
                    "close": item.get("close"),
                    "currency": item.get("currency"),
                    "source_id": item.get("source_id"),
                    "license_class": (item.get("rights_tag") or {}).get("license_class"),
                }
            )

        source_summary: dict[str, dict[str, Any]] = {}
        for item in snapshots:
            source_id = str(item.get("source_id") or "unknown")
            source = source_summary.setdefault(
                source_id,
                {
                    "source_id": source_id,
                    "markets": set(),
                    "license_classes": set(),
                    "latest_date": "",
                    "asset_count": 0,
                },
            )
            source["asset_count"] += 1
            if item.get("market"):
                source["markets"].add(item["market"])
            if item.get("license_class"):
                source["license_classes"].add(item["license_class"])
            if item.get("as_of_date") and str(item["as_of_date"]) > str(source["latest_date"]):
                source["latest_date"] = item["as_of_date"]

        acceptance_path = Path("artifacts/local-business-acceptance-after-us-eod.json")
        if not acceptance_path.exists():
            acceptance_path = Path("artifacts/local-business-acceptance-after-latest.json")
        acceptance = {}
        if acceptance_path.exists():
            acceptance_payload = json.loads(acceptance_path.read_text(encoding="utf-8"))
            checks = acceptance_payload.get("checks") or []
            acceptance = {
                "artifact_path": str(acceptance_path),
                "passed": bool(checks) and all(bool(item.get("passed")) for item in checks if isinstance(item, dict)),
                "check_count": acceptance_payload.get("check_count") or len(checks),
                "failed_count": sum(1 for item in checks if isinstance(item, dict) and not item.get("passed")),
                "base_url": acceptance_payload.get("base_url") or "",
            }

        daily_insight = daily_run.get("daily_insight") if isinstance(daily_run.get("daily_insight"), dict) else {}
        personal_intelligence = daily_run.get("personal_intelligence") if isinstance(daily_run.get("personal_intelligence"), dict) else {}
        pipeline = daily_run.get("pipeline") if isinstance(daily_run.get("pipeline"), dict) else {}
        return {
            "status": payload.get("status") or "available",
            "artifact_path": str(artifact_path),
            "daily_pipeline_artifact_path": str((daily_run.get("pointer") or {}).get("pipeline_output") or ""),
            "daily_insight_artifact_path": str(daily_run.get("daily_insight_path") or ""),
            "personal_intelligence_artifact_path": str(daily_run.get("personal_intelligence_path") or ""),
            "generated_at": payload.get("generated_at") or "",
            "base_url": payload.get("base_url") or "",
            "latest_market_date": analysis.get("latest_market_date") or analysis.get("window", {}).get("end_date") or "",
            "window": analysis.get("window") or {},
            "production_boundary": payload.get("production_boundary") or {},
            "counts": analysis.get("metrics_counts") or analysis.get("dashboard_counts") or {},
            "assets": assets,
            "returns": returns,
            "weights": weights,
            "snapshots": snapshots,
            "source_summary": [
                {
                    **item,
                    "markets": sorted(item["markets"]),
                    "license_classes": sorted(item["license_classes"]),
                }
                for item in source_summary.values()
            ],
            "portfolio": {
                "proposal_id": optimizer.get("proposal_id") or analysis.get("portfolio_forward", {}).get("proposal_id") or "",
                "status": optimizer.get("status") or analysis.get("portfolio_forward", {}).get("proposal_status") or "",
                "simulation_only": bool(analysis.get("portfolio_forward", {}).get("simulation_only", True)),
                "review_flags": analysis.get("portfolio_forward", {}).get("review_flags") or [],
                "constraints": optimizer.get("constraints") or {},
            },
            "decision_summary": analysis.get("decision_summary") or {},
            "data_quality": analysis.get("data_quality") or {},
            "supplemental_market_observations": analysis.get("supplemental_market_observations") or {},
            "research_evidence": analysis.get("research_evidence") or {},
            "daily_insight": {
                "status": daily_insight.get("status") or "",
                "as_of_date": daily_insight.get("as_of_date") or pipeline.get("run_date") or "",
                "generated_at": daily_insight.get("generated_at") or "",
                "market_freshness": daily_insight.get("market_freshness") or [],
                "actionable_research_summary": daily_insight.get("actionable_research_summary") or {},
                "quality_gates": daily_insight.get("quality_gates") or {},
                "evidence_backed_watchlist": daily_insight.get("evidence_backed_watchlist") or [],
                "research_and_events": daily_insight.get("research_and_events") or {},
                "production_boundary": daily_insight.get("production_boundary") or "",
                "pipeline_status": pipeline.get("status") or "",
                "pipeline_effective_end_dates": pipeline.get("effective_end_dates") or {},
            },
            "personal_intelligence": personal_intelligence,
            "business_acceptance": acceptance,
            "board_pack": analysis.get("board_pack") or {},
        }

    def _structured_logs_export(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.structured_logs_export(body, actor=actor)

    def _opentelemetry_logs_export(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.opentelemetry_logs_export(body, actor=actor)

    def _submit_opentelemetry_logs(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.create_opentelemetry_log_notifications(body, actor=actor)

    def _observability_readiness_report(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.observability_readiness_report(body, actor=actor)

    def _register_issuer(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.register_issuer(body, actor=actor))

    def _register_security(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.register_security(body, actor=actor))

    def _register_market_data_point(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.register_market_data_point(body, actor=actor))

    def _register_market_data_batch(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.register_market_data_batch(body, actor=actor)

    def _tdx_market_data_preview(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.tdx_market_data_preview(body)

    def _import_tdx_market_data(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.import_tdx_market_data(body, actor=actor)

    def _market_data_backfill(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.market_data_backfill(body, actor=actor)

    def _market_data_backfill_coverage_report(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.market_data_backfill_coverage_report(body)

    def _market_data_quality_report(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.market_data_quality_report(body)

    def _market_data_schema_coverage_report(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.market_data_schema_coverage_report(body)

    def _adjusted_market_data(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.adjusted_market_data_payload(body)

    def _market_data_returns(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.market_data_returns_payload(body)

    def _list_market_data(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.market_data_payload(body)

    def _register_corporate_action(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.register_corporate_action(body, actor=actor))

    def _list_corporate_actions(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.corporate_actions_payload(body)

    def _parse_13f_information_table(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.parse_13f_information_table(body, actor=actor)

    def _parse_13f_information_table_batch(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.parse_13f_information_table_batch(body, actor=actor)

    def _13f_mapping_readiness_report(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.form13f_mapping_readiness_report(body, actor=actor)

    def _register_13f_holding(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.register_13f_holding(body, actor=actor))

    def _list_13f_holdings(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.institutional_holdings_payload(body)

    def _institutional_holding_changes(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.institutional_holding_changes_payload(body)

    def _institutional_candidate_pool(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.institutional_candidate_pool(body)

    def _update_crowding_from_13f(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.update_crowding_from_13f(body, actor=actor))

    def _create_disclosure_event(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.create_disclosure_event(body, actor=actor))

    def _list_disclosure_events(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.disclosure_events_payload(body)

    def _disclosure_event_performance_report(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.disclosure_event_performance_payload(body, actor=actor, write_back=False)

    def _disclosure_event_performance_writeback(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.disclosure_event_performance_payload(body, actor=actor, write_back=True)

    def _classify_disclosure_event(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.classify_disclosure_event(body, actor=actor))

    def _register_entity_mapping(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.register_entity_mapping(body, actor=actor))

    def _list_entity_mappings(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        _ = actor
        return self.service.entity_mappings_payload(body)

    def _register_entity_mapping_batch(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.register_entity_mapping_batch(body, actor=actor)

    def _record_entity_mapping_label_batch(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.record_entity_mapping_label_batch(body, actor=actor)

    def _entity_mapping_labels(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        _ = actor
        return self.service.entity_mapping_labels_payload(body)

    def _entity_mapping_quality_report(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.entity_mapping_quality_report(body)

    def _entity_mapping_readiness_report(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.entity_mapping_readiness_report(body, actor=actor)

    def _seed_astock_connectors(self, _path: str, _body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return {"connectors": [to_plain(item) for item in self.service.seed_astock_connectors(actor=actor)]}

    def _register_astock_connector(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.register_astock_connector(body, actor=actor))

    def _list_astock_connectors(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.astock_connectors_payload(body)

    def _verify_astock_connectors(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.verify_astock_connectors(body, actor=actor)

    def _astock_connector_verification_readiness(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.astock_connector_verification_readiness(body, actor=actor)

    def _fetch_astock_connector_sample(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.fetch_astock_connector_sample(body, actor=actor)

    def _fetch_astock_supplemental_samples(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        """POST /api/connectors/astock/supplemental/fetch  (T-416)

        Fetches real HTTP sample rows from a public A-share supplemental
        connector (eastmoney_research, cninfo_announcements,
        tencent_valuation_snapshot, ths_hot_topics, baidu_concepts,
        dragon_tiger_list, unlock_calendar). Results are manual_reference
        only and must NOT enter the automated decision chain.
        """
        return self.service.fetch_astock_supplemental_samples(body, actor=actor)

    def _preview_connector_document(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.preview_connector_document(str(body["market"]), body["raw"])

    def _fetch_ashare_recent_filings(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.fetch_ashare_recent_filings(body)

    def _fetch_sec_recent_filings(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.fetch_sec_recent_filings(body)

    def _fetch_hkex_recent_filings(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.fetch_hkex_recent_filings(body)

    def _ingest_sec_recent_filings(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.ingest_sec_recent_filings(body, actor=actor)

    def _ingest_ashare_recent_filings(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.ingest_ashare_recent_filings(body, actor=actor)

    def _ingest_hkex_recent_filings(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.ingest_hkex_recent_filings(body, actor=actor)

    def _run_ingestion_job(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.run_ingestion_job(body, actor=actor))

    def _get_ingestion_job(self, path: str, _body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        match = re.fullmatch(r"^/api/ingestion/jobs/(?P<job_id>[^/]+)$", path)
        return self.service.ingestion_job_payload(match["job_id"])

    def _register_ingestion_schedule(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.register_ingestion_schedule(body, actor=actor))

    def _run_ingestion_schedules(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.run_ingestion_schedules(body, actor=actor)

    def _get_ingestion_schedule(self, path: str, _body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        match = re.fullmatch(r"^/api/ingestion/schedules/(?P<schedule_id>[^/]+)$", path)
        return self.service.ingestion_schedule_payload(match["schedule_id"])

    def _ingest_document(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.ingest_document(body, actor=actor))

    def _get_document(self, path: str, _body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        match = re.fullmatch(r"^/api/ingestion/documents/(?P<document_id>[^/]+)$", path)
        return self.service.document_payload(match["document_id"])

    def _register_benchmark(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.register_benchmark(body, actor=actor))

    def _evaluate_benchmark(self, path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        match = re.fullmatch(r"^/api/benchmarks/(?P<benchmark_id>[^/]+)/evaluate$", path)
        return to_plain(self.service.evaluate_benchmark(match["benchmark_id"], body, actor=actor))

    def _register_benchmark_sample(self, path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        match = re.fullmatch(r"^/api/benchmarks/(?P<benchmark_id>[^/]+)/samples$", path)
        return to_plain(self.service.register_benchmark_sample(match["benchmark_id"], body, actor=actor))

    def _list_benchmark_samples(self, path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        match = re.fullmatch(r"^/api/benchmarks/(?P<benchmark_id>[^/]+)/samples$", path)
        return self.service.benchmark_samples_payload(match["benchmark_id"], body)

    def _run_benchmark_suite(self, path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        match = re.fullmatch(r"^/api/benchmarks/(?P<benchmark_id>[^/]+)/run$", path)
        return to_plain(self.service.run_benchmark_suite(match["benchmark_id"], body, actor=actor))

    def _benchmark_readiness_report(self, path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        match = re.fullmatch(r"^/api/benchmarks/(?P<benchmark_id>[^/]+)/readiness-report$", path)
        return self.service.benchmark_readiness_report(match["benchmark_id"], body, actor=actor)

    def _create_prompt_change(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.create_prompt_change(body, actor=actor))

    def _list_prompt_changes(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.prompt_changes_payload(body)

    def _approve_prompt_change(self, path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        match = re.fullmatch(r"^/api/prompts/changes/(?P<request_id>[^/]+)/approve$", path)
        return to_plain(self.service.approve_prompt_change(match["request_id"], actor=actor, approved=bool(body.get("approved", True))))

    def _register_template(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.register_template(body, actor=actor))

    def _seed_default_templates(self, _path: str, _body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return {"templates": [to_plain(item) for item in self.service.seed_default_templates(actor=actor)]}

    def _register_scorecard(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.register_scorecard(body, actor=actor))

    def _create_research_card(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.create_research_card(body, actor=actor))

    def _scan_research_reports(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.scan_research_reports(body, actor=actor)

    def _list_research_reports(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.research_reports_payload(body)

    def _research_report_extraction_queue(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.research_report_extraction_queue(body, actor=actor)

    def _research_report_incremental_schedule(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        """POST /api/research-reports/incremental-schedule  (T-417)

        Generates an incremental OCR/extraction schedule for the local research report library.
        Supports dry_run, ocr_budget_mb, batch_size and Airflow/Cron-ready schedule_plan output.
        Restricted to local_reference use only; no training or fact-source boundary.
        """
        return self.service.research_report_incremental_schedule(body, actor=actor)

    def _research_report_governance_report(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.research_report_governance_report(body)

    def _research_report_mapping_report(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.research_report_mapping_report(body)

    def _research_report_viewpoint_report(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.research_report_viewpoint_report(body)

    def _structure_research_reports(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.structure_research_reports(body, actor=actor)

    def _update_research_report_realization(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.update_research_report_realization(body, actor=actor)

    def _ingest_research_report(self, path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        match = re.fullmatch(r"^/api/research-reports/(?P<report_id>[^/]+)/ingest$", path)
        return self.service.ingest_research_report(match["report_id"], body, actor=actor)

    def _extract_research_report(self, path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        match = re.fullmatch(r"^/api/research-reports/(?P<report_id>[^/]+)/extract$", path)
        return self.service.extract_research_report_text(match["report_id"], body, actor=actor)

    def _create_manual_reference(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.create_manual_reference(body, actor=actor)

    def _citation_boundary_readiness_report(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.citation_boundary_readiness_report(body, actor=actor)

    def _create_research_answer(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.create_research_answer(body, actor=actor))

    def _create_filing_qa_answer(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.create_filing_qa_answer(body, actor=actor)

    def _research_answer_quality_report(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.research_answer_quality_report(body)

    def _research_answer_summary_benchmark(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.research_answer_summary_benchmark(body)

    def _research_answer_readiness_report(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.research_answer_readiness_report(body, actor=actor)

    def _review_research_answer(self, path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        match = re.fullmatch(r"^/api/research/answers/(?P<answer_id>[^/]+)/review$", path)
        return to_plain(self.service.review_research_answer(match["answer_id"], body, actor=actor))

    def _get_research_answer(self, path: str, _body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        match = re.fullmatch(r"^/api/research/answers/(?P<answer_id>[^/]+)$", path)
        return self.service.research_answer_payload(match["answer_id"])

    def _run_sec_single_name_research(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.run_sec_single_name_research(body, actor=actor)

    def _extract_structured_facts(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.extract_structured_facts(body, actor=actor))

    def _get_extraction_result(self, path: str, _body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        match = re.fullmatch(r"^/api/extractions/(?P<extraction_id>[^/]+)$", path)
        return self.service.extraction_payload(match["extraction_id"])

    def _extract_evidence(self, body_path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        evidences = self.service.extract_evidence(
            str(body["document_id"]),
            actor=actor,
            parser_version=str(body.get("parser_version", "rule-0")),
            model_version=str(body.get("model_version", "rule-0")),
        )
        return {"evidence": [to_plain(e) for e in evidences]}

    def _parse_document_with_paddleocr(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.parse_document_with_paddleocr(body, actor=actor)

    def _list_manual_reviews(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.manual_review_payload(body)

    def _evidence_quality_report(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.evidence_quality_report(body)

    def _create_thesis(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.create_thesis(body, actor=actor))

    def _get_thesis(self, path: str, _body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        match = re.fullmatch(r"^/api/thesis/(?P<thesis_id>[^/]+)$", path)
        return self.service.thesis_payload(match["thesis_id"])

    def _run_scoring(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.run_scoring(body, actor=actor))

    def _register_crowding_snapshot(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.register_crowding_snapshot(body, actor=actor))

    def _run_challenger(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.run_challenger(body, actor=actor))

    def _register_playbook(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.register_playbook(body, actor=actor))

    def _seed_default_playbooks(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.seed_default_incident_playbooks(body, actor=actor)

    def _register_drill_schedule(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.register_drill_schedule(body, actor=actor))

    def _record_drill_result(self, path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        match = re.fullmatch(r"^/api/drill-schedules/(?P<schedule_id>[^/]+)/result$", path)
        return to_plain(self.service.record_drill_result(match["schedule_id"], body, actor=actor))

    def _create_incident_report(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.create_incident_report(body, actor=actor))

    def _register_alert_rule(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.register_alert_rule(body, actor=actor))

    def _seed_default_alert_rules(self, _path: str, _body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return {"rules": [to_plain(item) for item in self.service.seed_default_alert_rules(actor=actor)]}

    def _evaluate_alerts(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.evaluate_alerts(body, actor=actor)

    def _create_incidents_from_alerts(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.create_incidents_from_alerts(body, actor=actor)

    def _notify_alerts(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.notify_alerts(body, actor=actor)

    def _deliver_alert_notifications(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.deliver_alert_notifications(body, actor=actor)

    def _list_alert_notifications(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.alert_notifications_payload(body)

    def _list_alerts(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.alerts_payload(body)

    def _seed_llm_task_templates(self, _path: str, _body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return {"templates": [to_plain(item) for item in self.service.seed_default_llm_task_templates(actor=actor)]}

    def _register_llm_task_template(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.register_llm_task_template(body, actor=actor))

    def _list_llm_task_templates(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.llm_task_templates_payload(body)

    def _run_llm_task(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.run_llm_task(body, actor=actor))

    def _list_llm_task_runs(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.llm_task_runs_payload(body)

    def _llm_task_review_queue(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.llm_task_review_queue(body)

    def _llm_task_escalation_report(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.llm_task_escalation_report(body)

    def _notify_llm_task_escalations(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.create_llm_task_escalation_notifications(body, actor=actor)

    def _llm_budget_approvals(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.llm_budget_approvals_payload(body)

    def _request_llm_budget_approval(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.request_llm_budget_approval(body, actor=actor))

    def _decide_llm_budget_approval(self, path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        match = re.fullmatch(r"^/api/llm/budget-approvals/(?P<approval_id>[^/]+)/decide$", path)
        return to_plain(self.service.decide_llm_budget_approval(match["approval_id"], body, actor=actor))

    def _sync_llm_budget_approval(self, path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        match = re.fullmatch(r"^/api/llm/budget-approvals/(?P<approval_id>[^/]+)/sync$", path)
        return self.service.sync_llm_budget_approval(match["approval_id"], body, actor=actor)

    def _llm_readiness_report(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.llm_readiness_report(body, actor=actor)

    def _llm_task_metrics(self, _path: str, _body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.llm_task_metrics()

    def _llm_openai_chat_completions(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.llm_openai_chat_completions(body, actor=actor)

    def _llm_anthropic_messages(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.llm_anthropic_messages(body, actor=actor)

    def _register_workflow_definition(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.register_workflow_definition(body, actor=actor))

    def _list_workflow_definitions(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.workflow_definitions_payload(body)

    def _run_workflow_definition(self, path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        match = re.fullmatch(r"^/api/orchestration/dags/(?P<dag_id>[^/]+)/run$", path)
        return to_plain(self.service.run_workflow_definition(match["dag_id"], body, actor=actor))

    def _execute_workflow_definition(self, path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        match = re.fullmatch(r"^/api/orchestration/dags/(?P<dag_id>[^/]+)/execute$", path)
        return self.service.execute_workflow_definition(match["dag_id"], body, actor=actor)

    def _backfill_workflow_definition(self, path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        match = re.fullmatch(r"^/api/orchestration/dags/(?P<dag_id>[^/]+)/backfill$", path)
        return self.service.backfill_workflow_definition(match["dag_id"], body, actor=actor)

    def _retry_workflow_run(self, path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        match = re.fullmatch(r"^/api/orchestration/runs/(?P<run_id>[^/]+)/retry$", path)
        return to_plain(self.service.retry_workflow_run(match["run_id"], body, actor=actor))

    def _list_workflow_runs(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.workflow_runs_payload(body)

    def _workflow_sla_report(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.workflow_sla_report(body)

    def _create_workflow_incidents(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.create_workflow_incidents_from_sla(body, actor=actor)

    def _workflow_schedule_calendar(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.workflow_schedule_calendar(body)

    def _workflow_scheduler_handoff(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.workflow_scheduler_handoff(body, actor=actor)

    def _orchestration_readiness_report(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.orchestration_readiness_report(body, actor=actor)

    def _workflow_dependency_graph(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.workflow_dependency_graph(body)

    def _workflow_openlineage_export(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.workflow_openlineage_export(body, actor=actor)

    def _submit_openlineage_export(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.create_openlineage_submission_notifications(body, actor=actor)

    def _record_lineage_event(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.record_lineage_event(body, actor=actor))

    def _list_lineage_events(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.lineage_events_payload(body)

    def _register_model_version(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.register_model_version(body, actor=actor))

    def _list_model_versions(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.model_versions_payload(body)

    def _mlflow_model_registry_export(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.mlflow_model_registry_export(body, actor=actor)

    def _submit_mlflow_model_registry_export(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.create_mlflow_registration_notifications(body, actor=actor)

    def _get_signal(self, path: str, _body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        match = re.fullmatch(r"^/api/signals/(?P<signal_id>[^/]+)$", path)
        return self.service.signal_payload(match["signal_id"])

    def _build_decision_pack(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.build_decision_pack(body, actor=actor))

    def _get_decision_pack(self, path: str, _body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        match = re.fullmatch(r"^/api/decision-packs/(?P<decision_id>[^/]+)$", path)
        return self.service.decision_payload(match["decision_id"])

    def _sign_decision(self, path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        match = re.fullmatch(r"^/api/approvals/(?P<decision_id>[^/]+)/sign$", path)
        return to_plain(self.service.sign_decision(match["decision_id"], body, actor=actor))

    def _create_execution_intent(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.create_execution_intent(body, actor=actor))

    def _get_execution_intent(self, path: str, _body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        match = re.fullmatch(r"^/api/execution-intents/(?P<intent_id>[^/]+)$", path)
        return self.service.execution_intent_payload(match["intent_id"])

    def _simulate_execution_intent(self, path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        match = re.fullmatch(r"^/api/execution-intents/(?P<intent_id>[^/]+)/simulate$", path)
        return self.service.simulate_execution_intent(match["intent_id"], body, actor=actor)

    def _list_simulated_executions(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.simulated_executions_payload(body)

    def _create_exception(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.create_exception(body, actor=actor)

    def _create_review(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.create_review(body, actor=actor))

    def _get_review(self, path: str, _body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        match = re.fullmatch(r"^/api/reviews/(?P<review_id>[^/]+)$", path)
        return self.service.review_payload(match["review_id"])

    def _generate_operating_report(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.generate_operating_report(body, actor=actor))

    def _operating_report_red_flag_reminders(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.operating_report_red_flag_reminders(body)

    def _publish_operating_report(self, path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        match = re.fullmatch(r"^/api/operating-reports/(?P<report_id>[^/]+)/publish$", path)
        return to_plain(self.service.publish_operating_report(match["report_id"], body, actor=actor))

    def _export_operating_report_board_pack(self, path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        match = re.fullmatch(r"^/api/operating-reports/(?P<report_id>[^/]+)/board-pack$", path)
        return self.service.export_operating_report_board_pack(match["report_id"], body, actor=actor)

    def _resolve_operating_report_red_flag(self, path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        match = re.fullmatch(r"^/api/operating-reports/(?P<report_id>[^/]+)/red-flags/(?P<red_flag_id>[^/]+)/resolve$", path)
        return to_plain(self.service.resolve_operating_report_red_flag(match["report_id"], match["red_flag_id"], body, actor=actor))

    def _get_operating_report(self, path: str, _body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        match = re.fullmatch(r"^/api/operating-reports/(?P<report_id>[^/]+)$", path)
        return self.service.operating_report_payload(match["report_id"])

    def _create_strategy_replay(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.create_strategy_replay(body, actor=actor))

    def _list_strategy_replays(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.list_strategy_replays(body)

    def _compare_strategy_replays(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.strategy_replay_compare_report(body)

    def _get_strategy_replay(self, path: str, _body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        match = re.fullmatch(r"^/api/strategy-replays/(?P<replay_id>[^/]+)$", path)
        return self.service.strategy_replay_payload(match["replay_id"])

    def _run_portfolio_optimizer(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.run_portfolio_optimizer(body, actor=actor))

    def _portfolio_optimizer_compare_report(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.portfolio_optimizer_compare_report(body, actor=actor)

    def _portfolio_optimizer_readiness_report(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.portfolio_optimizer_readiness_report(body, actor=actor)

    def _portfolio_forward_report(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.portfolio_forward_report(body, actor=actor)

    def _portfolio_attribution_readiness_report(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.portfolio_attribution_readiness_report(body, actor=actor)

    def _portfolio_returns(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.portfolio_returns_payload(body)

    def _portfolio_valuation(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.portfolio_valuation_payload(body)

    def _register_portfolio_transaction(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.register_portfolio_transaction(body, actor=actor))

    def _import_portfolio_transactions(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.import_portfolio_transactions(body, actor=actor)

    def _list_portfolio_transactions(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.portfolio_transactions_payload(body)

    def _portfolio_positions_from_transactions(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.portfolio_positions_from_transactions(body)

    def _list_portfolio_proposals(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.list_portfolio_proposals(body)

    def _get_portfolio_proposal(self, path: str, _body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        match = re.fullmatch(r"^/api/portfolio/proposals/(?P<proposal_id>[^/]+)$", path)
        return self.service.portfolio_proposal_payload(match["proposal_id"])

    def _portfolio_attribution_backfill(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        """POST /api/portfolio/attribution/backfill  (T-408)

        Computes simulated portfolio attribution for a date range and optionally
        backfills the result to existing operating reports. Always simulation-only.
        """
        return self.service.portfolio_attribution_backfill(body, actor=actor)

    def _portfolio_simulated_feedback(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        """POST /api/portfolio/simulated-feedback  (T-409)

        Investment committee approval entry and simulated portfolio feedback.
        Updates proposal status (approved/rejected) and returns valuation/returns
        feedback driven by public EOD market data. Paper portfolio only.
        """
        return self.service.portfolio_simulated_feedback(body, actor=actor)

    def _register_macro_theme(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.register_macro_theme(body, actor=actor))

    def _list_macro_themes(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.macro_themes_payload(body)

    def _register_industry_chain(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.register_industry_chain(body, actor=actor))

    def _list_industry_chains(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.industry_chains_payload(body)

    def _create_industry_chain_template_candidate(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.create_industry_chain_template_candidate(body, actor=actor)

    def _list_industry_chain_template_candidates(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        _ = actor
        return self.service.industry_chain_template_candidates_payload(body)

    def _get_industry_chain_template_candidate(self, path: str, _body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        _ = actor
        match = re.fullmatch(r"^/api/industry-chains/template-candidates/(?P<candidate_id>[^/]+)$", path)
        return self.service.industry_chain_template_candidate_payload(match["candidate_id"])

    def _submit_industry_chain_template_candidate(self, path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        match = re.fullmatch(r"^/api/industry-chains/template-candidates/(?P<candidate_id>[^/]+)/(?:submit|submit-review)$", path)
        return self.service.submit_industry_chain_template_candidate(match["candidate_id"], body, actor=actor)

    def _review_industry_chain_template_candidate(self, path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        match = re.fullmatch(r"^/api/industry-chains/template-candidates/(?P<candidate_id>[^/]+)/review$", path)
        return self.service.review_industry_chain_template_candidate(match["candidate_id"], body, actor=actor)

    def _publish_industry_chain_template_candidate(self, path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        match = re.fullmatch(r"^/api/industry-chains/template-candidates/(?P<candidate_id>[^/]+)/publish$", path)
        return self.service.publish_industry_chain_template_candidate(match["candidate_id"], body, actor=actor)

    def _industry_chain_analysis(self, path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        match = re.fullmatch(r"^/api/industry-chains/(?P<chain_id>[^/]+)/analysis$", path)
        return self.service.industry_chain_analysis_payload(match["chain_id"], body, actor=actor)

    def _industry_chain_panorama(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.industry_chain_panorama_payload(body, actor=actor)

    def _industry_chain_panorama_readiness_report(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.industry_chain_panorama_readiness_report(body, actor=actor)

    def _list_company_positions(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.company_positions_payload(body)

    def _company_positions_schema(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.company_positions_schema_payload(body)

    def _company_positions_coverage_report(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.company_positions_coverage_report(body)

    def _register_company_profile(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.register_company_profile(body, actor=actor))

    def _list_company_profiles(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.company_profiles_payload(body)

    def _company_profile_schema(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.company_profile_schema_payload(body)

    def _register_financial_metric(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.register_financial_metric(body, actor=actor))

    def _list_financial_metrics(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.financial_metrics_payload(body)

    def _bootstrap_company_database(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.bootstrap_company_database(body, actor=actor)

    def _import_company_watchlist(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.import_company_watchlist(body, actor=actor)

    def _extract_company_profile_fields(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.extract_company_profile_fields(body, actor=actor)

    def _company_profile_field_assertions(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.company_profile_field_assertions_payload(body)

    def _review_company_profile_field_assertion(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.review_company_profile_field_assertion(body, actor=actor)

    def _company_material_inbox_ingest(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.company_material_inbox_ingest(body, actor=actor)

    def _build_company_database(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.build_company_database(body, actor=actor)

    def _build_company_database_batch(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.build_company_database_batch(body, actor=actor)

    def _retry_company_database_build_run(self, path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        match = re.fullmatch(r"^/api/company-database/batch/runs/(?P<run_id>[^/]+)/retry$", path)
        return self.service.retry_company_database_build_run(match["run_id"], body, actor=actor)

    def _company_database_build_runs(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.company_database_build_runs_payload(body)

    def _company_package_import_runs(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.company_package_import_runs_payload(body)

    def _company_package_import_material_manifests(self, path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        match = re.fullmatch(r"^/api/company-database/(?:package|watchlist)/import/runs/(?P<run_id>[^/]+)/material-manifests$", path)
        return self.service.company_package_import_material_manifests(match["run_id"], body, actor=actor)

    def _company_material_inbox_pending(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.company_material_inbox_pending(body, actor=actor)

    def _company_database_coverage_trends(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.company_database_coverage_trends(body, actor=actor)

    def _company_database_coverage_audit(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.company_database_coverage_audit(body, actor=actor)

    def _reconcile_company_database_quality(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.reconcile_company_database_quality(body, actor=actor)

    def _data_health_runs_summary(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.data_health_runs_summary(body, actor=actor)

    def _data_health_summary(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.data_health_summary(body, actor=actor)

    def _company_profile_coverage_audit(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.company_profile_coverage_audit(body, actor=actor)

    def _build_company_events(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.build_company_events(body, actor=actor)

    def _build_company_relationships(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.build_company_relationships(body, actor=actor)

    def _build_company_workflow(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.build_company_workflow(body, actor=actor)

    def _register_company_event(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.register_company_event(body, actor=actor))

    def _list_company_events(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.company_events_payload(body)

    def _review_company_events(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.review_company_events(body, actor=actor)

    def _review_company_event(self, path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        match = re.fullmatch(r"^/api/company-events/(?P<event_id>[^/]+)/review$", path)
        return to_plain(self.service.review_company_event(match["event_id"], body, actor=actor))

    def _register_company_relationship(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.register_company_relationship(body, actor=actor))

    def _list_company_relationships(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.company_relationships_payload(body)

    def _review_company_relationships(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.review_company_relationships(body, actor=actor)

    def _review_company_relationship(self, path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        match = re.fullmatch(r"^/api/company-relationships/(?P<relationship_id>[^/]+)/review$", path)
        return to_plain(self.service.review_company_relationship(match["relationship_id"], body, actor=actor))

    def _register_structured_research_report(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.register_structured_research_report(body, actor=actor))

    def _list_structured_research_reports(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.structured_research_reports_payload(body)

    def _register_report_viewpoint(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.register_report_viewpoint(body, actor=actor))

    def _list_report_viewpoints(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.report_viewpoints_payload(body)

    def _register_report_forecast(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.register_report_forecast(body, actor=actor))

    def _list_report_forecasts(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.report_forecasts_payload(body)

    def _register_analyst_profile(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.register_analyst_profile(body, actor=actor))

    def _list_analyst_profiles(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.analyst_profiles_payload(body)

    def _compute_analyst_reliability_score(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.compute_analyst_reliability_score(body, actor=actor))

    def _list_analyst_reliability_scores(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.analyst_reliability_scores_payload(body)

    def _register_observation_item(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.register_observation_item(body, actor=actor))

    def _list_observation_items(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.observation_items_payload(body)

    def _create_analysis_conclusion(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.create_analysis_conclusion(body, actor=actor))

    def _list_analysis_conclusions(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.analysis_conclusions_payload(body)

    def _record_simulation_feedback(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.record_simulation_feedback(body, actor=actor))

    def _list_simulation_feedback(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.simulation_feedback_payload(body)

    def _update_simulation_feedback_performance(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.update_simulation_feedback_performance(body, actor=actor)

    def _register_hotspot_lexicon(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.register_hotspot_lexicon(body, actor=actor))

    def _list_hotspot_lexicons(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.hotspot_lexicons_payload(body)

    def _register_company_position(self, path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        match = re.fullmatch(r"^/api/industry-chains/(?P<chain_id>[^/]+)/companies$", path)
        return to_plain(self.service.register_company_position(match["chain_id"], body, actor=actor))

    def _hotspot_expansion(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.hotspot_expansion(body, actor=actor)

    def _hotspot_readiness_report(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.hotspot_readiness_report(body, actor=actor)

    def _register_research_task(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.register_research_task(body, actor=actor))

    def _list_research_tasks(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.research_tasks_payload(body)

    def _create_research_tasks_from_hotspot(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.create_research_tasks_from_hotspot(body, actor=actor)

    def _create_research_tasks_from_hotspot_batch(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.create_research_tasks_from_hotspot_batch(body, actor=actor)

    def _update_research_task_status(self, path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        match = re.fullmatch(r"^/api/research/tasks/(?P<task_id>[^/]+)/status$", path)
        return to_plain(self.service.update_research_task_status(match["task_id"], body, actor=actor))

    def _chokepoint_readiness_report(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.chokepoint_readiness_report(body, actor=actor)

    def _create_chokepoint_research_run(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.create_chokepoint_research_run(body, actor=actor))

    def _list_chokepoint_research_runs(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.chokepoint_research_runs_payload(body)

    def _get_chokepoint_research_run(self, path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        match = re.fullmatch(r"^/api/chokepoint/runs/(?P<run_id>[^/]+)$", path)
        return to_plain(self.service.get_chokepoint_research_run(match["run_id"]))

    def _run_chokepoint_research_step(self, path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        match = re.fullmatch(r"^/api/chokepoint/runs/(?P<run_id>[^/]+)/steps/(?P<step_id>[^/]+)/run$", path)
        return to_plain(self.service.run_chokepoint_research_step(match["run_id"], match["step_id"], body, actor=actor))

    def _run_chokepoint_research_pipeline(self, path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        match = re.fullmatch(r"^/api/chokepoint/runs/(?P<run_id>[^/]+)/run$", path)
        return to_plain(self.service.run_chokepoint_research_pipeline(match["run_id"], body, actor=actor))

    def _finalize_chokepoint_research_run(self, path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        match = re.fullmatch(r"^/api/chokepoint/runs/(?P<run_id>[^/]+)/finalize$", path)
        return to_plain(self.service.finalize_chokepoint_research_run(match["run_id"], body, actor=actor))

    def _review_chokepoint_research_run(self, path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        match = re.fullmatch(r"^/api/chokepoint/runs/(?P<run_id>[^/]+)/review$", path)
        return to_plain(self.service.review_chokepoint_research_run(match["run_id"], body, actor=actor))

    def _create_chokepoint_verification_tasks(self, path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        match = re.fullmatch(r"^/api/chokepoint/runs/(?P<run_id>[^/]+)/verification-tasks$", path)
        return self.service.create_chokepoint_verification_tasks(match["run_id"], body, actor=actor)

    def _query_graph(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.query_graph(body)

    def _company_intelligence_by_symbol(self, path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        match = re.fullmatch(r"^/api/company-intelligence/(?P<symbol>[^/]+)$", path)
        payload = dict(body)
        payload["symbol"] = match["symbol"] if match else payload.get("symbol", "")
        return self.service.company_intelligence(payload)

    def _run_company_intelligence_cycle(self, path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        match = re.fullmatch(r"^/api/company-intelligence/(?P<symbol>[^/]+)/cycle/run$", path)
        payload = dict(body)
        payload["symbol"] = match["symbol"] if match else payload.get("symbol", "")
        return self.service.run_company_intelligence_cycle(payload, actor=actor)

    def _company_intelligence_cycle_runs(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.company_intelligence_cycle_runs_payload(body)

    def _graph_traceability_report(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.graph_traceability_report(body)

    def _graph_edge_quality_report(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.graph_edge_quality_report(body)

    def _graph_neo4j_export(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.graph_neo4j_export(body, actor=actor)

    def _sync_graph_neo4j(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.create_graph_adapter_sync_notifications(body, actor=actor)

    def _graph_vector_readiness_report(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.graph_vector_readiness_report(body, actor=actor)

    def _search(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.search(body)

    def _qdrant_vector_export(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.qdrant_vector_export(body, actor=actor)

    def _sync_qdrant_vectors(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.create_qdrant_sync_notifications(body, actor=actor)

    def _adapter_sync_retry_drill(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.adapter_sync_retry_drill(body, actor=actor)

    def _rebuild_search_indexes(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.rebuild_search_indexes(body, actor=actor)

    def _semantic_search(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.semantic_search(body)

    def _semantic_rerank(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.semantic_rerank(body)

    def _semantic_llm_rerank(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.semantic_llm_rerank(body, actor=actor)

    def _semantic_llm_rerank_benchmark(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.semantic_llm_rerank_benchmark(body, actor=actor)

    def _semantic_search_benchmark(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.semantic_search_benchmark(body)

    def _dashboard_ceo(self, _path: str, _body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.dashboard()

    def _dashboard_risk(self, _path: str, _body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.dashboard()

    def _readiness_checklist(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.readiness_checklist_payload(body)

    def _record_capacity_baseline(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.record_capacity_baseline_result(body, actor=actor)

    def _record_readiness_check(self, path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        match = re.fullmatch(r"^/api/readiness/checklist/(?P<check_id>[^/]+)$", path)
        check_id = match["check_id"] if match else str(body.get("check_id", ""))
        return to_plain(self.service.record_readiness_check(check_id, body, actor=actor))

    def _readiness_deployment_report(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.readiness_deployment_report(body, actor=actor)

    def _readiness_ui_report(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.ui_readiness_report(body, actor=actor)

    def _vision_acceptance_report(self, _path: str, _body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.vision_acceptance_report()

    def _readiness_evidence_package(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.readiness_evidence_package(body, actor=actor)

    def _notify_readiness_evidence_package(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.create_readiness_evidence_notifications(body, actor=actor)

    def _readiness_remediation_report(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.readiness_remediation_report(body)

    def _incident_calendar(self, _path: str, _body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.incident_calendar()


def create_default_router() -> ApiRouter:
    return ApiRouter()
