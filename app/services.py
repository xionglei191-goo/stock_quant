from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
import os
import re
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

from .errors import ComplianceGateError, ConflictError, NotFoundError, PermissionDenied, ValidationError
from .connectors import ConnectorRegistry
from .llm_gateway import LLMGateway
from .models import (
    AuditEvent,
    AlertNotification,
    AlertRule,
    BenchmarkConfig,
    BenchmarkResult,
    BenchmarkRun,
    BenchmarkSample,
    CorporateAction,
    DrillSchedule,
    DisclosureEvent,
    EntityMapping,
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
    Issuer,
    ManualReviewItem,
    MarketDataPoint,
    OperatingReport,
    PortfolioProposal,
    PromptChangeRequest,
    ResearchAnswer,
    ResearchCard,
    ResearchTemplate,
    ResearchSignal,
    ReviewRecord,
    Security,
    ScorecardProfile,
    SourceDefinition,
    StrategyReplay,
    SystemAlert,
    ThesisCard,
)
from .object_store import create_object_store_from_env
from .search import LocalSearchIndex, SearchRecord, create_search_index_from_env
from .store import InMemoryStore
from .utils import chunk_text, chunk_text_by_page, looks_like_html, new_id, parse_datetime, pdf_bytes_to_text, to_plain, utcnow


DEFAULT_SEC_USER_AGENT = "ai-native-quant-org/0.1 contact@example.com"
DEFAULT_HKEX_USER_AGENT = "ai-native-quant-org/0.1 contact@example.com"

TERM_LEXICON = {
    "revenue": ["revenue", "sales", "营业收入", "收入"],
    "net_profit": ["net profit", "profit attributable", "归母净利润", "净利润"],
    "gross_margin": ["gross margin", "毛利率"],
    "operating_cash_flow": ["operating cash flow", "经营活动现金流", "经营现金流"],
    "risk_factor": ["risk factor", "risk factors", "风险因素", "主要风险"],
}


