from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
import re
from io import StringIO
from typing import Any, Callable, Iterable, Mapping, Protocol


class SecurityLike(Protocol):
    security_id: str
    ticker: str
    figi: str
    isin: str


class EntityMappingLike(Protocol):
    mapping_id: str
    ticker: str
    figi: str
    isin: str
    cik: str
    lei: str


class IssuerLike(Protocol):
    issuer_id: str
    legal_name: str
    cik: str
    lei: str
    aliases: list[str]


SECTION_SPECS = [
    ("company_profile", "公司画像", "profile_available", 0.22, True, "fact_or_governed_record", "运行单标的研究或登记主体/证券"),
    ("market_data", "行情快照", "market_data_available", 0.14, True, "public_or_local_market_data", "导入公开/本地 EOD 行情"),
    ("events", "事件时间线", "event_timeline_available", 0.16, True, "official_public_fact_or_reviewed_event", "执行事件构建或补充公告证据"),
    ("relationships", "关系图谱", "relationship_graph_available", 0.16, True, "fact_or_reviewed_relationship_candidate", "执行关系构建并审核候选"),
    ("research_results", "研究观点", "research_results_available", 0.16, False, "opinion_layer_not_fact_source", "结构化研报或记录研究答案"),
    ("simulation_feedback", "模拟反馈", "simulation_feedback_available", 0.10, False, "paper_only_feedback", "记录 paper-only 模拟反馈"),
]


def symbol_tokens(symbol: str, *, normalize_us_symbol: Callable[[str], str], normalize_tdx_symbol: Callable[[str], str]) -> set[str]:
    raw = str(symbol or "").strip()
    if not raw:
        return set()
    upper = raw.upper()
    tokens = {raw, upper}
    us_symbol = normalize_us_symbol(raw)
    if us_symbol:
        tokens.add(us_symbol)
    tdx_symbol = normalize_tdx_symbol(raw)
    if tdx_symbol:
        tokens.add(tdx_symbol)
        tokens.add(f"SH{tdx_symbol}")
        tokens.add(f"SZ{tdx_symbol}")
        tokens.add(f"{tdx_symbol}.SH")
        tokens.add(f"{tdx_symbol}.SZ")
    return {token for token in tokens if token}


def security_matches(security: SecurityLike, tokens: set[str]) -> bool:
    values = {
        security.security_id,
        security.ticker,
        security.figi,
        security.isin,
    }
    return any(str(value).strip().upper() in tokens for value in values if str(value).strip())


def mapping_matches(mapping: EntityMappingLike, tokens: set[str]) -> bool:
    values = {mapping.mapping_id, mapping.ticker, mapping.figi, mapping.isin, mapping.cik, mapping.lei}
    return any(str(value).strip().upper() in tokens for value in values if str(value).strip())


def issuer_matches(issuer: IssuerLike, tokens: set[str]) -> bool:
    values = {issuer.issuer_id, issuer.legal_name, issuer.cik, issuer.lei, *issuer.aliases}
    return any(str(value).strip().upper() in tokens for value in values if str(value).strip())


def verdict_section_count(section: str, section_counts: Mapping[str, Any]) -> int:
    if section == "company_profile":
        return int(section_counts.get("company_profiles", 0) or 0) + int(section_counts.get("securities", 0) or 0)
    if section == "market_data":
        return int(section_counts.get("market_data", 0) or 0)
    if section == "events":
        return int(section_counts.get("company_events", 0) or 0) + int(section_counts.get("disclosure_events", 0) or 0)
    if section == "relationships":
        return int(section_counts.get("company_relationships", 0) or 0) + int(section_counts.get("graph_edges", 0) or 0)
    if section == "research_results":
        return int(section_counts.get("research_reports", 0) or 0) + int(section_counts.get("structured_research_reports", 0) or 0) + int(section_counts.get("report_viewpoints", 0) or 0) + int(section_counts.get("analysis_conclusions", 0) or 0)
    if section == "simulation_feedback":
        return int(section_counts.get("simulation_feedback_records", 0) or 0) + int(section_counts.get("simulated_executions", 0) or 0) + int(section_counts.get("portfolio_transactions", 0) or 0)
    return 0


def verdict_next_action(symbol: str, blocking_gaps: list[str], warning_gaps: list[str], data_quality: Mapping[str, Any]) -> dict[str, str]:
    action_map = {
        "company_profile": ("bootstrap_company_database", f"为 {symbol.upper()} 建立本地公司主体"),
        "market_data": ("coverage_audit", "补齐公开或本地行情"),
        "events": ("preview_batch_build", "生成公司事件时间线"),
        "relationships": ("preview_batch_build", "生成并审核公司关系"),
        "research_results": ("preview_research_structure", "结构化研报观点"),
        "simulation_feedback": ("record_simulation_feedback", "记录 paper-only 模拟反馈"),
        "event_evidence_backlinks": ("coverage_audit", "补齐事件证据回链"),
        "relationship_evidence_backlinks": ("coverage_audit", "补齐关系证据回链"),
    }
    for gap in [*blocking_gaps, *warning_gaps]:
        action, label = action_map.get(gap, ("coverage_audit", "查看覆盖审计"))
        return {"action": action, "label": label, "reason": f"完整度判断仍缺 {gap}"}
    if not data_quality.get("research_results_available"):
        return {"action": "preview_research_structure", "label": "结构化研报观点", "reason": "事实层可用后需要观点层支撑分析"}
    if not data_quality.get("simulation_feedback_available"):
        return {"action": "record_simulation_feedback", "label": "记录模拟反馈", "reason": "分析结果需要 paper-only 反馈验证"}
    return {"action": "none", "label": "继续复盘", "reason": "主要公司情报层已可用"}


