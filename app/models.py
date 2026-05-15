from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .errors import ValidationError
from .utils import parse_datetime, utcnow


def _validate_choice(value: str, choices: set[str], field_name: str) -> str:
    if value not in choices:
        raise ValidationError(f"{field_name} must be one of {sorted(choices)}")
    return value


@dataclass(slots=True)
class RightsTag:
    license_class: str
    training_allowed: bool = False
    redistribution_allowed: bool = False
    display_use: str = "allowed"
    non_display_use: str = "restricted"
    derived_data_use: str = "restricted"

    def __post_init__(self) -> None:
        _validate_choice(self.display_use, {"allowed", "restricted"}, "display_use")
        _validate_choice(self.non_display_use, {"allowed", "restricted"}, "non_display_use")
        _validate_choice(self.derived_data_use, {"allowed", "restricted"}, "derived_data_use")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RightsTag":
        return cls(
            license_class=str(data["license_class"]),
            training_allowed=bool(data.get("training_allowed", False)),
            redistribution_allowed=bool(data.get("redistribution_allowed", False)),
            display_use=str(data.get("display_use", "allowed")),
            non_display_use=str(data.get("non_display_use", "restricted")),
            derived_data_use=str(data.get("derived_data_use", "restricted")),
        )

    def allows(self, other: "RightsTag") -> bool:
        return (
            (not other.training_allowed or self.training_allowed)
            and (not other.redistribution_allowed or self.redistribution_allowed)
            and (other.display_use == "restricted" or self.display_use == "allowed")
            and (other.non_display_use == "restricted" or self.non_display_use == "allowed")
            and (other.derived_data_use == "restricted" or self.derived_data_use == "allowed")
        )


@dataclass(slots=True)
class SourceDefinition:
    source_id: str
    source_type: str
    rights_tag: RightsTag
    description: str = ""
    risk_level: str = "green"
    field_mapping: dict[str, str] = field(default_factory=dict)
    allowed_document_types: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SourceDefinition":
        rights_data = data.get("rights_tag")
        if rights_data is None:
            rights_data = {
                "license_class": data.get("license_class", ""),
                "training_allowed": data.get("training_allowed", False),
                "redistribution_allowed": data.get("redistribution_allowed", False),
                "display_use": data.get("display_use", "allowed"),
                "non_display_use": data.get("non_display_use", "restricted"),
                "derived_data_use": data.get("derived_data_use", "restricted"),
            }
        return cls(
            source_id=str(data["source_id"]),
            source_type=str(data["source_type"]),
            rights_tag=RightsTag.from_dict(rights_data),
            description=str(data.get("description", "")),
            risk_level=str(data.get("risk_level", "green")),
            field_mapping=dict(data.get("field_mapping", {})),
            allowed_document_types=list(data.get("allowed_document_types", [])),
        )


@dataclass(slots=True)
class IngestionJob:
    job_id: str
    status: str
    total: int
    created: int = 0
    skipped: int = 0
    failed: int = 0
    created_document_ids: list[str] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    started_at: Any = field(default_factory=utcnow)
    completed_at: Any = field(default_factory=utcnow)


@dataclass(slots=True)
class IngestionSchedule:
    schedule_id: str
    name: str
    payload: dict[str, Any] = field(default_factory=dict)
    cadence: str = "manual"
    status: str = "active"
    retry_limit: int = 2
    retry_count: int = 0
    last_job_id: str = ""
    last_status: str = ""
    last_error: str = ""
    next_run_at: Any = field(default_factory=utcnow)
    created_at: Any = field(default_factory=utcnow)
    updated_at: Any = field(default_factory=utcnow)


