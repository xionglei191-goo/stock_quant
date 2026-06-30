from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from urllib import request

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "artifacts" / "graph-quality-center" / "latest.json"


def _load_browser_matrix_runner():
    try:
        from ui_graph_multi_symbol_acceptance import run_matrix
    except ModuleNotFoundError:  # pragma: no cover - exercised when imported as scripts.graph_quality_center
        import sys

        scripts_dir = str(Path(__file__).resolve().parent)
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        from ui_graph_multi_symbol_acceptance import run_matrix
    return run_matrix


def _post_json(base_url: str, path: str, payload: dict[str, Any], *, timeout: float) -> dict[str, Any]:
    req = request.Request(
        base_url.rstrip("/") + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Role": "data_engineer", "X-Actor": "graph_quality_center"},
        method="POST",
    )
    with request.urlopen(req, timeout=timeout) as response:  # noqa: S310 - local CLI talks to configured app URL
        envelope = json.loads(response.read().decode("utf-8"))
    if not envelope.get("success", False):
        raise RuntimeError(json.dumps(envelope.get("error", envelope), ensure_ascii=False))
    return dict(envelope.get("data", {}))


def run_graph_quality_center(
    base_url: str,
    *,
    output: str | Path = DEFAULT_OUTPUT,
    markets: str = "A,U",
    limit: int = 20,
    execute: bool = False,
    run_enrichment: bool = False,
    browser_matrix: bool = False,
    symbols: str = "",
    timeout: float = 45.0,
    chrome_bin: str = "",
) -> dict[str, Any]:
    output_path = Path(output)
    payload = {
        "market": markets,
        "limit": limit,
        "batch_size": limit,
        "execute": execute,
        "run_enrichment": run_enrichment,
    }
    report = _post_json(base_url, "/api/graph/quality-center", payload, timeout=timeout)
    browser_report: dict[str, Any] | None = None
    if browser_matrix:
        run_matrix = _load_browser_matrix_runner()
        matrix_symbols = symbols or ",".join(item["symbol"] for item in report.get("items", [])[: min(5, limit)] if item.get("symbol"))
        browser_report = run_matrix(
            base_url,
            output=output_path.with_name(f"{output_path.stem}-browser-matrix{output_path.suffix or '.json'}"),
            chrome_bin=chrome_bin,
            timeout=timeout,
            cases=[
                {
                    "symbol": symbol.strip(),
                    "scope": "local",
                    "min_nodes": 8,
                    "min_links": 6,
                    "max_overlap_pairs": 8,
                    "max_near_edge_nodes": 2,
                    "min_community_labels": 1,
                    "check_persistence": False,
                    "check_path": False,
                }
                for symbol in matrix_symbols.split(",")
                if symbol.strip()
            ],
        )
    if browser_report is not None:
        report["browser_matrix"] = {
            "status": browser_report.get("status"),
            "case_count": browser_report.get("case_count"),
            "failure_count": browser_report.get("failure_count"),
            "artifact": str(output_path.with_name(f"{output_path.stem}-browser-matrix{output_path.suffix or '.json'}").resolve().relative_to(ROOT)),
        }
        if browser_report.get("status") != "passed":
            report["status"] = "needs_attention"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit knowledge graph gaps, quality gates, enrichment actions, and optional browser acceptance.")
    parser.add_argument("base_url", nargs="?", default="http://127.0.0.1:8000")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--market", "--markets", dest="markets", default="A,U")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--execute", action="store_true", help="Execute enrichment builders when --run-enrichment is set.")
    parser.add_argument("--run-enrichment", action="store_true", help="Run event and relationship builders for sampled symbols.")
    parser.add_argument("--browser-matrix", action="store_true", help="Also run browser-level graph acceptance for sampled symbols.")
    parser.add_argument("--symbols", default="", help="Comma-separated symbols for browser matrix; defaults to sampled symbols.")
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--chrome-bin", default="")
    args = parser.parse_args()
    report = run_graph_quality_center(
        args.base_url,
        output=args.output,
        markets=args.markets,
        limit=args.limit,
        execute=args.execute,
        run_enrichment=args.run_enrichment,
        browser_matrix=args.browser_matrix,
        symbols=args.symbols,
        timeout=args.timeout,
        chrome_bin=args.chrome_bin,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    if report.get("status") in {"failed", "no_targets"} or report.get("browser_matrix", {}).get("status") == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
