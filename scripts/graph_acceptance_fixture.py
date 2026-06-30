from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "artifacts" / "graph-acceptance-fixture.json"

COMPANIES = [
    {"issuer_id": "issuer_aapl", "security_id": "security_aapl_us", "ticker": "AAPL", "legal_name": "Apple Inc."},
    {"issuer_id": "issuer_nvda", "security_id": "security_nvda_us", "ticker": "NVDA", "legal_name": "NVIDIA Corporation"},
    {"issuer_id": "issuer_600519", "security_id": "sec_600519", "ticker": "600519", "legal_name": "贵州茅台酒股份有限公司", "market": "A", "exchange": "SSE", "currency": "CNY", "country": "CN"},
    {"issuer_id": "issuer_graph_aapl_peer", "security_id": "security_graph_aapl_peer", "ticker": "AAPL-P", "legal_name": "AAPL Graph Peer Co"},
    {"issuer_id": "issuer_graph_aapl_upstream", "security_id": "security_graph_aapl_upstream", "ticker": "AAPL-U", "legal_name": "AAPL Graph Upstream Co"},
    {"issuer_id": "issuer_graph_aapl_downstream", "security_id": "security_graph_aapl_downstream", "ticker": "AAPL-D", "legal_name": "AAPL Graph Downstream Co"},
]

INDUSTRY_CHAIN = {
    "chain_id": "chain_graph_acceptance_aapl",
    "name": "AAPL graph acceptance chain",
    "nodes": [
        {"node_id": "materials", "name": "关键材料", "level": "upstream", "category": "materials"},
        {"node_id": "devices", "name": "端侧设备生态", "level": "midstream", "category": "devices"},
        {"node_id": "services", "name": "服务与应用", "level": "downstream", "category": "services"},
    ],
    "edges": [
        {"source_node_id": "materials", "target_node_id": "devices", "relation_type": "upstream_of", "confidence": 0.8},
        {"source_node_id": "devices", "target_node_id": "services", "relation_type": "downstream_of", "confidence": 0.8},
    ],
    "taxonomy_version": "graph-acceptance-fixture-v1",
    "source_refs": ["local://graph-acceptance-fixture"],
}

COMPANY_POSITIONS = [
    {
        "position_id": "pos_graph_acceptance_aapl_focus",
        "issuer_id": "issuer_aapl",
        "security_id": "security_aapl_us",
        "node_ids": ["devices"],
        "role": "端侧设备生态焦点公司",
        "data_quality": "browser_acceptance_fixture",
    },
    {
        "position_id": "pos_graph_acceptance_aapl_peer",
        "issuer_id": "issuer_graph_aapl_peer",
        "security_id": "security_graph_aapl_peer",
        "node_ids": ["devices"],
        "role": "同类端侧设备生态公司",
        "data_quality": "browser_acceptance_fixture",
    },
    {
        "position_id": "pos_graph_acceptance_aapl_upstream",
        "issuer_id": "issuer_graph_aapl_upstream",
        "security_id": "security_graph_aapl_upstream",
        "node_ids": ["materials"],
        "role": "上游关键材料公司",
        "data_quality": "browser_acceptance_fixture",
    },
    {
        "position_id": "pos_graph_acceptance_aapl_downstream",
        "issuer_id": "issuer_graph_aapl_downstream",
        "security_id": "security_graph_aapl_downstream",
        "node_ids": ["services"],
        "role": "下游服务应用公司",
        "data_quality": "browser_acceptance_fixture",
    },
]

LISTING_RELATIONSHIPS = [
    ("rel_obsidian_listing_aapl", "issuer_aapl", "security_aapl_us"),
    ("rel_obsidian_listing_nvda", "issuer_nvda", "security_nvda_us"),
    ("rel_obsidian_listing_600519", "issuer_600519", "sec_600519"),
]

INSTITUTION_RELATIONSHIPS = [
    ("AAPL", "issuer_aapl", "security_aapl_us", 4),
    ("NVDA", "issuer_nvda", "security_nvda_us", 5),
    ("600519", "issuer_600519", "sec_600519", 3),
]

OWNERSHIP_RELATIONSHIPS = [
    ("rel_graph_acceptance_aapl_alpha_holder", "issuer_aapl", "security_aapl_us"),
    ("rel_graph_acceptance_peer_alpha_holder", "issuer_graph_aapl_peer", "security_graph_aapl_peer"),
]