@dataclass(slots=True)
class Issuer:
    issuer_id: str
    legal_name: str
    aliases: list[str] = field(default_factory=list)
    market: list[str] = field(default_factory=list)
    lei: str = ""
    cik: str = ""
    country: str = ""
    status: str = "active"
    created_at: Any = field(default_factory=utcnow)
    updated_at: Any = field(default_factory=utcnow)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Issuer":
        return cls(
            issuer_id=str(data["issuer_id"]),
            legal_name=str(data["legal_name"]),
            aliases=list(data.get("aliases", [])),
            market=list(data.get("market", [])),
            lei=str(data.get("lei", "")),
            cik=str(data.get("cik", "")),
            country=str(data.get("country", "")),
            status=str(data.get("status", "active")),
            created_at=parse_datetime(data.get("created_at")),
            updated_at=parse_datetime(data.get("updated_at")),
        )


@dataclass(slots=True)
class Security:
    security_id: str
    issuer_id: str
    ticker: str
    figi: str = ""
    isin: str = ""
    exchange: str = ""
    currency: str = ""
    market: str = "A"
    status: str = "active"

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Security":
        return cls(
            security_id=str(data["security_id"]),
            issuer_id=str(data["issuer_id"]),
            ticker=str(data["ticker"]),
            figi=str(data.get("figi", "")),
            isin=str(data.get("isin", "")),
            exchange=str(data.get("exchange", "")),
            currency=str(data.get("currency", "")),
            market=str(data.get("market", "A")),
            status=str(data.get("status", "active")),
        )


@dataclass(slots=True)
class MarketDataPoint:
    data_id: str
    security_id: str
    source_id: str
    market: str
    as_of_date: str
    data_type: str = "eod"
    currency: str = ""
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    adjusted_close: float = 0.0
    volume: float = 0.0
    rights_tag: RightsTag = field(default_factory=lambda: RightsTag("unknown"))
    created_at: Any = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        _validate_choice(self.market, {"A", "H", "U"}, "market")
        _validate_choice(self.data_type, {"eod", "delayed"}, "data_type")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MarketDataPoint":
        close_value = float(data.get("close", 0.0))
        return cls(
            data_id=str(data["data_id"]),
            security_id=str(data["security_id"]),
            source_id=str(data["source_id"]),
            market=str(data["market"]),
            as_of_date=str(data["as_of_date"]),
            data_type=str(data.get("data_type", "eod")),
            currency=str(data.get("currency", "")),
            open=float(data.get("open", 0.0)),
            high=float(data.get("high", 0.0)),
            low=float(data.get("low", 0.0)),
            close=close_value,
            adjusted_close=float(data.get("adjusted_close", close_value)),
            volume=float(data.get("volume", 0.0)),
            rights_tag=RightsTag.from_dict(data.get("rights_tag", {"license_class": "unknown"})),
            created_at=parse_datetime(data.get("created_at")),
        )


@dataclass(slots=True)
class CorporateAction:
    action_id: str
    security_id: str
    source_id: str
    action_type: str
    ex_date: str
    ratio: float = 1.0
    cash_amount: float = 0.0
    currency: str = ""
    description: str = ""
    created_at: Any = field(default_factory=utcnow)


@dataclass(slots=True)
class Document:
    document_id: str
    issuer_id: str
    security_id: str
    document_type: str
    source_id: str
    source_type: str
    source_uri: str
    rights_tag: RightsTag
    body: str = ""
    title: str = ""
    object_uri: str = ""
    content_sha256: str = ""
    published_at: Any = field(default_factory=utcnow)
    ingested_at: Any = field(default_factory=utcnow)
    language: str = "zh"
    version: str = "v1"

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Document":
        return cls(
            document_id=str(data["document_id"]),
            issuer_id=str(data["issuer_id"]),
            security_id=str(data.get("security_id", "")),
            document_type=str(data["document_type"]),
            source_id=str(data["source_id"]),
            source_type=str(data.get("source_type", "")),
            source_uri=str(data.get("source_uri", "")),
            rights_tag=RightsTag.from_dict(data["rights_tag"]),
            body=str(data.get("body", "")),
            title=str(data.get("title", "")),
            object_uri=str(data.get("object_uri", "")),
            content_sha256=str(data.get("content_sha256", "")),
            published_at=parse_datetime(data.get("published_at")),
            ingested_at=parse_datetime(data.get("ingested_at")),
            language=str(data.get("language", "zh")),
            version=str(data.get("version", "v1")),
        )


