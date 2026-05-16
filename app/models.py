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
    field_whitelist: list[str] = field(default_factory=list)
    retention_policy: str = ""
    cache_ttl_days: int = 0
    provenance_ref: str = ""
    usage_scope: str = ""
    collection_method: str = ""
    robots_policy: str = ""
    last_reviewed_at: Any = None
    review_cadence: str = "quarterly"
    review_owner: str = ""
    review_owner_role: str = ""
    source_tos_uri: str = ""

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
            field_whitelist=[str(item) for item in data.get("field_whitelist", [])],
            retention_policy=str(data.get("retention_policy", "")),
            cache_ttl_days=int(data.get("cache_ttl_days", 0)),
            provenance_ref=str(data.get("provenance_ref", data.get("contract_ref", ""))),
            usage_scope=str(data.get("usage_scope", data.get("commercial_scope", ""))),
            collection_method=str(data.get("collection_method", "")),
            robots_policy=str(data.get("robots_policy", "")),
            last_reviewed_at=parse_datetime(data.get("last_reviewed_at")) if data.get("last_reviewed_at") else None,
            review_cadence=str(data.get("review_cadence", "quarterly")),
            review_owner=str(data.get("review_owner", "")),
            review_owner_role=str(data.get("review_owner_role", "")),
            source_tos_uri=str(data.get("source_tos_uri", "")),
        )


@dataclass(slots=True)
class SourceReviewRecord:
    review_id: str
    source_id: str
    reviewer: str
    reviewed_at: Any = field(default_factory=utcnow)
    review_period: str = ""
    status: str = "approved"
    publicness_status: str = "confirmed_public_or_local"
    tos_status: str = "reviewed"
    robots_status: str = "reviewed_or_not_applicable"
    usage_scope_status: str = "within_boundary"
    notes: str = ""
    findings: list[str] = field(default_factory=list)
    next_review_due_at: Any = None

    def __post_init__(self) -> None:
        _validate_choice(self.status, {"approved", "conditional", "rejected"}, "status")
        _validate_choice(self.publicness_status, {"confirmed_public_or_local", "manual_reference_only", "unclear"}, "publicness_status")
        _validate_choice(self.tos_status, {"reviewed", "not_applicable", "needs_review"}, "tos_status")
        _validate_choice(self.robots_status, {"reviewed_or_not_applicable", "blocked", "needs_review"}, "robots_status")
        _validate_choice(self.usage_scope_status, {"within_boundary", "manual_reference_only", "blocked"}, "usage_scope_status")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SourceReviewRecord":
        return cls(
            review_id=str(data["review_id"]),
            source_id=str(data["source_id"]),
            reviewer=str(data["reviewer"]),
            reviewed_at=parse_datetime(data.get("reviewed_at")) if data.get("reviewed_at") else utcnow(),
            review_period=str(data.get("review_period", "")),
            status=str(data.get("status", "approved")),
            publicness_status=str(data.get("publicness_status", "confirmed_public_or_local")),
            tos_status=str(data.get("tos_status", "reviewed")),
            robots_status=str(data.get("robots_status", "reviewed_or_not_applicable")),
            usage_scope_status=str(data.get("usage_scope_status", "within_boundary")),
            notes=str(data.get("notes", "")),
            findings=[str(item) for item in data.get("findings", [])],
            next_review_due_at=parse_datetime(data.get("next_review_due_at")) if data.get("next_review_due_at") else None,
        )


