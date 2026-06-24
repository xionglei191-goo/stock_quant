from __future__ import annotations

import argparse
import base64
import json
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "ui-interaction-acceptance"


def _chrome_binary(explicit: str = "") -> str:
    candidates = [explicit] if explicit else []
    candidates.extend(["google-chrome", "chromium", "chromium-browser"])
    for candidate in candidates:
        if not candidate:
            continue
        found = shutil.which(candidate)
        if found:
            return found
    raise RuntimeError("Chrome/Chromium executable not found")


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _http_json(url: str, *, timeout: float = 5.0) -> Any:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _wait_for_debugger(port: int, *, timeout: float) -> None:
    deadline = time.time() + timeout
    last_error = ""
    while time.time() < deadline:
        try:
            _http_json(f"http://127.0.0.1:{port}/json/version", timeout=1.0)
            return
        except Exception as exc:  # noqa: BLE001 - diagnostic only
            last_error = str(exc)
            time.sleep(0.1)
    raise RuntimeError(f"Chrome debugger did not start: {last_error}")


def _websocket_accept(key: str) -> str:
    import hashlib

    magic = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
    digest = hashlib.sha1((key + magic).encode("ascii")).digest()
    return base64.b64encode(digest).decode("ascii")


class DevToolsClient:
    def __init__(self, websocket_url: str, *, timeout: float = 5.0) -> None:
        parsed = urllib.parse.urlparse(websocket_url)
        self.host = parsed.hostname or "127.0.0.1"
        self.port = int(parsed.port or 80)
        self.path = parsed.path
        if parsed.query:
            self.path += "?" + parsed.query
        self.timeout = timeout
        self.sock = socket.create_connection((self.host, self.port), timeout=timeout)
        self.sock.settimeout(timeout)
        key = base64.b64encode(str(time.time()).encode("ascii")).decode("ascii")
        request = (
            f"GET {self.path} HTTP/1.1\r\n"
            f"Host: {self.host}:{self.port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(request.encode("ascii"))
        response = self.sock.recv(4096).decode("latin1", errors="replace")
        if " 101 " not in response or _websocket_accept(key) not in response:
            raise RuntimeError(f"WebSocket handshake failed: {response[:200]}")
        self._next_id = 0

    def close(self) -> None:
        self.sock.close()

    def _send_frame(self, payload: bytes) -> None:
        header = bytearray([0x81])
        length = len(payload)
        mask_bit = 0x80
        if length < 126:
            header.append(mask_bit | length)
        elif length < 65536:
            header.extend([mask_bit | 126, (length >> 8) & 0xFF, length & 0xFF])
        else:
            header.append(mask_bit | 127)
            header.extend(length.to_bytes(8, "big"))
        mask = b"\x11\x22\x33\x44"
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        self.sock.sendall(bytes(header) + mask + masked)

    def _recv_frame(self) -> dict[str, Any]:
        first = self.sock.recv(2)
        if len(first) < 2:
            raise RuntimeError("short websocket frame")
        opcode = first[0] & 0x0F
        length = first[1] & 0x7F
        if length == 126:
            length = int.from_bytes(self.sock.recv(2), "big")
        elif length == 127:
            length = int.from_bytes(self.sock.recv(8), "big")
        masked = bool(first[1] & 0x80)
        mask = self.sock.recv(4) if masked else b""
        payload = b""
        while len(payload) < length:
            payload += self.sock.recv(length - len(payload))
        if masked:
            payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        if opcode == 8:
            raise RuntimeError("websocket closed")
        if opcode not in {1, 2}:
            return {}
        return json.loads(payload.decode("utf-8"))

    def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self._next_id += 1
        message_id = self._next_id
        self._send_frame(json.dumps({"id": message_id, "method": method, "params": params or {}}).encode("utf-8"))
        deadline = time.time() + self.timeout
        while time.time() < deadline:
            frame = self._recv_frame()
            if frame.get("id") == message_id:
                if "error" in frame:
                    raise RuntimeError(f"{method} failed: {frame['error']}")
                return frame.get("result", {})
        raise TimeoutError(f"timeout waiting for {method}")

    def evaluate(self, expression: str, *, await_promise: bool = True) -> Any:
        result = self.call(
            "Runtime.evaluate",
            {
                "expression": expression,
                "awaitPromise": await_promise,
                "returnByValue": True,
                "userGesture": True,
            },
        )
        remote = result.get("result", {})
        if "exceptionDetails" in result:
            raise RuntimeError(str(result["exceptionDetails"]))
        return remote.get("value")


def _wait_for(client: DevToolsClient, expression: str, *, timeout: float = 10.0) -> Any:
    deadline = time.time() + timeout
    last_value: Any = None
    while time.time() < deadline:
        last_value = client.evaluate(expression)
        if last_value:
            return last_value
        time.sleep(0.2)
    raise TimeoutError(f"condition did not become true: {expression}; last={last_value!r}")


def _run_check(
    client: DevToolsClient,
    name: str,
    click_expression: str,
    assert_expression: str,
    *,
    wait_timeout: float = 12.0,
) -> dict[str, Any]:
    started = time.time()
    try:
        client.evaluate(click_expression)
        value = _wait_for(client, assert_expression, timeout=wait_timeout)
        return {"name": name, "status": "passed", "value": value, "duration_ms": round((time.time() - started) * 1000)}
    except Exception as exc:  # noqa: BLE001 - acceptance diagnostics
        return {"name": name, "status": "failed", "error": str(exc), "duration_ms": round((time.time() - started) * 1000)}


def run_ui_interaction_acceptance(
    base_url: str,
    *,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    chrome_bin: str = "",
    timeout: float = 20.0,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    chrome = _chrome_binary(chrome_bin)
    port = _free_port()
    user_data = output / "chrome-profile"
    user_data.mkdir(parents=True, exist_ok=True)
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
    try:
        _wait_for_debugger(port, timeout=timeout)
        pages = _http_json(f"http://127.0.0.1:{port}/json", timeout=timeout)
        page = next((item for item in pages if item.get("type") == "page"), pages[0])
        client = DevToolsClient(page["webSocketDebuggerUrl"], timeout=timeout)
        client.call("Runtime.enable")
        client.call("Page.enable")
        client.call("Page.navigate", {"url": base_url.rstrip("/") + "/ui"})
        _wait_for(client, "location.pathname === '/ui' && document.querySelector('#analysisReturns') !== null", timeout=timeout)
        client.evaluate("document.querySelector('[data-action=\"seed-demo\"]').click(); true")
        _wait_for(
            client,
            "document.querySelector('#status').textContent.includes('样例已初始化') || document.querySelector('#status').textContent.includes('总览已刷新') || document.querySelector('#status').textContent.includes('最新分析已载入')",
            timeout=max(timeout, 45.0),
        )
        _wait_for(
            client,
            "document.querySelector('#decisionHeadline') && document.querySelector('#decisionHeadline').textContent.trim().length > 0 && document.querySelector('#decisionRecommendationRows').textContent.trim().length > 0",
            timeout=max(timeout, 45.0),
        )
        _wait_for(client, "document.querySelectorAll('[data-action=\"open-security\"]').length > 0", timeout=max(timeout, 45.0))

        checks = [
            _run_check(
                client,
                "return_tile_to_market_data",
                "document.querySelector('[data-action=\"open-security\"]').click(); true",
                "document.querySelector('[data-tab=\"ingestion\"]').classList.contains('active') && document.querySelector('#marketDataRows').textContent.trim().length > 0",
            ),
            _run_check(
                client,
                "research_evidence_to_search",
                "document.querySelector('[data-action=\"open-research\"]').click(); true",
                "document.querySelector('[data-tab=\"search\"]').classList.contains('active') && document.querySelector('#query').value.trim().length > 0",
            ),
            _run_check(
                client,
                "company_position_to_graph",
                "document.querySelector('[data-open=\"dashboard\"]').click(); true",
                "document.querySelector('[data-action=\"open-company\"]') !== null",
            ),
            _run_check(
                client,
                "company_position_click_loads_graph",
                "document.querySelector('[data-action=\"open-company\"]').click(); true",
                "document.querySelector('[data-tab=\"entity\"]').classList.contains('active') && document.querySelector('#issuerId').value.trim().length > 0 && document.querySelector('#issuerBox').textContent.trim().length > 2 && [document.querySelector('#graphCompanyPositionRows'), document.querySelector('#graphResearchTaskRows'), document.querySelector('#graphFactRows'), document.querySelector('#graphDecisionRows'), document.querySelector('#graphEdgeRows')].some((node) => node && node.textContent.trim().length > 0)",
            ),
            _run_check(
                client,
                "chain_to_hotspot",
                "document.querySelector('[data-open=\"dashboard\"]').click(); true",
                "document.querySelector('[data-action=\"open-hotspot\"]') !== null || document.querySelector('#runHotspotExpansion') !== null",
            ),
            _run_check(
                client,
                "chain_click_runs_hotspot",
                "const hot = document.querySelector('[data-action=\"open-hotspot\"]'); if (hot) { hot.click(); } else { document.querySelector('[data-open=\"search\"]').click(); document.querySelector('#runHotspotExpansion').click(); } true",
                "document.querySelector('[data-tab=\"search\"]').classList.contains('active') && document.querySelector('#hotspotBoundary').textContent.trim().length > 0",
                wait_timeout=max(timeout, 30.0),
            ),
            _run_check(
                client,
                "company_intelligence_spcx_research_flow",
                "document.querySelector('[data-open=\"search\"]').click(); document.querySelector('#companyIntelSymbol').value = 'SPCX'; document.querySelector('#secSingleTicker').value = 'SPCX'; document.querySelector('#runSecSingleName').click(); true",
                "document.querySelector('[data-tab=\"search\"]').classList.contains('active') && document.querySelector('#companyIntelStatus').textContent.trim().length > 0 && document.querySelector('#companyIntelProfileCount').textContent !== '0' && !document.querySelector('#companyIntelResearchRows').textContent.includes('暂无研究结果') && !document.querySelector('#companyIntelActionRows').textContent.includes('暂无模拟反馈') && document.querySelector('#companyIntelRawBox').textContent.includes('SPCX') && document.querySelector('#companyIntelRawBox').textContent.includes('research_results')",
                wait_timeout=max(timeout, 45.0),
            ),
            _run_check(
                client,
                "company_intelligence_empty_state_guidance",
                "document.querySelector('[data-open=\"search\"]').click(); document.querySelector('#companyIntelSymbol').value = 'ZZZNOLOCAL'; document.querySelector('#loadCompanyIntelligence').click(); true",
                "document.querySelector('#companyIntelGuidanceStatus').textContent.includes('未建档') && document.querySelector('#companyIntelMissingRows').textContent.includes('公司画像') && document.querySelector('#companyIntelNextActionRows').textContent.includes('建立最小公司情报档案') && document.querySelector('#companyIntelNextActionRows [data-action=\"company-intel-guidance\"]') !== null",
                wait_timeout=max(timeout, 20.0),
            ),
            _run_check(
                client,
                "company_report_structure_preview_dry_run",
                "document.querySelector('[data-open=\"search\"]').click(); document.querySelector('#companyIntelReportLimit').value = '2'; document.querySelector('#companyIntelReportQuery').value = 'SPCX'; document.querySelector('#previewCompanyReportStructure').click(); true",
                "document.querySelector('#companyIntelReportStructureStatus').textContent.includes('预览') && document.querySelector('#companyIntelReportStructureBox').textContent.includes('dry_run') && document.querySelector('#companyIntelReportStructureBox').textContent.includes('research_reports_are_viewpoint_signal')",
                wait_timeout=max(timeout, 20.0),
            ),
            _run_check(
                client,
                "company_database_operations_preview",
                "document.querySelector('[data-open=\"search\"]').click(); document.querySelector('#companyIntelBuildLimit').value = '1'; document.querySelector('#companyIntelBatchSize').value = '1'; document.querySelector('#auditCompanyCoverage').click(); true",
                "document.querySelector('#companyIntelBatchBuildStatus').textContent.includes('审计完成') && document.querySelector('#companyIntelOperationBox').textContent.includes('company_database_coverage_audit')",
                wait_timeout=max(timeout, 20.0),
            ),
            _run_check(
                client,
                "company_database_batch_preview",
                "document.querySelector('#previewCompanyBatchBuild').click(); true",
                "document.querySelector('#companyIntelBatchBuildStatus').textContent.includes('预览') && document.querySelector('#companyIntelOperationBox').textContent.includes('company_database_batch_build')",
                wait_timeout=max(timeout, 20.0),
            ),
            _run_check(
                client,
                "company_database_batch_execute_records_run_history",
                "document.querySelector('#runCompanyBatchBuild').click(); true",
                "document.querySelector('#companyIntelBatchBuildStatus').textContent.includes('已执行') && document.querySelector('#companyIntelRunHistoryStatus').textContent.trim().length > 0 && document.querySelector('#companyIntelRunHistoryStatus').textContent !== '待载入' && document.querySelector('#companyIntelRunRows').textContent.includes('executed') && document.querySelector('#companyIntelRunRows').textContent.includes('company_database_build_run_is_local_research_operations_history_no_live_trading')",
                wait_timeout=max(timeout, 30.0),
            ),
            _run_check(
                client,
                "company_report_realization_preview",
                "document.querySelector('#previewCompanyReportRealization').click(); true",
                "document.querySelector('#companyIntelRealizationStatus').textContent.includes('预览') && document.querySelector('#companyIntelOperationBox').textContent.includes('research_report_realization')",
                wait_timeout=max(timeout, 20.0),
            ),
            _run_check(
                client,
                "portfolio_proposal_loads_latest",
                "document.querySelector('[data-open=\"committee\"]').click(); document.querySelector('#loadPortfolioProposal').click(); true",
                "document.querySelector('[data-tab=\"committee\"]').classList.contains('active') && document.querySelector('#portfolioProposalBox').textContent.includes('组合方案') && document.querySelector('#portfolioProposalBox').textContent.includes('组合权重') && document.querySelector('#portfolioFeedbackDecision').textContent.includes('已载入')",
            ),
        ]
    finally:
        if client:
            client.close()
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()

    failures = [item for item in checks if item["status"] != "passed"]
    result = {
        "status": "passed" if not failures else "failed",
        "base_url": base_url,
        "ui_url": base_url.rstrip("/") + "/ui",
        "browser": chrome,
        "check_count": len(checks),
        "failure_count": len(failures),
        "checks": checks,
        "evidence_uri": f"artifact://ui-interaction-acceptance/{output.name}",
    }
    (output / "ui-interaction-acceptance.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run real click-through UI interaction acceptance with headless Chrome.")
    parser.add_argument("base_url", nargs="?", default="http://127.0.0.1:8000")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--chrome-bin", default="")
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args()
    result = run_ui_interaction_acceptance(args.base_url, output_dir=args.output_dir, chrome_bin=args.chrome_bin, timeout=args.timeout)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if result["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