@dataclass(slots=True)
class Evidence:
    evidence_id: str
    document_id: str
    section: str
    page_no: int
    bbox: str
    span_text: str
    canonical_text: str
    confidence: float
    created_at: Any = field(default_factory=utcnow)


@dataclass(slots=True)
class ThesisCard:
    thesis_id: str
    issuer_id: str
    horizon: str
    hypothesis: str
    catalyst: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    falsifiers: list[str] = field(default_factory=list)
    risk_factors: list[str] = field(default_factory=list)
    confidence: float = 0.0
    owner: str = ""
    status: str = "draft"
    valid_from: Any = field(default_factory=utcnow)
    valid_to: Any = field(default_factory=utcnow)


@dataclass(slots=True)
class ResearchSignal:
    signal_id: str
    thesis_id: str
    signal_type: str
    direction: str
    score: float
    source_model: str
    model_version: str
    generated_at: Any = field(default_factory=utcnow)
    rationale: str = ""
    profile_id: str = ""
    factor_scores: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class DecisionSignature:
    role: str
    user: str
    signed_at: Any = field(default_factory=utcnow)
    comment: str = ""


@dataclass(slots=True)
class DecisionPack:
    decision_id: str
    signal_ids: list[str] = field(default_factory=list)
    risk_checks: list[str] = field(default_factory=list)
    red_team_note: str = ""
    approval_state: str = "pending"
    signatures: list[DecisionSignature] = field(default_factory=list)
    created_at: Any = field(default_factory=utcnow)


@dataclass(slots=True)
class ExecutionIntent:
    intent_id: str
    decision_id: str
    action: str
    security_id: str = ""
    target_weight: float = 0.0
    rationale: str = ""
    status: str = "draft"
    created_by: str = ""
    created_at: Any = field(default_factory=utcnow)


@dataclass(slots=True)
class ReviewRecord:
    review_id: str
    decision_id: str
    realized_outcome: str
    attribution: str
    lesson: str
    next_action: str
    created_at: Any = field(default_factory=utcnow)


@dataclass(slots=True)
class ManualReviewItem:
    review_id: str
    document_id: str
    issue_type: str
    severity: str
    status: str = "open"
    parser_version: str = ""
    message: str = ""
    suggested_action: str = ""
    created_at: Any = field(default_factory=utcnow)
    updated_at: Any = field(default_factory=utcnow)


@dataclass(slots=True)
class OperatingReport:
    report_id: str
    period: str
    metrics: dict[str, Any] = field(default_factory=dict)
    red_flags: list[dict[str, Any]] = field(default_factory=list)
    owner: str = ""
    status: str = "draft"
    approvals: list[dict[str, Any]] = field(default_factory=list)
    created_at: Any = field(default_factory=utcnow)
    published_at: Any = None


@dataclass(slots=True)
class StrategyReplay:
    replay_id: str
    decision_id: str
    expected_outcome: str
    actual_outcome: str
    variance_reason: str
    next_action: str
    version: str = "v1"
    created_at: Any = field(default_factory=utcnow)


@dataclass(slots=True)
class PortfolioProposal:
    proposal_id: str
    universe: list[str] = field(default_factory=list)
    prior_returns: dict[str, float] = field(default_factory=dict)
    posterior_returns: dict[str, float] = field(default_factory=dict)
    candidate_weights: dict[str, float] = field(default_factory=dict)
    constraints: dict[str, Any] = field(default_factory=dict)
    risk_budget: dict[str, Any] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    status: str = "candidate"
    created_by: str = ""
    created_at: Any = field(default_factory=utcnow)


@dataclass(slots=True)
class BenchmarkConfig:
    benchmark_id: str
    language: str
    task_type: str
    sample_size: int
    metrics: dict[str, float] = field(default_factory=dict)
    threshold: dict[str, float] = field(default_factory=dict)
    status: str = "draft"
    created_at: Any = field(default_factory=utcnow)


