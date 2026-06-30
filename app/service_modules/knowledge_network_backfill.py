from __future__ import annotations

from typing import Any, Mapping

from app.utils import to_plain, utcnow


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _evidence_by_document(store: Any) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    for evidence in store.evidence.values():
        document_id = str(getattr(evidence, "document_id", "") or "").strip()
        evidence_id = str(getattr(evidence, "evidence_id", "") or "").strip()
        if not document_id or not evidence_id:
            continue
        mapping.setdefault(document_id, []).append(evidence_id)
    return {document_id: _unique(evidence_ids) for document_id, evidence_ids in mapping.items()}


def _report_document_id(store: Any, research_report_id: str) -> str:
    report = store.structured_research_reports.get(research_report_id)
    if report is not None:
        return str(getattr(report, "document_id", "") or "").strip()
    report_asset = store.research_reports.get(research_report_id)
    return str(getattr(report_asset, "document_id", "") or "").strip() if report_asset is not None else ""


def backfill_knowledge_network_evidence_links(
    service: Any,
    payload: Mapping[str, Any] | None = None,
    *,
    actor: str = "system",
) -> dict[str, Any]:
    payload = payload or {}
    execute = bool(payload.get("execute", False))
    dry_run = not execute
    limit = max(1, min(500, int(payload.get("limit", 100) or 100)))
    graph_filters = {
        key: str(payload.get(key, "") or "").strip()
        for key in ["issuer_id", "security_id", "relationship_type", "ownership_holder_key", "institutional_holder_key", "chain_id", "chain_node_id"]
        if str(payload.get(key, "") or "").strip()
    }
    graph = service.query_graph(graph_filters)
    evidence_by_doc = _evidence_by_document(service.store)
    generated_at = utcnow().isoformat()
    plans: list[dict[str, Any]] = []

    for event_row in graph.get("company_events", []):
        event_id = str(event_row.get("event_id", "") or "").strip()
        event = service.store.company_events.get(event_id)
        if event is None:
            continue
        candidate_evidence_ids = _unique(
            [
                evidence_id
                for document_id in getattr(event, "document_ids", [])
                for evidence_id in evidence_by_doc.get(str(document_id), [])
            ]
        )
        missing = [evidence_id for evidence_id in candidate_evidence_ids if evidence_id not in event.evidence_ids]
        if missing:
            plans.append(
                {
                    "resource_type": "company_event",
                    "resource_id": event.event_id,
                    "document_ids": list(event.document_ids),
                    "evidence_ids": missing,
                    "existing_evidence_ids": list(event.evidence_ids),
                }
            )

    for relationship_row in graph.get("company_relationships", []):
        relationship_id = str(relationship_row.get("relationship_id", "") or "").strip()
        relationship = service.store.company_relationships.get(relationship_id)
        if relationship is None:
            continue
        candidate_evidence_ids = _unique(
            [
                evidence_id
                for document_id in getattr(relationship, "document_ids", [])
                for evidence_id in evidence_by_doc.get(str(document_id), [])
            ]
        )
        missing = [evidence_id for evidence_id in candidate_evidence_ids if evidence_id not in relationship.evidence_ids]
        if missing:
            plans.append(
                {
                    "resource_type": "company_relationship",
                    "resource_id": relationship.relationship_id,
                    "document_ids": list(relationship.document_ids),
                    "evidence_ids": missing,
                    "existing_evidence_ids": list(relationship.evidence_ids),
                }
            )

    for viewpoint_row in graph.get("report_viewpoints", []):
        viewpoint_id = str(viewpoint_row.get("viewpoint_id", "") or "").strip()
        viewpoint = service.store.report_viewpoints.get(viewpoint_id)
        if viewpoint is None:
            continue
        document_id = _report_document_id(service.store, viewpoint.research_report_id)
        candidate_evidence_ids = evidence_by_doc.get(document_id, []) if document_id else []
        missing = [evidence_id for evidence_id in candidate_evidence_ids if evidence_id not in viewpoint.evidence_ids]
        if missing:
            plans.append(
                {
                    "resource_type": "report_viewpoint",
                    "resource_id": viewpoint.viewpoint_id,
                    "document_ids": [document_id] if document_id else [],
                    "evidence_ids": missing,
                    "existing_evidence_ids": list(viewpoint.evidence_ids),
                }
            )

    plans = plans[:limit]
    updated: list[dict[str, Any]] = []
    if execute:
        for plan in plans:
            resource_type = plan["resource_type"]
            resource_id = plan["resource_id"]
            evidence_ids = [str(item) for item in plan["evidence_ids"]]
            if resource_type == "company_event":
                resource = service.store.company_events[resource_id]
                resource.evidence_ids = _unique([*resource.evidence_ids, *evidence_ids])
                resource.metadata.setdefault("knowledge_network_evidence_backfill", {})
                if isinstance(resource.metadata["knowledge_network_evidence_backfill"], dict):
                    resource.metadata["knowledge_network_evidence_backfill"].update({"updated_at": generated_at, "actor": actor})
            elif resource_type == "company_relationship":
                resource = service.store.company_relationships[resource_id]
                resource.evidence_ids = _unique([*resource.evidence_ids, *evidence_ids])
                resource.metadata.setdefault("knowledge_network_evidence_backfill", {})
                if isinstance(resource.metadata["knowledge_network_evidence_backfill"], dict):
                    resource.metadata["knowledge_network_evidence_backfill"].update({"updated_at": generated_at, "actor": actor})
            elif resource_type == "report_viewpoint":
                resource = service.store.report_viewpoints[resource_id]
                resource.evidence_ids = _unique([*resource.evidence_ids, *evidence_ids])
                resource.notes = (resource.notes + "\n" if resource.notes else "") + f"Knowledge-network evidence backfilled at {generated_at}."
            else:
                continue
            updated.append({**plan, "status": "updated"})
        marker = getattr(service.store, "mark_dirty_for_resource", None)
        if callable(marker):
            for resource_type in ["company_event", "company_relationship", "report_viewpoint"]:
                marker(resource_type)
        service.store.commit()
        service._audit(
            actor,
            "backfill_knowledge_network_evidence_links",
            "graph",
            ",".join(graph_filters.values()) or "all",
            approval_state=f"updated={len(updated)}",
        )

    counts: dict[str, int] = {}
    for plan in plans:
        counts[plan["resource_type"]] = counts.get(plan["resource_type"], 0) + 1
    return {
        "schema_id": "knowledge-network-evidence-link-backfill-v1",
        "status": "executed" if execute else "dry_run",
        "execute": execute,
        "dry_run": dry_run,
        "filters": graph_filters,
        "planned_count": len(plans),
        "updated_count": len(updated),
        "planned_by_type": counts,
        "plans": plans,
        "updated": updated,
        "automation_allowed": False,
        "live_execution_allowed": False,
        "usage_boundary": "knowledge_network_evidence_link_backfill_updates_local_provenance_links_only_no_broker_no_trade_execution",
    }
