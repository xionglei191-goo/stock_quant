from __future__ import annotations

import argparse
import json
import shutil
import socket
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "artifacts" / "ui-graph-layout-acceptance.json"


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


def _post_json(url: str, payload: dict[str, Any], *, timeout: float = 8.0) -> Any:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-Role": "analyst",
            "X-Actor": "ui_graph_layout_acceptance",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _graph_readiness_probe(base_url: str, *, symbol: str, timeout: float) -> dict[str, Any]:
    payload = {
        "issuer_id": symbol if str(symbol).startswith("issuer_") else "",
        "symbol": "" if str(symbol).startswith("issuer_") else symbol,
        "record_readiness": False,
    }
    try:
        data = _post_json(f"{base_url.rstrip('/')}/api/graph/knowledge-network/readiness", payload, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 - acceptance artifact should record probe failures
        return {"status": "probe_failed", "error": str(exc), "payload": payload}
    return {
        "status": data.get("status"),
        "ready_for_obsidian_exploration": bool(data.get("ready_for_obsidian_exploration")),
        "present_layers": data.get("present_layers", []),
        "missing_layers": data.get("missing_layers", []),
        "thin_layers": data.get("thin_layers", []),
        "visible_communities": data.get("visible_communities", []),
        "graph_summary": data.get("graph_summary", {}),
        "cross_links": data.get("cross_links", {}),
        "seed_dependency": data.get("seed_dependency", {}),
        "next_actions": [
            item
            for item in data.get("next_actions", []) or []
            if isinstance(item, dict) and item.get("layer") in {"seed_dependency", "evidence", "document", "company_event", "viewpoint", "research_report"}
        ][:8],
        "usage_boundary": data.get("usage_boundary", ""),
        "automation_allowed": data.get("automation_allowed"),
        "live_execution_allowed": data.get("live_execution_allowed"),
    }


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
    import base64
    import hashlib

    magic = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
    digest = hashlib.sha1((key + magic).encode("ascii")).digest()
    return base64.b64encode(digest).decode("ascii")


class DevToolsClient:
    def __init__(self, websocket_url: str, *, timeout: float = 8.0) -> None:
        parsed = urllib.parse.urlparse(websocket_url)
        self.host = parsed.hostname or "127.0.0.1"
        self.port = int(parsed.port or 80)
        self.path = parsed.path
        if parsed.query:
            self.path += "?" + parsed.query
        self.timeout = timeout
        self.sock = socket.create_connection((self.host, self.port), timeout=timeout)
        self.sock.settimeout(timeout)
        import base64

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
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.extend([0x80 | 126, (length >> 8) & 0xFF, length & 0xFF])
        else:
            header.append(0x80 | 127)
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
        if "exceptionDetails" in result:
            raise RuntimeError(str(result["exceptionDetails"]))
        return result.get("result", {}).get("value")


def run_graph_layout_acceptance(
    base_url: str,
    *,
    symbol: str = "AAPL",
    scope: str = "local",
    output: str | Path = DEFAULT_OUTPUT,
    chrome_bin: str = "",
    timeout: float = 45.0,
    viewport_width: int = 1600,
    viewport_height: int = 950,
    expect_mobile_layout: bool = False,
    emulate_reduced_motion: bool = False,
    expect_reduced_motion: bool = False,
    expect_redundant_node_encoding: bool = False,
    max_overlap_pairs: int = 3,
    max_near_edge_nodes: int = 0,
    min_nodes: int = 32,
    min_links: int = 60,
    max_visible_nodes: int = 0,
    max_visible_links: int = 0,
    max_link_label_dom_count: int = 0,
    min_fps: float = 20.0,
    max_frame_ms: float = 35.0,
    min_community_labels: int = 2,
    min_visible_communities: int = 0,
    min_community_spread_ratio: float = 0.0,
    min_industry_nodes: int = 0,
    min_raw_knowledge_nodes: int = 0,
    min_visible_knowledge_types: int = 0,
    min_raw_structured_reports: int = 0,
    min_expansion_neighbor_delta: int = 1,
    min_visible_neighbors_after_click: int = 2,
    relationship_type: str = "",
    chain_id: str = "",
    chain_node_id: str = "",
    ownership_holder_key: str = "",
    institutional_holder_key: str = "",
    min_filtered_relationships: int = 0,
    expect_filter_chip: str = "",
    forbid_filter_chip: str = "",
    check_persistence: bool = False,
    check_path: bool = False,
    check_focus_switch: bool = False,
    check_view_controls: bool = True,
    check_trail: bool = True,
    check_saved_subgraph: bool = True,
    check_share_view: bool = False,
    expect_performance_mode: str = "",
    max_chain_node_splits: int = 0,
    check_readiness: bool = True,
    require_non_seed_readiness: bool = False,
) -> dict[str, Any]:
    chrome = _chrome_binary(chrome_bin)
    port = _free_port()
    scope = "global" if scope == "global" else "local"
    ui_url = base_url.rstrip("/") + "/ui"
    process = subprocess.Popen(
        [
            chrome,
            "--headless=new",
            "--no-sandbox",
            "--disable-gpu",
            "--hide-scrollbars",
            f"--window-size={viewport_width},{viewport_height}",
            f"--remote-debugging-port={port}",
            ui_url,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    client: DevToolsClient | None = None
    try:
        _wait_for_debugger(port, timeout=timeout)
        tabs = _http_json(f"http://127.0.0.1:{port}/json", timeout=5.0)
        page_tab = next(
            (
                tab
                for tab in tabs
                if tab.get("type") == "page" and str(tab.get("url", "")).rstrip("/") == ui_url.rstrip("/")
            ),
            None,
        )
        if page_tab is None:
            page_tab = next((tab for tab in tabs if tab.get("type") == "page"), tabs[0])
        websocket_url = page_tab["webSocketDebuggerUrl"]
        client = DevToolsClient(websocket_url, timeout=timeout)
        if emulate_reduced_motion:
            client.call(
                "Emulation.setEmulatedMedia",
                {
                    "features": [
                        {"name": "prefers-reduced-motion", "value": "reduce"},
                    ],
                },
            )
            client.call("Page.reload", {"ignoreCache": True})
            time.sleep(1.0)
        expression = f"""
            (async () => {{
              const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
              const waitFor = async (selector, timeoutMs = 12000) => {{
                const deadline = Date.now() + timeoutMs;
                while (Date.now() < deadline) {{
                  const element = document.querySelector(selector);
                  if (element) return element;
                  await wait(150);
                }}
                return null;
              }};
              const waitForApp = async (timeoutMs = 12000) => {{
                const deadline = Date.now() + timeoutMs;
                while (Date.now() < deadline) {{
                  if (typeof openTab === 'function' && typeof loadEntity === 'function') return true;
                  await wait(150);
                }}
                return false;
              }};
              await waitFor('button', 12000);
              await waitForApp(12000);
              const isVisible = (el) => !!(el && (el.offsetWidth || el.offsetHeight || el.getClientRects().length));
              if (typeof openTab === 'function') {{
                openTab('entity', {{ mode: 'personal' }});
              }} else {{
                const graphButton = [...document.querySelectorAll('button')]
                  .find((el) => isVisible(el) && el.dataset?.open === 'entity' && (el.textContent || '').trim() === '知识图谱')
                  || [...document.querySelectorAll('button')].find((el) => isVisible(el) && (el.textContent || '').trim() === '知识图谱');
                if (graphButton) graphButton.click();
              }}
              const input = await waitFor('#issuerId', 12000);
              if (!input) return {{ status: 'failed', error: 'missing issuerId input' }};
              input.value = {json.dumps(symbol)};
              if (window.knowledgeGraphState) {{
                window.knowledgeGraphState.pendingFilters = {{
                  relationshipType: {json.dumps(relationship_type)},
                  chainId: {json.dumps(chain_id)},
                  chainNodeId: {json.dumps(chain_node_id)},
                  ownershipHolderKey: {json.dumps(ownership_holder_key)},
                  institutionalHolderKey: {json.dumps(institutional_holder_key)}
                }};
              }}
              if (typeof loadEntity === 'function') {{
                await loadEntity();
              }} else {{
                document.querySelector('#loadEntity')?.click();
              }}
              const scopeSelect = document.querySelector('#graphScope');
              if (scopeSelect) {{
                scopeSelect.value = {json.dumps(scope)};
                scopeSelect.dispatchEvent(new Event('change', {{ bubbles: true }}));
              }}
              const svg = await waitFor('#knowledgeGraphCanvas', 12000);
              if (!svg) return {{ status: 'failed', error: 'missing graph svg' }};
              const visibleSvg = await (async () => {{
                const deadline = Date.now() + 12000;
                while (Date.now() < deadline) {{
                  const rect = svg.getBoundingClientRect();
                  if (rect.width > 200 && rect.height > 200 && document.querySelectorAll('.graph-node-svg').length > 0) return true;
                  await wait(250);
                }}
                return false;
              }})();
              if (!visibleSvg) {{
                const rect = svg.getBoundingClientRect();
                return {{
                  status: 'failed',
                  error: 'graph did not become visible',
                  rect: {{ width: rect.width, height: rect.height }},
                  node_count_text: document.querySelector('#knowledgeGraphNodeCount')?.textContent || ''
                }};
              }}
              const rect = svg.getBoundingClientRect();
              const graphExplorerElement = document.querySelector('.graph-explorer');
              const graphStageElement = document.querySelector('.graph-stage');
              const graphInspectorElement = document.querySelector('.graph-inspector');
              const explorerBox = graphExplorerElement?.getBoundingClientRect?.() || {{ left: 0, top: 0, width: 0, height: 0, right: 0, bottom: 0 }};
              const stageBox = graphStageElement?.getBoundingClientRect?.() || {{ left: 0, top: 0, width: 0, height: 0, right: 0, bottom: 0 }};
              const inspectorBox = graphInspectorElement?.getBoundingClientRect?.() || {{ left: 0, top: 0, width: 0, height: 0, right: 0, bottom: 0 }};
              const responsiveLayout = {{
                viewport_width: window.innerWidth,
                viewport_height: window.innerHeight,
                explorer_width: Number(explorerBox.width.toFixed(1)),
                stage_width: Number(stageBox.width.toFixed(1)),
                stage_height: Number(stageBox.height.toFixed(1)),
                svg_width: Number(rect.width.toFixed(1)),
                svg_height: Number(rect.height.toFixed(1)),
                inspector_width: Number(inspectorBox.width.toFixed(1)),
                inspector_height: Number(inspectorBox.height.toFixed(1)),
                inspector_below_stage: inspectorBox.top >= stageBox.bottom - 2,
                stage_overflows_viewport: stageBox.right > window.innerWidth + 1 || stageBox.left < -1,
                inspector_overflows_viewport: inspectorBox.right > window.innerWidth + 1 || inspectorBox.left < -1,
                explorer_columns: getComputedStyle(graphExplorerElement).gridTemplateColumns,
                toolbar_overflows_viewport: Boolean([...document.querySelectorAll('.graph-toolbar, .graph-toolbar .row, .graph-filter-row, .graph-view-actions')].some((element) => {{
                  const box = element.getBoundingClientRect();
                  return box.right > window.innerWidth + 1 || box.left < -1;
                }}))
              }};
              await wait(3600);
              const readNodes = () => [...document.querySelectorAll('.graph-node-svg')].map((el) => {{
                const match = /translate\\(([-0-9.]+) ([-0-9.]+)\\)/.exec(el.getAttribute('transform') || '');
                const circle = el.querySelector('circle[fill]') || el.querySelector('circle');
                const stateNode = window.knowledgeGraphState?.nodes?.find?.((item) => item.id === el.getAttribute('data-node-id')) || {{}};
                const typeCodeEl = el.querySelector('.graph-node-type-code');
                return {{
                  id: el.getAttribute('data-node-id'),
                  x: Number(match?.[1] || 0),
                  y: Number(match?.[2] || 0),
                  r: Number(circle?.getAttribute('r') || 0),
                  type: stateNode.type || '',
                  community: stateNode.community || '',
                  type_code: el.getAttribute('data-type-code') || '',
                  type_code_text: (typeCodeEl?.textContent || '').trim(),
                  has_type_code: Boolean(typeCodeEl && (typeCodeEl.textContent || '').trim()),
                  label: el.classList.contains('has-label'),
                  expanded: el.classList.contains('is-expanded'),
                  hidden_neighbors: Number(stateNode.hiddenNeighborCount || 0)
                }};
              }});
              const visibleNeighborCount = (nodeId) => {{
                const visibleIds = new Set([...document.querySelectorAll('.graph-node-svg')].map((el) => el.getAttribute('data-node-id')));
                return (window.knowledgeGraphState?.links || []).filter((link) =>
                  (link.source === nodeId && visibleIds.has(link.target)) || (link.target === nodeId && visibleIds.has(link.source))
                ).length;
              }};
              const nodes = readNodes();
              let overlapPairs = 0;
              for (let i = 0; i < nodes.length; i += 1) {{
                for (let j = i + 1; j < nodes.length; j += 1) {{
                  const d = Math.hypot(nodes[i].x - nodes[j].x, nodes[i].y - nodes[j].y);
                  if (d < nodes[i].r + nodes[j].r + 4) overlapPairs += 1;
                }}
              }}
              const nearEdgeNodes = nodes.filter((n) => n.x < 75 || n.y < 75 || n.x > rect.width - 75 || n.y > rect.height - 75).length;
              const visibleTypes = [...new Set(nodes.map((item) => item.type).filter(Boolean))];
              const encodedNodeTypes = [...new Set(nodes.filter((item) => item.has_type_code && item.type_code && item.type_code === item.type_code_text).map((item) => item.type).filter(Boolean))];
              const legendEncodings = [...document.querySelectorAll('#knowledgeGraphLegend [data-node-type]')].map((el) => ({{
                type: el.getAttribute('data-node-type') || '',
                code: el.getAttribute('data-type-code') || '',
                text: (el.querySelector('.graph-legend-code')?.textContent || '').trim(),
                label: (el.textContent || '').trim()
              }})).filter((item) => item.type);
              const legendEncodingTypes = [...new Set(legendEncodings.filter((item) => item.code && item.code === item.text).map((item) => item.type))];
              const initialGraphSnapshot = {{
                nodes: nodes.length,
                links: document.querySelectorAll('.graph-link-svg').length,
                labels: document.querySelectorAll('.graph-node-svg.has-label').length,
                community_labels: document.querySelectorAll('.graph-community-label').length,
                community_quality_labels: [...document.querySelectorAll('.graph-community-label')].filter((el) => /密度\\d+% · 强度\\d+ · 强边\\d+%/.test(el.textContent || '')).length,
                visible_node_types: visibleTypes,
                encoded_node_types: encodedNodeTypes,
                legend_encoded_types: legendEncodingTypes,
                legend_encodings: legendEncodings,
                missing_node_type_codes: visibleTypes.filter((type) => !encodedNodeTypes.includes(type)),
                missing_legend_type_codes: visibleTypes.filter((type) => !legendEncodingTypes.includes(type)),
                near_edge_nodes: nearEdgeNodes,
                overlap_pairs: overlapPairs,
                link_label_dom_count: Number(window.knowledgeGraphState?.renderStats?.linkLabelDomCount ?? document.querySelectorAll('.graph-link-label').length),
                render_stats: window.knowledgeGraphState?.renderStats || {{}},
              }};
              const communityBuckets = new Map();
              nodes.filter((node) => node.community).forEach((node) => {{
                const bucket = communityBuckets.get(node.community) || {{ community: node.community, count: 0, x: 0, y: 0 }};
                bucket.count += 1;
                bucket.x += node.x;
                bucket.y += node.y;
                communityBuckets.set(node.community, bucket);
              }});
              const communityCentroids = [...communityBuckets.values()]
                .filter((bucket) => bucket.count > 0)
                .map((bucket) => ({{
                  community: bucket.community,
                  count: bucket.count,
                  x: Number((bucket.x / bucket.count).toFixed(2)),
                  y: Number((bucket.y / bucket.count).toFixed(2))
                }}))
                .sort((a, b) => a.community.localeCompare(b.community));
              const communityDistances = [];
              for (let i = 0; i < communityCentroids.length; i += 1) {{
                for (let j = i + 1; j < communityCentroids.length; j += 1) {{
                  communityDistances.push(Math.hypot(
                    communityCentroids[i].x - communityCentroids[j].x,
                    communityCentroids[i].y - communityCentroids[j].y
                  ));
                }}
              }}
              const communityScale = Math.max(1, Math.min(rect.width, rect.height));
              const avgCommunityDistance = communityDistances.length
                ? communityDistances.reduce((sum, distance) => sum + distance, 0) / communityDistances.length
                : 0;
              const minCommunityDistance = communityDistances.length ? Math.min(...communityDistances) : 0;
              const perfBeforeInteractions = {{
                frames: Number(window.knowledgeGraphState?.perf?.frames || 0),
                fps: Number(window.knowledgeGraphState?.perf?.fps || 0),
                avg_frame_ms: Number(window.knowledgeGraphState?.perf?.avgFrameMs || 0),
                worst_frame_ms: Number(window.knowledgeGraphState?.perf?.worstFrameMs || 0),
                status: document.querySelector('#knowledgeGraphMotionStatus')?.textContent || ''
              }};
              const reducedMotion = {{
                matches: Boolean(window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches),
                dynamic: Boolean(window.knowledgeGraphState?.dynamic),
                reduced_state: Boolean(window.knowledgeGraphState?.reducedMotion),
                motion_override: Boolean(window.knowledgeGraphState?.motionOverride),
                frame_id: Number(window.knowledgeGraphState?.frameId || 0),
                status: document.querySelector('#knowledgeGraphMotionStatus')?.textContent || '',
                button_text: document.querySelector('#graphToggleDynamic')?.textContent || ''
              }};
              const visibleTextTargets = [
                '#knowledgeGraphCanvas text',
                '#knowledgeGraphNodeTitle',
                '#knowledgeGraphNodeType',
                '#knowledgeGraphNodeMeta',
                '#knowledgeGraphNeighborRows',
                '#knowledgeGraphPathSteps',
                '#knowledgeGraphTrailList',
                '#knowledgeGraphFocusHistoryList',
                '#knowledgeGraphFocusLabel',
                '#knowledgeGraphMotionStatus'
              ];
              const visibleTextsForRawCheck = () => visibleTextTargets.flatMap((selector) =>
                [...document.querySelectorAll(selector)].map((el) => (el.textContent || '').trim()).filter(Boolean)
              );
              const rawTextPattern = /\\b(md_|market_data_summary:|doc_obsidian|hold_obsidian|pos_obsidian|srr_obsidian|rr_obsidian|vp_obsidian|event_obsidian|rel_obsidian|VIEWPOINT_ON_COMPANY|RELATIONSHIP|[a-f0-9]{{12,}}\\s+main)\\b/i;
              const focusId = window.knowledgeGraphState?.focusId || nodes.find((n) => n.id)?.id || '';
              let rawTextProbe = {{ checked: false }};
              const marketProbeNode = nodes.find((node) => node.type === 'market_data');
              if (marketProbeNode?.id && window.CSS?.escape) {{
                const targetNode = document.querySelector(`.graph-node-svg[data-node-id="${{CSS.escape(marketProbeNode.id)}}"]`);
                if (targetNode) {{
                  const box = targetNode.getBoundingClientRect();
                  const cx = box.left + box.width / 2;
                  const cy = box.top + box.height / 2;
                  targetNode.dispatchEvent(new PointerEvent('pointerdown', {{ bubbles: true, pointerId: 9881, clientX: cx, clientY: cy, pointerType: 'mouse', isPrimary: true }}));
                  targetNode.dispatchEvent(new PointerEvent('pointerup', {{ bubbles: true, pointerId: 9881, clientX: cx, clientY: cy, pointerType: 'mouse', isPrimary: true }}));
                  targetNode.dispatchEvent(new MouseEvent('click', {{ bubbles: true, clientX: cx, clientY: cy }}));
                  await wait(400);
                  const probeTexts = visibleTextsForRawCheck();
                  rawTextProbe = {{
                    checked: true,
                    node_id: marketProbeNode.id,
                    selected_id: window.knowledgeGraphState?.selectedId || '',
                    raw_label_text_leaks: [...new Set(probeTexts.filter((text) => rawTextPattern.test(text)))].slice(0, 20)
                  }};
                  const focusNode = document.querySelector(`.graph-node-svg[data-node-id="${{CSS.escape(focusId)}}"]`);
                  if (focusNode) {{
                    const focusBox = focusNode.getBoundingClientRect();
                    const fx = focusBox.left + focusBox.width / 2;
                    const fy = focusBox.top + focusBox.height / 2;
                    focusNode.dispatchEvent(new PointerEvent('pointerdown', {{ bubbles: true, pointerId: 9882, clientX: fx, clientY: fy, pointerType: 'mouse', isPrimary: true }}));
                    focusNode.dispatchEvent(new PointerEvent('pointerup', {{ bubbles: true, pointerId: 9882, clientX: fx, clientY: fy, pointerType: 'mouse', isPrimary: true }}));
                    focusNode.dispatchEvent(new MouseEvent('click', {{ bubbles: true, clientX: fx, clientY: fy }}));
                    await wait(400);
                  }}
                }}
              }}
              const firstExpandableNode = nodes
                .filter((n) => n.id && n.id !== focusId && !n.expanded)
                .sort((a, b) =>
                  Number(b.hidden_neighbors > 0) - Number(a.hidden_neighbors > 0)
                  || Number(['event', 'research', 'evidence'].includes(b.type)) - Number(['event', 'research', 'evidence'].includes(a.type))
                  || b.hidden_neighbors - a.hidden_neighbors
                )[0] || nodes.find((n) => n.id && n.id !== focusId);
              const firstExpandable = firstExpandableNode?.id || '';
              const visibleNeighborsBeforeClick = firstExpandable ? visibleNeighborCount(firstExpandable) : 0;
              const nodesBeforeClick = nodes.length;
              const linksBeforeClick = document.querySelectorAll('.graph-link-svg').length;
              if (firstExpandable && window.CSS?.escape) {{
                const targetNode = document.querySelector(`.graph-node-svg[data-node-id="${{CSS.escape(firstExpandable)}}"]`);
                if (targetNode) {{
                  const box = targetNode.getBoundingClientRect();
                  const cx = box.left + box.width / 2;
                  const cy = box.top + box.height / 2;
                  targetNode.dispatchEvent(new PointerEvent('pointerdown', {{ bubbles: true, pointerId: 9871, clientX: cx, clientY: cy, pointerType: 'mouse', isPrimary: true }}));
                  targetNode.dispatchEvent(new PointerEvent('pointerup', {{ bubbles: true, pointerId: 9871, clientX: cx, clientY: cy, pointerType: 'mouse', isPrimary: true }}));
                  targetNode.dispatchEvent(new MouseEvent('click', {{ bubbles: true, clientX: cx, clientY: cy }}));
                }}
              }}
              await wait(2200);
              const nodesAfterClick = readNodes();
              const linksAfterClick = document.querySelectorAll('.graph-link-svg').length;
              const expansionCheck = {{
                node_id: firstExpandable,
                node_type: firstExpandableNode?.type || '',
                focus_before: focusId,
                focus_after: window.knowledgeGraphState?.focusId || '',
                hidden_neighbors_before: firstExpandableNode?.hidden_neighbors || 0,
                visible_neighbors_before: visibleNeighborsBeforeClick,
                visible_neighbors_after: firstExpandable ? visibleNeighborCount(firstExpandable) : 0,
                nodes_before: nodesBeforeClick,
                nodes_after: nodesAfterClick.length,
                node_delta: nodesAfterClick.length - nodesBeforeClick,
                links_before: linksBeforeClick,
                links_after: linksAfterClick,
                link_delta: linksAfterClick - linksBeforeClick,
                selected_id: window.knowledgeGraphState?.selectedId || '',
                expanded: Boolean(window.knowledgeGraphState?.expandedIds?.has?.(firstExpandable))
              }};
              expansionCheck.neighbor_delta = expansionCheck.visible_neighbors_after - expansionCheck.visible_neighbors_before;
              let viewControls = {{ checked: false }};
              if ({json.dumps(check_view_controls)}) {{
                const before = {{
                  x: Number(window.knowledgeGraphState?.transform?.x || 0),
                  y: Number(window.knowledgeGraphState?.transform?.y || 0),
                  scale: Number(window.knowledgeGraphState?.transform?.scale || 1)
                }};
                document.querySelector('#graphZoomIn')?.click();
                await wait(250);
                const afterZoomIn = {{
                  x: Number(window.knowledgeGraphState?.transform?.x || 0),
                  y: Number(window.knowledgeGraphState?.transform?.y || 0),
                  scale: Number(window.knowledgeGraphState?.transform?.scale || 1)
                }};
                document.querySelector('#graphZoomOut')?.click();
                await wait(250);
                document.querySelector('#graphFitView')?.click();
                await wait(350);
                const afterFit = {{
                  x: Number(window.knowledgeGraphState?.transform?.x || 0),
                  y: Number(window.knowledgeGraphState?.transform?.y || 0),
                  scale: Number(window.knowledgeGraphState?.transform?.scale || 1)
                }};
                document.querySelector('#graphCenterFocus')?.click();
                await wait(350);
                const afterCenter = {{
                  x: Number(window.knowledgeGraphState?.transform?.x || 0),
                  y: Number(window.knowledgeGraphState?.transform?.y || 0),
                  scale: Number(window.knowledgeGraphState?.transform?.scale || 1)
                }};
                viewControls = {{
                  checked: true,
                  buttons: ['graphZoomOut', 'graphZoomIn', 'graphFitView', 'graphCenterFocus'].filter((id) => Boolean(document.querySelector(`#${{id}}`))).length,
                  before,
                  after_zoom_in: afterZoomIn,
                  after_fit: afterFit,
                  after_center: afterCenter,
                  status: document.querySelector('#knowledgeGraphMotionStatus')?.textContent || ''
                }};
              }}
              let persistence = {{ checked: false }};
              if ({json.dumps(check_persistence)}) {{
                const draggableId = nodes.find((n) => n.id && n.id !== focusId)?.id || '';
                if (draggableId) {{
                  const node = window.knowledgeGraphState?.nodes?.find?.((item) => item.id === draggableId);
                  if (node && window.knowledgeGraphState) {{
                    const before = {{ x: node.x, y: node.y }};
                    node.x = Math.min(rect.width - 140, node.x + 37);
                    node.y = Math.min(rect.height - 140, node.y + 29);
                    node.vx = 0;
                    node.vy = 0;
                    window.knowledgeGraphState.fixedIds.add(draggableId);
                    window.knowledgeGraphState.positions[draggableId] = {{ x: node.x, y: node.y, vx: 0, vy: 0 }};
                    if (typeof saveKnowledgeGraphLayout === 'function') saveKnowledgeGraphLayout();
                    const storageKey = window.knowledgeGraphState.layoutKey;
                    if (typeof rerenderKnowledgeGraphExplorer === 'function') rerenderKnowledgeGraphExplorer();
                    await wait(900);
                    const restored = window.knowledgeGraphState.nodes.find((item) => item.id === draggableId);
                    persistence = {{
                      checked: true,
                      node_id: draggableId,
                      storage_key: storageKey,
                      stored: Boolean(storageKey && window.localStorage?.getItem(storageKey)),
                      fixed_after_reload: window.knowledgeGraphState.fixedIds.has(draggableId),
                      dx: Math.abs((restored?.x || 0) - (before.x + 37)),
                      dy: Math.abs((restored?.y || 0) - (before.y + 29))
                    }};
                    if (storageKey) window.localStorage?.removeItem(storageKey);
                  }}
                }}
              }}
              let pathCheck = {{ checked: false }};
              if ({json.dumps(check_path)}) {{
                const startId = focusId;
                const endId = nodes.find((n) => n.id && n.id !== startId)?.id || '';
                if (endId && window.knowledgeGraphState) {{
                  window.knowledgeGraphState.pathStartId = startId;
                  window.knowledgeGraphState.pathEndId = endId;
                  if (typeof refreshKnowledgeGraphPath === 'function') refreshKnowledgeGraphPath();
                  await wait(400);
                  pathCheck = {{
                    checked: true,
                    start_id: startId,
                    end_id: endId,
                    path_nodes: document.querySelectorAll('.graph-node-svg.is-path-node').length,
                    path_links: document.querySelectorAll('.graph-link-svg.is-path-link').length,
                    path_link_labels: document.querySelectorAll('.graph-link-label.is-path-link').length,
                    next_hops: document.querySelectorAll('.graph-next-hop').length,
                    next_hop_node_types: Array.from(document.querySelectorAll('.graph-next-hop')).map((item) => window.knowledgeGraphState?.nodeById?.get(item.dataset.nodeId)?.type || ''),
                    summary: document.querySelector('#knowledgeGraphPathSummary')?.textContent || ''
                  }};
                  const nextHop = document.querySelector('.graph-next-hop');
                  if (nextHop) {{
                    nextHop.click();
                    await wait(900);
                    pathCheck.after_next_hop_path_nodes = document.querySelectorAll('.graph-node-svg.is-path-node').length;
                    pathCheck.after_next_hop_path_links = document.querySelectorAll('.graph-link-svg.is-path-link').length;
                    pathCheck.after_next_hop_path_link_labels = document.querySelectorAll('.graph-link-label.is-path-link').length;
                  }}
                }}
              }}
              let focusSwitch = {{ checked: false }};
              if ({json.dumps(check_focus_switch)}) {{
                if (focusId && window.knowledgeGraphState?.focusId !== focusId) {{
                  switchKnowledgeGraphFocusNode(focusId);
                  await wait(1200);
                }}
                const beforeFocusId = window.knowledgeGraphState?.focusId || '';
                const visibleFocusNodeIds = new Set([...document.querySelectorAll('.graph-node-svg')].map((element) => element.getAttribute('data-node-id')));
                const visibleFocusNeighbors = (window.knowledgeGraphState?.links || [])
                  .map((link) => {{
                    if (link.source === beforeFocusId && visibleFocusNodeIds.has(link.target)) return window.knowledgeGraphState?.nodeById?.get?.(link.target);
                    if (link.target === beforeFocusId && visibleFocusNodeIds.has(link.source)) return window.knowledgeGraphState?.nodeById?.get?.(link.source);
                    return null;
                  }})
                  .filter(Boolean);
                const knowledgeFocusTarget = visibleFocusNeighbors.find((item) =>
                  item.id && item.id !== beforeFocusId && (['event', 'research', 'evidence'].includes(item.type) || ['research', 'evidence'].includes(item.community))
                );
                const focusTarget = knowledgeFocusTarget
                  || visibleFocusNeighbors.find((item) => item.id && item.id !== beforeFocusId)
                  || (window.knowledgeGraphState?.nodes || []).find((item) =>
                    item.id && item.id !== beforeFocusId && visibleFocusNodeIds.has(item.id) && (['event', 'research', 'evidence'].includes(item.type) || ['research', 'evidence'].includes(item.community))
                  )
                  || (window.knowledgeGraphState?.nodes || []).find((item) => item.id && item.id !== beforeFocusId && visibleFocusNodeIds.has(item.id));
                if (focusTarget && window.CSS?.escape) {{
                  const targetElement = document.querySelector(`.graph-node-svg[data-node-id="${{CSS.escape(focusTarget.id)}}"]`);
                  const targetBox = targetElement?.getBoundingClientRect?.();
                  const targetX = targetBox ? targetBox.left + targetBox.width / 2 : 0;
                  const targetY = targetBox ? targetBox.top + targetBox.height / 2 : 0;
                  if (targetElement && targetBox) {{
                    targetElement.dispatchEvent(new PointerEvent('pointerdown', {{ bubbles: true, pointerId: 7301, clientX: targetX, clientY: targetY, pointerType: 'mouse', isPrimary: true }}));
                    targetElement.dispatchEvent(new PointerEvent('pointerup', {{ bubbles: true, pointerId: 7301, clientX: targetX, clientY: targetY, pointerType: 'mouse', isPrimary: true }}));
                    targetElement.dispatchEvent(new MouseEvent('click', {{ bubbles: true, clientX: targetX, clientY: targetY }}));
                  }}
                  await wait(700);
                  if ((window.knowledgeGraphState?.focusId || '') !== focusTarget.id) {{
                    document.querySelector('#graphFocusSelected')?.click();
                    await wait(1200);
                  }} else {{
                    await wait(500);
                  }}
                  const afterFocusId = window.knowledgeGraphState?.focusId || '';
                  const pathAfterFocus = {{
                    start_id: window.knowledgeGraphState?.pathStartId || '',
                    end_id: window.knowledgeGraphState?.pathEndId || '',
                    path_nodes: document.querySelectorAll('.graph-node-svg.is-path-node').length,
                    path_links: document.querySelectorAll('.graph-link-svg.is-path-link').length
                  }};
                  const historyButtonsAfterFocus = [...document.querySelectorAll('.graph-focus-history-node')];
                  document.querySelector('#graphBackFocus')?.click();
                  await wait(1200);
                  const afterBackFocusId = window.knowledgeGraphState?.focusId || '';
                  const pathAfterBackFocus = {{
                    start_id: window.knowledgeGraphState?.pathStartId || '',
                    end_id: window.knowledgeGraphState?.pathEndId || '',
                    path_nodes: document.querySelectorAll('.graph-node-svg.is-path-node').length,
                    path_links: document.querySelectorAll('.graph-link-svg.is-path-link').length
                  }};
                  const historyButtonsAfterBack = [...document.querySelectorAll('.graph-focus-history-node')];
                  let keyboardNode = {{ checked: false }};
                  const keyboardTargetElement = document.querySelector(`.graph-node-svg[data-node-id="${{CSS.escape(focusTarget.id)}}"]`);
                  if (keyboardTargetElement) {{
                    const keyboardBeforeFocus = window.knowledgeGraphState?.focusId || '';
                    try {{
                      keyboardTargetElement.focus({{ preventScroll: true, focusVisible: true }});
                    }} catch (error) {{
                      keyboardTargetElement.focus();
                    }}
                    await wait(150);
                    const circleStyle = getComputedStyle(keyboardTargetElement.querySelector('circle'));
                    const textStyle = getComputedStyle(keyboardTargetElement.querySelector('text'));
                    const activeBeforeKey = document.activeElement === keyboardTargetElement;
                    const focusVisibleBeforeKey = keyboardTargetElement.matches(':focus-visible');
                    keyboardTargetElement.dispatchEvent(new KeyboardEvent('keydown', {{ bubbles: true, key: 'Enter', code: 'Enter' }}));
                    await wait(1000);
                    keyboardNode = {{
                      checked: true,
                      node_id: focusTarget.id,
                      before_focus_id: keyboardBeforeFocus,
                      after_focus_id: window.knowledgeGraphState?.focusId || '',
                      selected_id: window.knowledgeGraphState?.selectedId || '',
                      role: keyboardTargetElement.getAttribute('role') || '',
                      tab_index: keyboardTargetElement.getAttribute('tabindex') || '',
                      focusable: keyboardTargetElement.getAttribute('focusable') || '',
                      aria_label: keyboardTargetElement.getAttribute('aria-label') || '',
                      active_before_key: activeBeforeKey,
                      focus_visible_before_key: focusVisibleBeforeKey,
                      stroke_width_before_key: circleStyle.strokeWidth || '',
                      label_opacity_before_key: textStyle.opacity || ''
                    }};
                    document.querySelector('#graphBackFocus')?.click();
                    await wait(1000);
                  }}
                  const neighborRow = document.querySelector('.graph-neighbor[data-node-id]');
                  const neighborClick = {{
                    checked: Boolean(neighborRow),
                    before_focus_id: window.knowledgeGraphState?.focusId || '',
                    node_id: neighborRow?.dataset?.nodeId || ''
                  }};
                  if (neighborRow) {{
                    neighborRow.click();
                    await wait(1000);
                    neighborClick.after_focus_id = window.knowledgeGraphState?.focusId || '';
                    neighborClick.selected_id = window.knowledgeGraphState?.selectedId || '';
                    neighborClick.selected_title = document.querySelector('#knowledgeGraphNodeTitle')?.textContent || '';
                  }}
                  focusSwitch = {{
                    checked: true,
                    before_focus_id: beforeFocusId,
                    target_id: focusTarget.id,
                    pointer_checked: Boolean(targetElement && targetBox),
                    after_focus_id: afterFocusId,
                    after_back_focus_id: afterBackFocusId,
                    selected_id: window.knowledgeGraphState?.selectedId || '',
                    expanded: Boolean(window.knowledgeGraphState?.expandedIds?.has?.(focusTarget.id)),
                    back_expanded: Boolean(window.knowledgeGraphState?.expandedIds?.has?.(beforeFocusId)),
                    trail_nodes: window.knowledgeGraphState?.trailIds?.length || 0,
                    focus_label: document.querySelector('#knowledgeGraphFocusLabel')?.textContent || '',
                    path_after_focus: pathAfterFocus,
                    path_after_back_focus: pathAfterBackFocus,
                    neighbor_click: neighborClick,
                    keyboard_node: keyboardNode,
                    button_present: Boolean(document.querySelector('#graphFocusSelected')),
                    back_button_present: Boolean(document.querySelector('#graphBackFocus')),
                    history_nodes_after_focus: historyButtonsAfterFocus.length,
                    history_nodes_after_back: historyButtonsAfterBack.length,
                    history_labels_after_back: historyButtonsAfterBack.map((item) => item.textContent || '')
                  }};
                }}
              }}
              let communityClick = {{ checked: false }};
              const industryCommunity = document.querySelector('.graph-community-label[data-community="industry"]');
              if (industryCommunity) {{
                const beforeFocus = window.knowledgeGraphState?.focusId || '';
                const box = industryCommunity.getBoundingClientRect();
                const cx = box.left + box.width / 2;
                const cy = box.top + box.height / 2;
                industryCommunity.dispatchEvent(new PointerEvent('pointerdown', {{ bubbles: true, pointerId: 9911, clientX: cx, clientY: cy, pointerType: 'mouse', isPrimary: true }}));
                industryCommunity.dispatchEvent(new PointerEvent('pointerup', {{ bubbles: true, pointerId: 9911, clientX: cx, clientY: cy, pointerType: 'mouse', isPrimary: true }}));
                industryCommunity.dispatchEvent(new MouseEvent('click', {{ bubbles: true, clientX: cx, clientY: cy }}));
                await wait(1000);
                communityClick = {{
                  checked: true,
                  community: 'industry',
                  before_focus_id: beforeFocus,
                  after_focus_id: window.knowledgeGraphState?.focusId || '',
                  selected_id: window.knowledgeGraphState?.selectedId || '',
                  selected_title: document.querySelector('#knowledgeGraphNodeTitle')?.textContent || '',
                  focus_label: document.querySelector('#knowledgeGraphFocusLabel')?.textContent || ''
                }};
                let keyboardCommunity = {{ checked: false }};
                const keyboardCommunityElement = [...document.querySelectorAll('.graph-community-label')].find((element) => {{
                  const nodeId = communityRepresentativeNodeId(element.getAttribute('data-community') || '');
                  return nodeId && nodeId !== (window.knowledgeGraphState?.focusId || '');
                }});
                if (keyboardCommunityElement) {{
                  const beforeKeyboardFocus = window.knowledgeGraphState?.focusId || '';
                  const representativeId = communityRepresentativeNodeId(keyboardCommunityElement.getAttribute('data-community') || '');
                  try {{
                    keyboardCommunityElement.focus({{ preventScroll: true, focusVisible: true }});
                  }} catch (error) {{
                    keyboardCommunityElement.focus();
                  }}
                  await wait(150);
                  const circleStyle = getComputedStyle(keyboardCommunityElement.querySelector('circle'));
                  const activeBeforeKey = document.activeElement === keyboardCommunityElement;
                  const focusVisibleBeforeKey = keyboardCommunityElement.matches(':focus-visible');
                  keyboardCommunityElement.dispatchEvent(new KeyboardEvent('keydown', {{ bubbles: true, key: ' ', code: 'Space' }}));
                  await wait(1000);
                  keyboardCommunity = {{
                    checked: true,
                    community: keyboardCommunityElement.getAttribute('data-community') || '',
                    representative_id: representativeId,
                    before_focus_id: beforeKeyboardFocus,
                    after_focus_id: window.knowledgeGraphState?.focusId || '',
                    selected_id: window.knowledgeGraphState?.selectedId || '',
                    role: keyboardCommunityElement.getAttribute('role') || '',
                    tab_index: keyboardCommunityElement.getAttribute('tabindex') || '',
                    focusable: keyboardCommunityElement.getAttribute('focusable') || '',
                    aria_label: keyboardCommunityElement.getAttribute('aria-label') || '',
                    active_before_key: activeBeforeKey,
                    focus_visible_before_key: focusVisibleBeforeKey,
                    stroke_width_before_key: circleStyle.strokeWidth || ''
                  }};
                }}
                communityClick.keyboard_community = keyboardCommunity;
              }}
              let trailCheck = {{ checked: false }};
              if ({json.dumps(check_trail)}) {{
                const selectedId = window.knowledgeGraphState?.selectedId || window.knowledgeGraphState?.focusId || '';
                if (selectedId && window.knowledgeGraphState?.fixedIds?.has?.(selectedId)) {{
                  window.knowledgeGraphState.fixedIds.delete(selectedId);
                }}
                document.querySelector('#graphPinSelected')?.click();
                await wait(300);
                const pinnedAfterClick = selectedId ? window.knowledgeGraphState?.fixedIds?.has?.(selectedId) : false;
                document.querySelector('#graphSavePathTrail')?.click();
                await wait(300);
                const trailButtons = [...document.querySelectorAll('.graph-trail-node')];
                const beforeTrailClick = {{
                  x: Number(window.knowledgeGraphState?.transform?.x || 0),
                  y: Number(window.knowledgeGraphState?.transform?.y || 0),
                  scale: Number(window.knowledgeGraphState?.transform?.scale || 1)
                }};
                trailButtons[0]?.click();
                await wait(300);
                const afterTrailClick = {{
                  x: Number(window.knowledgeGraphState?.transform?.x || 0),
                  y: Number(window.knowledgeGraphState?.transform?.y || 0),
                  scale: Number(window.knowledgeGraphState?.transform?.scale || 1)
                }};
                const clickedTrailId = trailButtons[0]?.dataset?.nodeId || '';
                trailCheck = {{
                  checked: true,
                  buttons: ['graphPinSelected', 'graphSavePathTrail', 'graphClearTrail'].filter((id) => Boolean(document.querySelector(`#${{id}}`))).length,
                  selected_id: selectedId,
                  pinned_after_click: Boolean(pinnedAfterClick),
                  trail_nodes: trailButtons.length,
                  trail_state_nodes: window.knowledgeGraphState?.trailIds?.length || 0,
                  clicked_trail_id: clickedTrailId,
                  selected_after_trail_click: window.knowledgeGraphState?.selectedId || '',
                  before_trail_click: beforeTrailClick,
                  after_trail_click: afterTrailClick
                }};
              }}
              let savedSubgraph = {{ checked: false }};
              if ({json.dumps(check_saved_subgraph)}) {{
                document.querySelector('#graphSaveSubgraph')?.click();
                await wait(300);
                const storageKey = `ai_quant_graph_subgraph:${{window.knowledgeGraphState?.focusId || 'none'}}`;
                const storedRaw = window.localStorage?.getItem(storageKey) || '';
                let stored = {{}};
                try {{ stored = storedRaw ? JSON.parse(storedRaw) : {{}}; }} catch (_error) {{ stored = {{ parse_error: true }}; }}
                document.querySelector('#graphClearTrail')?.click();
                await wait(150);
                const afterClearTrailNodes = document.querySelectorAll('.graph-trail-node').length;
                document.querySelector('#graphRestoreSubgraph')?.click();
                await wait(600);
                const restoredTrailNodes = document.querySelectorAll('.graph-trail-node').length;
                savedSubgraph = {{
                  checked: true,
                  buttons: ['graphSaveSubgraph', 'graphRestoreSubgraph'].filter((id) => Boolean(document.querySelector(`#${{id}}`))).length,
                  storage_key: storageKey,
                  stored: Boolean(storedRaw),
                  stored_trail_nodes: Array.isArray(stored.trailIds) ? stored.trailIds.length : 0,
                  stored_scope: stored.scope || '',
                  after_clear_trail_nodes: afterClearTrailNodes,
                  restored_trail_nodes: restoredTrailNodes,
                  state_trail_nodes: window.knowledgeGraphState?.trailIds?.length || 0,
                  status: document.querySelector('#knowledgeGraphSubgraphStatus')?.textContent || ''
                }};
                if (storedRaw) window.localStorage?.removeItem(storageKey);
              }}
              let shareView = {{ checked: false }};
              if ({json.dumps(check_share_view)}) {{
                const expected = {{
                  focus_id: window.knowledgeGraphState?.focusId || '',
                  selected_id: window.knowledgeGraphState?.selectedId || '',
                  scope: window.knowledgeGraphState?.scope || '',
                  depth: Number(window.knowledgeGraphState?.depth || 0),
                  search: 'share-gate',
                  trail_nodes: window.knowledgeGraphState?.trailIds?.length || 0
                }};
                window.knowledgeGraphState.search = expected.search;
                const searchInput = document.querySelector('#graphSearch');
                if (searchInput) searchInput.value = expected.search;
                const shareUrl = typeof window.shareKnowledgeGraphView === 'function' ? await window.shareKnowledgeGraphView() : '';
                const graphParam = new URL(shareUrl || window.location.href).hash.replace(/^#/, '').split('&').find((part) => part.startsWith('graph='));
                const encoded = graphParam ? graphParam.slice('graph='.length) : '';
                const decoded = typeof window.decodeKnowledgeGraphShareState === 'function' ? window.decodeKnowledgeGraphShareState(encoded) : null;
                if (window.knowledgeGraphState) {{
                  window.knowledgeGraphState.search = '';
                  window.knowledgeGraphState.selectedId = '';
                  window.knowledgeGraphState.trailIds = [];
                  window.knowledgeGraphState.focusHistoryIds = [];
                  window.knowledgeGraphState.expandedIds = new Set();
                  window.knowledgeGraphState.transform = {{ x: 0, y: 0, scale: 1 }};
                }}
                if (typeof window.applyKnowledgeGraphSharedState === 'function') window.applyKnowledgeGraphSharedState(decoded);
                if (typeof window.rerenderKnowledgeGraphExplorer === 'function') window.rerenderKnowledgeGraphExplorer();
                await wait(900);
                shareView = {{
                  checked: true,
                  button: Boolean(document.querySelector('#graphShareView')),
                  url_has_graph_hash: Boolean(encoded),
                  decoded_focus_id: decoded?.focusId || '',
                  decoded_selected_id: decoded?.selectedId || '',
                  decoded_search: decoded?.search || '',
                  restored_focus_id: window.knowledgeGraphState?.focusId || '',
                  restored_selected_id: window.knowledgeGraphState?.selectedId || '',
                  restored_scope: window.knowledgeGraphState?.scope || '',
                  restored_depth: Number(window.knowledgeGraphState?.depth || 0),
                  restored_search: window.knowledgeGraphState?.search || '',
                  restored_trail_nodes: window.knowledgeGraphState?.trailIds?.length || 0,
                  restored_status: document.querySelector('#knowledgeGraphSubgraphStatus')?.textContent || '',
                  expected
                }};
              }}
              const visibleTexts = visibleTextsForRawCheck();
              return {{
                status: 'measured',
                rect: {{ width: rect.width, height: rect.height }},
                node_count_text: document.querySelector('#knowledgeGraphNodeCount')?.textContent || '',
                link_count_text: document.querySelector('#knowledgeGraphLinkCount')?.textContent || '',
                nodes: initialGraphSnapshot.nodes,
                links: initialGraphSnapshot.links,
                labels: initialGraphSnapshot.labels,
                overlap_pairs: initialGraphSnapshot.overlap_pairs,
                near_edge_nodes: initialGraphSnapshot.near_edge_nodes,
                initial_graph: initialGraphSnapshot,
                first_expandable: firstExpandable,
                expanded_after_click: document.querySelectorAll('.graph-node-svg.is-expanded').length,
                expansion_after_click: expansionCheck,
                selected_title_after_click: document.querySelector('#knowledgeGraphNodeTitle')?.textContent || '',
                focus_label: document.querySelector('#knowledgeGraphFocusLabel')?.textContent || '',
                responsive_layout: responsiveLayout,
                community_labels: initialGraphSnapshot.community_labels,
                community_quality_labels: initialGraphSnapshot.community_quality_labels,
                encoded_node_types: initialGraphSnapshot.encoded_node_types,
                legend_encoded_types: initialGraphSnapshot.legend_encoded_types,
                legend_encodings: initialGraphSnapshot.legend_encodings,
                missing_node_type_codes: initialGraphSnapshot.missing_node_type_codes,
                missing_legend_type_codes: initialGraphSnapshot.missing_legend_type_codes,
                visible_communities: [...new Set(nodes.map((item) => item.community).filter(Boolean))],
                community_centroids: communityCentroids,
                community_spread_ratio: Number((avgCommunityDistance / communityScale).toFixed(4)),
                min_community_spread_ratio: Number((minCommunityDistance / communityScale).toFixed(4)),
                visible_node_types: initialGraphSnapshot.visible_node_types,
                industry_nodes: nodes.filter((item) => item.community === 'industry').length,
                visible_knowledge_types: [...new Set(nodes.filter((item) => ['event', 'evidence', 'research', 'decision'].includes(item.type) || ['research', 'evidence'].includes(item.community)).map((item) => item.type || item.community).filter(Boolean))],
                performance: perfBeforeInteractions,
                reduced_motion: reducedMotion,
                performance_mode: window.knowledgeGraphState?.performanceMode || '',
                render_stats: initialGraphSnapshot.render_stats,
                graph_stage_performance_mode: Boolean(document.querySelector('.graph-stage.is-performance-mode')),
                link_label_dom_count: initialGraphSnapshot.link_label_dom_count,
                filter_chips: document.querySelector('#knowledgeGraphFilterChips')?.textContent || '',
                raw_knowledge_nodes: (window.knowledgeGraphState?.raw?.documents?.length || 0)
                  + (window.knowledgeGraphState?.raw?.company_events?.length || 0)
                  + (window.knowledgeGraphState?.raw?.structured_research_reports?.length || 0)
                  + (window.knowledgeGraphState?.raw?.report_viewpoints?.length || 0)
                  + (window.knowledgeGraphState?.raw?.evidence?.length || 0),
                raw_structured_reports: window.knowledgeGraphState?.raw?.structured_research_reports?.length || 0,
                raw_relationships: window.knowledgeGraphState?.raw?.company_relationships?.length || 0,
                raw_relationship_types: [...new Set((window.knowledgeGraphState?.raw?.company_relationships || []).map((item) => item.relationship_type).filter(Boolean))],
                raw_edge_relationships: (window.knowledgeGraphState?.raw?.edges || []).filter((item) => item.relationship_type).length,
                raw_edge_relationship_types: [...new Set((window.knowledgeGraphState?.raw?.edges || []).map((item) => item.relationship_type).filter(Boolean))],
                raw_edge_types: [...new Set((window.knowledgeGraphState?.raw?.edges || []).map((item) => item.type).filter(Boolean))],
                chain_node_splits: (window.knowledgeGraphState?.raw?.chain_nodes || []).filter((item) => {{
                  const nodeId = String(item.node_id || '').trim();
                  const chainId = String(item.chain_id || '').trim();
                  if (!nodeId || !chainId || nodeId.includes(':')) return false;
                  const ids = new Set((window.knowledgeGraphState?.nodes || []).map((node) => node.id));
                  return ids.has(nodeId) && ids.has(`${{chainId}}:${{nodeId}}`);
                }}).map((item) => `${{item.chain_id}}:${{item.node_id}}`).slice(0, 20),
                raw_text_probe: rawTextProbe,
                focus_switch: focusSwitch,
                community_click: communityClick,
                view_controls: viewControls,
                trail: trailCheck,
                saved_subgraph: savedSubgraph,
                share_view: shareView,
                persistence,
                path: pathCheck,
                motion_status: document.querySelector('#knowledgeGraphMotionStatus')?.textContent || '',
                visible_text_count: visibleTexts.length,
                raw_label_text_leaks: [...new Set(visibleTexts.filter((text) => rawTextPattern.test(text)))].slice(0, 20)
              }};
            }})()
            """
        last_error = ""
        for _ in range(3):
            try:
                result = client.evaluate(expression)
                break
            except RuntimeError as exc:
                last_error = str(exc)
                if "Execution context was destroyed" not in last_error:
                    raise
                time.sleep(1.0)
        else:
            result = {"status": "failed", "error": last_error}
    finally:
        if client is not None:
            client.close()
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()

    readiness = _graph_readiness_probe(base_url, symbol=symbol, timeout=min(max(timeout / 3, 5.0), 15.0)) if check_readiness else {"status": "skipped"}
    failures: list[dict[str, Any]] = []
    if not isinstance(result, dict) or result.get("status") != "measured":
        failures.append({"check": "browser_measurement", "result": result})
        result = result if isinstance(result, dict) else {"status": "failed", "raw": result}
    else:
        if int(result.get("nodes", 0)) < min_nodes:
            failures.append({"check": "min_nodes", "expected": min_nodes, "actual": result.get("nodes")})
        if int(result.get("links", 0)) < min_links:
            failures.append({"check": "min_links", "expected": min_links, "actual": result.get("links")})
        if max_visible_nodes and int(result.get("nodes", 0)) > max_visible_nodes:
            failures.append({"check": "max_visible_nodes", "expected": f"<={max_visible_nodes}", "actual": result.get("nodes"), "render_stats": result.get("render_stats")})
        if max_visible_links and int(result.get("links", 0)) > max_visible_links:
            failures.append({"check": "max_visible_links", "expected": f"<={max_visible_links}", "actual": result.get("links"), "render_stats": result.get("render_stats")})
        if max_link_label_dom_count and int(result.get("link_label_dom_count", 0)) > max_link_label_dom_count:
            failures.append({"check": "max_link_label_dom_count", "expected": f"<={max_link_label_dom_count}", "actual": result.get("link_label_dom_count"), "render_stats": result.get("render_stats")})
        if int(result.get("overlap_pairs", 0)) > max_overlap_pairs:
            failures.append({"check": "max_overlap_pairs", "expected": max_overlap_pairs, "actual": result.get("overlap_pairs")})
        if int(result.get("near_edge_nodes", 0)) > max_near_edge_nodes:
            failures.append({"check": "max_near_edge_nodes", "expected": max_near_edge_nodes, "actual": result.get("near_edge_nodes")})
        responsive_layout = result.get("responsive_layout") if isinstance(result.get("responsive_layout"), dict) else {}
        if expect_mobile_layout:
            if int(responsive_layout.get("viewport_width", 9999)) > 900:
                failures.append({"check": "mobile_viewport_width", "expected": "<=900", "actual": responsive_layout})
            elif not responsive_layout.get("inspector_below_stage"):
                failures.append({"check": "mobile_graph_single_column", "expected": "inspector below graph stage", "actual": responsive_layout})
            elif responsive_layout.get("stage_overflows_viewport") or responsive_layout.get("inspector_overflows_viewport") or responsive_layout.get("toolbar_overflows_viewport"):
                failures.append({"check": "mobile_graph_overflow", "expected": "graph stage, inspector, and toolbar fit viewport width", "actual": responsive_layout})
            elif float(responsive_layout.get("svg_height", 0)) < 440 or float(responsive_layout.get("stage_height", 0)) < 440:
                failures.append({"check": "mobile_graph_height", "expected": ">=440px graph viewport", "actual": responsive_layout})
        reduced_motion = result.get("reduced_motion") if isinstance(result.get("reduced_motion"), dict) else {}
        if expect_reduced_motion:
            if not reduced_motion.get("matches") or not reduced_motion.get("reduced_state"):
                failures.append({"check": "reduced_motion_media", "expected": "prefers-reduced-motion reduce is active in graph state", "actual": reduced_motion})
            elif reduced_motion.get("dynamic"):
                failures.append({"check": "reduced_motion_dynamic", "expected": "dynamic=false until user override", "actual": reduced_motion})
            elif int(reduced_motion.get("frame_id", 0)) != 0:
                failures.append({"check": "reduced_motion_animation_frame", "expected": "no active requestAnimationFrame", "actual": reduced_motion})
            elif "减少动态" not in str(reduced_motion.get("status", "")):
                failures.append({"check": "reduced_motion_status", "expected": "status includes 减少动态", "actual": reduced_motion})
            elif "继续动态" not in str(reduced_motion.get("button_text", "")):
                failures.append({"check": "reduced_motion_toggle", "expected": "button offers explicit opt-in to motion", "actual": reduced_motion})
        if expect_redundant_node_encoding:
            visible_types = set(result.get("visible_node_types") or [])
            encoded_types = set(result.get("encoded_node_types") or [])
            legend_types = set(result.get("legend_encoded_types") or [])
            missing_node_codes = sorted(visible_types - encoded_types)
            missing_legend_codes = sorted(visible_types - legend_types)
            if missing_node_codes:
                failures.append({"check": "node_redundant_type_codes", "expected": "every visible node type has a visible non-color code", "actual": {"missing": missing_node_codes, "node_missing": result.get("missing_node_type_codes")}})
            if missing_legend_codes:
                failures.append({"check": "legend_redundant_type_codes", "expected": "legend repeats each visible node type code", "actual": {"missing": missing_legend_codes, "legend": result.get("legend_encodings")}})
        if int(result.get("expanded_after_click", 0)) < 2:
            failures.append({"check": "node_expansion", "expected": ">=2", "actual": result.get("expanded_after_click")})
        expansion = result.get("expansion_after_click") if isinstance(result.get("expansion_after_click"), dict) else {}
        if not expansion.get("node_id"):
            failures.append({"check": "node_expansion_target", "expected": "expandable visible node", "actual": expansion})
        elif not expansion.get("expanded"):
            failures.append({"check": "node_expansion_state", "expected": "clicked node enters expandedIds", "actual": expansion})
        elif expansion.get("focus_after") != expansion.get("node_id"):
            failures.append({"check": "node_click_focus_switch", "expected": expansion.get("node_id"), "actual": expansion})
        elif int(expansion.get("hidden_neighbors_before", 0)) <= 0 and int(expansion.get("visible_neighbors_after", 0)) < 1:
            failures.append({"check": "node_click_visible_neighbor", "expected": ">=1 existing visible neighbor for leaf/sparse node", "actual": expansion})
        elif int(expansion.get("hidden_neighbors_before", 0)) > 0 and int(expansion.get("visible_neighbors_after", 0)) < min_visible_neighbors_after_click:
            failures.append({"check": "node_expansion_visible_neighbors", "expected": f">={min_visible_neighbors_after_click}", "actual": expansion})
        elif int(expansion.get("hidden_neighbors_before", 0)) > 0 and (
            int(expansion.get("neighbor_delta", 0)) < min_expansion_neighbor_delta
            and int(expansion.get("node_delta", 0)) < 1
            and int(expansion.get("link_delta", 0)) < 2
            and int(expansion.get("visible_neighbors_after", 0)) < min_visible_neighbors_after_click
        ):
            failures.append({"check": "node_expansion_delta", "expected": f"neighbor delta >= {min_expansion_neighbor_delta} or visible graph growth", "actual": expansion})
        expected_scope_label = "全局图" if scope == "global" else "局部图"
        if expected_scope_label not in str(result.get("focus_label", "")):
            failures.append({"check": "scope_label", "expected": expected_scope_label, "actual": result.get("focus_label")})
        if int(result.get("community_labels", 0)) < min_community_labels:
            failures.append({"check": "community_labels", "expected": f">={min_community_labels}", "actual": result.get("community_labels")})
        if int(result.get("community_quality_labels", 0)) < min_community_labels:
            failures.append({"check": "community_quality_labels", "expected": f">={min_community_labels}", "actual": result.get("community_quality_labels")})
        if min_visible_communities and len(result.get("visible_communities", []) or []) < min_visible_communities:
            failures.append({"check": "visible_communities", "expected": f">={min_visible_communities}", "actual": result.get("visible_communities")})
        if min_community_spread_ratio and len(result.get("visible_communities", []) or []) >= 3:
            community_spread_ratio = float(result.get("community_spread_ratio") or 0.0)
            if community_spread_ratio < min_community_spread_ratio:
                failures.append({
                    "check": "community_spread_ratio",
                    "expected": f">={min_community_spread_ratio}",
                    "actual": community_spread_ratio,
                    "centroids": result.get("community_centroids"),
                    "min_pair_ratio": result.get("min_community_spread_ratio"),
                })
        if min_industry_nodes and int(result.get("industry_nodes", 0)) < min_industry_nodes:
            failures.append({"check": "industry_nodes", "expected": f">={min_industry_nodes}", "actual": result.get("industry_nodes")})
        if min_raw_knowledge_nodes and int(result.get("raw_knowledge_nodes", 0)) < min_raw_knowledge_nodes:
            failures.append({"check": "raw_knowledge_nodes", "expected": f">={min_raw_knowledge_nodes}", "actual": result.get("raw_knowledge_nodes")})
        if min_raw_structured_reports and int(result.get("raw_structured_reports", 0)) < min_raw_structured_reports:
            failures.append({"check": "raw_structured_reports", "expected": f">={min_raw_structured_reports}", "actual": result.get("raw_structured_reports")})
        if int(result.get("raw_structured_reports", 0)) > 0 and "research" not in (result.get("visible_node_types") or []):
            failures.append({"check": "structured_reports_visible_research", "expected": "research node visible when structured reports exist", "actual": result.get("visible_node_types")})
        if min_visible_knowledge_types and len(result.get("visible_knowledge_types", []) or []) < min_visible_knowledge_types:
            failures.append({"check": "visible_knowledge_types", "expected": f">={min_visible_knowledge_types}", "actual": result.get("visible_knowledge_types")})
        perf = result.get("performance") if isinstance(result.get("performance"), dict) else {}
        reduced_motion = result.get("reduced_motion") if isinstance(result.get("reduced_motion"), dict) else {}
        fps_tolerance = 0.5
        avg_frame_ms = float(perf.get("avg_frame_ms", 999))
        if not expect_reduced_motion:
            if float(perf.get("fps", 0)) + fps_tolerance < min_fps and avg_frame_ms > max_frame_ms / 2:
                failures.append({"check": "graph_fps", "expected": f">={min_fps}", "actual": perf})
            if avg_frame_ms > max_frame_ms:
                failures.append({"check": "graph_avg_frame_ms", "expected": f"<={max_frame_ms}", "actual": perf})
            if "FPS" not in str(perf.get("status", "")) or "帧" not in str(perf.get("status", "")):
                failures.append({"check": "graph_performance_status", "expected": "status includes FPS and frame time", "actual": perf})
        elif avg_frame_ms > max_frame_ms:
            failures.append({"check": "reduced_motion_static_settle_ms", "expected": f"<={max_frame_ms}", "actual": {"performance": perf, "reduced_motion": reduced_motion}})
        if expect_performance_mode:
            if result.get("performance_mode") != expect_performance_mode:
                failures.append({"check": "graph_performance_mode", "expected": expect_performance_mode, "actual": result.get("performance_mode")})
            if expect_performance_mode == "large" and not result.get("graph_stage_performance_mode"):
                failures.append({"check": "graph_stage_performance_mode", "expected": "graph-stage.is-performance-mode", "actual": result.get("graph_stage_performance_mode")})
            if expect_performance_mode == "large" and "高性能" not in str(result.get("motion_status", "")):
                failures.append({"check": "graph_performance_mode_status", "expected": "status includes 高性能", "actual": result.get("motion_status")})
            if expect_performance_mode == "large" and "标签" not in str(result.get("motion_status", "")):
                failures.append({"check": "graph_performance_label_budget_status", "expected": "status includes label DOM budget", "actual": result.get("motion_status")})
        chain_node_splits = result.get("chain_node_splits") or []
        if len(chain_node_splits) > max_chain_node_splits:
            failures.append({"check": "chain_node_splits", "expected": f"<={max_chain_node_splits}", "actual": len(chain_node_splits), "examples": chain_node_splits[:5]})
        if result.get("raw_label_text_leaks"):
            failures.append({"check": "raw_label_text_leaks", "expected": "no raw graph ids in visible graph text", "actual": result.get("raw_label_text_leaks")})
        raw_text_probe = result.get("raw_text_probe") if isinstance(result.get("raw_text_probe"), dict) else {}
        if raw_text_probe.get("raw_label_text_leaks"):
            failures.append({"check": "raw_label_text_probe_leaks", "expected": "no raw graph ids after probing market node text", "actual": raw_text_probe})
        if expect_filter_chip and expect_filter_chip not in str(result.get("filter_chips", "")):
            failures.append({"check": "expected_filter_chip", "expected": expect_filter_chip, "actual": result.get("filter_chips", "")})
        if forbid_filter_chip and forbid_filter_chip in str(result.get("filter_chips", "")):
            failures.append({"check": "forbidden_filter_chip", "expected": f"not contains {forbid_filter_chip}", "actual": result.get("filter_chips", "")})
        if relationship_type:
            filter_chips = str(result.get("filter_chips", ""))
            relationship_types = set(result.get("raw_relationship_types", []) or [])
            edge_relationship_types = set(result.get("raw_edge_relationship_types", []) or [])
            combined_relationship_types = relationship_types | edge_relationship_types
            relationship_count = int(result.get("raw_relationships", 0)) + int(result.get("raw_edge_relationships", 0))
            if relationship_count < min_filtered_relationships:
                failures.append({"check": "filtered_relationship_count", "expected": f">={min_filtered_relationships}", "actual": relationship_count})
            if min_filtered_relationships > 0 and relationship_types != {relationship_type}:
                if combined_relationship_types != {relationship_type}:
                    failures.append({"check": "filtered_relationship_type", "expected": relationship_type, "actual": sorted(combined_relationship_types)})
            if relationship_type not in filter_chips and "关系类型" not in filter_chips:
                failures.append({"check": "relationship_filter_chip", "expected": relationship_type, "actual": filter_chips})
        if institutional_holder_key:
            filter_chips = str(result.get("filter_chips", ""))
            raw_edge_types = set(result.get("raw_edge_types", []) or [])
            if "SAME_HOLDER_RELATED_COMPANY" not in raw_edge_types:
                failures.append({"check": "institutional_holder_related_edge", "expected": "SAME_HOLDER_RELATED_COMPANY", "actual": sorted(raw_edge_types)})
            if institutional_holder_key not in filter_chips and "机构持有人" not in filter_chips:
                failures.append({"check": "institutional_holder_filter_chip", "expected": institutional_holder_key, "actual": filter_chips})
        if ownership_holder_key:
            filter_chips = str(result.get("filter_chips", ""))
            raw_relationship_types = set(result.get("raw_relationship_types", []) or [])
            raw_edge_types = set(result.get("raw_edge_types", []) or [])
            if "shareholder" not in raw_relationship_types:
                failures.append({"check": "ownership_holder_relationship", "expected": "shareholder", "actual": sorted(raw_relationship_types)})
            if "HAS_COMPANY_RELATIONSHIP" not in raw_edge_types:
                failures.append({"check": "ownership_holder_relationship_edge", "expected": "HAS_COMPANY_RELATIONSHIP", "actual": sorted(raw_edge_types)})
            if ownership_holder_key not in filter_chips and "股东" not in filter_chips:
                failures.append({"check": "ownership_holder_filter_chip", "expected": ownership_holder_key, "actual": filter_chips})
        view_controls = result.get("view_controls") if isinstance(result.get("view_controls"), dict) else {}
        if check_view_controls:
            if not view_controls.get("checked"):
                failures.append({"check": "view_controls", "expected": "checked", "actual": view_controls})
            elif int(view_controls.get("buttons", 0)) < 4:
                failures.append({"check": "view_control_buttons", "expected": 4, "actual": view_controls})
            elif float(view_controls.get("after_zoom_in", {}).get("scale", 0)) <= float(view_controls.get("before", {}).get("scale", 0)):
                failures.append({"check": "view_zoom_in", "expected": "scale increases", "actual": view_controls})
            elif float(view_controls.get("after_fit", {}).get("scale", 0)) <= 0:
                failures.append({"check": "view_fit", "expected": "positive scale", "actual": view_controls})
            elif abs(float(view_controls.get("after_center", {}).get("x", 0)) - float(view_controls.get("after_fit", {}).get("x", 0))) < 0.1 and abs(float(view_controls.get("after_center", {}).get("y", 0)) - float(view_controls.get("after_fit", {}).get("y", 0))) < 0.1:
                failures.append({"check": "view_center_focus", "expected": "transform changes", "actual": view_controls})
            elif "缩放" not in str(view_controls.get("status", "")):
                failures.append({"check": "view_status_zoom", "expected": "status includes zoom", "actual": view_controls})
        focus_switch = result.get("focus_switch") if isinstance(result.get("focus_switch"), dict) else {}
        if check_focus_switch:
            if not focus_switch.get("checked"):
                failures.append({"check": "focus_switch", "expected": "checked", "actual": focus_switch})
            elif not focus_switch.get("pointer_checked"):
                failures.append({"check": "focus_switch_pointer_chain", "expected": "pointerdown + pointerup target coordinates", "actual": focus_switch})
            elif not focus_switch.get("button_present"):
                failures.append({"check": "focus_switch_button", "expected": "graphFocusSelected", "actual": focus_switch})
            elif not focus_switch.get("back_button_present"):
                failures.append({"check": "focus_switch_back_button", "expected": "graphBackFocus", "actual": focus_switch})
            elif not focus_switch.get("target_id") or focus_switch.get("before_focus_id") == focus_switch.get("target_id"):
                failures.append({"check": "focus_switch_target", "expected": focus_switch.get("target_id"), "actual": focus_switch})
            elif focus_switch.get("after_focus_id") != focus_switch.get("target_id"):
                failures.append({"check": "focus_switch_forward_target", "expected": focus_switch.get("target_id"), "actual": focus_switch})
            elif focus_switch.get("after_back_focus_id") != focus_switch.get("before_focus_id"):
                failures.append({"check": "focus_switch_back_target", "expected": focus_switch.get("before_focus_id"), "actual": focus_switch})
            elif not focus_switch.get("expanded") or not focus_switch.get("back_expanded") or int(focus_switch.get("trail_nodes", 0)) < 1:
                failures.append({"check": "focus_switch_state", "expected": "expanded and trailed", "actual": focus_switch})
            elif int(focus_switch.get("history_nodes_after_focus", 0)) < 2 or int(focus_switch.get("history_nodes_after_back", 0)) < 2:
                failures.append({"check": "focus_switch_history", "expected": "history stack", "actual": focus_switch})
            elif focus_switch.get("path_after_focus", {}).get("start_id") != focus_switch.get("target_id") or focus_switch.get("path_after_focus", {}).get("end_id") != focus_switch.get("before_focus_id"):
                failures.append({"check": "focus_switch_path_context", "expected": "new focus keeps previous focus as path end", "actual": focus_switch})
            elif int(focus_switch.get("path_after_focus", {}).get("path_nodes", 0)) < 2 or int(focus_switch.get("path_after_focus", {}).get("path_links", 0)) < 1:
                failures.append({"check": "focus_switch_path_highlight", "expected": "forward focus path remains highlighted", "actual": focus_switch})
            elif focus_switch.get("path_after_back_focus", {}).get("start_id") != focus_switch.get("before_focus_id") or focus_switch.get("path_after_back_focus", {}).get("end_id") != focus_switch.get("target_id"):
                failures.append({"check": "focus_back_path_context", "expected": "back focus keeps target as path end", "actual": focus_switch})
            elif int(focus_switch.get("path_after_back_focus", {}).get("path_nodes", 0)) < 2 or int(focus_switch.get("path_after_back_focus", {}).get("path_links", 0)) < 1:
                failures.append({"check": "focus_back_path_highlight", "expected": "back focus path remains highlighted", "actual": focus_switch})
            elif not focus_switch.get("keyboard_node", {}).get("checked"):
                failures.append({"check": "focus_switch_keyboard_node", "expected": "keyboard-activated SVG node", "actual": focus_switch})
            elif focus_switch.get("keyboard_node", {}).get("after_focus_id") != focus_switch.get("keyboard_node", {}).get("node_id"):
                failures.append({"check": "focus_switch_keyboard_node_activation", "expected": "Enter switches SVG node focus", "actual": focus_switch})
            elif focus_switch.get("keyboard_node", {}).get("selected_id") != focus_switch.get("keyboard_node", {}).get("node_id"):
                failures.append({"check": "focus_switch_keyboard_node_selection", "expected": "Enter selects SVG node", "actual": focus_switch})
            elif focus_switch.get("keyboard_node", {}).get("role") != "button" or focus_switch.get("keyboard_node", {}).get("tab_index") != "0" or not focus_switch.get("keyboard_node", {}).get("aria_label"):
                failures.append({"check": "focus_switch_keyboard_node_semantics", "expected": "button role, tabindex, aria-label", "actual": focus_switch})
            elif not focus_switch.get("keyboard_node", {}).get("active_before_key") or not focus_switch.get("keyboard_node", {}).get("focus_visible_before_key"):
                failures.append({"check": "focus_switch_keyboard_node_focus_visible", "expected": "focused SVG node has focus-visible state", "actual": focus_switch})
            elif not focus_switch.get("neighbor_click", {}).get("checked"):
                failures.append({"check": "focus_switch_neighbor_click", "expected": "clickable neighbor row", "actual": focus_switch})
            elif focus_switch.get("neighbor_click", {}).get("after_focus_id") != focus_switch.get("neighbor_click", {}).get("node_id") or focus_switch.get("neighbor_click", {}).get("selected_id") != focus_switch.get("neighbor_click", {}).get("node_id"):
                failures.append({"check": "focus_switch_neighbor_activation", "expected": "neighbor click switches focus and selection", "actual": focus_switch})
            elif "焦点" not in str(focus_switch.get("focus_label", "")):
                failures.append({"check": "focus_switch_label", "expected": "焦点 label", "actual": focus_switch.get("focus_label")})
        community_click = result.get("community_click") if isinstance(result.get("community_click"), dict) else {}
        if check_focus_switch:
            if not community_click.get("checked"):
                failures.append({"check": "community_click", "expected": "checked", "actual": community_click})
            elif community_click.get("after_focus_id") == community_click.get("before_focus_id"):
                failures.append({"check": "community_click_focus_switch", "expected": "focus changes after community label click", "actual": community_click})
            elif not community_click.get("selected_title"):
                failures.append({"check": "community_click_selected_title", "expected": "selected community representative title", "actual": community_click})
            elif not community_click.get("keyboard_community", {}).get("checked"):
                failures.append({"check": "community_keyboard", "expected": "keyboard-activated SVG community label", "actual": community_click})
            elif community_click.get("keyboard_community", {}).get("after_focus_id") != community_click.get("keyboard_community", {}).get("representative_id"):
                failures.append({"check": "community_keyboard_activation", "expected": "Space switches to community representative", "actual": community_click})
            elif community_click.get("keyboard_community", {}).get("role") != "button" or community_click.get("keyboard_community", {}).get("tab_index") != "0" or not community_click.get("keyboard_community", {}).get("aria_label"):
                failures.append({"check": "community_keyboard_semantics", "expected": "button role, tabindex, aria-label", "actual": community_click})
            elif not community_click.get("keyboard_community", {}).get("active_before_key") or not community_click.get("keyboard_community", {}).get("focus_visible_before_key"):
                failures.append({"check": "community_keyboard_focus_visible", "expected": "focused community label has focus-visible state", "actual": community_click})
        trail = result.get("trail") if isinstance(result.get("trail"), dict) else {}
        if check_trail:
            if not trail.get("checked"):
                failures.append({"check": "graph_trail", "expected": "checked", "actual": trail})
            elif int(trail.get("buttons", 0)) < 3:
                failures.append({"check": "graph_trail_buttons", "expected": 3, "actual": trail})
            elif not trail.get("pinned_after_click"):
                failures.append({"check": "graph_pin_selected", "expected": "selected node fixed", "actual": trail})
            elif int(trail.get("trail_nodes", 0)) < 1 or int(trail.get("trail_state_nodes", 0)) < 1:
                failures.append({"check": "graph_trail_nodes", "expected": ">=1", "actual": trail})
            elif trail.get("clicked_trail_id") and trail.get("selected_after_trail_click") != trail.get("clicked_trail_id"):
                failures.append({"check": "graph_trail_select", "expected": "trail click selects node", "actual": trail})
        saved_subgraph = result.get("saved_subgraph") if isinstance(result.get("saved_subgraph"), dict) else {}
        if check_saved_subgraph:
            if not saved_subgraph.get("checked"):
                failures.append({"check": "saved_subgraph", "expected": "checked", "actual": saved_subgraph})
            elif int(saved_subgraph.get("buttons", 0)) < 2:
                failures.append({"check": "saved_subgraph_buttons", "expected": 2, "actual": saved_subgraph})
            elif not saved_subgraph.get("stored") or int(saved_subgraph.get("stored_trail_nodes", 0)) < 1:
                failures.append({"check": "saved_subgraph_storage", "expected": "stored trail nodes", "actual": saved_subgraph})
            elif int(saved_subgraph.get("after_clear_trail_nodes", 999)) != 0:
                failures.append({"check": "saved_subgraph_clear_before_restore", "expected": 0, "actual": saved_subgraph})
            elif int(saved_subgraph.get("restored_trail_nodes", 0)) < 1 or int(saved_subgraph.get("state_trail_nodes", 0)) < 1:
                failures.append({"check": "saved_subgraph_restore", "expected": "restored trail nodes", "actual": saved_subgraph})
            elif "已恢复" not in str(saved_subgraph.get("status", "")):
                failures.append({"check": "saved_subgraph_status", "expected": "已恢复", "actual": saved_subgraph})
        share_view = result.get("share_view") if isinstance(result.get("share_view"), dict) else {}
        if check_share_view:
            expected = share_view.get("expected") if isinstance(share_view.get("expected"), dict) else {}
            if not share_view.get("checked"):
                failures.append({"check": "share_view", "expected": "checked", "actual": share_view})
            elif not share_view.get("button"):
                failures.append({"check": "share_view_button", "expected": "graphShareView", "actual": share_view})
            elif not share_view.get("url_has_graph_hash"):
                failures.append({"check": "share_view_hash", "expected": "#graph share state", "actual": share_view})
            elif share_view.get("decoded_focus_id") != expected.get("focus_id"):
                failures.append({"check": "share_view_decode_focus", "expected": expected.get("focus_id"), "actual": share_view})
            elif share_view.get("decoded_selected_id") != expected.get("selected_id"):
                failures.append({"check": "share_view_decode_selection", "expected": expected.get("selected_id"), "actual": share_view})
            elif share_view.get("decoded_search") != expected.get("search"):
                failures.append({"check": "share_view_decode_search", "expected": expected.get("search"), "actual": share_view})
            elif share_view.get("restored_focus_id") != expected.get("focus_id"):
                failures.append({"check": "share_view_restore_focus", "expected": expected.get("focus_id"), "actual": share_view})
            elif share_view.get("restored_selected_id") != expected.get("selected_id"):
                failures.append({"check": "share_view_restore_selection", "expected": expected.get("selected_id"), "actual": share_view})
            elif share_view.get("restored_scope") != expected.get("scope") or share_view.get("restored_depth") != expected.get("depth"):
                failures.append({"check": "share_view_restore_filters", "expected": expected, "actual": share_view})
            elif share_view.get("restored_search") != expected.get("search"):
                failures.append({"check": "share_view_restore_search", "expected": expected.get("search"), "actual": share_view})
            elif int(share_view.get("restored_trail_nodes") or 0) < min(1, int(expected.get("trail_nodes") or 0)):
                failures.append({"check": "share_view_restore_trail", "expected": expected.get("trail_nodes"), "actual": share_view})
            elif "分享链接" not in str(share_view.get("restored_status", "")):
                failures.append({"check": "share_view_restore_status", "expected": "status includes 分享链接", "actual": share_view})
        persistence = result.get("persistence") if isinstance(result.get("persistence"), dict) else {}
        if check_persistence:
            if not persistence.get("checked"):
                failures.append({"check": "layout_persistence", "expected": "checked", "actual": persistence})
            elif not persistence.get("stored") or not persistence.get("fixed_after_reload"):
                failures.append({"check": "layout_persistence", "expected": "stored fixed node", "actual": persistence})
            elif float(persistence.get("dx", 999)) > 2.0 or float(persistence.get("dy", 999)) > 2.0:
                failures.append({"check": "layout_persistence_position", "expected": "within 2px", "actual": persistence})
        path = result.get("path") if isinstance(result.get("path"), dict) else {}
        if check_path:
            if not path.get("checked"):
                failures.append({"check": "path_highlight", "expected": "checked", "actual": path})
            elif int(path.get("path_nodes", 0)) < 2 or int(path.get("path_links", 0)) < 1:
                failures.append({"check": "path_highlight", "expected": ">=2 nodes and >=1 link", "actual": path})
            elif int(path.get("path_link_labels", 0)) < int(path.get("path_links", 0)):
                failures.append({"check": "path_link_labels", "expected": "path links have visible labels", "actual": path})
            elif int(path.get("next_hops", 0)) < 1:
                failures.append({"check": "path_next_hops", "expected": ">=1", "actual": path})
            elif int(path.get("after_next_hop_path_nodes", 0)) < 2 or int(path.get("after_next_hop_path_links", 0)) < 1:
                failures.append({"check": "path_next_hop_highlight", "expected": "path remains highlighted", "actual": path})
            elif int(path.get("after_next_hop_path_link_labels", 0)) < int(path.get("after_next_hop_path_links", 0)):
                failures.append({"check": "path_next_hop_link_labels", "expected": "next-hop path links have visible labels", "actual": path})
        if require_non_seed_readiness:
            seed_dependency = readiness.get("seed_dependency") if isinstance(readiness, dict) else {}
            if readiness.get("status") == "probe_failed":
                failures.append({"check": "knowledge_network_readiness_probe", "expected": "readiness probe available", "actual": readiness})
            elif readiness.get("status") != "ready" or not readiness.get("ready_for_obsidian_exploration"):
                failures.append({"check": "knowledge_network_readiness", "expected": "ready", "actual": readiness})
            elif isinstance(seed_dependency, dict) and seed_dependency.get("seed_dependent"):
                failures.append({"check": "knowledge_network_seed_dependency", "expected": "seed_dependent=false", "actual": seed_dependency})

    report = {
        "status": "passed" if not failures else "failed",
        "base_url": base_url,
        "ui_url": ui_url,
        "symbol": symbol,
        "scope": scope,
        "thresholds": {
            "max_overlap_pairs": max_overlap_pairs,
            "max_near_edge_nodes": max_near_edge_nodes,
            "min_nodes": min_nodes,
            "min_links": min_links,
            "max_visible_nodes": max_visible_nodes,
            "max_visible_links": max_visible_links,
            "max_link_label_dom_count": max_link_label_dom_count,
            "min_fps": min_fps,
            "max_frame_ms": max_frame_ms,
            "min_community_labels": min_community_labels,
            "min_visible_communities": min_visible_communities,
            "min_community_spread_ratio": min_community_spread_ratio,
            "min_industry_nodes": min_industry_nodes,
            "min_raw_knowledge_nodes": min_raw_knowledge_nodes,
            "min_raw_structured_reports": min_raw_structured_reports,
            "min_visible_knowledge_types": min_visible_knowledge_types,
            "min_expansion_neighbor_delta": min_expansion_neighbor_delta,
            "min_visible_neighbors_after_click": min_visible_neighbors_after_click,
            "relationship_type": relationship_type,
            "chain_id": chain_id,
            "chain_node_id": chain_node_id,
            "ownership_holder_key": ownership_holder_key,
            "institutional_holder_key": institutional_holder_key,
            "expect_filter_chip": expect_filter_chip,
            "forbid_filter_chip": forbid_filter_chip,
            "min_filtered_relationships": min_filtered_relationships,
            "check_persistence": check_persistence,
            "check_path": check_path,
            "check_focus_switch": check_focus_switch,
            "check_view_controls": check_view_controls,
            "check_trail": check_trail,
            "check_saved_subgraph": check_saved_subgraph,
            "check_share_view": check_share_view,
            "viewport_width": viewport_width,
            "viewport_height": viewport_height,
            "expect_mobile_layout": expect_mobile_layout,
            "emulate_reduced_motion": emulate_reduced_motion,
            "expect_reduced_motion": expect_reduced_motion,
            "expect_redundant_node_encoding": expect_redundant_node_encoding,
            "expect_performance_mode": expect_performance_mode,
            "max_chain_node_splits": max_chain_node_splits,
            "check_readiness": check_readiness,
            "require_non_seed_readiness": require_non_seed_readiness,
        },
        "measurement": result,
        "knowledge_network_readiness": readiness,
        "failure_count": len(failures),
        "failures": failures,
    }
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure Obsidian-style knowledge graph layout quality in the UI.")
    parser.add_argument("base_url", nargs="?", default="http://127.0.0.1:8000")
    parser.add_argument("--symbol", default="AAPL")
    parser.add_argument("--scope", choices=["local", "global"], default="local")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--chrome-bin", default="")
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--viewport-width", type=int, default=1600)
    parser.add_argument("--viewport-height", type=int, default=950)
    parser.add_argument("--expect-mobile-layout", action="store_true")
    parser.add_argument("--emulate-reduced-motion", action="store_true")
    parser.add_argument("--expect-reduced-motion", action="store_true")
    parser.add_argument("--expect-redundant-node-encoding", action="store_true")
    parser.add_argument("--max-overlap-pairs", type=int, default=3)
    parser.add_argument("--max-near-edge-nodes", type=int, default=0)
    parser.add_argument("--min-nodes", type=int, default=32)
    parser.add_argument("--min-links", type=int, default=60)
    parser.add_argument("--max-visible-nodes", type=int, default=0)
    parser.add_argument("--max-visible-links", type=int, default=0)
    parser.add_argument("--max-link-label-dom-count", type=int, default=0)
    parser.add_argument("--min-fps", type=float, default=20.0)
    parser.add_argument("--max-frame-ms", type=float, default=35.0)
    parser.add_argument("--min-community-labels", type=int, default=2)
    parser.add_argument("--min-visible-communities", type=int, default=0)
    parser.add_argument("--min-community-spread-ratio", type=float, default=0.0)
    parser.add_argument("--min-industry-nodes", type=int, default=0)
    parser.add_argument("--min-raw-knowledge-nodes", type=int, default=0)
    parser.add_argument("--min-raw-structured-reports", type=int, default=0)
    parser.add_argument("--min-visible-knowledge-types", type=int, default=0)
    parser.add_argument("--min-expansion-neighbor-delta", type=int, default=1)
    parser.add_argument("--min-visible-neighbors-after-click", type=int, default=2)
    parser.add_argument("--relationship-type", default="")
    parser.add_argument("--chain-id", default="")
    parser.add_argument("--chain-node-id", default="")
    parser.add_argument("--ownership-holder-key", default="")
    parser.add_argument("--institutional-holder-key", default="")
    parser.add_argument("--min-filtered-relationships", type=int, default=0)
    parser.add_argument("--expect-filter-chip", default="")
    parser.add_argument("--forbid-filter-chip", default="")
    parser.add_argument("--check-persistence", action="store_true")
    parser.add_argument("--check-path", action="store_true")
    parser.add_argument("--check-focus-switch", action="store_true")
    parser.add_argument("--skip-view-controls", action="store_true")
    parser.add_argument("--skip-trail", action="store_true")
    parser.add_argument("--skip-saved-subgraph", action="store_true")
    parser.add_argument("--check-share-view", action="store_true")
    parser.add_argument("--expect-performance-mode", choices=["", "standard", "large"], default="")
    parser.add_argument("--max-chain-node-splits", type=int, default=0)
    parser.add_argument("--skip-readiness-probe", action="store_true")
    parser.add_argument("--require-non-seed-readiness", action="store_true")
    args = parser.parse_args()
    report = run_graph_layout_acceptance(
        args.base_url,
        symbol=args.symbol,
        scope=args.scope,
        output=args.output,
        chrome_bin=args.chrome_bin,
        timeout=args.timeout,
        viewport_width=args.viewport_width,
        viewport_height=args.viewport_height,
        expect_mobile_layout=args.expect_mobile_layout,
        emulate_reduced_motion=args.emulate_reduced_motion,
        expect_reduced_motion=args.expect_reduced_motion,
        expect_redundant_node_encoding=args.expect_redundant_node_encoding,
        max_overlap_pairs=args.max_overlap_pairs,
        max_near_edge_nodes=args.max_near_edge_nodes,
        min_nodes=args.min_nodes,
        min_links=args.min_links,
        max_visible_nodes=args.max_visible_nodes,
        max_visible_links=args.max_visible_links,
        max_link_label_dom_count=args.max_link_label_dom_count,
        min_fps=args.min_fps,
        max_frame_ms=args.max_frame_ms,
        min_community_labels=args.min_community_labels,
        min_visible_communities=args.min_visible_communities,
        min_community_spread_ratio=args.min_community_spread_ratio,
        min_industry_nodes=args.min_industry_nodes,
        min_raw_knowledge_nodes=args.min_raw_knowledge_nodes,
        min_raw_structured_reports=args.min_raw_structured_reports,
        min_visible_knowledge_types=args.min_visible_knowledge_types,
        min_expansion_neighbor_delta=args.min_expansion_neighbor_delta,
        min_visible_neighbors_after_click=args.min_visible_neighbors_after_click,
        relationship_type=args.relationship_type,
        chain_id=args.chain_id,
        chain_node_id=args.chain_node_id,
        ownership_holder_key=args.ownership_holder_key,
        institutional_holder_key=args.institutional_holder_key,
        min_filtered_relationships=args.min_filtered_relationships,
        expect_filter_chip=args.expect_filter_chip,
        forbid_filter_chip=args.forbid_filter_chip,
        check_persistence=args.check_persistence,
        check_path=args.check_path,
        check_focus_switch=args.check_focus_switch,
        check_view_controls=not args.skip_view_controls,
        check_trail=not args.skip_trail,
        check_saved_subgraph=not args.skip_saved_subgraph,
        check_share_view=args.check_share_view,
        expect_performance_mode=args.expect_performance_mode,
        max_chain_node_splits=args.max_chain_node_splits,
        check_readiness=not args.skip_readiness_probe,
        require_non_seed_readiness=args.require_non_seed_readiness,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