def completeness_verdict(
    symbol: str,
    data_quality: Mapping[str, Any],
    section_counts: Mapping[str, Any],
    *,
    database_coverage: Mapping[str, Any],
    profile_field_coverage: Mapping[str, Any],
    deep_coverage_fields: Callable[..., list[str]],
) -> dict[str, Any]:
    profile_coverage = max(0.0, min(1.0, float(data_quality.get("profile_coverage", 0.0) or 0.0)))
    event_backlink_rate = max(0.0, min(1.0, float(data_quality.get("event_backlink_rate", 0.0) or 0.0)))
    relationship_backlink_rate = max(0.0, min(1.0, float(data_quality.get("relationship_backlink_rate", 0.0) or 0.0)))
    evidence_score = round(((event_backlink_rate + relationship_backlink_rate) / 2.0) if (event_backlink_rate or relationship_backlink_rate) else 0.0, 4)
    sections: list[dict[str, Any]] = []
    score = 0.0
    blocking_gaps: list[str] = []
    warning_gaps: list[str] = []
    for section, label, quality_key, weight, blocking, source_policy, action in SECTION_SPECS:
        available = bool(data_quality.get(quality_key))
        contribution = weight * max(0.5, profile_coverage) if section == "company_profile" and available else weight if available else 0.0
        score += contribution
        gap = not available
        if gap and blocking:
            blocking_gaps.append(section)
        elif gap:
            warning_gaps.append(section)
        sections.append(
            {
                "section": section,
                "label": label,
                "available": available,
                "blocking": blocking,
                "weight": weight,
                "score_contribution": round(contribution, 4),
                "source_policy": source_policy,
                "recommended_action": action,
                "record_count": int(section_counts.get(section, 0) or 0)
                if section in section_counts
                else verdict_section_count(section, section_counts),
            }
        )
    if event_backlink_rate == 0.0 and data_quality.get("event_timeline_available"):
        warning_gaps.append("event_evidence_backlinks")
    if relationship_backlink_rate == 0.0 and data_quality.get("relationship_graph_available"):
        warning_gaps.append("relationship_evidence_backlinks")
    score = min(1.0, score + (0.06 * evidence_score))
    ready_for_fact_review = not blocking_gaps
    ready_for_analysis = ready_for_fact_review and bool(data_quality.get("research_results_available"))
    ready_for_feedback_review = ready_for_analysis and bool(data_quality.get("simulation_feedback_available"))
    required_layers = [section for section, _label, _quality_key, _weight, _blocking, _source_policy, _action in SECTION_SPECS]
    missing_layers = list(dict.fromkeys([*blocking_gaps, *warning_gaps]))
    database_coverage_score = max(0.0, min(1.0, float(database_coverage.get("coverage_score", 0.0) or 0.0)))
    profile_field_coverage_score = max(0.0, min(1.0, float(profile_field_coverage.get("field_coverage_score", 0.0) or 0.0)))
    required_fact_fields = [str(field) for field in (profile_field_coverage.get("required_fields") or deep_coverage_fields(include_optional=False))]
    missing_fact_fields = [str(field) for field in profile_field_coverage.get("missing_fields", [])]
    if score >= 0.9 and not missing_layers:
        level = "complete"
    elif score >= 0.7:
        level = "near_complete"
    elif score >= 0.35:
        level = "partial"
    else:
        level = "sparse"
    if not data_quality.get("profile_available"):
        status = "not_found"
        label = "未建档"
    elif blocking_gaps:
        status = "incomplete"
        label = "需要补库"
    elif ready_for_feedback_review and score >= 0.9 and not warning_gaps:
        status = "complete"
        label = "完整"
    else:
        status = "usable_with_gaps"
        if ready_for_feedback_review:
            label = "可复盘"
        elif ready_for_analysis:
            label = "可分析"
        elif ready_for_fact_review:
            label = "事实层可用"
        else:
            label = "可用但有缺口"
    recommended_next_action = verdict_next_action(symbol, blocking_gaps, warning_gaps, data_quality)
    return {
        "schema_id": "company-intelligence-completeness-verdict-v1",
        "status": status,
        "label": label,
        "is_complete": status == "complete",
        "level": level,
        "score": round(score, 4),
        "required_layers": required_layers,
        "missing_layers": missing_layers,
        "database_coverage_score": database_coverage_score,
        "profile_field_coverage_score": profile_field_coverage_score,
        "required_fact_fields": required_fact_fields,
        "missing_fact_fields": missing_fact_fields,
        "blocking_gaps": list(dict.fromkeys(blocking_gaps)),
        "warning_gaps": list(dict.fromkeys(warning_gaps)),
        "ready_for_fact_review": ready_for_fact_review,
        "ready_for_analysis": ready_for_analysis,
        "ready_for_feedback_review": ready_for_feedback_review,
        "sections": sections,
        "evidence_backlink_score": evidence_score,
        "profile_coverage": profile_coverage,
        "source_policy_summary": {
            "fact_fields": "official_disclosure_company_ir_public_market_or_governed_local_records_only",
            "research_reports": "opinion_and_attention_slots_only_not_fact_source",
            "research_reports_can_complete_fact_fields": False,
        },
        "recommended_actions": [recommended_next_action] if recommended_next_action.get("action") != "none" else [],
        "usage_boundary": "completeness_verdict_is_data_readiness_only_not_investment_advice_no_live_trading",
        "recommended_next_action": recommended_next_action,
    }


