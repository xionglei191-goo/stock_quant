from __future__ import annotations

from collections import Counter, defaultdict, deque
from dataclasses import dataclass
import re
from typing import Any, Mapping

from app.utils import to_plain, utcnow

from . import graph_source_actions, knowledge_graph_bulk
from .graph_intelligence import graph_node_identity


RAW_LABEL_MARKERS = ("obsidian", "relationship", "pos_", "doc_", "hold_", "issuer_", "security_", "sec_", "md_", "vp_rr_", "rr_", "srr_")
QUALITY_REMEDIATION_USAGE_BOUNDARY = "graph_quality_remediation_is_dry_run_local_public_or_provided_data_only_no_broker_no_trade_execution"
SOURCE_QUEUE_QUALITY_CHECKS = {"edge_density", "community_count", "layer_count", "hub_dominance", "leaf_ratio", "graph_fragmentation"}
QUALITY_RECONCILE_CHECKS = {"duplicate_labels", "display_duplicate_edges", "duplicate_edges"}

RELATIONSHIP_TYPE_LABELS = {
    "industry_position": "产业链位置",
    "industry_peer": "同类关系",
    "upstream_of": "上游关系",
    "downstream_of": "下游关系",
    "ownership": "股权关系",
    "shareholder": "事实股东",
    "shareholder_candidate": "股东候选",
    "controller": "实际控制",
    "controller_candidate": "实控候选",
    "subsidiary": "子公司",
    "subsidiary_candidate": "子公司候选",
    "investee": "参股公司",
    "investee_candidate": "参股候选",
    "customer": "客户关系",
    "customer_candidate": "客户候选",
    "supplier": "供应商关系",
    "supplier_candidate": "供应商候选",
    "partner": "合作伙伴",
    "partner_candidate": "合作候选",
    "institution_coverage": "机构覆盖",
    "listed_security": "上市证券",
    "relationship": "关系",
    "relationship_subject": "关系主体",
    "relationship_object": "关系对象",
    "same_holder_related_company": "同持有人",
    "has_13f_holding": "13F 持仓",
    "holds_security": "持有证券",
    "issues": "发行证券",
    "positioned_as": "产业定位",
    "has_company_position": "产业定位",
    "security_for_position": "定位证券",
    "position_in_chain_node": "产业定位",
    "event_from_document": "事件资料",
    "event_on_security": "事件证券",
    "covered_by_report": "研报覆盖",
    "analyst_covers": "分析师覆盖",
    "report_has_viewpoint": "研报观点",
    "viewpoint_on_company": "观点覆盖",
    "viewpoint_evidence": "观点证据",
    "event_evidence": "事件证据",
    "relationship_evidence": "关系证据",
}


@dataclass(frozen=True)
class GraphQualityThresholds:
    min_edges: int = 12
    min_communities: int = 3
    min_layers: int = 5
    max_duplicate_labels: int = 0
    max_raw_label_leaks: int = 0
    max_display_duplicate_edges: int = 0
    max_duplicate_edges: int = 4
    min_structural_nodes: int = 8
    max_hub_edge_share: float = 0.72
    max_leaf_ratio: float = 0.86
    min_largest_component_ratio: float = 0.72

    def as_dict(self) -> dict[str, int | float]:
        return {
            "min_edges": self.min_edges,
            "min_communities": self.min_communities,
            "min_layers": self.min_layers,
            "max_duplicate_labels": self.max_duplicate_labels,
            "max_raw_label_leaks": self.max_raw_label_leaks,
            "max_display_duplicate_edges": self.max_display_duplicate_edges,
            "max_duplicate_edges": self.max_duplicate_edges,
            "min_structural_nodes": self.min_structural_nodes,
            "max_hub_edge_share": self.max_hub_edge_share,
            "max_leaf_ratio": self.max_leaf_ratio,
            "min_largest_component_ratio": self.min_largest_component_ratio,
        }


