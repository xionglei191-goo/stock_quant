"""Read-only knowledge-graph density and renderer-capacity audit helpers."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from time import perf_counter
from typing import Any, Iterable, Mapping
import json
import sqlite3


SCHEMA_ID = "graph-density-capacity-audit-v1"
LAYER_COLLECTIONS = {
    "company_profile": "company_profiles",
    "industry_position": "company_positions",
    "company_relationship": "company_relationships",
    "shareholder_holding": "institutional_holdings",
    "document": "documents",
    "evidence": "evidence",
    "company_event": "company_events",
    "research_report": "structured_research_reports",
    "viewpoint": "report_viewpoints",
}
SEED_FIXTURE_MARKERS = (
    "obsidian",
    "knowledge-graph-seed",
    "local_seed",
    "fixture",
    "acceptance",
    "example.invalid",
    "issuer_demo",
    "security_demo",
    "sec_demo",
    "demo corp",
    "demo holdings",
    "spcx research vehicle",
    "synthetic",
    "fallback",
    "local://samples/",
    "local_10k",
)
GOVERNED_URI_MARKERS = ("sec.gov/", "hkexnews.hk/", "sse.com.cn/", "szse.cn/", "local://")


def renderer_recommendation(nodes: int, edges: int) -> str:
    """Return the policy tier for a visible graph, independent of provenance."""
    if nodes <= 250 and edges <= 500:
        return "svg"
    if nodes <= 750 and edges <= 1500:
        return "svg_virtualized"
    if nodes <= 3000 and edges <= 6000:
        return "canvas"
    return "webgl"


def _provenance_text(record: Mapping[str, Any]) -> str:
    fields = [
        "issuer_id",
        "security_id",
        "document_id",
        "evidence_id",
        "event_id",
        "relationship_id",
        "position_id",
        "holding_id",
        "research_report_id",
        "viewpoint_id",
        "source_id",
        "source_ids",
        "source_type",
        "source_uri",
        "metadata",
        "rights_boundary",
        "company_universe_reason",
        "data_quality",
        "legal_name",
    ]
    scoped = {
        field: record.get(field)
        for field in fields
        if record.get(field) is not None and record.get(field) != "" and record.get(field) != [] and record.get(field) != {}
    }
    return json.dumps(scoped, ensure_ascii=False, sort_keys=True, default=str).lower()


def _direct_provenance(record: Mapping[str, Any]) -> str:
    text = _provenance_text(record)
    if any(marker in text for marker in SEED_FIXTURE_MARKERS):
        return "seed_fixture"
    rights = record.get("rights_tag", {})
    license_class = str(rights.get("license_class", "") if isinstance(rights, Mapping) else "").lower()
    source_uri = str(record.get("source_uri", "") or "").lower()
    source_values = [record.get("source_id", ""), *(record.get("source_ids", []) or [])]
    has_source = any(str(value or "").strip() for value in source_values)
    if any(marker in source_uri for marker in GOVERNED_URI_MARKERS):
        return "governed"
    if license_class in {"public", "local_research_reference", "local_public"} and (source_uri or has_source):
        return "governed"
    return "unclear"


def _read_records(path: Path) -> dict[str, list[dict[str, Any]]]:
    resolved = path.resolve()
    connection = sqlite3.connect(f"file:{resolved}?mode=ro", uri=True)
    try:
        tables = {str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "records" not in tables:
            return {}
        collections: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for collection, payload in connection.execute("SELECT collection, payload FROM records"):
            try:
                parsed = json.loads(payload)
            except (TypeError, json.JSONDecodeError):
                continue
            if isinstance(parsed, Mapping):
                collections[str(collection)].append(dict(parsed))
        return dict(collections)
    finally:
        connection.close()


def _record_id(record: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = str(record.get(key, "") or "").strip()
        if value:
            return value
    return ""


def _subject_rows(collections: Mapping[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    securities_by_issuer: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for security in collections.get("securities", []):
        securities_by_issuer[_record_id(security, "issuer_id")].append(security)
    rows: list[dict[str, Any]] = []
    for issuer in collections.get("issuers", []):
        issuer_id = _record_id(issuer, "issuer_id")
        securities = securities_by_issuer.get(issuer_id, [])
        rows.append(
            {
                "issuer_id": issuer_id,
                "name": _record_id(issuer, "legal_name", "name") or issuer_id,
                "symbols": sorted({_record_id(item, "ticker", "symbol") for item in securities if _record_id(item, "ticker", "symbol")}),
                "security_ids": sorted({_record_id(item, "security_id") for item in securities if _record_id(item, "security_id")}),
                "issuer_record": issuer,
            }
        )
    return rows


def _matches_subject(record: Mapping[str, Any], issuer_id: str, security_ids: set[str]) -> bool:
    if _record_id(record, "issuer_id") == issuer_id:
        return True
    if _record_id(record, "security_id") in security_ids:
        return True
    return issuer_id in {_record_id(record, "subject_id"), _record_id(record, "object_id")}


def _provenance_with_links(
    record: Mapping[str, Any],
    *,
    document_classes: Mapping[str, str],
    evidence_classes: Mapping[str, str],
    report_classes: Mapping[str, str],
) -> str:
    direct = _direct_provenance(record)
    if direct != "unclear":
        return direct
    linked: list[str] = []
    document_id = _record_id(record, "document_id")
    if document_id:
        linked.append(document_classes.get(document_id, "unclear"))
    linked.extend(document_classes.get(str(item), "unclear") for item in record.get("document_ids", []) or [])
    linked.extend(evidence_classes.get(str(item), "unclear") for item in record.get("evidence_ids", []) or [])
    report_id = _record_id(record, "research_report_id")
    if report_id:
        linked.append(report_classes.get(report_id, "unclear"))
    if "seed_fixture" in linked:
        return "seed_fixture"
    if "governed" in linked:
        return "governed"
    return "unclear"


def _link_ratio(linked: int, eligible: int) -> dict[str, Any]:
    return {
        "linked": linked,
        "eligible": eligible,
        "ratio": round(linked / eligible, 4) if eligible else None,
    }


def _audit_subject(collections: Mapping[str, list[dict[str, Any]]], subject: Mapping[str, Any]) -> dict[str, Any]:
    issuer_id = str(subject["issuer_id"])
    security_ids = set(subject["security_ids"])
    scoped: dict[str, list[dict[str, Any]]] = {}
    for layer, collection in LAYER_COLLECTIONS.items():
        rows = [row for row in collections.get(collection, []) if _matches_subject(row, issuer_id, security_ids)]
        scoped[layer] = rows

    documents = scoped["document"]
    document_ids = {_record_id(row, "document_id") for row in documents if _record_id(row, "document_id")}
    scoped["evidence"] = [row for row in collections.get("evidence", []) if _record_id(row, "document_id") in document_ids or _matches_subject(row, issuer_id, security_ids)]
    reports = scoped["research_report"]
    report_ids = {_record_id(row, "research_report_id", "report_id") for row in reports if _record_id(row, "research_report_id", "report_id")}
    scoped["viewpoint"] = [
        row
        for row in collections.get("report_viewpoints", [])
        if _matches_subject(row, issuer_id, security_ids) or _record_id(row, "research_report_id") in report_ids
    ]

    document_classes = {_record_id(row, "document_id"): _direct_provenance(row) for row in scoped["document"]}
    evidence_classes = {
        _record_id(row, "evidence_id"): _provenance_with_links(
            row,
            document_classes=document_classes,
            evidence_classes={},
            report_classes={},
        )
        for row in scoped["evidence"]
    }
    report_classes = {
        _record_id(row, "research_report_id", "report_id"): _provenance_with_links(
            row,
            document_classes=document_classes,
            evidence_classes=evidence_classes,
            report_classes={},
        )
        for row in scoped["research_report"]
    }

    layer_counts: dict[str, dict[str, int]] = {}
    classes_by_layer: dict[str, list[str]] = {}
    for layer, rows in scoped.items():
        classes = [
            _provenance_with_links(
                row,
                document_classes=document_classes,
                evidence_classes=evidence_classes,
                report_classes=report_classes,
            )
            for row in rows
        ]
        classes_by_layer[layer] = classes
        layer_counts[layer] = {
            "total": len(rows),
            "governed": classes.count("governed"),
            "seed_fixture": classes.count("seed_fixture"),
            "unclear": classes.count("unclear"),
        }

    evidence_by_document = {_record_id(row, "document_id") for row in scoped["evidence"]}
    evidence_ids = {_record_id(row, "evidence_id") for row in scoped["evidence"]}
    events = scoped["company_event"]
    relationships = scoped["company_relationship"]
    viewpoints = scoped["viewpoint"]
    cross_links = {
        "document_evidence": _link_ratio(len(document_ids & evidence_by_document), len(document_ids)),
        "event_document": _link_ratio(sum(bool(set(map(str, row.get("document_ids", []) or [])) & document_ids) for row in events), len(events)),
        "event_evidence": _link_ratio(sum(bool(set(map(str, row.get("evidence_ids", []) or [])) & evidence_ids) for row in events), len(events)),
        "relationship_evidence": _link_ratio(sum(bool(set(map(str, row.get("evidence_ids", []) or [])) & evidence_ids) for row in relationships), len(relationships)),
        "report_document": _link_ratio(sum(_record_id(row, "document_id") in document_ids for row in reports), len(reports)),
        "viewpoint_report": _link_ratio(sum(_record_id(row, "research_report_id") in report_ids for row in viewpoints), len(viewpoints)),
        "viewpoint_evidence": _link_ratio(sum(bool(set(map(str, row.get("evidence_ids", []) or [])) & evidence_ids) for row in viewpoints), len(viewpoints)),
    }
    eligible_links = sum(int(row["eligible"]) for row in cross_links.values())
    linked = sum(int(row["linked"]) for row in cross_links.values())

    total_rows = sum(row["total"] for row in layer_counts.values())
    governed_rows = sum(row["governed"] for row in layer_counts.values())
    seed_rows = sum(row["seed_fixture"] for row in layer_counts.values())
    unclear_rows = sum(row["unclear"] for row in layer_counts.values())
    governed_layers = [layer for layer, counts in layer_counts.items() if counts["governed"] > 0]
    estimated_nodes = 1 + len(security_ids) + total_rows
    estimated_edges = (
        len(security_ids)
        + len(scoped["industry_position"]) * 3
        + len(relationships) * 3
        + len(scoped["shareholder_holding"]) * 2
        + len(documents)
        + len(scoped["evidence"])
        + len(events)
        + len(reports)
        + len(viewpoints)
        + linked
    )
    issuer_class = _direct_provenance(subject["issuer_record"])
    if issuer_class == "unclear" and governed_rows:
        issuer_class = "governed"
    if seed_rows and seed_rows >= governed_rows + unclear_rows:
        issuer_class = "seed_fixture"
    return {
        "issuer_id": issuer_id,
        "name": subject["name"],
        "symbols": subject["symbols"],
        "provenance_class": issuer_class,
        "layer_counts": layer_counts,
        "governed_layer_coverage": {
            "covered": len(governed_layers),
            "required": len(LAYER_COLLECTIONS),
            "ratio": round(len(governed_layers) / len(LAYER_COLLECTIONS), 4),
            "layers": governed_layers,
            "missing_layers": [layer for layer in LAYER_COLLECTIONS if layer not in governed_layers],
        },
        "row_provenance": {
            "total": total_rows,
            "governed": governed_rows,
            "seed_fixture": seed_rows,
            "unclear": unclear_rows,
            "governed_ratio": round(governed_rows / total_rows, 4) if total_rows else 0.0,
        },
        "cross_links": cross_links,
        "cross_layer_link_coverage": _link_ratio(linked, eligible_links),
        "estimated_raw_model": {
            "nodes": estimated_nodes,
            "edges": estimated_edges,
            "policy_tier": renderer_recommendation(estimated_nodes, estimated_edges),
            "measurement_boundary": "model_estimate_not_browser_render_measurement",
        },
    }


def synthetic_model_curve(scales: Iterable[tuple[int, int]], *, repeats: int = 5) -> list[dict[str, Any]]:
    """Benchmark deterministic adjacency/filter preparation, not rendering."""
    rows: list[dict[str, Any]] = []
    for nodes, edges in scales:
        node_rows = [{"id": f"n{index}", "community": index % 7} for index in range(nodes)]
        edge_rows = [
            {"from": f"n{index % nodes}", "to": f"n{(index * 17 + 3) % nodes}", "type": f"t{index % 11}"}
            for index in range(edges)
        ] if nodes else []
        timings: list[float] = []
        checksum = 0
        for _ in range(max(1, repeats)):
            started = perf_counter()
            adjacency: dict[str, list[str]] = defaultdict(list)
            for edge in edge_rows:
                adjacency[edge["from"]].append(edge["to"])
                adjacency[edge["to"]].append(edge["from"])
            visible = [node for node in node_rows if adjacency.get(node["id"]) or node["community"] == 0]
            checksum = sum(len(adjacency.get(node["id"], [])) for node in visible)
            timings.append((perf_counter() - started) * 1000.0)
        rows.append(
            {
                "nodes": nodes,
                "edges": edges,
                "median_prepare_ms": round(median(timings), 4),
                "checksum": checksum,
                "policy_tier": renderer_recommendation(nodes, edges),
                "measurement_boundary": "synthetic_python_model_preparation_not_dom_canvas_or_webgl_rendering",
            }
        )
    return rows


def browser_measurements(paths: Iterable[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        measurement = payload.get("measurement", {}) if isinstance(payload, Mapping) else {}
        performance = measurement.get("performance", {}) if isinstance(measurement, Mapping) else {}
        nodes = int(measurement.get("nodes", 0) or 0)
        edges = int(measurement.get("links", 0) or 0)
        rows.append(
            {
                "artifact": str(path),
                "status": payload.get("status", "unknown"),
                "nodes": nodes,
                "edges": edges,
                "fps": performance.get("fps"),
                "avg_frame_ms": performance.get("avg_frame_ms"),
                "policy_tier": renderer_recommendation(nodes, edges),
                "provenance_class": "seed_fixture",
                "measurement_boundary": "existing_browser_measurement_but_seed_or_acceptance_data_not_governed_real_density",
            }
        )
    return rows


def build_density_capacity_audit(
    state_dbs: Iterable[Path],
    *,
    browser_artifacts: Iterable[Path] = (),
) -> dict[str, Any]:
    datasets: list[dict[str, Any]] = []
    subjects: list[dict[str, Any]] = []
    for path in state_dbs:
        collections = _read_records(path)
        dataset_subjects = _subject_rows(collections)
        audited = [_audit_subject(collections, subject) for subject in dataset_subjects]
        for row in audited:
            row["state_db"] = str(path)
        subjects.extend(audited)
        datasets.append(
            {
                "state_db": str(path),
                "subject_count": len(audited),
                "record_count": sum(len(rows) for rows in collections.values()),
                "read_mode": "sqlite_uri_mode_ro",
            }
        )

    governed_subjects = [row for row in subjects if row["provenance_class"] == "governed"]
    largest_governed = max(
        governed_subjects,
        key=lambda row: (row["estimated_raw_model"]["nodes"], row["estimated_raw_model"]["edges"]),
        default=None,
    )
    browser_rows = browser_measurements(browser_artifacts)
    largest_browser = max(browser_rows, key=lambda row: (row["nodes"], row["edges"]), default=None)
    real_browser_verified = any(row.get("provenance_class") == "governed" for row in browser_rows)
    raw_tier = largest_governed["estimated_raw_model"]["policy_tier"] if largest_governed else "unavailable"
    decision = {
        "current_renderer": "svg",
        "recommendation": "retain_svg_with_visible_graph_virtualization_and_run_governed_browser_capacity_gate",
        "raw_governed_model_tier": raw_tier,
        "real_governed_browser_capacity_verified": real_browser_verified,
        "canvas_or_webgl_migration_approved": False,
        "reason": (
            "Governed raw density may exceed the SVG full-materialization tier, but existing browser measurements are seed/fixture-only. "
            "Keep SVG for the bounded visible graph; do not approve Canvas/WebGL until a governed browser run crosses a visible threshold or fails the frame budget."
        ),
        "thresholds": {
            "svg": {"max_visible_nodes": 250, "max_visible_edges": 500, "min_fps": 45, "max_avg_frame_ms": 16.7},
            "svg_virtualized": {"max_visible_nodes": 750, "max_visible_edges": 1500},
            "canvas_trigger": {"visible_nodes_gt": 750, "visible_edges_gt": 1500, "or_fps_below": 45, "or_avg_frame_ms_above": 16.7, "required_consecutive_runs": 3},
            "webgl_trigger": {"visible_nodes_gt": 3000, "visible_edges_gt": 6000, "or_canvas_gate_failed": True},
        },
    }
    return {
        "schema_id": SCHEMA_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "artifact_metadata": {
            "classification": "local-only",
            "owner_group": "Data and Evidence",
            "contains_sensitive_data": False,
            "acceptable_for_non_local_release_gate": False,
        },
        "status": "measured_with_browser_gap" if subjects else "no_subjects",
        "datasets": datasets,
        "subject_count": len(subjects),
        "governed_subject_count": len(governed_subjects),
        "subjects": subjects,
        "largest_governed_subject": largest_governed,
        "browser_measurements": browser_rows,
        "largest_browser_measurement": largest_browser,
        "synthetic_model_curve": synthetic_model_curve([(100, 200), (250, 500), (500, 1000), (750, 1500), (1000, 2000), (3000, 6000)]),
        "renderer_decision": decision,
        "data_writes_performed": False,
        "automation_allowed": False,
        "live_execution_allowed": False,
        "usage_boundary": "read_only_local_density_and_capacity_audit_no_fact_import_no_broker_no_trade_execution",
    }
