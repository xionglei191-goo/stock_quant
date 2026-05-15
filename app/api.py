from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable
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
            ("POST", r"^/api/demo/full-flow$", self._seed_demo_full_flow),
            ("GET", r"^/api/health$", self._health),
            ("GET", r"^/api/metrics$", self._metrics),
            ("POST", r"^/api/issuers$", self._register_issuer),
            ("POST", r"^/api/securities$", self._register_security),
            ("POST", r"^/api/market-data/points$", self._register_market_data_point),
            ("POST", r"^/api/market-data/batch$", self._register_market_data_batch),
            ("GET", r"^/api/market-data$", self._list_market_data),
            ("POST", r"^/api/corporate-actions$", self._register_corporate_action),
            ("GET", r"^/api/corporate-actions$", self._list_corporate_actions),
            ("POST", r"^/api/13f/holdings$", self._register_13f_holding),
            ("GET", r"^/api/13f/holdings$", self._list_13f_holdings),
            ("POST", r"^/api/13f/crowding/update$", self._update_crowding_from_13f),
            ("POST", r"^/api/disclosure-events$", self._create_disclosure_event),
            ("GET", r"^/api/disclosure-events$", self._list_disclosure_events),
            ("POST", r"^/api/disclosure-events/classify$", self._classify_disclosure_event),
            ("POST", r"^/api/entity-mappings$", self._register_entity_mapping),
            ("POST", r"^/api/entity-mappings/batch$", self._register_entity_mapping_batch),
            ("GET", r"^/api/entity-mappings/quality-report$", self._entity_mapping_quality_report),
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
            ("POST", r"^/api/benchmarks/(?P<benchmark_id>[^/]+)/evaluate$", self._evaluate_benchmark),
            ("POST", r"^/api/prompts/changes$", self._create_prompt_change),
            ("POST", r"^/api/prompts/changes/(?P<request_id>[^/]+)/approve$", self._approve_prompt_change),
            ("POST", r"^/api/templates$", self._register_template),
            ("POST", r"^/api/templates/seed$", self._seed_default_templates),
            ("POST", r"^/api/scorecards$", self._register_scorecard),
            ("POST", r"^/api/research-cards$", self._create_research_card),
            ("POST", r"^/api/research/answers$", self._create_research_answer),
            ("POST", r"^/api/research/answers/(?P<answer_id>[^/]+)/review$", self._review_research_answer),
            ("GET", r"^/api/research/answers/(?P<answer_id>[^/]+)$", self._get_research_answer),
            ("POST", r"^/api/extractions/run$", self._extract_structured_facts),
            ("GET", r"^/api/extractions/(?P<extraction_id>[^/]+)$", self._get_extraction_result),
            ("POST", r"^/api/evidence/extract$", self._extract_evidence),
            ("GET", r"^/api/evidence/manual-reviews$", self._list_manual_reviews),
            ("GET", r"^/api/evidence/quality-report$", self._evidence_quality_report),
            ("POST", r"^/api/thesis/create$", self._create_thesis),
            ("GET", r"^/api/thesis/(?P<thesis_id>[^/]+)$", self._get_thesis),
            ("POST", r"^/api/scoring/run$", self._run_scoring),
            ("POST", r"^/api/crowding/snapshots$", self._register_crowding_snapshot),
            ("POST", r"^/api/challenger/run$", self._run_challenger),
            ("POST", r"^/api/playbooks$", self._register_playbook),
            ("POST", r"^/api/drill-schedules$", self._register_drill_schedule),
            ("POST", r"^/api/incident-reports$", self._create_incident_report),
            ("POST", r"^/api/alerts/rules$", self._register_alert_rule),
            ("POST", r"^/api/alerts/rules/seed$", self._seed_default_alert_rules),
            ("POST", r"^/api/alerts/evaluate$", self._evaluate_alerts),
            ("POST", r"^/api/alerts/notify$", self._notify_alerts),
            ("GET", r"^/api/alerts/notifications$", self._list_alert_notifications),
            ("GET", r"^/api/alerts$", self._list_alerts),
            ("POST", r"^/api/llm/openai/chat/completions$", self._llm_openai_chat_completions),
            ("POST", r"^/api/llm/anthropic/messages$", self._llm_anthropic_messages),
            ("GET", r"^/api/signals/(?P<signal_id>[^/]+)$", self._get_signal),
            ("POST", r"^/api/decision-packs/build$", self._build_decision_pack),
            ("GET", r"^/api/decision-packs/(?P<decision_id>[^/]+)$", self._get_decision_pack),
            ("POST", r"^/api/approvals/(?P<decision_id>[^/]+)/sign$", self._sign_decision),
            ("POST", r"^/api/execution-intents$", self._create_execution_intent),
            ("GET", r"^/api/execution-intents/(?P<intent_id>[^/]+)$", self._get_execution_intent),
            ("POST", r"^/api/exceptions$", self._create_exception),
            ("POST", r"^/api/reviews/create$", self._create_review),
            ("GET", r"^/api/reviews/(?P<review_id>[^/]+)$", self._get_review),
            ("POST", r"^/api/operating-reports$", self._generate_operating_report),
            ("POST", r"^/api/operating-reports/(?P<report_id>[^/]+)/publish$", self._publish_operating_report),
            ("POST", r"^/api/operating-reports/(?P<report_id>[^/]+)/red-flags/(?P<red_flag_id>[^/]+)/resolve$", self._resolve_operating_report_red_flag),
            ("GET", r"^/api/operating-reports/(?P<report_id>[^/]+)$", self._get_operating_report),
            ("POST", r"^/api/strategy-replays$", self._create_strategy_replay),
            ("GET", r"^/api/strategy-replays$", self._list_strategy_replays),
            ("GET", r"^/api/strategy-replays/(?P<replay_id>[^/]+)$", self._get_strategy_replay),
            ("POST", r"^/api/portfolio/optimize$", self._run_portfolio_optimizer),
            ("GET", r"^/api/portfolio/proposals$", self._list_portfolio_proposals),
            ("GET", r"^/api/portfolio/proposals/(?P<proposal_id>[^/]+)$", self._get_portfolio_proposal),
            ("GET", r"^/api/graph/query$", self._query_graph),
            ("GET", r"^/api/search$", self._search),
            ("POST", r"^/api/search$", self._search),
            ("GET", r"^/api/dashboard/ceo$", self._dashboard_ceo),
            ("GET", r"^/api/dashboard/risk$", self._dashboard_risk),
            ("GET", r"^/api/incidents/calendar$", self._incident_calendar),
        ]
        for route_method, pattern, handler in routes:
            if route_method == method and re.fullmatch(pattern, path):
                return handler
        return None

    def _authorize(self, method: str, path: str, role: str) -> bool:
        if path.startswith("/api/health") or path.startswith("/api/metrics"):
            return True
        safe_roles = {"system", "CEO", "CIO", "PM", "风险/合规", "平台负责人", "分析师", "数据工程", "NLP/ML 负责人", "海外研究负责人"}
        if role not in safe_roles:
            return False
        if path.startswith("/api/dashboard"):
            return True
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
        if path.startswith("/api/ingestion/sources") or path.startswith("/api/ingestion/documents") or path.startswith("/api/ingestion/sec") or path.startswith("/api/ingestion/ashare") or path.startswith("/api/ingestion/hkex") or path.startswith("/api/ingestion/jobs") or path.startswith("/api/ingestion/schedules") or path.startswith("/api/entity-mappings") or path.startswith("/api/connectors/preview") or path.startswith("/api/connectors/sec") or path.startswith("/api/connectors/ashare") or path.startswith("/api/connectors/hkex"):
            return role in {"system", "风险/合规", "平台负责人", "数据工程"}
        if path.startswith("/api/benchmarks") or path.startswith("/api/prompts/changes") or path.startswith("/api/scorecards"):
            return role in {"system", "NLP/ML 负责人", "风险/合规", "平台负责人", "CIO"}
        if path.startswith("/api/templates") or path.startswith("/api/research-cards") or path.startswith("/api/research/answers") or path.startswith("/api/crowding") or path.startswith("/api/challenger") or path.startswith("/api/playbooks") or path.startswith("/api/incident-reports") or path.startswith("/api/drill-schedules") or path.startswith("/api/alerts"):
            return role in {"system", "NLP/ML 负责人", "风险/合规", "平台负责人", "CIO", "PM", "分析师", "海外研究负责人"}
        if path.startswith("/api/llm"):
            return role in {"system", "CEO", "CIO", "风险/合规", "平台负责人", "分析师", "NLP/ML 负责人", "海外研究负责人"}
        if path.startswith("/api/evidence") or path.startswith("/api/extractions") or path.startswith("/api/thesis") or path.startswith("/api/scoring"):
            return role in {"system", "分析师", "海外研究负责人", "CIO", "PM", "平台负责人", "NLP/ML 负责人", "风险/合规"}
        if path.startswith("/api/decision-packs") or path.startswith("/api/approvals") or path.startswith("/api/exceptions"):
            return role in {"system", "CEO", "CIO", "风险/合规"}
        if path.startswith("/api/execution-intents"):
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

    def _seed_demo_full_flow(self, _path: str, _body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.seed_demo_full_flow(actor=actor)

    def _health(self, _path: str, _body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.health()

    def _metrics(self, _path: str, _body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.metrics()

    def _register_issuer(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.register_issuer(body, actor=actor))

    def _register_security(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.register_security(body, actor=actor))

    def _register_market_data_point(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.register_market_data_point(body, actor=actor))

    def _register_market_data_batch(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.register_market_data_batch(body, actor=actor)

    def _list_market_data(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.market_data_payload(body)

    def _register_corporate_action(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.register_corporate_action(body, actor=actor))

    def _list_corporate_actions(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.corporate_actions_payload(body)

    def _register_13f_holding(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.register_13f_holding(body, actor=actor))

    def _list_13f_holdings(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.institutional_holdings_payload(body)

    def _update_crowding_from_13f(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.update_crowding_from_13f(body, actor=actor))

    def _create_disclosure_event(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.create_disclosure_event(body, actor=actor))

    def _list_disclosure_events(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.disclosure_events_payload(body)

    def _classify_disclosure_event(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.classify_disclosure_event(body, actor=actor))

    def _register_entity_mapping(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.register_entity_mapping(body, actor=actor))

    def _register_entity_mapping_batch(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.register_entity_mapping_batch(body, actor=actor)

    def _entity_mapping_quality_report(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.entity_mapping_quality_report(body)

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

    def _create_prompt_change(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.create_prompt_change(body, actor=actor))

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

    def _create_research_answer(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.create_research_answer(body, actor=actor))

    def _review_research_answer(self, path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        match = re.fullmatch(r"^/api/research/answers/(?P<answer_id>[^/]+)/review$", path)
        return to_plain(self.service.review_research_answer(match["answer_id"], body, actor=actor))

    def _get_research_answer(self, path: str, _body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        match = re.fullmatch(r"^/api/research/answers/(?P<answer_id>[^/]+)$", path)
        return self.service.research_answer_payload(match["answer_id"])

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

    def _register_drill_schedule(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.register_drill_schedule(body, actor=actor))

    def _create_incident_report(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.create_incident_report(body, actor=actor))

    def _register_alert_rule(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.register_alert_rule(body, actor=actor))

    def _seed_default_alert_rules(self, _path: str, _body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return {"rules": [to_plain(item) for item in self.service.seed_default_alert_rules(actor=actor)]}

    def _evaluate_alerts(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.evaluate_alerts(body, actor=actor)

    def _notify_alerts(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.notify_alerts(body, actor=actor)

    def _list_alert_notifications(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.alert_notifications_payload(body)

    def _list_alerts(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.alerts_payload(body)

    def _llm_openai_chat_completions(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.llm_openai_chat_completions(body, actor=actor)

    def _llm_anthropic_messages(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.llm_anthropic_messages(body, actor=actor)

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

    def _create_exception(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.create_exception(body, actor=actor)

    def _create_review(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.create_review(body, actor=actor))

    def _get_review(self, path: str, _body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        match = re.fullmatch(r"^/api/reviews/(?P<review_id>[^/]+)$", path)
        return self.service.review_payload(match["review_id"])

    def _generate_operating_report(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.generate_operating_report(body, actor=actor))

    def _publish_operating_report(self, path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        match = re.fullmatch(r"^/api/operating-reports/(?P<report_id>[^/]+)/publish$", path)
        return to_plain(self.service.publish_operating_report(match["report_id"], body, actor=actor))

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

    def _get_strategy_replay(self, path: str, _body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        match = re.fullmatch(r"^/api/strategy-replays/(?P<replay_id>[^/]+)$", path)
        return self.service.strategy_replay_payload(match["replay_id"])

    def _run_portfolio_optimizer(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return to_plain(self.service.run_portfolio_optimizer(body, actor=actor))

    def _list_portfolio_proposals(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.list_portfolio_proposals(body)

    def _get_portfolio_proposal(self, path: str, _body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        match = re.fullmatch(r"^/api/portfolio/proposals/(?P<proposal_id>[^/]+)$", path)
        return self.service.portfolio_proposal_payload(match["proposal_id"])

    def _query_graph(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.query_graph(body)

    def _search(self, _path: str, body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.search(body)

    def _dashboard_ceo(self, _path: str, _body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.dashboard()

    def _dashboard_risk(self, _path: str, _body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.dashboard()

    def _incident_calendar(self, _path: str, _body: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self.service.incident_calendar()


def create_default_router() -> ApiRouter:
    return ApiRouter()