class SystemService:
    def __init__(self, store: InMemoryStore | None = None):
        self.store = store or InMemoryStore()
        self.connectors = ConnectorRegistry()
        self.llm_gateway = LLMGateway()
        self.object_store = create_object_store_from_env(Path.cwd() / "data" / "objects")
        self.search_index = create_search_index_from_env()
        self.local_search_index = LocalSearchIndex()
        self.search_fallback = os.environ.get("AI_QUANT_SEARCH_FALLBACK", "true").strip().lower() not in {"0", "false", "no"}
        self.started_at = utcnow()
        self.trace_id = ""

    def set_trace_id(self, trace_id: str) -> None:
        self.trace_id = trace_id

    def llm_openai_chat_completions(self, payload: Mapping[str, Any], *, actor: str = "system") -> dict[str, Any]:
        result = self.llm_gateway.openai_chat_completions(payload)
        self._audit(actor, "llm_openai_chat_completions", "llm_gateway", result["endpoint"], source="llm_gateway", model_version=result["model"])
        return result

    def llm_anthropic_messages(self, payload: Mapping[str, Any], *, actor: str = "system") -> dict[str, Any]:
        result = self.llm_gateway.anthropic_messages(payload)
        self._audit(actor, "llm_anthropic_messages", "llm_gateway", result["endpoint"], source="llm_gateway", model_version=result["model"])
        return result

    def _audit(
        self,
        actor: str,
        action: str,
        resource_type: str,
        resource_id: str,
        *,
        source: str = "api",
        version: str = "",
        model_version: str = "",
        prompt_version: str = "",
        approval_state: str = "",
        trace_id: str = "",
    ) -> None:
        self.store.audit_log.append(
            AuditEvent(
                event_id=new_id("evt"),
                actor=actor,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                source=source,
                version=version,
                model_version=model_version,
                prompt_version=prompt_version,
                approval_state=approval_state,
                trace_id=trace_id or self.trace_id,
            )
        )
        self.store.commit()

    def register_source(self, payload: Mapping[str, Any], *, actor: str = "system") -> SourceDefinition:
        source = payload if isinstance(payload, SourceDefinition) else SourceDefinition.from_dict(payload)
        if source.source_id in self.store.sources:
            raise ConflictError(f"source {source.source_id} already exists")
        self.store.sources[source.source_id] = source
        self._audit(actor, "register_source", "source", source.source_id, source=source.source_type, version=source.rights_tag.license_class)
        return source

    def seed_default_sources(self, *, actor: str = "system") -> list[SourceDefinition]:
        defaults = [
            {
                "source_id": "ashare_exchange",
                "source_type": "exchange",
                "risk_level": "green",
                "allowed_document_types": ["announcement", "annual_report"],
                "rights_tag": {
                    "license_class": "public",
                    "training_allowed": False,
                    "redistribution_allowed": False,
                    "display_use": "allowed",
                    "non_display_use": "restricted",
                    "derived_data_use": "restricted",
                },
            },
            {
                "source_id": "hkexnews",
                "source_type": "exchange",
                "risk_level": "green",
                "allowed_document_types": ["announcement", "annual_report"],
                "rights_tag": {
                    "license_class": "public",
                    "training_allowed": False,
                    "redistribution_allowed": False,
                    "display_use": "allowed",
                    "non_display_use": "restricted",
                    "derived_data_use": "restricted",
                },
            },
            {
                "source_id": "sec_edgar",
                "source_type": "regulatory",
                "risk_level": "green",
                "allowed_document_types": ["10-K", "10-Q", "8-K", "20-F", "6-K", "13F-HR", "13F-HR/A"],
                "rights_tag": {
                    "license_class": "public",
                    "training_allowed": False,
                    "redistribution_allowed": False,
                    "display_use": "allowed",
                    "non_display_use": "restricted",
                    "derived_data_use": "restricted",
                },
            },
            {
                "source_id": "authorized_eod_market_data",
                "source_type": "vendor",
                "description": "Whitelisted EOD or delayed market data for research, valuation, backtesting, and risk monitoring.",
                "risk_level": "yellow",
                "field_mapping": {
                    "security_id": "security_id",
                    "as_of_date": "as_of_date",
                    "close": "close",
                    "volume": "volume",
                },
                "rights_tag": {
                    "license_class": "authorized_eod_research",
                    "training_allowed": False,
                    "redistribution_allowed": False,
                    "display_use": "allowed",
                    "non_display_use": "allowed",
                    "derived_data_use": "restricted",
                },
            },
            {
                "source_id": "company_public_webcast",
                "source_type": "company_ir",
                "description": "Company-published public webcast, presentation, or transcript; retain source URI and citation boundary.",
                "risk_level": "green",
                "allowed_document_types": ["transcript", "presentation", "webcast"],
                "rights_tag": {
                    "license_class": "public_company_ir_reference",
                    "training_allowed": False,
                    "redistribution_allowed": False,
                    "display_use": "allowed",
                    "non_display_use": "restricted",
                    "derived_data_use": "restricted",
                },
            },
            {
                "source_id": "authorized_transcript_vendor",
                "source_type": "vendor",
                "description": "Contracted transcript source for internal reference only; no training, redistribution, or derived data without contract review.",
                "risk_level": "yellow",
                "allowed_document_types": ["transcript"],
                "rights_tag": {
                    "license_class": "authorized_transcript_internal",
                    "training_allowed": False,
                    "redistribution_allowed": False,
                    "display_use": "restricted",
                    "non_display_use": "restricted",
                    "derived_data_use": "restricted",
                },
            },
            {
                "source_id": "authorized_research_vendor",
                "source_type": "vendor",
                "description": "Contracted sell-side or expert research for citation tracking and analyst reference only.",
                "risk_level": "yellow",
                "allowed_document_types": ["research"],
                "rights_tag": {
                    "license_class": "authorized_research_reference",
                    "training_allowed": False,
                    "redistribution_allowed": False,
                    "display_use": "restricted",
                    "non_display_use": "restricted",
                    "derived_data_use": "restricted",
                },
            },
        ]
        created: list[SourceDefinition] = []
        for item in defaults:
            if item["source_id"] in self.store.sources:
                created.append(self.store.sources[item["source_id"]])
                continue
            created.append(self.register_source(item, actor=actor))
        return created

    def preview_connector_document(self, market: str, raw: Mapping[str, Any]) -> dict[str, Any]:
        normalized = self.connectors.normalize(market, dict(raw))
        return to_plain(normalized)

    def fetch_sec_recent_filings(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        cik = str(payload["cik"])
        documents = self.connectors.fetch_sec_recent_filings(
            cik,
            user_agent=self._sec_user_agent(payload),
            limit=self._bounded_limit(payload.get("limit", 10)),
            document_types=list(payload.get("document_types", [])) or None,
        )
        return {"filings": [to_plain(document) for document in documents]}

    def fetch_ashare_recent_filings(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        security_code = str(payload["security_code"])
        documents = self.connectors.fetch_ashare_recent_filings(
            security_code,
            user_agent=self._ashare_user_agent(payload),
            limit=self._bounded_limit(payload.get("limit", 10)),
            begin_date=str(payload.get("begin_date", "")),
            end_date=str(payload.get("end_date", "")),
            report_type=str(payload.get("report_type", "ALL")),
            security_type=str(payload.get("security_type", "0101,120100,020100,020200,120200")),
            exchange=str(payload.get("exchange", "auto")),
        )
        return {"filings": [to_plain(document) for document in documents]}

    def fetch_hkex_recent_filings(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        query = str(payload["query"])
        documents = self.connectors.fetch_hkex_recent_filings(
            query,
            user_agent=self._hkex_user_agent(payload),
            limit=self._bounded_limit(payload.get("limit", 10)),
            file_type=str(payload.get("file_type", "pdf")),
            language=str(payload.get("language", "en-UK")),
        )
        return {"filings": [to_plain(document) for document in documents]}

    def ingest_sec_recent_filings(self, payload: Mapping[str, Any], *, actor: str = "system") -> dict[str, Any]:
        issuer_id = str(payload["issuer_id"])
        if issuer_id not in self.store.issuers:
            raise NotFoundError(f"issuer {issuer_id} not found")
        security_id = str(payload.get("security_id", ""))
        if security_id and security_id not in self.store.securities:
            raise NotFoundError(f"security {security_id} not found")
        source_id = str(payload.get("source_id", "sec_edgar"))
        if source_id not in self.store.sources:
            if source_id == "sec_edgar":
                self.seed_default_sources(actor=actor)
            else:
                raise NotFoundError(f"source {source_id} not found")
        source = self.store.sources[source_id]
        user_agent = self._sec_user_agent(payload)
        include_body = bool(payload.get("include_body", False))
        include_attachment = bool(payload.get("include_attachment", False))
        max_body_bytes = int(payload.get("max_body_bytes", 2_000_000))
        max_attachment_bytes = int(payload.get("max_attachment_bytes", 10_000_000))
        filings = self.connectors.fetch_sec_recent_filings(
            str(payload["cik"]),
            user_agent=user_agent,
            limit=self._bounded_limit(payload.get("limit", 10)),
            document_types=list(payload.get("document_types", [])) or None,
        )
        created: list[dict[str, Any]] = []
        skipped: list[dict[str, str]] = []
        for filing in filings:
            document_id = self._sec_document_id(filing)
            if document_id in self.store.documents:
                skipped.append({"document_id": document_id, "reason": "already_exists"})
                continue
            body = filing.body
            if include_body:
                body = self.connectors.fetch_sec_document_body(filing.source_uri, user_agent=user_agent, max_bytes=max_body_bytes)
            stored_attachment = self._store_attachment("U", filing, document_id, user_agent=user_agent, max_bytes=max_attachment_bytes) if include_attachment else None
            document = self.ingest_document(
                {
                    "document_id": document_id,
                    "issuer_id": issuer_id,
                    "security_id": security_id,
                    "source_id": source_id,
                    "source_type": filing.source_type,
                    "document_type": filing.document_type,
                    "source_uri": filing.source_uri,
                    "rights_tag": to_plain(source.rights_tag),
                    "body": body,
                    "title": filing.title,
                    "object_uri": stored_attachment.uri if stored_attachment else "",
                    "content_sha256": stored_attachment.sha256 if stored_attachment else "",
                    "published_at": filing.published_at or None,
                    "language": filing.language,
                    "version": "sec_recent",
                },
                actor=actor,
            )
            created.append(to_plain(document))
        return {"created": created, "skipped": skipped}

    def ingest_ashare_recent_filings(self, payload: Mapping[str, Any], *, actor: str = "system") -> dict[str, Any]:
        issuer_id = str(payload["issuer_id"])
        if issuer_id not in self.store.issuers:
            raise NotFoundError(f"issuer {issuer_id} not found")
        security_id = str(payload.get("security_id", ""))
        if security_id and security_id not in self.store.securities:
            raise NotFoundError(f"security {security_id} not found")
        source_id = str(payload.get("source_id", "ashare_exchange"))
        if source_id not in self.store.sources:
            if source_id == "ashare_exchange":
                self.seed_default_sources(actor=actor)
            else:
                raise NotFoundError(f"source {source_id} not found")
        source = self.store.sources[source_id]
        filings = self.connectors.fetch_ashare_recent_filings(
            str(payload["security_code"]),
            user_agent=self._ashare_user_agent(payload),
            limit=self._bounded_limit(payload.get("limit", 10)),
            begin_date=str(payload.get("begin_date", "")),
            end_date=str(payload.get("end_date", "")),
            report_type=str(payload.get("report_type", "ALL")),
            security_type=str(payload.get("security_type", "0101,120100,020100,020200,120200")),
            exchange=str(payload.get("exchange", "auto")),
        )
        created: list[dict[str, Any]] = []
        skipped: list[dict[str, str]] = []
        include_attachment = bool(payload.get("include_attachment", False))
        max_attachment_bytes = int(payload.get("max_attachment_bytes", 10_000_000))
        user_agent = self._ashare_user_agent(payload)
        for filing in filings:
            document_id = self._ashare_document_id(filing)
            if document_id in self.store.documents:
                skipped.append({"document_id": document_id, "reason": "already_exists"})
                continue
            stored_attachment = self._store_attachment("A", filing, document_id, user_agent=user_agent, max_bytes=max_attachment_bytes) if include_attachment else None
            document = self.ingest_document(
                {
                    "document_id": document_id,
                    "issuer_id": issuer_id,
                    "security_id": security_id,
                    "source_id": source_id,
                    "source_type": filing.source_type,
                    "document_type": filing.document_type,
                    "source_uri": filing.source_uri,
                    "rights_tag": to_plain(source.rights_tag),
                    "body": filing.body or filing.title,
                    "title": filing.title,
                    "object_uri": stored_attachment.uri if stored_attachment else "",
                    "content_sha256": stored_attachment.sha256 if stored_attachment else "",
                    "published_at": filing.published_at or None,
                    "language": filing.language,
                    "version": "ashare_recent",
                },
                actor=actor,
            )
            created.append(to_plain(document))
        return {"created": created, "skipped": skipped}

    def ingest_hkex_recent_filings(self, payload: Mapping[str, Any], *, actor: str = "system") -> dict[str, Any]:
        issuer_id = str(payload["issuer_id"])
        if issuer_id not in self.store.issuers:
            raise NotFoundError(f"issuer {issuer_id} not found")
        security_id = str(payload.get("security_id", ""))
        if security_id and security_id not in self.store.securities:
            raise NotFoundError(f"security {security_id} not found")
        source_id = str(payload.get("source_id", "hkexnews"))
        if source_id not in self.store.sources:
            if source_id == "hkexnews":
                self.seed_default_sources(actor=actor)
            else:
                raise NotFoundError(f"source {source_id} not found")
        source = self.store.sources[source_id]
        filings = self.connectors.fetch_hkex_recent_filings(
            str(payload["query"]),
            user_agent=self._hkex_user_agent(payload),
            limit=self._bounded_limit(payload.get("limit", 10)),
            file_type=str(payload.get("file_type", "pdf")),
            language=str(payload.get("language", "en-UK")),
        )
        created: list[dict[str, Any]] = []
        skipped: list[dict[str, str]] = []
        include_attachment = bool(payload.get("include_attachment", False))
        max_attachment_bytes = int(payload.get("max_attachment_bytes", 10_000_000))
        user_agent = self._hkex_user_agent(payload)
        for filing in filings:
            document_id = self._hkex_document_id(filing)
            if document_id in self.store.documents:
                skipped.append({"document_id": document_id, "reason": "already_exists"})
                continue
            stored_attachment = self._store_attachment("H", filing, document_id, user_agent=user_agent, max_bytes=max_attachment_bytes) if include_attachment else None
            document = self.ingest_document(
                {
                    "document_id": document_id,
                    "issuer_id": issuer_id,
                    "security_id": security_id,
                    "source_id": source_id,
                    "source_type": filing.source_type,
                    "document_type": filing.document_type,
                    "source_uri": filing.source_uri,
                    "rights_tag": to_plain(source.rights_tag),
                    "body": filing.body,
                    "title": filing.title,
                    "object_uri": stored_attachment.uri if stored_attachment else "",
                    "content_sha256": stored_attachment.sha256 if stored_attachment else "",
                    "published_at": filing.published_at or None,
                    "language": filing.language,
                    "version": "hkex_recent",
                },
                actor=actor,
            )
            created.append(to_plain(document))
        return {"created": created, "skipped": skipped}

    def run_ingestion_job(self, payload: Mapping[str, Any], *, actor: str = "system") -> IngestionJob:
        items = list(payload.get("items", []))
        job = IngestionJob(
            job_id=str(payload.get("job_id", new_id("job"))),
            status="running",
            total=len(items),
            completed_at=utcnow(),
        )
        if job.job_id in self.store.ingestion_jobs:
            raise ConflictError(f"ingestion job {job.job_id} already exists")
        default_rights = payload.get("rights_tag")
        include_body = bool(payload.get("include_body", False))
        user_agent = self._sec_user_agent(payload)
        for index, item in enumerate(items):
            try:
                market = str(item["market"])
                issuer_id = str(item["issuer_id"])
                security_id = str(item.get("security_id", ""))
                raw = dict(item["raw"])
                normalized = self.connectors.normalize(market, raw)
                source_id = str(item.get("source_id", normalized.source_id))
                if source_id not in self.store.sources:
                    if source_id in {"ashare_exchange", "hkexnews", "sec_edgar"}:
                        self.seed_default_sources(actor=actor)
                    else:
                        raise NotFoundError(f"source {source_id} not found")
                if issuer_id not in self.store.issuers:
                    raise NotFoundError(f"issuer {issuer_id} not found")
                if security_id and security_id not in self.store.securities:
                    raise NotFoundError(f"security {security_id} not found")
                document_id = str(item.get("document_id", self._job_document_id(market, raw, normalized.source_uri)))
                if document_id in self.store.documents:
                    job.skipped += 1
                    continue
                body = str(item.get("body", normalized.body))
                if include_body and market == "U" and normalized.source_uri and not body:
                    body = self.connectors.fetch_sec_document_body(normalized.source_uri, user_agent=user_agent, max_bytes=int(payload.get("max_body_bytes", 2_000_000)))
                source = self.store.sources[source_id]
                document = self.ingest_document(
                    {
                        "document_id": document_id,
                        "issuer_id": issuer_id,
                        "security_id": security_id,
                        "source_id": source_id,
                        "source_type": normalized.source_type,
                        "document_type": normalized.document_type,
                        "source_uri": normalized.source_uri,
                        "rights_tag": dict(default_rights or item.get("rights_tag") or to_plain(source.rights_tag)),
                        "body": body,
                        "title": normalized.title,
                        "published_at": normalized.published_at or None,
                        "language": normalized.language,
                        "version": str(payload.get("version", "job")),
                    },
                    actor=actor,
                )
                job.created += 1
                job.created_document_ids.append(document.document_id)
            except Exception as exc:
                job.failed += 1
                job.errors.append({"index": index, "error": str(exc)})
        job.status = "failed" if job.failed and not job.created else "partial" if job.failed else "completed"
        job.completed_at = utcnow()
        self.store.ingestion_jobs[job.job_id] = job
        self._audit(actor, "run_ingestion_job", "ingestion_job", job.job_id, approval_state=job.status)
        return job

    def register_ingestion_schedule(self, payload: Mapping[str, Any], *, actor: str = "system") -> IngestionSchedule:
        schedule = IngestionSchedule(
            schedule_id=str(payload.get("schedule_id", new_id("sched"))),
            name=str(payload.get("name", "ingestion schedule")),
            payload=dict(payload.get("payload", {})),
            cadence=str(payload.get("cadence", "manual")),
            status=str(payload.get("status", "active")),
            retry_limit=int(payload.get("retry_limit", 2)),
            next_run_at=parse_datetime(payload.get("next_run_at")),
        )
        if schedule.schedule_id in self.store.ingestion_schedules:
            raise ConflictError(f"ingestion schedule {schedule.schedule_id} already exists")
        self.store.ingestion_schedules[schedule.schedule_id] = schedule
        self._audit(actor, "register_ingestion_schedule", "ingestion_schedule", schedule.schedule_id, approval_state=schedule.status)
        return schedule

    def run_ingestion_schedules(self, payload: Mapping[str, Any] | None = None, *, actor: str = "system") -> dict[str, Any]:
        payload = payload or {}
        now = utcnow()
        due_only = bool(payload.get("due_only", True))
        schedule_ids = {str(item) for item in payload.get("schedule_ids", [])}
        ran: list[dict[str, Any]] = []
        skipped: list[dict[str, str]] = []
        for schedule in list(self.store.ingestion_schedules.values()):
            if schedule_ids and schedule.schedule_id not in schedule_ids:
                continue
            if schedule.status not in {"active", "retrying"}:
                skipped.append({"schedule_id": schedule.schedule_id, "reason": schedule.status})
                continue
            if due_only and schedule.next_run_at > now:
                skipped.append({"schedule_id": schedule.schedule_id, "reason": "not_due"})
                continue
            result = self._run_ingestion_schedule(schedule, actor=actor)
            ran.append(result)
        return {"ran": ran, "skipped": skipped}

    def _run_ingestion_schedule(self, schedule: IngestionSchedule, *, actor: str) -> dict[str, Any]:
        run_payload = dict(schedule.payload)
        base_job_id = str(run_payload.get("job_id") or schedule.schedule_id)
        run_payload["job_id"] = f"{base_job_id}_{utcnow().strftime('%Y%m%d%H%M%S')}"
        try:
            job = self.run_ingestion_job(run_payload, actor=actor)
            schedule.last_job_id = job.job_id
            schedule.last_status = job.status
            schedule.last_error = ""
            if job.status in {"completed", "partial"}:
                schedule.retry_count = 0
                schedule.status = "active"
                schedule.next_run_at = self._next_schedule_run(schedule.cadence)
            else:
                self._mark_schedule_retry(schedule, f"job status {job.status}")
            schedule.updated_at = utcnow()
            self.store.commit()
            self._audit(actor, "run_ingestion_schedule", "ingestion_schedule", schedule.schedule_id, approval_state=schedule.status)
            return {"schedule_id": schedule.schedule_id, "job": to_plain(job), "status": schedule.status}
        except Exception as exc:
            self._mark_schedule_retry(schedule, str(exc))
            schedule.updated_at = utcnow()
            self.store.commit()
            self._audit(actor, "run_ingestion_schedule", "ingestion_schedule", schedule.schedule_id, approval_state=schedule.status)
            return {"schedule_id": schedule.schedule_id, "error": str(exc), "status": schedule.status}

    def register_issuer(self, payload: Mapping[str, Any], *, actor: str = "system") -> Issuer:
        issuer = payload if isinstance(payload, Issuer) else Issuer.from_dict(payload)
        if issuer.issuer_id in self.store.issuers:
            raise ConflictError(f"issuer {issuer.issuer_id} already exists")
        self.store.issuers[issuer.issuer_id] = issuer
        self._audit(actor, "register_issuer", "issuer", issuer.issuer_id)
        return issuer

    def register_security(self, payload: Mapping[str, Any], *, actor: str = "system") -> Security:
        security = payload if isinstance(payload, Security) else Security.from_dict(payload)
        if security.issuer_id not in self.store.issuers:
            raise NotFoundError(f"issuer {security.issuer_id} not found")
        if security.security_id in self.store.securities:
            raise ConflictError(f"security {security.security_id} already exists")
        self.store.securities[security.security_id] = security
        self._audit(actor, "register_security", "security", security.security_id)
        return security

    def register_market_data_point(self, payload: Mapping[str, Any], *, actor: str = "system") -> MarketDataPoint:
        security_id = str(payload["security_id"])
        security = self.store.securities.get(security_id)
        if security is None:
            raise NotFoundError(f"security {security_id} not found")
        source_id = str(payload.get("source_id", "authorized_eod_market_data"))
        if source_id not in self.store.sources:
            if source_id == "authorized_eod_market_data":
                self.seed_default_sources(actor=actor)
            else:
                raise NotFoundError(f"source {source_id} not found")
        source = self.store.sources[source_id]
        if source.risk_level == "red":
            raise PermissionDenied("red market data source cannot enter research layer")
        market = str(payload.get("market", security.market))
        if market != security.market:
            raise ValidationError(f"market {market} does not match security market {security.market}")
        as_of_date = str(payload["as_of_date"])
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", as_of_date):
            raise ValidationError("as_of_date must use YYYY-MM-DD")
        data_type = str(payload.get("data_type", "eod"))
        if data_type not in {"eod", "delayed"}:
            raise ValidationError("market data only supports authorized eod or delayed data")
        rights_tag = source.rights_tag if "rights_tag" not in payload else type(source.rights_tag).from_dict(payload["rights_tag"])
        if not source.rights_tag.allows(rights_tag):
            raise PermissionDenied("market data rights exceed source rights")
        prices = {
            "open": float(payload.get("open", 0.0)),
            "high": float(payload.get("high", 0.0)),
            "low": float(payload.get("low", 0.0)),
            "close": float(payload.get("close", 0.0)),
            "adjusted_close": float(payload.get("adjusted_close", payload.get("close", 0.0))),
            "volume": float(payload.get("volume", 0.0)),
        }
        if any(value < 0 for value in prices.values()):
            raise ValidationError("market data prices and volume must be non-negative")
        data_id = str(payload.get("data_id", self._market_data_id(security_id, as_of_date, data_type, source_id)))
        if data_id in self.store.market_data:
            raise ConflictError(f"market data {data_id} already exists")
        point = MarketDataPoint(
            data_id=data_id,
            security_id=security_id,
            source_id=source_id,
            market=market,
            as_of_date=as_of_date,
            data_type=data_type,
            currency=str(payload.get("currency", security.currency)),
            rights_tag=rights_tag,
            **prices,
        )
        self.store.market_data[point.data_id] = point
        self._audit(
            actor,
            "register_market_data_point",
            "market_data",
            point.data_id,
            source=source.source_type,
            version=point.rights_tag.license_class,
            approval_state=point.data_type,
        )
        return point

    def register_market_data_batch(self, payload: Mapping[str, Any], *, actor: str = "system") -> dict[str, Any]:
        items = payload.get("items", [])
        if not isinstance(items, list):
            raise ValidationError("market data batch requires items list")
        created: list[MarketDataPoint] = []
        errors: list[dict[str, Any]] = []
        for index, item in enumerate(items):
            if not isinstance(item, Mapping):
                errors.append({"index": index, "error": "item must be an object"})
                continue
            try:
                created.append(self.register_market_data_point(item, actor=actor))
            except (ValidationError, NotFoundError, PermissionDenied, ConflictError) as exc:
                errors.append({"index": index, "error": str(exc)})
        self._audit(actor, "register_market_data_batch", "market_data", str(payload.get("batch_id", "batch")), approval_state=f"created={len(created)};failed={len(errors)}")
        return {"created": [to_plain(item) for item in created], "errors": errors, "created_count": len(created), "failed_count": len(errors)}

    def register_corporate_action(self, payload: Mapping[str, Any], *, actor: str = "system") -> CorporateAction:
        security_id = str(payload["security_id"])
        if security_id not in self.store.securities:
            raise NotFoundError(f"security {security_id} not found")
        source_id = str(payload.get("source_id", "authorized_eod_market_data"))
        if source_id not in self.store.sources:
            if source_id == "authorized_eod_market_data":
                self.seed_default_sources(actor=actor)
            else:
                raise NotFoundError(f"source {source_id} not found")
        source = self.store.sources[source_id]
        if source.risk_level == "red":
            raise PermissionDenied("red corporate action source cannot enter research layer")
        action_type = str(payload["action_type"])
        if action_type not in {"split", "reverse_split", "cash_dividend", "stock_dividend", "symbol_change"}:
            raise ValidationError("unsupported corporate action type")
        ex_date = str(payload["ex_date"])
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", ex_date):
            raise ValidationError("ex_date must use YYYY-MM-DD")
        action = CorporateAction(
            action_id=str(payload.get("action_id", self._corporate_action_id(security_id, action_type, ex_date, source_id))),
            security_id=security_id,
            source_id=source_id,
            action_type=action_type,
            ex_date=ex_date,
            ratio=float(payload.get("ratio", 1.0)),
            cash_amount=float(payload.get("cash_amount", 0.0)),
            currency=str(payload.get("currency", self.store.securities[security_id].currency)),
            description=str(payload.get("description", "")),
        )
        if action.ratio < 0 or action.cash_amount < 0:
            raise ValidationError("corporate action ratio and cash amount must be non-negative")
        if action.action_id in self.store.corporate_actions:
            raise ConflictError(f"corporate action {action.action_id} already exists")
        self.store.corporate_actions[action.action_id] = action
        self._audit(actor, "register_corporate_action", "corporate_action", action.action_id, source=source.source_type, approval_state=action.action_type)
        return action

    def corporate_actions_payload(self, filters: Mapping[str, Any] | None = None) -> dict[str, Any]:
        filters = filters or {}
        security_id = str(filters.get("security_id", "")).strip()
        action_type = str(filters.get("action_type", "")).strip()
        limit = self._bounded_limit(filters.get("limit", 50))
        actions = list(self.store.corporate_actions.values())
        if security_id:
            actions = [item for item in actions if item.security_id == security_id]
        if action_type:
            actions = [item for item in actions if item.action_type == action_type]
        actions.sort(key=lambda item: (item.ex_date, item.security_id), reverse=True)
        return {"count": len(actions), "corporate_actions": [to_plain(item) for item in actions[:limit]]}

    def market_data_payload(self, filters: Mapping[str, Any] | None = None) -> dict[str, Any]:
        filters = filters or {}
        security_id = str(filters.get("security_id", "")).strip()
        market = str(filters.get("market", "")).strip()
        source_id = str(filters.get("source_id", "")).strip()
        data_type = str(filters.get("data_type", "")).strip()
        limit = self._bounded_limit(filters.get("limit", 50))
        points = list(self.store.market_data.values())
        if security_id:
            points = [item for item in points if item.security_id == security_id]
        if market:
            points = [item for item in points if item.market == market]
        if source_id:
            points = [item for item in points if item.source_id == source_id]
        if data_type:
            points = [item for item in points if item.data_type == data_type]
        points.sort(key=lambda item: (item.as_of_date, item.security_id, item.source_id), reverse=True)
        return {"market_data": [to_plain(item) for item in points[:limit]]}

    def register_entity_mapping(self, payload: Mapping[str, Any], *, actor: str = "system") -> EntityMapping:
        issuer_id = str(payload["issuer_id"])
        if issuer_id not in self.store.issuers:
            raise NotFoundError(f"issuer {issuer_id} not found")
        mapping_id = str(payload.get("mapping_id", new_id("map")))
        if mapping_id in self.store.entity_mappings:
            raise ConflictError(f"entity mapping {mapping_id} already exists")
        mapping = EntityMapping(
            mapping_id=mapping_id,
            issuer_id=issuer_id,
            lei=str(payload.get("lei", "")),
            cik=str(payload.get("cik", "")),
            figi=str(payload.get("figi", "")),
            isin=str(payload.get("isin", "")),
            ticker=str(payload.get("ticker", "")),
            market=str(payload.get("market", "")),
        )
        self.store.entity_mappings[mapping.mapping_id] = mapping
        self._audit(actor, "register_entity_mapping", "mapping", mapping.mapping_id)
        return mapping

    def register_entity_mapping_batch(self, payload: Mapping[str, Any], *, actor: str = "system") -> dict[str, Any]:
        items = payload.get("items", [])
        if not isinstance(items, list):
            raise ValidationError("entity mapping batch requires items list")
        created: list[EntityMapping] = []
        errors: list[dict[str, Any]] = []
        for index, item in enumerate(items):
            if not isinstance(item, Mapping):
                errors.append({"index": index, "error": "item must be an object"})
                continue
            try:
                created.append(self.register_entity_mapping(item, actor=actor))
            except (ValidationError, NotFoundError, ConflictError) as exc:
                errors.append({"index": index, "error": str(exc)})
        self._audit(actor, "register_entity_mapping_batch", "mapping", str(payload.get("batch_id", "batch")), approval_state=f"created={len(created)};failed={len(errors)}")
        return {"created": [to_plain(item) for item in created], "errors": errors, "created_count": len(created), "failed_count": len(errors)}

    def entity_mapping_quality_report(self, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        payload = payload or {}
        issuer_id = str(payload.get("issuer_id", "")).strip()
        mappings = list(self.store.entity_mappings.values())
        if issuer_id:
            mappings = [item for item in mappings if item.issuer_id == issuer_id]
        labels = payload.get("labels", [])
        checked = 0
        correct = 0
        mismatches: list[dict[str, Any]] = []
        if isinstance(labels, list):
            mapping_by_id = {item.mapping_id: item for item in self.store.entity_mappings.values()}
            for label in labels:
                if not isinstance(label, Mapping):
                    continue
                mapping = mapping_by_id.get(str(label.get("mapping_id", "")))
                if mapping is None:
                    mismatches.append({"mapping_id": str(label.get("mapping_id", "")), "reason": "missing_mapping"})
                    checked += 1
                    continue
                expected = {
                    "issuer_id": str(label.get("issuer_id", mapping.issuer_id)),
                    "market": str(label.get("market", mapping.market)),
                    "ticker": str(label.get("ticker", mapping.ticker)),
                }
                actual = {"issuer_id": mapping.issuer_id, "market": mapping.market, "ticker": mapping.ticker}
                checked += 1
                if actual == expected:
                    correct += 1
                else:
                    mismatches.append({"mapping_id": mapping.mapping_id, "expected": expected, "actual": actual})
        covered_issuers = {item.issuer_id for item in mappings}
        market_counts: dict[str, int] = {}
        for mapping in mappings:
            market_counts[mapping.market] = market_counts.get(mapping.market, 0) + 1
        return {
            "issuer_id": issuer_id,
            "mappings": len(mappings),
            "covered_issuers": len(covered_issuers),
            "market_counts": market_counts,
            "checked_labels": checked,
            "accuracy": round(correct / max(1, checked), 4) if checked else 0.0,
            "mismatches": mismatches,
        }

    def ingest_document(self, payload: Mapping[str, Any], *, actor: str = "system") -> Document:
        document = payload if isinstance(payload, Document) else Document.from_dict(payload)
        issuer = self.store.issuers.get(document.issuer_id)
        if issuer is None:
            raise NotFoundError(f"issuer {document.issuer_id} not found")
        source = self.store.sources.get(document.source_id)
        if source is None:
            raise NotFoundError(f"source {document.source_id} not found")
        if not source.rights_tag.allows(document.rights_tag):
            raise PermissionDenied("document rights exceed source rights")
        if document.security_id and document.security_id not in self.store.securities:
            raise NotFoundError(f"security {document.security_id} not found")
        if source.allowed_document_types and document.document_type not in source.allowed_document_types:
            raise ValidationError(f"document_type {document.document_type} is not allowed for source {source.source_id}")
        if document.document_id in self.store.documents:
            raise ConflictError(f"document {document.document_id} already exists")
        if document.body and not document.object_uri:
            suffix = ".html" if looks_like_html(document.body) else ".txt"
            stored = self.object_store.put_text(document.source_id, document.document_id, document.body, suffix=suffix)
            document = replace(document, object_uri=stored.uri, content_sha256=stored.sha256)
        self.store.documents[document.document_id] = document
        self._audit(
            actor,
            "ingest_document",
            "document",
            document.document_id,
            source=document.source_type or source.source_type,
            version=document.version,
        )
        return document

    def extract_evidence(
        self,
        document_id: str,
        *,
        actor: str = "system",
        parser_version: str = "rule-0",
        model_version: str = "rule-0",
    ) -> list[Evidence]:
        document = self.store.documents.get(document_id)
        if document is None:
            raise NotFoundError(f"document {document_id} not found")
        source_text = document.body or self._document_object_text(document)
        chunks = chunk_text_by_page(source_text)
        if not chunks:
            self._create_manual_review(
                document,
                issue_type="empty_or_scanned_document",
                severity="high",
                parser_version=parser_version,
                message="No extractable text was found. The file may be scanned, image-only, encrypted, or unsupported by the current parser.",
                suggested_action="Run OCR fallback or route the document to analyst review before using it as evidence.",
                actor=actor,
            )
            raise ValidationError("document body is empty")
        created: list[Evidence] = []
        for index, (page_no, chunk_index, chunk) in enumerate(chunks, start=1):
            evidence = Evidence(
                evidence_id=new_id("evi"),
                document_id=document_id,
                section=f"page_{page_no}_paragraph_{chunk_index}",
                page_no=page_no,
                bbox=f"page={page_no};chunk={chunk_index}",
                span_text=chunk,
                canonical_text=chunk.strip(),
                confidence=0.9 if index == 1 else 0.8,
            )
            self.store.evidence[evidence.evidence_id] = evidence
            created.append(evidence)
        self._audit(
            actor,
            "extract_evidence",
            "document",
            document_id,
            version=parser_version,
            model_version=model_version,
        )
        return created

    def manual_review_payload(self, filters: Mapping[str, Any] | None = None) -> dict[str, Any]:
        filters = filters or {}
        document_id = str(filters.get("document_id", "")).strip()
        status = str(filters.get("status", "")).strip()
        severity = str(filters.get("severity", "")).strip()
        limit = self._bounded_limit(filters.get("limit", 50))
        items = list(self.store.manual_reviews.values())
        if document_id:
            items = [item for item in items if item.document_id == document_id]
        if status:
            items = [item for item in items if item.status == status]
        if severity:
            items = [item for item in items if item.severity == severity]
        items.sort(key=lambda item: (item.status == "open", item.updated_at), reverse=True)
        return {"manual_reviews": [to_plain(item) for item in items[:limit]]}

    def evidence_quality_report(self, filters: Mapping[str, Any] | None = None) -> dict[str, Any]:
        filters = filters or {}
        issuer_id = str(filters.get("issuer_id", "")).strip()
        documents = list(self.store.documents.values())
        if issuer_id:
            documents = [document for document in documents if document.issuer_id == issuer_id]
        document_ids = {document.document_id for document in documents}
        evidence = [item for item in self.store.evidence.values() if item.document_id in document_ids]
        located = [item for item in evidence if item.page_no > 0 and bool(item.bbox)]
        manual_reviews = [item for item in self.store.manual_reviews.values() if item.document_id in document_ids]
        open_reviews = [item for item in manual_reviews if item.status == "open"]
        issue_counts: dict[str, int] = {}
        for item in manual_reviews:
            issue_counts[item.issue_type] = issue_counts.get(item.issue_type, 0) + 1
        documents_with_evidence = len({item.document_id for item in evidence})
        avg_confidence = sum(item.confidence for item in evidence) / len(evidence) if evidence else 0.0
        return {
            "issuer_id": issuer_id,
            "documents": len(documents),
            "documents_with_evidence": documents_with_evidence,
            "evidence": len(evidence),
            "locator_coverage": round(len(located) / max(1, len(evidence)), 4) if evidence else 0.0,
            "avg_confidence": round(avg_confidence, 4),
            "manual_reviews": len(manual_reviews),
            "open_manual_reviews": len(open_reviews),
            "parse_failure_rate": round(len({item.document_id for item in open_reviews}) / max(1, len(documents)), 4) if documents else 0.0,
            "issue_counts": issue_counts,
        }

    def _create_manual_review(
        self,
        document: Document,
        *,
        issue_type: str,
        severity: str,
        parser_version: str,
        message: str,
        suggested_action: str,
        actor: str,
    ) -> ManualReviewItem:
        review_id = self._manual_review_id(document.document_id, issue_type)
        existing = self.store.manual_reviews.get(review_id)
        if existing:
            existing.status = "open"
            existing.severity = severity
            existing.parser_version = parser_version
            existing.message = message
            existing.suggested_action = suggested_action
            existing.updated_at = utcnow()
            item = existing
            action = "update_manual_review"
        else:
            item = ManualReviewItem(
                review_id=review_id,
                document_id=document.document_id,
                issue_type=issue_type,
                severity=severity,
                parser_version=parser_version,
                message=message,
                suggested_action=suggested_action,
            )
            self.store.manual_reviews[item.review_id] = item
            action = "create_manual_review"
        self._audit(actor, action, "manual_review", item.review_id, version=parser_version, approval_state=item.status)
        return item

    def _document_object_text(self, document: Document) -> str:
        if not document.object_uri:
            return ""
        try:
            data = self.object_store.read_bytes(document.object_uri)
        except (FileNotFoundError, IsADirectoryError, OSError, ValueError):
            return ""
        suffix = Path(urlparse(document.object_uri).path).suffix.lower()
        if suffix == ".pdf" or data.startswith(b"%PDF"):
            return pdf_bytes_to_text(data)
        return data.decode("utf-8", errors="ignore")

    def create_thesis(
        self,
        payload: Mapping[str, Any],
        *,
        actor: str = "system",
    ) -> ThesisCard:
        evidence_ids = list(payload.get("evidence_ids", []))
        if not evidence_ids:
            raise ValidationError("thesis requires evidence")
        for evidence_id in evidence_ids:
            if evidence_id not in self.store.evidence:
                raise NotFoundError(f"evidence {evidence_id} not found")
        thesis_id = str(payload.get("thesis_id", new_id("thesis")))
        if thesis_id in self.store.theses:
            raise ConflictError(f"thesis {thesis_id} already exists")
        thesis = ThesisCard(
            thesis_id=thesis_id,
            issuer_id=str(payload["issuer_id"]),
            horizon=str(payload.get("horizon", "mid")),
            hypothesis=str(payload["hypothesis"]),
            catalyst=list(payload.get("catalyst", [])),
            evidence_ids=evidence_ids,
            falsifiers=list(payload.get("falsifiers", [])),
            risk_factors=list(payload.get("risk_factors", [])),
            confidence=float(payload.get("confidence", 0.0)),
            owner=str(payload.get("owner", actor)),
            status=str(payload.get("status", "draft")),
        )
        if thesis.issuer_id not in self.store.issuers:
            raise NotFoundError(f"issuer {thesis.issuer_id} not found")
        self.store.theses[thesis.thesis_id] = thesis
        self._audit(actor, "create_thesis", "thesis", thesis.thesis_id)
        return thesis

    def run_scoring(self, payload: Mapping[str, Any], *, actor: str = "system") -> ResearchSignal:
        thesis_id = str(payload["thesis_id"])
        strategy_type = str(payload.get("strategy_type", "long"))
        thesis = self.store.theses.get(thesis_id)
        if thesis is None:
            raise NotFoundError(f"thesis {thesis_id} not found")
        evidence_docs = [self.store.documents[self.store.evidence[eid].document_id] for eid in thesis.evidence_ids]
        factor_scores = dict(payload.get("factor_scores", {}))
        profile_id = str(payload.get("profile_id", ""))
        profile = self.store.scorecards.get(profile_id) if profile_id else None
        if profile and factor_scores:
            total_weight = sum(float(weight) for weight in profile.weights.values()) or 1.0
            raw_score = sum(float(profile.weights.get(name, 0.0)) * float(value) for name, value in factor_scores.items()) / total_weight
            score = max(0.0, min(1.0, raw_score))
            long_threshold = profile.threshold_long
            short_threshold = profile.threshold_short
        else:
            source_weights = {
                "regulatory": 0.18,
                "exchange": 0.16,
                "company_ir": 0.12,
                "vendor": 0.08,
            }
            base = 0.25 + min(0.4, 0.08 * len(thesis.evidence_ids))
            source_bonus = sum(source_weights.get(doc.source_type, 0.05) for doc in evidence_docs) / max(1, len(evidence_docs))
            falsifier_penalty = 0.1 * len(thesis.falsifiers)
            thesis_penalty = 0.05 if thesis.status not in {"review", "approved"} else 0.0
            score = max(0.0, min(1.0, base + source_bonus - falsifier_penalty - thesis_penalty))
            long_threshold = 0.55
            short_threshold = 0.55
        if strategy_type == "short":
            direction = "short" if score >= short_threshold else "neutral"
            signal_type = "event"
        elif strategy_type == "long":
            direction = "long" if score >= long_threshold else "neutral"
            signal_type = "value"
        else:
            direction = "neutral"
            signal_type = strategy_type
        signal = ResearchSignal(
            signal_id=str(payload.get("signal_id", new_id("sig"))),
            thesis_id=thesis_id,
            signal_type=signal_type,
            direction=direction,
            score=score,
            source_model=str(payload.get("source_model", "rules")),
            model_version=str(payload.get("model_version", "v1")),
            rationale=str(payload.get("rationale", "")),
            profile_id=profile.profile_id if profile else "",
            factor_scores=factor_scores,
        )
        self.store.signals[signal.signal_id] = signal
        thesis.confidence = score
        thesis.status = "review" if score >= 0.45 else thesis.status
        self._audit(actor, "run_scoring", "thesis", thesis_id, model_version=signal.model_version)
        return signal

    def build_decision_pack(self, payload: Mapping[str, Any], *, actor: str = "system") -> DecisionPack:
        signal_ids = list(payload.get("signal_ids", []))
        if not signal_ids:
            raise ValidationError("decision pack requires signal_ids")
        for signal_id in signal_ids:
            if signal_id not in self.store.signals:
                raise NotFoundError(f"signal {signal_id} not found")
        source_labels = {str(item).lower() for item in payload.get("source_labels", [])}
        if "private" in source_labels or "non_public" in source_labels:
            raise ComplianceGateError("Reg FD gate blocked non-public source")
        if payload.get("non_display_requested") and not payload.get("non_display_approved", False):
            raise ComplianceGateError("non-display gate blocked request")
        pack = DecisionPack(
            decision_id=str(payload.get("decision_id", new_id("dec"))),
            signal_ids=signal_ids,
            risk_checks=list(payload.get("risk_checks", [])),
            red_team_note=str(payload.get("red_team_note", "")),
        )
        self.store.decisions[pack.decision_id] = pack
        self._audit(actor, "build_decision_pack", "decision", pack.decision_id)
        return pack

    def sign_decision(self, decision_id: str, payload: Mapping[str, Any], *, actor: str = "system") -> DecisionPack:
        pack = self.store.decisions.get(decision_id)
        if pack is None:
            raise NotFoundError(f"decision {decision_id} not found")
        signature = DecisionSignature(
            role=str(payload["role"]),
            user=str(payload["user"]),
            comment=str(payload.get("comment", "")),
        )
        pack.signatures.append(signature)
        pack.approval_state = self._decision_state(pack)
        self._audit(actor, "sign_decision", "decision", decision_id, approval_state=pack.approval_state)
        return pack

    def create_exception(self, payload: Mapping[str, Any], *, actor: str = "system") -> dict[str, Any]:
        decision_id = str(payload["decision_id"])
        if decision_id not in self.store.decisions:
            raise NotFoundError(f"decision {decision_id} not found")
        exception = ExceptionItem(
            exception_id=str(payload.get("exception_id", new_id("exc"))),
            decision_id=decision_id,
            reason=str(payload.get("reason", "")),
            severity=str(payload.get("severity", "medium")),
        )
        self.store.exceptions[exception.exception_id] = exception
        self._audit(actor, "create_exception", "decision", decision_id, approval_state="exception")
        return to_plain(exception)

    def create_execution_intent(self, payload: Mapping[str, Any], *, actor: str = "system") -> ExecutionIntent:
        decision_id = str(payload["decision_id"])
        decision = self.store.decisions.get(decision_id)
        if decision is None:
            raise NotFoundError(f"decision {decision_id} not found")
        if decision.approval_state != "approved":
            raise ComplianceGateError("unsigned decision cannot enter execution intent")
        security_id = str(payload.get("security_id", ""))
        if security_id and security_id not in self.store.securities:
            raise NotFoundError(f"security {security_id} not found")
        intent = ExecutionIntent(
            intent_id=str(payload.get("intent_id", new_id("intent"))),
            decision_id=decision_id,
            action=str(payload["action"]),
            security_id=security_id,
            target_weight=float(payload.get("target_weight", 0.0)),
            rationale=str(payload.get("rationale", "")),
            status=str(payload.get("status", "draft")),
            created_by=str(payload.get("created_by", actor)),
        )
        if intent.intent_id in self.store.execution_intents:
            raise ConflictError(f"execution intent {intent.intent_id} already exists")
        self.store.execution_intents[intent.intent_id] = intent
        self._audit(actor, "create_execution_intent", "execution_intent", intent.intent_id, approval_state=decision.approval_state)
        return intent

    def create_review(self, payload: Mapping[str, Any], *, actor: str = "system") -> ReviewRecord:
        decision_id = str(payload["decision_id"])
        if decision_id not in self.store.decisions:
            raise NotFoundError(f"decision {decision_id} not found")
        review_id = str(payload.get("review_id", new_id("rev")))
        if review_id in self.store.reviews:
            raise ConflictError(f"review {review_id} already exists")
        review = ReviewRecord(
            review_id=review_id,
            decision_id=decision_id,
            realized_outcome=str(payload.get("realized_outcome", "")),
            attribution=str(payload.get("attribution", "")),
            lesson=str(payload.get("lesson", "")),
            next_action=str(payload.get("next_action", "")),
        )
        self.store.reviews[review.review_id] = review
        self._audit(actor, "create_review", "review", review.review_id)
        return review

    def generate_operating_report(self, payload: Mapping[str, Any], *, actor: str = "system") -> OperatingReport:
        period = str(payload["period"])
        report_id = str(payload.get("report_id", f"opr_{period.replace('-', '_')}"))
        if report_id in self.store.operating_reports:
            raise ConflictError(f"operating report {report_id} already exists")
        pending_decisions = sum(1 for decision in self.store.decisions.values() if decision.approval_state == "pending")
        approved_decisions = sum(1 for decision in self.store.decisions.values() if decision.approval_state == "approved")
        theses_with_evidence = sum(1 for thesis in self.store.theses.values() if thesis.evidence_ids)
        evidence_coverage = theses_with_evidence / max(1, len(self.store.theses))
        pending_prompts = sum(1 for request in self.store.prompt_changes.values() if request.status == "pending")
        open_exceptions = [item for item in self.store.exceptions.values() if item.status == "open"]
        challenger_coverage = len({item.thesis_id for item in self.store.challengers.values()}) / max(1, len(self.store.theses))
        metrics = {
            "sources": len(self.store.sources),
            "issuers": len(self.store.issuers),
            "documents": len(self.store.documents),
            "evidence": len(self.store.evidence),
            "theses": len(self.store.theses),
            "signals": len(self.store.signals),
            "pending_decisions": pending_decisions,
            "approved_decisions": approved_decisions,
            "execution_intents": len(self.store.execution_intents),
            "reviews": len(self.store.reviews),
            "audit_events": len(self.store.audit_log),
            "evidence_coverage": round(evidence_coverage, 4),
            "challenger_coverage": round(challenger_coverage, 4),
            "pending_prompt_changes": pending_prompts,
            "open_exceptions": len(open_exceptions),
        }
        red_flags: list[dict[str, Any]] = []
        if open_exceptions:
            red_flags.append({"type": "open_exceptions", "count": len(open_exceptions), "owner": "风险/合规", "due": "next_review"})
        if pending_decisions:
            red_flags.append({"type": "pending_decisions", "count": pending_decisions, "owner": "CIO", "due": "committee"})
        if pending_prompts:
            red_flags.append({"type": "pending_prompt_changes", "count": pending_prompts, "owner": "NLP/ML 负责人", "due": "before_release"})
        if evidence_coverage < 0.95 and self.store.theses:
            red_flags.append({"type": "low_evidence_coverage", "value": round(evidence_coverage, 4), "owner": "分析师", "due": "month_end"})
        if challenger_coverage < 1.0 and self.store.theses:
            red_flags.append({"type": "low_challenger_coverage", "value": round(challenger_coverage, 4), "owner": "风险/合规", "due": "month_end"})
        all_red_flags = list(payload.get("red_flags", [])) + red_flags
        for index, item in enumerate(all_red_flags, start=1):
            item.setdefault("red_flag_id", f"{report_id}_rf_{index}")
            item.setdefault("status", "open")
        report = OperatingReport(
            report_id=report_id,
            period=period,
            metrics=dict(payload.get("metrics", {})) | self._performance_metrics(payload) | metrics,
            red_flags=all_red_flags,
            owner=str(payload.get("owner", actor)),
            status=str(payload.get("status", "draft")),
        )
        self.store.operating_reports[report.report_id] = report
        self._audit(actor, "generate_operating_report", "operating_report", report.report_id)
        return report

    def publish_operating_report(self, report_id: str, payload: Mapping[str, Any], *, actor: str = "system") -> OperatingReport:
        report = self.store.operating_reports.get(report_id)
        if report is None:
            raise NotFoundError(f"operating report {report_id} not found")
        if report.status == "published":
            raise ConflictError(f"operating report {report_id} already published")
        approver_role = str(payload.get("approver_role", "CEO"))
        if approver_role not in {"CEO", "CIO", "风险/合规"}:
            raise PermissionDenied("operating report publish requires CEO, CIO, or risk approval")
        report.approvals.append(
            {
                "role": approver_role,
                "user": str(payload.get("user", actor)),
                "comment": str(payload.get("comment", "")),
                "signed_at": to_plain(utcnow()),
            }
        )
        report.status = "published"
        report.published_at = utcnow()
        self._audit(actor, "publish_operating_report", "operating_report", report.report_id, approval_state=report.status)
        return report

    def resolve_operating_report_red_flag(self, report_id: str, red_flag_id: str, payload: Mapping[str, Any], *, actor: str = "system") -> OperatingReport:
        report = self.store.operating_reports.get(report_id)
        if report is None:
            raise NotFoundError(f"operating report {report_id} not found")
        for item in report.red_flags:
            if str(item.get("red_flag_id", "")) == red_flag_id:
                item["status"] = str(payload.get("status", "resolved"))
                item["resolution"] = str(payload.get("resolution", ""))
                item["resolved_by"] = str(payload.get("resolved_by", actor))
                item["resolved_at"] = to_plain(utcnow())
                self._audit(actor, "resolve_operating_report_red_flag", "operating_report", report.report_id, approval_state=item["status"])
                return report
        raise NotFoundError(f"red flag {red_flag_id} not found")

    def _performance_metrics(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        metrics: dict[str, Any] = {}
        portfolio_returns = self._float_series(payload.get("portfolio_returns") or payload.get("returns"))
        if not portfolio_returns:
            portfolio_returns = self._returns_from_values(payload.get("portfolio_values") or payload.get("nav_series"))
        benchmark_returns = self._float_series(payload.get("benchmark_returns"))
        if not benchmark_returns:
            benchmark_returns = self._returns_from_values(payload.get("benchmark_values"))

        if portfolio_returns:
            total_return = self._compound_return(portfolio_returns)
            metrics.update(
                {
                    "period_count": len(portfolio_returns),
                    "total_return": round(total_return, 4),
                    "twr": round(total_return, 4),
                    "max_drawdown": round(self._max_drawdown(portfolio_returns), 4),
                }
            )
        if benchmark_returns:
            metrics["benchmark_return"] = round(self._compound_return(benchmark_returns), 4)
        if portfolio_returns and benchmark_returns:
            active_returns = [left - right for left, right in zip(portfolio_returns, benchmark_returns)]
            if active_returns:
                active_return = self._compound_return(portfolio_returns[: len(active_returns)]) - self._compound_return(benchmark_returns[: len(active_returns)])
                metrics["active_return"] = round(active_return, 4)
                active_mean = sum(active_returns) / len(active_returns)
                variance = sum((item - active_mean) ** 2 for item in active_returns) / len(active_returns)
                metrics["information_ratio"] = round(active_mean / (variance**0.5), 4) if variance > 0 else 0.0

        turnover = self._turnover_metric(payload)
        if turnover is not None:
            metrics["turnover"] = round(turnover, 4)
        attribution = payload.get("attribution")
        if isinstance(attribution, Mapping):
            metrics["attribution"] = dict(attribution)
        return metrics

    def _float_series(self, value: Any) -> list[float]:
        if not isinstance(value, list):
            return []
        values: list[float] = []
        for item in value:
            try:
                values.append(float(item))
            except (TypeError, ValueError):
                continue
        return values

    def _returns_from_values(self, value: Any) -> list[float]:
        values = self._float_series(value)
        returns: list[float] = []
        for previous, current in zip(values, values[1:]):
            if previous:
                returns.append((current / previous) - 1)
        return returns

    def _compound_return(self, returns: list[float]) -> float:
        compounded = 1.0
        for value in returns:
            compounded *= 1 + value
        return compounded - 1

    def _max_drawdown(self, returns: list[float]) -> float:
        peak = 1.0
        value = 1.0
        max_drawdown = 0.0
        for item in returns:
            value *= 1 + item
            peak = max(peak, value)
            if peak:
                max_drawdown = max(max_drawdown, (peak - value) / peak)
        return max_drawdown

    def _turnover_metric(self, payload: Mapping[str, Any]) -> float | None:
        if "turnover" in payload:
            try:
                return float(payload["turnover"])
            except (TypeError, ValueError):
                return None
        if "traded_value" in payload and ("average_nav" in payload or "average_gross_exposure" in payload):
            try:
                denominator = float(payload.get("average_nav") or payload.get("average_gross_exposure"))
                return float(payload["traded_value"]) / denominator if denominator else None
            except (TypeError, ValueError):
                return None
        positions = payload.get("positions") or payload.get("holdings")
        if isinstance(positions, list):
            total_change = 0.0
            seen = False
            for item in positions:
                if not isinstance(item, Mapping):
                    continue
                try:
                    current = float(item.get("weight", item.get("target_weight", 0.0)))
                    previous = float(item.get("previous_weight", 0.0))
                except (TypeError, ValueError):
                    continue
                total_change += abs(current - previous)
                seen = True
            if seen:
                return total_change / 2
        return None

    def _portfolio_universe(self, payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
        universe = payload.get("securities", [])
        if not isinstance(universe, list) or not universe:
            raise ValidationError("portfolio optimizer requires a non-empty securities list")
        securities: dict[str, dict[str, Any]] = {}
        for item in universe:
            if not isinstance(item, Mapping):
                continue
            security_id = str(item.get("security_id", ""))
            security = self.store.securities.get(security_id)
            if security is None:
                raise NotFoundError(f"security {security_id} not found")
            volatility = max(float(item.get("volatility", 0.2)), 0.0001)
            securities[security_id] = {
                "security_id": security_id,
                "market_weight": max(0.0, float(item.get("market_weight", 0.0))),
                "variance": volatility * volatility,
                "volatility": volatility,
                "market": str(item.get("market", security.market or "unknown")),
                "industry": str(item.get("industry", "unclassified")),
                "theme": str(item.get("theme", "")),
                "currency": str(item.get("currency", security.currency or "")),
            }
        if not securities:
            raise ValidationError("portfolio optimizer requires at least one valid security")
        return securities

    def _apply_portfolio_constraints(
        self,
        scores: Mapping[str, float],
        securities: Mapping[str, dict[str, Any]],
        constraints: Mapping[str, Any],
        risk_budget: Mapping[str, Any],
    ) -> dict[str, float]:
        restricted = {str(item) for item in constraints.get("restricted_securities", [])}
        max_weight = float(constraints.get("max_weight", 1.0))
        caps = {security_id: (0.0 if security_id in restricted else max_weight) for security_id in securities}
        weights = self._normalize_scores_with_caps(scores, caps)
        market_budget = self._budget_map(constraints.get("market_budget") or risk_budget.get("market") or risk_budget.get("markets"))
        industry_budget = self._budget_map(constraints.get("industry_budget") or risk_budget.get("industry") or risk_budget.get("industries"))
        theme_budget = self._budget_map(constraints.get("theme_budget") or risk_budget.get("theme") or risk_budget.get("themes"))
        currency_budget = self._budget_map(constraints.get("currency_budget") or risk_budget.get("currency") or risk_budget.get("currencies"))
        weights = self._apply_group_budget(weights, securities, caps, "market", market_budget)
        weights = self._apply_group_budget(weights, securities, caps, "industry", industry_budget)
        weights = self._apply_group_budget(weights, securities, caps, "theme", theme_budget)
        weights = self._apply_group_budget(weights, securities, caps, "currency", currency_budget)
        return weights

    def _normalize_scores_with_caps(self, scores: Mapping[str, float], caps: Mapping[str, float]) -> dict[str, float]:
        result = {security_id: 0.0 for security_id in scores}
        active = {security_id for security_id, cap in caps.items() if cap > 0}
        remaining = min(1.0, sum(caps[security_id] for security_id in active))
        base = {security_id: max(0.0, float(scores.get(security_id, 0.0))) for security_id in scores}
        if sum(base[security_id] for security_id in active) <= 0:
            base = {security_id: 1.0 for security_id in active}
        while active and remaining > 0:
            total = sum(base.get(security_id, 0.0) for security_id in active)
            if total <= 0:
                break
            capped = False
            for security_id in list(active):
                proposed = remaining * base.get(security_id, 0.0) / total
                if proposed > caps[security_id]:
                    result[security_id] = caps[security_id]
                    remaining -= caps[security_id]
                    active.remove(security_id)
                    capped = True
            if not capped:
                for security_id in active:
                    result[security_id] = remaining * base.get(security_id, 0.0) / total
                break
        return result

    def _budget_map(self, value: Any) -> dict[str, float]:
        if not isinstance(value, Mapping):
            return {}
        budget: dict[str, float] = {}
        for key, raw in value.items():
            try:
                budget[str(key)] = max(0.0, float(raw))
            except (TypeError, ValueError):
                continue
        return budget

    def _apply_group_budget(
        self,
        weights: dict[str, float],
        securities: Mapping[str, dict[str, Any]],
        caps: Mapping[str, float],
        group_key: str,
        budgets: Mapping[str, float],
    ) -> dict[str, float]:
        if not budgets:
            return weights
        adjusted = dict(weights)
        for _ in range(4):
            changed = False
            for group, budget in budgets.items():
                group_ids = [security_id for security_id, item in securities.items() if item.get(group_key) == group]
                total = sum(adjusted.get(security_id, 0.0) for security_id in group_ids)
                if total <= budget or total <= 0:
                    continue
                scale = budget / total
                freed = 0.0
                for security_id in group_ids:
                    old_weight = adjusted.get(security_id, 0.0)
                    adjusted[security_id] = old_weight * scale
                    freed += old_weight - adjusted[security_id]
                recipients = [security_id for security_id in adjusted if security_id not in group_ids and adjusted[security_id] < caps.get(security_id, 0.0)]
                self._redistribute_weight(adjusted, recipients, freed, caps)
                changed = True
            if not changed:
                break
        return adjusted

    def _redistribute_weight(self, weights: dict[str, float], recipients: list[str], amount: float, caps: Mapping[str, float]) -> None:
        remaining = amount
        while recipients and remaining > 1e-12:
            slack = {security_id: max(0.0, caps.get(security_id, 0.0) - weights.get(security_id, 0.0)) for security_id in recipients}
            total_slack = sum(slack.values())
            if total_slack <= 0:
                return
            moved = 0.0
            for security_id in list(recipients):
                add = min(slack[security_id], remaining * slack[security_id] / total_slack)
                weights[security_id] += add
                moved += add
                if weights[security_id] >= caps.get(security_id, 0.0) - 1e-12:
                    recipients.remove(security_id)
            remaining -= moved

    def _portfolio_group_exposure(self, weights: Mapping[str, float], securities: Mapping[str, dict[str, Any]], group_key: str) -> dict[str, float]:
        exposure: dict[str, float] = {}
        for security_id, weight in weights.items():
            group = str(securities[security_id].get(group_key, "unknown"))
            exposure[group] = exposure.get(group, 0.0) + float(weight)
        return {key: round(value, 6) for key, value in sorted(exposure.items())}

    def _portfolio_risk_contribution(self, weights: Mapping[str, float], securities: Mapping[str, dict[str, Any]]) -> dict[str, float]:
        raw = {
            security_id: max(0.0, float(weight)) * securities[security_id]["volatility"]
            for security_id, weight in weights.items()
        }
        total = sum(raw.values())
        if total <= 0:
            return {security_id: 0.0 for security_id in weights}
        return {security_id: round(value / total, 6) for security_id, value in raw.items()}

    def _portfolio_turnover(self, weights: Mapping[str, float], current_weights: Any) -> float:
        if not isinstance(current_weights, Mapping):
            return 0.0
        all_ids = set(weights) | {str(key) for key in current_weights}
        total = 0.0
        for security_id in all_ids:
            try:
                current = float(current_weights.get(security_id, 0.0))
            except (TypeError, ValueError):
                current = 0.0
            total += abs(float(weights.get(security_id, 0.0)) - current)
        return total / 2

    def _portfolio_stress_report(self, weights: Mapping[str, float], scenarios: Any) -> list[dict[str, Any]]:
        if not isinstance(scenarios, list):
            return []
        report: list[dict[str, Any]] = []
        for scenario in scenarios:
            if not isinstance(scenario, Mapping):
                continue
            shocks = scenario.get("shocks", {})
            if not isinstance(shocks, Mapping):
                continue
            portfolio_return = 0.0
            for security_id, weight in weights.items():
                try:
                    portfolio_return += float(weight) * float(shocks.get(security_id, 0.0))
                except (TypeError, ValueError):
                    continue
            report.append({"name": str(scenario.get("name", "stress")), "portfolio_return": round(portfolio_return, 6)})
        return report

    def _portfolio_walk_forward(self, weights: Mapping[str, float], history: Any) -> dict[str, Any]:
        if not isinstance(history, Mapping):
            return {}
        series = {str(security_id): self._float_series(values) for security_id, values in history.items()}
        lengths = [len(values) for values in series.values() if values]
        if not lengths:
            return {}
        periods = min(lengths)
        portfolio_returns = [
            sum(float(weights.get(security_id, 0.0)) * returns[index] for security_id, returns in series.items() if len(returns) > index)
            for index in range(periods)
        ]
        total_return = self._compound_return(portfolio_returns)
        return {
            "period_count": periods,
            "total_return": round(total_return, 6),
            "max_drawdown": round(self._max_drawdown(portfolio_returns), 6),
        }

    def create_strategy_replay(self, payload: Mapping[str, Any], *, actor: str = "system") -> StrategyReplay:
        decision_id = str(payload["decision_id"])
        if decision_id not in self.store.decisions:
            raise NotFoundError(f"decision {decision_id} not found")
        replay = StrategyReplay(
            replay_id=str(payload.get("replay_id", new_id("replay"))),
            decision_id=decision_id,
            expected_outcome=str(payload.get("expected_outcome", "")),
            actual_outcome=str(payload.get("actual_outcome", "")),
            variance_reason=str(payload.get("variance_reason", "")),
            next_action=str(payload.get("next_action", "")),
            version=str(payload.get("version", "v1")),
        )
        if replay.replay_id in self.store.strategy_replays:
            raise ConflictError(f"strategy replay {replay.replay_id} already exists")
        self.store.strategy_replays[replay.replay_id] = replay
        self._audit(actor, "create_strategy_replay", "strategy_replay", replay.replay_id)
        return replay

    def list_strategy_replays(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        decision_id = str(payload.get("decision_id", ""))
        version = str(payload.get("version", ""))
        actual_outcome = str(payload.get("actual_outcome", ""))
        created_from = parse_datetime(payload["created_from"]) if payload.get("created_from") else None
        created_to = parse_datetime(payload["created_to"]) if payload.get("created_to") else None
        replays: list[StrategyReplay] = []
        for replay in self.store.strategy_replays.values():
            if decision_id and replay.decision_id != decision_id:
                continue
            if version and replay.version != version:
                continue
            if actual_outcome and replay.actual_outcome != actual_outcome:
                continue
            if created_from and replay.created_at < created_from:
                continue
            if created_to and replay.created_at > created_to:
                continue
            replays.append(replay)
        replays.sort(key=lambda item: item.created_at, reverse=True)
        return {"count": len(replays), "replays": [to_plain(item) for item in replays]}

    def run_portfolio_optimizer(self, payload: Mapping[str, Any], *, actor: str = "system") -> PortfolioProposal:
        proposal_id = str(payload.get("proposal_id", new_id("pfp")))
        if proposal_id in self.store.portfolio_proposals:
            raise ConflictError(f"portfolio proposal {proposal_id} already exists")
        securities = self._portfolio_universe(payload)
        risk_aversion = float(payload.get("risk_aversion", 2.5))
        tau = float(payload.get("tau", 0.05))
        constraints = dict(payload.get("constraints", {}))
        risk_budget = dict(payload.get("risk_budget", {}))
        constraints["paper_only"] = True

        total_market_weight = sum(item["market_weight"] for item in securities.values())
        if total_market_weight <= 0:
            total_market_weight = float(len(securities))
            for item in securities.values():
                item["market_weight"] = 1.0
        for item in securities.values():
            item["market_weight"] = item["market_weight"] / total_market_weight

        prior_returns = {
            security_id: risk_aversion * item["variance"] * item["market_weight"]
            for security_id, item in securities.items()
        }
        posterior_returns = dict(prior_returns)
        view_diagnostics: list[dict[str, Any]] = []
        for view in payload.get("views", []):
            if not isinstance(view, Mapping):
                continue
            security_id = str(view.get("security_id", ""))
            if security_id not in securities:
                raise NotFoundError(f"portfolio view security {security_id} not found in universe")
            evidence_ids = [str(item) for item in view.get("evidence_ids", [])]
            for evidence_id in evidence_ids:
                if evidence_id not in self.store.evidence:
                    raise NotFoundError(f"portfolio view evidence {evidence_id} not found")
            confidence = min(1.0, max(0.01, float(view.get("confidence", 0.5))))
            view_return = float(view.get("expected_return", 0.0))
            variance = securities[security_id]["variance"]
            prior_variance = max(tau * variance, 1e-6)
            omega = max(prior_variance * (1.0 - confidence) / confidence, 1e-6)
            posterior = ((prior_returns[security_id] / prior_variance) + (view_return / omega)) / ((1.0 / prior_variance) + (1.0 / omega))
            posterior_returns[security_id] = posterior
            view_diagnostics.append(
                {
                    "security_id": security_id,
                    "confidence": round(confidence, 4),
                    "omega": round(omega, 8),
                    "prior_return": round(prior_returns[security_id], 6),
                    "view_return": round(view_return, 6),
                    "posterior_return": round(posterior, 6),
                    "evidence_ids": evidence_ids,
                }
            )

        scores = {
            security_id: max(0.0, posterior_returns[security_id]) / securities[security_id]["variance"]
            for security_id in securities
        }
        if sum(scores.values()) <= 0:
            scores = {security_id: item["market_weight"] for security_id, item in securities.items()}
        weights = self._apply_portfolio_constraints(scores, securities, constraints, risk_budget)
        rounded_weights = {security_id: round(weight, 6) for security_id, weight in weights.items()}
        diagnostics = {
            "method": "diagonal_black_litterman",
            "risk_aversion": risk_aversion,
            "tau": tau,
            "paper_only": True,
            "view_diagnostics": view_diagnostics,
            "market_exposure": self._portfolio_group_exposure(rounded_weights, securities, "market"),
            "industry_exposure": self._portfolio_group_exposure(rounded_weights, securities, "industry"),
            "theme_exposure": self._portfolio_group_exposure(rounded_weights, securities, "theme"),
            "currency_exposure": self._portfolio_group_exposure(rounded_weights, securities, "currency"),
            "risk_contribution": self._portfolio_risk_contribution(rounded_weights, securities),
            "turnover": round(self._portfolio_turnover(rounded_weights, constraints.get("current_weights", payload.get("current_weights", {}))), 6),
            "stress_report": self._portfolio_stress_report(rounded_weights, payload.get("stress_scenarios", [])),
            "walk_forward": self._portfolio_walk_forward(rounded_weights, payload.get("return_history", {})),
            "cash_weight": round(max(0.0, 1.0 - sum(rounded_weights.values())), 6),
        }
        proposal = PortfolioProposal(
            proposal_id=proposal_id,
            universe=list(securities.keys()),
            prior_returns={security_id: round(value, 6) for security_id, value in prior_returns.items()},
            posterior_returns={security_id: round(value, 6) for security_id, value in posterior_returns.items()},
            candidate_weights=rounded_weights,
            constraints=constraints,
            risk_budget=risk_budget,
            diagnostics=diagnostics,
            status=str(payload.get("status", "candidate")),
            created_by=str(payload.get("created_by", actor)),
        )
        self.store.portfolio_proposals[proposal.proposal_id] = proposal
        self._audit(actor, "run_portfolio_optimizer", "portfolio_proposal", proposal.proposal_id, approval_state=proposal.status)
        return proposal

    def portfolio_proposal_payload(self, proposal_id: str) -> dict[str, Any]:
        proposal = self.store.portfolio_proposals.get(proposal_id)
        if proposal is None:
            raise NotFoundError(f"portfolio proposal {proposal_id} not found")
        return to_plain(proposal)

    def list_portfolio_proposals(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        status = str(payload.get("status", ""))
        created_by = str(payload.get("created_by", ""))
        proposals = [
            proposal
            for proposal in self.store.portfolio_proposals.values()
            if (not status or proposal.status == status) and (not created_by or proposal.created_by == created_by)
        ]
        proposals.sort(key=lambda item: item.created_at, reverse=True)
        return {"count": len(proposals), "proposals": [to_plain(item) for item in proposals]}

    def register_benchmark(self, payload: Mapping[str, Any], *, actor: str = "system") -> BenchmarkConfig:
        benchmark = BenchmarkConfig(
            benchmark_id=str(payload.get("benchmark_id", new_id("bm"))),
            language=str(payload["language"]),
            task_type=str(payload["task_type"]),
            sample_size=int(payload.get("sample_size", 0)),
            metrics=dict(payload.get("metrics", {})),
            threshold=dict(payload.get("threshold", {})),
            status=str(payload.get("status", "draft")),
        )
        self.store.benchmarks[benchmark.benchmark_id] = benchmark
        self._audit(actor, "register_benchmark", "benchmark", benchmark.benchmark_id)
        return benchmark

    def evaluate_benchmark(self, benchmark_id: str, payload: Mapping[str, Any], *, actor: str = "system") -> BenchmarkResult:
        benchmark = self.store.benchmarks.get(benchmark_id)
        if benchmark is None:
            raise NotFoundError(f"benchmark {benchmark_id} not found")
        metrics = dict(payload.get("metrics", {}))
        passed = True
        for key, threshold_value in benchmark.threshold.items():
            value = float(metrics.get(key, 0.0))
            if value < float(threshold_value):
                passed = False
        result = BenchmarkResult(
            result_id=str(payload.get("result_id", new_id("bmr"))),
            benchmark_id=benchmark_id,
            passed=passed,
            metrics=metrics,
            threshold=dict(benchmark.threshold),
        )
        benchmark.status = "passed" if passed else "failed"
        self.store.benchmark_results[result.result_id] = result
        self._audit(actor, "evaluate_benchmark", "benchmark", benchmark_id, approval_state=benchmark.status)
        return result

    def register_benchmark_sample(self, benchmark_id: str, payload: Mapping[str, Any], *, actor: str = "system") -> BenchmarkSample:
        benchmark = self.store.benchmarks.get(benchmark_id)
        if benchmark is None:
            raise NotFoundError(f"benchmark {benchmark_id} not found")
        document_id = str(payload["document_id"])
        document = self.store.documents.get(document_id)
        if document is None:
            raise NotFoundError(f"document {document_id} not found")
        sample = BenchmarkSample(
            sample_id=str(payload.get("sample_id", self._benchmark_sample_id(benchmark_id, document_id))),
            benchmark_id=benchmark_id,
            document_id=document_id,
            language=str(payload.get("language", document.language)),
            expected_terms=[str(item) for item in payload.get("expected_terms", [])],
            expected_numbers=int(payload.get("expected_numbers", 0)),
            expected_periods=int(payload.get("expected_periods", 0)),
            expected_tables=int(payload.get("expected_tables", 0)),
            expected_pages=[int(item) for item in payload.get("expected_pages", [])],
            notes=str(payload.get("notes", "")),
            status=str(payload.get("status", "active")),
        )
        if sample.sample_id in self.store.benchmark_samples:
            raise ConflictError(f"benchmark sample {sample.sample_id} already exists")
        self.store.benchmark_samples[sample.sample_id] = sample
        benchmark.sample_size = len([item for item in self.store.benchmark_samples.values() if item.benchmark_id == benchmark_id and item.status == "active"])
        self._audit(actor, "register_benchmark_sample", "benchmark_sample", sample.sample_id, approval_state=sample.status)
        return sample

    def benchmark_samples_payload(self, benchmark_id: str, filters: Mapping[str, Any] | None = None) -> dict[str, Any]:
        if benchmark_id not in self.store.benchmarks:
            raise NotFoundError(f"benchmark {benchmark_id} not found")
        filters = filters or {}
        language = str(filters.get("language", "")).strip()
        status = str(filters.get("status", "")).strip()
        samples = [item for item in self.store.benchmark_samples.values() if item.benchmark_id == benchmark_id]
        if language:
            samples = [item for item in samples if item.language == language]
        if status:
            samples = [item for item in samples if item.status == status]
        samples.sort(key=lambda item: item.sample_id)
        return {"count": len(samples), "samples": [to_plain(item) for item in samples]}

    def run_benchmark_suite(self, benchmark_id: str, payload: Mapping[str, Any], *, actor: str = "system") -> BenchmarkRun:
        benchmark = self.store.benchmarks.get(benchmark_id)
        if benchmark is None:
            raise NotFoundError(f"benchmark {benchmark_id} not found")
        requested_ids = [str(item) for item in payload.get("sample_ids", [])]
        samples = [
            sample
            for sample in self.store.benchmark_samples.values()
            if sample.benchmark_id == benchmark_id and sample.status == "active" and (not requested_ids or sample.sample_id in requested_ids)
        ]
        if not samples:
            raise ValidationError("benchmark run requires at least one active sample")
        threshold = dict(benchmark.threshold)
        min_confidence = float(payload.get("min_confidence", threshold.get("avg_confidence", 0.75)))
        sample_reports = [self._benchmark_sample_report(sample, threshold=threshold, min_confidence=min_confidence, actor=actor) for sample in samples]
        aggregate = self._benchmark_aggregate_metrics(sample_reports)
        failed_samples = [report for report in sample_reports if not report["passed"]]
        aggregate_passed = all(float(aggregate.get(key, 0.0)) >= float(value) for key, value in threshold.items() if isinstance(aggregate.get(key), (int, float)))
        passed = aggregate_passed and not failed_samples
        run = BenchmarkRun(
            run_id=str(payload.get("run_id", new_id("bmrn"))),
            benchmark_id=benchmark_id,
            sample_ids=[sample.sample_id for sample in samples],
            passed=passed,
            metrics=aggregate,
            threshold=threshold,
            failed_samples=failed_samples,
            regression_examples=[report["sample_id"] for report in failed_samples],
        )
        if run.run_id in self.store.benchmark_runs:
            raise ConflictError(f"benchmark run {run.run_id} already exists")
        benchmark.status = "passed" if passed else "failed"
        self.store.benchmark_runs[run.run_id] = run
        self._audit(actor, "run_benchmark_suite", "benchmark", benchmark_id, approval_state=benchmark.status)
        return run

    def extract_structured_facts(self, payload: Mapping[str, Any], *, actor: str = "system") -> ExtractionResult:
        evidence_id = str(payload["evidence_id"])
        evidence = self.store.evidence.get(evidence_id)
        if evidence is None:
            raise NotFoundError(f"evidence {evidence_id} not found")
        document = self.store.documents.get(evidence.document_id)
        if document is None:
            raise NotFoundError(f"document {evidence.document_id} not found")
        benchmark_id = str(payload.get("benchmark_id", ""))
        benchmark = self.store.benchmarks.get(benchmark_id) if benchmark_id else None
        if benchmark_id and benchmark is None:
            raise NotFoundError(f"benchmark {benchmark_id} not found")
        expected_terms = {str(item) for item in payload.get("expected_terms", [])}
        expected_numbers = int(payload.get("expected_numbers", 0))
        expected_periods = int(payload.get("expected_periods", 0))
        expected_tables = int(payload.get("expected_tables", 0))
        text = evidence.canonical_text or evidence.span_text
        terms = self._extract_terms(text, evidence=evidence)
        numbers = self._extract_numbers(text, evidence=evidence)
        periods = self._extract_periods(text, evidence=evidence)
        tables = self._extract_tables(text, evidence=evidence)
        metrics = self._extraction_metrics(
            terms=terms,
            numbers=numbers,
            periods=periods,
            tables=tables,
            expected_terms=expected_terms,
            expected_numbers=expected_numbers,
            expected_periods=expected_periods,
            expected_tables=expected_tables,
        )
        threshold = benchmark.threshold if benchmark else {}
        passed = all(float(metrics.get(key, 0.0)) >= float(value) for key, value in threshold.items())
        result = ExtractionResult(
            extraction_id=str(payload.get("extraction_id", new_id("ext"))),
            evidence_id=evidence_id,
            document_id=evidence.document_id,
            language=document.language,
            task_type=str(payload.get("task_type", benchmark.task_type if benchmark else "term_extraction")),
            terms=terms,
            numbers=numbers,
            periods=periods,
            tables=tables,
            metrics=metrics,
            benchmark_id=benchmark_id,
            passed=passed if threshold else bool(terms or numbers or periods or tables),
            parser_version=str(payload.get("parser_version", "rule-0")),
        )
        if result.extraction_id in self.store.extraction_results:
            raise ConflictError(f"extraction {result.extraction_id} already exists")
        self.store.extraction_results[result.extraction_id] = result
        if benchmark:
            benchmark.status = "passed" if result.passed else "failed"
        self._audit(actor, "extract_structured_facts", "evidence", evidence_id, model_version=result.parser_version, approval_state="passed" if result.passed else "failed")
        return result

    def create_prompt_change(self, payload: Mapping[str, Any], *, actor: str = "system") -> PromptChangeRequest:
        request = PromptChangeRequest(
            request_id=str(payload.get("request_id", new_id("pr"))),
            prompt_name=str(payload["prompt_name"]),
            change_level=str(payload.get("change_level", "low")),
            requested_by=str(payload.get("requested_by", actor)),
            content=str(payload.get("content", "")),
        )
        self.store.prompt_changes[request.request_id] = request
        self._audit(actor, "create_prompt_change", "prompt", request.request_id, prompt_version=request.request_id)
        return request

    def approve_prompt_change(self, request_id: str, *, actor: str = "system", approved: bool = True) -> PromptChangeRequest:
        request = self.store.prompt_changes.get(request_id)
        if request is None:
            raise NotFoundError(f"prompt change {request_id} not found")
        request.status = "approved" if approved else "rejected"
        request.approvers.append(actor)
        self._audit(actor, "approve_prompt_change", "prompt", request_id, prompt_version=request_id, approval_state=request.status)
        return request

    def register_template(self, payload: Mapping[str, Any], *, actor: str = "system") -> ResearchTemplate:
        template = ResearchTemplate(
            template_id=str(payload.get("template_id", new_id("tpl"))),
            template_type=str(payload["template_type"]),
            name=str(payload["name"]),
            fields=list(payload.get("fields", [])),
            description=str(payload.get("description", "")),
        )
        self.store.templates[template.template_id] = template
        self._audit(actor, "register_template", "template", template.template_id)
        return template

    def seed_default_templates(self, *, actor: str = "system") -> list[ResearchTemplate]:
        defaults = [
            {
                "template_id": "tpl_company_default",
                "template_type": "company",
                "name": "Company Research Card",
                "fields": ["summary", "valuation", "risk", "evidence"],
                "description": "Default company research card template",
            },
            {
                "template_id": "tpl_industry_default",
                "template_type": "industry",
                "name": "Industry Research Card",
                "fields": ["summary", "industry_view", "catalyst", "evidence"],
                "description": "Default industry research card template",
            },
        ]
        created: list[ResearchTemplate] = []
        for item in defaults:
            if item["template_id"] in self.store.templates:
                created.append(self.store.templates[item["template_id"]])
                continue
            created.append(self.register_template(item, actor=actor))
        return created

    def seed_demo_full_flow(self, *, actor: str = "system") -> dict[str, Any]:
        self.seed_default_sources(actor=actor)
        self.seed_default_templates(actor=actor)
        if "issuer_demo" not in self.store.issuers:
            self.register_issuer(
                {
                    "issuer_id": "issuer_demo",
                    "legal_name": "Demo Holdings",
                    "aliases": ["Demo Corp"],
                    "market": ["A", "H", "U"],
                    "lei": "LEI-DEMO-HOLDINGS",
                    "cik": "0000320193",
                    "country": "US",
                },
                actor=actor,
            )
        if "security_demo_us" not in self.store.securities:
            self.register_security(
                {
                    "security_id": "security_demo_us",
                    "issuer_id": "issuer_demo",
                    "ticker": "DEMO",
                    "figi": "FIGI-DEMO-US",
                    "isin": "US000000DEMO",
                    "exchange": "NASDAQ",
                    "currency": "USD",
                    "market": "U",
                },
                actor=actor,
            )
        if "md_demo_us_2026_05_14_eod" not in self.store.market_data:
            self.register_market_data_point(
                {
                    "data_id": "md_demo_us_2026_05_14_eod",
                    "security_id": "security_demo_us",
                    "source_id": "authorized_eod_market_data",
                    "as_of_date": "2026-05-14",
                    "data_type": "eod",
                    "close": 187.42,
                    "adjusted_close": 187.42,
                    "volume": 52130000,
                },
                actor=actor,
            )
        if "doc_demo_10k" not in self.store.documents:
            source = self.store.sources["sec_edgar"]
            self.ingest_document(
                {
                    "document_id": "doc_demo_10k",
                    "issuer_id": "issuer_demo",
                    "security_id": "security_demo_us",
                    "source_id": "sec_edgar",
                    "source_type": "regulatory",
                    "document_type": "10-K",
                    "source_uri": "https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm",
                    "title": "Demo 10-K filing",
                    "body": "<html><body><p>Revenue grew with resilient services demand.</p><p>Risk factors include supply concentration and macro volatility.</p></body></html>",
                    "rights_tag": to_plain(source.rights_tag),
                    "language": "en",
                    "version": "demo",
                },
                actor=actor,
            )
        evidence = [item for item in self.store.evidence.values() if item.document_id == "doc_demo_10k"]
        if not evidence:
            evidence = self.extract_evidence("doc_demo_10k", actor=actor, parser_version="html-rule-1", model_version="html-rule-1")
        evidence_ids = [item.evidence_id for item in evidence]
        if "thesis_demo" not in self.store.theses:
            self.create_thesis(
                {
                    "thesis_id": "thesis_demo",
                    "issuer_id": "issuer_demo",
                    "horizon": "long",
                    "hypothesis": "Services resilience can support medium-term earnings quality",
                    "evidence_ids": evidence_ids,
                    "falsifiers": ["macro demand shock", "supply disruption"],
                    "risk_factors": ["valuation", "supply chain"],
                    "owner": "analyst_demo",
                    "status": "review",
                },
                actor=actor,
            )
        if "score_demo_long" not in self.store.scorecards:
            self.register_scorecard(
                {
                    "profile_id": "score_demo_long",
                    "strategy_type": "long",
                    "name": "Demo Long Scorecard",
                    "weights": {"quality": 0.4, "valuation": 0.25, "catalyst": 0.2, "risk": 0.15},
                    "threshold_long": 0.6,
                },
                actor=actor,
            )
        if "sig_demo" not in self.store.signals:
            self.run_scoring(
                {
                    "signal_id": "sig_demo",
                    "thesis_id": "thesis_demo",
                    "strategy_type": "long",
                    "profile_id": "score_demo_long",
                    "factor_scores": {"quality": 0.82, "valuation": 0.62, "catalyst": 0.74, "risk": 0.55},
                    "source_model": "scorecard",
                    "model_version": "demo-v1",
                    "rationale": "Evidence-backed quality and catalyst score exceed approval threshold.",
                },
                actor=actor,
            )
        if "hold_demo_a" not in self.store.institutional_holdings:
            self.register_13f_holding(
                {
                    "holding_id": "hold_demo_a",
                    "issuer_id": "issuer_demo",
                    "security_id": "security_demo_us",
                    "source_id": "sec_edgar",
                    "filer_cik": "0001067983",
                    "filer_name": "Demo Capital Partners",
                    "report_period": "2026-03-31",
                    "shares": 1250000,
                    "value_usd": 234000000,
                },
                actor=actor,
            )
        if "hold_demo_b" not in self.store.institutional_holdings:
            self.register_13f_holding(
                {
                    "holding_id": "hold_demo_b",
                    "issuer_id": "issuer_demo",
                    "security_id": "security_demo_us",
                    "source_id": "sec_edgar",
                    "filer_cik": "0001364742",
                    "filer_name": "Demo Long Term Fund",
                    "report_period": "2026-03-31",
                    "shares": 870000,
                    "value_usd": 163000000,
                },
                actor=actor,
            )
        if "crd_demo" not in self.store.crowding:
            self.update_crowding_from_13f(
                {
                    "snapshot_id": "crd_demo",
                    "issuer_id": "issuer_demo",
                    "report_period": "2026-03-31",
                },
                actor=actor,
            )
        if "chg_demo" not in self.store.challengers:
            self.run_challenger(
                {
                    "challenger_id": "chg_demo",
                    "thesis_id": "thesis_demo",
                    "source_conflict": 0.25,
                    "valuation_gap": 0.45,
                    "narrative_divergence": 0.35,
                    "policy_risk": 0.2,
                    "note": "Challenger asks for valuation discipline but does not block.",
                },
                actor=actor,
            )
        if "card_demo" not in self.store.research_cards:
            self.create_research_card(
                {
                    "card_id": "card_demo",
                    "template_id": "tpl_company_default",
                    "thesis_id": "thesis_demo",
                    "title": "Demo Holdings research card",
                    "fields": {
                        "summary": "Services resilience supports earnings quality.",
                        "valuation": "Requires discipline after multiple expansion.",
                        "risk": "Macro and supply concentration.",
                        "evidence": "doc_demo_10k",
                    },
                },
                actor=actor,
            )
        if "dec_demo" not in self.store.decisions:
            self.build_decision_pack(
                {
                    "decision_id": "dec_demo",
                    "signal_ids": ["sig_demo"],
                    "risk_checks": ["reg_fd", "non_display"],
                    "red_team_note": "Approved only after valuation and non-display checks.",
                    "non_display_requested": False,
                },
                actor=actor,
            )
        decision = self.store.decisions["dec_demo"]
        signed_roles = {signature.role for signature in decision.signatures}
        if "风险/合规" not in signed_roles:
            self.sign_decision("dec_demo", {"role": "风险/合规", "user": "risk_demo", "comment": "rights and Reg FD checks passed"}, actor=actor)
        if "CEO" not in signed_roles:
            self.sign_decision("dec_demo", {"role": "CEO", "user": "ceo_demo", "comment": "approved for execution intent"}, actor=actor)
        if "intent_demo" not in self.store.execution_intents:
            self.create_execution_intent(
                {
                    "intent_id": "intent_demo",
                    "decision_id": "dec_demo",
                    "security_id": "security_demo_us",
                    "action": "buy",
                    "target_weight": 0.05,
                    "rationale": "Approved research-backed long intent.",
                },
                actor=actor,
            )
        if "exc_demo" not in self.store.exceptions:
            self.create_exception(
                {
                    "exception_id": "exc_demo",
                    "decision_id": "dec_demo",
                    "reason": "Monitor crowding above watch threshold",
                    "severity": "medium",
                },
                actor=actor,
            )
        if "rev_demo" not in self.store.reviews:
            self.create_review(
                {
                    "review_id": "rev_demo",
                    "decision_id": "dec_demo",
                    "realized_outcome": "pending",
                    "attribution": "not yet realized",
                    "lesson": "track evidence freshness and valuation sensitivity",
                    "next_action": "review after next filing",
                },
                actor=actor,
            )
        if "replay_demo" not in self.store.strategy_replays:
            self.create_strategy_replay(
                {
                    "replay_id": "replay_demo",
                    "decision_id": "dec_demo",
                    "expected_outcome": "earnings quality improves with services resilience",
                    "actual_outcome": "pending",
                    "variance_reason": "not yet realized",
                    "next_action": "rerun replay after next filing",
                },
                actor=actor,
            )
        if "pb_demo" not in self.store.playbooks:
            self.register_playbook(
                {
                    "playbook_id": "pb_demo",
                    "incident_type": "model_hallucination",
                    "detection_rule": "missing or stale evidence link",
                    "auto_action": "block decision pack",
                    "manual_action": "rerun extraction and review prompt",
                    "owner_role": "CRO",
                },
                actor=actor,
            )
        if "drill_demo" not in self.store.drill_schedules:
            self.register_drill_schedule(
                {
                    "schedule_id": "drill_demo",
                    "incident_type": "model_hallucination",
                    "cadence": "monthly",
                    "owner": "CRO",
                    "notes": "Demo tabletop drill",
                },
                actor=actor,
            )
        period = f"{utcnow().year:04d}-{utcnow().month:02d}"
        report_id = f"opr_{period.replace('-', '_')}"
        if report_id not in self.store.operating_reports:
            self.generate_operating_report({"period": period, "report_id": report_id, "owner": "ceo_demo"}, actor=actor)
        return {
            "issuer_id": "issuer_demo",
            "security_id": "security_demo_us",
            "document_id": "doc_demo_10k",
            "thesis_id": "thesis_demo",
            "signal_id": "sig_demo",
            "decision_id": "dec_demo",
            "intent_id": "intent_demo",
            "review_id": "rev_demo",
            "replay_id": "replay_demo",
            "report_id": report_id,
            "dashboard": self.dashboard(),
        }

    def register_scorecard(self, payload: Mapping[str, Any], *, actor: str = "system") -> ScorecardProfile:
        profile = ScorecardProfile(
            profile_id=str(payload.get("profile_id", new_id("score"))),
            strategy_type=str(payload["strategy_type"]),
            name=str(payload["name"]),
            weights=dict(payload.get("weights", {})),
            threshold_long=float(payload.get("threshold_long", 0.55)),
            threshold_short=float(payload.get("threshold_short", 0.55)),
        )
        self.store.scorecards[profile.profile_id] = profile
        self._audit(actor, "register_scorecard", "scorecard", profile.profile_id)
        return profile

    def create_research_card(self, payload: Mapping[str, Any], *, actor: str = "system") -> ResearchCard:
        template_id = str(payload["template_id"])
        thesis_id = str(payload["thesis_id"])
        template = self.store.templates.get(template_id)
        if template is None:
            raise NotFoundError(f"template {template_id} not found")
        thesis = self.store.theses.get(thesis_id)
        if thesis is None:
            raise NotFoundError(f"thesis {thesis_id} not found")
        fields = dict(payload.get("fields", {}))
        missing = [field for field in template.fields if field not in fields]
        if missing:
            raise ValidationError(f"missing template fields: {missing}")
        card = ResearchCard(
            card_id=str(payload.get("card_id", new_id("card"))),
            template_id=template_id,
            template_type=template.template_type,
            issuer_id=thesis.issuer_id,
            thesis_id=thesis_id,
            title=str(payload.get("title", template.name)),
            fields=fields,
        )
        self.store.research_cards[card.card_id] = card
        self._audit(actor, "create_research_card", "card", card.card_id)
        return card

    def create_research_answer(self, payload: Mapping[str, Any], *, actor: str = "system") -> ResearchAnswer:
        question = str(payload["question"]).strip()
        if not question:
            raise ValidationError("question is required")
        issuer_id = str(payload.get("issuer_id", "")).strip()
        if issuer_id and issuer_id not in self.store.issuers:
            raise NotFoundError(f"issuer {issuer_id} not found")
        requested_evidence_ids = [str(item) for item in payload.get("evidence_ids", [])]
        evidence = self._answer_evidence(question, issuer_id=issuer_id, evidence_ids=requested_evidence_ids)
        if not evidence:
            raise ValidationError("research answer requires English evidence")
        documents = [self.store.documents[item.document_id] for item in evidence if item.document_id in self.store.documents]
        if not documents:
            raise ValidationError("research answer evidence must link to documents")
        non_english = [document.document_id for document in documents if document.language not in {"en", "mixed"}]
        if non_english:
            raise ValidationError(f"research answer requires English-first evidence, non-English documents: {non_english}")
        source_publicness = self._source_publicness(documents)
        source_text = "\n".join(item.canonical_text or item.span_text for item in evidence)
        summary_version = str(payload.get("summary_version", "summary-v1"))
        answer = ResearchAnswer(
            answer_id=str(payload.get("answer_id", new_id("ans"))),
            question=question,
            issuer_id=issuer_id or documents[0].issuer_id,
            evidence_ids=[item.evidence_id for item in evidence],
            source_document_ids=sorted({item.document_id for item in evidence}),
            english_source_text=source_text,
            chinese_summary=str(payload.get("chinese_summary") or self._chinese_summary(source_text, question=question)),
            summary_version=summary_version,
            prompt_version=str(payload.get("prompt_version", "research-answer-v1")),
            model_version=str(payload.get("model_version", "rule-summary-v1")),
            source_publicness=source_publicness,
            human_review_status=str(payload.get("human_review_status", "pending")),
            reviewer=str(payload.get("reviewer", "")),
        )
        if answer.answer_id in self.store.research_answers:
            raise ConflictError(f"research answer {answer.answer_id} already exists")
        self.store.research_answers[answer.answer_id] = answer
        self._audit(
            actor,
            "create_research_answer",
            "research_answer",
            answer.answer_id,
            version=summary_version,
            model_version=answer.model_version,
            prompt_version=answer.prompt_version,
            approval_state=answer.human_review_status,
        )
        return answer

    def research_answer_payload(self, answer_id: str) -> dict[str, Any]:
        answer = self.store.research_answers.get(answer_id)
        if answer is None:
            raise NotFoundError(f"research answer {answer_id} not found")
        return to_plain(answer)

    def review_research_answer(self, answer_id: str, payload: Mapping[str, Any], *, actor: str = "system") -> ResearchAnswer:
        answer = self.store.research_answers.get(answer_id)
        if answer is None:
            raise NotFoundError(f"research answer {answer_id} not found")
        status = str(payload.get("status", "approved"))
        if status not in {"pending", "approved", "rejected"}:
            raise ValidationError("research answer review status must be pending, approved, or rejected")
        answer.human_review_status = status
        answer.reviewer = str(payload.get("reviewer", actor))
        answer.updated_at = utcnow()
        self._audit(
            actor,
            "review_research_answer",
            "research_answer",
            answer.answer_id,
            version=answer.summary_version,
            model_version=answer.model_version,
            prompt_version=answer.prompt_version,
            approval_state=status,
        )
        return answer

    def register_crowding_snapshot(self, payload: Mapping[str, Any], *, actor: str = "system") -> CrowdingSnapshot:
        snapshot = CrowdingSnapshot(
            snapshot_id=str(payload.get("snapshot_id", new_id("crd"))),
            issuer_id=str(payload["issuer_id"]),
            score=float(payload.get("score", 0.0)),
            source=str(payload.get("source", "13F")),
            rationale=str(payload.get("rationale", "")),
        )
        self.store.crowding[snapshot.snapshot_id] = snapshot
        self._audit(actor, "register_crowding_snapshot", "crowding", snapshot.snapshot_id)
        return snapshot

    def register_13f_holding(self, payload: Mapping[str, Any], *, actor: str = "system") -> InstitutionalHolding:
        issuer_id = str(payload["issuer_id"])
        security_id = str(payload["security_id"])
        source_id = str(payload.get("source_id", "sec_edgar"))
        issuer = self.store.issuers.get(issuer_id)
        if issuer is None:
            raise NotFoundError(f"issuer {issuer_id} not found")
        security = self.store.securities.get(security_id)
        if security is None:
            raise NotFoundError(f"security {security_id} not found")
        if security.issuer_id != issuer_id:
            raise ValidationError(f"security {security_id} does not belong to issuer {issuer_id}")
        if source_id not in self.store.sources:
            if source_id == "sec_edgar":
                self.seed_default_sources(actor=actor)
            else:
                raise NotFoundError(f"source {source_id} not found")
        source = self.store.sources[source_id]
        if source.risk_level == "red":
            raise PermissionDenied("red 13F source cannot enter research layer")
        report_period = str(payload["report_period"])
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", report_period):
            raise ValidationError("report_period must use YYYY-MM-DD")
        shares = float(payload.get("shares", 0.0))
        value_usd = float(payload.get("value_usd", 0.0))
        if shares < 0 or value_usd < 0:
            raise ValidationError("13F shares and value_usd must be non-negative")
        holding = InstitutionalHolding(
            holding_id=str(payload.get("holding_id", self._holding_id(issuer_id, security_id, report_period, str(payload.get("filer_cik", ""))))),
            issuer_id=issuer_id,
            security_id=security_id,
            source_id=source_id,
            filer_cik=str(payload.get("filer_cik", "")),
            filer_name=str(payload.get("filer_name", "")),
            report_period=report_period,
            shares=shares,
            value_usd=value_usd,
            voting_authority=str(payload.get("voting_authority", "")),
        )
        if holding.holding_id in self.store.institutional_holdings:
            raise ConflictError(f"13F holding {holding.holding_id} already exists")
        self.store.institutional_holdings[holding.holding_id] = holding
        self._audit(actor, "register_13f_holding", "institutional_holding", holding.holding_id, source=source.source_type, version=source.rights_tag.license_class)
        return holding

    def institutional_holdings_payload(self, filters: Mapping[str, Any] | None = None) -> dict[str, Any]:
        filters = filters or {}
        issuer_id = str(filters.get("issuer_id", "")).strip()
        security_id = str(filters.get("security_id", "")).strip()
        report_period = str(filters.get("report_period", "")).strip()
        limit = self._bounded_limit(filters.get("limit", 50))
        holdings = list(self.store.institutional_holdings.values())
        if issuer_id:
            holdings = [item for item in holdings if item.issuer_id == issuer_id]
        if security_id:
            holdings = [item for item in holdings if item.security_id == security_id]
        if report_period:
            holdings = [item for item in holdings if item.report_period == report_period]
        holdings.sort(key=lambda item: (item.report_period, item.value_usd, item.holding_id), reverse=True)
        return {"holdings": [to_plain(item) for item in holdings[:limit]]}

    def update_crowding_from_13f(self, payload: Mapping[str, Any], *, actor: str = "system") -> CrowdingSnapshot:
        issuer_id = str(payload["issuer_id"])
        if issuer_id not in self.store.issuers:
            raise NotFoundError(f"issuer {issuer_id} not found")
        report_period = str(payload.get("report_period", "")).strip()
        holdings = [item for item in self.store.institutional_holdings.values() if item.issuer_id == issuer_id]
        if report_period:
            holdings = [item for item in holdings if item.report_period == report_period]
        if not holdings:
            raise ValidationError("no 13F holdings available for crowding update")
        total_value = sum(item.value_usd for item in holdings)
        if total_value <= 0:
            raise ValidationError("13F holdings total value must be positive")
        filer_count = len({item.filer_cik or item.filer_name for item in holdings})
        top_value = max(item.value_usd for item in holdings)
        top_share = top_value / total_value
        breadth_score = min(0.35, filer_count / 50 * 0.35)
        concentration_score = min(0.65, top_share * 0.65)
        score = round(min(1.0, concentration_score + breadth_score), 4)
        period_label = report_period or max(item.report_period for item in holdings)
        return self.register_crowding_snapshot(
            {
                "snapshot_id": str(payload.get("snapshot_id", f"crd_13f_{issuer_id}_{period_label}".replace("-", "_"))),
                "issuer_id": issuer_id,
                "score": score,
                "source": "13F",
                "rationale": f"{len(holdings)} holdings, {filer_count} filers, top holder share {top_share:.2%}, period {period_label}",
            },
            actor=actor,
        )

    def create_disclosure_event(self, payload: Mapping[str, Any], *, actor: str = "system") -> DisclosureEvent:
        document_id = str(payload["document_id"])
        document = self.store.documents.get(document_id)
        if document is None:
            raise NotFoundError(f"document {document_id} not found")
        evidence_ids = [str(item) for item in payload.get("evidence_ids", [])]
        for evidence_id in evidence_ids:
            if evidence_id not in self.store.evidence:
                raise NotFoundError(f"evidence {evidence_id} not found")
        event = DisclosureEvent(
            event_id=str(payload.get("event_id", new_id("de"))),
            document_id=document_id,
            issuer_id=str(payload.get("issuer_id", document.issuer_id)),
            security_id=str(payload.get("security_id", document.security_id)),
            event_type=str(payload.get("event_type", "filing_update")),
            severity=str(payload.get("severity", "low")),
            summary=str(payload.get("summary", document.title or document.document_type)),
            evidence_ids=evidence_ids,
            source_id=str(payload.get("source_id", document.source_id)),
            occurred_at=payload.get("occurred_at", document.published_at),
        )
        if event.event_id in self.store.disclosure_events:
            raise ConflictError(f"disclosure event {event.event_id} already exists")
        self.store.disclosure_events[event.event_id] = event
        self._audit(actor, "create_disclosure_event", "disclosure_event", event.event_id, source=event.source_id, approval_state=event.severity)
        return event

    def classify_disclosure_event(self, payload: Mapping[str, Any], *, actor: str = "system") -> DisclosureEvent:
        document_id = str(payload["document_id"])
        document = self.store.documents.get(document_id)
        if document is None:
            raise NotFoundError(f"document {document_id} not found")
        evidence = [item for item in self.store.evidence.values() if item.document_id == document_id]
        if not evidence:
            try:
                evidence = self.extract_evidence(document_id, actor=actor, parser_version="event-classifier", model_version="rule-event-v1")
            except ValidationError:
                evidence = []
        text = " ".join((item.canonical_text or item.span_text) for item in evidence) or document.body or document.title
        event_type = str(payload.get("event_type") or self._infer_disclosure_event_type(document.document_type, text))
        severity = str(payload.get("severity") or self._infer_disclosure_event_severity(event_type, text))
        summary = str(payload.get("summary") or self._disclosure_event_summary(document, event_type, text))
        return self.create_disclosure_event(
            {
                "event_id": str(payload.get("event_id", self._disclosure_event_id(document_id, event_type))),
                "document_id": document_id,
                "issuer_id": document.issuer_id,
                "security_id": document.security_id,
                "event_type": event_type,
                "severity": severity,
                "summary": summary,
                "evidence_ids": [item.evidence_id for item in evidence[:3]],
                "source_id": document.source_id,
                "occurred_at": document.published_at,
            },
            actor=actor,
        )

    def disclosure_events_payload(self, filters: Mapping[str, Any] | None = None) -> dict[str, Any]:
        filters = filters or {}
        issuer_id = str(filters.get("issuer_id", "")).strip()
        security_id = str(filters.get("security_id", "")).strip()
        event_type = str(filters.get("event_type", "")).strip()
        severity = str(filters.get("severity", "")).strip()
        limit = self._bounded_limit(filters.get("limit", 50))
        events = list(self.store.disclosure_events.values())
        if issuer_id:
            events = [item for item in events if item.issuer_id == issuer_id]
        if security_id:
            events = [item for item in events if item.security_id == security_id]
        if event_type:
            events = [item for item in events if item.event_type == event_type]
        if severity:
            events = [item for item in events if item.severity == severity]
        events.sort(key=lambda item: item.occurred_at, reverse=True)
        return {"count": len(events), "events": [to_plain(item) for item in events[:limit]]}

    def run_challenger(self, payload: Mapping[str, Any], *, actor: str = "system") -> ChallengerResult:
        thesis_id = str(payload["thesis_id"])
        thesis = self.store.theses.get(thesis_id)
        if thesis is None:
            raise NotFoundError(f"thesis {thesis_id} not found")
        conflict_score = float(payload.get("conflict_score", 0.0))
        source_conflict = float(payload.get("source_conflict", 0.0))
        valuation_gap = float(payload.get("valuation_gap", 0.0))
        narrative_divergence = float(payload.get("narrative_divergence", 0.0))
        policy_risk = float(payload.get("policy_risk", 0.0))
        total = max(0.0, min(1.0, 0.35 * source_conflict + 0.25 * valuation_gap + 0.25 * narrative_divergence + 0.15 * policy_risk))
        verdict = "block" if total >= 0.7 else "review" if total >= 0.4 else "pass"
        result = ChallengerResult(
            challenger_id=str(payload.get("challenger_id", new_id("chg"))),
            thesis_id=thesis_id,
            conflict_score=total,
            source_conflict=source_conflict,
            valuation_gap=valuation_gap,
            narrative_divergence=narrative_divergence,
            policy_risk=policy_risk,
            verdict=verdict,
            note=str(payload.get("note", "")),
        )
        self.store.challengers[result.challenger_id] = result
        self._audit(actor, "run_challenger", "thesis", thesis_id, approval_state=verdict)
        return result

    def register_playbook(self, payload: Mapping[str, Any], *, actor: str = "system") -> IncidentPlaybook:
        playbook = IncidentPlaybook(
            playbook_id=str(payload.get("playbook_id", new_id("pb"))),
            incident_type=str(payload["incident_type"]),
            detection_rule=str(payload.get("detection_rule", "")),
            auto_action=str(payload.get("auto_action", "")),
            manual_action=str(payload.get("manual_action", "")),
            owner_role=str(payload.get("owner_role", "CRO")),
        )
        self.store.playbooks[playbook.playbook_id] = playbook
        self._audit(actor, "register_playbook", "playbook", playbook.playbook_id)
        return playbook

    def register_drill_schedule(self, payload: Mapping[str, Any], *, actor: str = "system") -> DrillSchedule:
        schedule = DrillSchedule(
            schedule_id=str(payload.get("schedule_id", new_id("drill"))),
            incident_type=str(payload["incident_type"]),
            cadence=str(payload["cadence"]),
            owner=str(payload["owner"]),
            next_run_at=payload.get("next_run_at", utcnow()),
            notes=str(payload.get("notes", "")),
        )
        self.store.drill_schedules[schedule.schedule_id] = schedule
        self._audit(actor, "register_drill_schedule", "drill", schedule.schedule_id)
        return schedule

    def create_incident_report(self, payload: Mapping[str, Any], *, actor: str = "system") -> IncidentReport:
        playbook_id = str(payload["playbook_id"])
        playbook = self.store.playbooks.get(playbook_id)
        if playbook is None:
            raise NotFoundError(f"playbook {playbook_id} not found")
        report = IncidentReport(
            report_id=str(payload.get("report_id", new_id("ir"))),
            playbook_id=playbook_id,
            incident_type=playbook.incident_type,
            root_cause=str(payload.get("root_cause", "")),
            impact=str(payload.get("impact", "")),
            action_items=list(payload.get("action_items", [])),
            owner=str(payload.get("owner", playbook.owner_role)),
        )
        self.store.incident_reports[report.report_id] = report
        self._audit(actor, "create_incident_report", "incident", report.report_id)
        return report

    def register_alert_rule(self, payload: Mapping[str, Any], *, actor: str = "system") -> AlertRule:
        playbook_id = str(payload.get("playbook_id", ""))
        if playbook_id and playbook_id not in self.store.playbooks:
            raise NotFoundError(f"playbook {playbook_id} not found")
        rule = AlertRule(
            rule_id=str(payload.get("rule_id", new_id("alr"))),
            metric=str(payload["metric"]),
            operator=str(payload.get("operator", ">")),
            threshold=float(payload["threshold"]),
            severity=str(payload.get("severity", "medium")),
            owner=str(payload.get("owner", "风险/合规")),
            description=str(payload.get("description", "")),
            enabled=bool(payload.get("enabled", True)),
            playbook_id=playbook_id,
        )
        if rule.rule_id in self.store.alert_rules:
            raise ConflictError(f"alert rule {rule.rule_id} already exists")
        self.store.alert_rules[rule.rule_id] = rule
        self._audit(actor, "register_alert_rule", "alert_rule", rule.rule_id, approval_state="enabled" if rule.enabled else "disabled")
        return rule

    def seed_default_alert_rules(self, *, actor: str = "system") -> list[AlertRule]:
        defaults = [
            {
                "rule_id": "alert_open_manual_reviews",
                "metric": "counts.open_manual_reviews",
                "operator": ">",
                "threshold": 0,
                "severity": "high",
                "owner": "NLP/ML 负责人",
                "description": "Evidence parser failures require OCR or analyst review.",
            },
            {
                "rule_id": "alert_open_exceptions",
                "metric": "counts.open_exceptions",
                "operator": ">",
                "threshold": 0,
                "severity": "medium",
                "owner": "风险/合规",
                "description": "Open governance exceptions require risk follow-up.",
            },
            {
                "rule_id": "alert_pending_prompt_changes",
                "metric": "pending_prompt_changes",
                "operator": ">",
                "threshold": 0,
                "severity": "high",
                "owner": "NLP/ML 负责人",
                "description": "Prompt changes must be approved before release.",
            },
            {
                "rule_id": "alert_pending_decisions",
                "metric": "counts.pending_decisions",
                "operator": ">",
                "threshold": 0,
                "severity": "medium",
                "owner": "CIO",
                "description": "Pending decision packs require committee action.",
            },
        ]
        created: list[AlertRule] = []
        for item in defaults:
            existing = self.store.alert_rules.get(item["rule_id"])
            if existing:
                created.append(existing)
                continue
            created.append(self.register_alert_rule(item, actor=actor))
        return created

    def evaluate_alerts(self, payload: Mapping[str, Any] | None = None, *, actor: str = "system") -> dict[str, Any]:
        payload = payload or {}
        if payload.get("seed_defaults") and not self.store.alert_rules:
            self.seed_default_alert_rules(actor=actor)
        metrics = self.metrics()
        evaluated: list[dict[str, Any]] = []
        opened: list[SystemAlert] = []
        resolved: list[SystemAlert] = []
        for rule in self.store.alert_rules.values():
            if not rule.enabled:
                continue
            value = float(self._metric_value(metrics, rule.metric))
            triggered = self._compare_metric(value, rule.operator, rule.threshold)
            alert_id = self._alert_id(rule.rule_id)
            existing = self.store.system_alerts.get(alert_id)
            if triggered:
                message = f"{rule.metric} {rule.operator} {rule.threshold:g}; current value {value:g}"
                if existing:
                    existing.value = value
                    existing.threshold = rule.threshold
                    existing.severity = rule.severity
                    existing.status = "open"
                    existing.message = message
                    existing.owner = rule.owner
                    existing.playbook_id = rule.playbook_id
                    existing.updated_at = utcnow()
                    alert = existing
                else:
                    alert = SystemAlert(
                        alert_id=alert_id,
                        rule_id=rule.rule_id,
                        metric=rule.metric,
                        value=value,
                        threshold=rule.threshold,
                        severity=rule.severity,
                        status="open",
                        message=message,
                        owner=rule.owner,
                        playbook_id=rule.playbook_id,
                    )
                    self.store.system_alerts[alert.alert_id] = alert
                opened.append(alert)
            elif existing and existing.status == "open":
                existing.value = value
                existing.status = "resolved"
                existing.updated_at = utcnow()
                resolved.append(existing)
            evaluated.append({"rule_id": rule.rule_id, "metric": rule.metric, "value": value, "triggered": triggered})
        self._audit(
            actor,
            "evaluate_alerts",
            "alerts",
            "system",
            approval_state=f"open={len(opened)};resolved={len(resolved)}",
        )
        return {
            "evaluated": evaluated,
            "opened": [to_plain(item) for item in opened],
            "resolved": [to_plain(item) for item in resolved],
            "alerts": self.alerts_payload({"status": "open"})["alerts"],
        }

    def alerts_payload(self, filters: Mapping[str, Any] | None = None) -> dict[str, Any]:
        filters = filters or {}
        status = str(filters.get("status", "")).strip()
        severity = str(filters.get("severity", "")).strip()
        owner = str(filters.get("owner", "")).strip()
        limit = self._bounded_limit(filters.get("limit", 50))
        alerts = list(self.store.system_alerts.values())
        if status:
            alerts = [item for item in alerts if item.status == status]
        if severity:
            alerts = [item for item in alerts if item.severity == severity]
        if owner:
            alerts = [item for item in alerts if item.owner == owner]
        alerts.sort(key=lambda item: (item.status == "open", item.severity, item.updated_at), reverse=True)
        return {
            "rules": [to_plain(item) for item in self.store.alert_rules.values()],
            "alerts": [to_plain(item) for item in alerts[:limit]],
        }

    def notify_alerts(self, payload: Mapping[str, Any] | None = None, *, actor: str = "system") -> dict[str, Any]:
        payload = payload or {}
        channel = str(payload.get("channel", "webhook"))
        target = str(payload.get("target", "internal-risk-channel"))
        alert_ids = {str(item) for item in payload.get("alert_ids", [])}
        alerts = [item for item in self.store.system_alerts.values() if item.status == "open" and (not alert_ids or item.alert_id in alert_ids)]
        notifications: list[AlertNotification] = []
        for alert in alerts:
            notification = AlertNotification(
                notification_id=str(payload.get("notification_id", new_id("aln"))) if len(alerts) == 1 else new_id("aln"),
                alert_id=alert.alert_id,
                channel=channel,
                target=target,
                status="sent" if bool(payload.get("mark_sent", True)) else "pending",
                payload={
                    "severity": alert.severity,
                    "owner": alert.owner,
                    "message": alert.message,
                    "metric": alert.metric,
                    "value": alert.value,
                    "threshold": alert.threshold,
                },
            )
            self.store.alert_notifications[notification.notification_id] = notification
            notifications.append(notification)
        self._audit(actor, "notify_alerts", "alerts", channel, approval_state=f"notifications={len(notifications)}")
        return {"notifications": [to_plain(item) for item in notifications], "count": len(notifications)}

    def alert_notifications_payload(self, filters: Mapping[str, Any] | None = None) -> dict[str, Any]:
        filters = filters or {}
        alert_id = str(filters.get("alert_id", "")).strip()
        channel = str(filters.get("channel", "")).strip()
        status = str(filters.get("status", "")).strip()
        notifications = list(self.store.alert_notifications.values())
        if alert_id:
            notifications = [item for item in notifications if item.alert_id == alert_id]
        if channel:
            notifications = [item for item in notifications if item.channel == channel]
        if status:
            notifications = [item for item in notifications if item.status == status]
        notifications.sort(key=lambda item: item.created_at, reverse=True)
        return {"count": len(notifications), "notifications": [to_plain(item) for item in notifications]}

    def query_graph(self, filters: Mapping[str, Any] | None = None) -> dict[str, Any]:
        filters = filters or {}
        issuer_id = str(filters.get("issuer_id", "")).strip()
        thesis_id = str(filters.get("thesis_id", "")).strip()
        evidence_id = str(filters.get("evidence_id", "")).strip()
        security_id = str(filters.get("security_id", "")).strip()
        decision_id = str(filters.get("decision_id", "")).strip()
        data = {
            "issuers": [],
            "securities": [],
            "market_data": [],
            "corporate_actions": [],
            "documents": [],
            "evidence": [],
            "manual_reviews": [],
            "theses": [],
            "signals": [],
            "decisions": [],
            "execution_intents": [],
            "reviews": [],
            "strategy_replays": [],
            "exceptions": [],
            "entity_mappings": [],
            "research_cards": [],
            "crowding": [],
            "institutional_holdings": [],
            "disclosure_events": [],
            "challengers": [],
            "portfolio_proposals": [],
            "portfolio_positions": [],
            "edges": [],
        }
        seen: dict[str, set[str]] = {key: set() for key in data if key not in {"edges", "portfolio_positions"}}
        edge_keys: set[tuple[str, str, str]] = set()

        def add_node(collection: str, object_id: str, value: Any) -> None:
            if object_id and object_id not in seen[collection]:
                data[collection].append(to_plain(value))
                seen[collection].add(object_id)

        def add_edge(edge_type: str, from_id: str, to_id: str, **attrs: Any) -> None:
            if not from_id or not to_id:
                return
            edge_key = (edge_type, from_id, to_id)
            if edge_key in edge_keys:
                return
            edge = {"type": edge_type, "from": from_id, "to": to_id}
            edge.update(attrs)
            data["edges"].append(edge)
            edge_keys.add(edge_key)

        def add_document_graph(document: Document) -> None:
            add_node("documents", document.document_id, document)
            add_edge("DISCLOSES", document.issuer_id, document.document_id, as_of=to_plain(document.published_at), source_id=document.source_id)
            if document.security_id:
                add_edge("DISCLOSURE_FOR", document.document_id, document.security_id)
            for evidence in self.store.evidence.values():
                if evidence.document_id == document.document_id:
                    add_node("evidence", evidence.evidence_id, evidence)
                    add_edge("HAS_EVIDENCE", document.document_id, evidence.evidence_id, page_no=evidence.page_no, bbox=evidence.bbox)
            for review in self.store.manual_reviews.values():
                if review.document_id == document.document_id:
                    add_node("manual_reviews", review.review_id, review)
                    add_edge("NEEDS_REVIEW", document.document_id, review.review_id, issue_type=review.issue_type, severity=review.severity, status=review.status)

        def add_thesis_graph(thesis: ThesisCard) -> None:
            add_node("theses", thesis.thesis_id, thesis)
            add_edge("HAS_THESIS", thesis.issuer_id, thesis.thesis_id, valid_from=to_plain(thesis.valid_from), valid_to=to_plain(thesis.valid_to))
            for supported_evidence_id in thesis.evidence_ids:
                evidence = self.store.evidence.get(supported_evidence_id)
                if evidence is None:
                    continue
                add_node("evidence", evidence.evidence_id, evidence)
                document = self.store.documents.get(evidence.document_id)
                if document is not None:
                    add_document_graph(document)
                add_edge("SUPPORTS", evidence.evidence_id, thesis.thesis_id, confidence=evidence.confidence)
            for signal in self.store.signals.values():
                if signal.thesis_id == thesis.thesis_id:
                    add_node("signals", signal.signal_id, signal)
                    add_edge("GENERATES_SIGNAL", thesis.thesis_id, signal.signal_id, score=signal.score, direction=signal.direction)
            for card in self.store.research_cards.values():
                if card.thesis_id == thesis.thesis_id:
                    add_node("research_cards", card.card_id, card)
                    add_edge("SUMMARIZED_BY", thesis.thesis_id, card.card_id, template_type=card.template_type)
            for challenger in self.store.challengers.values():
                if challenger.thesis_id == thesis.thesis_id:
                    add_node("challengers", challenger.challenger_id, challenger)
                    add_edge("CHALLENGES", challenger.challenger_id, thesis.thesis_id, conflict_score=challenger.conflict_score, verdict=challenger.verdict)

        def add_decision_graph(decision: DecisionPack) -> None:
            add_node("decisions", decision.decision_id, decision)
            thesis_ids: set[str] = set()
            evidence_ids: set[str] = set()
            for signal_id in decision.signal_ids:
                signal = self.store.signals.get(signal_id)
                if signal is None:
                    continue
                add_node("signals", signal.signal_id, signal)
                add_edge("INCLUDED_IN_DECISION", signal.signal_id, decision.decision_id, approval_state=decision.approval_state)
                thesis = self.store.theses.get(signal.thesis_id)
                if thesis is not None:
                    thesis_ids.add(thesis.thesis_id)
                    evidence_ids.update(thesis.evidence_ids)
                    add_thesis_graph(thesis)
            for intent in self.store.execution_intents.values():
                if intent.decision_id != decision.decision_id:
                    continue
                add_node("execution_intents", intent.intent_id, intent)
                add_edge("CREATES_INTENT", decision.decision_id, intent.intent_id, approval_state=decision.approval_state)
                if intent.security_id:
                    add_edge("INTENT_ON", intent.intent_id, intent.security_id, action=intent.action, target_weight=intent.target_weight)
                    data["portfolio_positions"].append(
                        {
                            "intent_id": intent.intent_id,
                            "decision_id": decision.decision_id,
                            "security_id": intent.security_id,
                            "action": intent.action,
                            "target_weight": intent.target_weight,
                            "approval_state": decision.approval_state,
                            "thesis_ids": sorted(thesis_ids),
                            "evidence_ids": sorted(evidence_ids),
                            "risk_checks": list(decision.risk_checks),
                        }
                    )
            for review in self.store.reviews.values():
                if review.decision_id == decision.decision_id:
                    add_node("reviews", review.review_id, review)
                    add_edge("REVIEW_OF", review.review_id, decision.decision_id)
            for replay in self.store.strategy_replays.values():
                if replay.decision_id == decision.decision_id:
                    add_node("strategy_replays", replay.replay_id, replay)
                    add_edge("REPLAY_OF", replay.replay_id, decision.decision_id)
            for exception in self.store.exceptions.values():
                if exception.decision_id == decision.decision_id:
                    add_node("exceptions", exception.exception_id, exception)
                    add_edge("HAS_EXCEPTION", decision.decision_id, exception.exception_id, severity=exception.severity, status=exception.status)

        def add_issuer_graph(issuer: Issuer) -> None:
            add_node("issuers", issuer.issuer_id, issuer)
            for mapping in self.store.entity_mappings.values():
                if mapping.issuer_id == issuer.issuer_id:
                    add_node("entity_mappings", mapping.mapping_id, mapping)
                    add_edge("HAS_MAPPING", issuer.issuer_id, mapping.mapping_id, market=mapping.market, ticker=mapping.ticker)
            issuer_security_ids: set[str] = set()
            for security in self.store.securities.values():
                if security.issuer_id == issuer.issuer_id:
                    issuer_security_ids.add(security.security_id)
                    add_node("securities", security.security_id, security)
                    add_edge("ISSUES", issuer.issuer_id, security.security_id, market=security.market, ticker=security.ticker)
            for point in self.store.market_data.values():
                if point.security_id in issuer_security_ids:
                    add_node("market_data", point.data_id, point)
                    add_edge("HAS_MARKET_DATA", point.security_id, point.data_id, as_of_date=point.as_of_date, data_type=point.data_type)
            for action in self.store.corporate_actions.values():
                if action.security_id in issuer_security_ids:
                    add_node("corporate_actions", action.action_id, action)
                    add_edge("HAS_CORPORATE_ACTION", action.security_id, action.action_id, action_type=action.action_type, ex_date=action.ex_date)
            for document in self.store.documents.values():
                if document.issuer_id == issuer.issuer_id:
                    add_document_graph(document)
            for event in self.store.disclosure_events.values():
                if event.issuer_id == issuer.issuer_id:
                    add_node("disclosure_events", event.event_id, event)
                    add_edge("HAS_DISCLOSURE_EVENT", issuer.issuer_id, event.event_id, event_type=event.event_type, severity=event.severity)
                    add_edge("EVENT_FROM_DOCUMENT", event.event_id, event.document_id, source_id=event.source_id)
                    if event.security_id:
                        add_edge("EVENT_ON_SECURITY", event.event_id, event.security_id)
                    for event_evidence_id in event.evidence_ids:
                        add_edge("EVENT_EVIDENCE", event.event_id, event_evidence_id)
            for thesis in self.store.theses.values():
                if thesis.issuer_id == issuer.issuer_id:
                    add_thesis_graph(thesis)
            for decision in self.store.decisions.values():
                for signal_id in decision.signal_ids:
                    signal = self.store.signals.get(signal_id)
                    thesis = self.store.theses.get(signal.thesis_id) if signal else None
                    if thesis and thesis.issuer_id == issuer.issuer_id:
                        add_decision_graph(decision)
                        break
            for intent in self.store.execution_intents.values():
                if intent.security_id in issuer_security_ids:
                    decision = self.store.decisions.get(intent.decision_id)
                    if decision is not None:
                        add_decision_graph(decision)
                    else:
                        add_node("execution_intents", intent.intent_id, intent)
                        add_edge("INTENT_ON", intent.intent_id, intent.security_id, action=intent.action, target_weight=intent.target_weight)
            for holding in self.store.institutional_holdings.values():
                if holding.issuer_id == issuer.issuer_id:
                    add_node("institutional_holdings", holding.holding_id, holding)
                    add_edge("HAS_13F_HOLDING", issuer.issuer_id, holding.holding_id, report_period=holding.report_period, value_usd=holding.value_usd)
                    add_edge("HOLDS_SECURITY", holding.holding_id, holding.security_id, shares=holding.shares, value_usd=holding.value_usd)
            for snapshot in self.store.crowding.values():
                if snapshot.issuer_id == issuer.issuer_id:
                    add_node("crowding", snapshot.snapshot_id, snapshot)
                    add_edge("HAS_CROWDING", issuer.issuer_id, snapshot.snapshot_id, source=snapshot.source, score=snapshot.score)
                    if snapshot.source.upper() == "13F":
                        for holding in self.store.institutional_holdings.values():
                            if holding.issuer_id == issuer.issuer_id:
                                add_edge("CONTRIBUTES_TO_CROWDING", holding.holding_id, snapshot.snapshot_id, report_period=holding.report_period)
            for proposal in self.store.portfolio_proposals.values():
                proposal_security_ids = set(proposal.universe) | set(proposal.candidate_weights)
                if proposal_security_ids & issuer_security_ids:
                    add_node("portfolio_proposals", proposal.proposal_id, proposal)
                    add_edge("HAS_PORTFOLIO_PROPOSAL", issuer.issuer_id, proposal.proposal_id, status=proposal.status)
                    for proposal_security_id, weight in proposal.candidate_weights.items():
                        if proposal_security_id in issuer_security_ids:
                            add_edge("PROPOSES_WEIGHT", proposal.proposal_id, proposal_security_id, weight=weight)

        if issuer_id:
            issuer = self.store.issuers.get(issuer_id)
            if issuer:
                add_issuer_graph(issuer)
        if security_id:
            security = self.store.securities.get(security_id)
            if security:
                add_node("securities", security.security_id, security)
                issuer = self.store.issuers.get(security.issuer_id)
                if issuer:
                    add_issuer_graph(issuer)
                else:
                    for point in self.store.market_data.values():
                        if point.security_id == security.security_id:
                            add_node("market_data", point.data_id, point)
                            add_edge("HAS_MARKET_DATA", security.security_id, point.data_id, as_of_date=point.as_of_date, data_type=point.data_type)
                    for action in self.store.corporate_actions.values():
                        if action.security_id == security.security_id:
                            add_node("corporate_actions", action.action_id, action)
                            add_edge("HAS_CORPORATE_ACTION", security.security_id, action.action_id, action_type=action.action_type, ex_date=action.ex_date)
                    for intent in self.store.execution_intents.values():
                        if intent.security_id == security.security_id:
                            add_node("execution_intents", intent.intent_id, intent)
                            add_edge("INTENT_ON", intent.intent_id, security.security_id, action=intent.action, target_weight=intent.target_weight)
                    for proposal in self.store.portfolio_proposals.values():
                        if security.security_id in proposal.universe or security.security_id in proposal.candidate_weights:
                            add_node("portfolio_proposals", proposal.proposal_id, proposal)
                            add_edge("PROPOSES_WEIGHT", proposal.proposal_id, security.security_id, weight=proposal.candidate_weights.get(security.security_id, 0.0))
                    for event in self.store.disclosure_events.values():
                        if event.security_id == security.security_id:
                            add_node("disclosure_events", event.event_id, event)
                            add_edge("EVENT_ON_SECURITY", event.event_id, security.security_id)
        if evidence_id:
            evidence = self.store.evidence.get(evidence_id)
            if evidence:
                add_node("evidence", evidence.evidence_id, evidence)
                document = self.store.documents.get(evidence.document_id)
                if document is not None:
                    add_document_graph(document)
                    issuer = self.store.issuers.get(document.issuer_id)
                    if issuer:
                        add_node("issuers", issuer.issuer_id, issuer)
                for thesis in self.store.theses.values():
                    if evidence.evidence_id in thesis.evidence_ids:
                        add_thesis_graph(thesis)
        if thesis_id:
            thesis = self.store.theses.get(thesis_id)
            if thesis:
                add_thesis_graph(thesis)
                issuer = self.store.issuers.get(thesis.issuer_id)
                if issuer:
                    add_node("issuers", issuer.issuer_id, issuer)
                for decision in self.store.decisions.values():
                    if any((self.store.signals.get(signal_id) and self.store.signals[signal_id].thesis_id == thesis.thesis_id) for signal_id in decision.signal_ids):
                        add_decision_graph(decision)
        if decision_id:
            decision = self.store.decisions.get(decision_id)
            if decision:
                add_decision_graph(decision)
        return data

    def search(self, filters: Mapping[str, Any]) -> dict[str, Any]:
        query = str(filters.get("q", "")).strip()
        if not query:
            return {"query": query, "results": []}
        issuer_filter = str(filters.get("issuer_id", "")).strip()
        limit = self._bounded_limit(filters.get("limit", 20))
        terms = [term.lower() for term in re.findall(r"[\w\u4e00-\u9fff]+", query)]
        if not terms:
            return {"query": query, "results": []}
        records = self._search_records()
        try:
            sync_result = self.search_index.sync(records)
            results = self.search_index.search(records, query=query, issuer_id=issuer_filter, limit=limit)
            return {"query": query, "backend": self.search_index.backend, "sync": sync_result, "results": results}
        except Exception as exc:
            if self.search_index.backend != "local" and self.search_fallback:
                results = self.local_search_index.search(records, query=query, issuer_id=issuer_filter, limit=limit)
                return {
                    "query": query,
                    "backend": "local",
                    "fallback_from": self.search_index.backend,
                    "fallback_error": str(exc),
                    "results": results,
                }
            raise

    def _search_records(self) -> list[SearchRecord]:
        records: list[SearchRecord] = []
        for document in self.store.documents.values():
            body = document.body or self._document_object_text(document)
            records.append(
                SearchRecord(
                    resource_type="document",
                    resource_id=document.document_id,
                    issuer_id=document.issuer_id,
                    title=document.title or document.document_type,
                    body=" ".join(chunk_text(body)),
                    weight=1.0,
                )
            )
        for evidence in self.store.evidence.values():
            document = self.store.documents.get(evidence.document_id)
            records.append(
                SearchRecord(
                    resource_type="evidence",
                    resource_id=evidence.evidence_id,
                    issuer_id=document.issuer_id if document else "",
                    title=evidence.section,
                    body=evidence.span_text,
                    weight=1.5,
                )
            )
        for thesis in self.store.theses.values():
            records.append(
                SearchRecord(
                    resource_type="thesis",
                    resource_id=thesis.thesis_id,
                    issuer_id=thesis.issuer_id,
                    title=thesis.hypothesis,
                    body=" ".join(thesis.catalyst + thesis.falsifiers + thesis.risk_factors),
                    weight=1.2,
                )
            )
        for card in self.store.research_cards.values():
            records.append(
                SearchRecord(
                    resource_type="research_card",
                    resource_id=card.card_id,
                    issuer_id=card.issuer_id,
                    title=card.title,
                    body=" ".join(str(value) for value in card.fields.values()),
                    weight=1.1,
                )
            )
        for answer in self.store.research_answers.values():
            records.append(
                SearchRecord(
                    resource_type="research_answer",
                    resource_id=answer.answer_id,
                    issuer_id=answer.issuer_id,
                    title=answer.question,
                    body=f"{answer.chinese_summary} {answer.english_source_text}",
                    weight=1.0,
                )
            )
        for point in self.store.market_data.values():
            security = self.store.securities.get(point.security_id)
            records.append(
                SearchRecord(
                    resource_type="market_data",
                    resource_id=point.data_id,
                    issuer_id=security.issuer_id if security else "",
                    title=f"{point.security_id} {point.as_of_date} {point.data_type}",
                    body=f"{point.market} close {point.close} volume {point.volume} source {point.source_id}",
                    weight=0.6,
                )
            )
        for action in self.store.corporate_actions.values():
            security = self.store.securities.get(action.security_id)
            records.append(
                SearchRecord(
                    resource_type="corporate_action",
                    resource_id=action.action_id,
                    issuer_id=security.issuer_id if security else "",
                    title=f"{action.security_id} {action.action_type} {action.ex_date}",
                    body=f"ratio {action.ratio} cash {action.cash_amount} {action.currency} {action.description}",
                    weight=0.6,
                )
            )
        for holding in self.store.institutional_holdings.values():
            records.append(
                SearchRecord(
                    resource_type="institutional_holding",
                    resource_id=holding.holding_id,
                    issuer_id=holding.issuer_id,
                    title=f"{holding.filer_name or holding.filer_cik} {holding.report_period}",
                    body=f"{holding.security_id} shares {holding.shares} value_usd {holding.value_usd} source {holding.source_id}",
                    weight=0.7,
                )
            )
        for event in self.store.disclosure_events.values():
            records.append(
                SearchRecord(
                    resource_type="disclosure_event",
                    resource_id=event.event_id,
                    issuer_id=event.issuer_id,
                    title=f"{event.event_type} {event.severity}",
                    body=f"{event.summary} {event.document_id} {event.security_id}",
                    weight=0.9,
                )
            )
        for proposal in self.store.portfolio_proposals.values():
            records.append(
                SearchRecord(
                    resource_type="portfolio_proposal",
                    resource_id=proposal.proposal_id,
                    issuer_id="",
                    title=f"{proposal.proposal_id} {proposal.status}",
                    body=f"{proposal.universe} {proposal.candidate_weights} {proposal.diagnostics}",
                    weight=0.8,
                )
            )
        for sample in self.store.benchmark_samples.values():
            records.append(
                SearchRecord(
                    resource_type="benchmark_sample",
                    resource_id=sample.sample_id,
                    issuer_id="",
                    title=f"{sample.benchmark_id} {sample.language}",
                    body=f"{sample.document_id} {sample.expected_terms} pages {sample.expected_pages} {sample.notes}",
                    weight=0.5,
                )
            )
        return records

    def health(self) -> dict[str, Any]:
        now = utcnow()
        return {
            "status": "ok",
            "service": "ai-native-quant-org",
            "started_at": to_plain(self.started_at),
            "checked_at": to_plain(now),
            "uptime_seconds": round((now - self.started_at).total_seconds(), 3),
            "store": type(self.store).__name__,
            "object_store": self.object_store.describe(),
            "search_index": self.search_index.describe(),
        }

    def metrics(self) -> dict[str, Any]:
        dashboard = self.dashboard()
        return {
            "counts": dashboard["counts"],
            "audit_events": len(self.store.audit_log),
            "latest_audit": dashboard["latest_audit"],
            "open_exceptions": dashboard["counts"]["open_exceptions"],
            "pending_prompt_changes": sum(1 for item in self.store.prompt_changes.values() if item.status == "pending"),
            "object_store": self.object_store.describe(),
            "search_index": self.search_index.describe(),
            "store": type(self.store).__name__,
        }

    def dashboard(self) -> dict[str, Any]:
        pending_decisions = sum(1 for decision in self.store.decisions.values() if decision.approval_state == "pending")
        approved_decisions = sum(1 for decision in self.store.decisions.values() if decision.approval_state == "approved")
        open_exceptions = sum(1 for item in self.store.exceptions.values() if item.status == "open")
        open_manual_reviews = sum(1 for item in self.store.manual_reviews.values() if item.status == "open")
        open_alerts = sum(1 for item in self.store.system_alerts.values() if item.status == "open")
        market_data_summary = [
            {
                "data_id": point.data_id,
                "security_id": point.security_id,
                "market": point.market,
                "as_of_date": point.as_of_date,
                "data_type": point.data_type,
                "close": point.close,
                "volume": point.volume,
                "source_id": point.source_id,
                "license_class": point.rights_tag.license_class,
                "non_display_use": point.rights_tag.non_display_use,
            }
            for point in sorted(self.store.market_data.values(), key=lambda item: (item.as_of_date, item.security_id), reverse=True)[:10]
        ]
        corporate_action_summary = [
            {
                "action_id": action.action_id,
                "security_id": action.security_id,
                "action_type": action.action_type,
                "ex_date": action.ex_date,
                "ratio": action.ratio,
                "cash_amount": action.cash_amount,
            }
            for action in sorted(self.store.corporate_actions.values(), key=lambda item: (item.ex_date, item.security_id), reverse=True)[:10]
        ]
        institutional_holding_summary = [
            {
                "holding_id": holding.holding_id,
                "issuer_id": holding.issuer_id,
                "security_id": holding.security_id,
                "filer_name": holding.filer_name,
                "report_period": holding.report_period,
                "value_usd": holding.value_usd,
            }
            for holding in sorted(self.store.institutional_holdings.values(), key=lambda item: (item.report_period, item.value_usd), reverse=True)[:10]
        ]
        crowding_heatmap = [
            {
                "issuer_id": snapshot.issuer_id,
                "score": snapshot.score,
                "source": snapshot.source,
            }
            for snapshot in self.store.crowding.values()
        ]
        filings_timeline = [
            {
                "document_id": document.document_id,
                "issuer_id": document.issuer_id,
                "document_type": document.document_type,
                "published_at": to_plain(document.published_at),
                "title": document.title,
            }
            for document in sorted(self.store.documents.values(), key=lambda item: item.published_at, reverse=True)[:10]
        ]
        disclosure_event_wall = [
            {
                "event_id": event.event_id,
                "issuer_id": event.issuer_id,
                "security_id": event.security_id,
                "event_type": event.event_type,
                "severity": event.severity,
                "summary": event.summary,
                "occurred_at": to_plain(event.occurred_at),
            }
            for event in sorted(self.store.disclosure_events.values(), key=lambda item: item.occurred_at, reverse=True)[:10]
        ]
        return {
            "counts": {
                "sources": len(self.store.sources),
                "ingestion_jobs": len(self.store.ingestion_jobs),
                "ingestion_schedules": len(self.store.ingestion_schedules),
                "issuers": len(self.store.issuers),
                "securities": len(self.store.securities),
                "market_data": len(self.store.market_data),
                "corporate_actions": len(self.store.corporate_actions),
                "institutional_holdings": len(self.store.institutional_holdings),
                "disclosure_events": len(self.store.disclosure_events),
                "documents": len(self.store.documents),
                "evidence": len(self.store.evidence),
                "manual_reviews": len(self.store.manual_reviews),
                "open_manual_reviews": open_manual_reviews,
                "benchmark_samples": len(self.store.benchmark_samples),
                "benchmark_runs": len(self.store.benchmark_runs),
                "extraction_results": len(self.store.extraction_results),
                "research_answers": len(self.store.research_answers),
                "theses": len(self.store.theses),
                "signals": len(self.store.signals),
                "decisions": len(self.store.decisions),
                "pending_decisions": pending_decisions,
                "approved_decisions": approved_decisions,
                "execution_intents": len(self.store.execution_intents),
                "reviews": len(self.store.reviews),
                "operating_reports": len(self.store.operating_reports),
                "strategy_replays": len(self.store.strategy_replays),
                "portfolio_proposals": len(self.store.portfolio_proposals),
                "open_exceptions": open_exceptions,
                "alert_rules": len(self.store.alert_rules),
                "open_alerts": open_alerts,
                "alert_notifications": len(self.store.alert_notifications),
            },
            "market_data_summary": market_data_summary,
            "corporate_action_summary": corporate_action_summary,
            "institutional_holding_summary": institutional_holding_summary,
            "crowding_heatmap": crowding_heatmap,
            "filings_timeline": filings_timeline,
            "disclosure_event_wall": disclosure_event_wall,
            "exceptions": [to_plain(item) for item in self.store.exceptions.values()],
            "alerts": [to_plain(item) for item in self.store.system_alerts.values() if item.status == "open"],
            "latest_audit": to_plain(self.store.audit_log[-1]) if self.store.audit_log else None,
        }

    def document_payload(self, document_id: str) -> dict[str, Any]:
        document = self.store.documents.get(document_id)
        if document is None:
            raise NotFoundError(f"document {document_id} not found")
        return to_plain(document)

    def thesis_payload(self, thesis_id: str) -> dict[str, Any]:
        thesis = self.store.theses.get(thesis_id)
        if thesis is None:
            raise NotFoundError(f"thesis {thesis_id} not found")
        signal = next((sig for sig in self.store.signals.values() if sig.thesis_id == thesis_id), None)
        return {
            "thesis": to_plain(thesis),
            "signals": [to_plain(sig) for sig in self.store.signals.values() if sig.thesis_id == thesis_id],
            "primary_signal": to_plain(signal) if signal else None,
            "evidence": [to_plain(self.store.evidence[eid]) for eid in thesis.evidence_ids],
        }

    def signal_payload(self, signal_id: str) -> dict[str, Any]:
        signal = self.store.signals.get(signal_id)
        if signal is None:
            raise NotFoundError(f"signal {signal_id} not found")
        return to_plain(signal)

    def decision_payload(self, decision_id: str) -> dict[str, Any]:
        decision = self.store.decisions.get(decision_id)
        if decision is None:
            raise NotFoundError(f"decision {decision_id} not found")
        return to_plain(decision)

    def ingestion_job_payload(self, job_id: str) -> dict[str, Any]:
        job = self.store.ingestion_jobs.get(job_id)
        if job is None:
            raise NotFoundError(f"ingestion job {job_id} not found")
        return to_plain(job)

    def ingestion_schedule_payload(self, schedule_id: str) -> dict[str, Any]:
        schedule = self.store.ingestion_schedules.get(schedule_id)
        if schedule is None:
            raise NotFoundError(f"ingestion schedule {schedule_id} not found")
        return to_plain(schedule)

    def extraction_payload(self, extraction_id: str) -> dict[str, Any]:
        result = self.store.extraction_results.get(extraction_id)
        if result is None:
            raise NotFoundError(f"extraction {extraction_id} not found")
        return to_plain(result)

    def execution_intent_payload(self, intent_id: str) -> dict[str, Any]:
        intent = self.store.execution_intents.get(intent_id)
        if intent is None:
            raise NotFoundError(f"execution intent {intent_id} not found")
        return to_plain(intent)

    def review_payload(self, review_id: str) -> dict[str, Any]:
        review = self.store.reviews.get(review_id)
        if review is None:
            raise NotFoundError(f"review {review_id} not found")
        return to_plain(review)

    def operating_report_payload(self, report_id: str) -> dict[str, Any]:
        report = self.store.operating_reports.get(report_id)
        if report is None:
            raise NotFoundError(f"operating report {report_id} not found")
        return to_plain(report)

    def strategy_replay_payload(self, replay_id: str) -> dict[str, Any]:
        replay = self.store.strategy_replays.get(replay_id)
        if replay is None:
            raise NotFoundError(f"strategy replay {replay_id} not found")
        return to_plain(replay)

    def incident_calendar(self) -> dict[str, Any]:
        return {
            "playbooks": [to_plain(playbook) for playbook in self.store.playbooks.values()],
            "reports": [to_plain(report) for report in self.store.incident_reports.values()],
            "schedules": [to_plain(schedule) for schedule in self.store.drill_schedules.values()],
        }

    def _sec_user_agent(self, payload: Mapping[str, Any]) -> str:
        return str(payload.get("user_agent") or os.environ.get("AI_QUANT_SEC_USER_AGENT") or DEFAULT_SEC_USER_AGENT)

    def _ashare_user_agent(self, payload: Mapping[str, Any]) -> str:
        return str(payload.get("user_agent") or os.environ.get("AI_QUANT_ASHARE_USER_AGENT") or DEFAULT_SEC_USER_AGENT)

    def _hkex_user_agent(self, payload: Mapping[str, Any]) -> str:
        return str(payload.get("user_agent") or os.environ.get("AI_QUANT_HKEX_USER_AGENT") or DEFAULT_HKEX_USER_AGENT)

    def _bounded_limit(self, value: Any) -> int:
        return max(1, min(100, int(value)))

    def _sec_document_id(self, filing: Any) -> str:
        metadata = filing.metadata or {}
        accession_no = str(metadata.get("accession_no", "")).replace("-", "")
        primary_doc = str(metadata.get("primary_doc", "index")).rsplit("/", maxsplit=1)[-1]
        raw = f"sec_{accession_no}_{primary_doc}"
        return "doc_" + re.sub(r"[^A-Za-z0-9_-]+", "_", raw).strip("_").lower()

    def _ashare_document_id(self, filing: Any) -> str:
        basename = str(filing.source_uri or filing.title or new_id("ashare")).rsplit("/", maxsplit=1)[-1]
        raw = f"ashare_{basename}"
        return "doc_" + re.sub(r"[^A-Za-z0-9_-]+", "_", raw).strip("_").lower()

    def _hkex_document_id(self, filing: Any) -> str:
        basename = str(filing.source_uri or filing.title or new_id("hkex")).rsplit("/", maxsplit=1)[-1]
        raw = f"hkex_{basename}"
        return "doc_" + re.sub(r"[^A-Za-z0-9_-]+", "_", raw).strip("_").lower()

    def _market_data_id(self, security_id: str, as_of_date: str, data_type: str, source_id: str) -> str:
        raw = f"md_{source_id}_{security_id}_{as_of_date}_{data_type}"
        return re.sub(r"[^A-Za-z0-9_-]+", "_", raw).strip("_").lower()

    def _corporate_action_id(self, security_id: str, action_type: str, ex_date: str, source_id: str) -> str:
        raw = f"ca_{source_id}_{security_id}_{action_type}_{ex_date}"
        return re.sub(r"[^A-Za-z0-9_-]+", "_", raw).strip("_").lower()

    def _holding_id(self, issuer_id: str, security_id: str, report_period: str, filer_cik: str) -> str:
        raw = f"13f_{issuer_id}_{security_id}_{report_period}_{filer_cik or new_id('filer')}"
        return re.sub(r"[^A-Za-z0-9_-]+", "_", raw).strip("_").lower()

    def _disclosure_event_id(self, document_id: str, event_type: str) -> str:
        raw = f"de_{document_id}_{event_type}"
        return re.sub(r"[^A-Za-z0-9_-]+", "_", raw).strip("_").lower()

    def _infer_disclosure_event_type(self, document_type: str, text: str) -> str:
        lowered = text.lower()
        if "resign" in lowered or "appointed" in lowered or "chief executive" in lowered or "cfo" in lowered:
            return "management_change"
        if "guidance" in lowered or "outlook" in lowered or "forecast" in lowered:
            return "guidance_update"
        if "acquisition" in lowered or "merger" in lowered or "material definitive agreement" in lowered:
            return "material_agreement"
        if "repurchase" in lowered or "buyback" in lowered or "dividend" in lowered:
            return "capital_allocation"
        if document_type in {"8-K", "6-K"}:
            return "current_report"
        if document_type == "20-F":
            return "annual_foreign_private_issuer_report"
        return "filing_update"

    def _infer_disclosure_event_severity(self, event_type: str, text: str) -> str:
        lowered = text.lower()
        high_terms = ["material weakness", "going concern", "resign", "bankruptcy", "restatement", "investigation"]
        if any(term in lowered for term in high_terms):
            return "high"
        if event_type in {"management_change", "material_agreement", "guidance_update"}:
            return "medium"
        return "low"

    def _disclosure_event_summary(self, document: Document, event_type: str, text: str) -> str:
        snippet = re.sub(r"\s+", " ", text).strip()[:240]
        return f"{document.document_type} {event_type}: {snippet}"

    def _answer_evidence(self, question: str, *, issuer_id: str, evidence_ids: list[str]) -> list[Evidence]:
        if evidence_ids:
            evidence = []
            for evidence_id in evidence_ids:
                item = self.store.evidence.get(evidence_id)
                if item is None:
                    raise NotFoundError(f"evidence {evidence_id} not found")
                document = self.store.documents.get(item.document_id)
                if issuer_id and document and document.issuer_id != issuer_id:
                    raise ValidationError(f"evidence {evidence_id} does not belong to issuer {issuer_id}")
                evidence.append(item)
            return evidence
        terms = [term.lower() for term in re.findall(r"[\w]+", question) if len(term) >= 4]
        scored: list[tuple[int, Evidence]] = []
        for item in self.store.evidence.values():
            document = self.store.documents.get(item.document_id)
            if document is None:
                continue
            if issuer_id and document.issuer_id != issuer_id:
                continue
            if document.language not in {"en", "mixed"}:
                continue
            text = (item.canonical_text or item.span_text).lower()
            score = sum(1 for term in terms if term in text)
            if score > 0:
                scored.append((score, item))
        scored.sort(key=lambda pair: (pair[0], pair[1].confidence), reverse=True)
        return [item for _score, item in scored[:5]]

    def _source_publicness(self, documents: list[Document]) -> str:
        licenses = {document.rights_tag.license_class.lower() for document in documents}
        if licenses <= {"public"}:
            return "public"
        if any("private" in item or "restricted" in item for item in licenses):
            return "restricted"
        return ",".join(sorted(licenses)) or "unknown"

    def _chinese_summary(self, source_text: str, *, question: str) -> str:
        compact = " ".join(chunk_text(source_text))[:360]
        return f"问题：{question}\n中文摘要：基于英文原文证据，{compact}"

    def _alert_id(self, rule_id: str) -> str:
        raw = f"alert_{rule_id}"
        return re.sub(r"[^A-Za-z0-9_-]+", "_", raw).strip("_").lower()

    def _metric_value(self, metrics: Mapping[str, Any], path: str) -> float:
        current: Any = metrics
        for part in path.split("."):
            if isinstance(current, Mapping) and part in current:
                current = current[part]
            else:
                return 0.0
        if isinstance(current, bool):
            return 1.0 if current else 0.0
        try:
            return float(current)
        except (TypeError, ValueError):
            return 0.0

    def _compare_metric(self, value: float, operator: str, threshold: float) -> bool:
        if operator == ">":
            return value > threshold
        if operator == ">=":
            return value >= threshold
        if operator == "<":
            return value < threshold
        if operator == "<=":
            return value <= threshold
        if operator == "==":
            return value == threshold
        if operator == "!=":
            return value != threshold
        raise ValidationError(f"unsupported operator {operator}")

    def _manual_review_id(self, document_id: str, issue_type: str) -> str:
        raw = f"mrev_{document_id}_{issue_type}"
        return re.sub(r"[^A-Za-z0-9_-]+", "_", raw).strip("_").lower()

    def _store_attachment(self, market: str, filing: Any, document_id: str, *, user_agent: str, max_bytes: int) -> Any:
        data = self.connectors.fetch_document_binary(market, filing.source_uri, user_agent=user_agent, max_bytes=max_bytes)
        suffix = self._suffix_from_uri(filing.source_uri)
        return self.object_store.put_bytes(filing.source_id, document_id, data, suffix=suffix)

    def _suffix_from_uri(self, source_uri: str) -> str:
        name = Path(urlparse(source_uri).path).name
        suffix = Path(name).suffix.lower()
        return suffix if suffix and len(suffix) <= 12 else ".bin"

    def _mark_schedule_retry(self, schedule: IngestionSchedule, error: str) -> None:
        schedule.retry_count += 1
        schedule.last_error = error
        if schedule.retry_count > schedule.retry_limit:
            schedule.status = "failed"
        else:
            schedule.status = "retrying"
            schedule.next_run_at = utcnow()

    def _next_schedule_run(self, cadence: str) -> Any:
        now = utcnow()
        seconds = {
            "manual": 0,
            "hourly": 3600,
            "daily": 86400,
            "weekly": 604800,
        }.get(cadence, 0)
        if seconds <= 0:
            return now
        return now + timedelta(seconds=seconds)

    def _job_document_id(self, market: str, raw: Mapping[str, Any], source_uri: str) -> str:
        if raw.get("document_id"):
            return str(raw["document_id"])
        if market == "U" and raw.get("accession_no"):
            primary_doc = str(raw.get("primary_doc", "index")).rsplit("/", maxsplit=1)[-1]
            base = f"sec_{str(raw['accession_no']).replace('-', '')}_{primary_doc}"
        elif market == "A":
            base = f"ashare_{raw.get('code', '')}_{raw.get('announcement_id', '')}"
        elif market == "H":
            base = f"hkex_{raw.get('stock_code', '')}_{raw.get('release_id', '')}"
        else:
            base = source_uri or new_id("document")
        return "doc_" + re.sub(r"[^A-Za-z0-9_-]+", "_", base).strip("_").lower()

    def _snippet(self, text: str, terms: list[str]) -> str:
        compact = re.sub(r"\s+", " ", text).strip()
        lowered = compact.lower()
        positions = [lowered.find(term) for term in terms if lowered.find(term) >= 0]
        if not positions:
            return compact[:220]
        start = max(0, min(positions) - 70)
        end = min(len(compact), start + 220)
        return compact[start:end]

    def _extract_terms(self, text: str, *, evidence: Evidence) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        lowered = text.lower()
        seen: set[tuple[str, str, int]] = set()
        for canonical, aliases in TERM_LEXICON.items():
            for alias in aliases:
                pattern = re.escape(alias)
                flags = re.IGNORECASE if alias.isascii() else 0
                for match in re.finditer(pattern, text if not alias.isascii() else lowered, flags=flags):
                    matched_text = text[match.start() : match.end()]
                    key = (canonical, matched_text.lower(), match.start())
                    if key in seen:
                        continue
                    seen.add(key)
                    results.append(
                        {
                            "term": matched_text,
                            "canonical": canonical,
                            "start": match.start(),
                            "end": match.end(),
                            "page_no": evidence.page_no,
                            "bbox": evidence.bbox,
                            "confidence": 0.86,
                        }
                    )
        return sorted(results, key=lambda item: (item["start"], item["canonical"]))

    def _extract_numbers(self, text: str, *, evidence: Evidence) -> list[dict[str, Any]]:
        number_pattern = r"(?P<amount>[+-]?\d+(?:,\d{3})*(?:\.\d+)?)(?P<unit>\s*(?:%|percent|percentage points|bps|万|亿|万元|亿元|million|billion|mn|bn|元|美元|港元|人民币)?)"
        results: list[dict[str, Any]] = []
        for match in re.finditer(number_pattern, text, flags=re.IGNORECASE):
            raw = match.group(0).strip()
            if not raw:
                continue
            amount = float(match.group("amount").replace(",", ""))
            unit = match.group("unit").strip()
            results.append(
                {
                    "raw": raw,
                    "value": amount,
                    "unit": unit,
                    "start": match.start(),
                    "end": match.end(),
                    "page_no": evidence.page_no,
                    "bbox": evidence.bbox,
                    "confidence": 0.84,
                }
            )
        return results

    def _extract_periods(self, text: str, *, evidence: Evidence) -> list[dict[str, Any]]:
        patterns = [
            r"\b20\d{2}\s*(?:fiscal\s*)?(?:year|FY|Q[1-4])\b",
            r"\b(?:FY)?20\d{2}\b",
            r"\b20\d{2}[-/](?:0?[1-9]|1[0-2])[-/](?:0?[1-9]|[12]\d|3[01])\b",
            r"20\d{2}年(?:第[一二三四1-4]季度|半年度|年度|年报)?",
        ]
        results: list[dict[str, Any]] = []
        seen: set[tuple[str, int]] = set()
        for pattern in patterns:
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                raw = match.group(0)
                key = (raw, match.start())
                if key in seen:
                    continue
                seen.add(key)
                results.append(
                    {
                        "raw": raw,
                        "start": match.start(),
                        "end": match.end(),
                        "page_no": evidence.page_no,
                        "bbox": evidence.bbox,
                        "confidence": 0.82,
                    }
                )
        return sorted(results, key=lambda item: item["start"])

    def _extract_tables(self, text: str, *, evidence: Evidence) -> list[dict[str, Any]]:
        rows = self._table_rows_from_text(text)
        if not rows:
            return []
        header = rows[0]
        data_rows = rows[1:] if len(rows) > 1 else []
        cells: list[dict[str, Any]] = []
        for row_index, row in enumerate(data_rows, start=1):
            for col_index, value in enumerate(row):
                column = header[col_index] if col_index < len(header) else f"col_{col_index + 1}"
                cells.append(
                    {
                        "row": row_index,
                        "column": column,
                        "value": value,
                        "page_no": evidence.page_no,
                        "bbox": f"{evidence.bbox};row={row_index};col={col_index + 1}",
                    }
                )
        if not cells:
            return []
        return [
            {
                "headers": header,
                "rows": data_rows,
                "cells": cells,
                "row_count": len(data_rows),
                "column_count": len(header),
                "page_no": evidence.page_no,
                "bbox": evidence.bbox,
                "confidence": 0.78,
            }
        ]

    def _table_rows_from_text(self, text: str) -> list[list[str]]:
        if looks_like_html(text):
            html_rows = re.findall(r"<tr[^>]*>(.*?)</tr>", text, flags=re.I | re.S)
            rows: list[list[str]] = []
            for row_html in html_rows:
                cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, flags=re.I | re.S)
                clean = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", cell)).strip() for cell in cells]
                if clean:
                    rows.append(clean)
            if rows:
                return rows
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        pipe_lines = [line for line in lines if "|" in line]
        if len(pipe_lines) >= 2:
            rows = []
            for line in pipe_lines:
                cells = [cell.strip() for cell in line.strip("|").split("|")]
                if cells and not all(re.fullmatch(r":?-{3,}:?", cell or "") for cell in cells):
                    rows.append(cells)
            return rows if len(rows) >= 2 else []
        tab_lines = [line for line in lines if "\t" in line]
        if len(tab_lines) >= 2:
            return [[cell.strip() for cell in line.split("\t")] for line in tab_lines]
        return []

    def _extraction_metrics(
        self,
        *,
        terms: list[dict[str, Any]],
        numbers: list[dict[str, Any]],
        periods: list[dict[str, Any]],
        tables: list[dict[str, Any]],
        expected_terms: set[str],
        expected_numbers: int,
        expected_periods: int,
        expected_tables: int,
    ) -> dict[str, float]:
        extracted_terms = {str(item["canonical"]) for item in terms}
        if expected_terms:
            matched_terms = len(extracted_terms & expected_terms)
            precision = matched_terms / max(1, len(extracted_terms))
            recall = matched_terms / max(1, len(expected_terms))
            f1 = 2 * precision * recall / max(precision + recall, 1e-9)
        else:
            precision = 1.0 if terms else 0.0
            recall = precision
            f1 = precision
        number_recall = min(1.0, len(numbers) / max(1, expected_numbers)) if expected_numbers else (1.0 if numbers else 0.0)
        period_recall = min(1.0, len(periods) / max(1, expected_periods)) if expected_periods else (1.0 if periods else 0.0)
        table_recall = min(1.0, len(tables) / max(1, expected_tables)) if expected_tables else (1.0 if tables else 0.0)
        table_cells = sum(len(table.get("cells", [])) for table in tables)
        located_items = terms + numbers + periods + tables
        evidence_locator_rate = 1.0 if all(item.get("page_no") and item.get("bbox") for item in located_items) and located_items else 0.0
        table_locator_rate = 1.0 if tables and all(cell.get("bbox") for table in tables for cell in table.get("cells", [])) else 0.0
        return {
            "term_precision": round(precision, 4),
            "term_recall": round(recall, 4),
            "term_f1": round(f1, 4),
            "number_recall": round(number_recall, 4),
            "period_recall": round(period_recall, 4),
            "table_recall": round(table_recall, 4),
            "table_cell_count": float(table_cells),
            "table_locator_rate": round(table_locator_rate, 4),
            "evidence_locator_rate": round(evidence_locator_rate, 4),
        }

    def _benchmark_sample_id(self, benchmark_id: str, document_id: str) -> str:
        raw = f"bms_{benchmark_id}_{document_id}"
        return re.sub(r"[^A-Za-z0-9_-]+", "_", raw).strip("_").lower()

    def _benchmark_sample_report(
        self,
        sample: BenchmarkSample,
        *,
        threshold: Mapping[str, float],
        min_confidence: float,
        actor: str,
    ) -> dict[str, Any]:
        evidence = [item for item in self.store.evidence.values() if item.document_id == sample.document_id]
        extraction_error = ""
        if not evidence:
            try:
                evidence = self.extract_evidence(sample.document_id, actor=actor, parser_version="benchmark-suite", model_version="rule-baseline")
            except ValidationError as exc:
                extraction_error = str(exc)
                evidence = []
        terms: list[dict[str, Any]] = []
        numbers: list[dict[str, Any]] = []
        periods: list[dict[str, Any]] = []
        tables: list[dict[str, Any]] = []
        for item in evidence:
            text = item.canonical_text or item.span_text
            terms.extend(self._extract_terms(text, evidence=item))
            numbers.extend(self._extract_numbers(text, evidence=item))
            periods.extend(self._extract_periods(text, evidence=item))
            tables.extend(self._extract_tables(text, evidence=item))
        metrics = self._extraction_metrics(
            terms=terms,
            numbers=numbers,
            periods=periods,
            tables=tables,
            expected_terms={str(item) for item in sample.expected_terms},
            expected_numbers=sample.expected_numbers,
            expected_periods=sample.expected_periods,
            expected_tables=sample.expected_tables,
        )
        expected_pages = set(sample.expected_pages)
        found_pages = {item.page_no for item in evidence if item.page_no}
        metrics["page_hit_rate"] = round(len(expected_pages & found_pages) / max(1, len(expected_pages)), 4) if expected_pages else (1.0 if found_pages else 0.0)
        avg_confidence = sum(item.confidence for item in evidence) / len(evidence) if evidence else 0.0
        metrics["avg_confidence"] = round(avg_confidence, 4)
        low_confidence = bool(evidence) and avg_confidence < min_confidence
        manual_review = any(item.document_id == sample.document_id and item.status == "open" for item in self.store.manual_reviews.values())
        metrics["low_confidence_sample"] = 1.0 if low_confidence else 0.0
        metrics["low_confidence_intercepted"] = 1.0 if low_confidence or manual_review else 0.0
        reasons: list[str] = []
        if extraction_error:
            reasons.append(f"extraction_failed:{extraction_error}")
        for key, value in threshold.items():
            metric_value = metrics.get(key)
            if isinstance(metric_value, (int, float)) and float(metric_value) < float(value):
                reasons.append(f"{key}<{value}")
        if low_confidence:
            reasons.append(f"avg_confidence<{min_confidence}")
        return {
            "sample_id": sample.sample_id,
            "document_id": sample.document_id,
            "language": sample.language,
            "metrics": metrics,
            "passed": not reasons,
            "reasons": reasons,
        }

    def _benchmark_aggregate_metrics(self, reports: list[dict[str, Any]]) -> dict[str, Any]:
        aggregate: dict[str, Any] = {"sample_count": len(reports)}
        numeric_keys = sorted(
            {
                key
                for report in reports
                for key, value in report["metrics"].items()
                if isinstance(value, (int, float))
            }
        )
        for key in numeric_keys:
            aggregate[key] = round(sum(float(report["metrics"].get(key, 0.0)) for report in reports) / max(1, len(reports)), 4)
        low_confidence_samples = sum(1 for report in reports if report["metrics"].get("low_confidence_sample", 0.0))
        intercepted = sum(1 for report in reports if report["metrics"].get("low_confidence_sample", 0.0) and report["metrics"].get("low_confidence_intercepted", 0.0))
        aggregate["low_confidence_intercept_rate"] = round(intercepted / max(1, low_confidence_samples), 4) if low_confidence_samples else 1.0
        aggregate["failed_sample_count"] = sum(1 for report in reports if not report["passed"])
        language_metrics: dict[str, dict[str, float]] = {}
        for language in sorted({str(report["language"]) for report in reports}):
            language_reports = [report for report in reports if report["language"] == language]
            language_metrics[language] = {
                key: round(sum(float(report["metrics"].get(key, 0.0)) for report in language_reports) / max(1, len(language_reports)), 4)
                for key in numeric_keys
            }
        aggregate["language_metrics"] = language_metrics
        return aggregate

    def _decision_state(self, pack: DecisionPack) -> str:
        roles = {signature.role for signature in pack.signatures}
        if "CEO" in roles and (not pack.risk_checks or "风险/合规" in roles):
            return "approved"
        if any(signature.role == "风险/合规" and pack.risk_checks for signature in pack.signatures):
            return "pending"
        return "pending"
