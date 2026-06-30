from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any, Mapping

from app.models import CompanyPosition, CompanyRelationship, IndustryChain, Security
from app.utils import to_plain, utcnow


PRODUCTION_MARKETS = {"A", "U", "H", "HK"}
DEFAULT_CHAIN_BY_MARKET = {
    "A": ("chain_ashare_full_knowledge_graph", "A 股综合产业图谱"),
    "U": ("chain_us_full_knowledge_graph", "美股综合产业图谱"),
    "H": ("chain_hk_full_knowledge_graph", "港股综合产业图谱"),
    "HK": ("chain_hk_full_knowledge_graph", "港股综合产业图谱"),
}


@dataclass(slots=True)
class BulkGraphTarget:
    issuer_id: str
    security_id: str
    symbol: str
    market: str
    exchange: str = ""
    industry: str = ""
    sector: str = ""


def _split_markets(value: Any) -> set[str]:
    if isinstance(value, str):
        raw = value.split(",")
    elif isinstance(value, (list, tuple, set)):
        raw = list(value)
    else:
        raw = []
    markets = {str(item).strip().upper() for item in raw if str(item).strip()}
    return markets or {"A", "U"}


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "execute"}


def _safe_part(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in str(value or "")).strip("_") or "unknown"


def _security_in_scope(security: Security, markets: set[str]) -> bool:
    market = str(security.market or "").upper()
    if market not in markets:
        return False
    if str(security.status or "active") != "active":
        return False
    scope = str(security.company_universe_scope or "").strip()
    if scope:
        return scope == "in_scope"
    if market in {"H", "HK"}:
        return False
    security_type = str(security.security_type or "").lower()
    return security_type in {"", "common_stock", "common", "stock", "equity"}


