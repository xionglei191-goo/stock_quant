from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass, field, fields, is_dataclass
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Callable, Mapping, Sequence

from .market_data_storage import upsert_market_data_bar as upsert_typed_market_data_bar

from .models import (
    AuditEvent,
    AlertNotification,
    AlertRule,
    AnalystProfile,
    AnalystReliabilityScore,
    AnalysisConclusion,
    AStockConnectorDefinition,
    BenchmarkConfig,
    BenchmarkResult,
    BenchmarkRun,
    BenchmarkSample,
    CacheRetentionRunRecord,
    ChokepointResearchRun,
    CorporateAction,
    CompanyDatabaseBuildRun,
    CompanyIntelligenceCycleRun,
    CompanyPackageImportRun,
    CompanyEvent,
    CompanyPosition,
    CompanyProfile,
    CompanyProfileFieldAssertion,
    CompanyRelationship,
    DailyMainlineQueueItem,
    DailyMainlineRun,
    DailyWatchlistEntry,
    DrillSchedule,
    DisclosureEvent,
    EntityMapping,
    EntityMappingLabel,
    ChallengerResult,
    CrowdingSnapshot,
    DecisionPack,
    DecisionSignature,
    Document,
    Evidence,
    ExecutionIntent,
    ExtractionResult,
    ExceptionItem,
    FinancialMetric,
    IngestionJob,
    IngestionSchedule,
    IncidentPlaybook,
    IncidentReport,
    InstitutionalHolding,
    IndustryChain,
    IndustryChainTemplateCandidate,
    IndustryChainTemplateReview,
    Issuer,
    HotspotLexicon,
    LineageEvent,
    LLMBudgetApproval,
    LLMTaskRun,
    LLMTaskTemplate,
    ManualReviewItem,
    MarketDataPoint,
    MacroTheme,
    ModelVersionRecord,
    ObservationItem,
    OperatingReport,
    PortfolioProposal,
    PortfolioTransaction,
    PromptChangeRequest,
    ReadinessCheckRecord,
    ResearchAnswer,
    ResearchCard,
    ResearchReport,
    ResearchReportAsset,
    ResearchTask,
    ResearchTemplate,
    ResearchSignal,
    ReportForecast,
    ReportViewpoint,
    ReviewRecord,
    Security,
    SecretRotationRecord,
    UsageMetric,
    SimulatedExecution,
    SimulationFeedback,
    ScorecardProfile,
    SourceReviewRecord,
    SourceDefinition,
    StrategyReplay,
    SystemAlert,
    ThesisCard,
    WorkflowDefinition,
    WorkflowRun,
)
from .utils import parse_datetime, to_plain


CollectionSpec = tuple[str, str, type]
BASELINE_SCHEMA_VERSION = "0001_baseline_jsonb_records"


COLLECTIONS: tuple[CollectionSpec, ...] = (
    ("sources", "source_id", SourceDefinition),
    ("source_reviews", "review_id", SourceReviewRecord),
    ("astock_connectors", "connector_id", AStockConnectorDefinition),
    ("ingestion_jobs", "job_id", IngestionJob),
    ("ingestion_schedules", "schedule_id", IngestionSchedule),
    ("issuers", "issuer_id", Issuer),
    ("securities", "security_id", Security),
    ("market_data", "data_id", MarketDataPoint),
    ("corporate_actions", "action_id", CorporateAction),
    ("documents", "document_id", Document),
    ("evidence", "evidence_id", Evidence),
    ("theses", "thesis_id", ThesisCard),
    ("signals", "signal_id", ResearchSignal),
    ("decisions", "decision_id", DecisionPack),
    ("execution_intents", "intent_id", ExecutionIntent),
    ("simulated_executions", "execution_id", SimulatedExecution),
    ("reviews", "review_id", ReviewRecord),
    ("manual_reviews", "review_id", ManualReviewItem),
    ("operating_reports", "report_id", OperatingReport),
    ("strategy_replays", "replay_id", StrategyReplay),
    ("portfolio_proposals", "proposal_id", PortfolioProposal),
    ("portfolio_transactions", "transaction_id", PortfolioTransaction),
    ("macro_themes", "theme_id", MacroTheme),
    ("industry_chains", "chain_id", IndustryChain),
    ("industry_chain_template_candidates", "candidate_id", IndustryChainTemplateCandidate),
    ("industry_chain_template_reviews", "review_id", IndustryChainTemplateReview),
    ("company_positions", "position_id", CompanyPosition),
    ("company_database_build_runs", "run_id", CompanyDatabaseBuildRun),
    ("company_intelligence_cycle_runs", "run_id", CompanyIntelligenceCycleRun),
    ("company_package_import_runs", "run_id", CompanyPackageImportRun),
    ("company_profiles", "issuer_id", CompanyProfile),
    ("company_profile_field_assertions", "assertion_id", CompanyProfileFieldAssertion),
    ("financial_metrics", "metric_id", FinancialMetric),
    ("company_events", "event_id", CompanyEvent),
    ("company_relationships", "relationship_id", CompanyRelationship),
    ("hotspot_lexicons", "lexicon_id", HotspotLexicon),
    ("research_tasks", "task_id", ResearchTask),
    ("chokepoint_research_runs", "run_id", ChokepointResearchRun),
    ("benchmarks", "benchmark_id", BenchmarkConfig),
    ("benchmark_samples", "sample_id", BenchmarkSample),
    ("benchmark_results", "result_id", BenchmarkResult),
    ("benchmark_runs", "run_id", BenchmarkRun),
    ("extraction_results", "extraction_id", ExtractionResult),
    ("entity_mappings", "mapping_id", EntityMapping),
    ("entity_mapping_labels", "label_id", EntityMappingLabel),
    ("scorecards", "profile_id", ScorecardProfile),
    ("drill_schedules", "schedule_id", DrillSchedule),
    ("readiness_checks", "check_id", ReadinessCheckRecord),
    ("secret_rotations", "rotation_id", SecretRotationRecord),
    ("cache_retention_runs", "run_id", CacheRetentionRunRecord),
    ("prompt_changes", "request_id", PromptChangeRequest),
    ("llm_budget_approvals", "approval_id", LLMBudgetApproval),
    ("llm_task_templates", "template_id", LLMTaskTemplate),
    ("llm_task_runs", "run_id", LLMTaskRun),
    ("workflow_definitions", "dag_id", WorkflowDefinition),
    ("workflow_runs", "run_id", WorkflowRun),
    ("lineage_events", "lineage_id", LineageEvent),
    ("model_versions", "model_version_id", ModelVersionRecord),
    ("templates", "template_id", ResearchTemplate),
    ("research_answers", "answer_id", ResearchAnswer),
    ("research_cards", "card_id", ResearchCard),
    ("research_reports", "report_id", ResearchReportAsset),
    ("structured_research_reports", "research_report_id", ResearchReport),
    ("report_viewpoints", "viewpoint_id", ReportViewpoint),
    ("report_forecasts", "forecast_id", ReportForecast),
    ("analyst_profiles", "analyst_id", AnalystProfile),
    ("analyst_reliability_scores", "score_id", AnalystReliabilityScore),
    ("crowding", "snapshot_id", CrowdingSnapshot),
    ("institutional_holdings", "holding_id", InstitutionalHolding),
    ("disclosure_events", "event_id", DisclosureEvent),
    ("observation_items", "observation_id", ObservationItem),
    ("analysis_conclusions", "analysis_conclusion_id", AnalysisConclusion),
    ("simulation_feedback", "simulation_feedback_id", SimulationFeedback),
    ("challengers", "challenger_id", ChallengerResult),
    ("playbooks", "playbook_id", IncidentPlaybook),
    ("incident_reports", "report_id", IncidentReport),
    ("alert_rules", "rule_id", AlertRule),
    ("system_alerts", "alert_id", SystemAlert),
    ("alert_notifications", "notification_id", AlertNotification),
    ("exceptions", "exception_id", ExceptionItem),
    ("usage_metrics", "feature", UsageMetric),
    ("daily_mainline_runs", "run_id", DailyMainlineRun),
    ("daily_mainline_queue_items", "item_id", DailyMainlineQueueItem),
    ("daily_watchlist_entries", "entry_id", DailyWatchlistEntry),
)


