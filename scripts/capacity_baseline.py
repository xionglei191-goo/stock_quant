from __future__ import annotations

import argparse
import json
import time
from statistics import mean
from typing import Any

from app.services import SystemService


def run_capacity_baseline(*, records: int = 100) -> dict[str, Any]:
    service = SystemService()
    timings: dict[str, list[float]] = {"ingest_ms": [], "extract_ms": [], "search_ms": [], "dashboard_ms": []}
    service.register_source(
        {
            "source_id": "baseline_public",
            "source_type": "regulatory",
            "allowed_document_types": ["10-K"],
            "rights_tag": {
                "license_class": "public",
                "training_allowed": False,
                "redistribution_allowed": False,
                "display_use": "allowed",
                "non_display_use": "restricted",
                "derived_data_use": "restricted",
            },
        },
        actor="baseline",
    )
    service.register_issuer({"issuer_id": "issuer_baseline", "legal_name": "Baseline Corp", "market": ["U"]}, actor="baseline")
    service.register_security(
        {"security_id": "sec_baseline", "issuer_id": "issuer_baseline", "ticker": "BASE", "market": "U"},
        actor="baseline",
    )
    for index in range(records):
        document_id = f"doc_baseline_{index:05d}"
        started = time.perf_counter()
        service.ingest_document(
            {
                "document_id": document_id,
                "issuer_id": "issuer_baseline",
                "security_id": "sec_baseline",
                "source_id": "baseline_public",
                "source_type": "regulatory",
                "document_type": "10-K",
                "source_uri": f"https://example.invalid/{document_id}",
                "body": f"FY2025 revenue grew {index % 30 + 1}% and risk factors remain disclosed.",
                "rights_tag": {
                    "license_class": "public",
                    "training_allowed": False,
                    "redistribution_allowed": False,
                    "display_use": "allowed",
                    "non_display_use": "restricted",
                    "derived_data_use": "restricted",
                },
                "language": "en",
            },
            actor="baseline",
        )
        timings["ingest_ms"].append((time.perf_counter() - started) * 1000)
        started = time.perf_counter()
        service.extract_evidence(document_id, actor="baseline")
        timings["extract_ms"].append((time.perf_counter() - started) * 1000)
    for _ in range(10):
        started = time.perf_counter()
        service.search({"q": "revenue risk", "issuer_id": "issuer_baseline"})
        timings["search_ms"].append((time.perf_counter() - started) * 1000)
        started = time.perf_counter()
        service.dashboard()
        timings["dashboard_ms"].append((time.perf_counter() - started) * 1000)
    return {
        "records": records,
        "documents": len(service.store.documents),
        "evidence": len(service.store.evidence),
        "audit_events": len(service.store.audit_log),
        "avg_ms": {key: round(mean(values), 3) for key, values in timings.items()},
        "max_ms": {key: round(max(values), 3) for key, values in timings.items()},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a local capacity and latency baseline for the AI Quant service.")
    parser.add_argument("--records", type=int, default=100)
    args = parser.parse_args()
    print(json.dumps(run_capacity_baseline(records=args.records), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