@dataclass(slots=True)
class BenchmarkSample:
    sample_id: str
    benchmark_id: str
    document_id: str
    language: str
    expected_terms: list[str] = field(default_factory=list)
    expected_numbers: int = 0
    expected_periods: int = 0
    expected_tables: int = 0
    expected_pages: list[int] = field(default_factory=list)
    notes: str = ""
    status: str = "active"
    created_at: Any = field(default_factory=utcnow)


@dataclass(slots=True)
class PromptChangeRequest:
    request_id: str
    prompt_name: str
    change_level: str
    requested_by: str
    content: str
    status: str = "pending"
    approvers: list[str] = field(default_factory=list)
    created_at: Any = field(default_factory=utcnow)


@dataclass(slots=True)
class ResearchTemplate:
    template_id: str
    template_type: str
    name: str
    fields: list[str] = field(default_factory=list)
    description: str = ""
    created_at: Any = field(default_factory=utcnow)


@dataclass(slots=True)
class ResearchCard:
    card_id: str
    template_id: str
    template_type: str
    issuer_id: str
    thesis_id: str
    title: str
    fields: dict[str, Any] = field(default_factory=dict)
    created_at: Any = field(default_factory=utcnow)


@dataclass(slots=True)
class ResearchAnswer:
    answer_id: str
    question: str
    issuer_id: str
    evidence_ids: list[str] = field(default_factory=list)
    source_document_ids: list[str] = field(default_factory=list)
    english_source_text: str = ""
    chinese_summary: str = ""
    summary_version: str = "summary-v1"
    prompt_version: str = ""
    model_version: str = ""
    source_publicness: str = "unknown"
    human_review_status: str = "pending"
    reviewer: str = ""
    created_at: Any = field(default_factory=utcnow)
    updated_at: Any = field(default_factory=utcnow)


@dataclass(slots=True)
class CrowdingSnapshot:
    snapshot_id: str
    issuer_id: str
    score: float
    source: str
    rationale: str
    created_at: Any = field(default_factory=utcnow)


@dataclass(slots=True)
class InstitutionalHolding:
    holding_id: str
    issuer_id: str
    security_id: str
    source_id: str
    filer_cik: str
    filer_name: str
    report_period: str
    shares: float = 0.0
    value_usd: float = 0.0
    voting_authority: str = ""
    created_at: Any = field(default_factory=utcnow)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "InstitutionalHolding":
        return cls(
            holding_id=str(data["holding_id"]),
            issuer_id=str(data["issuer_id"]),
            security_id=str(data["security_id"]),
            source_id=str(data.get("source_id", "sec_edgar")),
            filer_cik=str(data.get("filer_cik", "")),
            filer_name=str(data.get("filer_name", "")),
            report_period=str(data["report_period"]),
            shares=float(data.get("shares", 0.0)),
            value_usd=float(data.get("value_usd", 0.0)),
            voting_authority=str(data.get("voting_authority", "")),
            created_at=parse_datetime(data.get("created_at")),
        )


@dataclass(slots=True)
class DisclosureEvent:
    event_id: str
    document_id: str
    issuer_id: str
    security_id: str = ""
    event_type: str = "filing_update"
    severity: str = "low"
    summary: str = ""
    evidence_ids: list[str] = field(default_factory=list)
    source_id: str = ""
    occurred_at: Any = field(default_factory=utcnow)
    created_at: Any = field(default_factory=utcnow)


@dataclass(slots=True)
class ChallengerResult:
    challenger_id: str
    thesis_id: str
    conflict_score: float
    source_conflict: float
    valuation_gap: float
    narrative_divergence: float
    policy_risk: float
    verdict: str
    note: str
    created_at: Any = field(default_factory=utcnow)


@dataclass(slots=True)
class IncidentPlaybook:
    playbook_id: str
    incident_type: str
    detection_rule: str
    auto_action: str
    manual_action: str
    owner_role: str
    created_at: Any = field(default_factory=utcnow)


