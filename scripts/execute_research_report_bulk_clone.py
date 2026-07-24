#!/usr/bin/env python3
"""Execute an exact registry batch range in one isolated research-report clone.

This is a T-619 bulk-clone accelerator. It never accepts a primary target and
never performs updates or deletes. The caller must promote its verified clone
result through a separate, single primary insert-only transaction.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.execute_research_report_clone_batch import ApiClient, execute_batch
from scripts.recover_watchlist_research_reports import BOUNDARY


EXPECTED_MANIFEST = "e932f352047eb58b4e0df797215598b7ee0bdd25b920432bf6c89173a301fa5e"


class BulkCloneRefused(RuntimeError):
    """Raised before a clone API mutation when the bulk contract is invalid."""


def _load(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BulkCloneRefused(f"{label} is unreadable") from exc
    if not isinstance(value, dict):
        raise BulkCloneRefused(f"{label} must be an object")
    return value


def _sha(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _batch_number(batch_id: str) -> int:
    try:
        return int(batch_id.rsplit("-", 1)[1])
    except (IndexError, ValueError) as exc:
        raise BulkCloneRefused("registry batch id is invalid") from exc


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decision", type=Path, required=True)
    parser.add_argument("--identity-manifest", type=Path, required=True)
    parser.add_argument("--approval", type=Path, required=True)
    parser.add_argument("--filesystem-root", type=Path, required=True)
    parser.add_argument("--registry-root", type=Path, required=True)
    parser.add_argument("--api-root", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--citation-char-limit", type=int, default=1200)
    parser.add_argument("--max-text-chars", type=int, default=50000)
    parser.add_argument("--pdf-pages", type=int, default=3)
    parser.add_argument("--pdftotext-timeout", type=int, default=10)
    parser.add_argument("--workers", type=int, default=4)
    return parser.parse_args()


def main() -> int:
    args = _args()
    approval = _load(args.approval, "bulk approval")
    if (
        approval.get("status") != "approved"
        or approval.get("manifest_sha256") != EXPECTED_MANIFEST
        or approval.get("primary_writes_allowed_during_clone") is not False
        or approval.get("updates_allowed") is not False
        or approval.get("deletes_allowed") is not False
    ):
        raise BulkCloneRefused("bulk approval does not preserve the clone-only insert contract")
    if not args.base_url.startswith(("http://127.0.0.1:18015", "http://localhost:18015")):
        raise BulkCloneRefused("bulk executor only accepts the attested clone endpoint")

    decision = _load(args.decision, "recovery decision")
    manifest = _load(args.identity_manifest, "identity manifest")
    identity_integrity = manifest.get("integrity") if isinstance(manifest.get("integrity"), Mapping) else {}
    decision_evidence = decision.get("input_evidence") if isinstance(decision.get("input_evidence"), Mapping) else {}
    if (
        decision_evidence.get("identity_manifest_sha256") != EXPECTED_MANIFEST
        or identity_integrity.get("manifest_sha256") != EXPECTED_MANIFEST
    ):
        raise BulkCloneRefused("registry manifest binding changed")
    entries = manifest.get("entries") if isinstance(manifest.get("entries"), list) else []
    entry_by_id = {str(item.get("report_id") or ""): dict(item) for item in entries if isinstance(item, Mapping)}
    if not entry_by_id or len(entry_by_id) != len(entries):
        raise BulkCloneRefused("identity manifest report IDs are incomplete or duplicate")
    recovery = decision.get("recovery_plan") if isinstance(decision.get("recovery_plan"), Mapping) else {}
    candidates = recovery.get("batches") if isinstance(recovery.get("batches"), list) else []
    batches = [dict(item) for item in candidates if isinstance(item, Mapping) and 15 <= _batch_number(str(item.get("batch_id") or "")) <= 44]
    batches.sort(key=lambda item: _batch_number(str(item["batch_id"])))
    if len(batches) != 30 or sum(int(item.get("report_count") or 0) for item in batches) != 7303:
        raise BulkCloneRefused("bulk range must contain exactly 30 batches and 7303 reports")

    if args.workers < 1 or args.workers > 8:
        raise BulkCloneRefused("--workers must be between 1 and 8")
    initial_output: dict[str, Any] = {
        "schema_version": "research-report-bulk-clone-execution-v1",
        "task_id": "T-619",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "running",
        "manifest_sha256": EXPECTED_MANIFEST,
        "batch_range": ["t613-batch-0015", "t613-batch-0044"],
        "expected_report_count": 7303,
        "primary_writes_allowed": False,
        "delete_operations": [],
        "update_operations": [],
        "raw_files_preserved": True,
        "opensearch_preserved": True,
        "fact_opinion_boundary": BOUNDARY,
        "batches": [],
    }
    seen: set[str] = set()
    plans: list[dict[str, Any]] = []
    for batch in batches:
        report_ids = [str(value) for value in batch.get("report_ids", [])]
        selected = [entry_by_id.get(report_id) for report_id in report_ids]
        if len(report_ids) != int(batch["report_count"]) or len(set(report_ids)) != len(report_ids) or any(item is None for item in selected):
            raise BulkCloneRefused(f"{batch['batch_id']} does not bind to exact identity entries")
        if seen.intersection(report_ids):
            raise BulkCloneRefused("report IDs overlap across bulk batches")
        seen.update(report_ids)
        plans.append({
            "related_task": "T-619",
            "manifest_sha256": EXPECTED_MANIFEST,
            "batch_id": batch["batch_id"],
            "batch_sha256": batch["batch_sha256"],
            "batch_entries": selected,
        })

    output = initial_output
    if args.output.is_file():
        checkpoint = _load(args.output, "bulk checkpoint")
        if (
            checkpoint.get("schema_version") != initial_output["schema_version"]
            or checkpoint.get("manifest_sha256") != EXPECTED_MANIFEST
            or checkpoint.get("primary_writes_allowed") is not False
        ):
            raise BulkCloneRefused("existing bulk checkpoint is incompatible")
        output = checkpoint
        output.pop("result_sha256", None)
        output["status"] = "running"
    completed_ids = {
        str(item.get("batch_id") or "")
        for item in output.get("batches", [])
        if isinstance(item, Mapping) and item.get("status") == "passed"
    }
    pending = [plan for plan in plans if str(plan["batch_id"]) not in completed_ids]

    def run_plan(plan: Mapping[str, Any]) -> dict[str, Any]:
        return execute_batch(
            plan,
            client=ApiClient(args.base_url, timeout=max(1.0, args.timeout)),
            filesystem_root=args.filesystem_root,
            registry_root=args.registry_root,
            api_root=args.api_root,
            citation_char_limit=max(1, min(args.citation_char_limit, 4000)),
            max_text_chars=max(1000, args.max_text_chars),
            pdf_pages=max(1, args.pdf_pages),
            pdftotext_timeout=max(1, args.pdftotext_timeout),
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(run_plan, plan): str(plan["batch_id"]) for plan in pending}
        for future in as_completed(futures):
            result = future.result()
            output["batches"].append(result)
            output["batches"].sort(key=lambda item: _batch_number(str(item.get("batch_id") or "")))
            output["completed_batches"] = sum(item.get("status") == "passed" for item in output["batches"])
            output["processed_count"] = sum(int(item.get("processed_count") or 0) for item in output["batches"])
            output["failed_count"] = sum(int(item.get("failed_count") or 0) for item in output["batches"])
            output["evidence_count"] = sum(int(item.get("evidence_count") or 0) for item in output["batches"])
            if result.get("status") != "passed":
                output["status"] = "failed"
            args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    output["status"] = "passed" if output.get("processed_count") == 7303 and output.get("failed_count") == 0 else output.get("status", "failed")
    output["result_sha256"] = _sha({key: value for key, value in output.items() if key != "result_sha256"})
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: output.get(key) for key in ("status", "completed_batches", "processed_count", "failed_count", "evidence_count", "result_sha256")}, ensure_ascii=False))
    return 0 if output["status"] == "passed" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BulkCloneRefused as exc:
        raise SystemExit(f"bulk clone refused: {exc}") from exc
