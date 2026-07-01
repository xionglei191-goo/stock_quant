from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ui_graph_layout_acceptance import run_graph_layout_acceptance


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "artifacts" / "ui-graph-multi-symbol-acceptance.json"

DEFAULT_CASES = [
    {
        "symbol": "AAPL",
        "scope": "local",
        "min_nodes": 32,
        "min_links": 60,
        "max_overlap_pairs": 3,
        "max_near_edge_nodes": 0,
        "min_community_labels": 2,
        "check_persistence": True,
        "check_path": True,
    },
    {
        "symbol": "NVDA",
        "scope": "local",
        "min_nodes": 24,
        "min_links": 35,
        "max_overlap_pairs": 5,
        "max_near_edge_nodes": 0,
        "min_community_labels": 1,
        "check_persistence": True,
        "check_path": True,
    },
    {
        "symbol": "600519",
        "scope": "local",
        "min_nodes": 12,
        "min_links": 10,
        "max_overlap_pairs": 4,
        "max_near_edge_nodes": 0,
        "min_community_labels": 1,
        "check_persistence": True,
        "check_path": False,
    },
    {
        "symbol": "AAPL",
        "scope": "global",
        "min_nodes": 70,
        "min_links": 150,
        "max_overlap_pairs": 80,
        "max_near_edge_nodes": 8,
        "min_community_labels": 2,
        "check_persistence": False,
        "check_path": True,
    },
]


def _case_output_path(output: Path, case: dict[str, Any]) -> Path:
    stem = output.stem
    suffix = output.suffix or ".json"
    symbol = str(case["symbol"]).lower().replace(".", "_")
    scope = str(case["scope"])
    return output.with_name(f"{stem}-{symbol}-{scope}{suffix}")


def run_matrix(
    base_url: str,
    *,
    output: str | Path = DEFAULT_OUTPUT,
    chrome_bin: str = "",
    timeout: float = 45.0,
    cases: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    output_path = Path(output)
    selected_cases = cases or DEFAULT_CASES
    results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for case in selected_cases:
        case_output = _case_output_path(output_path, case)
        report = run_graph_layout_acceptance(
            base_url,
            symbol=str(case["symbol"]),
            scope=str(case.get("scope", "local")),
            output=case_output,
            chrome_bin=chrome_bin,
            timeout=timeout,
            min_nodes=int(case.get("min_nodes", 1)),
            min_links=int(case.get("min_links", 1)),
            max_overlap_pairs=int(case.get("max_overlap_pairs", 999)),
            max_near_edge_nodes=int(case.get("max_near_edge_nodes", 999)),
            min_fps=float(case.get("min_fps", 20.0)),
            max_frame_ms=float(case.get("max_frame_ms", 35.0)),
            min_community_labels=int(case.get("min_community_labels", 2)),
            min_visible_communities=int(case.get("min_visible_communities", 0)),
            min_community_spread_ratio=float(case.get("min_community_spread_ratio", 0.0)),
            check_persistence=bool(case.get("check_persistence", False)),
            check_path=bool(case.get("check_path", False)),
            check_view_controls=bool(case.get("check_view_controls", True)),
            check_trail=bool(case.get("check_trail", True)),
            check_saved_subgraph=bool(case.get("check_saved_subgraph", True)),
        )
        row = {
            "symbol": case["symbol"],
            "scope": case.get("scope", "local"),
            "status": report["status"],
            "artifact": str(case_output.resolve().relative_to(ROOT)),
            "measurement": {
                "nodes": report.get("measurement", {}).get("nodes"),
                "links": report.get("measurement", {}).get("links"),
                "overlap_pairs": report.get("measurement", {}).get("overlap_pairs"),
                "near_edge_nodes": report.get("measurement", {}).get("near_edge_nodes"),
                "visible_communities": report.get("measurement", {}).get("visible_communities"),
                "community_spread_ratio": report.get("measurement", {}).get("community_spread_ratio"),
                "min_community_spread_ratio": report.get("measurement", {}).get("min_community_spread_ratio"),
                "fps": report.get("measurement", {}).get("performance", {}).get("fps"),
                "avg_frame_ms": report.get("measurement", {}).get("performance", {}).get("avg_frame_ms"),
                "saved_subgraph_restored": report.get("measurement", {}).get("saved_subgraph", {}).get("restored_trail_nodes"),
            },
            "failure_count": report.get("failure_count", 0),
            "failures": report.get("failures", []),
        }
        results.append(row)
        if report["status"] != "passed":
            failures.append(row)
    summary = {
        "status": "passed" if not failures else "failed",
        "base_url": base_url,
        "case_count": len(results),
        "failure_count": len(failures),
        "results": results,
        "failures": failures,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run multi-symbol Obsidian-style knowledge graph browser acceptance.")
    parser.add_argument("base_url", nargs="?", default="http://127.0.0.1:8000")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--chrome-bin", default="")
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--symbols", default="", help="Optional comma-separated symbols for local-scope smoke thresholds.")
    args = parser.parse_args()
    cases = None
    if args.symbols.strip():
        cases = [
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
            for symbol in args.symbols.split(",")
            if symbol.strip()
        ]
    report = run_matrix(args.base_url, output=args.output, chrome_bin=args.chrome_bin, timeout=args.timeout, cases=cases)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
