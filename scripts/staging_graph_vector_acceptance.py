from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
import sys
import time
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.staging_acceptance import DEFAULT_BASE_URL, StagingClient


def _json_request(url: str, *, method: str = "GET", body: dict[str, Any] | None = None, headers: dict[str, str] | None = None, timeout: float = 10.0) -> dict[str, Any]:
    data = json.dumps(body or {}).encode("utf-8") if body is not None else None
    request = Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    with urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw) if raw else {}


def _neo4j_auth_header(user: str, password: str) -> dict[str, str]:
    token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {token}"}


def _neo4j_scalar(url: str, auth: dict[str, str], statement: str, parameters: dict[str, Any] | None = None, *, timeout: float) -> Any:
    payload = {"statements": [{"statement": statement, "parameters": parameters or {}}]}
    result = _json_request(url, method="POST", body=payload, headers=auth, timeout=timeout)
    if result.get("errors"):
        raise RuntimeError(f"Neo4j query failed: {result['errors']}")
    rows = result.get("results", [{}])[0].get("data", [])
    if not rows:
        return None
    return rows[0].get("row", [None])[0]


def _neo4j_property_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _neo4j_sanitize_properties(values: dict[str, Any]) -> dict[str, Any]:
    return {str(key): _neo4j_property_value(value) for key, value in values.items()}


def _neo4j_sync(export: dict[str, Any], *, url: str, user: str, password: str, timeout: float) -> dict[str, Any]:
    auth = _neo4j_auth_header(user, password)
    _neo4j_scalar(url, auth, "RETURN 1 AS ok", timeout=timeout)
    nodes = [{"id": node["id"], "properties": _neo4j_sanitize_properties(dict(node.get("properties", {})))} for node in export.get("nodes", [])]
    relationships = [
        {
            "type": rel["type"],
            "start_id": rel["start_id"],
            "end_id": rel["end_id"],
            "properties": _neo4j_sanitize_properties(dict(rel.get("properties", {}))),
        }
        for rel in export.get("relationships", [])
    ]
    batch_id = export.get("content_sha256", "")[:16] or str(int(time.time()))
    _neo4j_scalar(
        url,
        auth,
        """
        UNWIND $nodes AS row
        MERGE (n:AIQuant {id: row.id})
        SET n += row.properties, n.last_sync_batch = $batch_id
        RETURN count(n) AS count
        """,
        {"nodes": nodes, "batch_id": batch_id},
        timeout=timeout,
    )
    # Dynamic relationship types are not parameterizable in Cypher, so group by sanitized type.
    by_type: dict[str, list[dict[str, Any]]] = {}
    for rel in relationships:
        rel_type = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in str(rel["type"]).upper()).strip("_") or "RELATED_TO"
        by_type.setdefault(rel_type, []).append(rel)
    for rel_type, rows in by_type.items():
        _neo4j_scalar(
            url,
            auth,
            f"""
            UNWIND $relationships AS row
            MERGE (start:AIQuant {{id: row.start_id}})
            MERGE (end:AIQuant {{id: row.end_id}})
            MERGE (start)-[r:{rel_type}]->(end)
            SET r += row.properties, r.last_sync_batch = $batch_id
            RETURN count(r) AS count
            """,
            {"relationships": rows, "batch_id": batch_id},
            timeout=timeout,
        )
    node_count = _neo4j_scalar(url, auth, "MATCH (n:AIQuant) RETURN count(n) AS count", timeout=timeout)
    relationship_count = _neo4j_scalar(url, auth, "MATCH (:AIQuant)-[r]->(:AIQuant) RETURN count(r) AS count", timeout=timeout)
    return {
        "status": "passed",
        "target": url,
        "export_node_count": export.get("node_count", 0),
        "export_relationship_count": export.get("relationship_count", 0),
        "synced_nodes": len(nodes),
        "synced_relationships": len(relationships),
        "stored_node_count": int(node_count or 0),
        "stored_relationship_count": int(relationship_count or 0),
        "batch_id": batch_id,
    }


