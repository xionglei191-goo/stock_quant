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
        diagnostics = client.evaluate(
            """
            (() => {
              const text = (selector) => document.querySelector(selector)?.textContent?.trim() || "";
              return {
                status: text("#status"),
                companyIntelSymbol: document.querySelector("#companyIntelSymbol")?.value || "",
                companyIntelReportQuery: document.querySelector("#companyIntelReportQuery")?.value || "",
                companyIntelVerdictStatus: text("#companyIntelVerdictStatus"),
                companyIntelVerdictRows: text("#companyIntelVerdictRows").slice(0, 240),
                companyIntelReportStructureStatus: text("#companyIntelReportStructureStatus"),
                companyIntelReportStructureBox: text("#companyIntelReportStructureBox").slice(0, 240),
                companyIntelBatchBuildStatus: text("#companyIntelBatchBuildStatus"),
                companyIntelRunHistoryStatus: text("#companyIntelRunHistoryStatus"),
                companyIntelRunRows: text("#companyIntelRunRows").slice(0, 240),
                companyIntelTrendStatus: text("#companyIntelTrendStatus"),
                companyIntelTrendRows: text("#companyIntelTrendRows").slice(0, 240),
                companyIntelProfileFieldCoverageStatus: text("#companyIntelProfileFieldCoverageStatus"),
                companyIntelProfileFieldExtractStatus: text("#companyIntelProfileFieldExtractStatus"),
                companyIntelMaterialInboxStatus: text("#companyIntelMaterialInboxStatus"),
                companyIntelMaterialInboxRows: text("#companyIntelMaterialInboxRows").slice(0, 240),
                companyIntelOwnershipManifestStatus: text("#companyIntelOwnershipManifestStatus"),
                companyIntelOwnershipManifestRows: text("#companyIntelOwnershipManifestRows").slice(0, 240),
                companyIntelOwnershipImportStatus: text("#companyIntelOwnershipImportStatus"),
                companyIntelOwnershipImportRows: text("#companyIntelOwnershipImportRows").slice(0, 240),
                companyIntelQualityReconcileStatus: text("#companyIntelQualityReconcileStatus"),
                companyIntelCycleStatus: text("#companyIntelCycleStatus"),
                companyIntelCycleDelta: text("#companyIntelCycleDelta"),
                companyIntelCycleFeedbackCount: text("#companyIntelCycleFeedbackCount"),
                companyIntelProfileFieldRows: text("#companyIntelProfileFieldRows").slice(0, 240),
                companyIntelProfileFieldExtractRows: text("#companyIntelProfileFieldExtractRows").slice(0, 240),
                companyIntelQualityReconcileRows: text("#companyIntelQualityReconcileRows").slice(0, 240)
              };
            })()
            """
        )
        return {
            "name": name,
            "status": "failed",
            "error": str(exc),
            "diagnostics": diagnostics,
            "duration_ms": round((time.time() - started) * 1000),
        }


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
        ownership_root = output / "ownership-fixtures"
        ownership_root.mkdir(parents=True, exist_ok=True)
        (ownership_root / "SPCX-ownership.csv").write_text(
            "\n".join(
                [
                    "股票代码,关系类型,股东名称,持股比例,报告期,来源",
                    "SPCX,十大股东,Alpha Capital,12.3%,2026Q1,local_acceptance_ownership",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        (ownership_root / "DEMO-ownership.csv").write_text(
            "\n".join(
                [
                    "股票代码,关系类型,股东名称,持股比例,报告期,来源",
                    "DEMO,十大股东,Alpha Capital,9.8%,2026Q1,local_acceptance_ownership",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        ownership_root_js = json.dumps(str(ownership_root))

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
                "document.querySelector('[data-tab=\"search\"]').classList.contains('active') && document.querySelector('#companyIntelStatus').textContent.trim().length > 0 && document.querySelector('#companyIntelVerdictStatus').textContent.trim().length > 0 && document.querySelector('#companyIntelVerdictRows').textContent.includes('研报边界') && document.querySelector('#companyIntelProfileCount').textContent !== '0' && !document.querySelector('#companyIntelResearchRows').textContent.includes('暂无研究结果') && !document.querySelector('#companyIntelActionRows').textContent.includes('暂无模拟反馈') && document.querySelector('#companyIntelRawBox').textContent.includes('SPCX') && document.querySelector('#companyIntelRawBox').textContent.includes('research_results') && document.querySelector('#companyIntelRawBox').textContent.includes('completeness_verdict')",
                wait_timeout=max(timeout, 45.0),
            ),
            _run_check(
                client,
                "company_industry_relationship_rows_have_trace_attrs",
                "(() => { document.querySelector('[data-open=\"search\"]').click(); renderCompanyRelationshipContext({relationship_context:{focus_issuer_ids:['issuer_demo'], summary:{peer_companies:1, upstream_companies:1, downstream_companies:1, industry_related_companies_total:3, industry_chain_nodes:1}, coverage_diagnostics:{industry_network_summary:{total:3, peers:1, upstream:1, downstream:1, chain_nodes:1}}, industry:{chain_nodes:[{chain_id:'chain_semis', chain_name:'Semiconductor', node_id:'node_design', node_name:'Design'}], peer_companies:[{issuer_id:'issuer_peer', display_name:'Peer Co', chain_id:'chain_semis', chain_name:'Semiconductor', node_ids:['node_design'], role:'designer', position_id:'pos_peer'}], upstream_companies:[{issuer_id:'issuer_upstream', display_name:'Upstream Co', chain_id:'chain_semis', chain_name:'Semiconductor', node_ids:['node_equipment'], role:'equipment', position_id:'pos_upstream'}], downstream_companies:[{issuer_id:'issuer_downstream', display_name:'Downstream Co', chain_id:'chain_semis', chain_name:'Semiconductor', node_ids:['node_device'], role:'device', position_id:'pos_downstream'}]}, ownership:{shareholders:[], approved_relationships:[], relationship_candidates:[], relationships:[], approved_shareholder_related_companies:[], shareholder_related_companies:[]}, dynamic_graph:{recommended_queries:[]}}}); return true; })()",
                "['peer','upstream','downstream'].every((direction) => { const row = document.querySelector(`#companyIntelRelationshipContextRows tr[data-industry-direction=\"${direction}\"]`); return row && row.dataset.action === 'open-relationship-graph' && row.dataset.industryRelationship && row.dataset.chainId === 'chain_semis' && row.dataset.chainNodeId && row.dataset.chainNodeIds && row.dataset.positionId; }) && document.querySelector('#companyIntelRelationshipContextRows tr[data-industry-direction=\"position\"]')?.dataset.industryRelationship === 'industry_position' && document.querySelector('#companyIntelPeerCount')?.dataset.networkTotal === '3'",
                wait_timeout=max(timeout, 30.0),
            ),
            _run_check(
                client,
                "company_industry_relationship_row_click_preserves_direction_chip",
                "Promise.resolve((async () => { document.querySelector('[data-open=\"search\"]').click(); renderCompanyRelationshipContext({relationship_context:{focus_issuer_ids:['issuer_demo'], summary:{peer_companies:1, upstream_companies:1, downstream_companies:1, industry_related_companies_total:3, industry_chain_nodes:1}, coverage_diagnostics:{industry_network_summary:{total:3, peers:1, upstream:1, downstream:1, chain_nodes:1}}, industry:{chain_nodes:[{chain_id:'chain_semis', chain_name:'Semiconductor', node_id:'node_design', node_name:'Design'}], peer_companies:[{issuer_id:'issuer_peer', display_name:'Peer Co', chain_id:'chain_semis', chain_name:'Semiconductor', node_ids:['node_design'], role:'designer', position_id:'pos_peer'}], upstream_companies:[{issuer_id:'issuer_upstream', display_name:'Upstream Co', chain_id:'chain_semis', chain_name:'Semiconductor', node_ids:['node_equipment'], role:'equipment', position_id:'pos_upstream'}], downstream_companies:[{issuer_id:'issuer_downstream', display_name:'Downstream Co', chain_id:'chain_semis', chain_name:'Semiconductor', node_ids:['node_device'], role:'device', position_id:'pos_downstream'}]}, ownership:{shareholders:[], approved_relationships:[], relationship_candidates:[], relationships:[], approved_shareholder_related_companies:[], shareholder_related_companies:[]}, dynamic_graph:{recommended_queries:[]}}}); const row = document.querySelector('#companyIntelRelationshipContextRows tr[data-industry-direction=\"upstream\"]'); if (!row) throw new Error('upstream industry row missing'); row.click(); return true; })())",
                "(() => { const chip = document.querySelector('#knowledgeGraphFilterChips [data-filter-key=\"industryDirection\"]'); return document.querySelector('[data-tab=\"entity\"]').classList.contains('active') && chip?.textContent.includes('产业方向') && chip?.textContent.includes('上游') && !chip?.textContent.includes('upstream') && chip?.dataset.filterRawValue === 'upstream' && chip?.title.includes('upstream') && document.querySelector('#knowledgeGraphFilterChips [data-filter-key=\"chainId\"]')?.dataset.filterRawValue === 'chain_semis' && document.querySelector('#knowledgeGraphFilterChips [data-filter-key=\"chainNodeId\"]')?.dataset.filterRawValue === 'node_equipment'; })()",
                wait_timeout=max(timeout, 30.0),
            ),
            _run_check(
                client,
                "company_industry_recommended_query_click_preserves_direction_chip",
                "Promise.resolve((async () => { document.querySelector('[data-open=\"search\"]').click(); renderCompanyRelationshipContext({relationship_context:{focus_issuer_ids:['issuer_demo'], summary:{peer_companies:1, upstream_companies:1, downstream_companies:1, industry_related_companies_total:3, industry_chain_nodes:1}, coverage_diagnostics:{industry_network_summary:{total:3, peers:1, upstream:1, downstream:1, chain_nodes:1}}, industry:{chain_nodes:[{chain_id:'chain_semis', chain_name:'Semiconductor', node_id:'node_design', node_name:'Design'}], peer_companies:[], upstream_companies:[], downstream_companies:[]}, ownership:{shareholders:[], approved_relationships:[], relationship_candidates:[], relationships:[], approved_shareholder_related_companies:[], shareholder_related_companies:[]}, dynamic_graph:{recommended_queries:[{label:'上游公司: Upstream Co', reason:'按当前公司所在节点展开上游公司网络', query:{issuer_id:'issuer_demo', relationship_type:'upstream_of', chain_id:'chain_semis', chain_node_id:'node_equipment', industry_direction:'upstream'}}]}}}); const row = document.querySelector('#companyIntelRelationshipContextRows tr[data-industry-direction=\"upstream\"]'); if (!row || !row.textContent.includes('图谱推荐入口')) throw new Error('upstream recommended query row missing'); row.click(); return true; })())",
                "(() => { const chip = document.querySelector('#knowledgeGraphFilterChips [data-filter-key=\"industryDirection\"]'); const typeChip = document.querySelector('#knowledgeGraphFilterChips [data-filter-key=\"relationshipType\"]'); return document.querySelector('[data-tab=\"entity\"]').classList.contains('active') && chip?.textContent.includes('产业方向') && chip?.textContent.includes('上游') && !chip?.textContent.includes('upstream') && chip?.dataset.filterRawValue === 'upstream' && chip?.title.includes('upstream') && typeChip?.textContent.includes('上游关系') && !typeChip?.textContent.includes('upstream_of') && typeChip?.dataset.filterRawValue === 'upstream_of' && typeChip?.title.includes('upstream_of') && document.querySelector('#knowledgeGraphFilterChips [data-filter-key=\"chainId\"]')?.dataset.filterRawValue === 'chain_semis' && document.querySelector('#knowledgeGraphFilterChips [data-filter-key=\"chainNodeId\"]')?.dataset.filterRawValue === 'node_equipment'; })()",
                wait_timeout=max(timeout, 30.0),
            ),
            _run_check(
                client,
                "company_relationship_rows_display_chinese_type_labels",
                "(() => { document.querySelector('[data-open=\"search\"]').click(); renderCompanyRelationshipContext({relationship_context:{focus_issuer_ids:['issuer_demo'], summary:{peer_companies:1, upstream_companies:0, downstream_companies:0, industry_related_companies_total:1, approved_ownership_relationships:1, ownership_candidates:1}, coverage_diagnostics:{industry_network_summary:{total:1, peers:1, upstream:0, downstream:0, chain_nodes:1}}, industry:{chain_nodes:[], peer_companies:[{issuer_id:'issuer_peer', display_name:'Peer Co', chain_id:'chain_semis', chain_name:'Semiconductor', node_ids:['node_design'], relationship_type:'industry_peer', position_id:'pos_peer'}], upstream_companies:[], downstream_companies:[]}, ownership:{shareholders:[], approved_relationships:[{object_id:'external_alpha', entity_name:'Alpha Capital', relationship_type:'shareholder', review_status:'approved', confidence:0.91, holder_key:'external_alpha', holder_name:'Alpha Capital'}], relationship_candidates:[{object_id:'external_beta', entity_name:'Beta Parent', relationship_type:'controller_candidate', review_status:'needs_review', confidence:0.62}], relationships:[], approved_shareholder_related_companies:[], shareholder_related_companies:[]}, dynamic_graph:{recommended_queries:[]}}}); return true; })()",
                "(() => { const rows = Array.from(document.querySelectorAll('#companyIntelRelationshipContextRows tr')); const compact = (row) => Array.from(row.querySelectorAll('td')).slice(0, 3).map((cell) => cell.textContent).join('|'); const peer = rows.find((row) => row.textContent.includes('Peer Co')); const fact = rows.find((row) => row.textContent.includes('事实股权关系') && row.textContent.includes('Alpha Capital')); const candidate = rows.find((row) => row.textContent.includes('股权候选') && row.textContent.includes('Beta Parent')); return peer && fact && candidate && compact(peer).includes('同类关系') && compact(fact).includes('事实股东') && compact(candidate).includes('实控候选') && !compact(peer).includes('industry_peer') && !compact(fact).includes('shareholder') && !compact(candidate).includes('controller_candidate') && fact.textContent.includes('shareholder') && candidate.textContent.includes('controller_candidate'); })()",
                wait_timeout=max(timeout, 30.0),
            ),
            _run_check(
                client,
                "company_shareholder_holding_source_label_is_readable",
                "(() => { document.querySelector('[data-open=\"search\"]').click(); renderCompanyRelationshipContext({relationship_context:{focus_issuer_ids:['issuer_demo'], summary:{shareholders:1}, coverage_diagnostics:{}, industry:{chain_nodes:[], peer_companies:[], upstream_companies:[], downstream_companies:[]}, ownership:{shareholders:[{holder_id:'000SOURCE', holder_key:'000SOURCE', holder_name:'Source Only Capital', issuer_id:'issuer_demo', security_id:'sec_demo', source_id:'sec_edgar', shares:1234, value_usd:5678}], approved_relationships:[], relationship_candidates:[], relationships:[], approved_shareholder_related_companies:[], shareholder_related_companies:[]}, dynamic_graph:{recommended_queries:[]}}}); const row = Array.from(document.querySelectorAll('#companyIntelRelationshipContextRows tr')).find((item) => item.textContent.includes('股东/持有人') && item.textContent.includes('Source Only Capital')); const cells = row ? Array.from(row.querySelectorAll('td')).map((cell) => cell.textContent) : []; const compact = cells.slice(0, 3).join('|'); window.__shareholderHoldingSourceLabelOk = Boolean(row && compact.includes('SEC 官方披露') && !compact.includes('sec_edgar') && row.dataset.sourceId === 'sec_edgar'); return window.__shareholderHoldingSourceLabelOk; })()",
                "window.__shareholderHoldingSourceLabelOk === true",
                wait_timeout=max(timeout, 30.0),
            ),
            _run_check(
                client,
                "company_relationship_gap_buttons_open_expected_entry",
                "(() => { const originalPreview = window.buildCompanyDatabaseBatch; const originalImport = window.importCompanyOwnershipTables; const originalOpenGraph = window.openRelationshipGraphContext; const calls = []; window.buildCompanyDatabaseBatch = async (...args) => { calls.push('preview_batch_build'); return true; }; window.importCompanyOwnershipTables = async (...args) => { calls.push('ownership_import_guidance'); document.querySelector('[data-tab=\"search\"]').classList.add('active'); const details = document.querySelector('#companyIntelAdvancedMaintenance'); if (details) details.open = true; return true; }; window.openRelationshipGraphContext = async (...args) => { calls.push('open_relationship_graph'); return true; }; document.querySelector('[data-open=\"search\"]').click(); const gapRows = [{layer:'industry_position', label:'产业链位置', evidence:'CompanyPosition + IndustryChain', target:{ui_action:'preview_batch_build'}},{layer:'peer_companies', label:'同类公司', evidence:'same chain node positions', target:{ui_action:'preview_batch_build'}},{layer:'upstream_companies', label:'上游公司', evidence:'IndustryChain edges + CompanyPosition / supplier relationships', target:{ui_action:'preview_batch_build'}},{layer:'downstream_companies', label:'下游公司', evidence:'IndustryChain edges + CompanyPosition / customer relationships', target:{ui_action:'preview_batch_build'}},{layer:'ownership_candidates', label:'股权/控制关系', evidence:'InstitutionalHolding / structured ownership CompanyRelationship', target:{ui_action:'ownership_import_guidance'}},{layer:'graph_edges', label:'动态图谱边', evidence:'/api/graph/query edges', target:{ui_action:'open_relationship_graph'}}].map((item) => ({...item, status:'missing_required', available:false, count:0, required:true, recommended_action:`补齐 ${item.label}`})); renderCompanyRelationshipContext({relationship_context:{focus_issuer_ids:['issuer_demo'], summary:{peer_companies:0, upstream_companies:0, downstream_companies:0, industry_related_companies_total:0, industry_chain_nodes:0, shareholders:0, ownership_relationships:0, approved_shareholder_related_companies:0, shareholder_related_companies:0, shareholder_related_companies_total:0}, coverage_diagnostics:{status:'missing', missing_required_layers:gapRows.map((item) => item.layer), diagnostics:gapRows, next_actions:gapRows.map((item) => ({action:'relationship_backfill', layer:item.layer, label:item.label, reason:item.recommended_action, target:item.target}))}, industry:{chain_nodes:[], peer_companies:[], upstream_companies:[], downstream_companies:[]}, ownership:{shareholders:[], approved_relationships:[], relationship_candidates:[], relationships:[], approved_shareholder_related_companies:[], shareholder_related_companies:[]}, dynamic_graph:{recommended_queries:[]}}}); const buttons = Array.from(document.querySelectorAll('#companyIntelRelationshipContextRows button[data-action=\"run-relationship-backfill-action\"]')); const layerSet = new Set(buttons.map((button) => button.dataset.layer)); if (gapRows.some((row) => !layerSet.has(row.layer))) throw new Error('not all relationship gap buttons rendered'); if (!buttons.find((button) => button.dataset.layer === 'peer_companies')?.dataset.targetUiAction) throw new Error('missing target ui action'); buttons.find((button) => button.dataset.layer === 'peer_companies').click(); buttons.find((button) => button.dataset.layer === 'ownership_candidates').click(); buttons.find((button) => button.dataset.layer === 'graph_edges').click(); window.__relationshipGapCalls = calls.join('|'); window.__relationshipGapButtonCount = buttons.length; window.buildCompanyDatabaseBatch = originalPreview; window.importCompanyOwnershipTables = originalImport; window.openRelationshipGraphContext = originalOpenGraph; return true; })()",
                "Number(window.__relationshipGapButtonCount || 0) === 6 && document.querySelector('#companyIntelRelationshipContextRows').textContent.includes('产业链位置') && document.querySelector('#companyIntelRelationshipContextRows').textContent.includes('同类公司') && document.querySelector('#companyIntelRelationshipContextRows').textContent.includes('上游公司') && document.querySelector('#companyIntelRelationshipContextRows').textContent.includes('下游公司') && document.querySelector('#companyIntelRelationshipContextRows').textContent.includes('股权/控制关系') && document.querySelector('#companyIntelRelationshipContextRows').textContent.includes('动态图谱边') && document.querySelector('#companyIntelRelationshipContextRows button[data-action=\"run-relationship-backfill-action\"][data-backfill-action=\"preview_batch_build\"][data-target-ui-action=\"preview_batch_build\"]') !== null && document.querySelector('#companyIntelRelationshipContextRows button[data-action=\"run-relationship-backfill-action\"][data-backfill-action=\"ownership_import_guidance\"][data-target-ui-action=\"ownership_import_guidance\"]') !== null && document.querySelector('#companyIntelRelationshipContextRows button[data-action=\"run-relationship-backfill-action\"][data-backfill-action=\"open_relationship_graph\"][data-target-ui-action=\"open_relationship_graph\"]') !== null && document.querySelector('[data-tab=\"search\"]').classList.contains('active') && document.querySelector('#companyIntelAdvancedMaintenance')?.open === true && String(window.__relationshipGapCalls || '').includes('preview_batch_build') && String(window.__relationshipGapCalls || '').includes('ownership_import_guidance') && String(window.__relationshipGapCalls || '').includes('open_relationship_graph')",
                wait_timeout=max(timeout, 30.0),
            ),
            _run_check(
                client,
                "company_relationship_enhancement_actions_use_target",
                "(() => { document.querySelector('[data-open=\"search\"]').click(); const optionalRows = [{layer:'shareholder_network', label:'13F持有人网络', evidence:'same-holder InstitutionalHolding records', target:{ui_action:'ownership_import_guidance'}},{layer:'approved_shareholder_network', label:'事实股东网络', evidence:'approved active ownership CompanyRelationship records', target:{ui_action:'ownership_import_guidance'}}].map((item) => ({...item, status:'missing_optional', available:false, count:0, required:false, recommended_action:`增强 ${item.label}`})); renderCompanyRelationshipContext({relationship_context:{focus_issuer_ids:['issuer_demo'], summary:{shareholders:0, shareholder_related_companies:0, approved_shareholder_related_companies:0, shareholder_related_companies_total:0}, coverage_diagnostics:{status:'complete', missing_required_layers:[], missing_optional_layers:optionalRows.map((item) => item.layer), diagnostics:optionalRows, enhancement_actions:optionalRows.map((item) => ({action:'relationship_enhancement', layer:item.layer, label:item.label, reason:item.recommended_action, target:item.target}))}, enhancement_actions:optionalRows.map((item) => ({action:'relationship_enhancement', layer:item.layer, label:item.label, reason:item.recommended_action, target:item.target})), industry:{chain_nodes:[], peer_companies:[], upstream_companies:[], downstream_companies:[]}, ownership:{shareholders:[], approved_relationships:[], relationship_candidates:[], relationships:[], approved_shareholder_related_companies:[], shareholder_related_companies:[]}, dynamic_graph:{recommended_queries:[]}}}); return true; })()",
                "document.querySelector('#companyIntelRelationshipContextRows').textContent.includes('13F持有人网络') && document.querySelector('#companyIntelRelationshipContextRows').textContent.includes('事实股东网络') && Array.from(document.querySelectorAll('#companyIntelRelationshipContextRows button[data-action=\"run-relationship-backfill-action\"]')).filter((button) => button.dataset.targetUiAction === 'ownership_import_guidance' && ['shareholder_network','approved_shareholder_network'].includes(button.dataset.layer)).length === 2",
                wait_timeout=max(timeout, 30.0),
            ),
            _run_check(
                client,
                "company_intelligence_empty_state_guidance",
                "document.querySelector('[data-open=\"search\"]').click(); document.querySelector('#companyIntelSymbol').value = 'ZZZNOLOCAL'; document.querySelector('#loadCompanyIntelligence').click(); true",
                "document.querySelector('#companyIntelGuidanceStatus').textContent.includes('未建档') && document.querySelector('#companyIntelVerdictStatus').textContent.includes('未建档') && document.querySelector('#companyIntelVerdictRows').textContent.includes('公司画像') && document.querySelector('#companyIntelMissingRows').textContent.includes('公司画像') && document.querySelector('#companyIntelNextActionRows').textContent.includes('建立最小公司情报档案') && document.querySelector('#companyIntelNextActionRows [data-action=\"company-intel-guidance\"]') !== null",
                wait_timeout=max(timeout, 20.0),
            ),
            _run_check(
                client,
                "company_report_structure_preview_dry_run",
                "document.querySelector('[data-open=\"search\"]').click(); document.querySelector('#companyIntelSymbol').value = 'SPCX'; document.querySelector('#companyIntelReportLimit').value = '2'; document.querySelector('#companyIntelReportQuery').value = 'SPCX'; document.querySelector('#previewCompanyReportStructure').click(); true",
                "document.querySelector('#companyIntelReportStructureStatus').textContent.includes('预览') && document.querySelector('#companyIntelReportStructureBox').textContent.includes('预览') && document.querySelector('#companyIntelReportStructureBox').textContent.includes('research_reports_are_viewpoint_signal')",
                wait_timeout=max(timeout, 20.0),
            ),
            _run_check(
                client,
                "company_database_operations_preview",
                "document.querySelector('[data-open=\"search\"]').click(); document.querySelector('#companyIntelSymbol').value = 'SPCX'; document.querySelector('#companyIntelBuildLimit').value = '1'; document.querySelector('#companyIntelBatchSize').value = '1'; document.querySelector('#auditCompanyCoverage').click(); true",
                "document.querySelector('#companyIntelBatchBuildStatus').textContent.includes('审计完成') && document.querySelector('#companyIntelOperationBox').textContent.includes('company_database_coverage_audit')",
                wait_timeout=max(timeout, 20.0),
            ),
            _run_check(
                client,
                "company_database_batch_preview",
                "document.querySelector('#companyIntelSymbol').value = 'SPCX'; document.querySelector('#companyIntelBatchBuildStatus').textContent = '等待'; document.querySelector('#companyIntelCoverageRows').innerHTML = ''; document.querySelector('#previewCompanyBatchBuild').click(); true",
                "document.querySelector('#companyIntelBatchBuildStatus').textContent.includes('预览') && document.querySelector('#companyIntelCoverageRows').textContent.trim().length > 0",
                wait_timeout=max(timeout, 60.0),
            ),
            _run_check(
                client,
                "company_profile_deep_field_coverage_load",
                "document.querySelector('#companyIntelSymbol').value = 'SPCX'; document.querySelector('#companyIntelProfileFieldList').value = 'business_summary,products,revenue,net_income'; document.querySelector('#auditCompanyProfileFieldCoverage').click(); true",
                "document.querySelector('#companyIntelProfileFieldCoverageStatus').textContent.includes('已审计') && document.querySelector('#companyIntelProfileFieldRows').textContent.trim().length > 0 && document.querySelector('#companyIntelProfileFieldCoverageScore').textContent.trim().length > 0",
                wait_timeout=max(timeout, 20.0),
            ),
            _run_check(
                client,
                "company_profile_field_extraction_preview",
                "document.querySelector('#companyIntelSymbol').value = 'SPCX'; document.querySelector('#previewCompanyProfileFieldExtract').click(); true",
                "document.querySelector('#companyIntelProfileFieldExtractStatus').textContent.includes('预览') && document.querySelector('#companyIntelProfileFieldCandidateCount').textContent.trim().length > 0 && document.querySelector('#companyIntelProfileFieldExtractRows').textContent.trim().length > 0",
                wait_timeout=max(timeout, 20.0),
            ),
            _run_check(
                client,
                "company_profile_assertion_conflict_queue_render",
                "document.querySelector('[data-open=\"search\"]').click(); renderCompanyProfileAssertionConflicts({schema_id:'company-profile-field-assertions-v1', count:1, conflict_count:1, superseded_count:0, status_counts:{conflict_candidate:1}, review_status_counts:{needs_review:1}, assertions:[{assertion_id:'cpfa_demo_conflict', issuer_id:'issuer_001', security_id:'sec_001', field_name:'website_url', value:'https://new-demo.example.com', document_ids:['doc_demo_website_new'], evidence_ids:['evi_demo_website_new'], source_ids:['src_company_ir_new'], review_status:'needs_review', assertion_status:'conflict_candidate', conflicts_with:['cpfa_demo_old'], conflicting_assertions:[{assertion_id:'cpfa_demo_old', value:'https://demo.example.com', confidence:0.9}], review_recommendation:{recommended_action:'prefer_candidate_after_review', candidate_score:0.91, best_conflict_score:0.82, freshness_score:1, source_priority_rank:4}}], usage_boundary:'profile_field_assertions_are_local_fact_provenance_records_no_live_trading'}, true); document.querySelector('[data-company-profile-assertion-select]').checked = true; true",
                "document.querySelector('#companyIntelProfileAssertionReviewStatus').textContent.includes('待复核') && document.querySelector('#companyIntelProfileAssertionConflictCount').textContent.includes('1') && document.querySelector('#companyIntelProfileAssertionRecommendationStatus').textContent.includes('1/1') && document.querySelector('#companyIntelProfileAssertionReviewRows').textContent.includes('旧值') && document.querySelector('#companyIntelProfileAssertionReviewRows').textContent.includes('prefer') && selectedCompanyProfileAssertionIds().includes('cpfa_demo_conflict') && document.querySelector('#companyIntelProfileAssertionReviewRows [data-action=\"review-company-profile-assertion\"][data-review-action=\"approve\"]') !== null && document.querySelector('#companyIntelOperationBox').textContent.includes('conflict_count')",
                wait_timeout=max(timeout, 20.0),
            ),
            _run_check(
                client,
                "company_relationship_review_queue_render",
                "document.querySelector('[data-open=\"search\"]').click(); renderCompanyRelationshipReview({relationships:{company_relationships:[{relationship_id:'rel_demo_candidate', issuer_id:'issuer_001', security_id:'sec_001', subject_type:'company', subject_id:'issuer_001', object_type:'company', object_id:'customer_demo', relationship_type:'customer_candidate', relationship_status:'unknown', review_status:'needs_review', confidence:0.72, evidence_ids:['ev_customer'], document_ids:['doc_customer'], source_ids:['src_company_ir'], metadata:{candidate_status:'candidate', entity_name:'Demo Customer'}, review_recommendation:{recommended_action:'prefer_approve_after_review', candidate_score:0.83}}]}}); document.querySelector('[data-company-relationship-select]').checked = true; true",
                "(() => { const row = document.querySelector('#companyIntelRelationshipReviewRows tr'); const compact = row ? Array.from(row.querySelectorAll('td')).slice(0, 3).map((cell) => cell.textContent).join('|') : ''; return document.querySelector('#companyIntelRelationshipReviewStatus').textContent.includes('待复核') && document.querySelector('#companyIntelRelationshipCandidateCount').textContent.includes('1') && document.querySelector('#companyIntelRelationshipRecommendationStatus').textContent.includes('1/1') && compact.includes('客户候选') && !compact.includes('customer_candidate') && row?.textContent.includes('customer_candidate') && row?.textContent.includes('Demo Customer') && row?.textContent.includes('prefer') && selectedCompanyRelationshipIds().includes('rel_demo_candidate') && document.querySelector('#companyIntelRelationshipReviewRows [data-action=\"review-company-relationship\"][data-review-action=\"approve\"]') !== null; })()",
                wait_timeout=max(timeout, 20.0),
            ),
            _run_check(
                client,
                "company_event_review_queue_render",
                "document.querySelector('[data-open=\"search\"]').click(); renderCompanyEventReview({facts_and_events:{company_events:[{event_id:'ce_demo_candidate', issuer_id:'issuer_001', security_id:'sec_001', event_type:'earnings_result', title:'Demo revenue increased', summary:'Revenue increased and margin improved.', fact_status:'verified', review_status:'needs_review', confidence:0.78, evidence_ids:['ev_event'], document_ids:['doc_event'], source_ids:['src_sec'], metadata:{classification_status:'candidate_needs_review', source_layer:'official_disclosure_text_classification'}, review_recommendation:{recommended_action:'prefer_approve_after_review', candidate_score:0.86}}]}}); document.querySelector('[data-company-event-select]').checked = true; true",
                "document.querySelector('#companyIntelEventReviewStatus').textContent.includes('待复核') && document.querySelector('#companyIntelEventCandidateCount').textContent.includes('1') && document.querySelector('#companyIntelEventRecommendationStatus').textContent.includes('1/1') && document.querySelector('#companyIntelEventReviewRows').textContent.includes('Demo revenue') && document.querySelector('#companyIntelEventReviewRows').textContent.includes('prefer') && selectedCompanyEventIds().includes('ce_demo_candidate') && document.querySelector('#companyIntelEventReviewRows [data-action=\"review-company-event\"][data-review-action=\"reclassify\"]') !== null",
                wait_timeout=max(timeout, 20.0),
            ),
            _run_check(
                client,
                "chokepoint_structured_conclusion_verification_panel",
                "document.querySelector('[data-open=\"chokepoint\"]').click(); syncChokepointRun({run_id:'cprun_demo_structured', status:'completed', current_step:'verification', topic:'AI power chokepoint', steps:[], issues:[], validation_context:{market_data:{count:1, latest:[{security_id:'sec_demo', as_of_date:'2026-06-26', close:42, volume:1000, source_id:'public_eod_market_data'}]}, facts:{count:1, items:[{evidence_id:'evi_demo_fact', document_id:'doc_demo', source_uri:'https://example.com/filing', snippet:'Confirmed capacity fact', confidence:0.9}]}, opinions:{count:0, items:[]}, knowledge_graph:{security_ids:['sec_demo'], issuer_ids:['issuer_demo']}, needs_verification:{count:1, items:[{task_id:'rtask_demo_open', status:'open', reason:'Verify customer qualification timing', priority:90, required_slots:['source_url','published_at']}], all_items:[{task_id:'rtask_demo_open', status:'open', reason:'Verify customer qualification timing', priority:90, required_slots:['source_url','published_at']},{task_id:'rtask_demo_done', status:'done', reason:'Closed source check', priority:70, required_slots:['source_url']}], closed_count:1, status_counts:{open:1, done:1}}}, conclusion:{status:'needs_evidence', one_line_conclusion:'Structured conclusion demo', thesis_strength_score:6.2, confidence:'medium', falsification_status:'needs_verification', evidence_quality_summary:{verification_task_count:1}, core_facts:[{text:'Confirmed capacity fact', evidence_id:'evi_demo_fact', source_uri:'https://example.com/filing', layer:'confirmed'}], inferences:[{text:'Switching cost inferred', layer:'inferred'}], speculations:[{text:'Customer ramp speculative', layer:'speculative'}], unknowns:[{text:'Customer qualification timing unknown', layer:'unknown', verification_status:'open'}], evidence_gaps:[{type:'verification_task', task_id:'rtask_demo_open', reason:'Verify customer qualification timing'}], market_pricing_context:{count:1, role:'market_pricing_validation_only'}, next_verification_tasks:[{task_id:'rtask_demo_open', status:'open', reason:'Verify customer qualification timing', priority:90}], verification_tasks:{open_count:1, closed_count:1, done_count:1, dismissed_count:0, status_counts:{open:1, done:1}}, usage_boundary:'research_only_not_investment_advice'}}); true",
                "document.querySelector('#cpFalsificationStatus').textContent.includes('needs_verification') && document.querySelector('#cpVerificationClosedCount').textContent.includes('1') && document.querySelector('#cpVerificationTaskRows').textContent.includes('demo open') && document.querySelector('#cpVerificationTaskRows').textContent.includes('demo done') && document.querySelector('#cpVerificationTaskRows [data-action=\"review-chokepoint-verification-task\"][data-task-status=\"done\"]') !== null && document.querySelector('#cpConclusionBox').textContent.includes('core_facts') && document.querySelector('#cpConclusionBox').textContent.includes('market_pricing_context')",
                wait_timeout=max(timeout, 20.0),
            ),
            _run_check(
                client,
                "company_material_inbox_preview_render",
                "document.querySelector('#companyIntelMaterialRootPath').value = '/tmp/company_materials/inbox'; document.querySelector('#companyIntelMaterialManifestGlob').value = '*.manifest.json'; document.querySelector('#companyIntelMaterialScanLimit').value = '2'; const payload = companyMaterialInboxPayload(false); renderCompanyMaterialInbox({schema_id:'company-material-inbox-ingest-v1', status:'dry_run', execute:false, dry_run:true, root_path:payload.root_path, manifest_glob:payload.manifest_glob, totals:{planned_count:1, invalid_count:1, documents_ingested:0}, items:[{manifest_path:'/tmp/company_materials/inbox/demo.manifest.json', file_path:'/tmp/company_materials/inbox/demo.txt', issuer_id:'issuer_demo', source_id:'demo_ir', source_type:'company_ir', document_type:'official_business_overview', document_id:'doc_cmat_demo', status:'planned', planned_actions:['register_source_if_missing','ingest_document']},{manifest_path:'/tmp/company_materials/inbox/bad.manifest.json', file_path:'/tmp/company_materials/inbox/report.txt', issuer_id:'issuer_demo', source_id:'demo_report', source_type:'broker_research', document_type:'research_report', status:'invalid', errors:['disallowed_source_type','disallowed_document_type','training_allowed_not_permitted']}], source_rules:{research_reports:'skipped_opinion_only_not_fact_source'}, usage_boundary:'local_company_material_inbox_only_official_ir_public_materials_no_external_download_no_training_no_live_trading'}, true); true",
                "document.querySelector('#companyIntelMaterialInboxStatus').textContent.includes('预览') && document.querySelector('#companyIntelMaterialPlannedCount').textContent.includes('1') && document.querySelector('#companyIntelMaterialInboxRows').textContent.includes('cmat demo') && document.querySelector('#companyIntelMaterialInboxRows').textContent.includes('broker_research')",
                wait_timeout=max(timeout, 20.0),
            ),
            _run_check(
                client,
                "company_package_import_preview_render",
                "(() => { document.querySelector('#companyIntelPackageRootPath').value = '/tmp/company_packages'; document.querySelector('#companyIntelPackageManifestGlob').value = '*.watchlist.*'; document.querySelector('#companyIntelPackageScanLimit').value = '2'; const pkgPayload = companyPackageImportPayload(false); renderCompanyPackageImport({schema_id:'company-database-package-import-v1', status:'dry_run', execute:false, dry_run:true, root_path:pkgPayload.root_path, manifest_glob:pkgPayload.manifest_glob, totals:{valid_count:1, planned_count:1, executed_count:0, already_exists_count:0, invalid_count:1, duplicate_count:0, failed_count:0}, companies:[{input_source:'package:demo.watchlist.csv', symbol:'PKGA', status:'dry_run', ids:{issuer_id:'issuer_bootstrap_pkga', security_id:'sec_bootstrap_pkga'}, created:{issuer:false, security:false, company_profile:false}, material_inbox_manifest_template:{file_path:'./pkga-company-profile.md'}},{input_source:'companies', symbol:'', status:'invalid', errors:['missing_symbol']}], next_actions:[{endpoint:'/api/company-database/material-inbox/ingest'}], usage_boundary:'local_company_database_package_import_only_no_external_download_no_research_report_fact_promotion_no_live_trading'}, true); return true; })()",
                "document.querySelector('#companyIntelPackageImportStatus').textContent.includes('预览') && document.querySelector('#companyIntelPackagePlannedCount').textContent.includes('1') && document.querySelector('#companyIntelPackageInvalidCount').textContent.includes('1') && document.querySelector('#companyIntelPackageImportRows').textContent.includes('PKGA') && document.querySelector('#companyIntelOperationBox').textContent.includes('local_company_database_package_import_only')",
                wait_timeout=max(timeout, 20.0),
            ),
            _run_check(
                client,
                "company_package_import_run_history_render",
                "(() => { renderCompanyPackageImportRuns({count:1, include_items:false, usage_boundary:'company_package_import_runs_are_local_watchlist_history_no_external_download_no_live_trading', runs:[{run_id:'pkg_import_demo', status:'executed', execute:true, dry_run:false, root_path:'/tmp/company_packages', manifest_glob:'*.watchlist.*', input_count:2, company_count:1, target_symbols:['PKGA'], target_issuer_ids:['issuer_bootstrap_pkga'], created_issuer_ids:['issuer_bootstrap_pkga'], existing_issuer_ids:[], duplicate_symbols:['PKGA'], invalid_symbols:[], totals:{valid_count:1, executed_count:1, already_exists_count:0, invalid_count:0, duplicate_count:1, failed_count:0}, items:[], item_details_omitted:true, completed_at:'2026-06-26T10:00:00Z', usage_boundary:'company_package_import_run_is_local_watchlist_history_no_external_download_no_live_trading'}]}, true); return true; })()",
                "document.querySelector('#companyIntelPackageRunHistoryStatus').textContent.includes('已执行') && document.querySelector('#companyIntelPackageRunHistoryCount').textContent.includes('1') && document.querySelector('#companyIntelPackageImportRunRows').textContent.includes('import demo') && document.querySelector('#companyIntelPackageImportRunRows').textContent.includes('本地导入历史') && document.querySelector('#companyIntelOperationBox').textContent.includes('company_package_import_runs_are_local_watchlist_history')",
                wait_timeout=max(timeout, 20.0),
            ),
            _run_check(
                client,
                "company_package_material_manifest_render",
                "(() => { renderCompanyPackageMaterialManifests({schema_id:'company-material-manifest-export-v1', status:'dry_run', execute:false, dry_run:true, run_id:'pkg_import_demo', output_root:'/tmp/company_materials/inbox', manifest_count:1, written_count:0, skipped_count:0, items:[{run_id:'pkg_import_demo', issuer_id:'issuer_bootstrap_pkga', security_id:'sec_bootstrap_pkga', symbol:'PKGA', status:'planned', manifest_path:'/tmp/company_materials/inbox/pkga-company-profile.manifest.json', template:{issuer_id:'issuer_bootstrap_pkga', security_id:'sec_bootstrap_pkga', source_type:'company_ir', document_type:'official_business_overview', source_uri:'https://example.com/investor-relations', file_path:'./pkga-company-profile.md'}}], usage_boundary:'local_company_material_manifest_export_only_no_external_download_no_training_no_live_trading'}, true); return true; })()",
                "document.querySelector('#companyIntelPackageManifestExportStatus').textContent.includes('预览') && document.querySelector('#companyIntelPackageManifestWrittenCount').textContent.includes('0/1') && document.querySelector('#companyIntelPackageManifestRows').textContent.includes('pkga company profile') && document.querySelector('#companyIntelPackageManifestRows').textContent.includes('company_ir') && document.querySelector('#companyIntelOperationBox').textContent.includes('company-material-manifest-export-v1')",
                wait_timeout=max(timeout, 20.0),
            ),
            _run_check(
                client,
                "company_ownership_manifest_preview_real_api",
                f"document.querySelector('[data-open=\"search\"]').click(); document.querySelector('#companyIntelSymbol').value = 'SPCX'; document.querySelector('#companyIntelOwnershipRootPath').value = {ownership_root_js}; document.querySelector('#companyIntelOwnershipManifestGlob').value = '*ownership.csv'; document.querySelector('#companyIntelOwnershipDefaultKind').value = 'shareholder'; document.querySelector('#previewCompanyOwnershipManifest').click(); true",
                "(() => { const row = document.querySelector('#companyIntelOwnershipManifestRows tr'); const compact = row ? Array.from(row.querySelectorAll('td')).slice(0, 3).map((cell) => cell.textContent).join('|') : ''; return document.querySelector('#companyIntelOwnershipManifestStatus').textContent.includes('预览') && document.querySelector('#companyIntelOwnershipManifestFileCount').textContent.includes('2') && document.querySelector('#companyIntelOwnershipManifestRows').textContent.includes('SPCX') && document.querySelector('#companyIntelOwnershipManifestRows').textContent.includes('DEMO') && compact.includes('事实股东') && !compact.includes('shareholder') && row?.textContent.includes('shareholder') && document.querySelector('#companyIntelOperationBox').textContent.includes('company-ownership-table-manifest'); })()",
                wait_timeout=max(timeout, 30.0),
            ),
            _run_check(
                client,
                "company_ownership_manifest_to_import_preview_real_api",
                "document.querySelector('#previewCompanyOwnershipImportFromManifest').click(); true",
                "(() => { const row = document.querySelector('#companyIntelOwnershipImportRows tr'); const compact = row ? Array.from(row.querySelectorAll('td')).slice(0, 3).map((cell) => cell.textContent).join('|') : ''; return document.querySelector('#companyIntelOwnershipImportStatus').textContent.includes('预览') && Number(document.querySelector('#companyIntelOwnershipCandidateCount').textContent.trim() || '0') >= 1 && document.querySelector('#companyIntelOwnershipImportRows').textContent.trim().length > 0 && compact.includes('DEMO-ownership') && !compact.includes('file_path') && !compact.includes('local structured ownership') && row?.textContent.includes('file_path') && row?.textContent.includes('local structured ownership') && document.querySelector('#companyIntelOperationBox').textContent.includes('股权表导入'); })()",
                wait_timeout=max(timeout, 30.0),
            ),
            _run_check(
                client,
                "company_ownership_import_execute_refreshes_review_queue",
                "document.querySelector('#runCompanyOwnershipImport').click(); true",
                "document.querySelector('#companyIntelOwnershipImportStatus').textContent.includes('已执行') && Number(document.querySelector('#companyIntelOwnershipCandidateCount').textContent.trim() || '0') >= 1",
                wait_timeout=max(timeout, 30.0),
            ),
            _run_check(
                client,
                "company_ownership_candidate_approve_promotes_graph_edge",
                "Promise.resolve((async () => { const ids = Array.from(document.querySelectorAll('#companyIntelRelationshipReviewRows [data-action=\"review-company-relationship\"][data-review-action=\"approve\"]')).map((button) => button.dataset.relationshipId).filter(Boolean); for (const id of ids) { await reviewCompanyRelationship(id, 'approve'); } return true; })())",
                "true",
                wait_timeout=max(timeout, 30.0),
            ),
            _run_check(
                client,
                "company_13f_holder_graph_click_loads_same_holder_network",
                "Promise.resolve((async () => { document.querySelector('#companyIntelSymbol').value = 'SPCX'; await loadCompanyIntelligence(false); const issuerId = latestCompanyIntelligence.resolution.issuer_ids[0]; const securityId = latestCompanyIntelligence.resolution.security_ids[0]; await api('/api/13f/holdings', {method:'POST', role:'data_engineer', body:{holding_id:'hold_acceptance_spcx_alpha', issuer_id:issuerId, security_id:securityId, source_id:'sec_edgar', filer_cik:'000HOLDER', filer_name:'Alpha Capital', report_period:'2026-03-31', shares:1000, value_usd:12000}}).catch((error) => { if (!String(error.message || '').includes('conflict')) throw error; }); await api('/api/13f/holdings', {method:'POST', role:'data_engineer', body:{holding_id:'hold_acceptance_demo_alpha', issuer_id:'issuer_demo', security_id:'security_demo_us', source_id:'sec_edgar', filer_cik:'000HOLDER', filer_name:'Alpha Capital', report_period:'2026-03-31', shares:2000, value_usd:22000}}).catch((error) => { if (!String(error.message || '').includes('conflict')) throw error; }); renderCompanyRelationshipContext({relationship_context:{focus_issuer_ids:[issuerId], summary:{shareholder_related_companies:1, shareholder_related_companies_total:1}, coverage_diagnostics:{shareholder_network_summary:{total:1, fact_network:0, holding_network:1}}, industry:{chain_nodes:[], peer_companies:[], upstream_companies:[], downstream_companies:[]}, ownership:{shareholders:[{holder_id:'000HOLDER', holder_key:'000HOLDER', holder_name:'Alpha Capital', issuer_id:issuerId, security_id:securityId, shares:1000, value_usd:12000, report_period:'2026-03-31'}], approved_relationships:[], relationship_candidates:[], relationships:[], approved_shareholder_related_companies:[], shareholder_related_companies:[{holder_id:'000HOLDER', holder_key:'000HOLDER', holder_name:'Alpha Capital', related_issuer_id:'issuer_demo', related_company:'Demo Holdings', security_id:'security_demo_us', shares:2000, value_usd:22000, report_period:'2026-03-31'}]}, dynamic_graph:{recommended_queries:[]}}}); const row = document.querySelector('#companyIntelRelationshipContextRows tr[data-action=\"open-relationship-graph\"][data-institutional-holder-key=\"000HOLDER\"]'); if (!row) throw new Error('13F holder graph row missing'); row.click(); return true; })())",
                "document.querySelector('[data-tab=\"entity\"]').classList.contains('active') && document.querySelector('#knowledgeGraphFilterChips').textContent.includes('13F持有人') && document.querySelector('#knowledgeGraphFilterChips').textContent.includes('Alpha Capital') && document.querySelector('#knowledgeGraphFilterChips [data-filter-key=\"institutionalHolderKey\"]')?.dataset.filterRawValue === '000HOLDER' && knowledgeGraphState.raw?.institutional_holdings?.some((item) => item.holding_id === 'hold_acceptance_spcx_alpha') && knowledgeGraphState.raw?.institutional_holdings?.some((item) => item.holding_id === 'hold_acceptance_demo_alpha') && knowledgeGraphState.raw?.edges?.some((item) => item.type === 'SAME_HOLDER_RELATED_COMPANY') && document.querySelector('#knowledgeGraphLinkCount').textContent !== '关系 0'",
                wait_timeout=max(timeout, 30.0),
            ),
            _run_check(
                client,
                "company_shareholder_row_has_holder_graph_attrs",
                "(() => { document.querySelector('[data-open=\"search\"]').click(); const row = Array.from(document.querySelectorAll('#companyIntelRelationshipContextRows tr[data-action=\"open-relationship-graph\"][data-institutional-holder-key=\"000HOLDER\"]')).find((item) => item.textContent.includes('股东/持有人') && item.textContent.includes('Alpha Capital')); if (!row) throw new Error('shareholder row holder graph attrs missing'); row.click(); return true; })()",
                "document.querySelector('[data-tab=\"entity\"]').classList.contains('active') && document.querySelector('#knowledgeGraphFilterChips').textContent.includes('13F持有人') && document.querySelector('#knowledgeGraphFilterChips [data-filter-key=\"institutionalHolderKey\"]')?.dataset.filterRawValue === '000HOLDER'",
                wait_timeout=max(timeout, 30.0),
            ),
            _run_check(
                client,
                "company_recommended_13f_holder_graph_query_click_loads_network",
                "Promise.resolve((async () => { document.querySelector('#companyIntelSymbol').value = 'SPCX'; await loadCompanyIntelligence(false); const row = Array.from(document.querySelectorAll('#companyIntelRelationshipContextRows tr[data-action=\"open-relationship-graph\"][data-institutional-holder-key=\"000HOLDER\"]')).find((item) => item.textContent.includes('图谱推荐入口')); if (!row) throw new Error('recommended 13F holder graph row missing'); row.click(); return true; })())",
                "document.querySelector('[data-tab=\"entity\"]').classList.contains('active') && document.querySelector('#knowledgeGraphFilterChips').textContent.includes('13F持有人') && document.querySelector('#knowledgeGraphFilterChips [data-filter-key=\"institutionalHolderKey\"]')?.dataset.filterRawValue === '000HOLDER' && knowledgeGraphState.raw?.institutional_holdings?.some((item) => item.holding_id === 'hold_acceptance_spcx_alpha') && knowledgeGraphState.raw?.institutional_holdings?.some((item) => item.holding_id === 'hold_acceptance_demo_alpha') && document.querySelector('#knowledgeGraphLinkCount').textContent !== '关系 0'",
                wait_timeout=max(timeout, 30.0),
            ),
            _run_check(
                client,
                "company_ownership_approved_same_holder_network_context",
                "Promise.resolve((async () => { const register = async (body) => api('/api/company-relationships', { method: 'POST', role: 'data_engineer', body }); await register({relationship_id:'rel_acceptance_demo_alpha_holder', issuer_id:'issuer_demo', security_id:'security_demo_us', subject_type:'company', subject_id:'issuer_demo', object_type:'company', object_id:'external_company_alpha_capital', relationship_type:'shareholder', relationship_status:'active', review_status:'approved', confidence:0.86, metadata:{entity_name:'Alpha Capital', source_layer:'browser_acceptance_fixture'}}); await register({relationship_id:'rel_acceptance_spcx_alpha_holder', issuer_id:latestCompanyIntelligence.resolution.issuer_ids[0], security_id:latestCompanyIntelligence.resolution.security_ids[0], subject_type:'company', subject_id:latestCompanyIntelligence.resolution.issuer_ids[0], object_type:'company', object_id:'external_company_alpha_capital', relationship_type:'shareholder', relationship_status:'active', review_status:'approved', confidence:0.84, metadata:{entity_name:'Alpha Capital', source_layer:'browser_acceptance_fixture'}}); document.querySelector('#companyIntelSymbol').value = 'SPCX'; await loadCompanyIntelligence(false); return true; })())",
                "document.querySelector('#companyIntelRelationshipContextRows').textContent.includes('事实股东关联') && document.querySelector('#companyIntelRelationshipContextRows').textContent.includes('Demo Holdings') && document.querySelector('#companyIntelRelationshipContextRows').textContent.includes('Alpha Capital') && document.querySelector('#companyIntelRelationshipContextRows [data-action=\"open-relationship-graph\"][data-ownership-holder-key=\"external_company_alpha_capital\"]') !== null && document.querySelector('#companyIntelShareholderRelatedCount').textContent.includes('事实 1') && document.querySelector('#companyIntelShareholderRelatedCount')?.dataset.factNetwork === '1' && Number(document.querySelector('#companyIntelShareholderRelatedCount')?.dataset.networkTotal || '0') >= 1 && document.querySelector('#companyIntelShareholderRelatedCount')?.title.includes('股东网络覆盖')",
                wait_timeout=max(timeout, 30.0),
            ),
            _run_check(
                client,
                "company_approved_relationship_row_click_loads_holder_network",
                "Promise.resolve((async () => { const row = Array.from(document.querySelectorAll('#companyIntelRelationshipContextRows tr[data-action=\"open-relationship-graph\"][data-ownership-holder-key=\"external_company_alpha_capital\"]')).find((item) => item.textContent.includes('事实股权关系') && item.textContent.includes('Alpha Capital')); if (!row) throw new Error('approved ownership row holder graph attrs missing'); row.click(); return true; })())",
                "document.querySelector('[data-tab=\"entity\"]').classList.contains('active') && document.querySelector('#knowledgeGraphFilterChips').textContent.includes('股东') && document.querySelector('#knowledgeGraphFilterChips').textContent.includes('Alpha Capital') && document.querySelector('#knowledgeGraphFilterChips [data-filter-key=\"ownershipHolderKey\"]')?.dataset.filterRawValue === 'external_company_alpha_capital' && knowledgeGraphState.raw?.company_relationships?.some((item) => item.relationship_id === 'rel_acceptance_spcx_alpha_holder') && knowledgeGraphState.raw?.company_relationships?.some((item) => item.relationship_id === 'rel_acceptance_demo_alpha_holder')",
                wait_timeout=max(timeout, 30.0),
            ),
            _run_check(
                client,
                "company_recommended_graph_query_click_loads_holder_network",
                "Promise.resolve((async () => { const row = Array.from(document.querySelectorAll('#companyIntelRelationshipContextRows tr[data-action=\"open-relationship-graph\"][data-ownership-holder-key=\"external_company_alpha_capital\"]')).find((item) => item.textContent.includes('图谱推荐入口')); if (!row) throw new Error('recommended holder graph row missing'); row.click(); return true; })())",
                "document.querySelector('[data-tab=\"entity\"]').classList.contains('active') && document.querySelector('#knowledgeGraphFilterChips').textContent.includes('股东') && document.querySelector('#knowledgeGraphFilterChips [data-filter-key=\"ownershipHolderKey\"]')?.dataset.filterRawValue === 'external_company_alpha_capital' && knowledgeGraphState.raw?.company_relationships?.some((item) => item.relationship_type === 'shareholder' && item.object_id === 'external_company_alpha_capital') && document.querySelector('#knowledgeGraphLinkCount').textContent !== '关系 0'",
                wait_timeout=max(timeout, 30.0),
            ),
            _run_check(
                client,
                "company_ownership_holder_key_graph_click_loads_same_holder_network",
                "(async () => { const issuerId = latestCompanyIntelligence.resolution.issuer_ids[0]; const response = await api(`/api/graph/query?issuer_id=${encodeURIComponent(issuerId)}&relationship_type=shareholder&ownership_holder_key=external_company_alpha_capital`, { role: 'analyst' }); openTab('entity'); setKnowledgeGraphActiveFilters({issuerId, relationshipType:'shareholder', ownershipHolderKey:'external_company_alpha_capital', ownershipHolderLabel:'Alpha Capital'}); renderKnowledgeGraph(response.data); return true; })()",
                "document.querySelector('[data-tab=\"entity\"]').classList.contains('active') && knowledgeGraphState.raw?.company_relationships?.some((item) => item.relationship_id === 'rel_acceptance_demo_alpha_holder') && knowledgeGraphState.raw?.company_relationships?.some((item) => item.relationship_id === 'rel_acceptance_spcx_alpha_holder') && knowledgeGraphState.raw?.edges?.some((item) => item.type === 'HAS_COMPANY_RELATIONSHIP' && item.from === 'issuer_demo' && item.relationship_type === 'shareholder') && knowledgeGraphState.raw?.edges?.some((item) => item.type === 'HAS_COMPANY_RELATIONSHIP' && item.from === 'issuer_spcx' && item.relationship_type === 'shareholder') && document.querySelector('#knowledgeGraphFilterChips').textContent.includes('股东') && document.querySelector('#knowledgeGraphFilterChips').textContent.includes('Alpha Capital') && !document.querySelector('#knowledgeGraphFilterChips').textContent.includes('external_company_alpha_capital') && document.querySelector('#knowledgeGraphFilterChips [data-filter-key=\"ownershipHolderKey\"]')?.dataset.filterRawValue === 'external_company_alpha_capital' && document.querySelector('#knowledgeGraphFilterChips [data-filter-key=\"ownershipHolderKey\"]')?.title.includes('external_company_alpha_capital') && document.querySelector('#knowledgeGraphLinkCount').textContent !== '关系 0'",
                wait_timeout=max(timeout, 30.0),
            ),
            _run_check(
                client,
                "company_ownership_approved_graph_filter_loads_shareholder_edge",
                "Promise.resolve((async () => { await openRelationshipGraphContext({issuerId: latestCompanyIntelligence.resolution.issuer_ids[0], relationshipType: 'shareholder'}); return true; })())",
                "(() => { const typeChip = document.querySelector('#knowledgeGraphFilterChips [data-filter-key=\"relationshipType\"]'); const edgeRow = Array.from(document.querySelectorAll('#graphEdgeRows tr')).find((row) => row.textContent.includes('shareholder') || row.textContent.includes('事实股东')); const compact = edgeRow ? Array.from(edgeRow.querySelectorAll('td')).slice(0, 3).map((cell) => cell.textContent).join('|') : ''; return document.querySelector('[data-tab=\"entity\"]').classList.contains('active') && compact.includes('事实股东') && !compact.includes('shareholder') && edgeRow?.textContent.includes('shareholder') && knowledgeGraphState.raw?.edges?.some((item) => item.relationship_type === 'shareholder') && typeChip?.textContent.includes('关系类型') && typeChip?.textContent.includes('事实股东') && !typeChip?.textContent.includes('shareholder') && typeChip?.dataset.filterRawValue === 'shareholder' && typeChip?.title.includes('shareholder') && document.querySelector('#knowledgeGraphLinkCount').textContent !== '关系 0'; })()",
                wait_timeout=max(timeout, 30.0),
            ),
            _run_check(
                client,
                "company_graph_inspector_neighbor_shows_relationship_label",
                "(() => { openTab('entity'); knowledgeGraphState.focusId = ''; knowledgeGraphState.selectedId = ''; knowledgeGraphState.search = ''; knowledgeGraphState.depth = 2; renderKnowledgeGraph({issuers:[{issuer_id:'issuer_demo', name:'Demo Co'},{issuer_id:'issuer_alpha', name:'Alpha Capital'}], securities:[], industry_chains:[], chain_nodes:[], company_positions:[], company_relationships:[], edges:[{from:'issuer_demo', to:'issuer_alpha', type:'HAS_COMPANY_RELATIONSHIP', relationship_type:'shareholder', confidence:0.91, source_id:'fixture_source'}]}); selectKnowledgeGraphNode('issuer_demo'); return true; })()",
                "(() => { const text = document.querySelector('#knowledgeGraphNeighborRows')?.textContent || ''; return text.includes('事实股东') && !text.includes('shareholder') && knowledgeGraphState.links.some((item) => item.meta?.relationship_type === 'shareholder'); })()",
                wait_timeout=max(timeout, 30.0),
            ),
            _run_check(
                client,
                "company_database_quality_reconcile_preview",
                "document.querySelector('#companyIntelSymbol').value = 'SPCX'; document.querySelector('#previewCompanyQualityReconcile').click(); true",
                "document.querySelector('#companyIntelQualityReconcileStatus').textContent.includes('预览') && document.querySelector('#companyIntelSourceQualityCount').textContent.trim().length > 0 && document.querySelector('#companyIntelQualityReconcileRows').textContent.trim().length > 0",
                wait_timeout=max(timeout, 20.0),
            ),
            _run_check(
                client,
                "company_database_batch_execute_records_run_history",
                "document.querySelector('#companyIntelSymbol').value = 'SPCX'; document.querySelector('#companyIntelBatchBuildStatus').textContent = '等待'; document.querySelector('#companyIntelRunRows').innerHTML = ''; document.querySelector('#runCompanyBatchBuild').click(); true",
                "document.querySelector('#companyIntelBatchBuildStatus').textContent.includes('已执行') && document.querySelector('#companyIntelRunHistoryStatus').textContent.trim().length > 0 && document.querySelector('#companyIntelRunHistoryStatus').textContent !== '待载入' && document.querySelector('#companyIntelRunRows').textContent.includes('已执行') && document.querySelector('#companyIntelRunRows').textContent.includes('本地补库历史')",
                wait_timeout=max(timeout, 30.0),
            ),
            _run_check(
                client,
                "company_database_run_retry_preview",
                "document.querySelector('#companyIntelRunRows [data-action=\"retry-company-build-run\"][data-execute=\"false\"]')?.click(); true",
                "document.querySelector('#companyIntelRunHistoryStatus').textContent.trim().length > 0 && document.querySelector('#companyIntelRunRows').textContent.includes('重试源') && document.querySelector('#companyIntelRunRows').textContent.includes('预览')",
                wait_timeout=max(timeout, 30.0),
            ),
            _run_check(
                client,
                "company_database_coverage_trends_load",
                "document.querySelector('#loadCompanyCoverageTrends').click(); true",
                "document.querySelector('#companyIntelTrendStatus').textContent.includes('已载入') && document.querySelector('#companyIntelTrendRows').textContent.includes('本地补库历史') && document.querySelector('#companyIntelTrendDelta').textContent.trim().length > 0 && !document.querySelector('#companyIntelOperationBox').textContent.includes('trend_rows')",
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
                "company_intelligence_cycle_preview",
                "document.querySelector('#previewCompanyIntelCycle').click(); true",
                "document.querySelector('#companyIntelCycleStatus').textContent.includes('预览') && document.querySelector('#companyIntelCycleDelta').textContent.trim().length > 0 && document.querySelector('#companyIntelCycleFeedbackCount').textContent.trim().length > 0 && document.querySelector('#status').textContent.includes('公司情报闭环刷新预览完成') && document.querySelector('#status').textContent.includes('反馈')",
                wait_timeout=max(timeout, 30.0),
            ),
            _run_check(
                client,
                "portfolio_proposal_loads_latest",
                "document.querySelector('[data-open=\"committee\"]').click(); document.querySelector('#loadPortfolioProposal').click(); true",
                "document.querySelector('[data-tab=\"committee\"]').classList.contains('active') && document.querySelector('#portfolioProposalBox').textContent.includes('组合方案') && document.querySelector('#portfolioProposalBox').textContent.includes('组合权重') && document.querySelector('#portfolioFeedbackDecision').textContent.includes('已载入')",
            ),
            _run_check(
                client,
                "latest_analysis_company_intelligence_chain_visible",
                "document.querySelector('[data-open=\"dashboard\"]').click(); true",
                "document.querySelector('[data-tab=\"dashboard\"]').classList.contains('active') && document.querySelector('#companyIntelligenceRows')?.textContent.trim().length > 0 && document.querySelector('#companyIntelCount')?.textContent.trim().length > 0 && document.querySelector('#companyIntelArtifact')?.textContent.trim().length > 0",
                wait_timeout=max(timeout, 45.0),
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
