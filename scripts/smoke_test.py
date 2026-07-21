from __future__ import annotations

import json
import sys
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BASE_URL = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://127.0.0.1:8000"


def request(method: str, path: str, body: dict | None = None, *, role: str = "system", actor: str = "smoke") -> dict:
    data = json.dumps(body or {}).encode("utf-8") if body is not None else None
    req = Request(
        f"{BASE_URL}{path}",
        data=data,
        method=method,
        headers={
            "Content-Type": "application/json",
            "X-Role": role,
            "X-Actor": actor,
            "X-Client-Origin": "acceptance",
        },
    )
    try:
        with urlopen(req, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        payload = json.loads(exc.read().decode("utf-8"))
    if not payload.get("success"):
        raise AssertionError(f"{method} {path} failed: {payload}")
    return payload


def main() -> None:
    health = request("GET", "/api/health", role="unknown")
    assert health["data"]["status"] == "ok"

    ui_req = Request(f"{BASE_URL}/ui", method="GET")
    with urlopen(ui_req, timeout=10) as response:
        html = response.read().decode("utf-8")
    assert response.status == 200
    assert "公司情报与市场综合分析平台" in html

    demo = request("POST", "/api/demo/full-flow", {}, role="platform", actor="platform_smoke")
    assert demo["data"]["decision_id"] == "dec_demo"
    assert demo["data"]["intent_id"] == "intent_demo"

    suffix = str(int(time.time() * 1000))
    simulated = request(
        "POST",
        f"/api/execution-intents/{demo['data']['intent_id']}/simulate",
        {
            "execution_id": f"simexec_smoke_{suffix}",
            "transaction_id": f"ptxn_simexec_smoke_{suffix}",
            "quantity": 10,
            "fill_price": 100.0,
            "account_id": f"smoke_paper_{suffix}",
        },
        role="pm",
        actor="pm_smoke",
    )
    assert simulated["data"]["mode"] == "simulated"
    assert simulated["data"]["live_execution_allowed"] is False
    assert simulated["data"]["transaction"]["source_id"] == "simulated_trade_execution"

    executions = request("GET", f"/api/simulated-executions?account_id=smoke_paper_{suffix}", role="pm", actor="pm_smoke")
    assert executions["data"]["total"] == 1

    metrics = request("GET", "/api/metrics", role="unknown")
    assert metrics["data"]["counts"]["documents"] >= 1
    assert metrics["data"]["audit_events"] >= 1

    query = urlencode({"q": "services resilience", "issuer_id": "issuer_demo", "limit": 5})
    search = request("GET", f"/api/search?{query}", role="ceo", actor="ceo_smoke")
    assert search["data"]["results"], search

    print("smoke ok")


if __name__ == "__main__":
    main()