@dataclass(slots=True)
class IncidentReport:
    report_id: str
    playbook_id: str
    incident_type: str
    root_cause: str
    impact: str
    action_items: list[str] = field(default_factory=list)
    owner: str = ""
    created_at: Any = field(default_factory=utcnow)


@dataclass(slots=True)
class AlertRule:
    rule_id: str
    metric: str
    operator: str
    threshold: float
    severity: str
    owner: str
    description: str = ""
    enabled: bool = True
    playbook_id: str = ""
    created_at: Any = field(default_factory=utcnow)
    updated_at: Any = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        _validate_choice(self.operator, {">", ">=", "<", "<=", "==", "!="}, "operator")
        _validate_choice(self.severity, {"low", "medium", "high", "critical"}, "severity")


@dataclass(slots=True)
class SystemAlert:
    alert_id: str
    rule_id: str
    metric: str
    value: float
    threshold: float
    severity: str
    status: str
    message: str
    owner: str
    playbook_id: str = ""
    incident_report_id: str = ""
    created_at: Any = field(default_factory=utcnow)
    updated_at: Any = field(default_factory=utcnow)


@dataclass(slots=True)
class AlertNotification:
    notification_id: str
    alert_id: str
    channel: str
    target: str
    status: str = "pending"
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: Any = field(default_factory=utcnow)


@dataclass(slots=True)
class ExceptionItem:
    exception_id: str
    decision_id: str
    reason: str
    severity: str
    status: str = "open"
    created_at: Any = field(default_factory=utcnow)


@dataclass(slots=True)
class AuditEvent:
    event_id: str
    actor: str
    action: str
    resource_type: str
    resource_id: str
    source: str
    version: str = ""
    model_version: str = ""
    prompt_version: str = ""
    approval_state: str = ""
    trace_id: str = ""
    timestamp: Any = field(default_factory=utcnow)


@dataclass(slots=True)
class BenchmarkResult:
    result_id: str
    benchmark_id: str
    passed: bool
    metrics: dict[str, float] = field(default_factory=dict)
    threshold: dict[str, float] = field(default_factory=dict)
    created_at: Any = field(default_factory=utcnow)


@dataclass(slots=True)
class BenchmarkRun:
    run_id: str
    benchmark_id: str
    sample_ids: list[str] = field(default_factory=list)
    passed: bool = False
    metrics: dict[str, Any] = field(default_factory=dict)
    threshold: dict[str, float] = field(default_factory=dict)
    failed_samples: list[dict[str, Any]] = field(default_factory=list)
    regression_examples: list[str] = field(default_factory=list)
    created_at: Any = field(default_factory=utcnow)


@dataclass(slots=True)
class ExtractionResult:
    extraction_id: str
    evidence_id: str
    document_id: str
    language: str
    task_type: str
    terms: list[dict[str, Any]] = field(default_factory=list)
    numbers: list[dict[str, Any]] = field(default_factory=list)
    periods: list[dict[str, Any]] = field(default_factory=list)
    tables: list[dict[str, Any]] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)
    benchmark_id: str = ""
    passed: bool = False
    parser_version: str = "rule-0"
    created_at: Any = field(default_factory=utcnow)


@dataclass(slots=True)
class EntityMapping:
    mapping_id: str
    issuer_id: str
    lei: str = ""
    cik: str = ""
    figi: str = ""
    isin: str = ""
    ticker: str = ""
    market: str = ""
    created_at: Any = field(default_factory=utcnow)


@dataclass(slots=True)
class ScorecardProfile:
    profile_id: str
    strategy_type: str
    name: str
    weights: dict[str, float] = field(default_factory=dict)
    threshold_long: float = 0.55
    threshold_short: float = 0.55
    created_at: Any = field(default_factory=utcnow)


@dataclass(slots=True)
class DrillSchedule:
    schedule_id: str
    incident_type: str
    cadence: str
    owner: str
    next_run_at: Any = field(default_factory=utcnow)
    notes: str = ""