DEFAULT_GRAPH_QUALITY_THRESHOLDS = GraphQualityThresholds()


def _threshold_int(payload: Mapping[str, Any], key: str, default: int) -> int:
    if key not in payload:
        return default
    value = payload.get(key)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _threshold_float(payload: Mapping[str, Any], key: str, default: float) -> float:
    if key not in payload:
        return default
    value = payload.get(key)
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _graph_quality_thresholds(payload: Mapping[str, Any]) -> GraphQualityThresholds:
    defaults = DEFAULT_GRAPH_QUALITY_THRESHOLDS
    return GraphQualityThresholds(
        min_edges=_threshold_int(payload, "min_edges", defaults.min_edges),
        min_communities=_threshold_int(payload, "min_communities", defaults.min_communities),
        min_layers=_threshold_int(payload, "min_layers", defaults.min_layers),
        max_duplicate_labels=_threshold_int(payload, "max_duplicate_labels", defaults.max_duplicate_labels),
        max_raw_label_leaks=_threshold_int(payload, "max_raw_label_leaks", defaults.max_raw_label_leaks),
        max_display_duplicate_edges=_threshold_int(payload, "max_display_duplicate_edges", defaults.max_display_duplicate_edges),
        max_duplicate_edges=_threshold_int(payload, "max_duplicate_edges", defaults.max_duplicate_edges),
        min_structural_nodes=_threshold_int(payload, "min_structural_nodes", defaults.min_structural_nodes),
        max_hub_edge_share=_threshold_float(payload, "max_hub_edge_share", defaults.max_hub_edge_share),
        max_leaf_ratio=_threshold_float(payload, "max_leaf_ratio", defaults.max_leaf_ratio),
        min_largest_component_ratio=_threshold_float(
            payload,
            "min_largest_component_ratio",
            defaults.min_largest_component_ratio,
        ),
    )


def _status_label(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text.replace("_", " ").replace("-", " ").strip().title()


def _relationship_type_label(value: Any) -> str:
    key = str(value or "").strip().lower()
    if not key:
        return ""
    return RELATIONSHIP_TYPE_LABELS.get(key, "")


def _holding_label(row: Mapping[str, Any]) -> str:
    holder = str(row.get("filer_name") or row.get("filer_cik") or "机构").strip()
    target = (
        _readable_id_label(row.get("security_id", ""), row)
        or _readable_id_label(row.get("issuer_id", ""), row)
        or str(row.get("security_id") or row.get("issuer_id") or "").strip()
    )
    period = str(row.get("report_period", "") or "").strip()
    parts = [holder]
    if target:
        parts.append(target)
    label = " / ".join(parts)
    if period:
        label = f"{label} · {period}"
    return f"13F 持仓 · {label}"


def _first_alias(row: Mapping[str, Any]) -> str:
    aliases = row.get("aliases") or row.get("entity_aliases") or []
    if isinstance(aliases, str):
        aliases = [aliases]
    if not isinstance(aliases, list):
        return ""
    for alias in aliases:
        text = str(alias or "").strip()
        if text:
            return text
    return ""


def _issuer_label(row: Mapping[str, Any]) -> str:
    ticker = str(row.get("ticker") or row.get("symbol") or "").strip()
    if not ticker:
        ticker = _first_alias(row)
    if not ticker:
        ticker = _readable_id_label(row.get("issuer_id") or row.get("node_id") or "", row)
    if ticker:
        return f"{ticker.upper()} · 公司"
    legal_name = str(row.get("legal_name") or row.get("name") or row.get("issuer_name") or "").strip()
    if legal_name:
        return f"{legal_name} · 公司"
    return ""


def _security_label(row: Mapping[str, Any]) -> str:
    ticker = str(row.get("ticker") or row.get("symbol") or "").strip()
    if not ticker:
        ticker = _readable_id_label(row.get("security_id") or row.get("node_id") or "", row)
    if ticker:
        market = str(row.get("market") or row.get("exchange") or "证券").strip()
        return f"{ticker.upper()} · {market}"
    return ""


def _readable_id_label(value: Any, row: Mapping[str, Any] | None = None) -> str:
    row = row or {}
    identifier = str(value or "").strip()
    lower = identifier.lower()
    if not identifier:
        return ""
    if lower.startswith("issuer_"):
        return str(identifier[len("issuer_") :]).upper()
    if lower.startswith("security_"):
        return str(identifier[len("security_") :].replace("_", " ")).upper()
    if lower.startswith("sec_"):
        return str(identifier[len("sec_") :]).upper()
    market_match = re.match(r"^md_.+?_(sec_[a-z0-9_]+|security_[a-z0-9_]+)_([0-9]{4}-[0-9]{2}-[0-9]{2})_(eod|delayed)$", lower)
    if market_match:
        security_label = _readable_id_label(row.get("security_id") or market_match.group(1))
        return f"行情 {security_label} {market_match.group(2)}"
    if lower.startswith("md_"):
        date = str(row.get("as_of_date", "") or "").strip()
        security_label = _readable_id_label(row.get("security_id", ""))
        return f"行情 {security_label} {date}".strip()
    if lower.startswith("vp_rr_") or lower.startswith("vp_"):
        return "研究观点"
    if lower.startswith("rr_") or lower.startswith("srr_"):
        return "研报主题"
    return ""


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "execute"}


