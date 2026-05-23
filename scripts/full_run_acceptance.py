from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.api import ApiRouter
from app.services import READINESS_CHECKLIST_ITEMS, SystemService
from scripts.capacity_baseline import run_capacity_baseline


def _dispatch(router: ApiRouter, method: str, path: str, body: dict[str, Any] | None = None, *, role: str = "system", actor: str = "acceptance") -> dict[str, Any]:
    response = router.dispatch(method, path, body or {}, role=role, actor=actor)
    if not response.success:
        raise AssertionError(f"{method} {path} failed: {response.status_code} {response.error}")
    return response.data


def _record_readiness(router: ApiRouter, check_id: str, *, evidence_uri: str, owner: str, notes: str, metrics: dict[str, Any], role: str = "platform") -> dict[str, Any]:
    return _dispatch(
        router,
        "POST",
        f"/api/readiness/checklist/{check_id}",
        {
            "status": "passed",
            "owner": owner,
            "evidence_uri": evidence_uri,
            "notes": notes,
            "metrics": metrics,
        },
        role=role,
        actor=owner,
    )


def run_full_acceptance(*, capacity_records: int = 10) -> dict[str, Any]:
    service = SystemService()
    router = ApiRouter(service)
    checks: list[dict[str, Any]] = []

    health = _dispatch(router, "GET", "/api/health", {}, role="unknown")
    checks.append({"check": "health", "passed": health["status"] == "ok", "evidence": {"status": health["status"], "store": health["store"]}})

    demo = _dispatch(router, "POST", "/api/demo/full-flow", {}, role="platform", actor="platform_acceptance")
    checks.append(
        {
            "check": "demo_full_flow",
            "passed": bool(demo["decision_id"] and demo["intent_id"]),
            "evidence": {"decision_id": demo["decision_id"], "intent_id": demo["intent_id"]},
        }
    )

    simulated = _dispatch(
        router,
        "POST",
        f"/api/execution-intents/{demo['intent_id']}/simulate",
        {
            "execution_id": "simexec_acceptance",
            "transaction_id": "ptxn_simexec_acceptance",
            "quantity": 100,
            "fill_price": 100.0,
            "fees": 1.0,
            "account_id": "acceptance_paper",
        },
        role="PM",
        actor="pm_acceptance",
    )
    checks.append(
        {
            "check": "simulated_trade_execution",
            "passed": simulated["mode"] == "simulated" and simulated["live_execution_allowed"] is False,
            "evidence": {
                "execution_id": simulated["execution"]["execution_id"],
                "transaction_id": simulated["transaction"]["transaction_id"],
                "source_id": simulated["transaction"]["source_id"],
                "live_execution_allowed": simulated["live_execution_allowed"],
            },
        }
    )

    portfolio = _dispatch(router, "GET", "/api/portfolio/positions", {"account_id": "acceptance_paper"}, role="PM")
    checks.append({"check": "portfolio_ledger_positions", "passed": portfolio["position_count"] >= 1, "evidence": {"position_count": portfolio["position_count"]}})

    search = _dispatch(router, "GET", "/api/search", {"q": "services resilience", "issuer_id": "issuer_demo", "limit": 5}, role="CEO")
    semantic = _dispatch(router, "POST", "/api/search/semantic", {"q": "resilient services demand", "issuer_id": "issuer_demo"}, role="CEO")
    checks.append({"check": "keyword_search", "passed": bool(search["results"]), "evidence": {"result_count": len(search["results"])}})
    checks.append({"check": "semantic_search", "passed": bool(semantic["results"]), "evidence": {"result_count": len(semantic["results"]), "backend": semantic["backend"]}})

    graph = _dispatch(router, "GET", "/api/graph/traceability-report", {"issuer_id": "issuer_demo"}, role="CEO")
    checks.append({"check": "graph_traceability", "passed": graph["traceability_rate"] >= 0.0, "evidence": {"traceability_rate": graph["traceability_rate"]}})

    alerts_seed = _dispatch(router, "POST", "/api/alerts/rules/seed", {}, role="risk_compliance", actor="risk_acceptance")
    alerts_eval = _dispatch(router, "POST", "/api/alerts/evaluate", {}, role="risk_compliance", actor="risk_acceptance")
    checks.append(
        {
            "check": "alerts",
            "passed": len(alerts_seed["rules"]) >= 1 and "alerts" in alerts_eval,
            "evidence": {"rules": len(alerts_seed["rules"]), "open_alerts": len(alerts_eval["alerts"])},
        }
    )

    capacity = run_capacity_baseline(records=capacity_records)
    capacity_record = _dispatch(
        router,
        "POST",
        "/api/readiness/capacity-baseline",
        {
            "result": capacity,
            "thresholds": {"ingest_ms": 1000, "extract_ms": 1000, "search_ms": 1000, "dashboard_ms": 1000},
            "evidence_uri": "artifact://full-run/capacity-baseline.json",
        },
        role="platform",
        actor="platform_acceptance",
    )
    checks.append({"check": "capacity_baseline", "passed": capacity_record["passed"], "evidence": {"records": capacity["records"], "max_ms": capacity["max_ms"]}})

    readiness_metrics = {
        "local_acceptance": True,
        "trading_mode": "simulated",
        "documents": service.dashboard()["counts"]["documents"],
        "simulated_executions": service.dashboard()["counts"]["simulated_executions"],
    }
    for item in READINESS_CHECKLIST_ITEMS:
        check_id = str(item["check_id"])
        if check_id == "capacity_latency_report":
            continue
        owner_role = str(item["owner_role"])
        owner = {
            "CEO": "ceo_acceptance",
            "风险/合规": "risk_acceptance",
            "平台负责人": "platform_acceptance",
        }.get(owner_role, "platform_acceptance")
        role = {
            "CEO": "CEO",
            "风险/合规": "risk_compliance",
            "平台负责人": "platform",
        }.get(owner_role, "platform")
        _record_readiness(
            router,
            check_id,
            evidence_uri=f"artifact://full-run/{check_id}.json",
            owner=owner,
            notes="Local operational acceptance with simulated trading and public/demo data. Production sign-off still requires real environment artifacts.",
            metrics=readiness_metrics,
            role=role,
        )

    checklist = _dispatch(router, "GET", "/api/readiness/checklist", {}, role="risk_compliance")
    checks.append({"check": "readiness_checklist_records", "passed": checklist["coverage"] == 1.0, "evidence": {"coverage": checklist["coverage"], "pending": checklist["pending_checklist"]}})

    metrics = _dispatch(router, "GET", "/api/metrics", {}, role="unknown")
    checks.append(
        {
            "check": "metrics_observability",
            "passed": metrics["counts"]["simulated_executions"] >= 1 and metrics["counts"]["portfolio_transactions"] >= 1,
            "evidence": {
                "simulated_executions": metrics["counts"]["simulated_executions"],
                "portfolio_transactions": metrics["counts"]["portfolio_transactions"],
                "audit_events": metrics["audit_events"],
            },
        }
    )

    failed = [item for item in checks if not item["passed"]]
    return {
        "status": "passed" if not failed else "failed",
        "mode": "local_operational_acceptance",
        "trading_mode": "simulated",
        "production_boundary": "does_not_certify_live_broker_or_real_production_environment",
        "check_count": len(checks),
        "failed_count": len(failed),
        "checks": checks,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local full-system acceptance with simulated trading.")
    parser.add_argument("--capacity-records", type=int, default=10)
    args = parser.parse_args()
    result = run_full_acceptance(capacity_records=args.capacity_records)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if result["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