def _qdrant_sync(export: dict[str, Any], *, base_url: str, collection: str, timeout: float) -> dict[str, Any]:
    base_url = base_url.rstrip("/")
    _json_request(f"{base_url}/collections", timeout=timeout)
    try:
        _json_request(
            f"{base_url}/collections/{collection}",
            method="PUT",
            body={"vectors": {"text_tf_hash": {"size": 64, "distance": "Cosine"}}},
            timeout=timeout,
        )
    except HTTPError as exc:
        if exc.code != 409:
            raise
    points = []
    for point in export.get("points", []):
        vectors = dict(point.get("vector", {}))
        payload = dict(point.get("payload", {}))
        points.append({"id": point["id"], "vector": vectors, "payload": payload})
    if points:
        _json_request(
            f"{base_url}/collections/{collection}/points?wait=true",
            method="PUT",
            body={"points": points},
            timeout=timeout,
        )
    count_result = _json_request(f"{base_url}/collections/{collection}/points/count", method="POST", body={"exact": True}, timeout=timeout)
    scroll_result = _json_request(f"{base_url}/collections/{collection}/points/scroll", method="POST", body={"limit": 1, "with_payload": True, "with_vector": False}, timeout=timeout)
    stored_count = int(count_result.get("result", {}).get("count", 0))
    sample = (scroll_result.get("result", {}).get("points") or [{}])[0]
    return {
        "status": "passed",
        "target": base_url,
        "collection": collection,
        "export_point_count": export.get("point_count", 0),
        "synced_points": len(points),
        "stored_point_count": stored_count,
        "sample_payload_keys": sorted((sample.get("payload") or {}).keys()),
    }


def run_staging_graph_vector_acceptance(
    *,
    base_url: str = DEFAULT_BASE_URL,
    neo4j_url: str = "http://127.0.0.1:7474/db/neo4j/tx/commit",
    neo4j_user: str = "neo4j",
    neo4j_password: str = "localneo4jpassword",
    qdrant_url: str = "http://127.0.0.1:6333",
    qdrant_collection: str = "ai_quant_staging_acceptance",
    timeout: float = 10.0,
) -> dict[str, Any]:
    client = StagingClient(base_url, timeout=timeout)
    client.request("POST", "/api/demo/full-flow", {}, role="platform", actor="graph_vector_acceptance")
    neo4j_export = client.request("POST", "/api/graph/neo4j/export", {"issuer_id": "issuer_demo", "record_export": True}, role="CEO", actor="graph_vector_acceptance")
    qdrant_export = client.request(
        "POST",
        "/api/search/qdrant/export",
        {"issuer_id": "issuer_demo", "collection": qdrant_collection, "include_restricted": False, "record_export": True},
        role="CEO",
        actor="graph_vector_acceptance",
    )
    neo4j_result = _neo4j_sync(neo4j_export, url=neo4j_url, user=neo4j_user, password=neo4j_password, timeout=timeout)
    qdrant_result = _qdrant_sync(qdrant_export, base_url=qdrant_url, collection=qdrant_collection, timeout=timeout)
    retry_seed = client.request("POST", "/api/graph/neo4j/sync", {"issuer_id": "issuer_demo", "target": "https://graph.example.invalid/neo4j", "channel": "webhook", "provider": "webhook", "force": True}, role="platform", actor="graph_vector_acceptance")
    retry_seed_2 = client.request("POST", "/api/search/qdrant/sync", {"issuer_id": "issuer_demo", "target": "https://vector.example.invalid/qdrant", "channel": "webhook", "provider": "webhook", "force": True}, role="platform", actor="graph_vector_acceptance")
    client.request("POST", "/api/alerts/notifications/deliver", {"channel": "webhook", "execute": True, "provider": "webhook", "timeout_ms": 100}, role="platform", actor="graph_vector_acceptance")
    retry = client.request("POST", "/api/search/adapter-sync/retry", {"channels": ["webhook"], "status": "failed", "execute": True, "provider": "dry-run-sender"}, role="platform", actor="graph_vector_acceptance")
    passed = (
        neo4j_result["synced_nodes"] >= int(neo4j_export.get("node_count", 0)) > 0
        and neo4j_result["synced_relationships"] >= int(neo4j_export.get("relationship_count", 0)) > 0
        and qdrant_result["synced_points"] >= int(qdrant_export.get("point_count", 0)) > 0
        and qdrant_result["stored_point_count"] >= qdrant_result["synced_points"]
        and int(retry.get("retried_count", 0)) >= 2
    )
    return {
        "status": "passed" if passed else "failed",
        "base_url": base_url,
        "neo4j": neo4j_result,
        "qdrant": qdrant_result,
        "retry_seed": {"neo4j": retry_seed, "qdrant": retry_seed_2},
        "retry": retry,
        "production_boundary": "direct_local_staging_neo4j_qdrant_sync_no_live_execution",
    }


