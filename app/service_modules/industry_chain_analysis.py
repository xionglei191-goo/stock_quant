"""Pure industry-chain panorama helpers (research/AI workflows domain).

Extracted from ``SystemService`` per the SystemService Modularization ADR.
These are deterministic functions of their arguments only (readiness coverage
scoring, stage bucketing/ordering, node relation shaping). They hold no
``SystemService`` state; ``SystemService`` keeps the same method names as thin
facades that delegate here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Mapping

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..models import IndustryChain


def readiness_coverage(counters: Mapping[str, Any]) -> dict[str, Any]:
    node_count = max(1, int(counters.get("node_count", 0) or 0))
    position_count = max(1, int(counters.get("company_node_position_count", 0) or 0))
    process_coverage = int(counters.get("process_ready_nodes", 0) or 0) / node_count
    flow_coverage = int(counters.get("flow_ready_nodes", 0) or 0) / node_count
    evidence_coverage = int(counters.get("official_evidence_ready_nodes", 0) or 0) / node_count
    economics_coverage = int(counters.get("economic_pool_ready_nodes", 0) or 0) / node_count
    company_mapping_coverage = int(counters.get("company_mapped_nodes", 0) or 0) / node_count
    attribution_coverage = int(counters.get("company_attribution_ready_positions", 0) or 0) / position_count
    readiness_score = (
        0.25 * process_coverage
        + 0.15 * flow_coverage
        + 0.2 * evidence_coverage
        + 0.15 * economics_coverage
        + 0.1 * company_mapping_coverage
        + 0.15 * attribution_coverage
    )
    return {
        "process_coverage": round(process_coverage, 4),
        "flow_coverage": round(flow_coverage, 4),
        "official_evidence_coverage": round(evidence_coverage, 4),
        "economic_pool_coverage": round(economics_coverage, 4),
        "company_mapping_coverage": round(company_mapping_coverage, 4),
        "company_attribution_coverage": round(attribution_coverage, 4),
        "readiness_score": round(readiness_score, 4),
    }


def stage_bucket(buckets: dict[str, dict[str, Any]], stage: str) -> dict[str, Any]:
    normalized = stage or "unknown"
    return buckets.setdefault(
        normalized,
        {
            "process_stage": normalized,
            "node_count": 0,
            "company_count": 0,
            "revenue_pool": 0.0,
            "profit_pool": 0.0,
            "mapped_revenue": 0.0,
            "mapped_profit": 0.0,
            "process_steps": [],
            "segments": [],
        },
    )


def stage_order(stage: str) -> int:
    return {
        "upstream": 10,
        "midstream": 20,
        "downstream": 30,
        "supporting": 40,
        "adjacent": 50,
        "unknown": 99,
    }.get(stage, 80)


def node_relations(chain: "IndustryChain") -> dict[str, dict[str, list[dict[str, Any]]]]:
    relations: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for edge in chain.edges:
        source_node_id = str(edge.get("source_node_id", "")).strip()
        target_node_id = str(edge.get("target_node_id", "")).strip()
        if source_node_id:
            relations.setdefault(source_node_id, {"upstream": [], "downstream": []})["downstream"].append(dict(edge))
        if target_node_id:
            relations.setdefault(target_node_id, {"upstream": [], "downstream": []})["upstream"].append(dict(edge))
    return relations