def _plain(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    result: dict[str, Any] = {}
    for name in getattr(value, "__dataclass_fields__", {}):
        result[name] = getattr(value, name)
    return result


def _first_text(row: Mapping[str, Any], keys: Iterable[str], default: str = "") -> str:
    for key in keys:
        value = str(row.get(key, "") or "").strip()
        if value:
            return value
    return default


def _issuer_label(issuer_id: str, issuers: Mapping[str, Mapping[str, Any]]) -> str:
    issuer = issuers.get(issuer_id, {})
    return _first_text(issuer, ["display_name", "legal_name", "name"], issuer_id)


def _node_label(chain: Mapping[str, Any], node_id: str) -> str:
    for node in chain.get("nodes", []) or []:
        if str(node.get("node_id", "")).strip() == node_id:
            return _first_text(node, ["name", "label", "node_id"], node_id)
    return node_id


def _dedupe_rows(rows: Iterable[Mapping[str, Any]], key: str) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for row in rows:
        value = str(row.get(key, "") or "").strip()
        if not value or value in seen:
            continue
        result.append(dict(row))
        seen.add(value)
    return result


def _relationship_diagnostic(
    *,
    layer: str,
    label: str,
    available: bool,
    count: int,
    required: bool,
    action: str,
    evidence: str,
) -> dict[str, Any]:
    status = "available" if available else ("missing_required" if required else "missing_optional")
    return {
        "layer": layer,
        "label": label,
        "status": status,
        "available": available,
        "count": count,
        "required": required,
        "recommended_action": action if not available else "继续维护来源和证据回链",
        "evidence": evidence,
    }


def _relationship_action_target(layer: str) -> dict[str, Any]:
    if layer in {"industry_position", "peer_companies", "upstream_companies", "downstream_companies"}:
        return {
            "target_type": "company_database_batch_build_preview",
            "endpoint": "/api/company-database/batch/build",
            "ui_action": "preview_batch_build",
            "method": "POST",
            "default_execute": False,
            "usage_boundary": "local_company_database_backfill_preview_only",
        }
    if layer in {"ownership_candidates", "shareholder_network", "approved_shareholder_network"}:
        return {
            "target_type": "ownership_import_or_review_guidance",
            "endpoint": "/api/company-database/relationships/build",
            "review_endpoint": "/api/company-database/relationships/review",
            "manifest_endpoint": "/api/company-database/ownership/manifest-template",
            "ui_action": "ownership_import_guidance",
            "method": "POST",
            "default_execute": False,
            "usage_boundary": "local_structured_ownership_import_and_manual_review_only",
        }
    if layer == "graph_edges":
        return {
            "target_type": "relationship_graph_query",
            "endpoint": "/api/graph/query",
            "ui_action": "open_relationship_graph",
            "method": "GET",
            "default_execute": False,
            "usage_boundary": "read_only_relationship_graph_exploration",
        }
    return {
        "target_type": "relationship_coverage_audit",
        "endpoint": "/api/company-intelligence/{symbol}",
        "ui_action": "coverage_audit",
        "method": "GET",
        "default_execute": False,
        "usage_boundary": "read_only_relationship_gap_review",
    }


def _relationship_coverage_diagnostics(summary: Mapping[str, Any]) -> dict[str, Any]:
    diagnostics = [
        _relationship_diagnostic(
            layer="industry_position",
            label="产业链位置",
            available=bool(summary.get("industry_positions") and summary.get("industry_chain_nodes")),
            count=int(summary.get("industry_chain_nodes", 0) or 0),
            required=True,
            action="补充 CompanyPosition / IndustryChain，先定位公司所在产业链节点",
            evidence="CompanyPosition + IndustryChain",
        ),
        _relationship_diagnostic(
            layer="peer_companies",
            label="同类公司",
            available=bool(summary.get("peer_companies")),
            count=int(summary.get("peer_companies", 0) or 0),
            required=True,
            action="为同一产业链节点补充更多公司位置，形成可比较公司集合",
            evidence="same chain node positions",
        ),
        _relationship_diagnostic(
            layer="upstream_companies",
            label="上游公司",
            available=bool(summary.get("upstream_companies")),
            count=int(summary.get("upstream_companies", 0) or 0),
            required=True,
            action="补充上游节点公司位置或供应商候选关系，并保留披露证据",
            evidence="IndustryChain edges + CompanyPosition / supplier relationships",
        ),
        _relationship_diagnostic(
            layer="downstream_companies",
            label="下游公司",
            available=bool(summary.get("downstream_companies")),
            count=int(summary.get("downstream_companies", 0) or 0),
            required=True,
            action="补充下游节点公司位置或客户/应用候选关系，并保留披露证据",
            evidence="IndustryChain edges + CompanyPosition / customer relationships",
        ),
        _relationship_diagnostic(
            layer="ownership_candidates",
            label="股权/控制关系",
            available=bool(summary.get("shareholders") or summary.get("ownership_relationships")),
            count=int(summary.get("shareholders", 0) or 0) + int(summary.get("ownership_relationships", 0) or 0),
            required=True,
            action="导入十大股东、实控人、子公司、参股公司表格并人工复核候选",
            evidence="InstitutionalHolding / structured ownership CompanyRelationship",
        ),
        _relationship_diagnostic(
            layer="shareholder_network",
            label="13F/持仓股东关联公司",
            available=bool(summary.get("shareholder_related_companies")),
            count=int(summary.get("shareholder_related_companies", 0) or 0),
            required=False,
            action="补充同一股东/持有人覆盖面，形成持股网络二跳展开",
            evidence="same-holder InstitutionalHolding records",
        ),
        _relationship_diagnostic(
            layer="approved_shareholder_network",
            label="事实股东关联公司",
            available=bool(summary.get("approved_shareholder_related_companies")),
            count=int(summary.get("approved_shareholder_related_companies", 0) or 0),
            required=False,
            action="批准股权/控制 CompanyRelationship 后，按同一事实股东展开关联公司",
            evidence="approved active ownership CompanyRelationship records",
        ),
        _relationship_diagnostic(
            layer="graph_edges",
            label="动态图谱边",
            available=bool(summary.get("graph_edges")),
            count=int(summary.get("graph_edges", 0) or 0),
            required=True,
            action="运行图谱查询/关系构建，确认关系、事件、证据回链已进入图谱",
            evidence="/api/graph/query edges",
        ),
    ]
    required_rows = [item for item in diagnostics if item["required"]]
    available_required = sum(1 for item in required_rows if item["available"])
    required_total = len(required_rows) or 1
    missing_required = [item["layer"] for item in required_rows if not item["available"]]
    missing_optional = [item["layer"] for item in diagnostics if not item["required"] and not item["available"]]
    industry_network_summary = {
        "total": int(summary.get("industry_related_companies_total", 0) or 0),
        "peers": int(summary.get("peer_companies", 0) or 0),
        "upstream": int(summary.get("upstream_companies", 0) or 0),
        "downstream": int(summary.get("downstream_companies", 0) or 0),
        "chain_nodes": int(summary.get("industry_chain_nodes", 0) or 0),
        "available": bool(summary.get("industry_related_companies_total")),
        "source_layers": ["CompanyPosition", "IndustryChain edges"],
    }
    shareholder_network_summary = {
        "total": int(summary.get("shareholder_related_companies_total", 0) or 0),
        "fact_network": int(summary.get("approved_shareholder_related_companies", 0) or 0),
        "holding_network": int(summary.get("shareholder_related_companies", 0) or 0),
        "available": bool(summary.get("shareholder_related_companies_total")),
        "source_layers": ["approved active ownership CompanyRelationship records", "same-holder InstitutionalHolding records"],
    }
    next_actions = [
        {
            "action": "relationship_backfill",
            "layer": item["layer"],
            "label": item["label"],
            "reason": item["recommended_action"],
            "target": _relationship_action_target(str(item["layer"])),
        }
        for item in diagnostics
        if item["required"] and not item["available"]
    ]
    enhancement_actions = [
        {
            "action": "relationship_enhancement",
            "layer": item["layer"],
            "label": item["label"],
            "reason": item["recommended_action"],
            "target": _relationship_action_target(str(item["layer"])),
        }
        for item in diagnostics
        if not item["required"] and not item["available"]
    ]
    return {
        "schema_id": "company-relationship-coverage-v1",
        "coverage_score": round(available_required / required_total, 4),
        "status": "complete" if not missing_required else ("partial" if available_required else "missing"),
        "missing_required_layers": missing_required,
        "missing_optional_layers": missing_optional,
        "industry_network_summary": industry_network_summary,
        "shareholder_network_summary": shareholder_network_summary,
        "diagnostics": diagnostics,
        "next_actions": next_actions,
        "enhancement_actions": enhancement_actions,
        "completion_rule": "required layers need industry position, peers, upstream, downstream, ownership/control, and graph edges; optional 13F same-holder and approved fact shareholder networks improve exploration depth",
    }


def _relationship_bucket(relationship_type: str) -> str:
    normalized = relationship_type.lower()
    if any(token in normalized for token in ["supplier", "upstream"]):
        return "upstream"
    if any(token in normalized for token in ["customer", "downstream"]):
        return "downstream"
    if any(token in normalized for token in ["competitor", "peer", "same_segment"]):
        return "peers"
    if any(token in normalized for token in ["shareholder", "holder", "equity", "ownership", "subsidiary", "controller", "controlling", "investee"]):
        return "ownership"
    if any(token in normalized for token in ["institution", "analyst", "coverage"]):
        return "coverage"
    return "other"


def ownership_holder_key(row: Mapping[str, Any]) -> str:
    object_id = str(row.get("object_id", "") or "").strip().lower()
    if object_id:
        return object_id
    metadata = row.get("metadata", {})
    if isinstance(metadata, Mapping):
        entity_name = str(metadata.get("entity_name", "") or "").strip().lower()
    else:
        entity_name = ""
    if not entity_name:
        entity_name = str(row.get("entity_name", "") or "").strip().lower()
    return re.sub(r"\s+", " ", entity_name)


_ownership_holder_key = ownership_holder_key


def institutional_holder_key(row: Mapping[str, Any]) -> str:
    value = str(row.get("filer_cik", "") or row.get("holder_id", "") or row.get("filer_name", "") or row.get("holder_name", "") or "").strip()
    return re.sub(r"\s+", " ", value).upper()


_institutional_holder_key = institutional_holder_key


OWNERSHIP_RELATIONSHIP_TYPE_ALIASES = {
    "shareholder": "shareholder_candidate",
    "holder": "shareholder_candidate",
    "top_shareholder": "shareholder_candidate",
    "top10_shareholder": "shareholder_candidate",
    "top_ten_shareholder": "shareholder_candidate",
    "controller": "controller_candidate",
    "actual_controller": "controller_candidate",
    "beneficial_owner": "controller_candidate",
    "controlling_shareholder": "controller_candidate",
    "subsidiary": "subsidiary_candidate",
    "controlled_subsidiary": "subsidiary_candidate",
    "investee": "investee_candidate",
    "equity_investment": "investee_candidate",
    "affiliate": "investee_candidate",
    "associate": "investee_candidate",
    "十大股东": "shareholder_candidate",
    "股东": "shareholder_candidate",
    "主要股东": "shareholder_candidate",
    "实控人": "controller_candidate",
    "实际控制人": "controller_candidate",
    "控股股东": "controller_candidate",
    "子公司": "subsidiary_candidate",
    "控股子公司": "subsidiary_candidate",
    "参股公司": "investee_candidate",
    "被投资公司": "investee_candidate",
}


OWNERSHIP_TABLE_FIELD_ALIASES = {
    "issuer": "issuer_id",
    "issuer_id": "issuer_id",
    "subject_id": "issuer_id",
    "主体": "issuer_id",
    "公司主体": "issuer_id",
    "security_id": "security_id",
    "证券": "security_id",
    "ticker": "ticker",
    "symbol": "symbol",
    "代码": "symbol",
    "股票代码": "symbol",
    "kind": "kind",
    "type": "kind",
    "relationship_type": "relationship_type",
    "关系类型": "kind",
    "类型": "kind",
    "类别": "kind",
    "entity_name": "entity_name",
    "name": "entity_name",
    "holder_name": "holder_name",
    "shareholder_name": "shareholder_name",
    "controller_name": "controller_name",
    "subsidiary_name": "subsidiary_name",
    "investee_name": "investee_name",
    "object_name": "entity_name",
    "股东名称": "shareholder_name",
    "股东": "shareholder_name",
    "持有人": "holder_name",
    "实控人": "controller_name",
    "实际控制人": "controller_name",
    "控股股东": "controller_name",
    "子公司": "subsidiary_name",
    "参股公司": "investee_name",
    "被投资公司": "investee_name",
    "名称": "entity_name",
    "object_id": "object_id",
    "related_issuer_id": "related_issuer_id",
    "share_ratio": "share_ratio",
    "ownership_pct": "ownership_pct",
    "持股比例": "share_ratio",
    "持股比例(%)": "share_ratio",
    "持股比例%": "share_ratio",
    "持股百分比": "share_ratio",
    "持股": "share_ratio",
    "持股数": "shares",
    "持股数量": "shares",
    "voting_pct": "voting_pct",
    "表决权比例": "voting_pct",
    "表决权": "voting_pct",
    "report_period": "report_period",
    "报告期": "report_period",
    "截止日期": "as_of_date",
    "as_of_date": "as_of_date",
    "rank": "rank",
    "排名": "rank",
    "source_id": "source_id",
    "来源": "source_id",
    "source_table": "source_table",
    "来源表": "source_table",
}


def _id_part(value: Any) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_\-\u4e00-\u9fff]+", "_", str(value or "").strip()).strip("_")
    return normalized.lower()[:80] or "unknown"


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def split_csv(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def discover_ownership_files(root_path: str, *, patterns: list[str], scan_limit: int) -> list[str]:
    root = Path(root_path).expanduser()
    if scan_limit <= 0:
        return []
    discovered: list[str] = []
    seen: set[str] = set()
    for pattern in patterns:
        for path in sorted(root.rglob(pattern)):
            if not path.is_file():
                continue
            rel_path = str(path.relative_to(root))
            if rel_path in seen:
                continue
            seen.add(rel_path)
            discovered.append(rel_path)
            if len(discovered) >= scan_limit:
                return discovered
    return discovered


def infer_symbols_from_ownership_paths(file_paths: Iterable[str]) -> list[str]:
    symbols: list[str] = []
    seen: set[str] = set()
    for raw_path in file_paths:
        text = str(raw_path)
        candidates = re.findall(r"(?i)(?:^|[^A-Za-z0-9])(?:sh|sz|bj)?(\d{6})(?:\.(?:sh|sz|bj|ss|xshg|xshe))?(?=$|[^A-Za-z0-9])", text)
        candidates.extend(re.findall(r"(?<![A-Za-z0-9])([A-Z]{1,5})(?=[_\-\.\s/]|$)", text))
        for candidate in candidates:
            symbol = candidate.upper()
            if symbol and symbol not in {"CSV", "TSV", "TXT", "MD", "JSON"} and symbol not in seen:
                symbols.append(symbol)
                seen.add(symbol)
    return symbols


def build_ownership_manifest_template(
    *,
    root_path: str,
    file_paths: list[str],
    scan_patterns: list[str],
    scan_limit: int,
    infer_symbols: bool,
    default_source_id: str,
    default_source_table: str,
    default_kind: str,
) -> dict[str, Any]:
    discovered_files = discover_ownership_files(root_path, patterns=scan_patterns, scan_limit=scan_limit) if scan_patterns else []
    merged = list(dict.fromkeys([*file_paths, *discovered_files]))
    files: list[dict[str, Any]] = []
    for file_path in merged:
        inferred = infer_symbols_from_ownership_paths([file_path]) if infer_symbols else []
        files.append(
            {
                "file_path": file_path,
                "symbol": inferred[0] if inferred else "",
                "default_kind": default_kind,
                "source_id": default_source_id,
                "source_table": default_source_table or Path(file_path).stem,
            }
        )
    return {
        "schema_id": "company-ownership-table-manifest-v1",
        "generated_at": utc_iso(),
        "root_path": root_path,
        "defaults": {
            "default_kind": default_kind,
            "source_id": default_source_id,
            "source_table": default_source_table,
        },
        "files": files,
        "usage_boundary": "local_ownership_manifest_template_edit_before_execute_no_live_trading",
    }


def _normalized_relationship_type(row: Mapping[str, Any]) -> str:
    raw_type = _first_text(row, ["relationship_type", "type", "kind", "category"], "shareholder_candidate")
    normalized = raw_type.strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in OWNERSHIP_RELATIONSHIP_TYPE_ALIASES:
        return OWNERSHIP_RELATIONSHIP_TYPE_ALIASES[normalized]
    if not normalized.endswith("_candidate"):
        normalized = f"{normalized}_candidate"
    return normalized


def _floatish(value: Any, default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    text = str(value).strip()
    try:
        if text.endswith("%"):
            return float(text[:-1]) / 100.0
        return float(text)
    except (TypeError, ValueError):
        return default


def _normalized_table_header(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "").strip().lower())


def _split_markdown_table_line(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _table_dialect(text: str) -> str:
    sample = "\n".join(line for line in text.splitlines() if line.strip())[:1000]
    if "\t" in sample:
        return "\t"
    return ","


def parse_structured_ownership_table(
    table_text: str,
    *,
    default_kind: str = "shareholder",
    source_table: str = "ownership_table",
    source_id: str = "local_structured_ownership",
) -> list[dict[str, Any]]:
    """Parse CSV/TSV/Markdown ownership tables into normalized ownership rows."""

    text = str(table_text or "").strip()
    if not text:
        return []
    rows: list[dict[str, Any]] = []
    non_empty_lines = [line for line in text.splitlines() if line.strip()]
    if non_empty_lines and non_empty_lines[0].lstrip().startswith("|"):
        parsed_rows = [_split_markdown_table_line(line) for line in non_empty_lines]
        parsed_rows = [row for row in parsed_rows if row and not all(re.fullmatch(r":?-{2,}:?", cell or "") for cell in row)]
        headers = parsed_rows[0] if parsed_rows else []
        data_rows = parsed_rows[1:]
    else:
        reader = csv.reader(StringIO(text), delimiter=_table_dialect(text))
        parsed_rows = [row for row in reader if any(str(cell).strip() for cell in row)]
        headers = parsed_rows[0] if parsed_rows else []
        data_rows = parsed_rows[1:]
    field_names = [OWNERSHIP_TABLE_FIELD_ALIASES.get(_normalized_table_header(header), _normalized_table_header(header)) for header in headers]
    for data_row in data_rows:
        row: dict[str, Any] = {}
        for index, value in enumerate(data_row):
            if index >= len(field_names):
                continue
            key = field_names[index]
            if not key:
                continue
            clean_value = str(value).strip()
            if clean_value:
                row[key] = clean_value
        if not row:
            continue
        row.setdefault("kind", default_kind)
        row.setdefault("source_id", source_id)
        row.setdefault("source_table", source_table)
        rows.append(row)
    return rows


def ownership_rows_from_payload(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    explicit_rows = payload.get("structured_ownership_relationships", payload.get("ownership_relationships", []))
    if isinstance(explicit_rows, Mapping):
        explicit_rows = [explicit_rows]
    if isinstance(explicit_rows, list):
        rows.extend(dict(row) for row in explicit_rows if isinstance(row, Mapping))
    table_specs = payload.get("structured_ownership_tables", payload.get("ownership_tables", []))
    if isinstance(table_specs, (str, Mapping)):
        table_specs = [table_specs]
    if isinstance(table_specs, list):
        for index, spec in enumerate(table_specs):
            if isinstance(spec, str):
                table_text = spec
                default_kind = "shareholder"
                source_table = f"ownership_table_{index + 1}"
                source_id = "local_structured_ownership"
            elif isinstance(spec, Mapping):
                table_text = str(spec.get("table_text", "") or spec.get("csv", "") or spec.get("tsv", "") or spec.get("markdown", "") or spec.get("body", "") or "")
                default_kind = _first_text(spec, ["default_kind", "kind", "relationship_type"], "shareholder")
                source_table = _first_text(spec, ["source_table", "name"], f"ownership_table_{index + 1}")
                source_id = _first_text(spec, ["source_id"], "local_structured_ownership")
            else:
                continue
            rows.extend(parse_structured_ownership_table(table_text, default_kind=default_kind, source_table=source_table, source_id=source_id))
    for key, kind in [
        ("ownership_table_text", "shareholder"),
        ("ownership_csv", "shareholder"),
        ("ownership_tsv", "shareholder"),
        ("shareholder_table_text", "shareholder"),
        ("controller_table_text", "controller"),
        ("subsidiary_table_text", "subsidiary"),
        ("investee_table_text", "investee"),
    ]:
        if payload.get(key):
            rows.extend(parse_structured_ownership_table(str(payload.get(key)), default_kind=kind, source_table=key, source_id="local_structured_ownership"))
    return rows


def structured_ownership_relationship_specs(
    *,
    issuer_id: str,
    security_id: str = "",
    ownership_rows: Iterable[Mapping[str, Any]] | None = None,
    existing_relationship_ids: Iterable[str] | None = None,
    default_source_id: str = "local_structured_ownership",
    confidence: float = 0.72,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Convert governed local ownership rows into CompanyRelationship payload specs.

    The function intentionally emits review candidates, not facts. It can represent
    A-share top shareholders, controllers, subsidiaries, and investee companies from
    a local import or manual structured input without requiring a schema migration.
    """

    if limit <= 0:
        return []
    existing_ids = {str(item) for item in (existing_relationship_ids or [])}
    specs: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in ownership_rows or []:
        relationship_type = _normalized_relationship_type(row)
        entity_name = _first_text(
            row,
            [
                "entity_name",
                "name",
                "holder_name",
                "shareholder_name",
                "controller_name",
                "company_name",
                "subsidiary_name",
                "investee_name",
                "object_name",
            ],
        )
        object_id = _first_text(row, ["object_id", "related_issuer_id", "entity_id"], f"external_company_{_id_part(entity_name)}")
        if not entity_name and not object_id:
            continue
        if not entity_name:
            entity_name = object_id
        key = (relationship_type, object_id.lower())
        if key in seen:
            continue
        seen.add(key)
        row_security_id = _first_text(row, ["security_id"], security_id)
        relationship_id = _first_text(row, ["relationship_id"], f"rel_structured_ownership_{_id_part(issuer_id)}_{_id_part(relationship_type)}_{_id_part(object_id)}")
        if relationship_id in existing_ids:
            continue
        source_ids = [str(item).strip() for item in row.get("source_ids", []) or [] if str(item).strip()]
        source_id = _first_text(row, ["source_id"], default_source_id)
        if source_id and source_id not in source_ids:
            source_ids.append(source_id)
        document_ids = [str(item).strip() for item in row.get("document_ids", []) or [] if str(item).strip()]
        evidence_ids = [str(item).strip() for item in row.get("evidence_ids", []) or [] if str(item).strip()]
        metadata = dict(row.get("metadata", {}) or {}) if isinstance(row.get("metadata"), Mapping) else {}
        for source_key, target_key in [
            ("share_ratio", "share_ratio"),
            ("ownership_pct", "share_ratio"),
            ("voting_pct", "voting_pct"),
            ("report_period", "report_period"),
            ("as_of_date", "as_of_date"),
            ("rank", "rank"),
            ("source_table", "source_table"),
        ]:
            if row.get(source_key) not in (None, "") and target_key not in metadata:
                metadata[target_key] = row.get(source_key)
        metadata.update(
            {
                "entity_name": entity_name,
                "source_layer": _first_text(row, ["source_layer"], "structured_ownership_candidate"),
                "candidate_status": "candidate",
                "rights_boundary": "structured_local_or_public_ownership_candidate_needs_review",
            }
        )
        specs.append(
            {
                "relationship_id": relationship_id,
                "issuer_id": issuer_id,
                "security_id": row_security_id,
                "subject_type": "company",
                "subject_id": issuer_id,
                "object_type": _first_text(row, ["object_type"], "company"),
                "object_id": object_id,
                "relationship_type": relationship_type,
                "direction": _first_text(row, ["direction"], "directed"),
                "weight": _floatish(row.get("weight", row.get("share_ratio", row.get("ownership_pct", 0.5))), 0.5),
                "source_ids": source_ids,
                "document_ids": document_ids[:20],
                "evidence_ids": evidence_ids[:20],
                "confidence": _floatish(row.get("confidence", confidence), confidence),
                "relationship_status": _first_text(row, ["relationship_status"], "unknown"),
                "review_status": _first_text(row, ["review_status"], "needs_review"),
                "metadata": metadata,
            }
        )
        if len(specs) >= limit:
            break
    return specs


def relationship_context(
    *,
    issuer_ids: Iterable[str],
    company_relationships: Iterable[Any],
    company_positions: Iterable[Any],
    all_company_positions: Iterable[Any],
    industry_chains: Iterable[Any],
    institutional_holdings: Iterable[Any],
    all_institutional_holdings: Iterable[Any],
    issuers: Mapping[str, Any],
    graph: Mapping[str, Any],
    limit: int = 20,
    all_company_relationships: Iterable[Any] | None = None,
) -> dict[str, Any]:
    """Build a company-centered relationship view from existing local graph records."""

    focus_issuer_ids = {str(issuer_id).strip() for issuer_id in issuer_ids if str(issuer_id).strip()}
    issuer_rows = {issuer_id: _plain(issuer) for issuer_id, issuer in issuers.items()}
    relationship_rows = [_plain(item) for item in company_relationships]
    all_relationship_rows = [_plain(item) for item in (all_company_relationships if all_company_relationships is not None else company_relationships)]
    position_rows = [_plain(item) for item in company_positions]
    all_position_rows = [_plain(item) for item in all_company_positions]
    chain_rows = {str(chain.get("chain_id", "") or "").strip(): chain for chain in (_plain(item) for item in industry_chains)}
    holding_rows = [_plain(item) for item in institutional_holdings]
    all_holding_rows = [_plain(item) for item in all_institutional_holdings]

    relationships_by_type: dict[str, list[dict[str, Any]]] = {
        "upstream": [],
        "downstream": [],
        "peers": [],
        "ownership": [],
        "coverage": [],
        "other": [],
    }
    for relationship in relationship_rows:
        bucket = _relationship_bucket(str(relationship.get("relationship_type", "")))
        relationships_by_type.setdefault(bucket, []).append(relationship)

    focus_node_refs: set[tuple[str, str]] = set()
    for position in position_rows:
        chain_id = str(position.get("chain_id", "") or "").strip()
        for node_id in position.get("node_ids", []) or []:
            node_id = str(node_id).strip()
            if chain_id and node_id:
                focus_node_refs.add((chain_id, node_id))

    peer_rows: list[dict[str, Any]] = []
    upstream_rows: list[dict[str, Any]] = []
    downstream_rows: list[dict[str, Any]] = []
    chain_node_rows: list[dict[str, Any]] = []
    for chain_id, node_id in sorted(focus_node_refs):
        chain = chain_rows.get(chain_id, {})
        chain_node_rows.append(
            {
                "chain_id": chain_id,
                "chain_name": _first_text(chain, ["name", "chain_id"], chain_id),
                "node_id": node_id,
                "node_name": _node_label(chain, node_id),
            }
        )
        upstream_node_ids: set[str] = set()
        downstream_node_ids: set[str] = set()
        for edge in chain.get("edges", []) or []:
            source_node_id = str(edge.get("source_node_id", "") or "").strip()
            target_node_id = str(edge.get("target_node_id", "") or "").strip()
            if target_node_id == node_id and source_node_id:
                upstream_node_ids.add(source_node_id)
            if source_node_id == node_id and target_node_id:
                downstream_node_ids.add(target_node_id)
        for position in all_position_rows:
            if str(position.get("chain_id", "") or "").strip() != chain_id:
                continue
            position_issuer_id = str(position.get("issuer_id", "") or "").strip()
            node_ids = {str(item).strip() for item in position.get("node_ids", []) or [] if str(item).strip()}
            base = {
                "issuer_id": position_issuer_id,
                "display_name": _issuer_label(position_issuer_id, issuer_rows),
                "security_id": str(position.get("security_id", "") or ""),
                "chain_id": chain_id,
                "chain_name": _first_text(chain, ["name", "chain_id"], chain_id),
                "node_ids": sorted(node_ids),
                "role": str(position.get("role", "") or ""),
                "position_id": str(position.get("position_id", "") or ""),
                "data_quality": str(position.get("data_quality", "") or ""),
            }
            if position_issuer_id not in focus_issuer_ids and node_id in node_ids:
                peer_rows.append({**base, "relationship_type": "industry_peer", "reason": f"同处 {_node_label(chain, node_id)}"})
            if node_ids.intersection(upstream_node_ids):
                upstream_rows.append({**base, "relationship_type": "upstream_of", "reason": "产业链上游节点"})
            if node_ids.intersection(downstream_node_ids):
                downstream_rows.append({**base, "relationship_type": "downstream_of", "reason": "产业链下游节点"})

    shareholder_rows: list[dict[str, Any]] = []
    ownership_relationship_rows: list[dict[str, Any]] = []
    approved_ownership_relationship_rows: list[dict[str, Any]] = []
    ownership_candidate_rows: list[dict[str, Any]] = []
    shareholder_related_rows: list[dict[str, Any]] = []
    focus_holder_keys: set[tuple[str, str]] = set()
    for holding in holding_rows:
        holder_key = _institutional_holder_key(holding)
        key = (
            str(holding.get("filer_cik", "") or "").strip().upper(),
            str(holding.get("filer_name", "") or "").strip().upper(),
        )
        focus_holder_keys.add(key)
        shareholder_rows.append(
            {
                "holder_id": key[0] or key[1],
                "holder_key": holder_key,
                "holder_name": str(holding.get("filer_name", "") or key[0]),
                "issuer_id": str(holding.get("issuer_id", "") or ""),
                "security_id": str(holding.get("security_id", "") or ""),
                "shares": float(holding.get("shares", 0.0) or 0.0),
                "value_usd": float(holding.get("value_usd", 0.0) or 0.0),
                "report_period": str(holding.get("report_period", "") or ""),
                "source_id": str(holding.get("source_id", "") or ""),
            }
        )
    for relationship in relationships_by_type.get("ownership", []):
        relationship_type = str(relationship.get("relationship_type", "") or "")
        entity_name = str(relationship.get("metadata", {}).get("entity_name", "") if isinstance(relationship.get("metadata"), Mapping) else "") or str(relationship.get("object_id", "") or "")
        row = {
            "relationship_id": str(relationship.get("relationship_id", "") or ""),
            "relationship_type": relationship_type,
            "entity_name": entity_name,
            "subject_id": str(relationship.get("subject_id", "") or ""),
            "object_id": str(relationship.get("object_id", "") or ""),
            "holder_key": _ownership_holder_key(relationship),
            "holder_name": entity_name or str(relationship.get("object_id", "") or ""),
            "relationship_status": str(relationship.get("relationship_status", "") or ""),
            "review_status": str(relationship.get("review_status", "") or ""),
            "confidence": float(relationship.get("confidence", 0.0) or 0.0),
            "source_ids": list(relationship.get("source_ids", []) or []),
            "document_ids": list(relationship.get("document_ids", []) or []),
            "evidence_ids": list(relationship.get("evidence_ids", []) or []),
            "metadata": dict(relationship.get("metadata", {}) or {}) if isinstance(relationship.get("metadata"), Mapping) else {},
        }
        ownership_relationship_rows.append(row)
        candidate_status = str(row["metadata"].get("candidate_status", "") or "")
        if relationship_type.endswith("_candidate") or row["review_status"] == "needs_review" or candidate_status == "candidate":
            ownership_candidate_rows.append(row)
        elif row["relationship_status"] == "active" and row["review_status"] in {"approved", "auto_generated", "reviewed"}:
            approved_ownership_relationship_rows.append(row)
    for holding in all_holding_rows:
        holder_key = _institutional_holder_key(holding)
        key = (
            str(holding.get("filer_cik", "") or "").strip().upper(),
            str(holding.get("filer_name", "") or "").strip().upper(),
        )
        related_issuer_id = str(holding.get("issuer_id", "") or "").strip()
        if key not in focus_holder_keys or related_issuer_id in focus_issuer_ids:
            continue
        shareholder_related_rows.append(
            {
                "holder_id": key[0] or key[1],
                "holder_key": holder_key,
                "holder_name": str(holding.get("filer_name", "") or key[0]),
                "related_issuer_id": related_issuer_id,
                "related_company": _issuer_label(related_issuer_id, issuer_rows),
                "security_id": str(holding.get("security_id", "") or ""),
                "shares": float(holding.get("shares", 0.0) or 0.0),
                "value_usd": float(holding.get("value_usd", 0.0) or 0.0),
                "report_period": str(holding.get("report_period", "") or ""),
            }
        )

    peer_rows = _dedupe_rows(peer_rows, "issuer_id")[:limit]
    upstream_rows = _dedupe_rows(upstream_rows, "issuer_id")[:limit]
    downstream_rows = _dedupe_rows(downstream_rows, "issuer_id")[:limit]
    ownership_relationship_rows = _dedupe_rows(ownership_relationship_rows, "relationship_id")[:limit]
    approved_ownership_relationship_rows = _dedupe_rows(approved_ownership_relationship_rows, "relationship_id")[:limit]
    ownership_candidate_rows = _dedupe_rows(ownership_candidate_rows, "relationship_id")[:limit]
    approved_holder_keys = {_ownership_holder_key(row) for row in approved_ownership_relationship_rows}
    approved_holder_keys.discard("")
    approved_shareholder_related_rows: list[dict[str, Any]] = []
    if approved_holder_keys:
        for relationship in all_relationship_rows:
            relationship_type = str(relationship.get("relationship_type", "") or "")
            if _relationship_bucket(relationship_type) != "ownership" or relationship_type.endswith("_candidate"):
                continue
            relationship_status = str(relationship.get("relationship_status", "") or "")
            review_status = str(relationship.get("review_status", "") or "")
            if relationship_status != "active" or review_status not in {"approved", "auto_generated", "reviewed"}:
                continue
            related_issuer_id = str(relationship.get("issuer_id", "") or relationship.get("subject_id", "") or "").strip()
            if not related_issuer_id or related_issuer_id in focus_issuer_ids:
                continue
            holder_key = _ownership_holder_key(relationship)
            if holder_key not in approved_holder_keys:
                continue
            metadata = dict(relationship.get("metadata", {}) or {}) if isinstance(relationship.get("metadata"), Mapping) else {}
            approved_shareholder_related_rows.append(
                {
                    "relationship_id": str(relationship.get("relationship_id", "") or ""),
                    "holder_id": str(relationship.get("object_id", "") or holder_key),
                    "holder_key": holder_key,
                    "holder_name": str(metadata.get("entity_name", "") or relationship.get("object_id", "") or holder_key),
                    "related_issuer_id": related_issuer_id,
                    "related_company": _issuer_label(related_issuer_id, issuer_rows),
                    "relationship_type": relationship_type,
                    "relationship_status": relationship_status,
                    "review_status": review_status,
                    "confidence": float(relationship.get("confidence", 0.0) or 0.0),
                    "metadata": metadata,
                    "source": "approved_company_relationship",
                }
            )
    approved_shareholder_related_rows = _dedupe_rows(approved_shareholder_related_rows, "relationship_id")[:limit]
    shareholder_related_rows = _dedupe_rows(shareholder_related_rows, "related_issuer_id")[:limit]

    graph_edges = graph.get("edges", []) if isinstance(graph.get("edges"), list) else []
    expansion_types = [
        "industry_peer",
        "upstream_of",
        "downstream_of",
        "shareholder_of",
        "shareholder_related_company",
        *sorted({str(item.get("relationship_type", "") or "") for item in relationship_rows if item.get("relationship_type")}),
    ]
    recommended_graph_queries: list[dict[str, Any]] = []
    focus_issuer_id = sorted(focus_issuer_ids)[0] if focus_issuer_ids else ""
    if focus_issuer_id:
        recommended_graph_queries.append(
            {
                "label": "公司中心关系图",
                "query": {"issuer_id": focus_issuer_id},
                "reason": "从当前公司出发展示本地关系、事件、证据和图谱边",
            }
        )
        for item in chain_node_rows[:3]:
            query = {
                "issuer_id": focus_issuer_id,
                "chain_id": item.get("chain_id", ""),
                "chain_node_id": item.get("node_id", ""),
            }
            recommended_graph_queries.append(
                {
                    "label": f"产业链节点: {item.get('node_name') or item.get('node_id')}",
                    "query": {key: value for key, value in query.items() if value},
                    "reason": "按当前产业链节点展开同类、上游和下游关系",
                }
            )
        industry_recommendation_specs = [
            ("peer", "同类公司", peer_rows, "industry_peer", "按同一产业链节点展开同类公司网络"),
            ("upstream", "上游公司", upstream_rows, "upstream_of", "按当前公司所在节点展开上游公司网络"),
            ("downstream", "下游公司", downstream_rows, "downstream_of", "按当前公司所在节点展开下游公司网络"),
        ]
        for direction, label, rows, relationship_type, reason in industry_recommendation_specs:
            if not rows:
                continue
            item = rows[0]
            query = {
                "issuer_id": focus_issuer_id,
                "relationship_type": relationship_type,
                "chain_id": item.get("chain_id", ""),
                "chain_node_id": (item.get("node_ids") or [""])[0],
                "industry_direction": direction,
            }
            recommended_graph_queries.append(
                {
                    "label": f"{label}: {item.get('display_name') or item.get('issuer_id')}",
                    "query": {key: value for key, value in query.items() if value},
                    "reason": reason,
                }
            )
        for item in approved_shareholder_related_rows[:3]:
            holder_key = str(item.get("holder_key", "") or item.get("holder_id", "") or "").strip()
            relationship_type = str(item.get("relationship_type", "") or "shareholder").strip()
            if not holder_key:
                continue
            recommended_graph_queries.append(
                {
                    "label": f"同一事实股东: {item.get('holder_name') or holder_key}",
                    "query": {
                        "issuer_id": focus_issuer_id,
                        "relationship_type": relationship_type,
                        "ownership_holder_key": holder_key,
                    },
                    "reason": "按同一已批准股东/持有人展开跨公司事实股东网络",
                }
            )
        for item in shareholder_related_rows[:3]:
            holder_key = str(item.get("holder_key", "") or item.get("holder_id", "") or "").strip()
            if not holder_key:
                continue
            recommended_graph_queries.append(
                {
                    "label": f"同一13F持有人: {item.get('holder_name') or holder_key}",
                    "query": {
                        "issuer_id": focus_issuer_id,
                        "institutional_holder_key": holder_key,
                    },
                    "reason": "按同一 13F/持仓持有人展开跨公司持仓网络",
                }
            )
        for relationship_type in list(dict.fromkeys([item for item in expansion_types if item]))[:5]:
            recommended_graph_queries.append(
                {
                    "label": f"关系类型: {relationship_type}",
                    "query": {"issuer_id": focus_issuer_id, "relationship_type": relationship_type},
                    "reason": "按单一关系类型聚焦动态图谱",
                }
            )
    summary = {
        "direct_relationships": len(relationship_rows),
        "industry_positions": len(position_rows),
        "industry_chain_nodes": len(chain_node_rows),
        "peer_companies": len(peer_rows),
        "upstream_companies": len(upstream_rows),
        "downstream_companies": len(downstream_rows),
        "industry_related_companies_total": len(peer_rows) + len(upstream_rows) + len(downstream_rows),
        "shareholders": len(shareholder_rows),
        "ownership_relationships": len(ownership_relationship_rows),
        "approved_ownership_relationships": len(approved_ownership_relationship_rows),
        "ownership_candidates": len(ownership_candidate_rows),
        "approved_shareholder_related_companies": len(approved_shareholder_related_rows),
        "shareholder_related_companies": len(shareholder_related_rows),
        "shareholder_related_companies_total": len(approved_shareholder_related_rows) + len(shareholder_related_rows),
        "graph_edges": len(graph_edges),
    }
    coverage_diagnostics = _relationship_coverage_diagnostics(summary)
    return {
        "schema_id": "company-relationship-context-v1",
        "focus_issuer_ids": sorted(focus_issuer_ids),
        "summary": summary,
        "coverage_diagnostics": coverage_diagnostics,
        "next_actions": coverage_diagnostics["next_actions"],
        "enhancement_actions": coverage_diagnostics["enhancement_actions"],
        "industry": {
            "positions": position_rows[:limit],
            "chain_nodes": chain_node_rows[:limit],
            "peer_companies": peer_rows,
            "upstream_companies": upstream_rows,
            "downstream_companies": downstream_rows,
        },
        "ownership": {
            "shareholders": shareholder_rows[:limit],
            "approved_relationships": approved_ownership_relationship_rows,
            "relationship_candidates": ownership_candidate_rows,
            "relationships": ownership_relationship_rows,
            "approved_shareholder_related_companies": approved_shareholder_related_rows,
            "shareholder_related_companies": shareholder_related_rows,
        },
        "relationships_by_type": {key: rows[:limit] for key, rows in relationships_by_type.items()},
        "dynamic_graph": {
            "default_depth": 2,
            "focus_issuer_ids": sorted(focus_issuer_ids),
            "expandable_relationship_types": list(dict.fromkeys([item for item in expansion_types if item])),
            "recommended_filters": ["issuer_id", "security_id", "relationship_type", "chain_id", "chain_node_id", "industry_direction", "ownership_holder_key", "institutional_holder_key"],
            "recommended_queries": recommended_graph_queries[:10],
            "usage": "company_centered_relationship_exploration",
        },
        "data_policy": {
            "database_rebuild_required": False,
            "relationship_backfill_required": True,
            "source_boundary": "derived_from_local_company_relationships_positions_holdings_and_graph_edges",
            "live_execution_allowed": False,
        },
    }