def select_full_graph_universe(store: Any, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    markets = _split_markets(payload.get("market", payload.get("markets", "A,U")))
    limit = max(0, int(payload.get("limit", 0) or 0))
    issuer_filter = {str(item).strip() for item in payload.get("issuer_ids", []) if str(item).strip()}
    security_filter = {str(item).strip() for item in payload.get("security_ids", []) if str(item).strip()}
    raw_symbols = payload.get("symbols", payload.get("symbol", []))
    if isinstance(raw_symbols, str):
        raw_symbols = raw_symbols.split(",")
    symbol_filter = {str(item).strip().upper() for item in raw_symbols if str(item).strip()} if isinstance(raw_symbols, (list, tuple, set)) else set()
    targets: list[BulkGraphTarget] = []
    skipped_by_market: Counter[str] = Counter()
    hk_available = False
    seen_issuers: set[str] = set()
    for security in sorted(store.securities.values(), key=lambda item: (str(item.market), str(item.ticker).upper(), str(item.security_id))):
        market = str(security.market or "").upper()
        if market in {"H", "HK"}:
            hk_available = True
        if issuer_filter and security.issuer_id not in issuer_filter:
            skipped_by_market[f"{market}:issuer_filter"] += 1
            continue
        if security_filter and security.security_id not in security_filter:
            skipped_by_market[f"{market}:security_filter"] += 1
            continue
        if symbol_filter and str(security.ticker or "").upper() not in symbol_filter:
            skipped_by_market[f"{market}:symbol_filter"] += 1
            continue
        if not _security_in_scope(security, markets):
            skipped_by_market[market or "unknown"] += 1
            continue
        if security.issuer_id in seen_issuers:
            skipped_by_market[f"{market}:duplicate_issuer"] += 1
            continue
        issuer = store.issuers.get(security.issuer_id)
        if issuer is None or str(getattr(issuer, "status", "active")) != "active":
            skipped_by_market[f"{market}:missing_issuer"] += 1
            continue
        targets.append(
            BulkGraphTarget(
                issuer_id=security.issuer_id,
                security_id=security.security_id,
                symbol=security.ticker,
                market=market,
                exchange=security.exchange,
                industry=security.industry or getattr(issuer, "industry", ""),
                sector=security.sector or getattr(issuer, "sector", ""),
            )
        )
        seen_issuers.add(security.issuer_id)
        if limit and len(targets) >= limit:
            break
    return {
        "schema_id": "full-knowledge-graph-universe-v1",
        "markets": sorted(markets),
        "target_count": len(targets),
        "targets": [asdict(target) for target in targets],
        "skipped_by_market": dict(skipped_by_market),
        "hk_universe_missing": ("H" in markets or "HK" in markets) and not hk_available,
        "usage_boundary": "current_production_universe_only_excludes_historical_delisted_and_non_company_directory_records",
    }


def _relationship_id_for(target: BulkGraphTarget) -> str:
    return f"rel_full_graph_listing_{_safe_part(target.security_id)}"


def _position_id_for(target: BulkGraphTarget) -> str:
    return f"pos_full_graph_{_safe_part(target.security_id)}"


def _chain_spec_for(target: BulkGraphTarget) -> tuple[str, str]:
    return DEFAULT_CHAIN_BY_MARKET.get(target.market, DEFAULT_CHAIN_BY_MARKET["A"])


def _position_node_for(target: BulkGraphTarget) -> tuple[str, str]:
    source = target.industry or target.sector
    if source:
        label = str(source).strip()
        return f"{_safe_part(target.market)}_{_safe_part(label)}", label
    label = f"{target.symbol} 待复核产业定位" if target.market in {"A", "H", "HK"} else f"{target.symbol} needs-review industry position"
    return f"{_safe_part(target.market)}_{_safe_part(target.symbol)}_needs_review", label


def _ensure_chain(store: Any, target: BulkGraphTarget, *, execute: bool) -> tuple[str, list[str], list[dict[str, Any]]]:
    chain_id, chain_name = _chain_spec_for(target)
    actions: list[dict[str, Any]] = []
    node_id, node_name = _position_node_for(target)
    if chain_id not in store.industry_chains:
        actions.append({"action": "create_industry_chain", "chain_id": chain_id, "name": chain_name})
        if execute:
            store.industry_chains[chain_id] = IndustryChain(
                chain_id=chain_id,
                name=chain_name,
                nodes=[{"node_id": node_id, "name": node_name, "level": 1, "category": "bulk_graph_needs_review"}],
                edges=[],
                taxonomy_version="full-knowledge-graph-bulk-v1",
                source_refs=["local://full-knowledge-graph/bulk"],
            )
    else:
        chain = store.industry_chains[chain_id]
        existing_node_ids = {str(node.get("node_id", "")).strip() for node in chain.nodes}
        if node_id not in existing_node_ids:
            actions.append({"action": "append_industry_chain_node", "chain_id": chain_id, "node_id": node_id, "name": node_name})
            if execute:
                chain.nodes.append({"node_id": node_id, "name": node_name, "level": 1, "category": "bulk_graph_needs_review"})
    return chain_id, [node_id], actions


def _layer_counts(service: Any, target: BulkGraphTarget) -> dict[str, int]:
    store = service.store
    document_ids = {
        item.document_id
        for item in store.documents.values()
        if item.issuer_id == target.issuer_id and (not item.security_id or item.security_id == target.security_id)
    }
    research_report_ids = {
        item.research_report_id
        for item in store.structured_research_reports.values()
        if item.issuer_id == target.issuer_id and (not item.security_id or item.security_id == target.security_id)
    }
    return {
        "listed_security": sum(
            1
            for item in store.company_relationships.values()
            if item.relationship_type == "listed_security"
            and item.issuer_id == target.issuer_id
            and (not item.security_id or item.security_id == target.security_id)
        ),
        "industry_position": sum(
            1
            for item in store.company_positions.values()
            if item.issuer_id == target.issuer_id and (not item.security_id or item.security_id == target.security_id)
        ),
        "shareholder_holding": sum(1 for item in store.institutional_holdings.values() if item.issuer_id == target.issuer_id and item.security_id == target.security_id),
        "document": len(document_ids),
        "evidence": sum(1 for item in store.evidence.values() if item.document_id in document_ids),
        "company_event": sum(
            1
            for item in store.company_events.values()
            if item.issuer_id == target.issuer_id and (not item.security_id or item.security_id == target.security_id)
        ),
        "research_report": len(research_report_ids),
        "viewpoint": sum(
            1
            for item in store.report_viewpoints.values()
            if (item.issuer_id == target.issuer_id or item.research_report_id in research_report_ids)
            and (not item.security_id or item.security_id == target.security_id)
        ),
        "edge": 0,
    }


def _readiness_from_counts(counts: Mapping[str, int]) -> dict[str, Any]:
    requirements = {
        "listed_security": 1,
        "industry_position": 1,
        "shareholder_holding": 1,
        "document": 1,
        "evidence": 1,
        "company_event": 1,
        "research_report": 1,
        "viewpoint": 1,
    }
    present_layers = [layer for layer, minimum in requirements.items() if int(counts.get(layer, 0) or 0) >= minimum]
    missing_layers = [layer for layer, minimum in requirements.items() if int(counts.get(layer, 0) or 0) < minimum]
    ready = not missing_layers
    return {
        "status": "ready" if ready else "needs_data",
        "ready_for_obsidian_exploration": ready,
        "present_layers": present_layers,
        "missing_layers": missing_layers,
        "weak_layers": [],
        "edge_count": int(counts.get("edge", 0) or 0),
    }


def process_full_graph_target(service: Any, target: BulkGraphTarget, *, execute: bool, actor: str, include_evidence_links: bool = False) -> dict[str, Any]:
    actions: list[dict[str, Any]] = []
    errors: list[str] = []
    before = _layer_counts(service, target)
    relationship_id = _relationship_id_for(target)
    if relationship_id not in service.store.company_relationships:
        action = {"action": "create_listed_security_relationship", "relationship_id": relationship_id}
        actions.append(action)
        if execute:
            service.store.company_relationships[relationship_id] = CompanyRelationship(
                relationship_id=relationship_id,
                issuer_id=target.issuer_id,
                security_id=target.security_id,
                subject_type="company",
                subject_id=target.issuer_id,
                object_type="security",
                object_id=target.security_id,
                relationship_type="listed_security",
                confidence=0.95,
                relationship_status="active",
                review_status="auto_generated",
                metadata={"source_layer": "full_knowledge_graph_bulk", "symbol": target.symbol, "market": target.market},
            )
    position_id = _position_id_for(target)
    existing_positions = [
        item
        for item in service.store.company_positions.values()
        if item.issuer_id == target.issuer_id and (not item.security_id or item.security_id == target.security_id)
    ]
    chain_id, node_ids, chain_actions = _ensure_chain(service.store, target, execute=execute)
    actions.extend(chain_actions)
    if not existing_positions:
        actions.append({"action": "create_company_position", "position_id": position_id, "chain_id": chain_id, "node_ids": node_ids})
        if execute:
            service.store.company_positions[position_id] = CompanyPosition(
                position_id=position_id,
                issuer_id=target.issuer_id,
                security_id=target.security_id,
                chain_id=chain_id,
                node_ids=node_ids,
                role=target.industry or target.sector or "生产 universe 基础产业定位",
                positioning_summary=f"{target.symbol} production-universe graph position generated from security industry metadata.",
                revenue_exposure={"industry": target.industry, "sector": target.sector, "source": "security_metadata"},
                technology_tags=[item for item in [target.industry, target.sector] if item],
                data_quality="needs_review",
            )
    else:
        managed_position = service.store.company_positions.get(position_id)
        if managed_position is not None and (managed_position.chain_id != chain_id or list(managed_position.node_ids) != node_ids):
            actions.append({"action": "repair_company_position_scope", "position_id": position_id, "chain_id": chain_id, "node_ids": node_ids})
            if execute:
                managed_position.chain_id = chain_id
                managed_position.node_ids = node_ids
                managed_position.data_quality = managed_position.data_quality or "needs_review"
    if include_evidence_links:
        link_result = service.backfill_knowledge_network_evidence_links({"issuer_id": target.issuer_id, "security_id": target.security_id, "limit": 100, "execute": execute}, actor=actor)
        if link_result.get("planned_count"):
            actions.append({"action": "backfill_evidence_links", "planned_count": link_result.get("planned_count", 0), "updated_count": link_result.get("updated_count", 0)})
    if execute:
        marker = getattr(service.store, "mark_dirty_for_resource", None)
        if callable(marker):
            for resource_type in ["company_relationship", "company_position", "industry_chain"]:
                marker(resource_type)
    after = _layer_counts(service, target)
    readiness = _readiness_from_counts(after)
    status = "ready" if readiness.get("ready_for_obsidian_exploration") else "needs_data"
    return {
        "issuer_id": target.issuer_id,
        "security_id": target.security_id,
        "symbol": target.symbol,
        "market": target.market,
        "status": "failed_with_reason" if errors else status,
        "layers_before": before,
        "layers_after": after,
        "actions": actions,
        "errors": errors,
        "readiness": {
            "status": readiness.get("status"),
            "ready_for_obsidian_exploration": bool(readiness.get("ready_for_obsidian_exploration")),
            "present_layers": readiness.get("present_layers", []),
            "missing_layers": readiness.get("missing_layers", []),
            "weak_layers": readiness.get("weak_layers", []),
            "edge_count": readiness.get("edge_count", 0),
        },
    }


def backfill_full_knowledge_graph(service: Any, payload: Mapping[str, Any] | None = None, *, actor: str = "system") -> dict[str, Any]:
    payload = payload or {}
    execute = _truthy(payload.get("execute", False))
    audit_only = _truthy(payload.get("audit_only", False))
    include_evidence_links = _truthy(payload.get("include_evidence_links", False))
    batch_size = max(1, min(500, int(payload.get("batch_size", 50) or 50)))
    universe = select_full_graph_universe(service.store, payload)
    all_targets = [BulkGraphTarget(**item) for item in universe["targets"]]
    skip_issuer_ids = {str(item) for item in payload.get("skip_issuer_ids", []) if str(item)}
    targets = [target for target in all_targets if target.issuer_id not in skip_issuer_ids]
    started_at = utcnow().isoformat()
    items: list[dict[str, Any]] = []
    failed_items: list[dict[str, Any]] = []
    if not audit_only:
        for target in targets[:batch_size]:
            try:
                row = process_full_graph_target(service, target, execute=execute, actor=actor, include_evidence_links=include_evidence_links)
            except Exception as exc:  # noqa: BLE001 - batch should continue and record failure
                row = {
                    "issuer_id": target.issuer_id,
                    "security_id": target.security_id,
                    "symbol": target.symbol,
                    "market": target.market,
                    "status": "failed_with_reason",
                    "layers_before": {},
                    "layers_after": {},
                    "actions": [],
                    "errors": [str(exc)],
                    "readiness": {},
                }
            items.append(row)
            if row["status"] == "failed_with_reason":
                failed_items.append(row)
        if execute:
            service.store.commit()
    else:
        for target in targets[:batch_size]:
            before = _layer_counts(service, target)
            items.append(
                {
                    "issuer_id": target.issuer_id,
                    "security_id": target.security_id,
                    "symbol": target.symbol,
                    "market": target.market,
                    "status": "audit_only",
                    "layers_before": before,
                    "layers_after": before,
                    "actions": [],
                    "errors": [],
                    "readiness": {},
                }
            )
    layer_coverage: dict[str, int] = {}
    missing_counter: Counter[str] = Counter()
    ready_count = 0
    needs_data_count = 0
    for item in items:
        after = item.get("layers_after", {}) or {}
        for layer, count in after.items():
            if layer == "edge":
                continue
            if int(count or 0) > 0:
                layer_coverage[layer] = layer_coverage.get(layer, 0) + 1
            else:
                missing_counter[layer] += 1
        if item.get("status") == "ready":
            ready_count += 1
        elif item.get("status") == "needs_data":
            needs_data_count += 1
    processed_count = len(items)
    return {
        "schema_id": "full-knowledge-graph-backfill-v1",
        "status": "audit_only" if audit_only else ("executed" if execute else "dry_run"),
        "execute": execute,
        "audit_only": audit_only,
        "include_evidence_links": include_evidence_links,
        "started_at": started_at,
        "completed_at": utcnow().isoformat(),
        "universe": {key: value for key, value in universe.items() if key != "targets"},
        "universe_count": universe["target_count"],
        "resume_skipped_count": max(0, len(all_targets) - len(targets)),
        "processed_count": processed_count,
        "ready_count": ready_count,
        "needs_data_count": needs_data_count,
        "failed_count": len(failed_items),
        "batch_size": batch_size,
        "layer_coverage": layer_coverage,
        "top_missing_layers": missing_counter.most_common(10),
        "items": items,
        "failed_items": failed_items,
        "automation_allowed": False,
        "live_execution_allowed": False,
        "usage_boundary": "full_knowledge_graph_backfill_local_research_data_only_no_broker_no_trade_execution",
    }
