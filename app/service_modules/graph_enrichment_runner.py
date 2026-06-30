from __future__ import annotations

from collections import Counter
from typing import Any, Mapping

from app.utils import utcnow

from . import graph_quality_center, knowledge_graph_bulk


PRIORITY_LAYERS = ["company_event", "company_relationship", "document", "evidence", "shareholder_holding", "research_report", "viewpoint"]
MANUAL_INPUT_LAYERS = {"document", "evidence", "shareholder_holding", "research_report", "viewpoint"}


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
        "layer_counts": dict(readiness.get("layer_counts", {}) or {}),
        "missing_layers": list(readiness.get("missing_layers", []) or []),
        "thin_layers": list(readiness.get("thin_layers", []) or []),
        "cross_links": dict(readiness.get("cross_links", {}) or {}),
        "quality_status": (item.get("quality_gate", {}) or {}).get("status", ""),
    }


def _row_candidate_activity(row: Mapping[str, Any]) -> dict[str, int]:
    event_result = row.get("event_result", {}) or {}
    relationship_result = row.get("relationship_result", {}) or {}
    return {
        "events_planned": int(event_result.get("events_planned", 0) or 0),
        "events_created": int(event_result.get("events_created", 0) or 0),
        "relationships_planned": int(relationship_result.get("relationships_planned", 0) or 0),
        "relationships_created": int(relationship_result.get("relationships_created", 0) or 0),
        "relationship_review_candidates": int(relationship_result.get("relationship_review_candidate_count", 0) or 0),
    }


def _source_input_queue(items: list[Mapping[str, Any]]) -> dict[str, Any]:
    layer_groups: dict[str, dict[str, Any]] = {}
    for row in items:
        for action in row.get("layer_action_plan", []) or []:
            if not action.get("manual_input_required"):
                continue
            layer = str(action.get("layer") or "").strip()
            if not layer:
                continue
            group = layer_groups.setdefault(
                layer,
                {
                    "layer": layer,
                    "action": action.get("action", ""),
                    "endpoint": action.get("endpoint", ""),
                    "fallback_endpoint": action.get("fallback_endpoint", ""),
                    "secondary_endpoint": action.get("secondary_endpoint", ""),
                    "method": action.get("method", ""),
                    "usage_boundary": action.get("usage_boundary", ""),
                    "required_source_fields": list(action.get("required_source_fields", []) or []),
                    "target_count": 0,
                    "targets": [],
                },
            )
            target_payload = dict(action.get("payload", {}) or {})
            target_key = (
                str(target_payload.get("issuer_id") or row.get("issuer_id") or ""),
                str(target_payload.get("security_id") or row.get("security_id") or ""),
                str(target_payload.get("symbol") or row.get("symbol") or ""),
            )
            existing_keys = {
                (str(item.get("issuer_id", "")), str(item.get("security_id", "")), str(item.get("symbol", "")))
                for item in group["targets"]
            }
            if target_key not in existing_keys:
                group["target_count"] += 1
                if len(group["targets"]) < 200:
                    group["targets"].append(
                        {
                            "issuer_id": target_key[0],
                            "security_id": target_key[1],
                            "symbol": target_key[2],
                            "market": row.get("market", ""),
                            "status": row.get("status", ""),
                        }
                    )
    layers = sorted(layer_groups.values(), key=lambda item: (str(item["layer"]), str(item["action"])))
    unique_targets = {
        (str(target.get("issuer_id", "")), str(target.get("security_id", "")), str(target.get("symbol", "")))
        for layer in layers
        for target in layer.get("targets", [])
    }
    return {
        "schema_id": "graph-source-input-queue-v1",
        "status": "needs_source_inputs" if layers else "empty",
        "layer_count": len(layers),
        "target_count": sum(int(item.get("target_count", 0) or 0) for item in layers),
        "unique_target_count": len(unique_targets),
        "layers": layers,
        "usage_boundary": "local_public_or_provided_source_input_queue_no_auto_fact_promotion_no_broker_no_trade_execution",
    }


