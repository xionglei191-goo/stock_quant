from __future__ import annotations

from typing import Any, Callable, Mapping, Protocol


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