def summarize_acceptance(result: dict[str, Any]) -> dict[str, Any]:
    neo4j = dict(result.get("neo4j", {}))
    qdrant = dict(result.get("qdrant", {}))
    retry = dict(result.get("retry", {}))
    retry_seed = result.get("retry_seed", {})
    if isinstance(retry_seed, dict):
        retry_seed_summary = {
            key: {
                "count": value.get("count", 0),
                "channel": value.get("channel", ""),
                "target": value.get("target", ""),
                "external_delivery_ready": value.get("external_delivery_ready", False),
            }
            for key, value in retry_seed.items()
            if isinstance(value, dict)
        }
    else:
        retry_seed_summary = {}
    return {
        "status": result.get("status", "failed"),
        "base_url": result.get("base_url", ""),
        "production_boundary": result.get("production_boundary", ""),
        "neo4j": {
            "status": neo4j.get("status", ""),
            "target": neo4j.get("target", ""),
            "export_node_count": neo4j.get("export_node_count", 0),
            "export_relationship_count": neo4j.get("export_relationship_count", 0),
            "synced_nodes": neo4j.get("synced_nodes", 0),
            "synced_relationships": neo4j.get("synced_relationships", 0),
            "stored_node_count": neo4j.get("stored_node_count", 0),
            "stored_relationship_count": neo4j.get("stored_relationship_count", 0),
        },
        "qdrant": {
            "status": qdrant.get("status", ""),
            "target": qdrant.get("target", ""),
            "collection": qdrant.get("collection", ""),
            "export_point_count": qdrant.get("export_point_count", 0),
            "synced_points": qdrant.get("synced_points", 0),
            "stored_point_count": qdrant.get("stored_point_count", 0),
            "sample_payload_keys": qdrant.get("sample_payload_keys", []),
        },
        "retry_seed": retry_seed_summary,
        "retry": {
            "candidate_count": retry.get("candidate_count", 0),
            "retryable_count": retry.get("retryable_count", 0),
            "retried_count": retry.get("retried_count", 0),
            "channels": retry.get("channels", []),
            "status_filter": retry.get("status_filter", ""),
            "usage_boundary": retry.get("usage_boundary", ""),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run direct Neo4j/Qdrant staging sync acceptance.")
    parser.add_argument("base_url", nargs="?", default=DEFAULT_BASE_URL)
    parser.add_argument("--neo4j-url", default="http://127.0.0.1:7474/db/neo4j/tx/commit")
    parser.add_argument("--neo4j-user", default="neo4j")
    parser.add_argument("--neo4j-password", default="localneo4jpassword")
    parser.add_argument("--qdrant-url", default="http://127.0.0.1:6333")
    parser.add_argument("--qdrant-collection", default="ai_quant_staging_acceptance")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--full-output", action="store_true", help="Print complete export and outbox payloads instead of a compact summary.")
    args = parser.parse_args()
    result = run_staging_graph_vector_acceptance(
        base_url=args.base_url,
        neo4j_url=args.neo4j_url,
        neo4j_user=args.neo4j_user,
        neo4j_password=args.neo4j_password,
        qdrant_url=args.qdrant_url,
        qdrant_collection=args.qdrant_collection,
        timeout=args.timeout,
    )
    print(json.dumps(result if args.full_output else summarize_acceptance(result), ensure_ascii=False, indent=2, sort_keys=True))
    if result["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