_COLLECTION_BY_NAME = {collection: (key_field, model_type) for collection, key_field, model_type in COLLECTIONS}


def _candidate_collections_for_resource(resource_type: str) -> list[str]:
    normalized = resource_type.strip().replace("-", "_")
    aliases = {
        "source": "sources",
        "source_review": "source_reviews",
        "astock_connector": "astock_connectors",
        "ingestion_job": "ingestion_jobs",
        "ingestion_schedule": "ingestion_schedules",
        "issuer": "issuers",
        "security": "securities",
        "market_data_point": "market_data",
        "market_data": "market_data",
        "corporate_action": "corporate_actions",
        "document": "documents",
        "evidence": "evidence",
        "thesis": "theses",
        "thesis_card": "theses",
        "signal": "signals",
        "research_signal": "signals",
        "decision": "decisions",
        "decision_pack": "decisions",
        "execution_intent": "execution_intents",
        "simulated_execution": "simulated_executions",
        "review": "reviews",
        "manual_review": "manual_reviews",
        "operating_report": "operating_reports",
        "strategy_replay": "strategy_replays",
        "portfolio_proposal": "portfolio_proposals",
        "portfolio_transaction": "portfolio_transactions",
        "macro_theme": "macro_themes",
        "industry_chain": "industry_chains",
        "industry_chain_template_candidate": "industry_chain_template_candidates",
        "industry_chain_template_review": "industry_chain_template_reviews",
        "company_position": "company_positions",
        "company_database_build_run": "company_database_build_runs",
        "company_intelligence_cycle_run": "company_intelligence_cycle_runs",
        "company_package_import_run": "company_package_import_runs",
        "company_profile": "company_profiles",
        "company_profile_field_assertion": "company_profile_field_assertions",
        "company_profile_field": "company_profile_field_assertions",
        "financial_metric": "financial_metrics",
        "company_event": "company_events",
        "company_relationship": "company_relationships",
        "hotspot_lexicon": "hotspot_lexicons",
        "research_task": "research_tasks",
        "chokepoint_research_run": "chokepoint_research_runs",
        "benchmark": "benchmarks",
        "benchmark_config": "benchmarks",
        "benchmark_sample": "benchmark_samples",
        "benchmark_result": "benchmark_results",
        "benchmark_run": "benchmark_runs",
        "extraction_result": "extraction_results",
        "entity_mapping": "entity_mappings",
        "entity_mapping_label": "entity_mapping_labels",
        "scorecard": "scorecards",
        "scorecard_profile": "scorecards",
        "drill_schedule": "drill_schedules",
        "readiness_check": "readiness_checks",
        "secret_rotation": "secret_rotations",
        "cache_retention_run": "cache_retention_runs",
        "prompt_change": "prompt_changes",
        "llm_budget_approval": "llm_budget_approvals",
        "llm_task_template": "llm_task_templates",
        "llm_task_run": "llm_task_runs",
        "workflow_definition": "workflow_definitions",
        "workflow_run": "workflow_runs",
        "lineage_event": "lineage_events",
        "model_version": "model_versions",
        "template": "templates",
        "research_answer": "research_answers",
        "research_card": "research_cards",
        "research_report": "research_reports",
        "research_report_asset": "research_reports",
        "structured_research_report": "structured_research_reports",
        "report_viewpoint": "report_viewpoints",
        "report_forecast": "report_forecasts",
        "analyst_profile": "analyst_profiles",
        "analyst_reliability_score": "analyst_reliability_scores",
        "crowding": "crowding",
        "crowding_snapshot": "crowding",
        "institutional_holding": "institutional_holdings",
        "disclosure_event": "disclosure_events",
        "observation_item": "observation_items",
        "analysis_conclusion": "analysis_conclusions",
        "simulation_feedback": "simulation_feedback",
        "challenger": "challengers",
        "challenger_result": "challengers",
        "playbook": "playbooks",
        "incident_playbook": "playbooks",
        "incident_report": "incident_reports",
        "alert_rule": "alert_rules",
        "system_alert": "system_alerts",
        "alert_notification": "alert_notifications",
        "graph": "alert_notifications",
        "exception": "exceptions",
        "exception_item": "exceptions",
    }
    candidates = [aliases.get(normalized, ""), normalized, f"{normalized}s"]
    if normalized.endswith("y"):
        candidates.append(f"{normalized[:-1]}ies")
    if normalized.endswith("_run"):
        candidates.append(f"{normalized}s")
    return [item for item in candidates if item in _COLLECTION_BY_NAME]


