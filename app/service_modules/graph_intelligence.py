from __future__ import annotations

from collections import Counter, defaultdict
import re
from typing import Any, Iterable, Mapping

from app.utils import to_plain


GRAPH_NODE_ID_CANDIDATES = [
    "id",
    "data_id",
    "issuer_id",
    "security_id",
    "card_id",
    "document_id",
    "evidence_id",
    "thesis_id",
    "signal_id",
    "decision_id",
    "intent_id",
    "proposal_id",
    "mapping_id",
    "snapshot_id",
    "holding_id",
    "event_id",
    "replay_id",
    "action_id",
    "challenger_id",
    "review_id",
    "exception_id",
    "task_id",
    "relationship_id",
    "research_report_id",
    "viewpoint_id",
    "forecast_id",
    "analyst_id",
    "score_id",
    "observation_id",
    "analysis_conclusion_id",
    "simulation_feedback_id",
]


def graph_node_identity(collection: str, row: Mapping[str, Any]) -> str:
    candidates = [
        f"{collection[:-1]}_id" if collection.endswith("s") else f"{collection}_id",
        *GRAPH_NODE_ID_CANDIDATES,
    ]
    for key in candidates:
        value = str(row.get(key, "")).strip()
        if value:
            return value
    return ""


def neo4j_label(collection: str) -> str:
    return "".join(part.capitalize() for part in collection.split("_"))


def neo4j_relationship_type(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_]+", "_", value).strip("_").upper()
    return normalized or "RELATED_TO"


def neo4j_properties(values: Mapping[str, Any], defaults: Mapping[str, Any]) -> dict[str, Any]:
    props = {str(key): to_plain(value) for key, value in values.items()}
    props.update(defaults)
    return props


GRAPH_KNOWLEDGE_REQUIRED_LAYERS = [
    "company_profile",
    "industry_position",
    "company_relationship",
    "shareholder_holding",
    "document",
    "evidence",
    "company_event",
    "research_report",
    "viewpoint",
]


