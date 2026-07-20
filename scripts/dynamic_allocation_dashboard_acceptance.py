"""Browser acceptance for an already-running dynamic allocation dashboard."""

from __future__ import annotations

import argparse
import base64
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from ui_interaction_acceptance import (
    DevToolsClient,
    _chrome_binary,
    _free_port,
    _http_json,
    _wait_for,
    _wait_for_debugger,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "dynamic-allocation-dashboard-acceptance"
VIEWPORTS = [
    {"name": "desktop", "width": 1440, "height": 1000},
    {"name": "mobile", "width": 390, "height": 844},
]


def run_acceptance(
    dashboard_url: str,
    *,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    chrome_bin: str = "",
    timeout: float = 30.0,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    chrome = _chrome_binary(chrome_bin)
    port = _free_port()
    user_data = Path(tempfile.mkdtemp(prefix="ai-quant-dynamic-dashboard-"))
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
    client: DevToolsClient | None = None
    checks: list[dict[str, Any]] = []
    try:
        _wait_for_debugger(port, timeout=timeout)
        pages = _http_json(f"http://127.0.0.1:{port}/json", timeout=timeout)
        page = next((item for item in pages if item.get("type") == "page"), pages[0])
        client = DevToolsClient(page["webSocketDebuggerUrl"], timeout=timeout)
        client.call("Runtime.enable")
        client.call("Page.enable")
        for viewport in VIEWPORTS:
            client.call(
                "Emulation.setDeviceMetricsOverride",
                {
                    "width": viewport["width"],
                    "height": viewport["height"],
                    "deviceScaleFactor": 1,
                    "mobile": viewport["name"] == "mobile",
                },
            )
            client.call("Page.navigate", {"url": dashboard_url})
            _wait_for(
                client,
                "document.body && document.body.innerText.includes('动态资产配置与风险控制') && document.body.innerText.includes('目标股票仓位')",
                timeout=timeout,
            )
            _wait_for(
                client,
                "document.querySelectorAll('[data-testid=\"stPlotlyChart\"]').length >= 1 && document.querySelectorAll('[data-testid=\"stTable\"]').length >= 1",
                timeout=timeout,
            )
            diagnostics = client.evaluate(
                """
                (() => ({
                  titleVisible: document.body.innerText.includes('动态资产配置与风险控制'),
                  allocationVisible: document.body.innerText.includes('目标股票仓位'),
                  paperOnlyVisible: document.body.innerText.includes('仅研究 / 纸面模拟'),
                  plotlyCount: document.querySelectorAll('[data-testid="stPlotlyChart"]').length,
                  tableCount: document.querySelectorAll('[data-testid="stTable"]').length,
                  exceptionCount: document.querySelectorAll('[data-testid="stException"]').length,
                  horizontalOverflow: document.documentElement.scrollWidth > window.innerWidth + 1,
                  width: window.innerWidth,
                  height: window.innerHeight
                }))()
                """
            )
            screenshot = client.call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
            screenshot_path = output / f"dashboard-{viewport['name']}.png"
            screenshot_path.write_bytes(base64.b64decode(screenshot["data"]))
            passed = bool(
                diagnostics.get("titleVisible")
                and diagnostics.get("allocationVisible")
                and diagnostics.get("paperOnlyVisible")
                and diagnostics.get("plotlyCount", 0) >= 1
                and diagnostics.get("tableCount", 0) >= 1
                and diagnostics.get("exceptionCount") == 0
                and not diagnostics.get("horizontalOverflow")
                and screenshot_path.stat().st_size > 1000
            )
            checks.append(
                {
                    "name": viewport["name"],
                    "status": "passed" if passed else "failed",
                    "diagnostics": diagnostics,
                    "screenshot": str(screenshot_path),
                    "screenshot_bytes": screenshot_path.stat().st_size,
                }
            )
    finally:
        if client:
            client.close()
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
        shutil.rmtree(user_data, ignore_errors=True)

    passed = bool(checks) and all(check["status"] == "passed" for check in checks)
    return {
        "status": "passed" if passed else "failed",
        "dashboard_url": dashboard_url,
        "browser": chrome,
        "checks": checks,
        "evidence_uri": "artifact://dynamic-allocation-dashboard-acceptance",
        "boundary": "local-only",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a running Streamlit dynamic-allocation dashboard")
    parser.add_argument("dashboard_url", nargs="?", default="http://127.0.0.1:8501")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--chrome-bin", default="")
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()
    result = run_acceptance(
        args.dashboard_url,
        output_dir=args.output_dir,
        chrome_bin=args.chrome_bin,
        timeout=args.timeout,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if result["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