DATETIME_FIELDS: dict[type, tuple[str, ...]] = {
    Evidence: ("created_at",),
    SourceReviewRecord: ("reviewed_at", "next_review_due_at"),
    AStockConnectorDefinition: ("last_checked_at",),
    IngestionJob: ("started_at", "completed_at"),
    IngestionSchedule: ("next_run_at", "created_at", "updated_at"),
    MarketDataPoint: ("created_at",),
    CorporateAction: ("created_at",),
    ThesisCard: ("valid_from", "valid_to"),
    ResearchSignal: ("generated_at",),
    DecisionPack: ("created_at",),
    ExecutionIntent: ("created_at",),
    SimulatedExecution: ("created_at",),
    ReviewRecord: ("created_at",),
    ManualReviewItem: ("created_at", "updated_at"),
    OperatingReport: ("created_at", "published_at"),
    StrategyReplay: ("created_at",),
    PortfolioProposal: ("created_at",),
    PortfolioTransaction: ("created_at",),
    MacroTheme: ("created_at",),
    IndustryChain: ("created_at", "published_at"),
    IndustryChainTemplateCandidate: ("created_at", "updated_at", "submitted_at", "published_at"),
    IndustryChainTemplateReview: ("created_at",),
    CompanyPosition: ("created_at",),
    CompanyDatabaseBuildRun: ("started_at", "completed_at", "created_at"),
    CompanyPackageImportRun: ("started_at", "completed_at", "created_at"),
    CompanyProfile: ("updated_at",),
    CompanyProfileFieldAssertion: ("as_of_date", "created_at", "updated_at"),
    FinancialMetric: ("period_start", "period_end", "created_at", "updated_at"),
    CompanyEvent: ("occurred_at", "detected_at", "created_at"),
    CompanyRelationship: ("valid_from", "valid_to", "created_at"),
    HotspotLexicon: ("created_at",),
    ResearchTask: ("created_at", "updated_at"),
    ChokepointResearchRun: ("created_at", "updated_at"),
    BenchmarkConfig: ("created_at",),
    BenchmarkSample: ("created_at",),
    BenchmarkResult: ("created_at",),
    BenchmarkRun: ("created_at",),
    ExtractionResult: ("created_at",),
    PromptChangeRequest: ("created_at",),
    EntityMapping: ("valid_from", "valid_to", "recorded_at", "created_at"),
    EntityMappingLabel: ("created_at",),
    ResearchTemplate: ("created_at",),
    ResearchAnswer: ("created_at", "updated_at"),
    ResearchCard: ("created_at",),
    ResearchReportAsset: ("indexed_at",),
    ResearchReport: ("published_at", "created_at", "updated_at"),
    ReportViewpoint: ("realization_checked_at", "created_at"),
    ReportForecast: ("checked_at", "created_at"),
    AnalystProfile: ("first_seen_at", "last_seen_at"),
    AnalystReliabilityScore: ("computed_at",),
    CrowdingSnapshot: ("created_at",),
    InstitutionalHolding: ("created_at",),
    DisclosureEvent: ("occurred_at", "created_at"),
    ObservationItem: ("due_at", "created_at", "closed_at"),
    AnalysisConclusion: ("valid_from", "valid_to", "created_at", "updated_at"),
    SimulationFeedback: ("start_at", "end_at", "created_at", "updated_at"),
    ChallengerResult: ("created_at",),
    IncidentPlaybook: ("created_at",),
    IncidentReport: ("created_at",),
    AlertRule: ("created_at", "updated_at"),
    SystemAlert: ("created_at", "updated_at"),
    AlertNotification: ("created_at",),
    ExceptionItem: ("created_at",),
    ScorecardProfile: ("created_at",),
    DrillSchedule: ("next_run_at", "last_run_at"),
    ReadinessCheckRecord: ("measured_at", "expires_at", "updated_at"),
    SecretRotationRecord: ("rotated_at", "next_rotation_due_at", "created_at"),
    CacheRetentionRunRecord: ("executed_at", "as_of", "created_at"),
    LLMBudgetApproval: ("expires_at", "created_at", "updated_at"),
    LLMTaskTemplate: ("created_at", "updated_at"),
    LLMTaskRun: ("created_at",),
    WorkflowDefinition: ("created_at", "updated_at"),
    WorkflowRun: ("started_at", "completed_at"),
    LineageEvent: ("created_at",),
    ModelVersionRecord: ("created_at",),
    UsageMetric: ("first_seen_at", "last_seen_at"),
    DailyMainlineRun: ("created_at",),
    DailyMainlineQueueItem: ("created_at",),
    DailyWatchlistEntry: ("joined_at",),
}


OPTIONAL_DATETIME_FIELDS: dict[type, tuple[str, ...]] = {
    OperatingReport: ("published_at",),
    IndustryChain: ("published_at",),
    IndustryChainTemplateCandidate: ("submitted_at", "published_at"),
    CompanyRelationship: ("valid_from", "valid_to"),
    CompanyProfileFieldAssertion: ("as_of_date",),
    SourceReviewRecord: ("next_review_due_at",),
    AStockConnectorDefinition: ("last_checked_at",),
    ReadinessCheckRecord: ("expires_at",),
    DrillSchedule: ("last_run_at",),
    SecretRotationRecord: ("next_rotation_due_at",),
    CacheRetentionRunRecord: ("executed_at",),
    EntityMapping: ("valid_to",),
    ReportViewpoint: ("realization_checked_at",),
    ReportForecast: ("checked_at",),
    ObservationItem: ("due_at", "closed_at"),
    AnalysisConclusion: ("valid_to",),
    SimulationFeedback: ("end_at",),
    LLMBudgetApproval: ("expires_at",),
}


def _hydrate_signature(data: dict[str, Any]) -> DecisionSignature:
    return DecisionSignature(
        role=str(data["role"]),
        user=str(data["user"]),
        signed_at=parse_datetime(data.get("signed_at")),
        comment=str(data.get("comment", "")),
    )


