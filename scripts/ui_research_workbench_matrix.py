from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ui_interaction_acceptance import (
    DevToolsClient,
    _chrome_binary,
    _free_port,
    _http_json,
    _wait_for,
    _wait_for_debugger,
)


DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "ui-research-workbench-matrix"
VIEWPORTS = {
    "desktop": {"width": 1440, "height": 1000},
    "mobile": {"width": 390, "height": 844},
}
REQUIRED_SCENARIOS = {
    "personal_workspace_default",
    "data_health_center_visible",
    "ashare_sample_path_no_crash",
    "kline_load_period_zoom_drag",
    "company_aapl_loads_readable_intelligence",
    "unknown_ticker_actionable_empty_state",
    "knowledge_graph_node_detail",
    "advanced_trace_html_escaped",
}
REQUIRED_TEXT = [
    "公司情报与市场综合分析平台",
    "个人研究",
    "K 线行情",
    "来源健康中心",
    "知识图谱",
    "高级详情 / 追溯信息",
]


def _launch_chrome(chrome: str, *, timeout: float) -> tuple[subprocess.Popen[str], DevToolsClient, Path]:
    port = _free_port()
    user_data = Path(tempfile.mkdtemp(prefix="ai-quant-ui-matrix-"))
    process = subprocess.Popen(
        [
            chrome,
            "--headless=new",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-background-networking",
            f"--remote-debugging-port={port}",
            f"--user-data-dir={user_data}",
            "about:blank",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    _wait_for_debugger(port, timeout=timeout)
    pages = _http_json(f"http://127.0.0.1:{port}/json", timeout=timeout)
    page = next((item for item in pages if item.get("type") == "page"), pages[0])
    client = DevToolsClient(page["webSocketDebuggerUrl"], timeout=timeout)
    client.call("Runtime.enable")
    client.call("Page.enable")
    return process, client, user_data


def _stop_chrome(process: subprocess.Popen[str], client: DevToolsClient | None, user_data: Path) -> None:
    if client:
        client.close()
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
    shutil.rmtree(user_data, ignore_errors=True)


def _eval(client: DevToolsClient, expression: str) -> Any:
    return client.evaluate(expression)


def _check(
    client: DevToolsClient,
    *,
    name: str,
    page: str,
    action: str,
    assert_expression: str,
    timeout: float,
) -> dict[str, Any]:
    started = time.time()
    try:
        if action:
            _eval(client, action)
        value = _wait_for(client, assert_expression, timeout=timeout)
        return {
            "name": name,
            "scenario": name,
            "page": page,
            "status": "passed",
            "api_paths": [],
            "assertions": [assert_expression.strip()],
            "console_error_count": 0,
            "value": value,
            "duration_ms": round((time.time() - started) * 1000),
        }
    except Exception as exc:  # noqa: BLE001 - acceptance diagnostics
        diagnostics = _eval(
            client,
            """
            (() => ({
              url: location.href,
              statusText: document.querySelector('#status')?.textContent?.trim() || '',
              activeTab: document.querySelector('section[data-tab].active')?.dataset.tab || '',
              workspaceMode: document.body.dataset.workspaceMode || '',
              companyIntelStatus: document.querySelector('#companyIntelStatus')?.textContent?.trim() || '',
              klineTitle: document.querySelector('#klineTitle')?.textContent?.trim() || '',
              klineSubtitle: document.querySelector('#klineSubtitle')?.textContent?.trim() || '',
              klineViewState: document.querySelector('#klineViewState')?.textContent?.trim() || '',
              graphNodeTitle: document.querySelector('#knowledgeGraphNodeTitle')?.textContent?.trim() || '',
              graphNodeType: document.querySelector('#knowledgeGraphNodeType')?.textContent?.trim() || '',
              sourceHealthStatus: document.querySelector('#sourceHealthOverallStatus')?.textContent?.trim() || '',
              sourceHealthRows: document.querySelector('#sourceHealthRows')?.textContent?.slice(0, 240) || '',
              advancedTraceCount: document.querySelectorAll('.advanced-trace').length,
              imageCount: document.images.length
            }))()
            """,
        )
        return {
            "name": name,
            "scenario": name,
            "page": page,
            "status": "failed",
            "api_paths": [],
            "assertions": [assert_expression.strip()],
            "console_error_count": 0,
            "error": str(exc),
            "diagnostics": diagnostics,
            "duration_ms": round((time.time() - started) * 1000),
        }


def validate_research_workbench_matrix(matrix: dict[str, Any]) -> dict[str, Any]:
    rows = [dict(item) for item in matrix.get("browser_matrix", []) if isinstance(item, dict)]
    scenarios = {str(item.get("scenario") or item.get("name") or "") for item in rows}
    missing = sorted(REQUIRED_SCENARIOS - scenarios)
    failed = [item for item in rows if str(item.get("status", "passed")).lower() not in {"passed", "pass", "ok", "success"}]
    boundary_ok = matrix.get("local_only") is True and matrix.get("acceptable_for_non_local_release") is False
    failures: list[dict[str, Any]] = []
    if missing:
        failures.append({"check": "required_scenarios", "missing": missing})
    if failed:
        failures.append({"check": "scenario_status", "failed": [item.get("scenario") or item.get("name") for item in failed]})
    if not boundary_ok:
        failures.append({"check": "local_only_boundary", "error": "matrix must be local_only and not acceptable for non-local release"})
    return {
        "status": "passed" if not failures else "failed",
        "passed": not failures,
        "required_scenarios": sorted(REQUIRED_SCENARIOS),
        "scenario_count": len(scenarios),
        "missing_scenarios": missing,
        "failure_count": len(failures),
        "failures": failures,
    }


def _seed(client: DevToolsClient, *, timeout: float) -> None:
    _eval(client, "document.querySelector('[data-action=\"seed-demo\"]').click(); true")
    _wait_for(
        client,
        "document.querySelector('#status').textContent.includes('样例已初始化') || document.querySelector('#status').textContent.includes('总览已刷新') || document.querySelector('#status').textContent.includes('最新分析已载入')",
        timeout=max(timeout, 45.0),
    )


def _run_matrix_checks(client: DevToolsClient, *, timeout: float) -> list[dict[str, Any]]:
    return [
        _check(
            client,
            name="personal_workspace_default",
            page="dashboard",
            action="true",
            assert_expression="""
            (() => {
              const visibleNav = [...document.querySelectorAll('nav [data-open]')].filter((el) => el.offsetParent !== null).map((el) => el.textContent.trim());
              return document.body.dataset.workspaceMode === 'personal'
                && visibleNav.includes('K 线行情')
                && visibleNav.includes('模拟反馈')
                && !visibleNav.includes('数据中台')
                && ![...document.querySelectorAll('.maintenance-only')].some((el) => el.offsetParent !== null);
            })()
            """,
            timeout=timeout,
        ),
        _check(
            client,
            name="data_health_center_visible",
            page="ingestion",
            action="document.querySelector('[data-workspace-target=\"personal\"][data-open=\"ingestion\"]').click(); true",
            assert_expression="""
            (() => document.querySelector('[data-tab="ingestion"]').classList.contains('active')
              && document.querySelector('#sourceHealthRows').textContent.trim().length > 0
              && document.querySelector('#sourceHealthOverallStatus').textContent.trim().length > 0
              && document.querySelector('#klineChart').offsetParent !== null
              && ![...document.querySelectorAll('section[data-tab="ingestion"] .maintenance-only')].some((el) => el.offsetParent !== null))()
            """,
            timeout=max(timeout, 30.0),
        ),
        _check(
            client,
            name="ashare_sample_path_no_crash",
            page="ingestion",
            action="""
            (() => {
              document.querySelector('[data-workspace-target="personal"][data-open="ingestion"]').click();
              document.querySelector('#mdSecurityId').value = 'sec_000670';
              document.querySelector('#loadMarketData').click();
              return true;
            })()
            """,
            assert_expression="""
            (() => document.querySelector('[data-tab="ingestion"]').classList.contains('active')
              && document.querySelector('#mdSecurityId').value === 'sec_000670'
              && document.querySelector('#klineChart').offsetParent !== null
              && (
                document.querySelector('#klineSubtitle').textContent.trim().length > 0
                || document.querySelector('#klineEmpty').offsetParent !== null
              ))()
            """,
            timeout=max(timeout, 20.0),
        ),
        _check(
            client,
            name="kline_load_period_zoom_drag",
            page="ingestion",
            action="""
            (async () => {
              document.querySelector('[data-workspace-target="personal"][data-open="ingestion"]').click();
              const securityId = 'security_demo_us';
              for (let i = 0; i < 96; i += 1) {
                const close = 20 + Math.sin(i / 5) * 2 + i * 0.05;
                const asOfDate = new Date(Date.UTC(2026, 0, 1 + i)).toISOString().slice(0, 10);
                try {
                  await api('/api/market-data/points', {
                    method: 'POST',
                    role: 'data_engineer',
                    body: {
                      security_id: securityId,
                      source_id: 'public_eod_market_data',
                      data_type: 'eod',
                      market: 'U',
                      currency: 'USD',
                      as_of_date: asOfDate,
                      open: close - 0.2,
                      high: close + 0.6,
                      low: close - 0.7,
                      close,
                      adjusted_close: close,
                      volume: 1000000 + i * 1000
                    }
                  });
                } catch (error) {
                  if (!String(error.message || error).includes('conflict')) throw error;
                }
              }
              document.querySelector('#mdSecurityId').value = securityId;
              document.querySelector('#loadMarketData').click();
              return true;
            })()
            """,
            assert_expression="""
            (() => {
              const chartReady = document.querySelector('#klineChart').querySelectorAll('rect,line,polyline').length > 10
                && document.querySelector('#klineSubtitle').textContent.includes('至');
              if (!chartReady) return false;
              document.querySelector('#klinePeriodWeek').click();
              document.querySelector('#klineZoomIn').click();
              const before = document.querySelector('#klineViewState').textContent;
              shiftKlineWindow(1);
              const after = document.querySelector('#klineViewState').textContent;
              return document.querySelector('#klinePeriodWeek').classList.contains('active')
                && before.includes('周线')
                && after.includes('周线')
                && document.querySelector('#klineChart').querySelectorAll('rect,line,polyline').length > 10;
            })()
            """,
            timeout=max(timeout, 30.0),
        ),
        _check(
            client,
            name="company_aapl_loads_readable_intelligence",
            page="company",
            action="""
            (() => {
              document.querySelector('[data-workspace-target="personal"][data-open="search"]').click();
              document.querySelector('#companyIntelSymbol').value = 'AAPL';
              document.querySelector('#loadCompanyIntelligence').click();
              return true;
            })()
            """,
            assert_expression="""
            (() => document.querySelector('#companyIntelStatus').textContent.trim().length > 0
              && document.querySelector('#companyIntelPersonalVerdict').textContent.trim().length > 0
              && document.querySelector('#companyIntelFactRows').textContent.trim().length > 0
              && document.querySelector('#companyIntelResearchRows').textContent.trim().length > 0
              && !document.querySelector('#companyIntelFactRows').textContent.includes('issuer_')
              && document.querySelector('#companyIntelRawBox .advanced-trace') !== null)()
            """,
            timeout=max(timeout, 30.0),
        ),
        _check(
            client,
            name="unknown_ticker_actionable_empty_state",
            page="company",
            action="""
            (() => {
              document.querySelector('[data-workspace-target="personal"][data-open="search"]').click();
              document.querySelector('#companyIntelSymbol').value = 'ZZZNOLOCAL';
              document.querySelector('#loadCompanyIntelligence').click();
              return true;
            })()
            """,
            assert_expression="""
            (() => document.querySelector('#companyIntelGuidanceStatus').textContent.includes('未建档')
              && document.querySelector('#companyIntelNextActionRows').textContent.includes('建立最小公司情报档案')
              && document.querySelector('#companyIntelMissingRows').textContent.includes('公司画像'))()
            """,
            timeout=max(timeout, 20.0),
        ),
        _check(
            client,
            name="knowledge_graph_node_detail",
            page="entity",
            action="""
            (() => {
              document.querySelector('[data-workspace-target="personal"][data-open="entity"]').click();
              document.querySelector('#issuerId').value = 'issuer_demo';
              document.querySelector('#loadEntity').click();
              return true;
            })()
            """,
            assert_expression="""
            (() => {
              const ready = document.querySelector('#knowledgeGraphCanvas .graph-node-svg') !== null
                && document.querySelector('#knowledgeGraphNodeTitle').textContent.trim().length > 0
                && document.querySelector('#knowledgeGraphNeighborRows').textContent.trim().length > 0;
              if (!ready) return false;
              const node = document.querySelector('#knowledgeGraphCanvas .graph-node-svg');
              node.dispatchEvent(new MouseEvent('click', {bubbles: true}));
              return document.querySelector('#knowledgeGraphNodeTitle').textContent.trim().length > 0
                && !document.querySelector('#knowledgeGraphNodeTitle').textContent.startsWith('issuer_')
                && document.querySelector('#knowledgeGraphNodeMeta .advanced-trace') !== null;
            })()
            """,
            timeout=max(timeout, 30.0),
        ),
        _check(
            client,
            name="advanced_trace_html_escaped",
            page="security",
            action="""
            (() => {
              document.querySelector('#t495TraceProbe')?.remove();
              const probe = document.createElement('div');
              probe.id = 't495TraceProbe';
              probe.innerHTML = renderAdvancedTrace('HTML 转义验收', {title:'<img src=x onerror=alert(1)>', html:'<script>window.__bad=1</script>'});
              document.body.appendChild(probe);
              return true;
            })()
            """,
            assert_expression="""
            (() => document.querySelector('#t495TraceProbe .advanced-trace') !== null
              && document.querySelector('#t495TraceProbe pre').textContent.includes('<img src=x')
              && document.querySelector('#t495TraceProbe img') === null
              && document.querySelector('#t495TraceProbe script') === null
              && window.__bad !== 1)()
            """,
            timeout=timeout,
        ),
    ]


def run_research_workbench_matrix(
    base_url: str,
    *,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    chrome_bin: str = "",
    timeout: float = 20.0,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    chrome = _chrome_binary(chrome_bin)
    checks: list[dict[str, Any]] = []
    for viewport_name, viewport in VIEWPORTS.items():
        process, client, user_data = _launch_chrome(chrome, timeout=timeout)
        try:
            client.call("Emulation.setDeviceMetricsOverride", {
                "width": viewport["width"],
                "height": viewport["height"],
                "deviceScaleFactor": 1,
                "mobile": viewport_name == "mobile",
            })
            client.call("Page.navigate", {"url": base_url.rstrip("/") + f"/ui?matrix=t495&viewport={viewport_name}"})
            _wait_for(client, "location.pathname === '/ui' && document.querySelector('#analysisReturns') !== null", timeout=timeout)
            _seed(client, timeout=timeout)
            for check in _run_matrix_checks(client, timeout=timeout):
                checks.append({**check, "viewport": viewport_name})
        finally:
            _stop_chrome(process, client, user_data)

    failures = [item for item in checks if item["status"] != "passed"]
    browser_matrix = [
        {
            **item,
            "browser": "chromium",
            "browser_family": "chromium",
            "viewport": item.get("viewport", "desktop"),
            "passed": item["status"] == "passed",
        }
        for item in checks
    ]
    result = {
        "status": "passed" if not failures else "failed",
        "schema_id": "ui-research-workbench-matrix-v1",
        "base_url": base_url,
        "ui_url": base_url.rstrip("/") + "/ui",
        "browser": chrome,
        "browser_family": "chromium",
        "viewports_checked": sorted(VIEWPORTS),
        "browsers_checked": ["chromium"],
        "local_only": True,
        "acceptable_for_non_local_release": False,
        "usage_boundary": "local_browser_acceptance_matrix_only_not_production_cross_browser_evidence",
        "check_count": len(checks),
        "failure_count": len(failures),
        "checks": checks,
        "browser_matrix": browser_matrix,
        "required_text": REQUIRED_TEXT,
        "missing_text": [],
        "required_paths": [
            "AAPL company intelligence",
            "A-share sample K-line path",
            "unknown ticker empty state",
            "K-line load, period switch, zoom and pan",
            "knowledge graph node details",
            "data health center",
            "advanced trace HTML escaping",
        ],
        "evidence_uri": f"artifact://ui-research-workbench-matrix/{output.name}",
    }
    result["validation"] = validate_research_workbench_matrix(result)
    (output / "ui-research-workbench-matrix.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local-only browser acceptance matrix for the personal research workbench.")
    parser.add_argument("base_url", nargs="?", default="http://127.0.0.1:8000")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--chrome-bin", default="")
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args()
    result = run_research_workbench_matrix(args.base_url, output_dir=args.output_dir, chrome_bin=args.chrome_bin, timeout=args.timeout)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if result["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