def _row_value(row: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = str(row.get(key, "") or "").strip()
        if value:
            return value
    return ""


def _issuer_aliases(issuer: Mapping[str, Any], securities: Iterable[Mapping[str, Any]]) -> set[str]:
    aliases = {
        _row_value(issuer, "issuer_id"),
        _row_value(issuer, "legal_name", "name"),
        _row_value(issuer, "cik"),
        _row_value(issuer, "lei"),
    }
    for alias in issuer.get("aliases", []) or []:
        text = str(alias or "").strip()
        if text:
            aliases.add(text)
    issuer_id = _row_value(issuer, "issuer_id")
    for security in securities:
        if _row_value(security, "issuer_id") != issuer_id:
            continue
        aliases.add(_row_value(security, "security_id"))
        aliases.add(_row_value(security, "ticker", "symbol", "code"))
    return {alias.lower() for alias in aliases if alias}


def _matches_issuer(row: Mapping[str, Any], issuer_id: str, security_ids: set[str], aliases: set[str]) -> bool:
    if _row_value(row, "issuer_id") == issuer_id:
        return True
    security_id = _row_value(row, "security_id")
    if security_id and security_id in security_ids:
        return True
    subject_id = _row_value(row, "subject_id")
    object_id = _row_value(row, "object_id")
    if subject_id == issuer_id or object_id == issuer_id:
        return True
    searchable = " ".join(
        str(row.get(key, "") or "")
        for key in ["title", "summary", "body", "statement", "source_uri", "entity_name", "metadata", "covered_entities"]
    ).lower()
    return bool(searchable and any(alias and alias in searchable for alias in aliases))


def _count_seed_rows(rows: Iterable[Mapping[str, Any]]) -> int:
    count = 0
    for row in rows:
        text = " ".join(
            str(row.get(key, "") or "")
            for key in ["source_id", "source_type", "source_uri", "metadata", "document_type", "rights_boundary"]
        ).lower()
        if "obsidian" in text or "local_seed" in text or "knowledge-graph-seed" in text:
            count += 1
    return count


def _layer_status(count: int, required: int) -> str:
    if count >= required:
        return "sufficient"
    if count > 0:
        return "thin"
    return "missing"


def _backfill_action(layer: str) -> str:
    return {
        "company_profile": "运行公司画像/字段抽取，补齐 issuer/company profile 基础事实",
        "industry_position": "运行产业链 company position 同步或人工定位公司所在链路节点",
        "company_relationship": "运行公司关系候选抽取和审核，把客户、供应商、竞争、股权关系物化为 CompanyRelationship",
        "shareholder_holding": "导入 13F/股东表或批准 ownership relationship，形成同持有人/事实股东网络",
        "document": "导入公司公告、IR、研报或本地材料为 Document",
        "evidence": "对 Document 执行 evidence 切片/抽取，形成可追溯证据节点",
        "company_event": "运行事件时间线构建和事件审核，把披露/新闻/研报材料物化为 CompanyEvent",
        "research_report": "扫描并结构化本地研报，生成 ResearchReport",
        "viewpoint": "结构化研报观点或人工登记 ReportViewpoint，把观点层接入图谱",
    }.get(layer, f"补齐 {layer} 数据层")


def knowledge_network_readiness_report(
    *,
    issuers: Iterable[Mapping[str, Any]],
    securities: Iterable[Mapping[str, Any]],
    company_profiles: Iterable[Mapping[str, Any]],
    company_positions: Iterable[Mapping[str, Any]],
    industry_chains: Iterable[Mapping[str, Any]],
    company_relationships: Iterable[Mapping[str, Any]],
    institutional_holdings: Iterable[Mapping[str, Any]],
    documents: Iterable[Mapping[str, Any]],
    evidence: Iterable[Mapping[str, Any]],
    company_events: Iterable[Mapping[str, Any]],
    structured_research_reports: Iterable[Mapping[str, Any]],
    report_viewpoints: Iterable[Mapping[str, Any]],
    graph: Mapping[str, Any],
    issuer_id: str = "",
    min_layers: int = 7,
    min_edges: int = 20,
    min_communities: int = 4,
) -> dict[str, Any]:
    issuer_rows = [dict(row) for row in issuers]
    security_rows = [dict(row) for row in securities]
    chain_rows = [dict(row) for row in industry_chains]
    if issuer_id:
        issuer_rows = [row for row in issuer_rows if _row_value(row, "issuer_id") == issuer_id]
    issuer_ids = {_row_value(row, "issuer_id") for row in issuer_rows if _row_value(row, "issuer_id")}
    if not issuer_ids and issuer_id:
        issuer_ids = {issuer_id}
    security_ids = {
        _row_value(row, "security_id")
        for row in security_rows
        if not issuer_ids or _row_value(row, "issuer_id") in issuer_ids
    }
    security_ids = {item for item in security_ids if item}
    aliases_by_issuer = {row["issuer_id"]: _issuer_aliases(row, security_rows) for row in issuer_rows if row.get("issuer_id")}

    def scoped(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
        scoped_rows: list[dict[str, Any]] = []
        for row in rows:
            plain = dict(row)
            if not issuer_ids:
                scoped_rows.append(plain)
                continue
            if any(_matches_issuer(plain, candidate, security_ids, aliases_by_issuer.get(candidate, set())) for candidate in issuer_ids):
                scoped_rows.append(plain)
        return scoped_rows

    profile_rows = scoped(company_profiles)
    position_rows = scoped(company_positions)
    relationship_rows = scoped(company_relationships)
    holding_rows = scoped(institutional_holdings)
    document_rows = scoped(documents)
    evidence_rows = list(evidence)
    document_ids = {_row_value(row, "document_id") for row in document_rows if _row_value(row, "document_id")}
    evidence_rows = [dict(row) for row in evidence_rows if not document_ids or _row_value(row, "document_id") in document_ids or (not issuer_ids and not document_ids)]
    event_rows = scoped(company_events)
    report_rows = scoped(structured_research_reports)
    report_ids = {_row_value(row, "research_report_id") for row in report_rows if _row_value(row, "research_report_id")}
    viewpoint_rows = [
        dict(row)
        for row in report_viewpoints
        if (not issuer_ids and not report_ids)
        or any(_matches_issuer(row, candidate, security_ids, aliases_by_issuer.get(candidate, set())) for candidate in issuer_ids)
        or _row_value(row, "research_report_id") in report_ids
    ]
    chain_ids = {_row_value(row, "chain_id") for row in position_rows if _row_value(row, "chain_id")}
    chain_edge_count = 0
    chain_node_count = 0
    for chain in chain_rows:
        if chain_ids and _row_value(chain, "chain_id") not in chain_ids:
            continue
        chain_edge_count += len(chain.get("edges", []) or [])
        chain_node_count += len(chain.get("nodes", []) or [])

    layer_counts = {
        "company_profile": len(profile_rows) or len(issuer_ids),
        "industry_position": len(position_rows),
        "company_relationship": len(relationship_rows),
        "shareholder_holding": len(holding_rows),
        "document": len(document_rows),
        "evidence": len(evidence_rows),
        "company_event": len(event_rows),
        "research_report": len(report_rows),
        "viewpoint": len(viewpoint_rows),
    }
    layer_requirements = {
        "company_profile": 1,
        "industry_position": 1,
        "company_relationship": 1,
        "shareholder_holding": 1,
        "document": 2,
        "evidence": 1,
        "company_event": 1,
        "research_report": 1,
        "viewpoint": 1,
    }
    layer_status = {layer: _layer_status(layer_counts[layer], layer_requirements[layer]) for layer in GRAPH_KNOWLEDGE_REQUIRED_LAYERS}
    present_layers = [layer for layer, status in layer_status.items() if status != "missing"]
    thin_layers = [layer for layer, status in layer_status.items() if status == "thin"]
    missing_layers = [layer for layer, status in layer_status.items() if status == "missing"]

    graph_edges = [dict(edge) for edge in graph.get("edges", []) or [] if isinstance(edge, Mapping)]
    edge_types = Counter(str(edge.get("type", "") or "") for edge in graph_edges)
    community_sources = {
        "company": bool(issuer_ids or security_ids or profile_rows),
        "industry": bool(position_rows or chain_edge_count),
        "relationship": bool(relationship_rows),
        "shareholder": bool(holding_rows),
        "document": bool(document_rows or evidence_rows),
        "event": bool(event_rows),
        "research": bool(report_rows or viewpoint_rows),
    }
    visible_communities = sorted([name for name, present in community_sources.items() if present])
    seed_document_ids = {
        _row_value(row, "document_id")
        for row in document_rows
        if _row_value(row, "document_id") and _count_seed_rows([row])
    }
    seed_evidence_rows = sum(1 for row in evidence_rows if _row_value(row, "document_id") in seed_document_ids)
    seed_rows = seed_evidence_rows + sum(
        _count_seed_rows(rows)
        for rows in [position_rows, relationship_rows, holding_rows, document_rows, event_rows, report_rows, viewpoint_rows]
    )
    real_rows = sum(layer_counts.values()) - seed_rows
    seed_ratio = round(seed_rows / max(1, seed_rows + real_rows), 4)
    cross_links = {
        "document_evidence_links": sum(1 for row in evidence_rows if _row_value(row, "document_id") in document_ids),
        "event_document_links": sum(1 for row in event_rows if row.get("document_ids")),
        "event_evidence_links": sum(1 for row in event_rows if row.get("evidence_ids")),
        "relationship_evidence_links": sum(1 for row in relationship_rows if row.get("evidence_ids")),
        "viewpoint_evidence_links": sum(1 for row in viewpoint_rows if row.get("evidence_ids")),
        "viewpoint_report_links": sum(1 for row in viewpoint_rows if _row_value(row, "research_report_id") in report_ids),
        "industry_chain_edges": chain_edge_count,
        "industry_chain_nodes": chain_node_count,
    }
    enough_layers = len(present_layers) >= min_layers
    enough_edges = len(graph_edges) >= min_edges
    enough_communities = len(visible_communities) >= min_communities
    not_seed_dependent = seed_ratio < 0.5 or real_rows >= seed_rows
    ready = enough_layers and enough_edges and enough_communities and not missing_layers and not_seed_dependent
    next_actions = [
        {"layer": layer, "status": layer_status[layer], "action": _backfill_action(layer)}
        for layer in [*missing_layers, *thin_layers]
    ]
    if seed_ratio >= 0.5:
        next_actions.append(
            {
                "layer": "seed_dependency",
                "status": "seed_dominant",
                "action": "用真实本地导入记录替换 Obsidian seed/fixture 数据，避免验收图谱只证明样例网络",
            }
        )
    if len(graph_edges) < min_edges:
        next_actions.append(
            {
                "layer": "graph_edges",
                "status": "thin",
                "action": "补充跨层边：Document-Evidence、Event-Document、Relationship-Evidence、Report-Viewpoint、Holding-Company",
            }
        )

    return {
        "schema_id": "knowledge-network-readiness-v1",
        "issuer_id": issuer_id,
        "issuer_count": len(issuer_ids) if issuer_ids else len(issuer_rows),
        "security_count": len(security_ids),
        "ready_for_obsidian_exploration": ready,
        "status": "ready" if ready else "needs_data",
        "layer_counts": layer_counts,
        "layer_status": layer_status,
        "present_layers": present_layers,
        "missing_layers": missing_layers,
        "thin_layers": thin_layers,
        "community_sources": community_sources,
        "visible_communities": visible_communities,
        "graph_summary": {
            "edges": len(graph_edges),
            "edge_types": dict(sorted(edge_types.items())),
            "communities": len(visible_communities),
            "min_edges": min_edges,
            "min_communities": min_communities,
        },
        "cross_links": cross_links,
        "seed_dependency": {
            "seed_rows": seed_rows,
            "real_rows": real_rows,
            "seed_ratio": seed_ratio,
            "seed_dependent": seed_ratio >= 0.5,
        },
        "next_actions": next_actions,
        "automation_allowed": False,
        "live_execution_allowed": False,
        "usage_boundary": "knowledge_network_readiness_is_local_data_density_audit_no_broker_no_trade_execution",
    }
