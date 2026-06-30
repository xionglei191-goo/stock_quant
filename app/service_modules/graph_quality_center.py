from __future__ import annotations

from collections import Counter
import re
from typing import Any, Mapping

from app.utils import to_plain, utcnow

from . import knowledge_graph_bulk
from .graph_intelligence import graph_node_identity


RAW_LABEL_MARKERS = ("obsidian", "relationship", "pos_", "doc_", "hold_", "issuer_", "security_", "sec_", "md_")


def _status_label(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text.replace("_", " ").replace("-", " ").strip().title()


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
        ticker = str(row.get("ticker") or row.get("symbol") or "").strip()
        if ticker:
            return f"{ticker.upper()} · 公司"
    if collection == "securities":
        ticker = str(row.get("ticker") or row.get("symbol") or "").strip()
        if ticker:
            market = str(row.get("market") or row.get("exchange") or "证券").strip()
            return f"{ticker.upper()} · {market}"
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


def _graph_quality_snapshot(graph: Mapping[str, Any], readiness: Mapping[str, Any], payload: Mapping[str, Any]) -> dict[str, Any]:
    max_duplicate_labels = int(payload.get("max_duplicate_labels", 4) or 4)
    max_raw_label_leaks = int(payload.get("max_raw_label_leaks", 8) or 8)
    min_edges = int(payload.get("min_edges", 12) or 12)
    min_communities = int(payload.get("min_communities", 3) or 3)
    min_layers = int(payload.get("min_layers", 5) or 5)
    labels: list[str] = []
    node_count = 0
    for collection, rows in graph.items():
        if collection == "edges" or not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            node_count += 1
            label = _node_label(collection, row)
            if label:
                labels.append(label)
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
    if edge_count < min_edges:
        failures.append({"check": "edge_density", "actual": edge_count, "expected_min": min_edges})
    if communities < min_communities:
        failures.append({"check": "community_count", "actual": communities, "expected_min": min_communities})
    if present_layers < min_layers:
        failures.append({"check": "layer_count", "actual": present_layers, "expected_min": min_layers})
    if len(duplicate_labels) > max_duplicate_labels:
        failures.append({"check": "duplicate_labels", "actual": len(duplicate_labels), "expected_max": max_duplicate_labels})
    if len(raw_label_leaks) > max_raw_label_leaks:
        failures.append({"check": "raw_label_leaks", "actual": len(raw_label_leaks), "expected_max": max_raw_label_leaks})
    return {
        "status": "passed" if not failures else "needs_attention",
        "node_count": node_count,
        "edge_count": edge_count,
        "community_count": communities,
        "present_layer_count": present_layers,
        "duplicate_labels": duplicate_labels,
        "raw_label_leaks": raw_label_leaks,
        "failures": failures,
        "thresholds": {
            "min_edges": min_edges,
            "min_communities": min_communities,
            "min_layers": min_layers,
            "max_duplicate_labels": max_duplicate_labels,
            "max_raw_label_leaks": max_raw_label_leaks,
        },
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


def graph_quality_center(service: Any, payload: Mapping[str, Any] | None = None, *, actor: str = "system") -> dict[str, Any]:
    payload = payload or {}
    execute = _truthy(payload.get("execute", False))
    run_enrichment = _truthy(payload.get("run_enrichment", payload.get("enrich", False)))
    include_events = _truthy(payload.get("include_events", True))
    include_relationships = _truthy(payload.get("include_relationships", True))
    batch_size = max(1, min(100, int(payload.get("batch_size", payload.get("limit", 20)) or 20)))
    universe = knowledge_graph_bulk.select_full_graph_universe(service.store, payload)
    targets = [knowledge_graph_bulk.BulkGraphTarget(**item) for item in universe["targets"][:batch_size]]
    started_at = utcnow().isoformat()
    items: list[dict[str, Any]] = []
    enrichment_runs: list[dict[str, Any]] = []
    for target in targets:
        filters = {
            "issuer_id": target.issuer_id,
            "security_id": target.security_id,
            "min_layers": payload.get("min_layers", 5),
            "min_edges": payload.get("min_edges", 12),
            "min_communities": payload.get("min_communities", 3),
        }
        graph = service.query_graph(filters)
        readiness = service.graph_knowledge_network_readiness(filters, actor=actor)
        quality = _graph_quality_snapshot(graph, readiness, payload)
        actions = [
            {
                "action": "build_company_events",
                "label": "从本地行情、披露和已绑定研报构建公司事件",
                "endpoint": "/api/company-database/events/build",
                "execute_required": True,
                "payload": _symbols_payload(target.symbol, payload, execute=False),
            },
            {
                "action": "build_company_relationships",
                "label": "从上市证券、研报覆盖、披露和股权表构建关系候选",
                "endpoint": "/api/company-database/relationships/build",
                "execute_required": True,
                "payload": _symbols_payload(target.symbol, payload, execute=False),
            },
            {
                "action": "review_relationship_and_event_candidates",
                "label": "审核候选事件和关系后再提升为可信图谱事实",
                "endpoint": "/api/company-database/events/review and /api/company-database/relationships/review",
                "execute_required": False,
                "payload": {"issuer_id": target.issuer_id, "security_id": target.security_id},
            },
        ]
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