def _hydrate_model(model_type: type, data: dict[str, Any]) -> Any:
    if model_type in {SourceDefinition, SourceReviewRecord, AStockConnectorDefinition, Issuer, Security, MarketDataPoint, Document, InstitutionalHolding, ResearchReportAsset}:
        return model_type.from_dict(data)
    if model_type is DecisionPack:
        data = dict(data)
        data["signatures"] = [_hydrate_signature(item) for item in data.get("signatures", [])]
    for field_name in DATETIME_FIELDS.get(model_type, ()):
        if field_name in OPTIONAL_DATETIME_FIELDS.get(model_type, ()) and data.get(field_name) in {None, ""}:
            data[field_name] = None
        else:
            data[field_name] = parse_datetime(data.get(field_name))
    if is_dataclass(model_type):
        allowed_fields = {item.name for item in fields(model_type)}
        data = {key: value for key, value in data.items() if key in allowed_fields}
    return model_type(**data)


def _hydrate_audit_event(data: dict[str, Any]) -> AuditEvent:
    data = dict(data)
    data["timestamp"] = parse_datetime(data.get("timestamp"))
    return AuditEvent(**data)


def _json_payload(data: Any) -> dict[str, Any]:
    if isinstance(data, str):
        return json.loads(data)
    return dict(data)


@dataclass(slots=True)
class InMemoryStore:
    sources: dict[str, SourceDefinition] = field(default_factory=dict)
    source_reviews: dict[str, SourceReviewRecord] = field(default_factory=dict)
    astock_connectors: dict[str, AStockConnectorDefinition] = field(default_factory=dict)
    ingestion_jobs: dict[str, IngestionJob] = field(default_factory=dict)
    ingestion_schedules: dict[str, IngestionSchedule] = field(default_factory=dict)
    issuers: dict[str, Issuer] = field(default_factory=dict)
    securities: dict[str, Security] = field(default_factory=dict)
    market_data: dict[str, MarketDataPoint] = field(default_factory=dict)
    corporate_actions: dict[str, CorporateAction] = field(default_factory=dict)
    documents: dict[str, Document] = field(default_factory=dict)
    evidence: dict[str, Evidence] = field(default_factory=dict)
    theses: dict[str, ThesisCard] = field(default_factory=dict)
    signals: dict[str, ResearchSignal] = field(default_factory=dict)
    decisions: dict[str, DecisionPack] = field(default_factory=dict)
    execution_intents: dict[str, ExecutionIntent] = field(default_factory=dict)
    simulated_executions: dict[str, SimulatedExecution] = field(default_factory=dict)
    reviews: dict[str, ReviewRecord] = field(default_factory=dict)
    manual_reviews: dict[str, ManualReviewItem] = field(default_factory=dict)
    operating_reports: dict[str, OperatingReport] = field(default_factory=dict)
    strategy_replays: dict[str, StrategyReplay] = field(default_factory=dict)
    portfolio_proposals: dict[str, PortfolioProposal] = field(default_factory=dict)
    portfolio_transactions: dict[str, PortfolioTransaction] = field(default_factory=dict)
    macro_themes: dict[str, MacroTheme] = field(default_factory=dict)
    industry_chains: dict[str, IndustryChain] = field(default_factory=dict)
    industry_chain_template_candidates: dict[str, IndustryChainTemplateCandidate] = field(default_factory=dict)
    industry_chain_template_reviews: dict[str, IndustryChainTemplateReview] = field(default_factory=dict)
    company_positions: dict[str, CompanyPosition] = field(default_factory=dict)
    company_database_build_runs: dict[str, CompanyDatabaseBuildRun] = field(default_factory=dict)
    company_intelligence_cycle_runs: dict[str, CompanyIntelligenceCycleRun] = field(default_factory=dict)
    company_package_import_runs: dict[str, CompanyPackageImportRun] = field(default_factory=dict)
    company_profiles: dict[str, CompanyProfile] = field(default_factory=dict)
    company_profile_field_assertions: dict[str, CompanyProfileFieldAssertion] = field(default_factory=dict)
    financial_metrics: dict[str, FinancialMetric] = field(default_factory=dict)
    company_events: dict[str, CompanyEvent] = field(default_factory=dict)
    company_relationships: dict[str, CompanyRelationship] = field(default_factory=dict)
    hotspot_lexicons: dict[str, HotspotLexicon] = field(default_factory=dict)
    research_tasks: dict[str, ResearchTask] = field(default_factory=dict)
    chokepoint_research_runs: dict[str, ChokepointResearchRun] = field(default_factory=dict)
    benchmarks: dict[str, BenchmarkConfig] = field(default_factory=dict)
    benchmark_samples: dict[str, BenchmarkSample] = field(default_factory=dict)
    benchmark_results: dict[str, BenchmarkResult] = field(default_factory=dict)
    benchmark_runs: dict[str, BenchmarkRun] = field(default_factory=dict)
    extraction_results: dict[str, ExtractionResult] = field(default_factory=dict)
    entity_mappings: dict[str, EntityMapping] = field(default_factory=dict)
    entity_mapping_labels: dict[str, EntityMappingLabel] = field(default_factory=dict)
    scorecards: dict[str, ScorecardProfile] = field(default_factory=dict)
    drill_schedules: dict[str, DrillSchedule] = field(default_factory=dict)
    readiness_checks: dict[str, ReadinessCheckRecord] = field(default_factory=dict)
    secret_rotations: dict[str, SecretRotationRecord] = field(default_factory=dict)
    cache_retention_runs: dict[str, CacheRetentionRunRecord] = field(default_factory=dict)
    prompt_changes: dict[str, PromptChangeRequest] = field(default_factory=dict)
    llm_budget_approvals: dict[str, LLMBudgetApproval] = field(default_factory=dict)
    llm_task_templates: dict[str, LLMTaskTemplate] = field(default_factory=dict)
    llm_task_runs: dict[str, LLMTaskRun] = field(default_factory=dict)
    workflow_definitions: dict[str, WorkflowDefinition] = field(default_factory=dict)
    workflow_runs: dict[str, WorkflowRun] = field(default_factory=dict)
    lineage_events: dict[str, LineageEvent] = field(default_factory=dict)
    model_versions: dict[str, ModelVersionRecord] = field(default_factory=dict)
    templates: dict[str, ResearchTemplate] = field(default_factory=dict)
    research_answers: dict[str, ResearchAnswer] = field(default_factory=dict)
    research_cards: dict[str, ResearchCard] = field(default_factory=dict)
    research_reports: dict[str, ResearchReportAsset] = field(default_factory=dict)
    structured_research_reports: dict[str, ResearchReport] = field(default_factory=dict)
    report_viewpoints: dict[str, ReportViewpoint] = field(default_factory=dict)
    report_forecasts: dict[str, ReportForecast] = field(default_factory=dict)
    analyst_profiles: dict[str, AnalystProfile] = field(default_factory=dict)
    analyst_reliability_scores: dict[str, AnalystReliabilityScore] = field(default_factory=dict)
    crowding: dict[str, CrowdingSnapshot] = field(default_factory=dict)
    institutional_holdings: dict[str, InstitutionalHolding] = field(default_factory=dict)
    disclosure_events: dict[str, DisclosureEvent] = field(default_factory=dict)
    observation_items: dict[str, ObservationItem] = field(default_factory=dict)
    analysis_conclusions: dict[str, AnalysisConclusion] = field(default_factory=dict)
    simulation_feedback: dict[str, SimulationFeedback] = field(default_factory=dict)
    challengers: dict[str, ChallengerResult] = field(default_factory=dict)
    playbooks: dict[str, IncidentPlaybook] = field(default_factory=dict)
    incident_reports: dict[str, IncidentReport] = field(default_factory=dict)
    alert_rules: dict[str, AlertRule] = field(default_factory=dict)
    system_alerts: dict[str, SystemAlert] = field(default_factory=dict)
    alert_notifications: dict[str, AlertNotification] = field(default_factory=dict)
    exceptions: dict[str, ExceptionItem] = field(default_factory=dict)
    usage_metrics: dict[str, UsageMetric] = field(default_factory=dict)
    daily_mainline_runs: dict[str, DailyMainlineRun] = field(default_factory=dict)
    daily_mainline_queue_items: dict[str, DailyMainlineQueueItem] = field(default_factory=dict)
    daily_watchlist_entries: dict[str, DailyWatchlistEntry] = field(default_factory=dict)
    audit_log: list[AuditEvent] = field(default_factory=list)

    def commit(self) -> None:
        return None

    def commit_all(self) -> None:
        self.commit()


