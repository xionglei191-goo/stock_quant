from __future__ import annotations

from typing import Any, Mapping


LOCAL_SOURCE_USAGE_BOUNDARY = "local_public_or_provided_data_only_no_broker_no_trade_execution"
SOURCE_INPUT_QUEUE_USAGE_BOUNDARY = "local_public_or_provided_source_input_queue_no_auto_fact_promotion_no_broker_no_trade_execution"

MANUAL_INPUT_LAYERS = {"document", "evidence", "shareholder_holding", "research_report", "viewpoint"}
SOURCE_BACKED_LAYERS = ("document", "evidence", "shareholder_holding", "research_report", "viewpoint")

REQUIRED_SOURCE_FIELDS: dict[str, list[str]] = {
    "shareholder_holding": [
        "filer identity",
        "report period",
        "security identifier",
        "holding quantity or market value",
        "public filing/source URI",
    ],
    "document": [
        "document type",
        "source id",
        "source URI or local path",
        "issuer/security mapping",
        "rights/source boundary",
    ],
    "evidence": [
        "document id",
        "quoted span or extracted text",
        "issuer/security mapping",
        "parser/model version",
    ],
    "research_report": [
        "research report asset id or local path",
        "broker/institution",
        "publication date",
        "opinion-only boundary",
    ],
    "viewpoint": [
        "research_report_id",
        "viewpoint text/topic",
        "viewpoint type",
        "issuer/security mapping",
        "opinion-only boundary",
    ],
}

LAYER_ACTION_SPECS: dict[str, dict[str, Any]] = {
    "company_event": {
        "action": "build_company_events",
        "label": "从本地行情、披露和已绑定研报构建公司事件",
        "endpoint": "/api/company-database/events/build",
        "execute_required": True,
        "manual_input_required": False,
    },
    "company_relationship": {
        "action": "build_company_relationships",
        "label": "从上市证券、研报覆盖、披露和股权表构建关系候选",
        "endpoint": "/api/company-database/relationships/build",
        "execute_required": True,
        "manual_input_required": False,
    },
    "shareholder_holding": {
        "action": "import_13f_holdings",
        "label": "导入或映射公开 13F/持仓数据，补齐持有人网络",
        "endpoint": "/api/13f/filings/parse",
        "fallback_endpoint": "/api/13f/holdings",
        "execute_required": True,
        "manual_input_required": True,
    },
    "document": {
        "action": "ingest_source_documents",
        "label": "登记本地或公开来源文档，补齐图谱文档层",
        "endpoint": "/api/ingestion/documents",
        "execute_required": True,
        "manual_input_required": True,
    },
    "evidence": {
        "action": "extract_and_link_evidence",
        "label": "从已登记文档抽取证据并回链事件、关系和观点",
        "endpoint": "/api/evidence/extract",
        "secondary_endpoint": "/api/graph/knowledge-network/evidence-links/backfill",
        "execute_required": True,
        "manual_input_required": True,
    },
    "research_report": {
        "action": "structure_research_reports",
        "label": "把已入库研报结构化为观点层对象，保持观点边界",
        "endpoint": "/api/research-reports/structure",
        "execute_required": True,
        "manual_input_required": True,
    },
    "viewpoint": {
        "action": "structure_or_register_viewpoints",
        "label": "生成或登记研报观点，补齐观点节点和观点边",
        "endpoint": "/api/research-reports/structure",
        "fallback_endpoint": "/api/research-report-viewpoints",
        "execute_required": True,
        "manual_input_required": True,
    },
}


def layer_action(
    layer: str,
    target_payload: Mapping[str, Any],
    *,
    symbol_payload: Mapping[str, Any] | None = None,
    source_payload_style: str = "target",
) -> dict[str, Any] | None:
    spec = LAYER_ACTION_SPECS.get(layer)
    if not spec:
        return None
    action = {
        "layer": layer,
        "method": "POST",
        "default_execute": False,
        "usage_boundary": LOCAL_SOURCE_USAGE_BOUNDARY,
        **spec,
    }
    payload = dict(target_payload)
    if layer in {"company_event", "company_relationship"}:
        payload = dict(symbol_payload or target_payload)
    elif layer == "shareholder_holding":
        payload = {**payload, "import_holdings": False}
    elif layer == "document":
        payload = {**payload, "automation_allowed": False}
    elif layer == "evidence":
        payload = {**payload, "execute": False}
    elif layer in {"research_report", "viewpoint"} and source_payload_style == "symbol" and symbol_payload is not None:
        payload = {**dict(symbol_payload), "dry_run": True}
    action["payload"] = payload
    if layer in MANUAL_INPUT_LAYERS:
        action["required_source_fields"] = list(REQUIRED_SOURCE_FIELDS.get(layer, []))
    return action


def candidate_review_action(target_payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "layer": "candidate_review",
        "action": "review_relationship_and_event_candidates",
        "label": "审核候选事件和关系后再提升为可信图谱事实",
        "endpoint": "/api/company-database/events/review and /api/company-database/relationships/review",
        "method": "POST",
        "execute_required": False,
        "default_execute": False,
        "payload": dict(target_payload),
        "usage_boundary": "manual_review_required_before_fact_promotion",
    }