def _manual_layer_action(layer: str, target: knowledge_graph_bulk.BulkGraphTarget) -> dict[str, Any]:
    target_payload = {"issuer_id": target.issuer_id, "security_id": target.security_id, "symbol": target.symbol}
    specs: dict[str, dict[str, Any]] = {
        "shareholder_holding": {
            "action": "import_13f_holdings",
            "endpoint": "/api/13f/filings/parse",
            "fallback_endpoint": "/api/13f/holdings",
            "label": "导入或映射公开 13F/持仓数据，补齐持有人网络",
        },
        "document": {
            "action": "ingest_source_documents",
            "endpoint": "/api/ingestion/documents",
            "label": "登记本地或公开来源文档，补齐图谱文档层",
        },
        "evidence": {
            "action": "extract_and_link_evidence",
            "endpoint": "/api/evidence/extract",
            "secondary_endpoint": "/api/graph/knowledge-network/evidence-links/backfill",
            "label": "从已登记文档抽取证据并回链事件、关系和观点",
        },
        "research_report": {
            "action": "structure_research_reports",
            "endpoint": "/api/research-reports/structure",
            "label": "把已入库研报结构化为观点层对象，保持观点边界",
        },
        "viewpoint": {
            "action": "structure_or_register_viewpoints",
            "endpoint": "/api/research-reports/structure",
            "fallback_endpoint": "/api/research-report-viewpoints",
            "label": "生成或登记研报观点，补齐观点节点和观点边",
        },
    }
    spec = specs.get(layer, {"action": "review_layer_gap", "endpoint": "", "label": f"补齐 {layer} 图谱层"})
    source_requirements = {
        "shareholder_holding": ["filer identity", "report period", "security identifier", "holding quantity or market value", "public filing/source URI"],
        "document": ["document type", "source id", "source URI or local path", "issuer/security mapping", "rights/source boundary"],
        "evidence": ["document id", "quoted span or extracted text", "issuer/security mapping", "parser/model version"],
        "research_report": ["research report asset id or local path", "broker/institution", "publication date", "opinion-only boundary"],
        "viewpoint": ["research_report_id", "viewpoint text/topic", "viewpoint type", "issuer/security mapping", "opinion-only boundary"],
    }
    return {
        "layer": layer,
        "method": "POST" if spec.get("endpoint") else "",
        "default_execute": False,
        "execute_required": True,
        "manual_input_required": True,
        "payload": target_payload,
        "required_source_fields": source_requirements.get(layer, []),
        "usage_boundary": "local_public_or_provided_data_only_no_broker_no_trade_execution",
        **spec,
    }


def _layer_action_plan(target: knowledge_graph_bulk.BulkGraphTarget, before_gaps: set[str], priority_layers: set[str], *, force_build: bool) -> list[dict[str, Any]]:
    planned_layers = before_gaps if not priority_layers else before_gaps & priority_layers
    if force_build:
        planned_layers = planned_layers | priority_layers
    plan: list[dict[str, Any]] = []
    for layer in sorted(planned_layers):
        if layer == "company_event":
            plan.append(
                {
                    "layer": layer,
                    "action": "build_company_events",
                    "endpoint": "/api/company-database/events/build",
                    "method": "POST",
                    "default_execute": False,
                    "execute_required": True,
                    "manual_input_required": False,
                    "payload": {"symbols": [target.symbol], "issuer_ids": [target.issuer_id], "limit": 1, "execute": False},
                    "usage_boundary": "local_public_or_provided_data_only_no_broker_no_trade_execution",
                }
            )
        elif layer == "company_relationship":
            plan.append(
                {
                    "layer": layer,
                    "action": "build_company_relationships",
                    "endpoint": "/api/company-database/relationships/build",
                    "method": "POST",
                    "default_execute": False,
                    "execute_required": True,
                    "manual_input_required": False,
                    "payload": {"symbols": [target.symbol], "issuer_ids": [target.issuer_id], "limit": 1, "execute": False},
                    "usage_boundary": "local_public_or_provided_data_only_no_broker_no_trade_execution",
                }
            )
        elif layer in MANUAL_INPUT_LAYERS:
            plan.append(_manual_layer_action(layer, target))
    return plan


