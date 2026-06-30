from __future__ import annotations

from collections import Counter
from typing import Any, Mapping

from app.utils import utcnow

from . import graph_quality_center, knowledge_graph_bulk


PRIORITY_LAYERS = ["company_event", "company_relationship", "document", "evidence", "shareholder_holding", "research_report", "viewpoint"]


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "execute"}


def _safe_int(value: Any, default: int, *, minimum: int = 0, maximum: int = 10_000) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _symbols_payload(target: knowledge_graph_bulk.BulkGraphTarget, payload: Mapping[str, Any], *, execute: bool) -> dict[str, Any]:
    result: dict[str, Any] = {
        "symbols": [target.symbol],
        "issuer_ids": [target.issuer_id],
        "limit": 1,
        "execute": execute,
    }
    for key in [
        "event_limit",
        "relationship_limit",
        "include_market_data",
        "include_research_coverage",
        "include_disclosures",
        "include_structured_disclosures",
        "include_listings",
        "include_institution_coverage",
        "include_disclosure_candidates",
        "include_structured_ownership",
    ]:
        if key in payload:
            result[key] = payload[key]
    return result


def _needs_enrichment(readiness: Mapping[str, Any], layers: set[str]) -> bool:
    missing = set(str(item) for item in readiness.get("missing_layers", []) or [])
    thin = set(str(item) for item in readiness.get("thin_layers", []) or [])
    if not layers:
        return bool(missing or thin)
    return bool((missing | thin) & layers)


def _action_summary(item: Mapping[str, Any]) -> dict[str, Any]:
    readiness = item.get("readiness", {}) or {}
    return {
        "missing_layers": list(readiness.get("missing_layers", []) or []),
        "thin_layers": list(readiness.get("thin_layers", []) or []),
        "cross_links": dict(readiness.get("cross_links", {}) or {}),
        "quality_status": (item.get("quality_gate", {}) or {}).get("status", ""),
    }


