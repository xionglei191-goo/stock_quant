from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass, field
import json
from pathlib import Path
import sqlite3
from typing import Any, Callable

from .models import (
    AuditEvent,
    AlertNotification,
    AlertRule,
    AStockConnectorDefinition,
    BenchmarkConfig,
    BenchmarkResult,
    BenchmarkRun,
    BenchmarkSample,
    CacheRetentionRunRecord,
    CorporateAction,
    CompanyPosition,
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
    IngestionJob,
    IngestionSchedule,
    IncidentPlaybook,
    IncidentReport,
    InstitutionalHolding,
    IndustryChain,
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
    OperatingReport,
    PortfolioProposal,
    PortfolioTransaction,
    PromptChangeRequest,
    ReadinessCheckRecord,
    ResearchAnswer,
    ResearchCard,
    ResearchReportAsset,
    ResearchTask,
    ResearchTemplate,
    ResearchSignal,
    ReviewRecord,
    Security,
    SecretRotationRecord,
    SimulatedExecution,
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
    ("company_positions", "position_id", CompanyPosition),
    ("hotspot_lexicons", "lexicon_id", HotspotLexicon),
    ("research_tasks", "task_id", ResearchTask),
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
    ("crowding", "snapshot_id", CrowdingSnapshot),
    ("institutional_holdings", "holding_id", InstitutionalHolding),
    ("disclosure_events", "event_id", DisclosureEvent),
    ("challengers", "challenger_id", ChallengerResult),
    ("playbooks", "playbook_id", IncidentPlaybook),
    ("incident_reports", "report_id", IncidentReport),
    ("alert_rules", "rule_id", AlertRule),
    ("system_alerts", "alert_id", SystemAlert),
    ("alert_notifications", "notification_id", AlertNotification),
    ("exceptions", "exception_id", ExceptionItem),
)


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
    IndustryChain: ("created_at",),
    CompanyPosition: ("created_at",),
    HotspotLexicon: ("created_at",),
    ResearchTask: ("created_at", "updated_at"),
    BenchmarkConfig: ("created_at",),
    BenchmarkSample: ("created_at",),
    BenchmarkResult: ("created_at",),
    BenchmarkRun: ("created_at",),
    ExtractionResult: ("created_at",),
    PromptChangeRequest: ("created_at",),
    EntityMappingLabel: ("created_at",),
    ResearchTemplate: ("created_at",),
    ResearchAnswer: ("created_at", "updated_at"),
    ResearchCard: ("created_at",),
    ResearchReportAsset: ("indexed_at",),
    CrowdingSnapshot: ("created_at",),
    InstitutionalHolding: ("created_at",),
    DisclosureEvent: ("occurred_at", "created_at"),
    ChallengerResult: ("created_at",),
    IncidentPlaybook: ("created_at",),
    IncidentReport: ("created_at",),
    AlertRule: ("created_at", "updated_at"),
    SystemAlert: ("created_at", "updated_at"),
    AlertNotification: ("created_at",),
    ExceptionItem: ("created_at",),
    EntityMapping: ("created_at",),
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
}


OPTIONAL_DATETIME_FIELDS: dict[type, tuple[str, ...]] = {
    OperatingReport: ("published_at",),
    SourceReviewRecord: ("next_review_due_at",),
    AStockConnectorDefinition: ("last_checked_at",),
    ReadinessCheckRecord: ("expires_at",),
    DrillSchedule: ("last_run_at",),
    SecretRotationRecord: ("next_rotation_due_at",),
    CacheRetentionRunRecord: ("executed_at",),
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
    company_positions: dict[str, CompanyPosition] = field(default_factory=dict)
    hotspot_lexicons: dict[str, HotspotLexicon] = field(default_factory=dict)
    research_tasks: dict[str, ResearchTask] = field(default_factory=dict)
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
    crowding: dict[str, CrowdingSnapshot] = field(default_factory=dict)
    institutional_holdings: dict[str, InstitutionalHolding] = field(default_factory=dict)
    disclosure_events: dict[str, DisclosureEvent] = field(default_factory=dict)
    challengers: dict[str, ChallengerResult] = field(default_factory=dict)
    playbooks: dict[str, IncidentPlaybook] = field(default_factory=dict)
    incident_reports: dict[str, IncidentReport] = field(default_factory=dict)
    alert_rules: dict[str, AlertRule] = field(default_factory=dict)
    system_alerts: dict[str, SystemAlert] = field(default_factory=dict)
    alert_notifications: dict[str, AlertNotification] = field(default_factory=dict)
    exceptions: dict[str, ExceptionItem] = field(default_factory=dict)
    audit_log: list[AuditEvent] = field(default_factory=list)

    def commit(self) -> None:
        return None


class SQLiteStore(InMemoryStore):
    def __init__(self, path: str | Path):
        super().__init__()
        self.path = Path(path)
        self._ensure_schema()
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
        self._ensure_schema()
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

    def _load(self) -> None:
        specs = {collection: (key_field, model_type) for collection, key_field, model_type in COLLECTIONS}
        with closing(self._connect()) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT collection, item_id, payload, position
                    FROM ai_quant.records
                    ORDER BY collection, position NULLS LAST, item_id
                    """
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
            getattr(self, collection)[item_id] = _hydrate_model(model_type, _json_payload(payload))
        for (payload,) in audit_rows:
            self.audit_log.append(_hydrate_audit_event(_json_payload(payload)))

    def commit(self) -> None:
        with closing(self._connect()) as connection:
            with connection:
                with connection.cursor() as cursor:
                    cursor.execute("DELETE FROM ai_quant.records")
                    cursor.execute("DELETE FROM ai_quant.audit_log")
                    for collection, key_field, _model_type in COLLECTIONS:
                        records = getattr(self, collection)
                        for item_id, item in records.items():
                            cursor.execute(
                                """
                                INSERT INTO ai_quant.records (collection, item_id, payload, position)
                                VALUES (%s, %s, %s::jsonb, %s)
                                ON CONFLICT (collection, item_id)
                                DO UPDATE SET payload = EXCLUDED.payload, position = EXCLUDED.position
                                """,
                                (
                                    collection,
                                    str(getattr(item, key_field)),
                                    json.dumps(to_plain(item), ensure_ascii=False, sort_keys=True),
                                    None,
                                ),
                            )
                    for position, event in enumerate(self.audit_log):
                        event_payload = to_plain(event)
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