@dataclass(slots=True)
class AStockConnectorDefinition:
    connector_id: str
    provider: str
    endpoint_type: str
    source_id: str
    rights_tag: RightsTag
    priority: int = 100
    status: str = "candidate"
    requires_key: bool = False
    rate_limit_per_minute: int = 30
    field_mapping: dict[str, str] = field(default_factory=dict)
    allowed_use: list[str] = field(default_factory=lambda: ["manual_reference"])
    notes: str = ""
    last_check_status: str = "not_checked"
    last_error: str = ""
    last_checked_at: Any = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AStockConnectorDefinition":
        return cls(
            connector_id=str(data["connector_id"]),
            provider=str(data["provider"]),
            endpoint_type=str(data["endpoint_type"]),
            source_id=str(data["source_id"]),
            rights_tag=RightsTag.from_dict(data.get("rights_tag", {"license_class": "candidate_astock_reference"})),
            priority=int(data.get("priority", 100)),
            status=str(data.get("status", "candidate")),
            requires_key=bool(data.get("requires_key", False)),
            rate_limit_per_minute=int(data.get("rate_limit_per_minute", 30)),
            field_mapping=dict(data.get("field_mapping", {})),
            allowed_use=[str(item) for item in data.get("allowed_use", ["manual_reference"])],
            notes=str(data.get("notes", "")),
            last_check_status=str(data.get("last_check_status", "not_checked")),
            last_error=str(data.get("last_error", "")),
            last_checked_at=parse_datetime(data.get("last_checked_at")) if data.get("last_checked_at") else None,
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
    locator: dict[str, Any] = field(default_factory=dict)
    assets: list[dict[str, Any]] = field(default_factory=list)
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
class SimulatedExecution:
    execution_id: str
    intent_id: str
    transaction_id: str
    mode: str = "simulated"
    status: str = "filled"
    fill_price: float = 0.0
    quantity: float = 0.0
    notional: float = 0.0
    slippage_bps: float = 0.0
    fees: float = 0.0
    account_id: str = ""
    simulator_version: str = "sim-v1"
    live_execution_allowed: bool = False
    created_by: str = ""
    created_at: Any = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        _validate_choice(self.mode, {"simulated"}, "mode")
        _validate_choice(self.status, {"filled", "rejected"}, "status")
        if self.live_execution_allowed:
            raise ValidationError("simulated execution records cannot enable live execution")


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
class PortfolioTransaction:
    transaction_id: str
    security_id: str
    trade_date: str
    side: str
    quantity: float
    price: float
    currency: str = ""
    fees: float = 0.0
    source_id: str = ""
    account_id: str = ""
    strategy_id: str = ""
    created_at: Any = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        _validate_choice(self.side, {"buy", "sell"}, "side")


@dataclass(slots=True)
class MacroTheme:
    theme_id: str
    name: str
    description: str = ""
    trigger_type: str = "manual"
    as_of_date: str = ""
    source_refs: list[str] = field(default_factory=list)
    macro_drivers: list[str] = field(default_factory=list)
    risk_factors: list[str] = field(default_factory=list)
    confidence: float = 0.5
    created_at: Any = field(default_factory=utcnow)


@dataclass(slots=True)
class IndustryChain:
    chain_id: str
    name: str
    root_theme_id: str = ""
    nodes: list[dict[str, Any]] = field(default_factory=list)
    edges: list[dict[str, Any]] = field(default_factory=list)
    taxonomy_version: str = "industry-chain-v1"
    source_refs: list[str] = field(default_factory=list)
    created_at: Any = field(default_factory=utcnow)


@dataclass(slots=True)
class CompanyPosition:
    position_id: str
    issuer_id: str
    security_id: str = ""
    chain_id: str = ""
    node_ids: list[str] = field(default_factory=list)
    role: str = ""
    positioning_summary: str = ""
    revenue_exposure: dict[str, Any] = field(default_factory=dict)
    profit_exposure: dict[str, Any] = field(default_factory=dict)
    capacity: dict[str, Any] = field(default_factory=dict)
    customers: list[str] = field(default_factory=list)
    suppliers: list[str] = field(default_factory=list)
    competitors: list[str] = field(default_factory=list)
    technology_tags: list[str] = field(default_factory=list)
    valuation_metrics: dict[str, Any] = field(default_factory=dict)
    event_refs: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    data_quality: str = "needs_review"
    created_at: Any = field(default_factory=utcnow)


@dataclass(slots=True)
class HotspotLexicon:
    lexicon_id: str
    name: str
    terms: list[str] = field(default_factory=list)
    synonyms: dict[str, list[str]] = field(default_factory=dict)
    related_chain_nodes: list[dict[str, Any]] = field(default_factory=list)
    default_data_slots: list[str] = field(default_factory=lambda: ["revenue_exposure", "profit_exposure", "capacity", "customers", "suppliers", "valuation_metrics"])
    source_refs: list[str] = field(default_factory=list)
    taxonomy_version: str = "hotspot-lexicon-v1"
    created_at: Any = field(default_factory=utcnow)


@dataclass(slots=True)
class ResearchTask:
    task_id: str
    task_type: str
    source: str = "manual"
    issuer_id: str = ""
    security_id: str = ""
    chain_id: str = ""
    node_ids: list[str] = field(default_factory=list)
    position_id: str = ""
    required_slots: list[str] = field(default_factory=list)
    reason: str = ""
    status: str = "open"
    priority: int = 50
    assignee: str = ""
    evidence_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: Any = field(default_factory=utcnow)
    updated_at: Any = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        _validate_choice(self.status, {"open", "in_progress", "done", "dismissed"}, "status")


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
class LLMTaskTemplate:
    template_id: str
    task_type: str
    prompt_name: str
    prompt_version: str
    content: str
    provider: str = "openai"
    model: str = ""
    status: str = "draft"
    approved_prompt_change_id: str = ""
    fallback_chain: list[str] = field(default_factory=lambda: ["rule_summary", "manual_review"])
    data_domains: list[str] = field(default_factory=list)
    allowed_roles: list[str] = field(default_factory=list)
    risk_level: str = "medium"
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    estimated_cost_per_1k_tokens: float = 0.0
    max_latency_ms: int = 30000
    created_at: Any = field(default_factory=utcnow)
    updated_at: Any = field(default_factory=utcnow)


@dataclass(slots=True)
class LLMTaskRun:
    run_id: str
    template_id: str
    task_type: str
    status: str
    provider: str
    model: str
    prompt_version: str
    input_summary: str = ""
    output: dict[str, Any] = field(default_factory=dict)
    fallback_used: str = ""
    latency_ms: int = 0
    estimated_input_tokens: int = 0
    estimated_output_tokens: int = 0
    estimated_cost: float = 0.0
    error: str = ""
    human_review_required: bool = True
    created_at: Any = field(default_factory=utcnow)


@dataclass(slots=True)
class LLMBudgetApproval:
    approval_id: str
    escalation_id: str
    requested_by: str
    requested_budget: float
    current_budget: float = 0.0
    reason: str = ""
    status: str = "pending"
    approvers: list[dict[str, Any]] = field(default_factory=list)
    linked_notification_ids: list[str] = field(default_factory=list)
    expires_at: Any = None
    created_at: Any = field(default_factory=utcnow)
    updated_at: Any = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        _validate_choice(self.status, {"pending", "approved", "rejected", "expired"}, "status")
        if self.requested_budget <= 0:
            raise ValidationError("requested_budget must be positive")
        if self.current_budget < 0:
            raise ValidationError("current_budget must be non-negative")


@dataclass(slots=True)
class WorkflowDefinition:
    dag_id: str
    name: str
    tasks: list[dict[str, Any]] = field(default_factory=list)
    cadence: str = "manual"
    owner_role: str = "平台负责人"
    status: str = "active"
    idempotency_key_fields: list[str] = field(default_factory=list)
    description: str = ""
    created_at: Any = field(default_factory=utcnow)
    updated_at: Any = field(default_factory=utcnow)


@dataclass(slots=True)
class WorkflowRun:
    run_id: str
    dag_id: str
    status: str
    idempotency_key: str
    inputs: dict[str, Any] = field(default_factory=dict)
    task_statuses: dict[str, str] = field(default_factory=dict)
    output_refs: list[str] = field(default_factory=list)
    error: str = ""
    started_at: Any = field(default_factory=utcnow)
    completed_at: Any = field(default_factory=utcnow)


@dataclass(slots=True)
class LineageEvent:
    lineage_id: str
    job_run_id: str
    dataset: str
    input_refs: list[str] = field(default_factory=list)
    output_refs: list[str] = field(default_factory=list)
    code_version: str = ""
    model_versions: list[str] = field(default_factory=list)
    prompt_versions: list[str] = field(default_factory=list)
    created_at: Any = field(default_factory=utcnow)


@dataclass(slots=True)
class ModelVersionRecord:
    model_version_id: str
    model_name: str
    version: str
    model_type: str = "llm"
    artifact_uri: str = ""
    training_dataset_ids: list[str] = field(default_factory=list)
    prompt_versions: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    status: str = "candidate"
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
    citation_char_limit: int = 0
    citation_truncated: bool = False
    citations: list[dict[str, Any]] = field(default_factory=list)
    human_review_status: str = "pending"
    reviewer: str = ""
    created_at: Any = field(default_factory=utcnow)
    updated_at: Any = field(default_factory=utcnow)


@dataclass(slots=True)
class ResearchReportAsset:
    report_id: str
    source_id: str
    broker: str
    file_path: str
    file_name: str
    title: str
    year: str = ""
    month: str = ""
    file_type: str = "pdf"
    size_bytes: int = 0
    fingerprint: str = ""
    content_sha256: str = ""
    rights_tag: RightsTag = field(default_factory=lambda: RightsTag("local_research_reference", False, False, "restricted", "restricted", "restricted"))
    document_id: str = ""
    issuer_id: str = ""
    security_id: str = ""
    industry: str = ""
    event_ids: list[str] = field(default_factory=list)
    status: str = "indexed"
    indexed_at: Any = field(default_factory=utcnow)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ResearchReportAsset":
        return cls(
            report_id=str(data["report_id"]),
            source_id=str(data["source_id"]),
            broker=str(data.get("broker", "")),
            file_path=str(data["file_path"]),
            file_name=str(data.get("file_name", "")),
            title=str(data.get("title", "")),
            year=str(data.get("year", "")),
            month=str(data.get("month", "")),
            file_type=str(data.get("file_type", "pdf")),
            size_bytes=int(data.get("size_bytes", 0)),
            fingerprint=str(data.get("fingerprint", "")),
            content_sha256=str(data.get("content_sha256", "")),
            rights_tag=RightsTag.from_dict(data.get("rights_tag", {"license_class": "local_research_reference", "display_use": "restricted"})),
            document_id=str(data.get("document_id", "")),
            issuer_id=str(data.get("issuer_id", "")),
            security_id=str(data.get("security_id", "")),
            industry=str(data.get("industry", "")),
            event_ids=[str(item) for item in data.get("event_ids", [])],
            status=str(data.get("status", "indexed")),
            indexed_at=parse_datetime(data.get("indexed_at")),
        )


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
    item_code: str = ""
    item_title: str = ""
    severity: str = "low"
    summary: str = ""
    evidence_ids: list[str] = field(default_factory=list)
    source_id: str = ""
    post_event_performance: dict[str, Any] = field(default_factory=dict)
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
class ReadinessCheckRecord:
    check_id: str
    status: str
    owner: str
    evidence_uri: str = ""
    notes: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)
    measured_at: Any = field(default_factory=utcnow)
    expires_at: Any = None
    updated_at: Any = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        _validate_choice(self.status, {"pending", "passed", "failed", "blocked"}, "status")