class SQLiteStore(InMemoryStore):
    def __init__(self, path: str | Path):
        super().__init__()
        self.path = Path(path)
        self._ensure_schema_if_needed()
        self._load()

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(self.path)

    def _ensure_schema(self) -> None:
        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS records (
                        collection TEXT NOT NULL,
                        item_id TEXT NOT NULL,
                        payload TEXT NOT NULL,
                        position INTEGER,
                        PRIMARY KEY (collection, item_id)
                    )
                    """
                )

    def _ensure_schema_if_needed(self) -> None:
        self._ensure_schema()

    def _load(self) -> None:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT collection, item_id, payload, position FROM records ORDER BY collection, position, item_id"
            ).fetchall()
        specs = {collection: (key_field, model_type) for collection, key_field, model_type in COLLECTIONS}
        for collection, item_id, payload, _position in rows:
            data = json.loads(payload)
            if collection == "audit_log":
                self.audit_log.append(_hydrate_audit_event(data))
                continue
            if collection not in specs:
                continue
            _key_field, model_type = specs[collection]
            getattr(self, collection)[item_id] = _hydrate_model(model_type, data)

    def commit(self) -> None:
        with closing(self._connect()) as connection:
            with connection:
                connection.execute("DELETE FROM records")
                for collection, key_field, _model_type in COLLECTIONS:
                    records = getattr(self, collection)
                    for item_id, item in records.items():
                        connection.execute(
                            "INSERT INTO records (collection, item_id, payload, position) VALUES (?, ?, ?, NULL)",
                            (collection, str(getattr(item, key_field)), json.dumps(to_plain(item), ensure_ascii=False, sort_keys=True)),
                        )
                for position, event in enumerate(self.audit_log):
                    connection.execute(
                        "INSERT INTO records (collection, item_id, payload, position) VALUES (?, ?, ?, ?)",
                        ("audit_log", event.event_id, json.dumps(to_plain(event), ensure_ascii=False, sort_keys=True), position),
                    )


class PostgreSQLStore(InMemoryStore):
    """PostgreSQL runtime adapter using the documented JSONB records schema."""

    def __init__(
        self,
        dsn: str,
        *,
        connect: Callable[[str], Any] | None = None,
        schema_path: str | Path | None = None,
    ):
        super().__init__()
        self.dsn = dsn
        self._connect_func = connect or self._default_connect
        self.schema_path = Path(schema_path) if schema_path else Path(__file__).resolve().parents[1] / "docs" / "postgresql-schema.sql"
        self._lazy_collections: set[str] = set()
        self._lazy_market_data_count = 0
        self._record_hashes: dict[tuple[str, str], str] = {}
        self._audit_hashes: dict[str, str] = {}
        self._persisted_audit_ids: list[str] = []
        self._dirty_collections: set[str] = set()
        self._ensure_schema_if_needed()
        self._load()

    def _default_connect(self, dsn: str) -> Any:
        try:
            import psycopg  # type: ignore[import-not-found]
        except ModuleNotFoundError as exc:  # pragma: no cover - depends on optional runtime package
            raise RuntimeError("PostgreSQLStore requires psycopg. Install with the postgres extra or install psycopg[binary].") from exc
        return psycopg.connect(dsn)

    def _connect(self) -> Any:
        return self._connect_func(self.dsn)

    def _ensure_schema(self) -> None:
        schema_sql = self.schema_path.read_text(encoding="utf-8")
        with closing(self._connect()) as connection:
            with connection:
                with connection.cursor() as cursor:
                    cursor.execute(schema_sql)
                    try:
                        cursor.execute(
                            """
                            INSERT INTO ai_quant.schema_migrations (version, description)
                            VALUES (%s, %s)
                            ON CONFLICT (version)
                            DO UPDATE SET description = EXCLUDED.description, applied_at = now()
                            """,
                            (BASELINE_SCHEMA_VERSION, f"Applied {self.schema_path}"),
                        )
                    except TypeError:
                        cursor.execute(
                            f"""
                            INSERT INTO ai_quant.schema_migrations (version, description)
                            VALUES ('{BASELINE_SCHEMA_VERSION}', 'Applied {self.schema_path}')
                            ON CONFLICT (version)
                            DO UPDATE SET description = EXCLUDED.description, applied_at = now()
                            """
                        )

    def _baseline_schema_recorded(self) -> bool:
        try:
            with closing(self._connect()) as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT to_regclass('ai_quant.schema_migrations') IS NOT NULL")
                    row = cursor.fetchone()
                    if not row or not bool(row[0]):
                        return False
                    cursor.execute("SELECT 1 FROM ai_quant.schema_migrations WHERE version = %s", (BASELINE_SCHEMA_VERSION,))
                    return cursor.fetchone() is not None
        except Exception:
            return False

    def _ensure_schema_if_needed(self) -> None:
        if self._baseline_schema_recorded():
            return
        self._ensure_schema()

    def _load(self) -> None:
        specs = {collection: (key_field, model_type) for collection, key_field, model_type in COLLECTIONS}
        with closing(self._connect()) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT to_regclass('ai_quant.market_data_bars') IS NOT NULL")
                typed_market_data_available = bool(cursor.fetchone()[0])
                if typed_market_data_available:
                    self._lazy_collections.add("market_data")
                records_sql = """
                    SELECT collection, item_id, payload, position
                    FROM ai_quant.records
                """
                if "market_data" in self._lazy_collections:
                    records_sql += "\n                    WHERE collection <> 'market_data'"
                records_sql += "\n                    ORDER BY collection, position NULLS LAST, item_id"
                cursor.execute(
                    records_sql
                )
                record_rows = cursor.fetchall()
                cursor.execute(
                    """
                    SELECT payload
                    FROM ai_quant.audit_log
                    ORDER BY timestamp, event_id
                    """
                )
                audit_rows = cursor.fetchall()
        for collection, item_id, payload, _position in record_rows:
            if collection not in specs:
                continue
            _key_field, model_type = specs[collection]
            plain_payload = _json_payload(payload)
            getattr(self, collection)[item_id] = _hydrate_model(model_type, plain_payload)
            self._record_hashes[(collection, str(item_id))] = self._payload_hash(plain_payload)
        for (payload,) in audit_rows:
            plain_payload = _json_payload(payload)
            event = _hydrate_audit_event(plain_payload)
            self.audit_log.append(event)
            self._persisted_audit_ids.append(event.event_id)
            self._audit_hashes[event.event_id] = self._payload_hash(plain_payload)

    def _payload_hash(self, payload: Any) -> str:
        return json.dumps(to_plain(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    def mark_dirty_for_resource(self, resource_type: str) -> None:
        self._dirty_collections.update(_candidate_collections_for_resource(resource_type))

    def commit_all(self) -> None:
        pending = set(self._dirty_collections)
        self._dirty_collections.clear()
        try:
            self.commit()
        except Exception:
            self._dirty_collections.update(pending)
            raise

    def commit(self) -> None:
        record_hashes_before = dict(self._record_hashes)
        audit_hashes_before = dict(self._audit_hashes)
        persisted_audit_ids_before = list(self._persisted_audit_ids)
        typed_market_data_available = False
        typed_market_data_keys: set[str] = set()
        try:
            with closing(self._connect()) as connection:
                with connection:
                    cursor = connection.cursor()
                    cursor.execute("SELECT to_regclass('ai_quant.market_data_bars') IS NOT NULL")
                    typed_market_data_available = bool(cursor.fetchone()[0])
                    current_keys: set[tuple[str, str]] = set()
                    target_collections = set(self._dirty_collections)
                    if not target_collections:
                        target_collections = {collection for collection, _key_field, _model_type in COLLECTIONS}
                    for collection, key_field, _model_type in COLLECTIONS:
                        if collection not in target_collections:
                            continue
                        records = getattr(self, collection)
                        for item_id, item in records.items():
                            item_id = str(getattr(item, key_field))
                            current_keys.add((collection, item_id))
                            payload = to_plain(item)
                            payload_hash = self._payload_hash(payload)
                            if self._record_hashes.get((collection, item_id)) == payload_hash:
                                if collection == "market_data" and typed_market_data_available:
                                    typed_market_data_keys.add(item_id)
                                continue
                            if collection == "market_data" and typed_market_data_available:
                                self.upsert_market_data_bar(item, cursor=cursor, payload=payload)
                                self._record_hashes[(collection, item_id)] = payload_hash
                                typed_market_data_keys.add(item_id)
                                continue
                            cursor.execute(
                                """
                                INSERT INTO ai_quant.records (collection, item_id, payload, position)
                                VALUES (%s, %s, %s::jsonb, %s)
                                ON CONFLICT (collection, item_id)
                                DO UPDATE SET payload = EXCLUDED.payload, position = EXCLUDED.position
                                """,
                                (
                                    collection,
                                    item_id,
                                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                                    None,
                                ),
                            )
                            self._record_hashes[(collection, item_id)] = payload_hash
                    if not self._dirty_collections:
                        deletable_previous_keys = {
                            key
                            for key in self._record_hashes
                            if key[0] != "market_data" and key[0] not in self._lazy_collections and key not in current_keys
                        }
                        for collection, item_id in sorted(deletable_previous_keys):
                            cursor.execute("DELETE FROM ai_quant.records WHERE collection = %s AND item_id = %s", (collection, item_id))
                            self._record_hashes.pop((collection, item_id), None)
                    current_audit_ids = [event.event_id for event in self.audit_log]
                    persisted_count = len(self._persisted_audit_ids)
                    append_only = (
                        len(current_audit_ids) >= persisted_count
                        and current_audit_ids[:persisted_count] == self._persisted_audit_ids
                    )
                    audit_start = persisted_count if append_only else 0
                    for position, event in enumerate(self.audit_log[audit_start:], start=audit_start):
                        event_payload = to_plain(event)
                        payload_hash = self._payload_hash(event_payload)
                        if self._audit_hashes.get(event.event_id) == payload_hash:
                            continue
                        cursor.execute(
                            """
                            INSERT INTO ai_quant.audit_log (
                                event_id,
                                actor,
                                action,
                                resource_type,
                                resource_id,
                                source,
                                version,
                                model_version,
                                prompt_version,
                                approval_state,
                                trace_id,
                                payload,
                                timestamp
                            )
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                            ON CONFLICT (event_id)
                            DO UPDATE SET
                                actor = EXCLUDED.actor,
                                action = EXCLUDED.action,
                                resource_type = EXCLUDED.resource_type,
                                resource_id = EXCLUDED.resource_id,
                                source = EXCLUDED.source,
                                version = EXCLUDED.version,
                                model_version = EXCLUDED.model_version,
                                prompt_version = EXCLUDED.prompt_version,
                                approval_state = EXCLUDED.approval_state,
                                trace_id = EXCLUDED.trace_id,
                                payload = EXCLUDED.payload,
                                timestamp = EXCLUDED.timestamp
                            """,
                            (
                                event.event_id,
                                event.actor,
                                event.action,
                                event.resource_type,
                                event.resource_id,
                                event.source,
                                event.version,
                                event.model_version,
                                event.prompt_version,
                                event.approval_state,
                                event.trace_id,
                                json.dumps(event_payload, ensure_ascii=False, sort_keys=True),
                                event.timestamp,
                            ),
                        )
                        self._audit_hashes[event.event_id] = payload_hash
                    if not append_only:
                        for event_id in sorted(set(self._audit_hashes) - set(current_audit_ids)):
                            cursor.execute("DELETE FROM ai_quant.audit_log WHERE event_id = %s", (event_id,))
                            self._audit_hashes.pop(event_id, None)
                    self._persisted_audit_ids = current_audit_ids
        except Exception:
            self._record_hashes = record_hashes_before
            self._audit_hashes = audit_hashes_before
            self._persisted_audit_ids = persisted_audit_ids_before
            raise
        self._dirty_collections.clear()
        if typed_market_data_available and typed_market_data_keys:
            for item_id in typed_market_data_keys:
                self.market_data.pop(item_id, None)
                self._record_hashes.pop(("market_data", item_id), None)

    def market_data_bars_available(self) -> bool:
        with closing(self._connect()) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT to_regclass('ai_quant.market_data_bars') IS NOT NULL")
                row = cursor.fetchone()
        return bool(row and row[0])

    def upsert_market_data_bar(self, point: MarketDataPoint, *, cursor: Any | None = None, payload: dict[str, Any] | None = None) -> None:
        plain_payload = payload or to_plain(point)
        if cursor is not None:
            upsert_typed_market_data_bar(cursor, plain_payload)
            return
        with closing(self._connect()) as connection:
            with connection:
                with connection.cursor() as local_cursor:
                    upsert_typed_market_data_bar(local_cursor, plain_payload)

    def query_market_data_points(
        self,
        *,
        security_id: str = "",
        market: str = "",
        source_id: str = "",
        data_type: str = "",
        start_date: str = "",
        end_date: str = "",
        as_of_date_lte: str = "",
        limit: int = 50,
        descending: bool = True,
    ) -> list[MarketDataPoint]:
        if self.market_data_bars_available():
            return self._query_market_data_bars(
                security_id=security_id,
                market=market,
                source_id=source_id,
                data_type=data_type,
                start_date=start_date,
                end_date=end_date,
                as_of_date_lte=as_of_date_lte,
                limit=limit,
                descending=descending,
            )
        return []

    def _query_market_data_bars(
        self,
        *,
        security_id: str = "",
        market: str = "",
        source_id: str = "",
        data_type: str = "",
        start_date: str = "",
        end_date: str = "",
        as_of_date_lte: str = "",
        limit: int = 50,
        descending: bool = True,
    ) -> list[MarketDataPoint]:
        clauses = ["TRUE"]
        params: list[Any] = []
        if security_id:
            clauses.append("b.security_id = %s")
            params.append(security_id)
        if market:
            clauses.append("b.market = %s")
            params.append(market)
        if source_id:
            clauses.append("b.source_id = %s")
            params.append(source_id)
        if data_type:
            clauses.append("b.data_type = %s")
            params.append(data_type)
        if start_date:
            clauses.append("b.as_of_date >= %s::date")
            params.append(start_date)
        if end_date:
            clauses.append("b.as_of_date <= %s::date")
            params.append(end_date)
        if as_of_date_lte:
            clauses.append("b.as_of_date <= %s::date")
            params.append(as_of_date_lte)
        order = "DESC" if descending else "ASC"
        bounded_limit = max(1, min(int(limit or 50), 10000))
        params.append(bounded_limit)
        sql = f"""
            SELECT
                b.data_id,
                b.security_id,
                b.source_id,
                b.market,
                b.as_of_date::text,
                b.data_type,
                b.currency,
                b.open,
                b.high,
                b.low,
                b.close,
                b.adjusted_close,
                b.volume,
                b.amount,
                p.rights_tag,
                b.created_at
            FROM ai_quant.market_data_bars AS b
            JOIN ai_quant.market_data_rights_policies AS p
              ON p.policy_id = b.rights_policy_id
            WHERE {' AND '.join(clauses)}
            ORDER BY b.as_of_date {order}, b.data_id {order}
            LIMIT %s
        """
        with closing(self._connect()) as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, tuple(params))
                rows = cursor.fetchall()
        return [
            MarketDataPoint.from_dict(
                {
                    "data_id": str(data_id),
                    "security_id": str(row_security_id),
                    "source_id": str(row_source_id),
                    "market": str(row_market),
                    "as_of_date": str(row_as_of_date),
                    "data_type": str(row_data_type),
                    "currency": str(row_currency or ""),
                    "open": float(row_open or 0.0),
                    "high": float(row_high or 0.0),
                    "low": float(row_low or 0.0),
                    "close": float(row_close or 0.0),
                    "adjusted_close": float(row_adjusted_close or row_close or 0.0),
                    "volume": float(row_volume or 0.0),
                    "amount": float(row_amount or 0.0),
                    "rights_tag": _json_payload(row_rights_tag),
                    "created_at": row_created_at,
                }
            )
            for (
                data_id,
                row_security_id,
                row_source_id,
                row_market,
                row_as_of_date,
                row_data_type,
                row_currency,
                row_open,
                row_high,
                row_low,
                row_close,
                row_adjusted_close,
                row_volume,
                row_amount,
                row_rights_tag,
                row_created_at,
            ) in rows
        ]

    def count_market_data_points(
        self,
        *,
        security_id: str = "",
        market: str = "",
        source_id: str = "",
        data_type: str = "",
    ) -> int:
        if self.market_data_bars_available():
            clauses = ["TRUE"]
            params: list[Any] = []
            if security_id:
                clauses.append("security_id = %s")
                params.append(security_id)
            if market:
                clauses.append("market = %s")
                params.append(market)
            if source_id:
                clauses.append("source_id = %s")
                params.append(source_id)
            if data_type:
                clauses.append("data_type = %s")
                params.append(data_type)
            sql = f"SELECT COUNT(*) FROM ai_quant.market_data_bars WHERE {' AND '.join(clauses)}"
            with closing(self._connect()) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(sql, tuple(params))
                    return int(cursor.fetchone()[0] or 0)
        return 0

    def query_market_disturbance_rows(
        self,
        *,
        as_of_date: str,
        targets: Sequence[Mapping[str, Any]],
        history_rows: int = 20,
        limit: int = 20000,
    ) -> list[dict[str, Any]]:
        """Read the latest EOD bar plus prior/history aggregates per security."""

        normalized_targets = [
            {
                "market": str(item.get("market") or "").strip().upper(),
                "source_id": str(item.get("source_id") or "").strip(),
                "data_type": str(item.get("data_type") or "eod").strip(),
            }
            for item in targets
            if isinstance(item, Mapping)
            and str(item.get("market") or "").strip()
            and str(item.get("source_id") or "").strip()
        ]
        if not normalized_targets or not self.market_data_bars_available():
            return []
        target_clauses: list[str] = []
        params: list[Any] = [str(as_of_date)]
        for target in normalized_targets:
            target_clauses.append("(b.market = %s AND b.source_id = %s AND b.data_type = %s)")
            params.extend([target["market"], target["source_id"], target["data_type"]])
        params.extend(
            [
                max(1, min(int(history_rows or 20), 120)),
                max(1, min(int(limit or 20000), 50000)),
            ]
        )
        sql = f"""
            WITH ranked AS (
                SELECT
                    b.*,
                    ROW_NUMBER() OVER (
                        PARTITION BY b.security_id
                        ORDER BY b.as_of_date DESC, b.data_id DESC
                    ) AS row_number
                FROM ai_quant.market_data_bars AS b
                WHERE b.as_of_date <= %s::date
                  AND ({' OR '.join(target_clauses)})
            ),
            current_rows AS (
                SELECT *
                FROM ranked
                WHERE row_number = 1
            )
            SELECT
                c.security_id,
                c.market,
                c.source_id,
                c.data_type,
                c.as_of_date::text,
                c.open,
                c.high,
                c.low,
                c.close,
                c.volume,
                c.amount,
                previous.close,
                history.avg_volume,
                history.avg_amount,
                COALESCE(security.payload->>'issuer_id', ''),
                COALESCE(security.payload->>'ticker', c.security_id),
                COALESCE(issuer.payload->>'legal_name', security.payload->>'ticker', c.security_id)
            FROM current_rows AS c
            LEFT JOIN LATERAL (
                SELECT b.close
                FROM ai_quant.market_data_bars AS b
                WHERE b.security_id = c.security_id
                  AND b.source_id = c.source_id
                  AND b.data_type = c.data_type
                  AND b.as_of_date < c.as_of_date
                ORDER BY b.as_of_date DESC, b.data_id DESC
                LIMIT 1
            ) AS previous ON TRUE
            LEFT JOIN LATERAL (
                SELECT
                    AVG(NULLIF(recent.volume, 0)) AS avg_volume,
                    AVG(NULLIF(recent.amount, 0)) AS avg_amount
                FROM (
                    SELECT b.volume, b.amount
                    FROM ai_quant.market_data_bars AS b
                    WHERE b.security_id = c.security_id
                      AND b.source_id = c.source_id
                      AND b.data_type = c.data_type
                      AND b.as_of_date < c.as_of_date
                    ORDER BY b.as_of_date DESC, b.data_id DESC
                    LIMIT %s
                ) AS recent
            ) AS history ON TRUE
            LEFT JOIN ai_quant.records AS security
              ON security.collection = 'securities'
             AND security.item_id = c.security_id
            LEFT JOIN ai_quant.records AS issuer
              ON issuer.collection = 'issuers'
             AND issuer.item_id = security.payload->>'issuer_id'
            ORDER BY c.as_of_date DESC, c.security_id
            LIMIT %s
        """
        with closing(self._connect()) as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, tuple(params))
                rows = cursor.fetchall()
        return [
            {
                "security_id": str(security_id),
                "market": str(market),
                "source_id": str(source_id),
                "data_type": str(data_type),
                "as_of_date": str(row_date),
                "open": float(row_open or 0.0),
                "high": float(high or 0.0),
                "low": float(low or 0.0),
                "close": float(close or 0.0),
                "volume": float(volume or 0.0),
                "amount": float(amount or 0.0),
                "previous_close": float(previous_close or 0.0),
                "average_volume": float(average_volume or 0.0),
                "average_amount": float(average_amount or 0.0),
                "issuer_id": str(issuer_id or ""),
                "ticker": str(ticker or security_id),
                "issuer_name": str(issuer_name or ticker or security_id),
            }
            for (
                security_id,
                market,
                source_id,
                data_type,
                row_date,
                row_open,
                high,
                low,
                close,
                volume,
                amount,
                previous_close,
                average_volume,
                average_amount,
                issuer_id,
                ticker,
                issuer_name,
            ) in rows
        ]

    def estimate_market_data_points(self) -> int:
        if not self.market_data_bars_available():
            return int(self._lazy_market_data_count or 0)
        with closing(self._connect()) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT GREATEST(
                        COALESCE((SELECT n_live_tup FROM pg_stat_user_tables WHERE schemaname = 'ai_quant' AND relname = 'market_data_bars'), 0),
                        COALESCE((SELECT reltuples::bigint FROM pg_class WHERE oid = 'ai_quant.market_data_bars'::regclass), 0)
                    )::bigint
                    """
                )
                row = cursor.fetchone()
        estimate = int(row[0] or 0) if row else 0
        return max(estimate, int(self._lazy_market_data_count or 0), len(self.market_data))
