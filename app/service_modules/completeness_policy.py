"""公司完整度判定的唯一口径（纯函数，无 IO、无状态）。

背景：既有 `company_intelligence.completeness_verdict` 只看分层可用性与加权分，
`missing_fact_fields` 不参与判定，于是出现 `score=0.988` 且 27 项缺失字段同时
被报告为 `complete`（实测 `/api/company-intelligence/600519`）。本模块把判定收敛为
一处，供公司情报响应与当日清单共用（需求 5.1、5.2、5.3、5.4、5.5、5.8；设计 §4.8）。

判定规则（`resolve_status`）：

- `profile_available` 为假 → `status="not_found"`。
- 其余情况 `status="complete"` 当且仅当同时满足：
  1. 无 `blocking_gaps`；
  2. 无 `warning_gaps`；
  3. `missing_fact_fields` 为空；
  4. `LAYER_COVERAGE_THRESHOLDS` 中每个键在 `coverage_scores` 里的取值 ≥ 对应阈值。
- 其余任何非 `not_found` 情况一律 `status="partial"`，不再区分 `incomplete` /
  `usable_with_gaps`（取值域收敛已获批准，设计 §9 风险 1）。

`missing_layers` 的构成（顺序稳定，去重后保序）：

1. `blocking_gaps` 原样（调用方给出的分层标识，视为不透明字符串）；
2. `warning_gaps` 原样；
3. 未达阈值的覆盖度分层名，按 `LAYER_COVERAGE_THRESHOLDS` 的键序，
   分层名 = 覆盖度键去掉 `_score` 后缀（如 `database_coverage_score` →
   `database_coverage`）；`coverage_scores` 缺该键时按 0.0 处理，即视为未达标；
4. `missing_fact_fields` 非空时追加 `MISSING_FACT_FIELDS_LAYER`。

`coverage_denominator` 的 `score` 为 `round(filled_fields / total_fields, 4)`
（与仓库既有覆盖度分值保留 4 位小数的口径一致），`total_fields` 为 0 时 `score=0.0`。

`next_actions` 对任何非 `complete` 状态至少返回 1 条，每条都含 `target_field`、
`source_type`，以及 `command` 与 `endpoint` 两个键且至少一个非空。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

__all__ = [
    "LAYER_COVERAGE_THRESHOLDS",
    "MISSING_FACT_FIELDS_LAYER",
    "STATUS_LABELS",
    "STATUS_VALUES",
    "coverage_denominator",
    "next_actions",
    "resolve_status",
]


LAYER_COVERAGE_THRESHOLDS: dict[str, float] = {
    "profile_field_coverage_score": 0.9,
    "database_coverage_score": 0.9,
    "relationship_coverage_score": 0.9,
}

STATUS_VALUES = ("complete", "partial", "not_found")

STATUS_LABELS: dict[str, str] = {
    "complete": "完整",
    "partial": "部分完整",
    "not_found": "未建档",
}

MISSING_FACT_FIELDS_LAYER = "profile_fact_fields"

_DEFAULT_ACTION_LIMIT = 12

# 分层补库动作：键为分层标识（既有 SECTION_SPECS 分层、公司库覆盖分节、
# 关系覆盖诊断分层与覆盖度分层），值为 (action, label, source_type, endpoint, command)。
_LAYER_ACTIONS: dict[str, tuple[str, str, str, str, str]] = {
    "company_profile": (
        "bootstrap_company_database",
        "建立本地公司主体与证券档案",
        "official_disclosure",
        "/api/company-database/bootstrap",
        "python3 scripts/build_company_database_minimum.py",
    ),
    "security": (
        "build_company_database",
        "补齐证券主体登记",
        "official_disclosure",
        "/api/company-database/build",
        "python3 scripts/build_company_database_minimum.py",
    ),
    "market_data": (
        "backfill_market_data",
        "补齐公开或本地 EOD 行情",
        "public_or_local_market_data",
        "/api/market-data/backfill",
        "python3 scripts/backfill_market_data.py",
    ),
    "financial_snapshot": (
        "backfill_financial_snapshot",
        "补齐财报快照字段",
        "official_financial_report",
        "/api/company-financial-metrics",
        "python3 scripts/backfill_company_financials_public.py",
    ),
    "documents": (
        "ingest_company_material",
        "导入官方披露材料",
        "official_disclosure",
        "/api/company-database/material-inbox/ingest",
        "python3 scripts/company_material_inbox_ingest.py",
    ),
    "events": (
        "build_company_events",
        "生成公司事件时间线",
        "official_public_fact_or_reviewed_event",
        "/api/company-database/events/build",
        "python3 scripts/company_material_inbox_ingest.py",
    ),
    "company_events": (
        "build_company_events",
        "生成公司事件时间线",
        "official_public_fact_or_reviewed_event",
        "/api/company-database/events/build",
        "python3 scripts/company_material_inbox_ingest.py",
    ),
    "disclosure_events": (
        "ingest_disclosure_events",
        "补齐公告披露事件",
        "official_disclosure",
        "/api/disclosure-events",
        "python3 scripts/company_material_inbox_ingest.py",
    ),
    "relationships": (
        "build_company_relationships",
        "生成并审核公司关系",
        "official_disclosure_or_reviewed_relationship",
        "/api/company-database/relationships/build",
        "python3 scripts/sync_ashare_company_positions.py",
    ),
    "company_relationships": (
        "build_company_relationships",
        "生成并审核公司关系",
        "official_disclosure_or_reviewed_relationship",
        "/api/company-database/relationships/build",
        "python3 scripts/sync_ashare_company_positions.py",
    ),
    "industry_position": (
        "sync_company_positions",
        "补齐产业链位置",
        "official_disclosure_or_reviewed_relationship",
        "/api/company-positions",
        "python3 scripts/sync_ashare_company_positions.py",
    ),
    "peer_companies": (
        "sync_company_positions",
        "补齐同一产业链节点的可比公司",
        "official_disclosure_or_reviewed_relationship",
        "/api/company-positions",
        "python3 scripts/sync_ashare_company_positions.py",
    ),
    "upstream_companies": (
        "build_company_relationships",
        "补齐上游公司关系",
        "official_disclosure_or_reviewed_relationship",
        "/api/company-database/relationships/build",
        "python3 scripts/sync_ashare_company_positions.py",
    ),
    "downstream_companies": (
        "build_company_relationships",
        "补齐下游公司关系",
        "official_disclosure_or_reviewed_relationship",
        "/api/company-database/relationships/build",
        "python3 scripts/sync_ashare_company_positions.py",
    ),
    "ownership_candidates": (
        "import_ownership_tables",
        "导入股权/控制关系表并人工复核",
        "official_disclosure_or_reviewed_relationship",
        "/api/company-database/relationships/build",
        "python3 scripts/import_company_ownership_tables.py",
    ),
    "shareholder_network": (
        "import_ownership_tables",
        "扩展持股股东覆盖面",
        "official_disclosure_or_reviewed_relationship",
        "/api/company-database/relationships/build",
        "python3 scripts/import_company_ownership_tables.py",
    ),
    "approved_shareholder_network": (
        "review_ownership_relationships",
        "复核并批准股权关系候选",
        "official_disclosure_or_reviewed_relationship",
        "/api/company-database/relationships/review",
        "",
    ),
    "graph_edges": (
        "build_knowledge_graph",
        "把关系与事件写入知识图谱",
        "local_governed_graph_records",
        "/api/graph/query",
        "python3 scripts/backfill_full_knowledge_graph.py",
    ),
    "event_evidence_backlinks": (
        "backfill_event_evidence",
        "补齐事件证据回链",
        "official_public_evidence",
        "/api/evidence/extract",
        "python3 scripts/backfill_document_evidence.py",
    ),
    "relationship_evidence_backlinks": (
        "backfill_relationship_evidence",
        "补齐关系证据回链",
        "official_public_evidence",
        "/api/graph/knowledge-network/evidence-links/backfill",
        "python3 scripts/backfill_knowledge_network_evidence_links.py",
    ),
    "research_results": (
        "structure_research_reports",
        "结构化研报观点",
        "opinion_layer_not_fact_source",
        "/api/research-reports/structure",
        "python3 scripts/research_report_inbox_ingest.py",
    ),
    "research_reports": (
        "ingest_research_reports",
        "导入本地研报",
        "opinion_layer_not_fact_source",
        "/api/research-reports",
        "python3 scripts/research_report_inbox_ingest.py",
    ),
    "structured_viewpoints": (
        "structure_research_reports",
        "结构化研报观点",
        "opinion_layer_not_fact_source",
        "/api/research-reports/structure",
        "python3 scripts/research_report_inbox_ingest.py",
    ),
    "observation_items": (
        "run_personal_research_loop",
        "登记观察项",
        "local_workflow_records",
        "/api/personal-research/loop-overview",
        "python3 scripts/personal_intelligence_refresh.py",
    ),
    "analysis_conclusions": (
        "run_personal_research_loop",
        "登记分析结论",
        "local_workflow_records",
        "/api/personal-research/loop-overview",
        "python3 scripts/personal_intelligence_refresh.py",
    ),
    "simulation_feedback": (
        "record_simulation_feedback",
        "记录 paper-only 模拟反馈",
        "paper_only_feedback",
        "/api/simulation-feedback",
        "",
    ),
    "profile_field_coverage": (
        "extract_profile_fields",
        "提高公司画像字段覆盖度",
        "official_disclosure",
        "/api/company-database/profile-fields/extract",
        "python3 scripts/company_material_inbox_ingest.py",
    ),
    "database_coverage": (
        "audit_company_database_coverage",
        "提高公司库分节覆盖度",
        "official_disclosure",
        "/api/company-database/coverage/audit",
        "python3 scripts/build_company_database_minimum.py",
    ),
    "relationship_coverage": (
        "build_company_relationships",
        "提高关系分层覆盖度",
        "official_disclosure_or_reviewed_relationship",
        "/api/company-database/relationships/build",
        "python3 scripts/sync_ashare_company_positions.py",
    ),
    MISSING_FACT_FIELDS_LAYER: (
        "backfill_profile_fact_fields",
        "补齐公司画像事实字段",
        "official_disclosure",
        "/api/company-database/profile-fields/extract",
        "python3 scripts/company_material_inbox_ingest.py",
    ),
}

_DEFAULT_LAYER_ACTION = (
    "coverage_audit",
    "查看覆盖审计并补齐缺失分层",
    "official_disclosure",
    "/api/company-database/coverage/audit",
    "python3 scripts/build_company_database_minimum.py",
)

# 事实字段 → 字段组，镜像 `SystemService._company_profile_deep_coverage_row` 的分组。
_FACT_FIELD_GROUPS: dict[str, str] = {
    "legal_name": "identity",
    "display_name": "identity",
    "aliases": "identity",
    "country": "identity",
    "region": "identity",
    "sector": "identity",
    "industry": "identity",
    "identifiers": "identity",
    "security_ids": "listing",
    "tickers": "listing",
    "exchange": "listing",
    "market": "listing",
    "currency": "listing",
    "figi": "listing",
    "isin": "listing",
    "security_type": "listing",
    "status": "listing",
    "listing_date": "listing",
    "business_summary": "business",
    "products": "business",
    "employee_count": "business",
    "company_details": "business",
    "website_url": "contact",
    "ir_url": "contact",
    "headquarters": "contact",
    "management": "governance_people",
    "key_customers": "relationship_clues",
    "key_suppliers": "relationship_clues",
    "as_of_date": "market_snapshot",
    "close": "market_snapshot",
    "volume": "market_snapshot",
    "amount": "market_snapshot",
    "valuation_metrics": "market_snapshot",
    "period": "financial_snapshot",
    "revenue": "financial_snapshot",
    "net_income": "financial_snapshot",
    "gross_margin": "financial_snapshot",
    "cash": "financial_snapshot",
    "debt": "financial_snapshot",
    "source_ids": "source_evidence",
    "authorized_documents": "source_evidence",
    "field_evidence_ids": "source_evidence",
    "evidence_backlinks": "source_evidence",
    "research_report_count": "coverage_opinion",
    "structured_report_count": "coverage_opinion",
    "report_viewpoint_count": "coverage_opinion",
    "analyst_count": "coverage_opinion",
    "latest_report_at": "coverage_opinion",
    "latest_event_at": "workflow_feedback",
    "company_event_count": "workflow_feedback",
    "relationship_count": "workflow_feedback",
    "open_observation_count": "workflow_feedback",
    "analysis_conclusion_count": "workflow_feedback",
    "profile_coverage": "quality",
    "missing_fields": "quality",
    "event_backlink_rate": "quality",
    "relationship_backlink_rate": "quality",
}

# 字段组 → (action, label, source_type, endpoint, command)。
_FIELD_GROUP_ACTIONS: dict[str, tuple[str, str, str, str, str]] = {
    "identity": (
        "backfill_profile_identity_field",
        "补齐主体身份字段",
        "official_disclosure",
        "/api/company-database/profile-fields/extract",
        "python3 scripts/build_company_database_minimum.py",
    ),
    "listing": (
        "backfill_profile_listing_field",
        "补齐上市与证券属性字段",
        "exchange_disclosure",
        "/api/company-database/profile-fields/extract",
        "python3 scripts/build_company_database_minimum.py",
    ),
    "business": (
        "backfill_profile_business_field",
        "补齐业务描述字段",
        "company_ir_or_official_disclosure",
        "/api/company-database/material-inbox/ingest",
        "python3 scripts/company_material_inbox_ingest.py",
    ),
    "contact": (
        "backfill_profile_contact_field",
        "补齐官网与 IR 联系字段",
        "company_official",
        "/api/company-database/material-inbox/ingest",
        "python3 scripts/company_material_inbox_ingest.py",
    ),
    "governance_people": (
        "backfill_profile_governance_field",
        "补齐治理与管理层字段",
        "company_ir_or_official_disclosure",
        "/api/company-database/material-inbox/ingest",
        "python3 scripts/company_material_inbox_ingest.py",
    ),
    "relationship_clues": (
        "backfill_profile_relationship_clue_field",
        "补齐客户/供应商线索字段",
        "company_ir_or_official_disclosure",
        "/api/company-database/material-inbox/ingest",
        "python3 scripts/company_material_inbox_ingest.py",
    ),
    "market_snapshot": (
        "backfill_market_data",
        "补齐行情快照字段",
        "public_or_local_market_data",
        "/api/market-data/backfill",
        "python3 scripts/backfill_market_data.py",
    ),
    "financial_snapshot": (
        "backfill_financial_snapshot",
        "补齐财报快照字段",
        "official_financial_report",
        "/api/company-financial-metrics",
        "python3 scripts/backfill_company_financials_public.py",
    ),
    "source_evidence": (
        "backfill_field_evidence",
        "补齐字段证据回链",
        "official_public_evidence",
        "/api/evidence/extract",
        "python3 scripts/backfill_document_evidence.py",
    ),
    "coverage_opinion": (
        "structure_research_reports",
        "补齐研报观点槽位",
        "opinion_layer_not_fact_source",
        "/api/research-reports/structure",
        "python3 scripts/research_report_inbox_ingest.py",
    ),
    "workflow_feedback": (
        "run_personal_research_loop",
        "补齐研究流程记录",
        "local_workflow_records",
        "/api/personal-research/loop-overview",
        "python3 scripts/personal_intelligence_refresh.py",
    ),
    "quality": (
        "reconcile_company_quality",
        "重算公司画像质量指标",
        "derived_local_quality_metric",
        "/api/company-database/quality/reconcile",
        "python3 scripts/company_basic_info_production_audit.py",
    ),
}

_DEFAULT_FIELD_GROUP = "identity"


def _identifiers(values: Sequence[str] | None) -> list[str]:
    """Normalize an identifier sequence: drop blanks, dedupe, preserve order."""

    result: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _coverage_value(coverage_scores: Mapping[str, Any] | None, key: str) -> float:
    """Read a coverage score clamped to [0, 1]; missing/unparsable reads as 0.0."""

    raw = (coverage_scores or {}).get(key, 0.0)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 0.0
    if value != value:  # NaN never satisfies a threshold.
        return 0.0
    return max(0.0, min(1.0, value))


def _coverage_layer_name(coverage_key: str) -> str:
    return coverage_key[: -len("_score")] if coverage_key.endswith("_score") else coverage_key


def _non_negative_int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def resolve_status(
    *,
    profile_available: bool,
    blocking_gaps: Sequence[str],
    warning_gaps: Sequence[str],
    missing_fact_fields: Sequence[str],
    coverage_scores: Mapping[str, float],
) -> dict[str, Any]:
    """唯一判定入口，返回 `{"status", "label", "is_complete", "missing_layers"}`。

    `status="complete"` 当且仅当：`profile_available` ∧ 无 blocking/warning gaps
    ∧ `missing_fact_fields` 为空 ∧ `LAYER_COVERAGE_THRESHOLDS` 的所有阈值项达标。
    其余非 `not_found` 情况一律 `status="partial"`，并给出 `missing_layers`。
    """

    blocking = _identifiers(blocking_gaps)
    warning = _identifiers(warning_gaps)
    missing_fields = _identifiers(missing_fact_fields)
    unmet_coverage_layers = [
        _coverage_layer_name(coverage_key)
        for coverage_key, threshold in LAYER_COVERAGE_THRESHOLDS.items()
        if _coverage_value(coverage_scores, coverage_key) < float(threshold)
    ]
    missing_layers = _identifiers(
        [
            *blocking,
            *warning,
            *unmet_coverage_layers,
            *([MISSING_FACT_FIELDS_LAYER] if missing_fields else []),
        ]
    )
    if not profile_available:
        status = "not_found"
    elif blocking or warning or missing_fields or unmet_coverage_layers:
        status = "partial"
    else:
        status = "complete"
    return {
        "status": status,
        "label": STATUS_LABELS[status],
        "is_complete": status == "complete",
        "missing_layers": missing_layers,
    }


def coverage_denominator(*, total_fields: int, filled_fields: int) -> dict[str, Any]:
    """返回 `{"total_fields", "filled_fields", "score"}`，声明覆盖度分值的分母。

    `score = round(filled_fields / total_fields, 4)`；`total_fields` 为 0 时 `score=0.0`。
    `filled_fields` 被夹到 `[0, total_fields]`，负数与非数值输入按 0 处理。
    """

    total = _non_negative_int(total_fields)
    filled = min(_non_negative_int(filled_fields), total)
    score = round(filled / total, 4) if total else 0.0
    return {"total_fields": total, "filled_fields": filled, "score": score}


def _action_entry(
    *,
    target_field: str,
    target_type: str,
    spec: tuple[str, str, str, str, str],
    reason: str,
) -> dict[str, Any]:
    action, label, source_type, endpoint, command = spec
    return {
        "action": action,
        "label": label,
        "target_field": target_field,
        "target_type": target_type,
        "source_type": source_type,
        "endpoint": endpoint,
        "command": command,
        "reason": reason,
    }


def next_actions(
    *,
    status: str,
    missing_layers: Sequence[str],
    missing_fact_fields: Sequence[str],
) -> list[dict[str, Any]]:
    """非 `complete` 必返回 ≥1 条，每条含 `target_field` / `source_type` / `command` 或 `endpoint`。"""

    normalized_status = str(status or "").strip() or "partial"
    if normalized_status == "complete":
        return []
    actions: list[dict[str, Any]] = []
    for layer in _identifiers(missing_layers)[:_DEFAULT_ACTION_LIMIT]:
        if layer == MISSING_FACT_FIELDS_LAYER and _identifiers(missing_fact_fields):
            # 事实字段缺口逐字段给动作，避免与字段级条目重复。
            continue
        actions.append(
            _action_entry(
                target_field=layer,
                target_type="layer",
                spec=_LAYER_ACTIONS.get(layer, _DEFAULT_LAYER_ACTION),
                reason=f"完整度判定仍缺分层 {layer}",
            )
        )
    for field_name in _identifiers(missing_fact_fields)[:_DEFAULT_ACTION_LIMIT]:
        group = _FACT_FIELD_GROUPS.get(field_name, _DEFAULT_FIELD_GROUP)
        spec = _FIELD_GROUP_ACTIONS.get(group, _FIELD_GROUP_ACTIONS[_DEFAULT_FIELD_GROUP])
        actions.append(
            _action_entry(
                target_field=field_name,
                target_type="fact_field",
                spec=spec,
                reason=f"事实字段 {field_name}（{group}）尚未填充",
            )
        )
    if not actions:
        actions.append(
            _action_entry(
                target_field="company_profile" if normalized_status == "not_found" else "database_coverage",
                target_type="layer",
                spec=_LAYER_ACTIONS["company_profile"] if normalized_status == "not_found" else _DEFAULT_LAYER_ACTION,
                reason=f"完整度状态为 {normalized_status}，需要先确认公司库覆盖情况",
            )
        )
    return actions