def graph_enrichment_runner(service: Any, payload: Mapping[str, Any] | None = None, *, actor: str = "system") -> dict[str, Any]:
    payload = payload or {}
    execute = _truthy(payload.get("execute", False))
    audit_only = _truthy(payload.get("audit_only", False))
    include_events = _truthy(payload.get("include_events", True))
    include_relationships = _truthy(payload.get("include_relationships", True))
    limit = _safe_int(payload.get("limit", 50), 50, minimum=1, maximum=1000)
    batch_size = _safe_int(payload.get("batch_size", limit), limit, minimum=1, maximum=200)
    raw_layers = payload.get("priority_layers", payload.get("layers", PRIORITY_LAYERS))
    if isinstance(raw_layers, str):
        priority_layers = {item.strip() for item in raw_layers.split(",") if item.strip()}
    elif isinstance(raw_layers, (list, tuple, set)):
        priority_layers = {str(item).strip() for item in raw_layers if str(item).strip()}
    else:
        priority_layers = set(PRIORITY_LAYERS)
    started_at = utcnow().isoformat()
    universe = knowledge_graph_bulk.select_full_graph_universe(service.store, {**payload, "limit": limit})
    targets = [knowledge_graph_bulk.BulkGraphTarget(**item) for item in universe["targets"]]
    items: list[dict[str, Any]] = []
    skipped_items: list[dict[str, Any]] = []
    failed_items: list[dict[str, Any]] = []
    event_totals = Counter()
    relationship_totals = Counter()
    missing_counter = Counter()
    selected = 0
    for target in targets:
        quality_before = service.graph_quality_center(
            {
                **payload,
                "market": target.market,
                "limit": 1,
                "batch_size": 1,
                "issuer_ids": [target.issuer_id],
                "run_enrichment": False,
            },
            actor=actor,
        )
        before_item = (quality_before.get("items") or [{}])[0]
        before_summary = _action_summary(before_item)
        for layer in before_summary["missing_layers"]:
            missing_counter[layer] += 1
        if not _needs_enrichment(before_item.get("readiness", {}) or {}, priority_layers):
            skipped_items.append(
                {
                    "issuer_id": target.issuer_id,
                    "security_id": target.security_id,
                    "symbol": target.symbol,
                    "market": target.market,
                    "reason": "no_priority_layer_gap",
                    "before": before_summary,
                }
            )
            continue
        if selected >= batch_size:
            skipped_items.append(
                {
                    "issuer_id": target.issuer_id,
                    "security_id": target.security_id,
                    "symbol": target.symbol,
                    "market": target.market,
                    "reason": "batch_size_reached",
                    "before": before_summary,
                }
            )
            continue
        selected += 1
        row: dict[str, Any] = {
            "issuer_id": target.issuer_id,
            "security_id": target.security_id,
            "symbol": target.symbol,
            "market": target.market,
            "status": "audit_only" if audit_only else ("executed" if execute else "dry_run"),
            "before": before_summary,
            "event_result": {},
            "relationship_result": {},
            "after": {},
            "errors": [],
        }
        try:
            if not audit_only and include_events:
                event_result = service.build_company_events(_symbols_payload(target, payload, execute=execute), actor=actor)
                row["event_result"] = {
                    "status": event_result.get("status"),
                    "events_planned": event_result.get("events_planned", 0),
                    "events_created": event_result.get("events_created", 0),
                    "companies": event_result.get("companies", []),
                }
                event_totals["planned"] += int(event_result.get("events_planned", 0) or 0)
                event_totals["created"] += int(event_result.get("events_created", 0) or 0)
            if not audit_only and include_relationships:
                relationship_result = service.build_company_relationships(_symbols_payload(target, payload, execute=execute), actor=actor)
                row["relationship_result"] = {
                    "status": relationship_result.get("status"),
                    "relationships_planned": relationship_result.get("relationships_planned", 0),
                    "relationships_created": relationship_result.get("relationships_created", 0),
                    "relationship_review_candidate_count": relationship_result.get("relationship_review_candidate_count", 0),
                    "companies": relationship_result.get("companies", []),
                }
                relationship_totals["planned"] += int(relationship_result.get("relationships_planned", 0) or 0)
                relationship_totals["created"] += int(relationship_result.get("relationships_created", 0) or 0)
                relationship_totals["review_candidates"] += int(relationship_result.get("relationship_review_candidate_count", 0) or 0)
            quality_after = service.graph_quality_center(
                {
                    **payload,
                    "market": target.market,
                    "limit": 1,
                    "batch_size": 1,
                    "issuer_ids": [target.issuer_id],
                    "run_enrichment": False,
                },
                actor=actor,
            )
            after_item = (quality_after.get("items") or [{}])[0]
            row["after"] = _action_summary(after_item)
        except Exception as exc:  # noqa: BLE001 - batch runner should report and continue
            row["status"] = "failed_with_reason"
            row["errors"].append(str(exc))
            failed_items.append(row)
        items.append(row)
    if execute and (event_totals["created"] or relationship_totals["created"]):
        service.store.commit()
    return {
        "schema_id": "graph-enrichment-runner-v1",
        "status": "audit_only" if audit_only else ("executed" if execute else "dry_run"),
        "execute": execute,
        "audit_only": audit_only,
        "started_at": started_at,
        "completed_at": utcnow().isoformat(),
        "universe": {key: value for key, value in universe.items() if key != "targets"},
        "universe_count": universe.get("target_count", 0),
        "processed_count": len(items),
        "skipped_count": len(skipped_items),
        "failed_count": len(failed_items),
        "batch_size": batch_size,
        "priority_layers": sorted(priority_layers),
        "include_events": include_events,
        "include_relationships": include_relationships,
        "event_totals": dict(event_totals),
        "relationship_totals": dict(relationship_totals),
        "top_missing_layers_before": missing_counter.most_common(10),
        "items": items,
        "skipped_items": skipped_items[:200],
        "failed_items": failed_items,
        "next_recommended_actions": [
            "先审阅 dry-run 中的 event_result 和 relationship_result，再决定是否小批 execute。",
            "execute 后候选事件/关系仍需 review 队列审核，通过后才作为可信事实边使用。",
            "每批执行后重跑 graph_quality_center 或浏览器矩阵，确认图谱变厚且交互没有退化。",
        ],
        "automation_allowed": False,
        "live_execution_allowed": False,
        "usage_boundary": "graph_enrichment_runner_uses_local_public_or_provided_data_only_candidates_need_review_no_broker_no_trade_execution",
    }
