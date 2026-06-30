from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Mapping


INDUSTRY_RELATIONSHIP_TYPES = {"industry_peer", "upstream_of", "downstream_of"}


@dataclass(frozen=True)
class IndustryRelationshipPlan:
    chain: Any
    focus_position: Any
    related_position: Any
    related_node_ids: list[str]
    edge_type: str
    from_id: str
    to_id: str
    relationship_type: str
    node_ids: list[str]
    confidence: float


@dataclass(frozen=True)
class InstitutionalHolderPlan:
    holding: Any
    holder_key: str
    related_holdings: list[Any]


def _node_ids(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {str(item).strip() for item in value if str(item).strip()}


def _direct_neighbor_nodes(chain: Any, focus_node_ids: set[str]) -> tuple[set[str], set[str]]:
    upstream_node_ids: set[str] = set()
    downstream_node_ids: set[str] = set()
    for edge in getattr(chain, "edges", []) or []:
        if not isinstance(edge, Mapping):
            continue
        source_node_id = str(edge.get("source_node_id", "") or "").strip()
        target_node_id = str(edge.get("target_node_id", "") or "").strip()
        if target_node_id in focus_node_ids and source_node_id:
            upstream_node_ids.add(source_node_id)
        if source_node_id in focus_node_ids and target_node_id:
            downstream_node_ids.add(target_node_id)
    return upstream_node_ids, downstream_node_ids


def _is_low_confidence_bulk_position(position: Any) -> bool:
    if str(getattr(position, "data_quality", "") or "").strip() != "needs_review":
        return False
    position_id = str(getattr(position, "position_id", "") or "")
    role = str(getattr(position, "role", "") or "")
    summary = str(getattr(position, "positioning_summary", "") or "")
    return (
        position_id.startswith("pos_full_graph_")
        or "production-universe" in summary
        or role in {"生产 universe 基础产业定位", "production universe basic industry position"}
    )


def plan_industry_relationship_edges(
    store: Any,
    issuer_id: str,
    *,
    relationship_type_filter: str = "",
    chain_id: str = "",
    chain_node_id: str = "",
    position_in_scope: Callable[[Any], bool] | None = None,
    include_low_confidence_related: bool = False,
) -> list[IndustryRelationshipPlan]:
    if relationship_type_filter and relationship_type_filter not in INDUSTRY_RELATIONSHIP_TYPES:
        return []
    position_in_scope = position_in_scope or (lambda _position: True)
    plans: list[IndustryRelationshipPlan] = []
    focus_positions = [
        position
        for position in getattr(store, "company_positions", {}).values()
        if position.issuer_id == issuer_id and position.chain_id and position.node_ids and position_in_scope(position)
    ]
    for focus_position in focus_positions:
        if chain_id and focus_position.chain_id != chain_id:
            continue
        chain = getattr(store, "industry_chains", {}).get(focus_position.chain_id)
        if chain is None:
            continue
        focus_node_ids = _node_ids(focus_position.node_ids)
        if not focus_node_ids:
            continue
        upstream_node_ids, downstream_node_ids = _direct_neighbor_nodes(chain, focus_node_ids)
        for related_position in getattr(store, "company_positions", {}).values():
            if related_position.chain_id != focus_position.chain_id or related_position.position_id == focus_position.position_id:
                continue
            if related_position.issuer_id == issuer_id:
                continue
            if not include_low_confidence_related and _is_low_confidence_bulk_position(related_position):
                continue
            related_node_ids = _node_ids(related_position.node_ids)
            if not related_node_ids:
                continue
            shared_nodes = focus_node_ids & related_node_ids
            if chain_node_id and relationship_type_filter == "industry_peer":
                shared_nodes &= {chain_node_id}
            if shared_nodes and (not relationship_type_filter or relationship_type_filter == "industry_peer"):
                plans.append(
                    IndustryRelationshipPlan(
                        chain=chain,
                        focus_position=focus_position,
                        related_position=related_position,
                        related_node_ids=sorted(related_node_ids),
                        edge_type="INDUSTRY_PEER",
                        from_id=issuer_id,
                        to_id=related_position.issuer_id,
                        relationship_type="industry_peer",
                        node_ids=sorted(shared_nodes),
                        confidence=0.75,
                    )
                )
            upstream_nodes = related_node_ids & upstream_node_ids
            if chain_node_id and relationship_type_filter == "upstream_of":
                upstream_nodes &= {chain_node_id}
            if upstream_nodes and (not relationship_type_filter or relationship_type_filter == "upstream_of"):
                plans.append(
                    IndustryRelationshipPlan(
                        chain=chain,
                        focus_position=focus_position,
                        related_position=related_position,
                        related_node_ids=sorted(related_node_ids),
                        edge_type="INDUSTRY_UPSTREAM_OF",
                        from_id=related_position.issuer_id,
                        to_id=issuer_id,
                        relationship_type="upstream_of",
                        node_ids=sorted(upstream_nodes),
                        confidence=0.72,
                    )
                )
            downstream_nodes = related_node_ids & downstream_node_ids
            if chain_node_id and relationship_type_filter == "downstream_of":
                downstream_nodes &= {chain_node_id}
            if downstream_nodes and (not relationship_type_filter or relationship_type_filter == "downstream_of"):
                plans.append(
                    IndustryRelationshipPlan(
                        chain=chain,
                        focus_position=focus_position,
                        related_position=related_position,
                        related_node_ids=sorted(related_node_ids),
                        edge_type="INDUSTRY_DOWNSTREAM_OF",
                        from_id=issuer_id,
                        to_id=related_position.issuer_id,
                        relationship_type="downstream_of",
                        node_ids=sorted(downstream_nodes),
                        confidence=0.72,
                    )
                )
    return plans


def plan_institutional_holder_edges(
    store: Any,
    issuer_id: str,
    *,
    holder_key_filter: str = "",
    holding_key: Callable[[Any], str],
    security_in_scope: Callable[[str], bool] | None = None,
) -> list[InstitutionalHolderPlan]:
    holder_key_filter = str(holder_key_filter or "").strip().upper()
    security_in_scope = security_in_scope or (lambda _security_id: True)
    plans: list[InstitutionalHolderPlan] = []
    holdings = list(getattr(store, "institutional_holdings", {}).values())
    for holding in holdings:
        holder_key = str(holding_key(holding) or "").strip().upper()
        if holding.issuer_id != issuer_id and (not holder_key_filter or holder_key != holder_key_filter):
            continue
        if not security_in_scope(holding.security_id):
            continue
        related_holdings = []
        if holder_key:
            related_holdings = [
                related_holding
                for related_holding in holdings
                if related_holding.holding_id != holding.holding_id and str(holding_key(related_holding) or "").strip().upper() == holder_key
            ]
        plans.append(InstitutionalHolderPlan(holding=holding, holder_key=holder_key, related_holdings=related_holdings))
    return plans


def plan_ownership_holder_relationships(
    store: Any,
    issuer_id: str,
    *,
    holder_key_filter: str = "",
    relationship_type_filter: str = "",
    security_in_scope: Callable[[str], bool] | None = None,
    holder_key: Callable[[Any], str],
    relationship_bucket: Callable[[str], str],
) -> list[Any]:
    holder_key_filter = str(holder_key_filter or "").strip().lower()
    security_in_scope = security_in_scope or (lambda _security_id: True)
    relationships = []
    for relationship in getattr(store, "company_relationships", {}).values():
        relationship_in_focus = (
            relationship.issuer_id == issuer_id
            or relationship.subject_id == issuer_id
            or relationship.object_id == issuer_id
        )
        if not holder_key_filter and not relationship_in_focus:
            continue
        if holder_key_filter:
            if str(holder_key(relationship) or "").strip().lower() != holder_key_filter:
                continue
            relationship_type = str(relationship.relationship_type or "")
            if relationship_type.endswith("_candidate"):
                continue
            if relationship_bucket(relationship_type) != "ownership":
                continue
            if relationship.relationship_status != "active" or relationship.review_status not in {"approved", "auto_generated", "reviewed"}:
                continue
        if relationship.security_id and not security_in_scope(relationship.security_id):
            continue
        if relationship_type_filter and relationship.relationship_type != relationship_type_filter:
            continue
        relationships.append(relationship)
    return relationships
