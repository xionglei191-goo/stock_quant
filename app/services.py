from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from .errors import ComplianceGateError, ConflictError, NotFoundError, PermissionDenied, ValidationError
from .connectors import ConnectorRegistry
from .document_parser import PaddleOCRParser
from .llm_gateway import LLMGateway
from .research_reports import cheap_fingerprint, content_sha256, infer_report_metadata, iter_report_files, report_id_for_path, safe_source_part
from .tdx_market_data import TDXMarketDataAdapter, TDXVipdocAdapter
from .models import (
    AuditEvent,
    AlertNotification,
    AlertRule,
    AStockConnectorDefinition,
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
    LineageEvent,
    LLMTaskRun,
    LLMTaskTemplate,
    ManualReviewItem,
    MarketDataPoint,
    ModelVersionRecord,
    OperatingReport,
    PortfolioProposal,
    PortfolioTransaction,
    PromptChangeRequest,
    ReadinessCheckRecord,
    ResearchAnswer,
    ResearchCard,
    ResearchReportAsset,
    ResearchTemplate,
    ResearchSignal,
    ReviewRecord,
    Security,
    ScorecardProfile,
    SourceDefinition,
    SourceReviewRecord,
    StrategyReplay,
    SystemAlert,
    ThesisCard,
    WorkflowDefinition,
    WorkflowRun,
)
from .object_store import create_object_store_from_env
from .search import LocalSearchIndex, LocalSemanticIndex, SearchRecord, create_search_index_from_env
from .store import InMemoryStore
from .utils import chunk_text, chunk_text_by_page, looks_like_html, new_id, parse_datetime, pdf_bytes_to_text, to_plain, utcnow


DEFAULT_SEC_USER_AGENT = "ai-native-quant-org/0.1 contact@example.com"
DEFAULT_HKEX_USER_AGENT = "ai-native-quant-org/0.1 contact@example.com"
PUBLIC_EOD_MARKET_DATA_SOURCE_ID = "public_eod_market_data"
LOCAL_RESEARCH_REPORT_SOURCE_ID = "local_research_reports"
MANUAL_TRANSCRIPT_REFERENCE_SOURCE_ID = "manual_reference_transcripts"
SOURCE_ID_ALIASES = {
    "authorized_eod_market_data": PUBLIC_EOD_MARKET_DATA_SOURCE_ID,
    "authorized_research_vendor": LOCAL_RESEARCH_REPORT_SOURCE_ID,
    "authorized_transcript_vendor": MANUAL_TRANSCRIPT_REFERENCE_SOURCE_ID,
}

TERM_LEXICON = {
    "revenue": ["revenue", "sales", "营业收入", "收入"],
    "net_profit": ["net profit", "profit attributable", "归母净利润", "净利润"],
    "gross_margin": ["gross margin", "毛利率"],
    "operating_cash_flow": ["operating cash flow", "经营活动现金流", "经营现金流"],
    "risk_factor": ["risk factor", "risk factors", "风险因素", "主要风险"],
}

