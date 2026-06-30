from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from scripts.graph_acceptance_fixture import prepare_graph_acceptance_fixture
    from scripts.seed_obsidian_knowledge_graph import post_seed as seed_obsidian_knowledge_graph
    from scripts.ui_graph_layout_acceptance import run_graph_layout_acceptance
except ModuleNotFoundError:
    from graph_acceptance_fixture import prepare_graph_acceptance_fixture
    from seed_obsidian_knowledge_graph import post_seed as seed_obsidian_knowledge_graph
    from ui_graph_layout_acceptance import run_graph_layout_acceptance


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "artifacts" / "ui-graph-relationship-filter-acceptance.json"

DEFAULT_CASES = [
    {"symbol": "AAPL", "relationship_type": "listed_security", "min_relationships": 1, "min_nodes": 2, "min_links": 2},
    {"symbol": "AAPL", "relationship_type": "institution_coverage", "min_relationships": 4, "min_nodes": 5, "min_links": 8, "requires_acceptance_fixture": True},
    {"symbol": "AAPL", "relationship_type": "industry_peer", "min_relationships": 1, "min_links": 8},
    {"symbol": "AAPL", "relationship_type": "upstream_of", "min_relationships": 1, "min_links": 8},
    {"symbol": "AAPL", "relationship_type": "downstream_of", "min_relationships": 1, "min_links": 8},
    {"symbol": "AAPL", "relationship_type": "shareholder", "ownership_holder_key": "external_graph_acceptance_alpha_capital", "case_label": "ownership_holder_alpha", "min_nodes": 5, "min_links": 8, "min_relationships": 2, "requires_acceptance_fixture": True},
    {"symbol": "AAPL", "institutional_holder_key": "0000102909", "case_label": "institutional_holder_vanguard", "min_nodes": 8, "min_links": 8, "min_relationships": 0},
    {"symbol": "NVDA", "relationship_type": "listed_security", "min_relationships": 1, "min_nodes": 2, "min_links": 2},
    {"symbol": "NVDA", "relationship_type": "institution_coverage", "min_relationships": 5, "min_nodes": 5, "min_links": 8, "requires_acceptance_fixture": True},
    {"symbol": "600519", "relationship_type": "listed_security", "min_relationships": 1, "min_nodes": 2, "min_links": 2},
    {"symbol": "600519", "relationship_type": "institution_coverage", "min_relationships": 3, "min_nodes": 5, "min_links": 8, "requires_acceptance_fixture": True},
]

def _case_output_path(output: Path, case: dict[str, Any]) -> Path:
    stem = output.stem
    suffix = output.suffix or ".json"
    symbol = str(case["symbol"]).lower().replace(".", "_")
    label = str(case.get("case_label") or case.get("relationship_type") or case.get("institutional_holder_key") or "all").lower().replace(".", "_")
    return output.with_name(f"{stem}-{symbol}-{label}{suffix}")


def _artifact_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(ROOT))
    except ValueError:
        return str(resolved)


def run_filter_matrix(
    base_url: str,
    *,
    output: str | Path = DEFAULT_OUTPUT,
    chrome_bin: str = "",
    timeout: float = 45.0,
    cases: list[dict[str, Any]] | None = None,
    prepare_industry_fixture: bool = True,
) -> dict[str, Any]:
    output_path = Path(output)
    selected_cases = cases or DEFAULT_CASES
    fixture_result = prepare_graph_acceptance_fixture(base_url, timeout=timeout) if prepare_industry_fixture else {"status": "skipped"}
    obsidian_seed_result = seed_obsidian_knowledge_graph(base_url, timeout=timeout) if prepare_industry_fixture else {"status": "skipped"}
    results: list[dict[str, Any]] = []
    skipped_cases: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for case in selected_cases:
        if not prepare_industry_fixture and case.get("requires_acceptance_fixture"):
            skipped_cases.append(
                {
                    "symbol": case["symbol"],
                    "relationship_type": case.get("relationship_type", ""),
                    "ownership_holder_key": case.get("ownership_holder_key", ""),
                    "institutional_holder_key": case.get("institutional_holder_key", ""),
                    "case_label": case.get("case_label", ""),
                    "reason": "requires_acceptance_fixture",
                }
            )
            continue
        case_output = _case_output_path(output_path, case)
        report = run_graph_layout_acceptance(
            base_url,
            symbol=str(case["symbol"]),
            scope="local",
            output=case_output,
            chrome_bin=chrome_bin,
            timeout=timeout,
            min_nodes=int(case.get("min_nodes", 8)),
            min_links=int(case.get("min_links", 8)),
            max_overlap_pairs=int(case.get("max_overlap_pairs", 8)),
            max_near_edge_nodes=int(case.get("max_near_edge_nodes", 2)),
            min_community_labels=int(case.get("min_community_labels", 1)),
            relationship_type=str(case.get("relationship_type", "")),
            ownership_holder_key=str(case.get("ownership_holder_key", "")),
            institutional_holder_key=str(case.get("institutional_holder_key", "")),
            min_filtered_relationships=int(case.get("min_relationships", 1)),
            check_persistence=False,
            check_path=False,
            check_view_controls=True,
            check_trail=True,
            check_saved_subgraph=True,
        )
        measurement = report.get("measurement", {})
        row = {
            "symbol": case["symbol"],
            "relationship_type": case.get("relationship_type", ""),
            "ownership_holder_key": case.get("ownership_holder_key", ""),
            "institutional_holder_key": case.get("institutional_holder_key", ""),
            "case_label": case.get("case_label", ""),
            "status": report["status"],
            "artifact": _artifact_path(case_output),
            "measurement": {
                "nodes": measurement.get("nodes"),
                "links": measurement.get("links"),
                "raw_relationships": measurement.get("raw_relationships"),
                "raw_relationship_types": measurement.get("raw_relationship_types"),
                "raw_edge_relationships": measurement.get("raw_edge_relationships"),
                "raw_edge_relationship_types": measurement.get("raw_edge_relationship_types"),
                "raw_edge_types": measurement.get("raw_edge_types"),
                "filter_chips": measurement.get("filter_chips"),
                "fps": measurement.get("performance", {}).get("fps"),
                "avg_frame_ms": measurement.get("performance", {}).get("avg_frame_ms"),
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
        "industry_fixture": fixture_result,
        "obsidian_seed": obsidian_seed_result,
        "case_count": len(results),
        "skipped_case_count": len(skipped_cases),
        "failure_count": len(failures),
        "results": results,
        "skipped_cases": skipped_cases,
        "failures": failures,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run relationship-filtered knowledge graph browser acceptance.")
    parser.add_argument("base_url", nargs="?", default="http://127.0.0.1:8000")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--chrome-bin", default="")
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--skip-industry-fixture", action="store_true")
    args = parser.parse_args()
    report = run_filter_matrix(args.base_url, output=args.output, chrome_bin=args.chrome_bin, timeout=args.timeout, prepare_industry_fixture=not args.skip_industry_fixture)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