def _fast_quality_item(service: Any, target: knowledge_graph_bulk.BulkGraphTarget) -> dict[str, Any]:
    counts = knowledge_graph_bulk._layer_counts(service, target)
    relationship_count = sum(
        1
        for item in service.store.company_relationships.values()
        if item.issuer_id == target.issuer_id and (not item.security_id or item.security_id == target.security_id)
    )
    layer_counts = {
        "company_profile": 1,
        "industry_position": counts.get("industry_position", 0),
        "company_relationship": relationship_count,
        "shareholder_holding": counts.get("shareholder_holding", 0),
        "document": counts.get("document", 0),
        "evidence": counts.get("evidence", 0),
        "company_event": counts.get("company_event", 0),
        "research_report": counts.get("research_report", 0),
        "viewpoint": counts.get("viewpoint", 0),
    }
    requirements = {
        "company_profile": 1,
        "industry_position": 1,
        "company_relationship": 1,
        "shareholder_holding": 1,
        "document": 1,
        "evidence": 1,
        "company_event": 1,
        "research_report": 1,
        "viewpoint": 1,
    }
    present_layers = [layer for layer, minimum in requirements.items() if int(layer_counts.get(layer, 0) or 0) >= minimum]
    missing_layers = [layer for layer, minimum in requirements.items() if int(layer_counts.get(layer, 0) or 0) < minimum]
    readiness = {
        "status": "ready" if not missing_layers else "needs_data",
        "ready_for_obsidian_exploration": not missing_layers,
        "layer_counts": layer_counts,
        "present_layers": present_layers,
        "missing_layers": missing_layers,
        "thin_layers": [],
        "cross_links": {},
    }
    return {
        "readiness": readiness,
        "quality_gate": {"status": "not_evaluated_fast_mode"},
    }