SENSITIVE_TEXT_PATTERNS = [
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("cn_mobile", re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")),
    ("cn_id", re.compile(r"(?<!\d)\d{17}[\dXx](?!\w)")),
    (
        "secret_literal",
        re.compile(r"\b(api[_-]?key|access[_-]?token|bearer[_-]?token|secret|signature)\b\s*[:=]\s*['\"]?([A-Za-z0-9_\-./+=]{8,})", re.IGNORECASE),
    ),
]

READINESS_CHECKLIST_ITEMS = [
    {
        "check_id": "real_data_smoke_test",
        "label": "真实数据 smoke test",
        "owner_role": "平台负责人",
        "required": True,
    },
    {
        "check_id": "production_ui_screenshot_acceptance",
        "label": "生产 UI 截图验收",
        "owner_role": "平台负责人",
        "required": True,
    },
    {
        "check_id": "cross_browser_acceptance",
        "label": "跨浏览器验收",
        "owner_role": "平台负责人",
        "required": True,
    },
    {
        "check_id": "capacity_latency_report",
        "label": "容量和延迟报告",
        "owner_role": "平台负责人",
        "required": True,
    },
    {
        "check_id": "backup_restore_drill",
        "label": "备份恢复演练",
        "owner_role": "平台负责人",
        "required": True,
    },
    {
        "check_id": "permission_red_team_test",
        "label": "权限红队测试",
        "owner_role": "风险/合规",
        "required": True,
    },
    {
        "check_id": "compliance_review_record",
        "label": "合规复核记录",
        "owner_role": "风险/合规",
        "required": True,
    },
    {
        "check_id": "launch_checklist",
        "label": "上线 checklist",
        "owner_role": "CEO",
        "required": True,
    },
]


class SystemService:
    def __init__(self, store: InMemoryStore | None = None):
        self.store = store or InMemoryStore()
        self.connectors = ConnectorRegistry()
        self.llm_gateway = LLMGateway()
        self.document_parser = PaddleOCRParser()
        self.tdx_market_data = TDXMarketDataAdapter()
        self.tdx_vipdoc = TDXVipdocAdapter()
        self.object_store = create_object_store_from_env(Path.cwd() / "data" / "objects")
        self.search_index = create_search_index_from_env()
        self.local_search_index = LocalSearchIndex()
        self.semantic_index = LocalSemanticIndex()
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

    def register_llm_task_template(self, payload: Mapping[str, Any], *, actor: str = "system") -> LLMTaskTemplate:
        status = str(payload.get("status", "draft"))
        if status not in {"draft", "pending", "approved", "deprecated"}:
            raise ValidationError("LLM task template status must be draft, pending, approved, or deprecated")
        approved_change_id = str(payload.get("approved_prompt_change_id", "")).strip()
        if status == "approved":
            if not approved_change_id:
                raise ValidationError("approved LLM task template requires approved_prompt_change_id")
            change = self.store.prompt_changes.get(approved_change_id)
            if change is None or change.status != "approved":
                raise ValidationError("approved_prompt_change_id must reference an approved prompt change")
        template = LLMTaskTemplate(
            template_id=str(payload.get("template_id", new_id("llmtpl"))),
            task_type=str(payload["task_type"]),
            prompt_name=str(payload["prompt_name"]),
            prompt_version=str(payload.get("prompt_version") or approved_change_id or "draft"),
            content=str(payload.get("content", "")),
            provider=str(payload.get("provider", "openai")),
            model=str(payload.get("model", "")),
            status=status,
            approved_prompt_change_id=approved_change_id,
            fallback_chain=[str(item) for item in payload.get("fallback_chain", ["rule_summary", "manual_review"])],
            data_domains=[str(item) for item in payload.get("data_domains", [])],
            allowed_roles=[str(item) for item in payload.get("allowed_roles", [])],
            risk_level=str(payload.get("risk_level", "medium")),
            input_schema=dict(payload.get("input_schema", {})),
            output_schema=dict(payload.get("output_schema", {})),
            estimated_cost_per_1k_tokens=float(payload.get("estimated_cost_per_1k_tokens", 0.0)),
            max_latency_ms=int(payload.get("max_latency_ms", 30000)),
        )
        if template.provider not in {"openai", "anthropic"}:
            raise ValidationError("LLM task template provider must be openai or anthropic")
        if template.risk_level not in {"low", "medium", "high", "critical"}:
            raise ValidationError("LLM task template risk_level must be low, medium, high, or critical")
        if template.template_id in self.store.llm_task_templates:
            raise ConflictError(f"LLM task template {template.template_id} already exists")
        self.store.llm_task_templates[template.template_id] = template
        self._audit(
            actor,
            "register_llm_task_template",
            "llm_task_template",
            template.template_id,
            source="llm_gateway",
            version=template.prompt_version,
            prompt_version=template.prompt_version,
            approval_state=template.status,
        )
        return template

    def seed_default_llm_task_templates(self, *, actor: str = "system") -> list[LLMTaskTemplate]:
        defaults = [
            {
                "template_id": "llmtpl_research_summary_v1",
                "task_type": "research_summary",
                "prompt_name": "research-summary",
                "content": "请基于以下公开披露或本地参考材料生成中文研究摘要，并保留英文原文引用线索。\n\n{{source_text}}",
                "data_domains": ["public_filing", "local_research_reference"],
                "allowed_roles": ["分析师", "海外研究负责人", "CIO", "风险/合规"],
                "risk_level": "medium",
                "fallback_chain": ["rule_summary", "manual_review"],
            },
            {
                "template_id": "llmtpl_filing_qa_v1",
                "task_type": "filing_qa",
                "prompt_name": "filing-qa",
                "content": "你是英文披露文件研究助手。问题：{{question}}\n\n英文原文证据：\n{{source_text}}",
                "data_domains": ["public_filing"],
                "allowed_roles": ["分析师", "海外研究负责人", "CIO"],
                "risk_level": "medium",
                "fallback_chain": ["rule_summary", "manual_review"],
            },
            {
                "template_id": "llmtpl_challenger_v1",
                "task_type": "challenger",
                "prompt_name": "challenger",
                "content": "请作为反方研究员，找出该投资假设的关键反证和需要人工复核的弱点。\n\n假设：{{hypothesis}}\n证据：{{source_text}}",
                "data_domains": ["public_filing", "public_market_data"],
                "allowed_roles": ["CIO", "风险/合规", "PM", "分析师"],
                "risk_level": "high",
                "fallback_chain": ["rule_summary", "manual_review"],
            },
            {
                "template_id": "llmtpl_incident_rca_v1",
                "task_type": "incident_rca",
                "prompt_name": "incident-rca",
                "content": "根据事故记录生成 RCA 草稿，必须区分事实、推断和待确认项。\n\n{{incident_context}}",
                "data_domains": ["audit", "ops"],
                "allowed_roles": ["平台负责人", "风险/合规", "CEO"],
                "risk_level": "high",
                "fallback_chain": ["rule_summary", "manual_review"],
            },
        ]
        created: list[LLMTaskTemplate] = []
        for item in defaults:
            if item["template_id"] in self.store.llm_task_templates:
                created.append(self.store.llm_task_templates[item["template_id"]])
                continue
            change_id = f"pr_{item['template_id']}_baseline"
            if change_id not in self.store.prompt_changes:
                self.create_prompt_change(
                    {
                        "request_id": change_id,
                        "prompt_name": item["prompt_name"],
                        "change_level": "baseline",
                        "requested_by": actor,
                        "content": item["content"],
                    },
                    actor=actor,
                )
                self.approve_prompt_change(change_id, actor=actor, approved=True)
            created.append(
                self.register_llm_task_template(
                    {
                        **item,
                        "status": "approved",
                        "approved_prompt_change_id": change_id,
                        "prompt_version": change_id,
                    },
                    actor=actor,
                )
            )
        return created

    def llm_task_templates_payload(self, filters: Mapping[str, Any] | None = None) -> dict[str, Any]:
        filters = filters or {}
        task_type = str(filters.get("task_type", "")).strip()
        status = str(filters.get("status", "")).strip()
        limit = self._bounded_limit(filters.get("limit", 100), max_value=1000)
        templates = list(self.store.llm_task_templates.values())
        if task_type:
            templates = [item for item in templates if item.task_type == task_type]
        if status:
            templates = [item for item in templates if item.status == status]
        templates = sorted(templates, key=lambda item: item.updated_at, reverse=True)[:limit]
        return {"templates": [to_plain(item) for item in templates], "total": len(templates)}

    def run_llm_task(self, payload: Mapping[str, Any], *, actor: str = "system") -> LLMTaskRun:
        template_id = str(payload["template_id"])
        template = self.store.llm_task_templates.get(template_id)
        if template is None:
            raise NotFoundError(f"LLM task template {template_id} not found")
        if template.status != "approved" and not bool(payload.get("allow_unapproved", False)):
            raise ComplianceGateError("LLM task template must be approved before production use")
        caller_role = str(payload.get("role", "")).strip()
        if template.allowed_roles and caller_role and caller_role not in template.allowed_roles:
            raise PermissionDenied(f"role {caller_role} is not allowed for LLM task template {template_id}")
        variables = dict(payload.get("variables", {}))
        rendered_prompt = self._render_llm_prompt(template.content, variables)
        provider = str(payload.get("provider", template.provider))
        model = str(payload.get("model") or template.model or self.llm_gateway.default_model)
        previous_output = payload.get("previous_output")
        started = time.monotonic()
        run_id = str(payload.get("run_id", new_id("llmrun")))
        output: dict[str, Any] = {}
        error = ""
        fallback_used = ""
        status = "succeeded"
        try:
            if provider == "openai":
                response = self.llm_gateway.openai_chat_completions(self._openai_task_payload(payload, rendered_prompt, model=model))
            elif provider == "anthropic":
                response = self.llm_gateway.anthropic_messages(self._anthropic_task_payload(payload, rendered_prompt, model=model))
            else:
                raise ValidationError("LLM task provider must be openai or anthropic")
            output = {"mode": "llm", "response": response["response"]}
        except Exception as exc:
            error = str(exc)
            status, fallback_used, output = self._llm_task_fallback(
                template,
                rendered_prompt,
                previous_output=previous_output,
                error=error,
            )
        latency_ms = max(0, int((time.monotonic() - started) * 1000))
        output_text = self._llm_output_text(output)
        input_tokens = self._estimate_tokens(rendered_prompt)
        output_tokens = self._estimate_tokens(output_text)
        estimated_cost = round((input_tokens + output_tokens) / 1000 * template.estimated_cost_per_1k_tokens, 6)
        human_review_required = template.risk_level in {"high", "critical"} or fallback_used in {"manual_review", "rule_summary", "previous_stable"} or bool(payload.get("human_review_required", False))
        run = LLMTaskRun(
            run_id=run_id,
            template_id=template.template_id,
            task_type=template.task_type,
            status=status,
            provider=provider,
            model=model,
            prompt_version=template.prompt_version,
            input_summary=self._summarize_text(rendered_prompt),
            output=output,
            fallback_used=fallback_used,
            latency_ms=latency_ms,
            estimated_input_tokens=input_tokens,
            estimated_output_tokens=output_tokens,
            estimated_cost=estimated_cost,
            error=error,
            human_review_required=human_review_required,
        )
        if run.run_id in self.store.llm_task_runs:
            raise ConflictError(f"LLM task run {run.run_id} already exists")
        self.store.llm_task_runs[run.run_id] = run
        self._audit(
            actor,
            "run_llm_task",
            "llm_task_run",
            run.run_id,
            source="llm_gateway",
            version=template.prompt_version,
            model_version=model,
            prompt_version=template.prompt_version,
            approval_state=status,
        )
        return run

    def llm_task_runs_payload(self, filters: Mapping[str, Any] | None = None) -> dict[str, Any]:
        filters = filters or {}
        task_type = str(filters.get("task_type", "")).strip()
        status = str(filters.get("status", "")).strip()
        limit = self._bounded_limit(filters.get("limit", 100), max_value=1000)
        runs = list(self.store.llm_task_runs.values())
        if task_type:
            runs = [item for item in runs if item.task_type == task_type]
        if status:
            runs = [item for item in runs if item.status == status]
        runs = sorted(runs, key=lambda item: item.created_at, reverse=True)[:limit]
        return {"runs": [to_plain(item) for item in runs], "total": len(runs)}

    def llm_task_metrics(self) -> dict[str, Any]:
        runs = list(self.store.llm_task_runs.values())
        failed = [item for item in runs if item.status != "succeeded"]
        fallbacks = [item for item in runs if item.fallback_used]
        review_required = [item for item in runs if item.human_review_required]
        avg_latency = round(sum(item.latency_ms for item in runs) / max(1, len(runs)), 2)
        total_cost = round(sum(item.estimated_cost for item in runs), 6)
        cost_budget = float(os.environ.get("AI_QUANT_LLM_COST_BUDGET", "10") or 10)
        error_rate = round(len(failed) / max(1, len(runs)), 4) if runs else 0.0
        return {
            "templates": len(self.store.llm_task_templates),
            "approved_templates": sum(1 for item in self.store.llm_task_templates.values() if item.status == "approved"),
            "runs": len(runs),
            "failed_runs": len(failed),
            "error_rate": error_rate,
            "fallback_runs": len(fallbacks),
            "human_review_required": len(review_required),
            "avg_latency_ms": avg_latency,
            "estimated_cost": total_cost,
            "cost_budget": cost_budget,
            "cost_budget_used": round(total_cost / max(0.000001, cost_budget), 4),
        }

    def _render_llm_prompt(self, template: str, variables: Mapping[str, Any]) -> str:
        rendered = template
        for key, value in variables.items():
            rendered = rendered.replace("{{" + str(key) + "}}", str(value))
            rendered = rendered.replace("{{ " + str(key) + " }}", str(value))
        unresolved = re.findall(r"\{\{\s*([A-Za-z0-9_.-]+)\s*\}\}", rendered)
        if unresolved:
            raise ValidationError(f"missing LLM prompt variables: {sorted(set(unresolved))}")
        if not rendered.strip():
            raise ValidationError("rendered LLM prompt is empty")
        return rendered

    def _openai_task_payload(self, payload: Mapping[str, Any], prompt: str, *, model: str) -> dict[str, Any]:
        body = dict(payload.get("llm_payload", {}))
        body.setdefault("model", model)
        body.setdefault("temperature", float(payload.get("temperature", 0.2)))
        body.setdefault("messages", [{"role": "user", "content": prompt}])
        return body

    def _anthropic_task_payload(self, payload: Mapping[str, Any], prompt: str, *, model: str) -> dict[str, Any]:
        body = dict(payload.get("llm_payload", {}))
        body.setdefault("model", model)
        body.setdefault("max_tokens", int(payload.get("max_tokens", 1024)))
        body.setdefault("messages", [{"role": "user", "content": prompt}])
        return body

    def _llm_task_fallback(
        self,
        template: LLMTaskTemplate,
        prompt: str,
        *,
        previous_output: Any,
        error: str,
    ) -> tuple[str, str, dict[str, Any]]:
        for fallback in template.fallback_chain:
            if fallback == "previous_stable" and previous_output:
                return "fallback", "previous_stable", {"mode": "previous_stable", "response": previous_output, "needs_review": True}
            if fallback == "rule_summary":
                return "fallback", "rule_summary", {"mode": "rule_summary", "summary": self._rule_summary(prompt), "needs_review": True, "upstream_error": error}
            if fallback == "manual_review":
                return "needs_review", "manual_review", {"mode": "manual_review", "needs_review": True, "upstream_error": error}
        return "failed", "", {"mode": "failed", "needs_review": True, "upstream_error": error}

    def _rule_summary(self, text: str) -> str:
        normalized = " ".join(text.split())
        if len(normalized) <= 260:
            return normalized
        return normalized[:257].rstrip() + "..."

    def _llm_output_text(self, output: Mapping[str, Any]) -> str:
        if "summary" in output:
            return str(output["summary"])
        response = output.get("response")
        if isinstance(response, Mapping):
            choices = response.get("choices")
            if isinstance(choices, list) and choices:
                message = choices[0].get("message") if isinstance(choices[0], Mapping) else None
                if isinstance(message, Mapping):
                    return str(message.get("content", ""))
            content = response.get("content")
            if isinstance(content, list) and content:
                first = content[0]
                if isinstance(first, Mapping):
                    return str(first.get("text", ""))
            return str(response)[:2000]
        return str(output)[:2000]

    def _estimate_tokens(self, text: str) -> int:
        if not text:
            return 0
        return max(1, int(len(text) / 4))

    def _summarize_text(self, text: str) -> str:
        normalized = " ".join(text.split())
        return normalized[:300]

    def register_workflow_definition(self, payload: Mapping[str, Any], *, actor: str = "system") -> WorkflowDefinition:
        tasks = [dict(item) for item in payload.get("tasks", [])]
        if not tasks:
            raise ValidationError("workflow definition requires at least one task")
        missing_task_ids = [index for index, item in enumerate(tasks) if not str(item.get("task_id", "")).strip()]
        if missing_task_ids:
            raise ValidationError(f"workflow tasks missing task_id at positions: {missing_task_ids}")
        workflow = WorkflowDefinition(
            dag_id=str(payload.get("dag_id", new_id("dag"))),
            name=str(payload["name"]),
            tasks=tasks,
            cadence=str(payload.get("cadence", "manual")),
            owner_role=str(payload.get("owner_role", "平台负责人")),
            status=str(payload.get("status", "active")),
            idempotency_key_fields=[str(item) for item in payload.get("idempotency_key_fields", [])],
            description=str(payload.get("description", "")),
        )
        if workflow.status not in {"active", "paused", "deprecated"}:
            raise ValidationError("workflow status must be active, paused, or deprecated")
        if workflow.dag_id in self.store.workflow_definitions:
            raise ConflictError(f"workflow definition {workflow.dag_id} already exists")
        self.store.workflow_definitions[workflow.dag_id] = workflow
        self._audit(actor, "register_workflow_definition", "workflow_definition", workflow.dag_id, approval_state=workflow.status)
        return workflow

    def run_workflow_definition(self, dag_id: str, payload: Mapping[str, Any], *, actor: str = "system") -> WorkflowRun:
        workflow = self.store.workflow_definitions.get(dag_id)
        if workflow is None:
            raise NotFoundError(f"workflow definition {dag_id} not found")
        if workflow.status != "active" and not bool(payload.get("allow_inactive", False)):
            raise ComplianceGateError("workflow definition must be active before run")
        inputs = dict(payload.get("inputs", {}))
        idempotency_key = str(payload.get("idempotency_key", "")).strip() or self._workflow_idempotency_key(workflow, inputs)
        if not bool(payload.get("force", False)):
            existing = next((item for item in self.store.workflow_runs.values() if item.dag_id == dag_id and item.idempotency_key == idempotency_key), None)
            if existing:
                return existing
        task_statuses = {str(task["task_id"]): "succeeded" for task in workflow.tasks}
        task_overrides = payload.get("task_statuses", {})
        if isinstance(task_overrides, Mapping):
            task_statuses.update({str(key): str(value) for key, value in task_overrides.items() if str(key) in task_statuses})
        output_refs = [str(item) for item in payload.get("output_refs", [])]
        run = WorkflowRun(
            run_id=str(payload.get("run_id", new_id("wfrun"))),
            dag_id=dag_id,
            status=str(payload.get("status", "succeeded")),
            idempotency_key=idempotency_key,
            inputs=inputs,
            task_statuses=task_statuses,
            output_refs=output_refs,
            error=str(payload.get("error", "")),
        )
        if run.status not in {"queued", "running", "succeeded", "failed", "needs_review"}:
            raise ValidationError("workflow run status must be queued, running, succeeded, failed, or needs_review")
        if run.run_id in self.store.workflow_runs:
            raise ConflictError(f"workflow run {run.run_id} already exists")
        self.store.workflow_runs[run.run_id] = run
        self._audit(actor, "run_workflow_definition", "workflow_run", run.run_id, version=workflow.dag_id, approval_state=run.status)
        return run

    def retry_workflow_run(self, run_id: str, payload: Mapping[str, Any] | None = None, *, actor: str = "system") -> WorkflowRun:
        payload = payload or {}
        failed_run = self.store.workflow_runs.get(run_id)
        if failed_run is None:
            raise NotFoundError(f"workflow run {run_id} not found")
        if failed_run.status not in {"failed", "needs_review"} and not bool(payload.get("force", False)):
            raise ComplianceGateError("only failed or needs_review workflow runs can be retried without force")
        retry_inputs = dict(failed_run.inputs)
        retry_inputs.update(dict(payload.get("inputs", {})))
        retry_payload = {
            "run_id": str(payload.get("run_id", new_id("wfrun_retry"))),
            "inputs": retry_inputs,
            "idempotency_key": str(payload.get("idempotency_key", f"{failed_run.idempotency_key}:retry:{new_id('retry')}")),
            "force": True,
            "status": str(payload.get("status", "succeeded")),
            "output_refs": [str(item) for item in payload.get("output_refs", failed_run.output_refs)],
        }
        if "task_statuses" in payload:
            retry_payload["task_statuses"] = payload["task_statuses"]
        retry = self.run_workflow_definition(failed_run.dag_id, retry_payload, actor=actor)
        retry.inputs["retry_of"] = failed_run.run_id
        retry.inputs["retry_error"] = failed_run.error
        self._audit(actor, "retry_workflow_run", "workflow_run", retry.run_id, version=failed_run.dag_id, approval_state=retry.status)
        return retry

    def workflow_runs_payload(self, filters: Mapping[str, Any] | None = None) -> dict[str, Any]:
        filters = filters or {}
        dag_id = str(filters.get("dag_id", "")).strip()
        status = str(filters.get("status", "")).strip()
        limit = self._bounded_limit(filters.get("limit", 100), max_value=1000)
        runs = list(self.store.workflow_runs.values())
        if dag_id:
            runs = [item for item in runs if item.dag_id == dag_id]
        if status:
            runs = [item for item in runs if item.status == status]
        runs = sorted(runs, key=lambda item: item.started_at, reverse=True)[:limit]
        return {"runs": [to_plain(item) for item in runs], "total": len(runs)}

    def prompt_changes_payload(self, filters: Mapping[str, Any] | None = None) -> dict[str, Any]:
        filters = filters or {}
        status = str(filters.get("status", "")).strip()
        prompt_name = str(filters.get("prompt_name", "")).strip()
        limit = self._bounded_limit(filters.get("limit", 100), max_value=1000)
        changes = list(self.store.prompt_changes.values())
        if status:
            changes = [item for item in changes if item.status == status]
        if prompt_name:
            changes = [item for item in changes if item.prompt_name == prompt_name]
        changes.sort(key=lambda item: item.created_at, reverse=True)
        return {"changes": [to_plain(item) for item in changes[:limit]], "total": len(changes)}

    def workflow_definitions_payload(self, filters: Mapping[str, Any] | None = None) -> dict[str, Any]:
        filters = filters or {}
        status = str(filters.get("status", "")).strip()
        limit = self._bounded_limit(filters.get("limit", 100), max_value=1000)
        definitions = list(self.store.workflow_definitions.values())
        if status:
            definitions = [item for item in definitions if item.status == status]
        definitions = sorted(definitions, key=lambda item: item.updated_at, reverse=True)[:limit]
        return {"workflows": [to_plain(item) for item in definitions], "total": len(definitions)}

    def record_lineage_event(self, payload: Mapping[str, Any], *, actor: str = "system") -> LineageEvent:
        job_run_id = str(payload["job_run_id"])
        if job_run_id not in self.store.workflow_runs and bool(payload.get("require_workflow_run", True)):
            raise NotFoundError(f"workflow run {job_run_id} not found")
        event = LineageEvent(
            lineage_id=str(payload.get("lineage_id", new_id("lin"))),
            job_run_id=job_run_id,
            dataset=str(payload["dataset"]),
            input_refs=[str(item) for item in payload.get("input_refs", [])],
            output_refs=[str(item) for item in payload.get("output_refs", [])],
            code_version=str(payload.get("code_version", "")),
            model_versions=[str(item) for item in payload.get("model_versions", [])],
            prompt_versions=[str(item) for item in payload.get("prompt_versions", [])],
        )
        if event.lineage_id in self.store.lineage_events:
            raise ConflictError(f"lineage event {event.lineage_id} already exists")
        self.store.lineage_events[event.lineage_id] = event
        self._audit(actor, "record_lineage_event", "lineage_event", event.lineage_id, version=event.code_version)
        return event

    def lineage_events_payload(self, filters: Mapping[str, Any] | None = None) -> dict[str, Any]:
        filters = filters or {}
        job_run_id = str(filters.get("job_run_id", "")).strip()
        dataset = str(filters.get("dataset", "")).strip()
        limit = self._bounded_limit(filters.get("limit", 100), max_value=1000)
        events = list(self.store.lineage_events.values())
        if job_run_id:
            events = [item for item in events if item.job_run_id == job_run_id]
        if dataset:
            events = [item for item in events if item.dataset == dataset]
        events = sorted(events, key=lambda item: item.created_at, reverse=True)[:limit]
        return {"lineage_events": [to_plain(item) for item in events], "total": len(events)}

    def register_model_version(self, payload: Mapping[str, Any], *, actor: str = "system") -> ModelVersionRecord:
        record = ModelVersionRecord(
            model_version_id=str(payload.get("model_version_id", new_id("modelv"))),
            model_name=str(payload["model_name"]),
            version=str(payload["version"]),
            model_type=str(payload.get("model_type", "llm")),
            artifact_uri=str(payload.get("artifact_uri", "")),
            training_dataset_ids=[str(item) for item in payload.get("training_dataset_ids", [])],
            prompt_versions=[str(item) for item in payload.get("prompt_versions", [])],
            metrics=dict(payload.get("metrics", {})),
            status=str(payload.get("status", "candidate")),
        )
        if record.status not in {"candidate", "approved", "deprecated", "rolled_back"}:
            raise ValidationError("model version status must be candidate, approved, deprecated, or rolled_back")
        if record.model_version_id in self.store.model_versions:
            raise ConflictError(f"model version {record.model_version_id} already exists")
        self.store.model_versions[record.model_version_id] = record
        self._audit(actor, "register_model_version", "model_version", record.model_version_id, model_version=record.version, approval_state=record.status)
        return record

    def model_versions_payload(self, filters: Mapping[str, Any] | None = None) -> dict[str, Any]:
        filters = filters or {}
        model_name = str(filters.get("model_name", "")).strip()
        status = str(filters.get("status", "")).strip()
        limit = self._bounded_limit(filters.get("limit", 100), max_value=1000)
        records = list(self.store.model_versions.values())
        if model_name:
            records = [item for item in records if item.model_name == model_name]
        if status:
            records = [item for item in records if item.status == status]
        records = sorted(records, key=lambda item: item.created_at, reverse=True)[:limit]
        return {"model_versions": [to_plain(item) for item in records], "total": len(records)}

    def _workflow_idempotency_key(self, workflow: WorkflowDefinition, inputs: Mapping[str, Any]) -> str:
        if workflow.idempotency_key_fields:
            material = {field: inputs.get(field) for field in workflow.idempotency_key_fields}
        else:
            material = inputs
        raw = json.dumps(to_plain(material), ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(f"{workflow.dag_id}:{raw}".encode("utf-8")).hexdigest()[:24]

    def parse_document_with_paddleocr(self, payload: Mapping[str, Any], *, actor: str = "system") -> dict[str, Any]:
        optional_payload = self._document_parser_optional_payload(payload)
        document_id = str(payload.get("document_id", "")).strip()
        file_url = str(payload.get("file_url") or payload.get("fileUrl") or "").strip()
        if document_id:
            document = self.store.documents.get(document_id)
            if document is None:
                raise NotFoundError(f"document {document_id} not found")
            result = self._parse_document_with_paddleocr(document, optional_payload=optional_payload)
            resource_id = document_id
        elif file_url:
            result = self.document_parser.parse_url(file_url, optional_payload=optional_payload)
            resource_id = file_url
        else:
            raise ValidationError("document parser requires document_id or file_url")
        self._audit(
            actor,
            "parse_document_with_paddleocr",
            "document_parser",
            resource_id,
            source="paddleocr",
            version=str(result.get("job_id", "")),
            model_version=str(result.get("model", "")),
        )
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
        canonical_source_id = self._canonical_source_id(source.source_id)
        if canonical_source_id != source.source_id:
            source = replace(source, source_id=canonical_source_id)
        self._normalize_source_governance(source)
        if source.source_id in self.store.sources:
            raise ConflictError(f"source {source.source_id} already exists")
        self.store.sources[source.source_id] = source
        self._audit(actor, "register_source", "source", source.source_id, source=source.source_type, version=source.rights_tag.license_class)
        return source

    def update_source_governance(self, source_id: str, payload: Mapping[str, Any], *, actor: str = "system") -> SourceDefinition:
        source_id = self._canonical_source_id(source_id)
        source = self.store.sources.get(source_id)
        if source is None:
            raise NotFoundError(f"source {source_id} not found")
        if "field_whitelist" in payload:
            source.field_whitelist = [str(item) for item in payload.get("field_whitelist", [])]
        if "retention_policy" in payload:
            source.retention_policy = str(payload.get("retention_policy", ""))
        if "cache_ttl_days" in payload:
            source.cache_ttl_days = int(payload.get("cache_ttl_days", 0))
        if "provenance_ref" in payload or "contract_ref" in payload:
            provenance_ref = str(payload.get("provenance_ref", payload.get("contract_ref", "")))
            source.provenance_ref = provenance_ref
        if "usage_scope" in payload or "commercial_scope" in payload:
            usage_scope = str(payload.get("usage_scope", payload.get("commercial_scope", "")))
            source.usage_scope = usage_scope
        if "collection_method" in payload:
            source.collection_method = str(payload.get("collection_method", ""))
        if "robots_policy" in payload:
            source.robots_policy = str(payload.get("robots_policy", ""))
        if "last_reviewed_at" in payload:
            source.last_reviewed_at = parse_datetime(payload.get("last_reviewed_at"))
        if "review_cadence" in payload:
            source.review_cadence = str(payload.get("review_cadence", "quarterly"))
        if "review_owner" in payload:
            source.review_owner = str(payload.get("review_owner", ""))
        if "review_owner_role" in payload:
            source.review_owner_role = str(payload.get("review_owner_role", ""))
        if "source_tos_uri" in payload:
            source.source_tos_uri = str(payload.get("source_tos_uri", ""))
        if "risk_level" in payload:
            source.risk_level = str(payload.get("risk_level", source.risk_level))
        self._normalize_source_governance(source, preserve_existing=True)
        self._audit(actor, "update_source_governance", "source", source.source_id, source=source.source_type, version=source.rights_tag.license_class, approval_state=source.risk_level)
        return source

    def record_source_review(self, source_id: str, payload: Mapping[str, Any], *, actor: str = "system") -> SourceReviewRecord:
        source_id = self._canonical_source_id(source_id)
        source = self.store.sources.get(source_id)
        if source is None:
            raise NotFoundError(f"source {source_id} not found")
        reviewed_at = parse_datetime(payload.get("reviewed_at")) if payload.get("reviewed_at") else utcnow()
        review_period = str(payload.get("review_period") or self._review_period(reviewed_at))
        next_review_due_at = parse_datetime(payload.get("next_review_due_at")) if payload.get("next_review_due_at") else self._next_source_review_due_at(reviewed_at, source.review_cadence)
        review = SourceReviewRecord(
            review_id=str(payload.get("review_id", new_id("srrev"))),
            source_id=source_id,
            reviewer=str(payload.get("reviewer") or actor),
            reviewed_at=reviewed_at,
            review_period=review_period,
            status=str(payload.get("status", "approved")),
            publicness_status=str(payload.get("publicness_status", "confirmed_public_or_local")),
            tos_status=str(payload.get("tos_status", "reviewed")),
            robots_status=str(payload.get("robots_status", "reviewed_or_not_applicable")),
            usage_scope_status=str(payload.get("usage_scope_status", "within_boundary")),
            notes=str(payload.get("notes", "")),
            findings=[str(item) for item in payload.get("findings", [])],
            next_review_due_at=next_review_due_at,
        )
        if review.review_id in self.store.source_reviews:
            raise ConflictError(f"source review {review.review_id} already exists")
        self.store.source_reviews[review.review_id] = review
        source.last_reviewed_at = review.reviewed_at
        self._audit(
            actor,
            "record_source_review",
            "source_review",
            review.review_id,
            source=source.source_type,
            version=source.rights_tag.license_class,
            approval_state=review.status,
        )
        return review

    def source_reviews_payload(self, filters: Mapping[str, Any] | None = None) -> dict[str, Any]:
        filters = filters or {}
        source_id = self._canonical_source_id(str(filters.get("source_id", "")).strip()) if filters.get("source_id") else ""
        status = str(filters.get("status", "")).strip()
        due_before = parse_datetime(filters.get("due_before")) if filters.get("due_before") else None
        limit = self._bounded_limit(filters.get("limit", 100), 1000)
        reviews = list(self.store.source_reviews.values())
        if source_id:
            reviews = [review for review in reviews if review.source_id == source_id]
        if status:
            reviews = [review for review in reviews if review.status == status]
        if due_before:
            reviews = [review for review in reviews if review.next_review_due_at and review.next_review_due_at <= due_before]
        reviews.sort(key=lambda item: (item.reviewed_at, item.review_id), reverse=True)
        return {"total": len(reviews), "reviews": [to_plain(item) for item in reviews[:limit]]}

    def source_review_reminders_payload(self, filters: Mapping[str, Any] | None = None) -> dict[str, Any]:
        filters = filters or {}
        as_of = parse_datetime(filters.get("as_of")) if filters.get("as_of") else utcnow()
        due_within_days = max(0, int(filters.get("due_within_days", 30)))
        due_before = parse_datetime(filters.get("due_before")) if filters.get("due_before") else as_of + timedelta(days=due_within_days)
        owner = str(filters.get("owner", "")).strip()
        owner_role = str(filters.get("owner_role", "")).strip()
        source_type = str(filters.get("source_type", "")).strip()
        risk_level = str(filters.get("risk_level", "")).strip()
        include_blocked = self._truthy(filters.get("include_blocked", True))
        limit = self._bounded_limit(filters.get("limit", 100), 1000)
        rows = self._source_review_reminder_rows(as_of=as_of, due_before=due_before)
        if owner:
            rows = [row for row in rows if row["review_owner"] == owner]
        if owner_role:
            rows = [row for row in rows if row["review_owner_role"] == owner_role]
        if source_type:
            rows = [row for row in rows if row["source_type"] == source_type]
        if risk_level:
            rows = [row for row in rows if row["risk_level"] == risk_level]
        if not include_blocked:
            rows = [row for row in rows if not row["blocked_reasons"]]
        owner_board: dict[str, dict[str, Any]] = {}
        for row in rows:
            key = row["review_owner"] or row["review_owner_role"] or "未分配"
            board_row = owner_board.setdefault(
                key,
                {
                    "owner": row["review_owner"],
                    "owner_role": row["review_owner_role"],
                    "total": 0,
                    "overdue": 0,
                    "due_soon": 0,
                    "missing_review": 0,
                    "blocked": 0,
                    "source_ids": [],
                },
            )
            board_row["total"] += 1
            if row["status"] == "overdue":
                board_row["overdue"] += 1
            elif row["status"] == "due_soon":
                board_row["due_soon"] += 1
            if row["missing_review"]:
                board_row["missing_review"] += 1
            if row["blocked_reasons"]:
                board_row["blocked"] += 1
            board_row["source_ids"].append(row["source_id"])
        owner_rows = sorted(owner_board.values(), key=lambda item: (-int(item["overdue"]), -int(item["due_soon"]), str(item["owner_role"]), str(item["owner"])))
        rows.sort(key=lambda item: (item["due_at"] or "", item["source_id"]))
        return {
            "as_of": to_plain(as_of),
            "due_before": to_plain(due_before),
            "total": len(rows),
            "overdue": sum(1 for row in rows if row["status"] == "overdue"),
            "due_soon": sum(1 for row in rows if row["status"] == "due_soon"),
            "missing_review": sum(1 for row in rows if row["missing_review"]),
            "owner_board": owner_rows,
            "reminders": rows[:limit],
        }

    def source_governance_report(self, filters: Mapping[str, Any] | None = None) -> dict[str, Any]:
        filters = filters or {}
        risk_level = str(filters.get("risk_level", "")).strip()
        source_type = str(filters.get("source_type", "")).strip()
        sources = list(self.store.sources.values())
        if risk_level:
            sources = [source for source in sources if source.risk_level == risk_level]
        if source_type:
            sources = [source for source in sources if source.source_type == source_type]
        rows: list[dict[str, Any]] = []
        covered = 0
        automation_ready = 0
        reviewed_sources = 0
        review_overdue = 0
        reviews_by_source: dict[str, list[SourceReviewRecord]] = {}
        for review in self.store.source_reviews.values():
            reviews_by_source.setdefault(review.source_id, []).append(review)
        for source in sorted(sources, key=lambda item: item.source_id):
            gaps = self._source_governance_gaps(source)
            blocked_reasons = list(gaps)
            if source.risk_level == "red":
                blocked_reasons.append("red_source_manual_reference_only")
            source_reviews = sorted(reviews_by_source.get(source.source_id, []), key=lambda item: (item.reviewed_at, item.review_id), reverse=True)
            latest_review = source_reviews[0] if source_reviews else None
            if latest_review:
                reviewed_sources += 1
                if self._source_review_overdue(latest_review):
                    review_overdue += 1
                blocked_reasons.extend(self._source_review_blockers(latest_review))
            is_automation_ready = not blocked_reasons
            if not gaps:
                covered += 1
            if is_automation_ready:
                automation_ready += 1
            rows.append(
                {
                    "source_id": source.source_id,
                    "source_type": source.source_type,
                    "risk_level": source.risk_level,
                    "license_class": source.rights_tag.license_class,
                    "retention_policy": source.retention_policy,
                    "cache_ttl_days": source.cache_ttl_days,
                    "usage_scope": source.usage_scope,
                    "field_whitelist": list(source.field_whitelist),
                    "provenance_ref": source.provenance_ref,
                    "collection_method": source.collection_method,
                    "robots_policy": source.robots_policy,
                    "last_reviewed_at": to_plain(source.last_reviewed_at),
                    "review_cadence": source.review_cadence,
                    "review_owner": self._source_review_owner(source),
                    "review_owner_role": self._source_review_owner_role(source),
                    "latest_review": to_plain(latest_review) if latest_review else None,
                    "review_count": len(source_reviews),
                    "review_overdue": self._source_review_overdue(latest_review) if latest_review else False,
                    "source_tos_uri": source.source_tos_uri,
                    "automation_ready": is_automation_ready,
                    "blocked_reasons": blocked_reasons,
                    "gaps": gaps,
                }
            )
        return {
            "total": len(rows),
            "covered": covered,
            "automation_ready": automation_ready,
            "reviewed_sources": reviewed_sources,
            "review_coverage": round(reviewed_sources / max(1, len(rows)), 4) if rows else 1.0,
            "review_overdue": review_overdue,
            "coverage": round(covered / max(1, len(rows)), 4) if rows else 1.0,
            "automation_ready_coverage": round(automation_ready / max(1, len(rows)), 4) if rows else 1.0,
            "sources": rows,
        }

    def audit_completeness_report(self, filters: Mapping[str, Any] | None = None) -> dict[str, Any]:
        filters = filters or {}
        action_prefix = str(filters.get("action_prefix", "")).strip()
        events = list(self.store.audit_log)
        if action_prefix:
            events = [event for event in events if event.action.startswith(action_prefix)]
        required_fields = ["event_id", "actor", "action", "resource_type", "resource_id", "source", "timestamp"]
        field_counts = {field: 0 for field in required_fields}
        incomplete: list[dict[str, Any]] = []
        for event in events:
            plain = to_plain(event)
            missing = [field for field in required_fields if plain.get(field) in {"", None}]
            for field in required_fields:
                if field not in missing:
                    field_counts[field] += 1
            if missing:
                incomplete.append({"event_id": event.event_id, "action": event.action, "missing": missing})
        total = len(events)
        field_coverage = {field: round(count / max(1, total), 4) if total else 1.0 for field, count in field_counts.items()}
        return {
            "total": total,
            "complete": total - len(incomplete),
            "coverage": round((total - len(incomplete)) / max(1, total), 4) if total else 1.0,
            "field_coverage": field_coverage,
            "incomplete": incomplete[:100],
        }

    def data_security_report(self, filters: Mapping[str, Any] | None = None) -> dict[str, Any]:
        filters = filters or {}
        resource_type_filter = str(filters.get("resource_type", "")).strip()
        finding_type_filter = str(filters.get("finding_type", "")).strip()
        issuer_id_filter = str(filters.get("issuer_id", "")).strip()
        source_id_filter = self._canonical_source_id(str(filters.get("source_id", "")).strip()) if filters.get("source_id") else ""
        limit = self._bounded_limit(filters.get("limit", 100), 1000)
        scan_char_limit = self._bounded_limit(filters.get("scan_char_limit", 20000), 200000)

        resources = self._data_security_scan_resources(scan_char_limit=scan_char_limit)
        if resource_type_filter:
            resources = [item for item in resources if item["resource_type"] == resource_type_filter]
        if issuer_id_filter:
            resources = [item for item in resources if item["issuer_id"] == issuer_id_filter]
        if source_id_filter:
            resources = [item for item in resources if item["source_id"] == source_id_filter]

        findings: list[dict[str, Any]] = []
        by_type: dict[str, int] = {}
        by_resource_type: dict[str, int] = {}
        by_source: dict[str, int] = {}
        by_severity: dict[str, int] = {}
        for resource in resources:
            for finding in self._sensitive_findings_for_text(resource["text"], resource=resource):
                if finding_type_filter and finding["finding_type"] != finding_type_filter:
                    continue
                findings.append(finding)
                by_type[finding["finding_type"]] = by_type.get(finding["finding_type"], 0) + 1
                by_resource_type[finding["resource_type"]] = by_resource_type.get(finding["resource_type"], 0) + 1
                by_source[finding["source_id"]] = by_source.get(finding["source_id"], 0) + 1
                by_severity[finding["severity"]] = by_severity.get(finding["severity"], 0) + 1

        findings.sort(key=lambda item: (item["severity_rank"], item["resource_type"], item["resource_id"], item["start_offset"]), reverse=True)
        for finding in findings:
            finding.pop("severity_rank", None)
        return {
            "total": len(findings),
            "by_type": by_type,
            "by_resource_type": by_resource_type,
            "by_source": by_source,
            "by_severity": by_severity,
            "filters": {
                "resource_type": resource_type_filter,
                "finding_type": finding_type_filter,
                "issuer_id": issuer_id_filter,
                "source_id": source_id_filter,
                "scan_char_limit": scan_char_limit,
            },
            "findings": findings[:limit],
        }

    def record_permission_denied(self, method: str, path: str, *, role: str, actor: str = "system") -> None:
        self._audit(
            actor,
            "permission_denied",
            "api_route",
            f"{method} {path}",
            source="api_gateway",
            approval_state=f"role={role}",
        )

    def _data_security_scan_resources(self, *, scan_char_limit: int) -> list[dict[str, Any]]:
        resources: list[dict[str, Any]] = []

        def add_resource(
            *,
            resource_type: str,
            resource_id: str,
            document_id: str,
            issuer_id: str,
            source_id: str,
            field_name: str,
            text: str,
            rights_tag: Any,
        ) -> None:
            if not text:
                return
            source = self.store.sources.get(source_id)
            resources.append(
                {
                    "resource_type": resource_type,
                    "resource_id": resource_id,
                    "document_id": document_id,
                    "issuer_id": issuer_id,
                    "source_id": source_id,
                    "source_type": source.source_type if source else "",
                    "source_risk_level": source.risk_level if source else "unknown",
                    "rights_tag": to_plain(rights_tag) if rights_tag else {},
                    "field_name": field_name,
                    "text": text[:scan_char_limit],
                }
            )

        for document in self.store.documents.values():
            add_resource(
                resource_type="document",
                resource_id=document.document_id,
                document_id=document.document_id,
                issuer_id=document.issuer_id,
                source_id=document.source_id,
                field_name="body",
                text=document.body or self._document_object_text(document),
                rights_tag=document.rights_tag,
            )
        for evidence in self.store.evidence.values():
            document = self.store.documents.get(evidence.document_id)
            add_resource(
                resource_type="evidence",
                resource_id=evidence.evidence_id,
                document_id=evidence.document_id,
                issuer_id=document.issuer_id if document else "",
                source_id=document.source_id if document else "",
                field_name="span_text",
                text="\n".join(part for part in [evidence.span_text, evidence.canonical_text] if part),
                rights_tag=document.rights_tag if document else None,
            )
        for answer in self.store.research_answers.values():
            source_id = ""
            rights_tag = None
            for document_id in answer.source_document_ids:
                document = self.store.documents.get(document_id)
                if document:
                    source_id = document.source_id
                    rights_tag = document.rights_tag
                    break
            add_resource(
                resource_type="research_answer",
                resource_id=answer.answer_id,
                document_id=",".join(answer.source_document_ids),
                issuer_id=answer.issuer_id,
                source_id=source_id,
                field_name="answer_text",
                text=f"{answer.english_source_text}\n{answer.chinese_summary}",
                rights_tag=rights_tag,
            )
        return resources

    def _sensitive_findings_for_text(self, text: str, *, resource: Mapping[str, Any]) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        for finding_type, pattern in SENSITIVE_TEXT_PATTERNS:
            for match in pattern.finditer(text):
                severity = self._sensitive_finding_severity(finding_type)
                findings.append(
                    {
                        "finding_type": finding_type,
                        "severity": severity,
                        "resource_type": resource["resource_type"],
                        "resource_id": resource["resource_id"],
                        "document_id": resource["document_id"],
                        "issuer_id": resource["issuer_id"],
                        "source_id": resource["source_id"],
                        "source_type": resource["source_type"],
                        "source_risk_level": resource["source_risk_level"],
                        "rights_tag": resource["rights_tag"],
                        "field_name": resource["field_name"],
                        "start_offset": match.start(),
                        "end_offset": match.end(),
                        "match_hash": hashlib.sha256(match.group(0).encode("utf-8")).hexdigest(),
                        "snippet": self._masked_sensitive_context(text, match, finding_type=finding_type),
                        "severity_rank": {"medium": 1, "high": 2, "critical": 3}.get(severity, 0),
                    }
                )
        return findings

    def _sensitive_finding_severity(self, finding_type: str) -> str:
        if finding_type == "secret_literal":
            return "critical"
        if finding_type == "cn_id":
            return "high"
        return "medium"

    def _masked_sensitive_context(self, text: str, match: re.Match[str], *, finding_type: str) -> str:
        _ = finding_type
        context_start = max(0, match.start() - 48)
        context_end = min(len(text), match.end() + 48)
        context = text[context_start:context_end]
        for pattern_type, pattern in SENSITIVE_TEXT_PATTERNS:
            context = pattern.sub(lambda item, pattern_type=pattern_type: self._mask_sensitive_value(item, finding_type=pattern_type), context)
        return re.sub(r"\s+", " ", context).strip()

    def _mask_sensitive_value(self, match: re.Match[str], *, finding_type: str) -> str:
        value = match.group(0)
        if finding_type == "secret_literal":
            key = match.group(1) if match.lastindex else "secret"
            return f"{key}=***REDACTED***"
        if finding_type == "email" and "@" in value:
            local, domain = value.split("@", 1)
            local_mask = f"{local[:1]}***" if local else "***"
            if "." in domain:
                domain_head, domain_tail = domain.rsplit(".", 1)
                domain = f"{domain_head[:1]}***.{domain_tail}"
            else:
                domain = "***"
            return f"{local_mask}@{domain}"
        if finding_type == "cn_mobile" and len(value) >= 7:
            return f"{value[:3]}****{value[-4:]}"
        if finding_type == "cn_id" and len(value) >= 8:
            return f"{value[:4]}**********{value[-4:]}"
        return "***REDACTED***"

    def _normalize_source_governance(self, source: SourceDefinition, *, preserve_existing: bool = False) -> None:
        _ = preserve_existing
        if source.risk_level not in {"green", "yellow", "red"}:
            raise ValidationError("source risk_level must be green, yellow, or red")
        if not source.field_whitelist:
            source.field_whitelist = sorted({str(value) for value in source.field_mapping.values() if str(value)})
        public_source_types = {"regulatory", "exchange", "company_ir", "public_market_data", "public_web", "local_reference"}
        if not source.retention_policy:
            if source.source_type in public_source_types:
                source.retention_policy = "retain_public_reference_with_source_uri"
            elif source.risk_level == "red":
                source.retention_policy = "manual_reference_only_no_cache"
            else:
                source.retention_policy = "review_public_terms_before_cache"
        if not source.cache_ttl_days:
            if source.source_type in public_source_types:
                source.cache_ttl_days = 3650
            elif source.risk_level == "red":
                source.cache_ttl_days = 0
            else:
                source.cache_ttl_days = 90
        if not source.usage_scope:
            if source.source_type in public_source_types:
                source.usage_scope = "public_reference_internal_research"
            elif source.risk_level == "red":
                source.usage_scope = "manual_reference_only"
            else:
                source.usage_scope = "public_terms_review_required"
        if not source.collection_method:
            if source.source_type in {"regulatory", "exchange", "company_ir"}:
                source.collection_method = "official_public_endpoint"
            elif source.source_type == "public_market_data":
                source.collection_method = "local_file_or_public_api"
            elif source.source_type == "local_reference":
                source.collection_method = "local_filesystem"
            elif source.source_type == "manual_reference":
                source.collection_method = "manual_only"
            else:
                source.collection_method = "public_connector_candidate"
        if not source.robots_policy:
            if source.source_type in {"regulatory", "exchange", "company_ir", "public_market_data", "local_reference"}:
                source.robots_policy = "reviewed_public_or_local_source"
            elif source.risk_level == "red":
                source.robots_policy = "manual_review_required"
        if not source.review_cadence:
            source.review_cadence = "quarterly"
        if not source.review_owner_role:
            source.review_owner_role = self._default_source_review_owner_role(source)
        if not source.review_owner:
            source.review_owner = source.review_owner_role

    def _source_governance_gaps(self, source: SourceDefinition) -> list[str]:
        gaps: list[str] = []
        if not source.retention_policy:
            gaps.append("missing_retention_policy")
        if source.cache_ttl_days < 0:
            gaps.append("invalid_cache_ttl_days")
        if source.source_type in {"public_market_data", "public_web", "local_reference", "third_party_connector"} and not (source.provenance_ref or source.source_tos_uri):
            gaps.append("missing_provenance_ref")
        if source.source_type in {"public_web", "third_party_connector"} and not source.robots_policy:
            gaps.append("missing_robots_policy")
        if not source.usage_scope:
            gaps.append("missing_usage_scope")
        if not source.collection_method:
            gaps.append("missing_collection_method")
        if source.field_mapping and not source.field_whitelist:
            gaps.append("missing_field_whitelist")
        if source.risk_level not in {"green", "yellow", "red"}:
            gaps.append("invalid_risk_level")
        if source.rights_tag.training_allowed and source.risk_level != "green":
            gaps.append("training_allowed_on_non_green_source")
        return gaps

    def _source_review_reminder_rows(self, *, as_of: Any, due_before: Any) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        reviews_by_source: dict[str, list[SourceReviewRecord]] = {}
        for review in self.store.source_reviews.values():
            reviews_by_source.setdefault(review.source_id, []).append(review)
        for source in self.store.sources.values():
            review_owner_role = self._source_review_owner_role(source)
            review_owner = self._source_review_owner(source)
            source_reviews = sorted(reviews_by_source.get(source.source_id, []), key=lambda item: (item.reviewed_at, item.review_id), reverse=True)
            latest_review = source_reviews[0] if source_reviews else None
            due_at = latest_review.next_review_due_at if latest_review and latest_review.next_review_due_at else self._source_initial_review_due_at(source, as_of)
            if due_at and due_at > due_before:
                continue
            status = "overdue" if due_at and due_at < as_of else "due_soon"
            gaps = self._source_governance_gaps(source)
            blocked_reasons = list(gaps)
            if source.risk_level == "red":
                blocked_reasons.append("red_source_manual_reference_only")
            if latest_review:
                blocked_reasons.extend(self._source_review_blockers(latest_review))
            rows.append(
                {
                    "source_id": source.source_id,
                    "source_type": source.source_type,
                    "risk_level": source.risk_level,
                    "license_class": source.rights_tag.license_class,
                    "review_owner": review_owner,
                    "review_owner_role": review_owner_role,
                    "review_cadence": source.review_cadence,
                    "last_reviewed_at": to_plain(latest_review.reviewed_at if latest_review else source.last_reviewed_at),
                    "latest_review_id": latest_review.review_id if latest_review else "",
                    "latest_review_status": latest_review.status if latest_review else "missing",
                    "due_at": to_plain(due_at),
                    "status": status,
                    "missing_review": latest_review is None,
                    "blocked_reasons": blocked_reasons,
                    "gaps": gaps,
                }
            )
        return rows

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
                "source_id": PUBLIC_EOD_MARKET_DATA_SOURCE_ID,
                "source_type": "public_market_data",
                "description": "Public or locally provided EOD/delayed market data for research, valuation, backtesting, and risk monitoring.",
                "risk_level": "green",
                "field_mapping": {
                    "security_id": "security_id",
                    "as_of_date": "as_of_date",
                    "open": "open",
                    "high": "high",
                    "low": "low",
                    "close": "close",
                    "adjusted_close": "adjusted_close",
                    "volume": "volume",
                },
                "provenance_ref": "local://data/local/tdx/market_data.duckdb",
                "source_tos_uri": "https://www.tdx.com.cn/",
                "usage_scope": "public_or_local_eod_internal_research_backtest_risk",
                "rights_tag": {
                    "license_class": "public_eod_reference",
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
                "source_id": MANUAL_TRANSCRIPT_REFERENCE_SOURCE_ID,
                "source_type": "manual_reference",
                "description": "Non-public or unclear transcript notes are manual-reference only and blocked from automated ingestion.",
                "risk_level": "red",
                "allowed_document_types": ["transcript", "private_meeting_note", "roadshow_note", "expert_note", "research"],
                "usage_scope": "manual_reference_only",
                "retention_policy": "manual_reference_only_no_cache",
                "rights_tag": {
                    "license_class": "manual_transcript_reference",
                    "training_allowed": False,
                    "redistribution_allowed": False,
                    "display_use": "restricted",
                    "non_display_use": "restricted",
                    "derived_data_use": "restricted",
                },
            },
            {
                "source_id": LOCAL_RESEARCH_REPORT_SOURCE_ID,
                "source_type": "local_reference",
                "description": "Local research report library for citation tracking and analyst reference only.",
                "risk_level": "yellow",
                "allowed_document_types": ["research"],
                "provenance_ref": "local://research-reports",
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
        ]
        created: list[SourceDefinition] = []
        for item in defaults:
            if item["source_id"] in self.store.sources:
                created.append(self.store.sources[item["source_id"]])
                continue
            created.append(self.register_source(item, actor=actor))
        return created

    def seed_astock_connectors(self, *, actor: str = "system") -> list[AStockConnectorDefinition]:
        defaults = [
            ("eastmoney_research", "eastmoney", "research_discovery", 10, False, {"title": "title", "url": "source_uri", "published_at": "published_at"}),
            ("cninfo_announcements", "cninfo", "announcement", 20, False, {"security_code": "ticker", "title": "title", "url": "source_uri"}),
            ("tencent_valuation_snapshot", "tencent", "valuation_snapshot", 30, False, {"symbol": "ticker", "pe": "pe_ttm", "pb": "pb"}),
            ("ths_hot_topics", "tonghuashun", "hot_topic", 40, False, {"topic": "theme", "stocks": "constituents"}),
            ("baidu_concepts", "baidu_stock", "concept_fund_flow", 50, False, {"concept": "theme", "net_inflow": "net_inflow"}),
            ("dragon_tiger_list", "exchange_public", "dragon_tiger_list", 60, False, {"trade_date": "as_of_date", "security_code": "ticker"}),
            ("unlock_calendar", "exchange_public", "unlock_calendar", 70, False, {"unlock_date": "event_date", "security_code": "ticker"}),
            ("iwencai_optional", "iwencai", "query", 90, True, {"query": "query", "rows": "rows"}),
        ]
        created: list[AStockConnectorDefinition] = []
        for connector_id, provider, endpoint_type, priority, requires_key, mapping in defaults:
            if connector_id in self.store.astock_connectors:
                created.append(self.store.astock_connectors[connector_id])
                continue
            source_id = f"astock_{connector_id}"
            rights_tag = {
                "license_class": "candidate_astock_reference",
                "training_allowed": False,
                "redistribution_allowed": False,
                "display_use": "restricted",
                "non_display_use": "restricted",
                "derived_data_use": "restricted",
            }
            if source_id not in self.store.sources:
                self.register_source(
                    {
                        "source_id": source_id,
                        "source_type": "third_party_connector",
                        "description": f"A-share supplemental connector candidate: {provider} {endpoint_type}.",
                        "risk_level": "yellow",
                        "field_mapping": mapping,
                        "rights_tag": rights_tag,
                    },
                    actor=actor,
                )
            created.append(
                self.register_astock_connector(
                    {
                        "connector_id": connector_id,
                        "provider": provider,
                        "endpoint_type": endpoint_type,
                        "source_id": source_id,
                        "priority": priority,
                        "requires_key": requires_key,
                        "rate_limit_per_minute": 20 if provider in {"iwencai", "tonghuashun"} else 60,
                        "field_mapping": mapping,
                        "allowed_use": ["manual_reference", "supplemental_research"],
                        "rights_tag": rights_tag,
                        "notes": "Candidate connector from a-stock-data / public A-share data ecosystem; verify license and stability before automation.",
                    },
                    actor=actor,
                )
            )
        return created

    def register_astock_connector(self, payload: Mapping[str, Any], *, actor: str = "system") -> AStockConnectorDefinition:
        connector = AStockConnectorDefinition.from_dict(payload)
        if connector.status not in {"candidate", "verified", "blocked", "deprecated"}:
            raise ValidationError("A-stock connector status must be candidate, verified, blocked, or deprecated")
        if connector.last_check_status not in {"not_checked", "passed", "failed", "blocked", "manual_review"}:
            raise ValidationError("A-stock connector last_check_status must be not_checked, passed, failed, blocked, or manual_review")
        if connector.source_id not in self.store.sources:
            raise NotFoundError(f"source {connector.source_id} not found")
        if connector.connector_id in self.store.astock_connectors:
            raise ConflictError(f"A-stock connector {connector.connector_id} already exists")
        if connector.rights_tag.training_allowed or connector.rights_tag.redistribution_allowed:
            raise ComplianceGateError("supplemental A-stock connectors cannot default to training or redistribution use")
        self.store.astock_connectors[connector.connector_id] = connector
        self._audit(actor, "register_astock_connector", "astock_connector", connector.connector_id, source=connector.provider, approval_state=connector.status)
        return connector

    def astock_connectors_payload(self, filters: Mapping[str, Any] | None = None) -> dict[str, Any]:
        filters = filters or {}
        provider = str(filters.get("provider", "")).strip()
        status = str(filters.get("status", "")).strip()
        requires_key = filters.get("requires_key")
        limit = self._bounded_limit(filters.get("limit", 100), max_value=1000)
        connectors = list(self.store.astock_connectors.values())
        if provider:
            connectors = [item for item in connectors if item.provider == provider]
        if status:
            connectors = [item for item in connectors if item.status == status]
        if requires_key is not None:
            expected_requires_key = requires_key if isinstance(requires_key, bool) else str(requires_key).strip().lower() in {"1", "true", "yes"}
            connectors = [item for item in connectors if item.requires_key is expected_requires_key]
        connectors = sorted(connectors, key=lambda item: item.priority)[:limit]
        return {"connectors": [to_plain(item) for item in connectors], "total": len(connectors)}

    def verify_astock_connectors(self, payload: Mapping[str, Any], *, actor: str = "system") -> dict[str, Any]:
        results = payload.get("results")
        if results is None:
            results = [payload]
        updated: list[AStockConnectorDefinition] = []
        for item in results:
            if not isinstance(item, Mapping):
                raise ValidationError("A-stock connector verification result must be an object")
            connector_id = str(item["connector_id"])
            connector = self.store.astock_connectors.get(connector_id)
            if connector is None:
                raise NotFoundError(f"A-stock connector {connector_id} not found")
            status = str(item.get("status", "manual_review"))
            if status not in {"passed", "failed", "blocked", "manual_review"}:
                raise ValidationError("A-stock connector verification status must be passed, failed, blocked, or manual_review")
            connector.last_check_status = status
            connector.last_error = str(item.get("error", ""))
            connector.last_checked_at = utcnow()
            if status == "passed":
                connector.status = "verified"
            elif status == "blocked":
                connector.status = "blocked"
            else:
                connector.status = "candidate"
            updated.append(connector)
            self._audit(actor, "verify_astock_connector", "astock_connector", connector.connector_id, source=connector.provider, approval_state=status)
        return {"updated": [to_plain(item) for item in updated], "total": len(updated)}

    def fetch_astock_connector_sample(self, payload: Mapping[str, Any], *, actor: str = "system") -> dict[str, Any]:
        connector_id = str(payload["connector_id"])
        connector = self.store.astock_connectors.get(connector_id)
        if connector is None:
            raise NotFoundError(f"A-stock connector {connector_id} not found")
        source = self.store.sources.get(connector.source_id)
        if source is None:
            raise NotFoundError(f"source {connector.source_id} not found")
        if connector.status == "blocked" or source.risk_level == "red":
            raise ComplianceGateError("blocked or red-zone A-stock connector cannot be fetched")
        if connector.rights_tag.training_allowed or connector.rights_tag.redistribution_allowed:
            raise ComplianceGateError("A-stock connector fetch cannot allow training or redistribution")
        rows = payload.get("sample_rows", payload.get("rows", []))
        if isinstance(rows, Mapping):
            rows = [rows]
        if not isinstance(rows, list):
            raise ValidationError("A-stock connector sample_rows must be a list")
        limit = self._bounded_limit(payload.get("limit", len(rows) or 1), 500)
        normalized_rows: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        for index, row in enumerate(rows[:limit]):
            if not isinstance(row, Mapping):
                errors.append({"index": index, "error": "row must be an object"})
                continue
            normalized = self._normalize_astock_connector_row(connector, row)
            normalized_rows.append(normalized)
        allowed_for_automation = connector.status == "verified" and source.risk_level == "green" and source.source_type in {"exchange", "regulatory", "public_market_data"}
        result = {
            "connector_id": connector.connector_id,
            "provider": connector.provider,
            "endpoint_type": connector.endpoint_type,
            "source_id": connector.source_id,
            "status": connector.status,
            "last_check_status": connector.last_check_status,
            "allowed_use": list(connector.allowed_use),
            "rights_tag": to_plain(connector.rights_tag),
            "source_risk_level": source.risk_level,
            "source_usage_scope": source.usage_scope,
            "source_tos_uri": source.source_tos_uri,
            "automation_allowed": allowed_for_automation,
            "automation_blockers": self._astock_automation_blockers(connector, source),
            "normalized_rows": normalized_rows,
            "errors": errors,
            "created_count": len(normalized_rows),
            "failed_count": len(errors),
        }
        connector.last_check_status = "passed" if not errors else "manual_review"
        connector.last_error = "; ".join(item["error"] for item in errors[:3])
        connector.last_checked_at = utcnow()
        self._audit(actor, "fetch_astock_connector_sample", "astock_connector", connector.connector_id, source=connector.provider, approval_state=connector.last_check_status)
        return result

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
        source_id = self._canonical_source_id(str(payload.get("source_id", PUBLIC_EOD_MARKET_DATA_SOURCE_ID)))
        if source_id not in self.store.sources:
            if source_id == PUBLIC_EOD_MARKET_DATA_SOURCE_ID:
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
            raise ValidationError("market data only supports public eod or delayed data")
        rights_tag = source.rights_tag if "rights_tag" not in payload else type(source.rights_tag).from_dict(payload["rights_tag"])
        if not source.rights_tag.allows(rights_tag):
            raise PermissionDenied("market data rights exceed source rights")
        self._validate_market_data_field_boundary(payload, source)
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
        source_id = self._canonical_source_id(str(payload.get("source_id", PUBLIC_EOD_MARKET_DATA_SOURCE_ID)))
        if source_id not in self.store.sources:
            if source_id == PUBLIC_EOD_MARKET_DATA_SOURCE_ID:
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
        source_id = self._canonical_source_id(str(filters.get("source_id", "")).strip()) if filters.get("source_id") else ""
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

    def adjusted_market_data_payload(self, filters: Mapping[str, Any] | None = None) -> dict[str, Any]:
        filters = filters or {}
        security_id = str(filters.get("security_id", "")).strip()
        if not security_id:
            raise ValidationError("adjusted market data requires security_id")
        if security_id not in self.store.securities:
            raise NotFoundError(f"security {security_id} not found")
        source_id = self._canonical_source_id(str(filters.get("source_id", PUBLIC_EOD_MARKET_DATA_SOURCE_ID)))
        data_type = str(filters.get("data_type", "eod"))
        adjustment_mode = str(filters.get("adjustment_mode", filters.get("mode", "backward"))).strip().lower()
        if adjustment_mode not in {"raw", "backward", "forward"}:
            raise ValidationError("adjustment_mode must be raw, backward, or forward")
        start_date = str(filters.get("start_date", ""))
        end_date = str(filters.get("end_date", ""))
        limit = self._bounded_limit(filters.get("limit", 500), 10000)
        points = [
            point
            for point in self.store.market_data.values()
            if point.security_id == security_id and point.source_id == source_id and point.data_type == data_type
        ]
        if start_date:
            points = [point for point in points if point.as_of_date >= start_date]
        if end_date:
            points = [point for point in points if point.as_of_date <= end_date]
        points.sort(key=lambda item: item.as_of_date)
        actions = [
            action
            for action in self.store.corporate_actions.values()
            if action.security_id == security_id and action.source_id == source_id
        ]
        actions.sort(key=lambda item: (item.ex_date, item.action_id))
        adjusted_rows: list[dict[str, Any]] = []
        for point in points[:limit]:
            factor, event_ids = self._market_data_adjustment_factor(point, actions, adjustment_mode=adjustment_mode)
            cash_dividend = self._cash_dividend_for_date(point.as_of_date, actions)
            adjusted_rows.append(
                {
                    **to_plain(point),
                    "raw_close": point.close,
                    "raw_adjusted_close": point.adjusted_close,
                    "adjustment_mode": adjustment_mode,
                    "adjustment_factor": round(factor, 10),
                    "computed_adjusted_open": round(point.open * factor, 6),
                    "computed_adjusted_high": round(point.high * factor, 6),
                    "computed_adjusted_low": round(point.low * factor, 6),
                    "computed_adjusted_close": round(point.close * factor, 6),
                    "corporate_action_ids": event_ids,
                    "cash_dividend": round(cash_dividend, 6),
                    "computed_adjusted_cash_dividend": round(cash_dividend * factor, 6),
                }
            )
        return {
            "security_id": security_id,
            "source_id": source_id,
            "data_type": data_type,
            "adjustment_mode": adjustment_mode,
            "adjustment_policy": {
                "raw": "Use stored OHLC and adjusted_close without applying corporate actions.",
                "backward": "Apply future split, reverse split, and stock dividend actions to older prices for backtest continuity.",
                "forward": "Apply past split, reverse split, and stock dividend actions to newer prices for old-share-basis continuity.",
                "cash_dividends": "Cash dividends are returned per ex-date and are only included in returns when total_return_method=cash_dividend_reinvested.",
            },
            "corporate_actions": [to_plain(action) for action in actions],
            "count": len(adjusted_rows),
            "market_data": adjusted_rows,
        }

    def market_data_returns_payload(self, filters: Mapping[str, Any] | None = None) -> dict[str, Any]:
        filters = filters or {}
        adjusted = self.adjusted_market_data_payload(filters)
        price_field = str(filters.get("price_field", "computed_adjusted_close"))
        if price_field not in {"computed_adjusted_close", "close", "adjusted_close"}:
            raise ValidationError("price_field must be computed_adjusted_close, close, or adjusted_close")
        total_return_method = str(filters.get("total_return_method", "price_only")).strip().lower()
        if total_return_method not in {"price_only", "cash_dividend_reinvested"}:
            raise ValidationError("total_return_method must be price_only or cash_dividend_reinvested")
        prices = [
            (
                str(row["as_of_date"]),
                float(row.get(price_field, 0.0) or 0.0),
                float(row.get("computed_adjusted_cash_dividend" if price_field == "computed_adjusted_close" else "cash_dividend", 0.0) or 0.0),
            )
            for row in adjusted["market_data"]
            if float(row.get(price_field, 0.0) or 0.0) > 0
        ]
        returns: list[dict[str, Any]] = []
        for (previous_date, previous_price, _previous_cash), (current_date, current_price, current_cash) in zip(prices, prices[1:]):
            cash_component = current_cash if total_return_method == "cash_dividend_reinvested" else 0.0
            period_return = (current_price + cash_component) / previous_price - 1.0 if previous_price else 0.0
            returns.append(
                {
                    "previous_date": previous_date,
                    "as_of_date": current_date,
                    "previous_price": round(previous_price, 6),
                    "price": round(current_price, 6),
                    "cash_dividend": round(cash_component, 6),
                    "return": round(period_return, 8),
                }
            )
        return_values = [item["return"] for item in returns]
        total_return = self._compound_return(return_values) if return_values else 0.0
        volatility = self._series_volatility(return_values)
        return {
            "security_id": adjusted["security_id"],
            "source_id": adjusted["source_id"],
            "data_type": adjusted["data_type"],
            "adjustment_mode": adjusted["adjustment_mode"],
            "price_field": price_field,
            "total_return_method": total_return_method,
            "price_count": len(prices),
            "return_count": len(returns),
            "total_return": round(total_return, 8),
            "volatility": round(volatility, 8),
            "max_drawdown": round(self._max_drawdown(return_values), 8) if return_values else 0.0,
            "returns": returns,
            "adjustment_policy": adjusted["adjustment_policy"],
        }

    def market_data_quality_report(self, filters: Mapping[str, Any] | None = None) -> dict[str, Any]:
        filters = filters or {}
        security_id = str(filters.get("security_id", "")).strip()
        market = str(filters.get("market", "")).strip()
        source_id = self._canonical_source_id(str(filters.get("source_id", "")).strip()) if filters.get("source_id") else ""
        data_type = str(filters.get("data_type", "")).strip()
        max_gap_days = int(filters.get("max_gap_days", 7))
        points = list(self.store.market_data.values())
        if security_id:
            points = [item for item in points if item.security_id == security_id]
        if market:
            points = [item for item in points if item.market == market]
        if source_id:
            points = [item for item in points if item.source_id == source_id]
        if data_type:
            points = [item for item in points if item.data_type == data_type]

        invalid_ohlc: list[dict[str, Any]] = []
        source_rights_gaps: list[dict[str, Any]] = []
        source_counts: dict[str, int] = {}
        security_counts: dict[str, int] = {}
        series: dict[tuple[str, str, str], list[MarketDataPoint]] = {}
        for point in points:
            source_counts[point.source_id] = source_counts.get(point.source_id, 0) + 1
            security_counts[point.security_id] = security_counts.get(point.security_id, 0) + 1
            series.setdefault((point.security_id, point.source_id, point.data_type), []).append(point)
            if point.high < max(point.open, point.close, point.low) or point.low > min(point.open, point.close, point.high):
                invalid_ohlc.append(
                    {
                        "data_id": point.data_id,
                        "security_id": point.security_id,
                        "as_of_date": point.as_of_date,
                        "open": point.open,
                        "high": point.high,
                        "low": point.low,
                        "close": point.close,
                        "issue": "ohlc_range_inconsistent",
                    }
                )
            source = self.store.sources.get(point.source_id)
            if source is None:
                source_rights_gaps.append({"data_id": point.data_id, "source_id": point.source_id, "issue": "source_not_registered"})
            elif source.risk_level == "red":
                source_rights_gaps.append({"data_id": point.data_id, "source_id": point.source_id, "issue": "red_source_in_research_layer"})
            elif not source.rights_tag.allows(point.rights_tag):
                source_rights_gaps.append({"data_id": point.data_id, "source_id": point.source_id, "issue": "point_rights_exceed_source"})

        source_governance = self.source_governance_report({"source_type": ""})
        source_gap_map = {row["source_id"]: row["gaps"] for row in source_governance["sources"]}
        used_source_gaps = [
            {"source_id": used_source_id, "gaps": source_gap_map.get(used_source_id, ["source_not_registered"])}
            for used_source_id in sorted(source_counts)
            if source_gap_map.get(used_source_id, ["source_not_registered"])
        ]

        date_gaps: list[dict[str, Any]] = []
        series_summary: list[dict[str, Any]] = []
        for (series_security_id, series_source_id, series_data_type), items in sorted(series.items()):
            valid_dates = sorted(parsed for item in items if (parsed := self._parse_quality_date(item.as_of_date)) is not None)
            for previous, current in zip(valid_dates, valid_dates[1:]):
                gap_days = (current - previous).days - 1
                if gap_days > max_gap_days:
                    date_gaps.append(
                        {
                            "security_id": series_security_id,
                            "source_id": series_source_id,
                            "data_type": series_data_type,
                            "previous_date": previous.isoformat(),
                            "current_date": current.isoformat(),
                            "gap_days": gap_days,
                        }
                    )
            series_summary.append(
                {
                    "security_id": series_security_id,
                    "source_id": series_source_id,
                    "data_type": series_data_type,
                    "count": len(items),
                    "start_date": min(valid_dates).isoformat() if valid_dates else "",
                    "end_date": max(valid_dates).isoformat() if valid_dates else "",
                }
            )

        issue_count = len(invalid_ohlc) + len(source_rights_gaps) + len(used_source_gaps) + len(date_gaps)
        total = len(points)
        return {
            "total_points": total,
            "quality_score": round(max(0.0, 1.0 - issue_count / max(1, total)), 4) if total else 1.0,
            "source_counts": source_counts,
            "security_counts": security_counts,
            "series": series_summary,
            "invalid_ohlc": invalid_ohlc[:100],
            "source_rights_gaps": source_rights_gaps[:100],
            "source_governance_gaps": used_source_gaps[:100],
            "date_gaps": date_gaps[:100],
            "issue_count": issue_count,
        }

    def tdx_market_data_preview(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        adapter = self._tdx_adapter(payload)
        rows = adapter.query_daily(
            symbols=self._tdx_symbols(payload),
            start_date=str(payload.get("start_date", "1900-01-01")),
            end_date=str(payload.get("end_date", "2099-12-31")),
            limit=self._bounded_limit(payload.get("limit", 100), 10000),
        )
        result = {
            "adapter": adapter.describe(),
            "rows": rows,
            "count": len(rows),
        }
        if bool(payload.get("include_summary", False)):
            result["summary"] = adapter.summary()
        return result

    def import_tdx_market_data(self, payload: Mapping[str, Any], *, actor: str = "system") -> dict[str, Any]:
        source_id = self._canonical_source_id(str(payload.get("source_id", PUBLIC_EOD_MARKET_DATA_SOURCE_ID)))
        if source_id not in self.store.sources:
            if source_id == PUBLIC_EOD_MARKET_DATA_SOURCE_ID:
                self.seed_default_sources(actor=actor)
            else:
                raise NotFoundError(f"source {source_id} not found")
        data_type = str(payload.get("data_type", "eod"))
        adapter = self._tdx_adapter(payload)
        rows = adapter.query_daily(
            symbols=self._tdx_symbols(payload),
            start_date=str(payload.get("start_date", "1900-01-01")),
            end_date=str(payload.get("end_date", "2099-12-31")),
            limit=self._bounded_limit(payload.get("limit", 100), 10000),
        )
        security_map = payload.get("security_map", {})
        if not isinstance(security_map, Mapping):
            raise ValidationError("security_map must be an object when provided")
        created: list[MarketDataPoint] = []
        skipped: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        for index, row in enumerate(rows):
            symbol = str(row.get("symbol", "")).strip()
            trade_date = str(row.get("trade_date", "")).strip()
            security = self._resolve_tdx_security(symbol, security_map)
            if security is None:
                errors.append({"index": index, "symbol": symbol, "trade_date": trade_date, "error": "security mapping not found"})
                continue
            data_id = self._market_data_id(security.security_id, trade_date, data_type, source_id)
            if data_id in self.store.market_data and bool(payload.get("skip_existing", True)):
                skipped.append({"index": index, "symbol": symbol, "trade_date": trade_date, "data_id": data_id})
                continue
            try:
                created.append(
                    self.register_market_data_point(
                        {
                            "data_id": data_id,
                            "security_id": security.security_id,
                            "source_id": source_id,
                            "market": security.market,
                            "as_of_date": trade_date,
                            "data_type": data_type,
                            "currency": security.currency,
                            "open": row.get("open", 0.0) or 0.0,
                            "high": row.get("high", 0.0) or 0.0,
                            "low": row.get("low", 0.0) or 0.0,
                            "close": row.get("close", 0.0) or 0.0,
                            "adjusted_close": row.get("close", 0.0) or 0.0,
                            "volume": row.get("volume", 0.0) or 0.0,
                        },
                        actor=actor,
                    )
                )
            except (ValidationError, NotFoundError, PermissionDenied, ConflictError) as exc:
                errors.append({"index": index, "symbol": symbol, "trade_date": trade_date, "error": str(exc)})
        self._audit(
            actor,
            "import_tdx_market_data",
            "market_data",
            str(payload.get("batch_id", "tdx_import")),
            source="tdx",
            approval_state=f"created={len(created)};skipped={len(skipped)};failed={len(errors)}",
        )
        return {
            "adapter": adapter.describe(),
            "source_rows": len(rows),
            "created": [to_plain(item) for item in created],
            "skipped": skipped,
            "errors": errors,
            "created_count": len(created),
            "skipped_count": len(skipped),
            "failed_count": len(errors),
        }

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
        canonical_source_id = self._canonical_source_id(document.source_id)
        if canonical_source_id != document.source_id:
            document = replace(document, source_id=canonical_source_id)
        sanitized_source_uri = self._sanitize_source_uri(document.source_uri)
        if sanitized_source_uri != document.source_uri:
            document = replace(document, source_uri=sanitized_source_uri)
        issuer = self.store.issuers.get(document.issuer_id)
        if issuer is None:
            raise NotFoundError(f"issuer {document.issuer_id} not found")
        source = self.store.sources.get(document.source_id)
        if source is None:
            raise NotFoundError(f"source {document.source_id} not found")
        if source.risk_level == "red":
            raise PermissionDenied("red source cannot enter automated document ingestion")
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

    def scan_research_reports(self, payload: Mapping[str, Any], *, actor: str = "system") -> dict[str, Any]:
        raw_root = str(payload.get("root_path") or os.environ.get("AI_QUANT_RESEARCH_REPORT_ROOT") or "").strip()
        if not raw_root:
            raise ValidationError("research report scan requires root_path or AI_QUANT_RESEARCH_REPORT_ROOT")
        root = Path(raw_root).expanduser()
        if not root.exists() or not root.is_dir():
            raise ValidationError(f"research report root not found: {root}")
        extensions = payload.get("extensions", [".pdf"])
        if isinstance(extensions, str):
            extensions = [item.strip() for item in extensions.split(",")]
        if not isinstance(extensions, list):
            raise ValidationError("extensions must be a list or comma-separated string")
        limit = self._bounded_limit(payload.get("limit", 1000), 10000)
        hash_files = bool(payload.get("hash_files", False))
        per_broker_sources = bool(payload.get("per_broker_sources", True))
        files = iter_report_files(root, extensions={str(item).lower() for item in extensions}, limit=limit)
        reports: list[ResearchReportAsset] = []
        for path in files:
            metadata = infer_report_metadata(path, root)
            broker = str(metadata["broker"])
            source_id = self._research_report_source_id(broker) if per_broker_sources else LOCAL_RESEARCH_REPORT_SOURCE_ID
            self._ensure_research_report_source(source_id, broker, actor=actor)
            report = ResearchReportAsset(
                report_id=report_id_for_path(path),
                source_id=source_id,
                broker=broker,
                file_path=str(path),
                file_name=path.name,
                title=str(metadata["title"]),
                year=str(metadata["year"]),
                month=str(metadata["month"]),
                file_type=path.suffix.lower().lstrip(".") or "unknown",
                size_bytes=path.stat().st_size,
                fingerprint=cheap_fingerprint(path, root),
                content_sha256=content_sha256(path) if hash_files else "",
                rights_tag=self.store.sources[source_id].rights_tag,
            )
            existing = self.store.research_reports.get(report.report_id)
            if existing and existing.document_id:
                report.document_id = existing.document_id
                report.status = existing.status
            self.store.research_reports[report.report_id] = report
            reports.append(report)
        self._audit(
            actor,
            "scan_research_reports",
            "research_report",
            str(root),
            source="research_report_manifest",
            approval_state=f"indexed={len(reports)}",
        )
        return {"root_path": str(root), "indexed_count": len(reports), "reports": [to_plain(item) for item in reports]}

    def research_reports_payload(self, filters: Mapping[str, Any] | None = None) -> dict[str, Any]:
        filters = filters or {}
        broker = str(filters.get("broker", "")).strip().lower()
        source_id = str(filters.get("source_id", "")).strip()
        status = str(filters.get("status", "")).strip()
        query = str(filters.get("q", "")).strip().lower()
        limit = self._bounded_limit(filters.get("limit", 50), 1000)
        reports = list(self.store.research_reports.values())
        if broker:
            reports = [item for item in reports if broker in item.broker.lower()]
        if source_id:
            reports = [item for item in reports if item.source_id == source_id]
        if status:
            reports = [item for item in reports if item.status == status]
        if query:
            reports = [item for item in reports if query in f"{item.title} {item.file_name} {item.broker} {item.year} {item.month}".lower()]
        reports.sort(key=lambda item: (item.year, item.month, item.broker, item.file_name), reverse=True)
        return {"count": len(reports), "reports": [to_plain(item) for item in reports[:limit]]}

    def ingest_research_report(self, report_id: str, payload: Mapping[str, Any], *, actor: str = "system") -> dict[str, Any]:
        report = self.store.research_reports.get(report_id)
        if report is None:
            raise NotFoundError(f"research report {report_id} not found")
        issuer_id = str(payload["issuer_id"])
        security_id = str(payload.get("security_id", ""))
        document_id = str(payload.get("document_id", f"doc_{report.report_id}"))
        if document_id in self.store.documents:
            report.document_id = document_id
            report.status = "ingested"
            self.store.commit()
            return {"report": to_plain(report), "document": to_plain(self.store.documents[document_id]), "created": False}
        document = self.ingest_document(
            {
                "document_id": document_id,
                "issuer_id": issuer_id,
                "security_id": security_id,
                "source_id": report.source_id,
                "source_type": "local_reference",
                "document_type": "research",
                "source_uri": f"research-report://{report.report_id}",
                "object_uri": report.file_path,
                "content_sha256": report.content_sha256,
                "body": "",
                "title": report.title,
                "rights_tag": to_plain(report.rights_tag),
                "language": str(payload.get("language", "zh")),
                "version": str(payload.get("version", "v1")),
            },
            actor=actor,
        )
        report.document_id = document.document_id
        report.status = "ingested"
        self.store.research_reports[report.report_id] = report
        self._audit(actor, "ingest_research_report", "research_report", report.report_id, source=report.source_id, approval_state=report.status)
        return {"report": to_plain(report), "document": to_plain(document), "created": True}

    def extract_research_report_text(self, report_id: str, payload: Mapping[str, Any] | None = None, *, actor: str = "system") -> dict[str, Any]:
        payload = payload or {}
        report = self.store.research_reports.get(report_id)
        if report is None:
            raise NotFoundError(f"research report {report_id} not found")
        if not report.document_id:
            raise ValidationError("research report must be ingested before text extraction")
        document = self.store.documents.get(report.document_id)
        if document is None:
            raise NotFoundError(f"document {report.document_id} not found")
        citation_char_limit = self._bounded_limit(payload.get("citation_char_limit", 1200), max_value=4000)
        parser_version = str(payload.get("parser_version", "research-report-text-1"))
        text = str(payload.get("text", "")).strip()
        if not text:
            text = document.body.strip() or self._read_research_report_text(report)
        if not text:
            review = self._create_manual_review(
                document,
                issue_type="research_report_text_extraction_required",
                severity="medium",
                message="No extractable local research report text is available for citation indexing.",
                suggested_action="Run OCR/text extraction before citing this local research report.",
                actor=actor,
                parser_version=parser_version,
            )
            report.status = "needs_text_review"
            self._audit(actor, "extract_research_report_text", "research_report", report.report_id, source=report.source_id, approval_state=report.status)
            return {
                "report": to_plain(report),
                "document": to_plain(document),
                "status": report.status,
                "evidence": [],
                "manual_review": to_plain(review),
                "citation_char_limit": citation_char_limit,
            }
        limited_text, truncated = self._citation_limited_text(text, source_publicness="restricted", char_limit=citation_char_limit)
        document.body = limited_text
        evidence = self._research_report_citation_evidence(document, limited_text, parser_version=parser_version)
        for item in evidence:
            self.store.evidence[item.evidence_id] = item
        report.status = "text_indexed"
        self._audit(actor, "extract_research_report_text", "research_report", report.report_id, source=report.source_id, approval_state=report.status)
        return {
            "report": to_plain(report),
            "document": to_plain(document),
            "status": report.status,
            "evidence": [to_plain(item) for item in evidence],
            "manual_review": None,
            "citation_char_limit": citation_char_limit,
            "citation_truncated": truncated,
        }

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
        fallback_error = ""
        if not chunks and self.document_parser.configured():
            try:
                parsed = self._parse_document_with_paddleocr(document)
                source_text = str(parsed.get("text", ""))
                chunks = chunk_text_by_page(source_text)
                if chunks:
                    parser_version = f"{parser_version}+paddleocr-vl"
                    model_version = str(parsed.get("model") or model_version)
                    self._audit(
                        actor,
                        "parse_document_with_paddleocr",
                        "document",
                        document_id,
                        source="paddleocr",
                        version=str(parsed.get("job_id", "")),
                        model_version=model_version,
                    )
                else:
                    fallback_error = "PaddleOCR returned no extractable markdown"
            except ValidationError as exc:
                fallback_error = str(exc)
        if not chunks:
            message = "No extractable text was found. The file may be scanned, image-only, encrypted, or unsupported by the current parser."
            if fallback_error:
                message = f"{message} OCR fallback failed or returned no text: {fallback_error}"
            self._create_manual_review(
                document,
                issue_type="empty_or_scanned_document",
                severity="high",
                parser_version=parser_version,
                message=message,
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
        issue_type = str(filters.get("issue_type", "")).strip()
        status = str(filters.get("status", "")).strip()
        severity = str(filters.get("severity", "")).strip()
        limit = self._bounded_limit(filters.get("limit", 50))
        items = list(self.store.manual_reviews.values())
        if document_id:
            items = [item for item in items if item.document_id == document_id]
        if issue_type:
            items = [item for item in items if item.issue_type == issue_type]
        if status:
            items = [item for item in items if item.status == status]
        if severity:
            items = [item for item in items if item.severity == severity]
        items.sort(key=lambda item: (item.status == "open", item.updated_at), reverse=True)
        return {"manual_reviews": [to_plain(item) for item in items[:limit]]}

    def create_manual_reference(self, payload: Mapping[str, Any], *, actor: str = "system") -> dict[str, Any]:
        self.seed_default_sources(actor=actor)
        raw_text = str(payload.get("body") or payload.get("text") or payload.get("content") or "").strip()
        if raw_text:
            raise ValidationError("manual reference intake stores metadata only; do not submit private or unclear source text")
        source_id = self._canonical_source_id(str(payload.get("source_id", MANUAL_TRANSCRIPT_REFERENCE_SOURCE_ID)))
        source = self.store.sources.get(source_id)
        if source is None:
            raise NotFoundError(f"source {source_id} not found")
        if source.source_type != "manual_reference" and source.risk_level != "red":
            raise ValidationError("manual reference intake requires a manual/red source")
        document_type = str(payload.get("document_type", "transcript"))
        if source.allowed_document_types and document_type not in source.allowed_document_types:
            raise ValidationError(f"document_type {document_type} is not allowed for source {source.source_id}")
        issuer_id = str(payload.get("issuer_id", "")).strip()
        security_id = str(payload.get("security_id", "")).strip()
        if issuer_id and issuer_id not in self.store.issuers:
            raise NotFoundError(f"issuer {issuer_id} not found")
        if security_id and security_id not in self.store.securities:
            raise NotFoundError(f"security {security_id} not found")
        rights_tag = source.rights_tag if "rights_tag" not in payload else type(source.rights_tag).from_dict(payload["rights_tag"])
        if not source.rights_tag.allows(rights_tag):
            raise PermissionDenied("manual reference rights exceed source rights")
        document_id = str(payload.get("document_id", new_id("manualref")))
        if document_id in self.store.documents:
            raise ConflictError(f"document {document_id} already exists")
        source_uri = str(payload.get("source_uri") or f"manual-reference://{source_id}/{document_id}")
        document = Document(
            document_id=document_id,
            issuer_id=issuer_id,
            security_id=security_id,
            document_type=document_type,
            source_id=source_id,
            source_type=source.source_type,
            source_uri=self._sanitize_source_uri(source_uri),
            rights_tag=rights_tag,
            body="",
            title=str(payload.get("title", "")),
            object_uri="",
            content_sha256="",
            published_at=parse_datetime(payload.get("published_at")) if payload.get("published_at") else utcnow(),
            language=str(payload.get("language", "mixed")),
            version="manual_reference_metadata_only",
        )
        self.store.documents[document.document_id] = document
        review = self._create_manual_review(
            document,
            issue_type="manual_reference_boundary_review",
            severity=str(payload.get("severity", "high")),
            parser_version="manual-reference-metadata",
            message=str(payload.get("notes", "Manual-only reference metadata requires compliance review before any automated ingestion.")),
            suggested_action="Confirm publicness, TOS/robots, Reg FD status, and usage boundary. Keep text outside the automated fact layer unless reclassified.",
            actor=actor,
        )
        self._audit(actor, "create_manual_reference", "document", document.document_id, source=source.source_type, version=rights_tag.license_class, approval_state=review.status)
        return {"document": to_plain(document), "manual_review": to_plain(review)}

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

    def _document_parser_optional_payload(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        raw = payload.get("optional_payload", payload.get("optionalPayload", {}))
        if raw is None:
            return {}
        if not isinstance(raw, Mapping):
            raise ValidationError("optional_payload must be an object")
        return dict(raw)

    def _parse_document_with_paddleocr(self, document: Document, *, optional_payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        if document.object_uri:
            try:
                data = self.object_store.read_bytes(document.object_uri)
            except (FileNotFoundError, IsADirectoryError, OSError, ValueError):
                data = b""
            if data:
                filename = Path(urlparse(document.object_uri).path).name or f"{document.document_id}.pdf"
                return self.document_parser.parse_bytes(data, filename=filename, optional_payload=optional_payload)
        source_uri = str(document.source_uri or "").strip()
        if source_uri.startswith(("http://", "https://")):
            return self.document_parser.parse_url(source_uri, optional_payload=optional_payload)
        raise ValidationError("document has no readable object_uri or http(s) source_uri for PaddleOCR parsing")

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
                "public_market_data": 0.08,
                "local_reference": 0.04,
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
        all_red_flags = [self._normalize_operating_red_flag(item, report_id=report_id, index=index, period=period) for index, item in enumerate(all_red_flags, start=1)]
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

    def operating_report_red_flag_reminders(self, filters: Mapping[str, Any] | None = None) -> dict[str, Any]:
        filters = filters or {}
        as_of_date = str(filters.get("as_of_date", utcnow().date().isoformat()))
        owner = str(filters.get("owner", "")).strip()
        status = str(filters.get("status", "open")).strip()
        reminders: list[dict[str, Any]] = []
        for report in self.store.operating_reports.values():
            for item in report.red_flags:
                if owner and str(item.get("owner", "")) != owner and str(item.get("owner_role", "")) != owner:
                    continue
                if status and str(item.get("status", "")) != status:
                    continue
                due_date = str(item.get("due_date", ""))
                reminders.append(
                    {
                        "report_id": report.report_id,
                        "period": report.period,
                        "red_flag_id": item.get("red_flag_id", ""),
                        "type": item.get("type", ""),
                        "owner": item.get("owner", ""),
                        "owner_role": item.get("owner_role", item.get("owner", "")),
                        "due_date": due_date,
                        "status": item.get("status", ""),
                        "overdue": bool(due_date and due_date < as_of_date and item.get("status") == "open"),
                    }
                )
        reminders.sort(key=lambda item: (not item["overdue"], item["due_date"], item["report_id"]))
        return {
            "as_of_date": as_of_date,
            "total": len(reminders),
            "overdue": sum(1 for item in reminders if item["overdue"]),
            "reminders": reminders,
        }

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

    def _series_volatility(self, returns: list[float]) -> float:
        if len(returns) < 2:
            return 0.0
        mean_return = sum(returns) / len(returns)
        variance = sum((item - mean_return) ** 2 for item in returns) / (len(returns) - 1)
        return variance ** 0.5

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

    def portfolio_returns_payload(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        holdings = payload.get("holdings", payload.get("weights", []))
        if isinstance(holdings, Mapping):
            holdings = [{"security_id": key, "weight": value} for key, value in holdings.items()]
        if not isinstance(holdings, list) or not holdings:
            raise ValidationError("portfolio returns require holdings list or weights object")
        source_id = self._canonical_source_id(str(payload.get("source_id", PUBLIC_EOD_MARKET_DATA_SOURCE_ID)))
        data_type = str(payload.get("data_type", "eod"))
        adjustment_mode = str(payload.get("adjustment_mode", "backward"))
        total_return_method = str(payload.get("total_return_method", "price_only"))
        start_date = str(payload.get("start_date", ""))
        end_date = str(payload.get("end_date", ""))
        limit = self._bounded_limit(payload.get("limit", 10000), 10000)

        series_by_security: dict[str, dict[str, float]] = {}
        normalized_weights: dict[str, float] = {}
        component_summaries: list[dict[str, Any]] = []
        for item in holdings:
            if not isinstance(item, Mapping):
                raise ValidationError("portfolio holding must be an object")
            security_id = str(item["security_id"])
            weight = float(item.get("weight", 0.0))
            if weight < 0:
                raise ValidationError("portfolio returns do not support short weights in this MVP path")
            if security_id not in self.store.securities:
                raise NotFoundError(f"security {security_id} not found")
            result = self.market_data_returns_payload(
                {
                    "security_id": security_id,
                    "source_id": source_id,
                    "data_type": data_type,
                    "adjustment_mode": adjustment_mode,
                    "total_return_method": total_return_method,
                    "start_date": start_date,
                    "end_date": end_date,
                    "limit": limit,
                }
            )
            series_by_security[security_id] = {str(row["as_of_date"]): float(row["return"]) for row in result["returns"]}
            normalized_weights[security_id] = weight
            component_summaries.append(
                {
                    "security_id": security_id,
                    "weight": weight,
                    "return_count": result["return_count"],
                    "total_return": result["total_return"],
                    "volatility": result["volatility"],
                    "max_drawdown": result["max_drawdown"],
                }
            )
        total_weight = sum(normalized_weights.values())
        if total_weight <= 0:
            raise ValidationError("portfolio total weight must be positive")
        normalized_weights = {security_id: weight / total_weight for security_id, weight in normalized_weights.items()}
        common_dates = sorted(set.intersection(*(set(series.keys()) for series in series_by_security.values()))) if series_by_security else []
        returns = []
        for as_of_date in common_dates:
            component_returns = {security_id: series[as_of_date] for security_id, series in series_by_security.items()}
            portfolio_return = sum(normalized_weights[security_id] * component_returns[security_id] for security_id in normalized_weights)
            returns.append(
                {
                    "as_of_date": as_of_date,
                    "return": round(portfolio_return, 8),
                    "component_returns": {security_id: round(value, 8) for security_id, value in component_returns.items()},
                }
            )
        return_values = [item["return"] for item in returns]
        attribution = self._portfolio_return_attribution(returns, normalized_weights, payload.get("groups", {}))
        return {
            "source_id": source_id,
            "data_type": data_type,
            "adjustment_mode": adjustment_mode,
            "total_return_method": total_return_method,
            "weights": {security_id: round(weight, 8) for security_id, weight in normalized_weights.items()},
            "components": component_summaries,
            "attribution": attribution,
            "return_count": len(returns),
            "total_return": round(self._compound_return(return_values), 8) if return_values else 0.0,
            "volatility": round(self._series_volatility(return_values), 8),
            "max_drawdown": round(self._max_drawdown(return_values), 8) if return_values else 0.0,
            "returns": returns,
            "coverage": {
                "common_dates": len(common_dates),
                "component_count": len(series_by_security),
                "requires_common_return_dates": True,
            },
        }

    def _portfolio_return_attribution(self, returns: list[dict[str, Any]], weights: Mapping[str, float], groups: Any) -> dict[str, Any]:
        group_overrides = groups if isinstance(groups, Mapping) else {}
        group_keys = ["market", "currency", "industry", "style"]
        attribution: dict[str, dict[str, dict[str, float]]] = {key: {} for key in group_keys}
        for security_id, weight in weights.items():
            security = self.store.securities.get(security_id)
            override = group_overrides.get(security_id, {}) if isinstance(group_overrides.get(security_id, {}), Mapping) else {}
            contribution = sum(float(row.get("component_returns", {}).get(security_id, 0.0)) * float(weight) for row in returns)
            for group_key in group_keys:
                if group_key in override:
                    group_value = str(override.get(group_key) or "unknown")
                elif security and hasattr(security, group_key):
                    group_value = str(getattr(security, group_key) or "unknown")
                else:
                    group_value = "unknown"
                row = attribution[group_key].setdefault(group_value, {"weight": 0.0, "period_contribution": 0.0})
                row["weight"] += float(weight)
                row["period_contribution"] += contribution
        return {
            group_key: {
                group_value: {
                    "weight": round(values["weight"], 8),
                    "period_contribution": round(values["period_contribution"], 8),
                }
                for group_value, values in sorted(groups_for_key.items())
            }
            for group_key, groups_for_key in attribution.items()
        }

    def portfolio_valuation_payload(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        holdings = payload.get("holdings", [])
        if not isinstance(holdings, list) or not holdings:
            raise ValidationError("portfolio valuation requires holdings list")
        as_of_date = str(payload.get("as_of_date", "9999-12-31"))
        source_id = self._canonical_source_id(str(payload.get("source_id", PUBLIC_EOD_MARKET_DATA_SOURCE_ID)))
        data_type = str(payload.get("data_type", "eod"))
        price_field = str(payload.get("price_field", "close"))
        if price_field not in {"close", "adjusted_close"}:
            raise ValidationError("valuation price_field must be close or adjusted_close")
        cash = float(payload.get("cash", 0.0))
        currency = str(payload.get("currency", "CNY"))
        positions: list[dict[str, Any]] = []
        missing_prices: list[dict[str, Any]] = []
        total_market_value = cash
        for item in holdings:
            if not isinstance(item, Mapping):
                raise ValidationError("valuation holding must be an object")
            security_id = str(item["security_id"])
            shares = float(item.get("shares", 0.0))
            if shares < 0:
                raise ValidationError("portfolio valuation does not support short shares in this MVP path")
            if security_id not in self.store.securities:
                raise NotFoundError(f"security {security_id} not found")
            point = self._latest_market_data_point(security_id, source_id=source_id, data_type=data_type, as_of_date=as_of_date)
            if point is None:
                missing_prices.append({"security_id": security_id, "reason": "no_market_data_at_or_before_as_of_date"})
                continue
            price = float(getattr(point, price_field))
            market_value = shares * price
            total_market_value += market_value
            positions.append(
                {
                    "security_id": security_id,
                    "shares": shares,
                    "price": round(price, 6),
                    "price_date": point.as_of_date,
                    "market_value": round(market_value, 6),
                    "source_id": point.source_id,
                    "data_type": point.data_type,
                    "price_field": price_field,
                }
            )
        for position in positions:
            position["weight"] = round(float(position["market_value"]) / total_market_value, 8) if total_market_value else 0.0
        cash_weight = round(cash / total_market_value, 8) if total_market_value else 0.0
        return {
            "as_of_date": as_of_date,
            "source_id": source_id,
            "data_type": data_type,
            "price_field": price_field,
            "currency": currency,
            "cash": round(cash, 6),
            "cash_weight": cash_weight,
            "gross_market_value": round(sum(float(position["market_value"]) for position in positions), 6),
            "total_market_value": round(total_market_value, 6),
            "positions": positions,
            "missing_prices": missing_prices,
            "position_count": len(positions),
            "missing_price_count": len(missing_prices),
            "valuation_policy": "Uses latest public/provided market data at or before as_of_date; does not imply execution or tradability.",
        }

    def register_portfolio_transaction(self, payload: Mapping[str, Any], *, actor: str = "system") -> PortfolioTransaction:
        security_id = str(payload["security_id"])
        if security_id not in self.store.securities:
            raise NotFoundError(f"security {security_id} not found")
        trade_date = str(payload["trade_date"])
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", trade_date):
            raise ValidationError("trade_date must use YYYY-MM-DD")
        source_id = self._canonical_source_id(str(payload.get("source_id", PUBLIC_EOD_MARKET_DATA_SOURCE_ID)))
        if source_id not in self.store.sources:
            if source_id == PUBLIC_EOD_MARKET_DATA_SOURCE_ID:
                self.seed_default_sources(actor=actor)
            else:
                raise NotFoundError(f"source {source_id} not found")
        source = self.store.sources[source_id]
        if source.risk_level == "red":
            raise PermissionDenied("red transaction source cannot enter portfolio ledger")
        transaction = PortfolioTransaction(
            transaction_id=str(payload.get("transaction_id", new_id("ptxn"))),
            security_id=security_id,
            trade_date=trade_date,
            side=str(payload["side"]),
            quantity=float(payload.get("quantity", 0.0)),
            price=float(payload.get("price", 0.0)),
            currency=str(payload.get("currency", self.store.securities[security_id].currency)),
            fees=float(payload.get("fees", 0.0)),
            source_id=source_id,
            account_id=str(payload.get("account_id", "")),
            strategy_id=str(payload.get("strategy_id", "")),
        )
        if transaction.quantity <= 0 or transaction.price < 0 or transaction.fees < 0:
            raise ValidationError("transaction quantity must be positive and price/fees non-negative")
        if transaction.transaction_id in self.store.portfolio_transactions:
            raise ConflictError(f"portfolio transaction {transaction.transaction_id} already exists")
        self.store.portfolio_transactions[transaction.transaction_id] = transaction
        self._audit(actor, "register_portfolio_transaction", "portfolio_transaction", transaction.transaction_id, source=source.source_type, approval_state=transaction.side)
        return transaction

    def portfolio_transactions_payload(self, filters: Mapping[str, Any] | None = None) -> dict[str, Any]:
        filters = filters or {}
        security_id = str(filters.get("security_id", "")).strip()
        account_id = str(filters.get("account_id", "")).strip()
        strategy_id = str(filters.get("strategy_id", "")).strip()
        limit = self._bounded_limit(filters.get("limit", 100), 1000)
        transactions = list(self.store.portfolio_transactions.values())
        if security_id:
            transactions = [item for item in transactions if item.security_id == security_id]
        if account_id:
            transactions = [item for item in transactions if item.account_id == account_id]
        if strategy_id:
            transactions = [item for item in transactions if item.strategy_id == strategy_id]
        transactions.sort(key=lambda item: (item.trade_date, item.transaction_id), reverse=True)
        return {"total": len(transactions), "transactions": [to_plain(item) for item in transactions[:limit]]}

    def portfolio_positions_from_transactions(self, filters: Mapping[str, Any] | None = None) -> dict[str, Any]:
        filters = filters or {}
        as_of_date = str(filters.get("as_of_date", "9999-12-31"))
        account_id = str(filters.get("account_id", "")).strip()
        strategy_id = str(filters.get("strategy_id", "")).strip()
        transactions = [item for item in self.store.portfolio_transactions.values() if item.trade_date <= as_of_date]
        if account_id:
            transactions = [item for item in transactions if item.account_id == account_id]
        if strategy_id:
            transactions = [item for item in transactions if item.strategy_id == strategy_id]
        shares: dict[str, float] = {}
        cost: dict[str, float] = {}
        for transaction in sorted(transactions, key=lambda item: (item.trade_date, item.transaction_id)):
            sign = 1.0 if transaction.side == "buy" else -1.0
            shares[transaction.security_id] = shares.get(transaction.security_id, 0.0) + sign * transaction.quantity
            cash_flow = sign * transaction.quantity * transaction.price + transaction.fees
            cost[transaction.security_id] = cost.get(transaction.security_id, 0.0) + cash_flow
        positions = [
            {
                "security_id": security_id,
                "shares": round(quantity, 8),
                "net_cost": round(cost.get(security_id, 0.0), 6),
            }
            for security_id, quantity in sorted(shares.items())
            if abs(quantity) > 1e-9
        ]
        return {
            "as_of_date": as_of_date,
            "account_id": account_id,
            "strategy_id": strategy_id,
            "positions": positions,
            "position_count": len(positions),
            "transaction_count": len(transactions),
        }

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
                    "source_id": PUBLIC_EOD_MARKET_DATA_SOURCE_ID,
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
        raw_source_text = "\n".join(item.canonical_text or item.span_text for item in evidence)
        citation_char_limit = self._bounded_limit(payload.get("citation_char_limit", 600), max_value=2000)
        source_text, citation_truncated = self._citation_limited_text(raw_source_text, source_publicness=source_publicness, char_limit=citation_char_limit)
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
            citation_char_limit=0 if source_publicness == "public" else citation_char_limit,
            citation_truncated=citation_truncated,
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

    def research_answer_quality_report(self, filters: Mapping[str, Any] | None = None) -> dict[str, Any]:
        filters = filters or {}
        issuer_id = str(filters.get("issuer_id", "")).strip()
        review_status = str(filters.get("human_review_status", filters.get("status", ""))).strip()
        limit = self._bounded_limit(filters.get("limit", 100), 1000)
        answers = list(self.store.research_answers.values())
        if issuer_id:
            answers = [item for item in answers if item.issuer_id == issuer_id]
        if review_status:
            answers = [item for item in answers if item.human_review_status == review_status]
        rows: list[dict[str, Any]] = []
        status_counts: dict[str, int] = {}
        source_linked = 0
        reviewed = 0
        citation_truncated = 0
        for answer in sorted(answers, key=lambda item: item.created_at, reverse=True):
            issues: list[str] = []
            status_counts[answer.human_review_status] = status_counts.get(answer.human_review_status, 0) + 1
            evidence = [self.store.evidence[evidence_id] for evidence_id in answer.evidence_ids if evidence_id in self.store.evidence]
            evidence_document_ids = {item.document_id for item in evidence}
            missing_evidence = [evidence_id for evidence_id in answer.evidence_ids if evidence_id not in self.store.evidence]
            missing_documents = [document_id for document_id in answer.source_document_ids if document_id not in self.store.documents]
            if not answer.evidence_ids or missing_evidence:
                issues.append("missing_evidence")
            if not answer.source_document_ids or missing_documents:
                issues.append("missing_source_document")
            if answer.source_document_ids and not set(answer.source_document_ids).issubset(evidence_document_ids):
                issues.append("source_document_not_backed_by_evidence")
            if not answer.english_source_text.strip():
                issues.append("missing_english_source_text")
            if answer.source_publicness != "public" and answer.citation_char_limit <= 0:
                issues.append("missing_restricted_citation_limit")
            if answer.citation_truncated:
                issues.append("citation_truncated")
                citation_truncated += 1
            if answer.human_review_status != "approved":
                issues.append("pending_human_review")
            else:
                reviewed += 1
            linked = not any(issue in issues for issue in {"missing_evidence", "missing_source_document", "source_document_not_backed_by_evidence", "missing_english_source_text"})
            if linked:
                source_linked += 1
            rows.append(
                {
                    "answer_id": answer.answer_id,
                    "issuer_id": answer.issuer_id,
                    "question": answer.question,
                    "human_review_status": answer.human_review_status,
                    "reviewer": answer.reviewer,
                    "evidence_count": len(answer.evidence_ids),
                    "linked_evidence_count": len(evidence),
                    "source_document_ids": list(answer.source_document_ids),
                    "source_publicness": answer.source_publicness,
                    "citation_char_limit": answer.citation_char_limit,
                    "citation_truncated": answer.citation_truncated,
                    "summary_version": answer.summary_version,
                    "prompt_version": answer.prompt_version,
                    "model_version": answer.model_version,
                    "issues": issues,
                    "source_linked": linked,
                }
            )
        total = len(rows)
        return {
            "total": total,
            "review_status_counts": status_counts,
            "pending_review": sum(1 for row in rows if row["human_review_status"] != "approved"),
            "approved": reviewed,
            "citation_truncated": citation_truncated,
            "source_link_rate": round(source_linked / max(1, total), 4) if total else 1.0,
            "review_coverage": round(reviewed / max(1, total), 4) if total else 1.0,
            "answers": rows[:limit],
        }

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

    def seed_default_incident_playbooks(self, payload: Mapping[str, Any] | None = None, *, actor: str = "system") -> dict[str, Any]:
        payload = payload or {}
        defaults = [
            {
                "playbook_id": "pb_document_parser_failure",
                "incident_type": "document_parser_failure",
                "detection_rule": "open manual reviews or OCR/parser failures",
                "auto_action": "route affected documents to manual review and block evidence use",
                "manual_action": "inspect parser logs, rerun OCR, and update parser regression samples",
                "owner_role": "NLP/ML 负责人",
            },
            {
                "playbook_id": "pb_data_ingestion_failure",
                "incident_type": "data_ingestion_failure",
                "detection_rule": "ingestion job failure, source review overdue, or data quality gap",
                "auto_action": "pause the affected source and keep last known good data",
                "manual_action": "verify source TOS/provenance, rerun ingestion, and document skipped records",
                "owner_role": "数据工程",
            },
            {
                "playbook_id": "pb_search_degradation",
                "incident_type": "search_degradation",
                "detection_rule": "search fallback or semantic benchmark recall drop",
                "auto_action": "fallback to local search and mark restricted results",
                "manual_action": "rebuild index, inspect embeddings/reranker, and rerun search benchmark",
                "owner_role": "平台负责人",
            },
            {
                "playbook_id": "pb_llm_gateway_failure",
                "incident_type": "llm_gateway_failure",
                "detection_rule": "LLM task error rate or budget alert",
                "auto_action": "use rule summary fallback and hold high-risk outputs for review",
                "manual_action": "check model/provider health, prompt approval, spend budget, and fallback quality",
                "owner_role": "NLP/ML 负责人",
            },
            {
                "playbook_id": "pb_permission_or_data_leak",
                "incident_type": "permission_or_data_leak",
                "detection_rule": "permission denied events or sensitive findings",
                "auto_action": "block unauthorized request and mask sensitive snippets",
                "manual_action": "review audit trail, rotate exposed keys, delete/cache-expire sensitive records if required",
                "owner_role": "风险/合规",
            },
        ]
        created_playbooks: list[IncidentPlaybook] = []
        created_schedules: list[DrillSchedule] = []
        create_schedules = self._truthy(payload.get("create_schedules", True))
        for item in defaults:
            playbook = self.store.playbooks.get(item["playbook_id"])
            if playbook is None:
                playbook = self.register_playbook(item, actor=actor)
            created_playbooks.append(playbook)
            if create_schedules:
                schedule_id = f"drill_{playbook.incident_type}_quarterly"
                schedule = self.store.drill_schedules.get(schedule_id)
                if schedule is None:
                    schedule = self.register_drill_schedule(
                        {
                            "schedule_id": schedule_id,
                            "incident_type": playbook.incident_type,
                            "cadence": "quarterly",
                            "owner": playbook.owner_role,
                            "notes": f"Quarterly tabletop drill for {playbook.incident_type}",
                        },
                        actor=actor,
                    )
                created_schedules.append(schedule)
        return {
            "playbooks": [to_plain(item) for item in created_playbooks],
            "schedules": [to_plain(item) for item in created_schedules],
        }

    def _ensure_generic_alert_playbook(self, *, actor: str = "system") -> IncidentPlaybook:
        playbook = self.store.playbooks.get("pb_generic_alert_triage")
        if playbook:
            return playbook
        return self.register_playbook(
            {
                "playbook_id": "pb_generic_alert_triage",
                "incident_type": "generic_alert_triage",
                "detection_rule": "open alert without a specific playbook",
                "auto_action": "keep the alert open and notify the owner",
                "manual_action": "triage owner, impact, rollback, and RCA follow-up",
                "owner_role": "风险/合规",
            },
            actor=actor,
        )

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
            {
                "rule_id": "alert_source_review_overdue",
                "metric": "source_review_overdue",
                "operator": ">",
                "threshold": 0,
                "severity": "medium",
                "owner": "风险/合规",
                "description": "Source governance reviews are overdue; confirm publicness, TOS, robots, and usage boundaries.",
            },
            {
                "rule_id": "alert_llm_cost_budget",
                "metric": "llm_tasks.cost_budget_used",
                "operator": ">=",
                "threshold": 1,
                "severity": "medium",
                "owner": "NLP/ML 负责人",
                "description": "LLM task estimated cost has reached the configured budget.",
            },
            {
                "rule_id": "alert_llm_error_rate",
                "metric": "llm_tasks.error_rate",
                "operator": ">",
                "threshold": 0.2,
                "severity": "medium",
                "owner": "NLP/ML 负责人",
                "description": "LLM task error rate exceeds budget and needs fallback review.",
            },
            {
                "rule_id": "alert_workflow_failed_runs",
                "metric": "workflow_failed_runs",
                "operator": ">",
                "threshold": 0,
                "severity": "high",
                "owner": "平台负责人",
                "description": "Workflow runs failed or need review; replay with frozen inputs and inspect lineage.",
            },
            {
                "rule_id": "alert_sensitive_findings",
                "metric": "sensitive_findings",
                "operator": ">",
                "threshold": 0,
                "severity": "high",
                "owner": "风险/合规",
                "description": "PII or secret-like literals were found in indexed data and require masking or deletion review.",
            },
            {
                "rule_id": "alert_permission_denied_events",
                "metric": "permission_denied_events",
                "operator": ">",
                "threshold": 0,
                "severity": "medium",
                "owner": "风险/合规",
                "description": "Unauthorized API access attempts were blocked and audited.",
            },
            {
                "rule_id": "alert_research_answer_pending_review",
                "metric": "research_answer_pending_reviews",
                "operator": ">",
                "threshold": 0,
                "severity": "medium",
                "owner": "海外研究负责人",
                "description": "Research answers are waiting for human review before production use.",
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

    def create_incidents_from_alerts(self, payload: Mapping[str, Any] | None = None, *, actor: str = "system") -> dict[str, Any]:
        payload = payload or {}
        alert_ids = {str(item) for item in payload.get("alert_ids", [])}
        include_without_playbook = self._truthy(payload.get("include_without_playbook", False))
        alerts = [item for item in self.store.system_alerts.values() if item.status == "open" and (not alert_ids or item.alert_id in alert_ids)]
        created: list[IncidentReport] = []
        skipped: list[dict[str, str]] = []
        for alert in alerts:
            if alert.incident_report_id:
                skipped.append({"alert_id": alert.alert_id, "reason": "already_linked", "incident_report_id": alert.incident_report_id})
                continue
            rule = self.store.alert_rules.get(alert.rule_id)
            playbook_id = alert.playbook_id or (rule.playbook_id if rule else "")
            if not playbook_id and include_without_playbook:
                playbook_id = self._ensure_generic_alert_playbook(actor=actor).playbook_id
            playbook = self.store.playbooks.get(playbook_id)
            if playbook is None:
                skipped.append({"alert_id": alert.alert_id, "reason": "missing_playbook"})
                continue
            report_id = f"ir_{alert.alert_id}"
            report = self.store.incident_reports.get(report_id)
            if report is None:
                report = IncidentReport(
                    report_id=report_id,
                    playbook_id=playbook.playbook_id,
                    incident_type=playbook.incident_type,
                    root_cause=str(payload.get("root_cause", "open_alert_requires_triage")),
                    impact=str(payload.get("impact", alert.message)),
                    action_items=[str(item) for item in payload.get("action_items", [playbook.auto_action, playbook.manual_action]) if str(item)],
                    owner=str(payload.get("owner", alert.owner or playbook.owner_role)),
                )
                self.store.incident_reports[report.report_id] = report
                created.append(report)
            alert.incident_report_id = report.report_id
            alert.updated_at = utcnow()
            self._audit(actor, "create_alert_incident", "incident", report.report_id, source="alerting", approval_state=alert.severity)
        return {"created": [to_plain(item) for item in created], "skipped": skipped, "count": len(created)}

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

    def semantic_search(self, filters: Mapping[str, Any]) -> dict[str, Any]:
        query = str(filters.get("q", "")).strip()
        if not query:
            return {"query": query, "results": []}
        issuer_filter = str(filters.get("issuer_id", "")).strip()
        resource_types = {str(item).strip() for item in filters.get("resource_types", []) if str(item).strip()} if isinstance(filters.get("resource_types", []), list) else set()
        include_restricted = self._truthy(filters.get("include_restricted", False))
        limit = self._bounded_limit(filters.get("limit", 20))
        records = self._search_records()
        if resource_types:
            records = [record for record in records if record.resource_type in resource_types]
        if not include_restricted:
            records = [record for record in records if self._search_record_boundary(record)["risk_level"] != "restricted"]
        sync_result = self.semantic_index.sync(records)
        results = self.semantic_index.search(records, query=query, issuer_id=issuer_filter, limit=limit)
        enriched_results = []
        for item in results:
            boundary = self._search_record_boundary_by_ref(str(item["resource_type"]), str(item["resource_id"]))
            enriched = dict(item)
            enriched["source_boundary"] = boundary["source_boundary"]
            enriched["rights_tag"] = boundary["rights_tag"]
            enriched["risk_level"] = boundary["risk_level"]
            if boundary["risk_level"] == "restricted":
                enriched["snippet"] = self._citation_limited_text(str(enriched.get("snippet", "")), source_publicness="restricted", char_limit=160)[0]
            enriched_results.append(enriched)
        return {
            "query": query,
            "backend": self.semantic_index.backend,
            "sync": sync_result,
            "results": enriched_results,
            "rights_filter": "inherits_search_record_scope",
            "payload_filter": {"issuer_id": issuer_filter, "resource_types": sorted(resource_types), "include_restricted": include_restricted},
        }

    def semantic_search_benchmark(self, filters: Mapping[str, Any]) -> dict[str, Any]:
        samples = filters.get("samples", [])
        if not isinstance(samples, list):
            raise ValidationError("semantic search benchmark requires samples list")
        limit = self._bounded_limit(filters.get("limit", 5), max_value=50)
        rows: list[dict[str, Any]] = []
        hits = 0
        for index, sample in enumerate(samples):
            if not isinstance(sample, Mapping):
                continue
            expected_ids = {str(item) for item in sample.get("expected_resource_ids", [])}
            result = self.semantic_search(
                {
                    "q": str(sample.get("q", "")),
                    "issuer_id": str(sample.get("issuer_id", "")),
                    "resource_types": sample.get("resource_types", []),
                    "include_restricted": bool(sample.get("include_restricted", False)),
                    "limit": limit,
                }
            )
            returned_ids = {str(item["resource_id"]) for item in result["results"]}
            hit = bool(expected_ids & returned_ids) if expected_ids else bool(returned_ids)
            hits += 1 if hit else 0
            rows.append({"index": index, "query": sample.get("q", ""), "expected_resource_ids": sorted(expected_ids), "returned_resource_ids": sorted(returned_ids), "hit": hit})
        return {"samples": len(rows), "hits": hits, "recall_at_k": round(hits / max(1, len(rows)), 4), "results": rows}

    def record_readiness_check(self, check_id: str, payload: Mapping[str, Any], *, actor: str = "system") -> ReadinessCheckRecord:
        check_id = str(check_id or payload.get("check_id", "")).strip()
        known = {item["check_id"] for item in READINESS_CHECKLIST_ITEMS}
        if check_id not in known:
            raise ValidationError(f"unknown readiness check_id: {check_id}")
        measured_at = parse_datetime(payload.get("measured_at")) if payload.get("measured_at") else utcnow()
        expires_at = parse_datetime(payload.get("expires_at")) if payload.get("expires_at") else None
        record = ReadinessCheckRecord(
            check_id=check_id,
            status=str(payload.get("status", "passed")),
            owner=str(payload.get("owner", actor)),
            evidence_uri=str(payload.get("evidence_uri", "")),
            notes=str(payload.get("notes", "")),
            metrics=dict(payload.get("metrics", {})),
            measured_at=measured_at,
            expires_at=expires_at,
            updated_at=utcnow(),
        )
        action = "update_readiness_check" if check_id in self.store.readiness_checks else "record_readiness_check"
        self.store.readiness_checks[check_id] = record
        self._audit(actor, action, "readiness_check", check_id, approval_state=record.status)
        return record

    def readiness_checklist_payload(self, filters: Mapping[str, Any] | None = None) -> dict[str, Any]:
        filters = filters or {}
        status_filter = str(filters.get("status", "")).strip()
        owner_role_filter = str(filters.get("owner_role", "")).strip()
        now = utcnow()
        rows: list[dict[str, Any]] = []
        for item in READINESS_CHECKLIST_ITEMS:
            record = self.store.readiness_checks.get(str(item["check_id"]))
            row: dict[str, Any] = {
                **item,
                "status": "pending",
                "effective_status": "pending",
                "owner": item["owner_role"],
                "evidence_uri": "",
                "notes": "",
                "metrics": {},
                "measured_at": None,
                "expires_at": None,
                "updated_at": None,
            }
            if record:
                row.update(to_plain(record))
                effective_status = record.status
                if record.status == "passed" and record.expires_at and record.expires_at < now:
                    effective_status = "expired"
                row["effective_status"] = effective_status
            if status_filter and row["effective_status"] != status_filter and row["status"] != status_filter:
                continue
            if owner_role_filter and row["owner_role"] != owner_role_filter:
                continue
            rows.append(row)
        required_rows = [item for item in rows if item["required"]]
        passed_rows = [item for item in required_rows if item["effective_status"] == "passed"]
        pending = [item["check_id"] for item in required_rows if item["effective_status"] != "passed"]
        return {
            "required": len(required_rows),
            "passed": len(passed_rows),
            "coverage": round(len(passed_rows) / max(1, len(required_rows)), 4) if required_rows else 1.0,
            "pending_checklist": pending,
            "checks": rows,
        }

    def vision_acceptance_report(self) -> dict[str, Any]:
        documents = list(self.store.documents.values())
        documents_with_evidence = {item.document_id for item in self.store.evidence.values()}
        evidence_coverage = len(documents_with_evidence) / max(1, len(documents)) if documents else 0.0
        theses = list(self.store.theses.values())
        conclusions_with_evidence = [item for item in theses if item.evidence_ids]
        conclusion_link_rate = len(conclusions_with_evidence) / max(1, len(theses)) if theses else 0.0
        pending_prompt_changes = sum(1 for item in self.store.prompt_changes.values() if item.status == "pending")
        high_risk_theses = [item for item in theses if item.confidence < 0.5 or item.status in {"review", "approved"}]
        challenged = {item.thesis_id for item in self.store.challengers.values()}
        high_risk_challenger_coverage = len([item for item in high_risk_theses if item.thesis_id in challenged]) / max(1, len(high_risk_theses)) if high_risk_theses else 1.0
        red_zone_training_records = self._red_zone_training_records()
        latest_benchmark = max(self.store.benchmark_runs.values(), key=lambda item: item.created_at, default=None)
        benchmark_metrics = latest_benchmark.metrics if latest_benchmark else {}
        entity_quality = self.entity_mapping_quality_report({})
        source_governance = self.source_governance_report({})
        audit_completeness = self.audit_completeness_report({})
        readiness_checklist = self.readiness_checklist_payload({})
        incident_drill_coverage = self._incident_drill_coverage()
        gates = [
            self._gate("evidence_coverage", evidence_coverage, 0.95, ">="),
            self._gate("research_conclusion_source_link_rate", conclusion_link_rate, 0.95, ">="),
            self._gate("pending_prompt_changes", float(pending_prompt_changes), 0.0, "=="),
            self._gate("red_zone_training_records", float(red_zone_training_records), 0.0, "=="),
            self._gate("high_risk_challenger_coverage", high_risk_challenger_coverage, 1.0, ">="),
            self._gate("source_governance_coverage", float(source_governance.get("coverage", 0.0)), 0.95, ">="),
            self._gate("audit_completeness", float(audit_completeness.get("coverage", 0.0)), 1.0, ">="),
            self._gate("entity_mapping_accuracy", float(entity_quality.get("accuracy", 0.0)), 0.98, ">="),
            self._gate("core_terms_f1", float(benchmark_metrics.get("term_f1", benchmark_metrics.get("core_terms_f1", 0.0))), 0.90, ">="),
            self._gate("evidence_page_hit_rate", float(benchmark_metrics.get("page_hit_rate", 0.0)), 0.95, ">="),
            self._gate("numeric_mapping_accuracy", float(benchmark_metrics.get("number_recall", benchmark_metrics.get("numeric_mapping_accuracy", 0.0))), 0.92, ">="),
            self._gate("quarterly_incident_drill_coverage", incident_drill_coverage, 1.0, ">="),
            self._gate("readiness_checklist_coverage", float(readiness_checklist["coverage"]), 1.0, ">="),
        ]
        pending_checklist = readiness_checklist["pending_checklist"]
        status = "ready" if all(item["passed"] for item in gates) and not pending_checklist else "not_ready"
        return {
            "status": status,
            "gates": gates,
            "readiness_checklist": readiness_checklist["checks"],
            "readiness_checklist_coverage": readiness_checklist["coverage"],
            "pending_checklist": pending_checklist,
            "counts": {
                "documents": len(documents),
                "theses": len(theses),
                "benchmark_runs": len(self.store.benchmark_runs),
                "entity_mappings": len(self.store.entity_mappings),
                "sources": len(self.store.sources),
                "readiness_checks": len(self.store.readiness_checks),
                "incident_playbooks": len(self.store.playbooks),
                "incident_drill_schedules": len(self.store.drill_schedules),
                "incident_reports": len(self.store.incident_reports),
                "audit_events": len(self.store.audit_log),
            },
        }

    def _gate(self, name: str, value: float, threshold: float, operator: str) -> dict[str, Any]:
        if operator == ">=":
            passed = value >= threshold
        elif operator == "==":
            passed = value == threshold
        else:
            raise ValidationError(f"unsupported gate operator: {operator}")
        return {"name": name, "value": round(value, 4), "threshold": threshold, "operator": operator, "passed": passed}

    def _red_zone_training_records(self) -> int:
        red_sources = {source.source_id for source in self.store.sources.values() if source.risk_level == "red" or source.rights_tag.training_allowed}
        documents = [item for item in self.store.documents.values() if item.source_id in red_sources]
        reports = [item for item in self.store.research_reports.values() if item.source_id in red_sources]
        return len(documents) + len(reports)

    def _incident_drill_coverage(self) -> float:
        incident_types = {item.incident_type for item in self.store.playbooks.values()}
        if not incident_types:
            return 0.0
        scheduled_types = {item.incident_type for item in self.store.drill_schedules.values()}
        reported_types = {item.incident_type for item in self.store.incident_reports.values()}
        covered = incident_types & scheduled_types & reported_types
        return round(len(covered) / max(1, len(incident_types)), 4)

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
        for report in self.store.research_reports.values():
            records.append(
                SearchRecord(
                    resource_type="research_report",
                    resource_id=report.report_id,
                    issuer_id="",
                    title=report.title,
                    body=f"{report.broker} {report.file_name} {report.year} {report.month} {report.status} {report.source_id}",
                    weight=0.9,
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

    def _search_record_boundary(self, record: SearchRecord) -> dict[str, Any]:
        return self._search_record_boundary_by_ref(record.resource_type, record.resource_id)

    def _search_record_boundary_by_ref(self, resource_type: str, resource_id: str) -> dict[str, Any]:
        rights: RightsTag | None = None
        source_boundary = "unknown"
        if resource_type == "document":
            document = self.store.documents.get(resource_id)
            rights = document.rights_tag if document else None
            source_boundary = document.source_id if document else "unknown"
        elif resource_type == "evidence":
            evidence = self.store.evidence.get(resource_id)
            document = self.store.documents.get(evidence.document_id) if evidence else None
            rights = document.rights_tag if document else None
            source_boundary = document.source_id if document else "unknown"
        elif resource_type == "research_report":
            report = self.store.research_reports.get(resource_id)
            rights = report.rights_tag if report else None
            source_boundary = report.source_id if report else "unknown"
        elif resource_type == "research_answer":
            answer = self.store.research_answers.get(resource_id)
            source_boundary = answer.source_publicness if answer else "unknown"
        if rights is None:
            return {"source_boundary": source_boundary or "unknown", "rights_tag": {}, "risk_level": "allowed"}
        risk_level = "restricted" if rights.display_use == "restricted" or rights.non_display_use == "restricted" else "allowed"
        return {"source_boundary": source_boundary, "rights_tag": to_plain(rights), "risk_level": risk_level}

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
            "semantic_index": self.semantic_index.describe(),
            "llm_gateway": self.llm_gateway.describe(),
            "document_parser": self.document_parser.describe(),
            "tdx_market_data": self.tdx_market_data.describe(),
            "tdx_vipdoc": self.tdx_vipdoc.describe(),
        }

    def metrics(self) -> dict[str, Any]:
        dashboard = self.dashboard()
        source_review_reminders = self.source_review_reminders_payload({"due_within_days": 30, "limit": 1000})
        failed_workflow_runs = sum(1 for item in self.store.workflow_runs.values() if item.status in {"failed", "needs_review"})
        running_workflow_runs = sum(1 for item in self.store.workflow_runs.values() if item.status in {"queued", "running"})
        sensitive_findings = self.data_security_report({"limit": 1000})["total"]
        answer_quality = self.research_answer_quality_report({"limit": 1000})
        permission_denied_events = sum(1 for item in self.store.audit_log if item.action == "permission_denied")
        return {
            "counts": dashboard["counts"],
            "audit_events": len(self.store.audit_log),
            "latest_audit": dashboard["latest_audit"],
            "open_exceptions": dashboard["counts"]["open_exceptions"],
            "pending_prompt_changes": sum(1 for item in self.store.prompt_changes.values() if item.status == "pending"),
            "source_review_overdue": source_review_reminders["overdue"],
            "source_review_due_soon": source_review_reminders["due_soon"],
            "source_review_missing": source_review_reminders["missing_review"],
            "workflow_failed_runs": failed_workflow_runs,
            "workflow_running_runs": running_workflow_runs,
            "sensitive_findings": sensitive_findings,
            "research_answer_pending_reviews": answer_quality["pending_review"],
            "research_answer_source_link_rate": answer_quality["source_link_rate"],
            "permission_denied_events": permission_denied_events,
            "object_store": self.object_store.describe(),
            "search_index": self.search_index.describe(),
            "semantic_index": self.semantic_index.describe(),
            "llm_gateway": self.llm_gateway.describe(),
            "llm_tasks": self.llm_task_metrics(),
            "document_parser": self.document_parser.describe(),
            "tdx_market_data": self.tdx_market_data.describe(),
            "tdx_vipdoc": self.tdx_vipdoc.describe(),
            "store": type(self.store).__name__,
        }

    def dashboard(self) -> dict[str, Any]:
        pending_decisions = sum(1 for decision in self.store.decisions.values() if decision.approval_state == "pending")
        approved_decisions = sum(1 for decision in self.store.decisions.values() if decision.approval_state == "approved")
        open_exceptions = sum(1 for item in self.store.exceptions.values() if item.status == "open")
        open_manual_reviews = sum(1 for item in self.store.manual_reviews.values() if item.status == "open")
        open_alerts = sum(1 for item in self.store.system_alerts.values() if item.status == "open")
        source_review_reminders = self.source_review_reminders_payload({"due_within_days": 30, "limit": 10})
        sensitive_findings = self.data_security_report({"limit": 1000})["total"]
        answer_quality = self.research_answer_quality_report({"limit": 1000})
        permission_denied_events = sum(1 for item in self.store.audit_log if item.action == "permission_denied")
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
                "astock_connectors": len(self.store.astock_connectors),
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
                "research_reports": len(self.store.research_reports),
                "llm_task_templates": len(self.store.llm_task_templates),
                "llm_task_runs": len(self.store.llm_task_runs),
                "workflow_definitions": len(self.store.workflow_definitions),
                "workflow_runs": len(self.store.workflow_runs),
                "lineage_events": len(self.store.lineage_events),
                "model_versions": len(self.store.model_versions),
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
                "source_review_overdue": source_review_reminders["overdue"],
                "source_review_due_soon": source_review_reminders["due_soon"],
                "source_review_missing": source_review_reminders["missing_review"],
                "sensitive_findings": sensitive_findings,
                "research_answer_pending_reviews": answer_quality["pending_review"],
                "permission_denied_events": permission_denied_events,
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
            "source_review_reminders": source_review_reminders["reminders"],
            "source_review_owner_board": source_review_reminders["owner_board"],
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

    def _bounded_limit(self, value: Any, max_value: int = 100) -> int:
        return max(1, min(max_value, int(value)))

    def _truthy(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() not in {"", "0", "false", "no", "off"}
        return bool(value)

    def _parse_quality_date(self, value: str) -> date | None:
        try:
            return date.fromisoformat(str(value))
        except ValueError:
            return None

    def _canonical_source_id(self, source_id: str) -> str:
        return SOURCE_ID_ALIASES.get(str(source_id).strip(), str(source_id).strip())

    def _default_source_review_owner_role(self, source: SourceDefinition) -> str:
        if source.source_type in {"regulatory", "exchange", "public_market_data", "public_web", "third_party_connector"}:
            return "数据工程"
        if source.source_type in {"company_ir", "local_reference", "manual_reference"}:
            return "风险/合规"
        return "平台负责人"

    def _source_review_owner_role(self, source: SourceDefinition) -> str:
        return source.review_owner_role or self._default_source_review_owner_role(source)

    def _source_review_owner(self, source: SourceDefinition) -> str:
        return source.review_owner or self._source_review_owner_role(source)

    def _market_data_adjustment_factor(self, point: MarketDataPoint, actions: list[CorporateAction], *, adjustment_mode: str) -> tuple[float, list[str]]:
        if adjustment_mode == "raw":
            return 1.0, []
        factor = 1.0
        event_ids: list[str] = []
        for action in actions:
            applies = action.ex_date > point.as_of_date if adjustment_mode == "backward" else action.ex_date <= point.as_of_date
            if not applies:
                continue
            event_factor = self._corporate_action_price_factor(action, adjustment_mode=adjustment_mode)
            if event_factor == 1.0:
                continue
            factor *= event_factor
            event_ids.append(action.action_id)
        return factor, event_ids

    def _corporate_action_price_factor(self, action: CorporateAction, *, adjustment_mode: str) -> float:
        ratio = float(action.ratio or 1.0)
        if ratio <= 0:
            return 1.0
        if action.action_type == "split":
            return (1.0 / ratio) if adjustment_mode == "backward" else ratio
        if action.action_type == "reverse_split":
            return ratio if adjustment_mode == "backward" else (1.0 / ratio)
        if action.action_type == "stock_dividend":
            base = 1.0 + ratio
            return (1.0 / base) if adjustment_mode == "backward" else base
        return 1.0

    def _cash_dividend_for_date(self, as_of_date: str, actions: list[CorporateAction]) -> float:
        return sum(float(action.cash_amount or 0.0) for action in actions if action.action_type == "cash_dividend" and action.ex_date == as_of_date)

    def _latest_market_data_point(self, security_id: str, *, source_id: str, data_type: str, as_of_date: str) -> MarketDataPoint | None:
        points = [
            point
            for point in self.store.market_data.values()
            if point.security_id == security_id and point.source_id == source_id and point.data_type == data_type and point.as_of_date <= as_of_date
        ]
        points.sort(key=lambda item: item.as_of_date, reverse=True)
        return points[0] if points else None

    def _normalize_operating_red_flag(self, item: Mapping[str, Any], *, report_id: str, index: int, period: str) -> dict[str, Any]:
        normalized = dict(item)
        normalized.setdefault("red_flag_id", f"{report_id}_rf_{index}")
        normalized.setdefault("status", "open")
        owner = str(normalized.get("owner", normalized.get("owner_role", "风险/合规")))
        normalized["owner"] = owner
        normalized.setdefault("owner_role", owner)
        normalized.setdefault("due", "month_end")
        normalized.setdefault("due_date", self._red_flag_due_date(str(normalized.get("due", "")), period))
        normalized.setdefault("created_at", to_plain(utcnow()))
        return normalized

    def _red_flag_due_date(self, due: str, period: str) -> str:
        due = str(due or "").strip()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", due):
            return due
        if due in {"next_review", "committee", "before_release", "month_end", ""}:
            try:
                year_text, month_text = period.split("-", maxsplit=1)
                year = int(year_text)
                month = int(month_text)
                if month == 12:
                    next_month = date(year + 1, 1, 1)
                else:
                    next_month = date(year, month + 1, 1)
                return (next_month - timedelta(days=1)).isoformat()
            except (ValueError, TypeError):
                return utcnow().date().isoformat()
        return utcnow().date().isoformat()

    def _validate_market_data_field_boundary(self, payload: Mapping[str, Any], source: SourceDefinition) -> None:
        if not source.field_whitelist:
            return
        operational_fields = {"data_id", "security_id", "source_id", "market", "as_of_date", "data_type", "currency", "rights_tag"}
        allowed_fields = set(source.field_whitelist) | operational_fields
        unknown_fields = sorted(str(key) for key in payload if str(key) not in allowed_fields)
        if unknown_fields:
            raise ValidationError(f"market data fields exceed source whitelist: {', '.join(unknown_fields)}")

    def _review_period(self, reviewed_at: Any) -> str:
        month = int(reviewed_at.month)
        quarter = (month - 1) // 3 + 1
        return f"{reviewed_at.year}Q{quarter}"

    def _next_source_review_due_at(self, reviewed_at: Any, cadence: str) -> Any:
        cadence = str(cadence or "quarterly").strip().lower()
        days_by_cadence = {
            "monthly": 30,
            "quarterly": 90,
            "semiannual": 182,
            "semi-annually": 182,
            "annual": 365,
            "yearly": 365,
        }
        days = days_by_cadence.get(cadence, 90)
        return reviewed_at + timedelta(days=days)

    def _source_initial_review_due_at(self, source: SourceDefinition, as_of: Any) -> Any:
        if source.last_reviewed_at:
            return self._next_source_review_due_at(source.last_reviewed_at, source.review_cadence)
        return as_of

    def _source_review_overdue(self, review: SourceReviewRecord | None) -> bool:
        return bool(review and review.next_review_due_at and review.next_review_due_at < utcnow())

    def _source_review_blockers(self, review: SourceReviewRecord) -> list[str]:
        blockers: list[str] = []
        if review.status == "rejected":
            blockers.append("latest_source_review_rejected")
        if review.publicness_status == "unclear":
            blockers.append("latest_source_publicness_unclear")
        if review.tos_status == "needs_review":
            blockers.append("latest_source_tos_needs_review")
        if review.robots_status in {"blocked", "needs_review"}:
            blockers.append(f"latest_source_robots_{review.robots_status}")
        if review.usage_scope_status == "blocked":
            blockers.append("latest_source_usage_scope_blocked")
        return blockers

    def _normalize_astock_connector_row(self, connector: AStockConnectorDefinition, row: Mapping[str, Any]) -> dict[str, Any]:
        normalized: dict[str, Any] = {
            "connector_id": connector.connector_id,
            "provider": connector.provider,
            "endpoint_type": connector.endpoint_type,
            "source_id": connector.source_id,
            "rights_tag": to_plain(connector.rights_tag),
        }
        for raw_field, target_field in connector.field_mapping.items():
            if raw_field in row:
                normalized[str(target_field)] = row[raw_field]
        for key in ("title", "source_uri", "published_at", "ticker", "security_code", "as_of_date", "event_date", "theme", "concept", "pe_ttm", "pb", "net_inflow"):
            if key in row and key not in normalized:
                normalized[key] = row[key]
        if "source_uri" in normalized:
            normalized["source_uri"] = self._sanitize_source_uri(str(normalized["source_uri"]))
        normalized["raw_keys"] = sorted(str(key) for key in row.keys())
        normalized["usage_boundary"] = "manual_reference_or_supplemental_research_only"
        return normalized

    def _astock_automation_blockers(self, connector: AStockConnectorDefinition, source: SourceDefinition) -> list[str]:
        blockers: list[str] = []
        if connector.status != "verified":
            blockers.append("connector_not_verified")
        if source.risk_level != "green":
            blockers.append(f"source_risk_{source.risk_level}")
        if source.source_type not in {"exchange", "regulatory", "public_market_data"}:
            blockers.append(f"source_type_{source.source_type}_not_core_fact_source")
        if connector.rights_tag.display_use == "restricted" or connector.rights_tag.non_display_use == "restricted":
            blockers.append("restricted_rights_manual_reference_only")
        if connector.rights_tag.training_allowed or connector.rights_tag.redistribution_allowed:
            blockers.append("training_or_redistribution_not_allowed")
        return blockers

    def _read_research_report_text(self, report: ResearchReportAsset) -> str:
        path = Path(report.file_path)
        if path.suffix.lower() == ".txt" and path.exists():
            try:
                return path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                return ""
        return ""

    def _research_report_citation_evidence(self, document: Document, text: str, *, parser_version: str) -> list[Evidence]:
        chunks = chunk_text(text)
        evidence: list[Evidence] = []
        for index, chunk in enumerate(chunks[:20]):
            evidence.append(
                Evidence(
                    evidence_id=f"evi_{document.document_id}_research_{index}",
                    document_id=document.document_id,
                    section="research_report_citation",
                    page_no=index + 1,
                    bbox=f"research_report://{document.document_id};chunk={index}",
                    span_text=chunk,
                    canonical_text=chunk,
                    confidence=0.72,
                )
            )
        return evidence

    def _tdx_symbols(self, payload: Mapping[str, Any]) -> list[str]:
        raw_symbols = payload.get("symbols", payload.get("symbol", []))
        if isinstance(raw_symbols, str):
            symbols = [item.strip() for item in raw_symbols.split(",")]
        elif isinstance(raw_symbols, list):
            symbols = [str(item).strip() for item in raw_symbols]
        else:
            symbols = []
        symbols = [self._normalize_tdx_symbol(symbol) for symbol in symbols if self._normalize_tdx_symbol(symbol)]
        if not symbols:
            raise ValidationError("TDX market data requires symbols")
        return list(dict.fromkeys(symbols))

    def _tdx_adapter(self, payload: Mapping[str, Any]) -> Any:
        source_format = str(payload.get("source_format", payload.get("adapter", "duckdb"))).strip().lower()
        if source_format in {"duckdb", "local_duckdb", ""}:
            return self.tdx_market_data
        if source_format in {"vipdoc", "day", "tdx_vipdoc"}:
            return self.tdx_vipdoc
        raise ValidationError("TDX source_format must be duckdb or vipdoc")

    def _resolve_tdx_security(self, symbol: str, security_map: Mapping[str, Any]) -> Security | None:
        mapped = str(security_map.get(symbol) or security_map.get(self._normalize_tdx_symbol(symbol)) or "").strip()
        if mapped and mapped in self.store.securities:
            return self.store.securities[mapped]
        normalized = self._normalize_tdx_symbol(symbol)
        if normalized in self.store.securities:
            return self.store.securities[normalized]
        for security in self.store.securities.values():
            if self._normalize_tdx_symbol(security.ticker) == normalized:
                return security
        return None

    def _normalize_tdx_symbol(self, symbol: str) -> str:
        value = str(symbol).strip().lower()
        value = re.sub(r"^(sh|sz|bj)", "", value)
        value = re.sub(r"\.(sh|sz|bj|ss|szse|sse)$", "", value)
        return re.sub(r"\D+", "", value)

    def _research_report_source_id(self, broker: str) -> str:
        return f"local_research_{safe_source_part(broker)}"

    def _ensure_research_report_source(self, source_id: str, broker: str, *, actor: str) -> None:
        if source_id in self.store.sources:
            return
        self.register_source(
            {
                "source_id": source_id,
                "source_type": "local_reference",
                "description": f"Local research report source for {broker}. External viewpoint only, not a fact source.",
                "risk_level": "yellow",
                "allowed_document_types": ["research"],
                "provenance_ref": f"local://research-reports/{safe_source_part(broker)}",
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
            actor=actor,
        )

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
        if licenses and all(item == "public" or item.startswith("public_") for item in licenses):
            return "public"
        if any("private" in item or "restricted" in item for item in licenses):
            return "restricted"
        return ",".join(sorted(licenses)) or "unknown"

    def _citation_limited_text(self, source_text: str, *, source_publicness: str, char_limit: int) -> tuple[str, bool]:
        if source_publicness == "public" or len(source_text) <= char_limit:
            return source_text, False
        clipped = source_text[:char_limit].rstrip()
        return f"{clipped}\n[TRUNCATED_FOR_CITATION_BOUNDARY]", True

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

    def _sanitize_source_uri(self, source_uri: str) -> str:
        value = str(source_uri or "").strip()
        if not value:
            return ""
        parsed = urlparse(value)
        if not parsed.scheme or not parsed.netloc:
            return value
        sensitive_keys = {"access_token", "api_key", "apikey", "auth", "key", "password", "secret", "signature", "token"}
        query = []
        for key, item_value in parse_qsl(parsed.query, keep_blank_values=True):
            query.append((key, "REDACTED" if key.lower() in sensitive_keys else item_value))
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, urlencode(query, doseq=True), ""))

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