def _symbols_payload(symbol: str, payload: Mapping[str, Any], *, execute: bool) -> dict[str, Any]:
    result = {
        "symbols": [symbol],
        "limit": 1,
        "execute": execute,
    }
    for key in ["event_limit", "relationship_limit"]:
        if key in payload:
            result[key] = payload[key]
    return result


def _node_label(collection: str, row: Mapping[str, Any]) -> str:
    if collection == "market_data":
        readable = _readable_id_label(row.get("data_id") or graph_node_identity(collection, row), row)
        if readable:
            return readable
    if collection == "issuers":
        label = _issuer_label(row)
        if label:
            return label
    if collection == "securities":
        label = _security_label(row)
        if label:
            return label
    if collection == "institutional_holdings":
        return _holding_label(row)
    for key in [
        "label",
        "name",
        "legal_name",
        "ticker",
        "title",
        "summary",
        "entity_name",
        "filer_name",
        "relationship_type",
        "event_type",
        "document_type",
    ]:
        value = str(row.get(key, "") or "").strip()
        if value:
            if key == "relationship_type":
                readable_relationship = _relationship_type_label(value)
                if readable_relationship:
                    return readable_relationship
            readable = _readable_id_label(value, row)
            return readable or value
    metadata = row.get("metadata")
    if isinstance(metadata, Mapping):
        for key in ["entity_name", "display_name", "label"]:
            value = str(metadata.get(key, "") or "").strip()
            if value:
                return value
    identity = graph_node_identity(collection, row)
    return _readable_id_label(identity, row) or _status_label(identity)