def post_json(
    base_url: str,
    path: str,
    body: dict[str, Any],
    *,
    role: str = "data_engineer",
    actor: str = "graph_acceptance_fixture",
    timeout: float = 10.0,
) -> dict[str, Any]:
    request = Request(
        f"{base_url.rstrip('/')}{path}",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json", "X-Role": role, "X-Actor": actor},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raw = exc.read().decode("utf-8")
        payload = json.loads(raw) if raw else {"success": False, "error": {"message": str(exc), "status": exc.code}}
        message = str(payload.get("error", {}).get("message", "")).lower()
        if exc.code == 409 or "already exists" in message:
            return {"success": True, "data": {"status": "already_exists", "path": path}}
        raise


def prepare_graph_acceptance_fixture(base_url: str, *, timeout: float = 10.0) -> dict[str, Any]:
    operations: list[dict[str, Any]] = []
    for company in COMPANIES:
        issuer_payload = {
            "issuer_id": company["issuer_id"],
            "legal_name": company["legal_name"],
            "aliases": [company["ticker"]],
            "market": [str(company.get("market", "U"))],
            "country": str(company.get("country", "US")),
            "status": "active",
        }
        issuer_result = post_json(base_url, "/api/issuers", issuer_payload, timeout=timeout)
        operations.append({"type": "issuer", "id": company["issuer_id"], "status": issuer_result.get("data", {}).get("status", "created")})

        security_payload = {
            "security_id": company["security_id"],
            "issuer_id": company["issuer_id"],
            "ticker": company["ticker"],
            "exchange": str(company.get("exchange", "NASDAQ")),
            "currency": str(company.get("currency", "USD")),
            "market": str(company.get("market", "U")),
            "status": "active",
            "company_universe_scope": "out_of_scope",
            "company_universe_reason": "local_graph_acceptance_fixture_only",
        }
        security_result = post_json(base_url, "/api/securities", security_payload, timeout=timeout)
        operations.append({"type": "security", "id": company["security_id"], "status": security_result.get("data", {}).get("status", "created")})

    chain_result = post_json(base_url, "/api/industry-chains", INDUSTRY_CHAIN, timeout=timeout)
    operations.append({"type": "industry_chain", "id": INDUSTRY_CHAIN["chain_id"], "status": chain_result.get("data", {}).get("status", "created")})

    for position in COMPANY_POSITIONS:
        position_result = post_json(base_url, f"/api/industry-chains/{INDUSTRY_CHAIN['chain_id']}/companies", position, timeout=timeout)
        operations.append({"type": "company_position", "id": position["position_id"], "status": position_result.get("data", {}).get("status", "created")})

    for relationship_id, issuer_id, security_id in LISTING_RELATIONSHIPS:
        relationship_result = post_json(
            base_url,
            "/api/company-relationships",
            {
                "relationship_id": relationship_id,
                "issuer_id": issuer_id,
                "security_id": security_id,
                "subject_type": "company",
                "subject_id": issuer_id,
                "object_type": "security",
                "object_id": security_id,
                "relationship_type": "listed_security",
                "relationship_status": "active",
                "review_status": "auto_generated",
                "confidence": 0.95,
                "metadata": {"source_layer": "graph_acceptance_fixture"},
            },
            timeout=timeout,
        )
        operations.append({"type": "company_relationship", "id": relationship_id, "status": relationship_result.get("data", {}).get("status", "created")})

    for symbol, issuer_id, security_id, count in INSTITUTION_RELATIONSHIPS:
        for index in range(1, count + 1):
            relationship_id = f"rel_graph_acceptance_{symbol.lower()}_coverage_{index}"
            institution_id = f"institution_graph_acceptance_{symbol.lower()}_{index}"
            relationship_result = post_json(
                base_url,
                "/api/company-relationships",
                {
                    "relationship_id": relationship_id,
                    "issuer_id": issuer_id,
                    "security_id": security_id,
                    "subject_type": "institution",
                    "subject_id": institution_id,
                    "object_type": "company",
                    "object_id": issuer_id,
                    "relationship_type": "institution_coverage",
                    "relationship_status": "active",
                    "review_status": "needs_review",
                    "confidence": 0.72,
                    "metadata": {"entity_name": f"Graph Acceptance Institution {index}", "source_layer": "graph_acceptance_fixture"},
                },
                timeout=timeout,
            )
            operations.append({"type": "company_relationship", "id": relationship_id, "status": relationship_result.get("data", {}).get("status", "created")})

    for relationship_id, issuer_id, security_id in OWNERSHIP_RELATIONSHIPS:
        relationship_result = post_json(
            base_url,
            "/api/company-relationships",
            {
                "relationship_id": relationship_id,
                "issuer_id": issuer_id,
                "security_id": security_id,
                "subject_type": "company",
                "subject_id": issuer_id,
                "object_type": "company",
                "object_id": "external_graph_acceptance_alpha_capital",
                "relationship_type": "shareholder",
                "relationship_status": "active",
                "review_status": "approved",
                "confidence": 0.86,
                "metadata": {"entity_name": "Graph Acceptance Alpha Capital", "source_layer": "graph_acceptance_fixture"},
            },
            timeout=timeout,
        )
        operations.append({"type": "company_relationship", "id": relationship_id, "status": relationship_result.get("data", {}).get("status", "created")})

    return {
        "status": "prepared",
        "base_url": base_url,
        "operation_count": len(operations),
        "operations": operations,
        "usage_boundary": "local_graph_acceptance_fixture_only_no_broker_no_trade_execution",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare local graph acceptance fixture data through public APIs.")
    parser.add_argument("base_url", nargs="?", default="http://127.0.0.1:8000")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()
    result = prepare_graph_acceptance_fixture(args.base_url, timeout=args.timeout)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