def _quality_item(service: Any, target: knowledge_graph_bulk.BulkGraphTarget, payload: Mapping[str, Any], *, actor: str, quality_mode: str) -> dict[str, Any]:
    if quality_mode != "full":
        return _fast_quality_item(service, target)
    quality = service.graph_quality_center(
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
    return (quality.get("items") or [{}])[0]


def graph_enrichment_runner(service: Any, payload: Mapping[str, Any] | None = None, *, actor: str = "system") -> dict[str, Any]:
    payload = payload or {}
    execute = _truthy(payload.get("execute", False))
    audit_only = _truthy(payload.get("audit_only", False))
    include_events = _truthy(payload.get("include_events", True))
    include_relationships = _truthy(payload.get("include_relationships", True))
    force_build = _truthy(payload.get("force_build", False))
    quality_mode = str(payload.get("quality_mode", "fast") or "fast").strip().lower()
    if quality_mode not in {"fast", "full"}:
        quality_mode = "fast"
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
    skip_issuer_ids = {str(item).strip() for item in payload.get("skip_issuer_ids", []) if str(item).strip()}
    items: list[dict[str, Any]] = []
    skipped_items: list[dict[str, Any]] = []
    failed_items: list[dict[str, Any]] = []
    event_totals = Counter()
    relationship_totals = Counter()
    missing_counter = Counter()
    selected = 0
    for target in targets:
        if target.issuer_id in skip_issuer_ids:
            skipped_items.append(
                {
                    "issuer_id": target.issuer_id,
                    "security_id": target.security_id,
                    "symbol": target.symbol,
                    "market": target.market,
                    "reason": "resume_completed",
                }
            )
            continue
        before_item = _quality_item(service, target, payload, actor=actor, quality_mode=quality_mode)
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
            "layer_action_plan": [],
            "manual_input_required_layers": [],
            "after": {},
            "errors": [],
        }
        try:
            before_gaps = set(before_summary["missing_layers"]) | set(before_summary["thin_layers"])
            layer_action_plan = _layer_action_plan(target, before_gaps, priority_layers, force_build=force_build)
            row["layer_action_plan"] = layer_action_plan
            row["manual_input_required_layers"] = [
                item["layer"] for item in layer_action_plan if item.get("manual_input_required")
            ]
            should_build_events = force_build or "company_event" in before_gaps
            should_build_relationships = force_build or "company_relationship" in before_gaps
            if not audit_only and include_events and should_build_events:
                event_result = service.build_company_events(_symbols_payload(target, payload, execute=execute), actor=actor)
                row["event_result"] = {
                    "status": event_result.get("status"),
                    "events_planned": event_result.get("events_planned", 0),
                    "events_created": event_result.get("events_created", 0),
                    "companies": event_result.get("companies", []),
                }
                event_totals["planned"] += int(event_result.get("events_planned", 0) or 0)
                event_totals["created"] += int(event_result.get("events_created", 0) or 0)
            elif not audit_only and include_events:
                row["event_result"] = {"status": "skipped_no_company_event_gap", "events_planned": 0, "events_created": 0, "companies": []}
            if not audit_only and include_relationships and should_build_relationships:
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
            elif not audit_only and include_relationships:
                row["relationship_result"] = {"status": "skipped_no_company_relationship_gap", "relationships_planned": 0, "relationships_created": 0, "relationship_review_candidate_count": 0, "companies": []}
            after_item = _quality_item(service, target, payload, actor=actor, quality_mode=quality_mode)
            row["after"] = _action_summary(after_item)
            activity = _row_candidate_activity(row)
            row["candidate_activity"] = activity
            if not audit_only and not any(activity.values()):
                if row["manual_input_required_layers"]:
                    row["status"] = "waiting_for_source_inputs"
                    row["next_action"] = "按 layer_action_plan 补充本地/公开材料、持仓、证据或研报观点后再重跑增厚；本次不应写入完成恢复集。"
                else:
                    row["status"] = "no_candidate_sources"
                    row["next_action"] = "补充公告、研报、股东表或行情来源后再重跑增厚；本次不应写入完成恢复集。"
        except Exception as exc:  # noqa: BLE001 - batch runner should report and continue
            row["status"] = "failed_with_reason"
            row["errors"].append(str(exc))
            failed_items.append(row)
        items.append(row)
    if execute and (event_totals["created"] or relationship_totals["created"]):
        service.store.commit()
    no_targets = not targets
    status = "no_targets" if no_targets else ("audit_only" if audit_only else ("executed" if execute else "dry_run"))
    source_queue = _source_input_queue(items)
    return {
        "schema_id": "graph-enrichment-runner-v1",
        "status": status,
        "execute": execute,
        "audit_only": audit_only,
        "started_at": started_at,
        "completed_at": utcnow().isoformat(),
        "universe": {key: value for key, value in universe.items() if key != "targets"},
        "universe_count": universe.get("target_count", 0),
        "processed_count": len(items),
        "skipped_count": len(skipped_items),
        "resume_skipped_count": sum(1 for item in skipped_items if item.get("reason") == "resume_completed"),
        "failed_count": len(failed_items),
        "global_failures": [{"check": "target_universe", "actual": 0, "expected_min": 1}] if no_targets else [],
        "batch_size": batch_size,
        "priority_layers": sorted(priority_layers),
        "include_events": include_events,
        "include_relationships": include_relationships,
        "force_build": force_build,
        "quality_mode": quality_mode,
        "event_totals": dict(event_totals),
        "relationship_totals": dict(relationship_totals),
        "top_missing_layers_before": missing_counter.most_common(10),
        "manual_input_required_count": sum(1 for item in items if item.get("manual_input_required_layers")),
        "manual_input_required_layers": sorted(
            {layer for item in items for layer in item.get("manual_input_required_layers", [])}
        ),
        "source_input_queue": source_queue,
        "items": items,
        "skipped_items": skipped_items[:200],
        "failed_items": failed_items,
        "next_recommended_actions": [
            "先审阅 dry-run 中的 event_result 和 relationship_result，再决定是否小批 execute。",
            "document/evidence/shareholder_holding/research_report/viewpoint 层需要先按 layer_action_plan 补充本地或公开来源材料。",
            "execute 后候选事件/关系仍需 review 队列审核，通过后才作为可信事实边使用。",
            "每批执行后重跑 graph_quality_center 或浏览器矩阵，确认图谱变厚且交互没有退化。",
        ],
        "automation_allowed": False,
        "live_execution_allowed": False,
        "usage_boundary": "graph_enrichment_runner_uses_local_public_or_provided_data_only_candidates_need_review_no_broker_no_trade_execution",
    }