def _edge_endpoint(edge: Mapping[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = str(edge.get(key, "") or "").strip()
        if value:
            return value
    return ""


def _chain_node_identity(row: Mapping[str, Any]) -> str:
    node_id = str(row.get("node_id", "") or "").strip()
    chain_id = str(row.get("chain_id", "") or "").strip()
    if not node_id:
        return graph_node_identity("chain_nodes", row)
    if chain_id and ":" not in node_id:
        return f"{chain_id}:{node_id}"
    return node_id


def _position_chain_node_identity(row: Mapping[str, Any], node_id: Any) -> str:
    raw_node_id = str(node_id or "").strip()
    chain_id = str(row.get("chain_id", "") or "").strip()
    if chain_id and raw_node_id and ":" not in raw_node_id:
        return f"{chain_id}:{raw_node_id}"
    return raw_node_id


def _display_relationship_edge(row: Mapping[str, Any]) -> tuple[str, str, str] | None:
    source = _edge_endpoint(row, ("source_issuer_id", "from_issuer_id", "subject_id", "issuer_id", "from"))
    target = _edge_endpoint(row, ("target_issuer_id", "to_issuer_id", "object_id", "related_issuer_id", "to"))
    edge_type = str(row.get("relationship_type") or "COMPANY_RELATIONSHIP").strip() or "COMPANY_RELATIONSHIP"
    if not source or not target or source == target:
        return None
    return source, target, edge_type


def _graph_structure_metrics(graph: Mapping[str, Any], *, display_model: bool = True) -> dict[str, Any]:
    node_ids: set[str] = set()
    redirects: dict[str, str] = {}
    for collection, rows in graph.items():
        if collection == "edges" or not isinstance(rows, list):
            continue
        for row in rows:
            if isinstance(row, Mapping):
                identity = _chain_node_identity(row) if display_model and collection == "chain_nodes" else graph_node_identity(collection, row)
                if display_model and collection == "market_data":
                    security_id = str(row.get("security_id", "") or "").strip()
                    if security_id:
                        redirects[identity] = f"market_data_summary:{security_id}"
                if display_model and collection == "company_relationships":
                    display_edge = _display_relationship_edge(row)
                    if display_edge:
                        redirects[identity] = f"relationship_summary:{display_edge[0]}:{display_edge[1]}:{display_edge[2]}"
                node_ids.add(redirects.get(identity, identity))
                if display_model and collection == "company_positions":
                    for node_id in row.get("node_ids", []) or []:
                        scoped_node_id = _position_chain_node_identity(row, node_id)
                        if scoped_node_id:
                            node_ids.add(scoped_node_id)

    degree: Counter[str] = Counter()
    edge_type_counts: Counter[str] = Counter()
    edge_keys: Counter[tuple[str, str, str]] = Counter()
    adjacency: dict[str, set[str]] = defaultdict(set)
    valid_edge_count = 0
    seen_display_edges: set[tuple[str, str, str]] = set()
    if display_model:
        for row in graph.get("company_relationships", []) or []:
            if not isinstance(row, Mapping):
                continue
            display_edge = _display_relationship_edge(row)
            if not display_edge:
                continue
            source, target, edge_type = display_edge
            node_ids.add(source)
            node_ids.add(target)
            ordered = (source, target) if source <= target else (target, source)
            edge_key = (ordered[0], ordered[1], edge_type)
            edge_keys[edge_key] += 1
            if edge_key in seen_display_edges:
                continue
            seen_display_edges.add(edge_key)
            valid_edge_count += 1
            degree[source] += 1
            degree[target] += 1
            edge_type_counts[edge_type] += 1
            adjacency[source].add(target)
            adjacency[target].add(source)
    for edge in graph.get("edges", []) or []:
        if not isinstance(edge, Mapping):
            continue
        raw_edge_type = str(edge.get("type") or edge.get("relationship_type") or edge.get("label") or "RELATED").strip()
        if display_model and raw_edge_type in {"HAS_COMPANY_RELATIONSHIP", "RELATIONSHIP_SUBJECT", "RELATIONSHIP_OBJECT"}:
            continue
        raw_source = _edge_endpoint(edge, ("from", "source", "source_id", "from_id"))
        raw_target = _edge_endpoint(edge, ("to", "target", "target_id", "to_id"))
        source = redirects.get(raw_source, raw_source)
        target = redirects.get(raw_target, raw_target)
        edge_type = raw_edge_type
        if not source or not target:
            continue
        node_ids.add(source)
        node_ids.add(target)
        ordered = (source, target) if source <= target else (target, source)
        edge_key = (ordered[0], ordered[1], edge_type)
        if display_model and edge_key in seen_display_edges:
            continue
        seen_display_edges.add(edge_key)
        edge_keys[edge_key] += 1
        valid_edge_count += 1
        degree[source] += 1
        degree[target] += 1
        edge_type_counts[edge_type] += 1
        adjacency[source].add(target)
        adjacency[target].add(source)

    connected_nodes = set(degree)
    isolated_node_count = len(node_ids - connected_nodes)
    leaf_count = sum(1 for node_id in node_ids if degree.get(node_id, 0) == 1)
    max_degree = max(degree.values(), default=0)
    duplicate_edge_count = sum(count - 1 for count in edge_keys.values() if count > 1)

    visited: set[str] = set()
    component_sizes: list[int] = []
    for node_id in node_ids:
        if node_id in visited:
            continue
        size = 0
        queue: deque[str] = deque([node_id])
        visited.add(node_id)
        while queue:
            current = queue.popleft()
            size += 1
            for neighbor in adjacency.get(current, set()):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        component_sizes.append(size)

    node_count = len(node_ids)
    largest_component_size = max(component_sizes, default=0)
    return {
        "node_count": node_count,
        "valid_edge_count": valid_edge_count,
        "isolated_node_count": isolated_node_count,
        "component_count": len(component_sizes),
        "largest_component_ratio": round(largest_component_size / node_count, 4) if node_count else 0.0,
        "leaf_node_count": leaf_count,
        "leaf_ratio": round(leaf_count / node_count, 4) if node_count else 0.0,
        "max_degree": max_degree,
        "hub_edge_share": round(max_degree / valid_edge_count, 4) if valid_edge_count else 0.0,
        "duplicate_edge_count": duplicate_edge_count,
        "edge_type_counts": edge_type_counts.most_common(12),
        "display_model": display_model,
    }


def _graph_quality_snapshot(graph: Mapping[str, Any], readiness: Mapping[str, Any], payload: Mapping[str, Any]) -> dict[str, Any]:
    thresholds = _graph_quality_thresholds(payload)
    labels_by_identity: dict[str, str] = {}
    node_count = 0
    for collection, rows in graph.items():
        if collection == "edges" or not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            node_count += 1
            identity = graph_node_identity(collection, row)
            label = _node_label(collection, row)
            if label and identity not in labels_by_identity:
                labels_by_identity[identity] = label
    labels = list(labels_by_identity.values())
    label_counts = Counter(labels)
    duplicate_labels = [
        {"label": label, "count": count}
        for label, count in sorted(label_counts.items(), key=lambda item: (-item[1], item[0]))
        if count > 1
    ][:20]
    raw_label_leaks = [
        label
        for label in sorted(set(labels))
        if any(marker in label.lower() for marker in RAW_LABEL_MARKERS) and not any("\u4e00" <= ch <= "\u9fff" for ch in label)
    ][:50]
    edge_count = len(graph.get("edges", []) or [])
    communities = len(readiness.get("visible_communities", []) or [])
    present_layers = len(readiness.get("present_layers", []) or [])
    failures: list[dict[str, Any]] = []
    if edge_count < thresholds.min_edges:
        failures.append({"check": "edge_density", "actual": edge_count, "expected_min": thresholds.min_edges})
    if communities < thresholds.min_communities:
        failures.append({"check": "community_count", "actual": communities, "expected_min": thresholds.min_communities})
    if present_layers < thresholds.min_layers:
        failures.append({"check": "layer_count", "actual": present_layers, "expected_min": thresholds.min_layers})
    if len(duplicate_labels) > thresholds.max_duplicate_labels:
        failures.append({"check": "duplicate_labels", "actual": len(duplicate_labels), "expected_max": thresholds.max_duplicate_labels})
    if len(raw_label_leaks) > thresholds.max_raw_label_leaks:
        failures.append({"check": "raw_label_leaks", "actual": len(raw_label_leaks), "expected_max": thresholds.max_raw_label_leaks})
    structure = _graph_structure_metrics(graph, display_model=True)
    raw_structure = _graph_structure_metrics(graph, display_model=False)
    if structure["duplicate_edge_count"] > thresholds.max_display_duplicate_edges:
        failures.append(
            {
                "check": "display_duplicate_edges",
                "actual": structure["duplicate_edge_count"],
                "expected_max": thresholds.max_display_duplicate_edges,
            }
        )
    if raw_structure["duplicate_edge_count"] > thresholds.max_duplicate_edges:
        failures.append({"check": "duplicate_edges", "actual": raw_structure["duplicate_edge_count"], "expected_max": thresholds.max_duplicate_edges})
    if structure["node_count"] >= thresholds.min_structural_nodes and structure["valid_edge_count"] >= thresholds.min_edges:
        if structure["hub_edge_share"] > thresholds.max_hub_edge_share:
            failures.append({"check": "hub_dominance", "actual": structure["hub_edge_share"], "expected_max": thresholds.max_hub_edge_share})
        if structure["leaf_ratio"] > thresholds.max_leaf_ratio:
            failures.append({"check": "leaf_ratio", "actual": structure["leaf_ratio"], "expected_max": thresholds.max_leaf_ratio})
        if structure["largest_component_ratio"] < thresholds.min_largest_component_ratio:
            failures.append({"check": "graph_fragmentation", "actual": structure["largest_component_ratio"], "expected_min": thresholds.min_largest_component_ratio})
    return {
        "status": "passed" if not failures else "needs_attention",
        "node_count": node_count,
        "edge_count": edge_count,
        "structure": structure,
        "raw_structure": raw_structure,
        "community_count": communities,
        "present_layer_count": present_layers,
        "duplicate_labels": duplicate_labels,
        "raw_label_leaks": raw_label_leaks,
        "failures": failures,
        "thresholds": thresholds.as_dict(),
    }


def _layer_gap_summary(items: list[Mapping[str, Any]]) -> dict[str, Any]:
    missing = Counter()
    thin = Counter()
    for item in items:
        readiness = item.get("readiness", {}) or {}
        for layer in readiness.get("missing_layers", []) or []:
            missing[str(layer)] += 1
        for layer in readiness.get("thin_layers", []) or []:
            thin[str(layer)] += 1
    return {
        "missing_layers": missing.most_common(),
        "thin_layers": thin.most_common(),
    }


def _enhancement_actions(target: knowledge_graph_bulk.BulkGraphTarget, readiness: Mapping[str, Any], payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    missing_layers = {str(item) for item in readiness.get("missing_layers", []) or []}
    thin_layers = {str(item) for item in readiness.get("thin_layers", []) or []}
    gap_layers = missing_layers | thin_layers
    symbol_payload = _symbols_payload(target.symbol, payload, execute=False)
    target_payload = {"issuer_id": target.issuer_id, "security_id": target.security_id, "symbol": target.symbol}
    actions: list[dict[str, Any]] = []
    for layer in graph_source_actions.LAYER_ACTION_SPECS:
        if layer not in gap_layers:
            continue
        action = graph_source_actions.layer_action(
            layer,
            target_payload,
            symbol_payload=symbol_payload,
            source_payload_style="symbol",
        )
        if action:
            actions.append(action)
    if {"company_event", "company_relationship"} & gap_layers:
        actions.append(graph_source_actions.candidate_review_action({"issuer_id": target.issuer_id, "security_id": target.security_id}))
    return actions


def _quality_remediation_actions(
    target: knowledge_graph_bulk.BulkGraphTarget,
    quality_gate: Mapping[str, Any],
    readiness: Mapping[str, Any],
    payload: Mapping[str, Any],
) -> list[dict[str, Any]]:
    failures = quality_gate.get("failures", []) or []
    checks = {str(item.get("check", "")) for item in failures if isinstance(item, Mapping)}
    target_payload = {"issuer_id": target.issuer_id, "security_id": target.security_id, "symbol": target.symbol}
    actions: list[dict[str, Any]] = []
    if checks & SOURCE_QUEUE_QUALITY_CHECKS:
        missing_layers = [str(item) for item in readiness.get("missing_layers", []) or []]
        thin_layers = [str(item) for item in readiness.get("thin_layers", []) or []]
        priority_layers = [layer for layer in graph_source_actions.SOURCE_BACKED_LAYERS if layer in set(missing_layers + thin_layers)]
        actions.append(
            {
                "action": "preview_graph_source_input_queue",
                "label": "预览来源输入队列，优先补齐让图谱变厚的真实数据层",
                "quality_checks": sorted(checks & SOURCE_QUEUE_QUALITY_CHECKS),
                "endpoint": "/api/graph/enrichment-runner",
                "method": "POST",
                "default_execute": False,
                "payload": {
                    "market": payload.get("market", "A,U"),
                    "issuer_ids": [target.issuer_id],
                    "limit": 1,
                    "batch_size": 1,
                    "priority_layers": ",".join(priority_layers or graph_source_actions.SOURCE_BACKED_LAYERS),
                    "quality_mode": "fast",
                    "include_events": False,
                    "include_relationships": False,
                    "execute": False,
                },
                "next_action": "先补来源层，再重跑展示质量检查。",
                "usage_boundary": QUALITY_REMEDIATION_USAGE_BOUNDARY,
            }
        )
    if checks & QUALITY_RECONCILE_CHECKS:
        actions.append(
            {
                "action": "preview_company_database_quality_reconcile",
                "label": "预览公司数据库质量归并，定位重复标签或重复事实边",
                "quality_checks": sorted(checks & QUALITY_RECONCILE_CHECKS),
                "endpoint": "/api/company-database/quality/reconcile",
                "method": "POST",
                "default_execute": False,
                "payload": {
                    "symbols": [target.symbol] if target.symbol else [],
                    "issuer_ids": [target.issuer_id],
                    "merge_duplicates": False,
                    "execute": False,
                },
                "next_action": "先 dry-run 审查重复项，人工确认后再执行归并。",
                "usage_boundary": QUALITY_REMEDIATION_USAGE_BOUNDARY,
            }
        )
    if "raw_label_leaks" in checks:
        actions.append(
            {
                "action": "inspect_graph_label_model",
                "label": "检查图谱标签模型，修正泄漏到可见文本的内部 ID",
                "quality_checks": ["raw_label_leaks"],
                "endpoint": "/api/graph/quality-center",
                "method": "POST",
                "default_execute": False,
                "payload": {
                    "issuer_ids": [target.issuer_id],
                    "limit": 1,
                    "batch_size": 1,
                    "max_raw_label_leaks": 0,
                    "execute": False,
                },
                "next_action": "定位 raw label 来源后修正展示标签或节点 identity 口径。",
                "usage_boundary": QUALITY_REMEDIATION_USAGE_BOUNDARY,
            }
        )
    return actions


def graph_quality_center(service: Any, payload: Mapping[str, Any] | None = None, *, actor: str = "system") -> dict[str, Any]:
    payload = payload or {}
    execute = _truthy(payload.get("execute", False))
    run_enrichment = _truthy(payload.get("run_enrichment", payload.get("enrich", False)))
    include_events = _truthy(payload.get("include_events", True))
    include_relationships = _truthy(payload.get("include_relationships", True))
    batch_size = max(1, min(100, int(payload.get("batch_size", payload.get("limit", 20)) or 20)))
    thresholds = _graph_quality_thresholds(payload)
    universe = knowledge_graph_bulk.select_full_graph_universe(service.store, payload)
    targets = [knowledge_graph_bulk.BulkGraphTarget(**item) for item in universe["targets"][:batch_size]]
    started_at = utcnow().isoformat()
    items: list[dict[str, Any]] = []
    enrichment_runs: list[dict[str, Any]] = []
    for target in targets:
        filters = {
            "issuer_id": target.issuer_id,
            "security_id": target.security_id,
            "min_layers": thresholds.min_layers,
            "min_edges": thresholds.min_edges,
            "min_communities": thresholds.min_communities,
        }
        graph = service.query_graph(filters)
        readiness = service.graph_knowledge_network_readiness(filters, actor=actor)
        quality = _graph_quality_snapshot(graph, readiness, payload)
        quality["remediation_actions"] = _quality_remediation_actions(target, quality, readiness, payload)
        actions = _enhancement_actions(target, readiness, payload)
        item = {
            "issuer_id": target.issuer_id,
            "security_id": target.security_id,
            "symbol": target.symbol,
            "market": target.market,
            "readiness": {
                "status": readiness.get("status"),
                "ready_for_obsidian_exploration": readiness.get("ready_for_obsidian_exploration"),
                "layer_counts": readiness.get("layer_counts", {}),
                "missing_layers": readiness.get("missing_layers", []),
                "thin_layers": readiness.get("thin_layers", []),
                "visible_communities": readiness.get("visible_communities", []),
                "cross_links": readiness.get("cross_links", {}),
                "seed_dependency": readiness.get("seed_dependency", {}),
            },
            "quality_gate": quality,
            "enhancement_actions": actions,
        }
        if run_enrichment:
            if include_events:
                event_result = service.build_company_events(_symbols_payload(target.symbol, payload, execute=execute), actor=actor)
                enrichment_runs.append({"symbol": target.symbol, "type": "events", "status": event_result.get("status"), "events_planned": event_result.get("events_planned"), "events_created": event_result.get("events_created")})
            if include_relationships:
                relationship_result = service.build_company_relationships(_symbols_payload(target.symbol, payload, execute=execute), actor=actor)
                enrichment_runs.append({"symbol": target.symbol, "type": "relationships", "status": relationship_result.get("status"), "relationships_planned": relationship_result.get("relationships_planned"), "relationships_created": relationship_result.get("relationships_created")})
        items.append(item)
    failing = [item for item in items if item["quality_gate"]["status"] != "passed" or item["readiness"]["status"] != "ready"]
    ready_count = sum(1 for item in items if item["readiness"]["status"] == "ready")
    passed_quality_count = sum(1 for item in items if item["quality_gate"]["status"] == "passed")
    no_targets = not items
    status = "no_targets" if no_targets else ("passed" if not failing else "needs_attention")
    global_failures = [{"check": "target_universe", "actual": 0, "expected_min": 1}] if no_targets else []
    return {
        "schema_id": "graph-quality-center-v1",
        "status": status,
        "started_at": started_at,
        "completed_at": utcnow().isoformat(),
        "execute": execute,
        "run_enrichment": run_enrichment,
        "universe": {key: value for key, value in universe.items() if key != "targets"},
        "processed_count": len(items),
        "ready_count": ready_count,
        "passed_quality_count": passed_quality_count,
        "needs_attention_count": len(failing) + len(global_failures),
        "global_failures": global_failures,
        "gap_summary": _layer_gap_summary(items),
        "items": items,
        "enrichment_runs": enrichment_runs,
        "next_recommended_actions": [
            "优先补 missing_layers 中排名最高的数据层，再重跑本脚本确认图谱质量门。",
            "候选事件/关系默认只进入 needs_review，人工审核通过后再提升为可信事实关系。",
            "浏览器级布局和点击验收继续使用 scripts/ui_graph_multi_symbol_acceptance.py 或本脚本的 --browser-matrix。",
        ],
        "automation_allowed": False,
        "live_execution_allowed": False,
        "usage_boundary": "graph_quality_center_uses_local_public_or_provided_data_only_no_broker_no_trade_execution",
    }