@dataclass(slots=True)
class SecretRotationRecord:
    rotation_id: str
    secret_name: str
    provider: str
    owner: str
    status: str = "rotated"
    evidence_uri: str = ""
    notes: str = ""
    rotated_at: Any = field(default_factory=utcnow)
    next_rotation_due_at: Any = None
    created_at: Any = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        _validate_choice(self.status, {"scheduled", "rotated", "failed", "waived"}, "status")


@dataclass(slots=True)
class CacheRetentionRunRecord:
    run_id: str
    actor: str
    status: str = "dry_run_recorded"
    dry_run: bool = True
    execute_requested: bool = False
    reviewed_count: int = 0
    retained_count: int = 0
    due_soon_count: int = 0
    expired_count: int = 0
    no_cache_count: int = 0
    deletion_required_count: int = 0
    filters: dict[str, Any] = field(default_factory=dict)
    records: list[dict[str, Any]] = field(default_factory=list)
    usage_boundary: str = "cache_retention_records_are_governance_evidence_not_physical_delete"
    execution_evidence_uri: str = ""
    execution_provider: str = ""
    external_deleted_count: int = 0
    execution_notes: str = ""
    executed_at: Any = None
    as_of: Any = field(default_factory=utcnow)
    created_at: Any = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        _validate_choice(self.status, {"dry_run_recorded", "approval_required", "executed_outside_app"}, "status")


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
    confidence: float = 0.0
    source: str = "entity_mapping_registry"
    version: str = "v1"
    created_at: Any = field(default_factory=utcnow)


@dataclass(slots=True)
class EntityMappingLabel:
    label_id: str
    mapping_id: str
    issuer_id: str
    ticker: str
    market: str
    reviewer: str = ""
    source: str = "manual_gold_label"
    notes: str = ""
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
    last_run_at: Any = None
    last_result: str = ""
    rca_summary: str = ""
    action_items: list[str] = field(default_factory=list)
