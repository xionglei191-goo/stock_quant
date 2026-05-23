from __future__ import annotations

import argparse
import json
from pathlib import Path
import time
from typing import Any, Callable
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class LocalApiClient:
    def __init__(self, base_url: str, *, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        *,
        role: str = "platform",
        actor: str = "local_business_acceptance",
    ) -> dict[str, Any]:
        data = json.dumps(body or {}).encode("utf-8") if body is not None else None
        request = Request(
            f"{self.base_url}{path}",
            data=data,
            method=method,
            headers={"Content-Type": "application/json", "X-Role": role, "X-Actor": actor},
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raw = exc.read().decode("utf-8")
            payload = json.loads(raw) if raw else {"success": False, "error": {"message": str(exc)}}
        if not payload.get("success"):
            raise AssertionError(f"{method} {path} failed: {payload}")
        return payload["data"]


def _step(checks: list[dict[str, Any]], name: str, fn: Callable[[], dict[str, Any]], required: Callable[[dict[str, Any]], bool]) -> dict[str, Any] | None:
    started = time.perf_counter()
    try:
        evidence = fn()
        passed = bool(required(evidence))
        checks.append({"check": name, "passed": passed, "elapsed_ms": round((time.perf_counter() - started) * 1000, 3), "evidence": evidence, "error": ""})
        return evidence
    except Exception as exc:
        checks.append({"check": name, "passed": False, "elapsed_ms": round((time.perf_counter() - started) * 1000, 3), "evidence": {}, "error": str(exc)})
        return None


def run_local_business_acceptance(base_url: str, *, timeout: float = 30.0, research_root: str = "/data/local/research_reports") -> dict[str, Any]:
    client = LocalApiClient(base_url, timeout=timeout)
    suffix = str(int(time.time() * 1000))
    checks: list[dict[str, Any]] = []

    health = _step(
        checks,
        "runtime_backends",
        lambda: client.request("GET", "/api/health", role="unknown"),
        lambda data: data["status"] == "ok"
        and data["store"] == "PostgreSQLStore"
        and data["object_store"]["backend"] == "s3"
        and data["search_index"]["backend"] == "opensearch"
        and data["tdx_market_data"]["configured"],
    )

    _step(
        checks,
        "tdx_full_market_data_api",
        lambda: {
            "latest": client.request(
                "GET",
                "/api/market-data?" + urlencode({"security_id": "sec_600000", "source_id": "public_eod_market_data", "data_type": "eod", "limit": 3}),
                role="data_engineer",
            ),
            "returns": client.request(
                "GET",
                "/api/market-data/returns?"
                + urlencode(
                    {
                        "security_id": "sec_600000",
                        "source_id": "public_eod_market_data",
                        "data_type": "eod",
                        "start_date": "2026-05-01",
                        "end_date": "2026-05-15",
                        "limit": 20,
                    }
                ),
                role="data_engineer",
            ),
            "quality": client.request(
                "GET",
                "/api/market-data/quality-report?"
                + urlencode({"security_id": "sec_600000", "source_id": "public_eod_market_data", "data_type": "eod", "sample_limit": 1000}),
                role="data_engineer",
            ),
        },
        lambda data: len(data["latest"]["market_data"]) == 3 and data["returns"]["return_count"] > 0 and data["quality"]["total_points"] >= 6000,
    )

    demo = _step(
        checks,
        "demo_research_execution_seed",
        lambda: client.request("POST", "/api/demo/full-flow", {}, role="platform"),
        lambda data: bool(data.get("issuer_id")) and bool(data.get("intent_id")),
    )

    _step(
        checks,
        "portfolio_valuation_and_optimizer",
        lambda: {
            "valuation": client.request(
                "POST",
                "/api/portfolio/valuation",
                {
                    "as_of_date": "2026-05-15",
                    "cash": 100000.0,
                    "currency": "CNY",
                    "holdings": [{"security_id": "sec_600000", "shares": 1000}, {"security_id": "sec_000001", "shares": 800}],
                    "groups": {
                        "sec_600000": {"industry": "bank", "style": "value"},
                        "sec_000001": {"industry": "bank", "style": "quality"},
                    },
                },
                role="CIO",
            ),
            "optimizer": client.request(
                "POST",
                "/api/portfolio/optimize",
                {
                    "proposal_id": f"pfp_business_{suffix}",
                    "risk_aversion": 2.5,
                    "tau": 0.05,
                    "securities": [
                        {"security_id": "sec_600000", "market_weight": 0.5, "volatility": 0.22, "market": "A", "industry": "bank"},
                        {"security_id": "sec_000001", "market_weight": 0.5, "volatility": 0.24, "market": "A", "industry": "bank"},
                    ],
                    "views": [{"security_id": "sec_600000", "expected_return": 0.06, "confidence": 0.7}],
                    "constraints": {"max_weight": 0.7, "market_budget": {"A": 1.0}},
                    "return_history": {"sec_600000": [0.01, -0.005, 0.003], "sec_000001": [0.008, -0.004, 0.002]},
                },
                role="CIO",
            ),
        },
        lambda data: data["valuation"]["missing_price_count"] == 0 and data["valuation"]["total_market_value"] > 0 and data["optimizer"]["constraints"]["paper_only"],
    )

    _step(
        checks,
        "research_report_scan",
        lambda: client.request("POST", "/api/research-reports/scan", {"root_path": research_root, "extensions": [".pdf", ".txt", ".md"], "limit": 20}, role="data_engineer"),
        lambda data: data.get("indexed_count", 0) > 0 or data.get("total_files", 0) > 0,
    )

    _step(
        checks,
        "entity_mapping_13f_crowding",
        lambda: {
            "mapping": client.request(
                "POST",
                "/api/entity-mappings/batch",
                {
                    "batch_id": f"map_business_{suffix}",
                    "items": [
                        {"mapping_id": f"map_business_600000_{suffix}", "issuer_id": "issuer_600000", "ticker": "600000", "market": "A", "confidence": 0.95},
                        {"mapping_id": f"map_business_000001_{suffix}", "issuer_id": "issuer_000001", "ticker": "000001", "market": "A", "confidence": 0.95},
                    ],
                },
                role="platform",
            ),
            "holding_prev": client.request(
                "POST",
                "/api/13f/holdings",
                {
                    "holding_id": f"hold_business_prev_{suffix}",
                    "issuer_id": "issuer_demo",
                    "security_id": "security_demo_us",
                    "source_id": "sec_edgar",
                    "filer_cik": "0001000001",
                    "filer_name": "Business Acceptance Fund",
                    "report_period": "2025-12-31",
                    "shares": 100,
                    "value_usd": 10000,
                },
                role="data_engineer",
            ),
            "holding_now": client.request(
                "POST",
                "/api/13f/holdings",
                {
                    "holding_id": f"hold_business_now_{suffix}",
                    "issuer_id": "issuer_demo",
                    "security_id": "security_demo_us",
                    "source_id": "sec_edgar",
                    "filer_cik": "0001000001",
                    "filer_name": "Business Acceptance Fund",
                    "report_period": "2026-03-31",
                    "shares": 150,
                    "value_usd": 16000,
                },
                role="data_engineer",
            ),
            "changes": client.request("GET", "/api/13f/holdings/changes?" + urlencode({"issuer_id": "issuer_demo", "report_period": "2026-03-31"}), role="CEO"),
            "crowding": client.request(
                "POST",
                "/api/13f/crowding/update",
                {"snapshot_id": f"crd_business_{suffix}", "issuer_id": "issuer_demo", "report_period": "2026-03-31"},
                role="CIO",
            ),
        },
        lambda data: data["mapping"]["created_count"] >= 2 and len(data["changes"].get("changes", [])) >= 1 and data["crowding"]["score"] >= 0,
    )

    _step(
        checks,
        "hotspot_graph_search",
        lambda: {
            "hotspot": client.request("POST", "/api/hotspots/expand", {"query": "GPU", "seed_chain_id": "chain_demo_electronics", "max_depth": 2}, role="analyst"),
            "graph": client.request("GET", "/api/graph/query?" + urlencode({"chain_id": "chain_demo_electronics"}), role="analyst"),
            "semantic": client.request("POST", "/api/search/semantic", {"q": "resilient services demand", "issuer_id": "issuer_demo"}, role="CEO"),
        },
        lambda data: data["hotspot"]["ranked_candidates"]["candidate_count"] >= 1 and bool(data["graph"]["chain_nodes"]) and bool(data["semantic"]["results"]),
    )

    _step(
        checks,
        "orchestration_observability_readiness",
        lambda: {
            "dag": client.request(
                "POST",
                "/api/orchestration/dags",
                {
                    "dag_id": f"dag_business_{suffix}",
                    "name": "Local business acceptance",
                    "cadence": "manual",
                    "tasks": [{"task_id": "collect", "owner": "platform", "sla_minutes": 10}],
                },
                role="platform",
            ),
            "run": client.request("POST", f"/api/orchestration/dags/dag_business_{suffix}/run", {"run_id": f"wfrun_business_{suffix}"}, role="platform"),
            "observability": client.request("GET", "/api/observability/readiness-report", role="platform"),
            "storage": client.request("GET", "/api/governance/storage-readiness-report", role="platform"),
            "security": client.request("GET", "/api/governance/security-readiness-report", role="risk_compliance"),
            "graph_vector": client.request("GET", "/api/graph-vector/readiness-report", role="platform"),
        },
        lambda data: data["run"]["status"] == "succeeded" and all(isinstance(data[key], dict) for key in ["observability", "storage", "security", "graph_vector"]),
    )

    _step(
        checks,
        "metrics_and_readiness_package",
        lambda: {
            "metrics": client.request("GET", "/api/metrics", role="unknown"),
            "package": client.request("POST", "/api/readiness/evidence-package", {"record_export": True}, role="CEO"),
        },
        lambda data: data["metrics"]["counts"]["issuers"] > 0 and data["package"].get("ready_for_launch") is True,
    )

    failed = [item for item in checks if not item["passed"]]
    return {
        "status": "passed" if not failed else "failed",
        "mode": "local_business_acceptance",
        "base_url": base_url,
        "trading_mode": "simulated_only",
        "production_boundary": "no_live_broker_no_automatic_order_execution",
        "health": health,
        "check_count": len(checks),
        "failed_count": len(failed),
        "checks": checks,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local HTTP business acceptance across the main product modules.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--research-root", default="/data/local/research_reports")
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    result = run_local_business_acceptance(args.base_url, timeout=args.timeout, research_root=args.research_root)
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    if result["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
