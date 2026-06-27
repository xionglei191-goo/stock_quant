from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
import sys
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.production_evidence_plan_check import validate_evidence_collection_plan


OWNER_GROUP_BY_ROLE = {
    "平台负责人": "Platform and Quality",
    "数据工程": "Data and Evidence",
    "NLP/ML 负责人": "Research and AI Workflows",
    "CIO": "Research and AI Workflows / Portfolio",
    "风险/合规": "Governance, Security, and Compliance",
    "分析师": "Research and AI Workflows",
    "未分配": "PM / Release Coordination",
}


TASK_COLLECTION_REQUIREMENTS = {
    "T-402": {
        "procedure": [
            "Build the benchmark from public filings, official company reports, and explicitly licensed/local documents only.",
            "Record the benchmark id, schema version, sample inclusion/exclusion rules, annotator QA process, and pass metrics.",
            "Exclude restricted sell-side reports, transcripts, and boundary-unclear material from training or benchmark gold labels.",
        ],
        "minimum": [
            "300-500 real Chinese filing/report samples plus an English SEC sample set with source and rights metadata.",
            "OCR bbox/table-cell gold labels, annotation manual, summary quality sample, and regression baseline report.",
            "Pass/fail metrics for extraction accuracy, table quality, summary quality, and boundary compliance.",
        ],
        "reviewers": ["Data and Evidence", "Governance, Security, and Compliance"],
    },
    "T-404": {
        "procedure": [
            "Run PostgreSQL, S3-compatible object store, and OpenSearch smoke tests in the real non-local environment.",
            "Capture capacity, latency, backup restore, and least-privilege policy evidence from the same release target.",
            "Record exact environment, command, timestamp, producer, and pass/fail thresholds for every artifact.",
        ],
        "minimum": [
            "PostgreSQL/S3/OpenSearch connectivity and read/write/query proof.",
            "Capacity and latency baseline with target thresholds.",
            "Backup restore drill result and least-privilege access review.",
        ],
        "reviewers": ["Governance, Security, and Compliance"],
    },
    "T-405": {
        "procedure": [
            "Run a large real Form 13F parsing batch for a declared source window.",
            "Compare CUSIP/FIGI/issuer mapping against a gold set and record the accuracy threshold.",
            "Publish the unresolved/unmapped review queue with owner and next action.",
        ],
        "minimum": [
            "Sample size, filing date window, accepted 13F source list, and parser version.",
            "CUSIP/FIGI/issuer mapping accuracy report with threshold and failures.",
            "Unmapped review queue grouped by issuer/security and severity.",
        ],
        "reviewers": ["Platform and Quality"],
    },
    "T-406": {
        "procedure": [
            "Run ADR/Chinese ADR real batch entity mapping and export source-to-entity decisions.",
            "Verify entity page browser acceptance and external Neo4j/Qdrant sync artifacts.",
            "Route review across data quality, UI acceptance, and platform sync owners.",
        ],
        "minimum": [
            "Batch mapping artifact with duplicate/ambiguous entity counts and reviewer decisions.",
            "Entity page browser acceptance evidence using real mapped entities.",
            "Neo4j/Qdrant sync record counts, failure count, and recovery notes.",
        ],
        "reviewers": ["Product and UI", "Platform and Quality"],
    },
    "T-406A": {
        "procedure": [
            "Collect hotspot query/gold refs and offline rerank evaluation without invoking live trading or broker workflows.",
            "Attach company positioning and industry-chain taxonomy review artifacts required by `/api/hotspots/readiness-report`.",
            "Prove persisted or reviewed research tasks through the readiness report gates, not through a standalone queue URI.",
        ],
        "minimum": [
            "Hotspot gold refs artifact, rerank evaluation sample count, top-1 accuracy, and model/fallback version.",
            "Company positioning review and chain taxonomy review artifacts accepted by the readiness endpoint.",
            "Evidence that research tasks are persisted or explicitly reviewed while automation remains disabled.",
        ],
        "reviewers": ["Data and Evidence", "Governance, Security, and Compliance"],
    },
    "T-407": {
        "procedure": [
            "Run real-volume browser acceptance on desktop and mobile viewports across the declared browser matrix.",
            "Record target workflows, screenshot manifest, console errors, overflow criteria, and access-control scenarios.",
            "Store screenshots and acceptance logs under immutable external staging/production URIs.",
        ],
        "minimum": [
            "Browser matrix with versions, viewport sizes, workflows, and pass/fail result.",
            "Screenshot manifest and visual overflow review.",
            "Access-control review for unauthorized, analyst, and governance roles.",
        ],
        "reviewers": ["Product and UI", "Governance, Security, and Compliance"],
    },
    "T-408": {
        "procedure": [
            "Reconcile simulated portfolio performance against NAV/ledger extracts using paper-only data.",
            "Generate the board pack and replay evidence from the same immutable ledger snapshot.",
            "Confirm the packet contains no broker connection, order placement, or live execution artifact.",
        ],
        "minimum": [
            "Performance and NAV/ledger reconciliation with variance explanation.",
            "Board pack artifact and strategy replay acceptance.",
            "Paper-only boundary statement and reviewer sign-off.",
        ],
        "reviewers": ["Governance, Security, and Compliance"],
    },
    "T-409": {
        "procedure": [
            "Run the production PyPortfolioOpt/CVXPY solver comparison with declared versions and parameters.",
            "Capture constraint reports and comparison output using paper-only portfolio inputs.",
            "Record infeasible-solver handling and reviewer sign-off.",
        ],
        "minimum": [
            "Solver version, parameter artifact, and reproducible input snapshot.",
            "Comparison report and constraint report.",
            "Paper-only/no-order-execution boundary statement.",
        ],
        "reviewers": ["Platform and Quality", "Governance, Security, and Compliance"],
    },
    "T-410": {
        "procedure": [
            "Run real research-answer quality evaluation with declared dataset, rubric, judge/human process, and pass threshold.",
            "Check citation provenance, unsupported claims, hallucination rate, and restricted-source exclusion.",
            "Compare fallback behavior at scale and archive both model and fallback outputs.",
        ],
        "minimum": [
            "Model quality eval, fallback comparison, and summary rubric artifacts.",
            "Dataset definition, scoring rubric, pass threshold, and reviewer process.",
            "Citation/provenance and source-boundary compliance results.",
        ],
        "reviewers": ["Governance, Security, and Compliance", "Data and Evidence"],
    },
    "T-411": {
        "procedure": [
            "Run OTel collector ingestion against the real backend and capture query examples for metrics, logs, and traces.",
            "Prove retention policy execution, alert channel delivery, and incident drill flow.",
            "Record timestamps, alert recipient/channel, and drill acceptance criteria.",
        ],
        "minimum": [
            "Collector evidence, logs backend proof, and query evidence.",
            "Retention policy artifact and external alert delivery evidence.",
            "Incident drill evidence with owner, timeline, and result.",
        ],
        "reviewers": ["Governance, Security, and Compliance"],
    },
    "T-412": {
        "procedure": [
            "Complete the production parameter checklist and secret manager integration proof without exposing secret values.",
            "Run or reference the backup/restore artifact for this deployment target.",
            "Archive canary scope, rollback triggers, release checklist, and owner approval.",
        ],
        "minimum": [
            "Production parameters, secret metadata, backup restore evidence, and capacity baseline.",
            "Release checklist with named approver.",
            "Canary plan and rollback plan with trigger criteria.",
        ],
        "reviewers": ["Governance, Security, and Compliance", "PM / Release Coordination"],
    },
    "T-414": {
        "procedure": [
            "Review citation length policy, source review coverage, restricted-source handling, and manual-reference metadata-only behavior.",
            "Use `citation_policy_uri` for the policy artifact accepted by `/api/research/citation-boundary/readiness-report`.",
            "Record reviewed-empty evidence where no manual-reference bodies are allowed.",
        ],
        "minimum": [
            "Citation policy artifact, source review coverage report, and manual-reference review artifact.",
            "Restricted-source exclusion and metadata-only proof.",
            "Research governance artifact showing no restricted training or unsupported citation behavior.",
        ],
        "reviewers": ["Research and AI Workflows", "Data and Evidence"],
    },
    "T-416": {
        "procedure": [
            "Verify every approved A-stock connector endpoint and record license/TOS owner review.",
            "Use the approved connector list: baidu_concepts, cninfo_announcements, dragon_tiger_list, eastmoney_research, tencent_valuation_snapshot, ths_hot_topics, unlock_calendar.",
            "Capture endpoint availability, stability, rate-limit/quota behavior, and field sample artifacts.",
        ],
        "minimum": [
            "Endpoint availability and stability artifacts for every approved connector.",
            "Rate-limit/quota verification and license/TOS review.",
            "Field sample artifact with connector id, timestamp, and schema version.",
        ],
        "reviewers": ["Governance, Security, and Compliance", "Platform and Quality"],
    },
    "T-418": {
        "procedure": [
            "Separate LLM gateway readiness from research-answer quality; reuse T-410 evidence only when source URI and scope are explicit.",
            "Run gateway smoke covering provider/model versions, timeout/fallback behavior, and redacted request ids.",
            "Archive budget/spend limit snapshot and failure-mode evidence without secrets.",
        ],
        "minimum": [
            "Real model quality, fallback quality, gateway smoke, and budget sync artifacts.",
            "Provider/model version, timeout, fallback, and failure-mode coverage.",
            "Secret-free request metadata and spend/limit snapshot.",
        ],
        "reviewers": ["Governance, Security, and Compliance", "Platform and Quality"],
    },
    "T-419": {
        "procedure": [
            "Run non-local Neo4j/Qdrant sync jobs and record expected record counts and actual counts.",
            "Measure batch throughput against declared thresholds.",
            "Inject or document a failure/retry scenario and recovery result.",
        ],
        "minimum": [
            "Neo4j and Qdrant sync artifacts with record counts and job identifiers.",
            "Throughput baseline with threshold and environment.",
            "Failure injection/retry recovery evidence.",
        ],
        "reviewers": ["Data and Evidence"],
    },
    "T-420": {
        "procedure": [
            "Declare scheduler choice and environment, then run deployment evidence for the real orchestration target.",
            "Prove external sensor connectivity, distributed worker queue isolation, and a large-window backfill drill.",
            "Capture OpenLineage and MLflow client evidence with lineage/run identifiers.",
        ],
        "minimum": [
            "Scheduler deployment, worker pool, external sensor, and backfill drill artifacts.",
            "OpenLineage client and MLflow registry proof.",
            "Run logs with environment, backfill window, status, and failure handling.",
        ],
        "reviewers": ["Data and Evidence", "Governance, Security, and Compliance"],
    },
    "T-421": {
        "procedure": [
            "Collect secret/KMS evidence as metadata only; never archive secret values, tokens, private keys, or signed URLs.",
            "Run external delete evidence from the approved executor identity and capture permission-denied/audit or red-team proof.",
            "Verify scoped API permissions, key rotation evidence, and object/search delete behavior in the external environment.",
        ],
        "minimum": [
            "Secret manager/KMS metadata with no secret values, provider scope, key rotation evidence, and least-privilege policy.",
            "External delete executor identity, object/search delete result, and audit trail.",
            "Permission review or red-team proof with no credentials in artifacts.",
        ],
        "reviewers": ["Platform and Quality", "PM / Release Coordination"],
    },
}


def owner_group_for_role(owner_role: str) -> str:
    return OWNER_GROUP_BY_ROLE.get(owner_role, "PM / Release Coordination")


def _atomic_write_text(path: str | Path, text: str) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_name(f".{output_path.name}.tmp")
    tmp_path.write_text(text, encoding="utf-8")
    tmp_path.replace(output_path)


def build_owner_packets(plan: Mapping[str, Any]) -> dict[str, Any]:
    validation = validate_evidence_collection_plan(plan)
    if not validation["passed"]:
        raise AssertionError(json.dumps(validation, ensure_ascii=False, sort_keys=True))
    tasks = [dict(item) for item in plan.get("tasks", []) if isinstance(item, Mapping)]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for task in tasks:
        grouped[str(task.get("owner_role", "未分配"))].append(task)
    owner_packets: list[dict[str, Any]] = []
    for owner_role, rows in sorted(grouped.items()):
        artifact_field_count = sum(len(row.get("artifact_fields", [])) for row in rows)
        owner_packets.append(
            {
                "owner_role": owner_role,
                "task_count": len(rows),
                "artifact_field_count": artifact_field_count,
                "task_ids": [str(row.get("task_id", "")) for row in rows],
                "tasks": rows,
            }
        )
    return {
        "packet_id": "production_external_evidence_owner_packets",
        "source_plan_id": plan.get("plan_id", ""),
        "production_boundary": "owner packets are collection instructions only; they are not release evidence",
        "owner_count": len(owner_packets),
        "task_count": len(tasks),
        "artifact_field_count": sum(packet["artifact_field_count"] for packet in owner_packets),
        "owners": owner_packets,
    }


def render_owner_packets_markdown(packet: Mapping[str, Any]) -> str:
    lines = [
        "# Production External Evidence Owner Packets",
        "",
        "- Status: active",
        "- Owner group: PM / Release Coordination",
        "- Last updated: 2026-06-27",
        "- Related tasks: T-402, T-404, T-405, T-406, T-406A, T-407, T-408, T-409, T-410, T-411, T-412, T-414, T-416, T-418, T-419, T-420, T-421",
        "- Scope: owner-by-owner external evidence collection instructions for non-local production closure",
        "- Non-goals: local-only release approval, generating or fabricating evidence, broker integration, automatic trading",
        "",
        "## Purpose",
        "",
        "These packets convert the production evidence collection plan into owner-specific work. They are collection instructions only and are not release evidence. Every artifact URI must later be replaced with a concrete external staging/production archive URI, validated by `scripts/production_evidence_plan_check.py --require-filled-uris`, covered by artifact inventory, and passed through the strict release gate.",
        "",
        "## Summary",
        "",
        f"- Owner packets: {packet.get('owner_count', 0)}",
        f"- External evidence tasks: {packet.get('task_count', 0)}",
        f"- Required artifact fields: {packet.get('artifact_field_count', 0)}",
        f"- Boundary: {packet.get('production_boundary', '')}",
        "",
    ]
    for owner in packet.get("owners", []):
        if not isinstance(owner, Mapping):
            continue
        lines.extend(
            [
                f"## {owner.get('owner_role', '未分配')}",
                "",
                f"- Task count: {owner.get('task_count', 0)}",
                f"- Artifact field count: {owner.get('artifact_field_count', 0)}",
                f"- Task IDs: {', '.join(str(item) for item in owner.get('task_ids', []))}",
                "",
            ]
        )
        for task in owner.get("tasks", []):
            if not isinstance(task, Mapping):
                continue
            fields = [str(item) for item in task.get("artifact_fields", [])]
            blockers = [str(item) for item in task.get("external_evidence_blockers", [])]
            task_id = str(task.get("task_id", ""))
            requirements = TASK_COLLECTION_REQUIREMENTS.get(task_id, {})
            procedure = [str(item) for item in requirements.get("procedure", [])] if isinstance(requirements, Mapping) else []
            minimum = [str(item) for item in requirements.get("minimum", [])] if isinstance(requirements, Mapping) else []
            reviewers = [str(item) for item in requirements.get("reviewers", [])] if isinstance(requirements, Mapping) else []
            lines.extend(
                [
                    f"### {task_id}",
                    "",
                    f"- Readiness endpoint: `{task.get('readiness_endpoint', '')}`",
                    f"- Acceptance rule: {task.get('acceptance_rule', '')}",
                    f"- Owner group: {owner_group_for_role(str(owner.get('owner_role', '未分配')))}",
                    "- External blockers:",
                    *[f"  - {item}" for item in blockers],
                    "- Required artifact fields:",
                    *[f"  - `{field}`" for field in fields],
                    "- URI template:",
                ]
            )
            template = task.get("artifact_uri_template", {})
            if isinstance(template, Mapping):
                for field in fields:
                    lines.append(f"  - `{field}`: `{template.get(field, '')}`")
            if procedure:
                lines.extend(["- Collection procedure:", *[f"  - {item}" for item in procedure]])
            if minimum:
                lines.extend(["- Minimum artifact contents:", *[f"  - {item}" for item in minimum]])
            if reviewers:
                lines.extend(["- Reviewer routing:", *[f"  - {item}" for item in reviewers]])
            lines.append("")
    lines.extend(
        [
            "## Release Gate Handoff",
            "",
            "After owners upload the real evidence objects, run:",
            "",
            "```bash",
            "python3 scripts/production_evidence_plan_check.py artifacts/production-evidence-collection-plan.json --require-filled-uris",
            "python3 scripts/production_artifact_inventory_check.py artifacts/production-artifact-inventory.json --plan artifacts/production-evidence-collection-plan.json --evidence-package artifacts/readiness-evidence-package.json --manifest artifacts/production-closure-manifest.json",
            "python3 scripts/production_release_gate.py --plan artifacts/production-evidence-collection-plan.json --evidence-package artifacts/readiness-evidence-package.json --artifact-inventory artifacts/production-artifact-inventory.json --artifact-bundle-root artifacts/production-evidence-bundle --manifest-output artifacts/production-closure-manifest.json",
            "```",
            "",
            "Do not use local-only artifacts, demo artifacts, localhost URLs, `file://`, `local://`, or `artifact://staging-local` as production evidence.",
        ]
    )
    return "\n".join(lines) + "\n"


def render_task_packet_markdown(task: Mapping[str, Any], *, owner_role: str) -> str:
    task_id = str(task.get("task_id", ""))
    fields = [str(item) for item in task.get("artifact_fields", [])]
    blockers = [str(item) for item in task.get("external_evidence_blockers", [])]
    requirements = TASK_COLLECTION_REQUIREMENTS.get(task_id, {})
    procedure = [str(item) for item in requirements.get("procedure", [])] if isinstance(requirements, Mapping) else []
    minimum = [str(item) for item in requirements.get("minimum", [])] if isinstance(requirements, Mapping) else []
    reviewers = [str(item) for item in requirements.get("reviewers", [])] if isinstance(requirements, Mapping) else []
    lines = [
        f"# Production Evidence Task Packet: {task_id}",
        "",
        "- Status: blocked_external_evidence",
        f"- Owner role: {owner_role}",
        f"- Owner group: {owner_group_for_role(owner_role)}",
        "- Last updated: 2026-06-27",
        f"- Related task: {task_id}",
        "- Scope: collect real external staging/production evidence for this task",
        "- Non-goals: local-only release approval, generating or fabricating evidence, broker integration, automatic trading",
        "",
        "## Objective",
        "",
        f"Collect and archive the external evidence required to unblock `{task_id}` for non-local production closure.",
        "",
        "## Readiness Endpoint",
        "",
        f"- `{task.get('readiness_endpoint', '')}`",
        "",
        "## External Blockers",
        "",
        *[f"- {item}" for item in blockers],
        "",
        "## Required Artifact Fields",
        "",
        *[f"- `{field}`" for field in fields],
        "",
        "## URI Template",
        "",
    ]
    template = task.get("artifact_uri_template", {})
    if isinstance(template, Mapping):
        for field in fields:
            lines.append(f"- `{field}`: `{template.get(field, '')}`")
    lines.extend(
        [
            "",
            "## Collection Procedure",
            "",
            *[f"- {item}" for item in procedure],
            "",
            "## Minimum Artifact Contents",
            "",
            *[f"- {item}" for item in minimum],
            "",
            "## Reviewer Routing",
            "",
            *[f"- {item}" for item in reviewers],
            "",
            "## Source And Boundary Rules",
            "",
            "- Evidence must come from the declared external staging/production environment.",
            "- Preserve local-first and paper-only boundaries; do not include broker credentials, live order execution, or automatic trading evidence.",
            "- Redact secrets, tokens, signed URLs, private keys, and personal credentials before archiving.",
            "- Restricted or boundary-unclear research content may be metadata/manual-reference evidence only, not training data or automated fact evidence.",
        ]
    )
    lines.extend(
        [
            "",
            "## Acceptance",
            "",
            "- Every URI is a concrete external staging/production archive URI.",
            "- No URI is local-only, demo, localhost, `file://`, `local://`, or `artifact://staging-local`.",
            "- Artifact inventory records sha256, size, environment, producer, owner, retention, and immutable/object-lock metadata.",
            "- The filled evidence plan passes `scripts/production_evidence_plan_check.py --require-filled-uris`.",
            "- The strict release gate passes before any task status is changed to DONE.",
            "",
            "## Commands",
            "",
            "```bash",
            "python3 scripts/production_evidence_plan_check.py artifacts/production-evidence-collection-plan.json --require-filled-uris",
            "python3 scripts/production_artifact_inventory_check.py artifacts/production-artifact-inventory.json --plan artifacts/production-evidence-collection-plan.json --evidence-package artifacts/readiness-evidence-package.json --manifest artifacts/production-closure-manifest.json",
            "python3 scripts/production_release_gate.py --plan artifacts/production-evidence-collection-plan.json --evidence-package artifacts/readiness-evidence-package.json --artifact-inventory artifacts/production-artifact-inventory.json --artifact-bundle-root artifacts/production-evidence-bundle --manifest-output artifacts/production-closure-manifest.json",
            "```",
        ]
    )
    return "\n".join(lines) + "\n"


def write_task_packets(packet: Mapping[str, Any], output_dir: str | Path) -> list[str]:
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for owner in packet.get("owners", []):
        if not isinstance(owner, Mapping):
            continue
        owner_role = str(owner.get("owner_role", "未分配"))
        for task in owner.get("tasks", []):
            if not isinstance(task, Mapping):
                continue
            task_id = str(task.get("task_id", "")).lower()
            safe_task_id = task_id.replace("_", "-")
            path = target / f"{safe_task_id}-production-evidence.md"
            _atomic_write_text(path, render_task_packet_markdown(task, owner_role=owner_role))
            written.append(str(path))
    return written


def validate_owner_packets(packet: Mapping[str, Any]) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []

    def expect(condition: bool, check: str, error: str, **extra: Any) -> None:
        if not condition:
            failures.append({"check": check, "error": error, **extra})

    owners = [dict(item) for item in packet.get("owners", []) if isinstance(item, Mapping)]
    expect(packet.get("packet_id") == "production_external_evidence_owner_packets", "packet_id", "unexpected packet id")
    expect("not release evidence" in str(packet.get("production_boundary", "")).lower(), "production_boundary", "packets must state they are not release evidence")
    expect(int(packet.get("owner_count", -1)) == len(owners), "owner_count", "owner_count must match owner rows")
    task_ids: list[str] = []
    artifact_field_count = 0
    for owner in owners:
        tasks = [dict(item) for item in owner.get("tasks", []) if isinstance(item, Mapping)]
        expect(int(owner.get("task_count", -1)) == len(tasks), "owner_task_count", "owner task_count mismatch", owner_role=owner.get("owner_role"))
        owner_fields = sum(len(task.get("artifact_fields", [])) for task in tasks)
        artifact_field_count += owner_fields
        expect(int(owner.get("artifact_field_count", -1)) == owner_fields, "owner_artifact_field_count", "owner artifact_field_count mismatch", owner_role=owner.get("owner_role"))
        for task in tasks:
            task_id = str(task.get("task_id", ""))
            task_ids.append(task_id)
            requirements = TASK_COLLECTION_REQUIREMENTS.get(task_id, {})
            expect(str(task.get("status", "")) == "blocked_external_evidence", "task_status", "task must remain blocked_external_evidence", task_id=task_id)
            expect(bool(task.get("readiness_endpoint")), "readiness_endpoint", "readiness endpoint is required", task_id=task_id)
            expect(bool(task.get("artifact_fields")), "artifact_fields", "artifact fields are required", task_id=task_id)
            expect(bool(task.get("external_evidence_blockers")), "external_evidence_blockers", "external blockers are required", task_id=task_id)
            expect(bool(requirements.get("procedure")) if isinstance(requirements, Mapping) else False, "collection_procedure", "task collection procedure is required", task_id=task_id)
            expect(bool(requirements.get("minimum")) if isinstance(requirements, Mapping) else False, "minimum_artifact_contents", "minimum artifact contents are required", task_id=task_id)
    duplicates = sorted(task_id for task_id in set(task_ids) if task_ids.count(task_id) > 1)
    expect(not duplicates, "duplicate_task_ids", "task ids must not be duplicated across owners", duplicates=duplicates)
    expect(int(packet.get("task_count", -1)) == len(task_ids), "task_count", "task_count must match all owner task rows")
    expect(int(packet.get("artifact_field_count", -1)) == artifact_field_count, "artifact_field_count", "artifact_field_count must match all fields")
    passed = not failures
    return {
        "status": "passed" if passed else "failed",
        "passed": passed,
        "owner_count": len(owners),
        "task_count": len(task_ids),
        "artifact_field_count": artifact_field_count,
        "failure_count": len(failures),
        "failures": failures,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build owner-specific production evidence collection packets.")
    parser.add_argument("plan_json", help="Production evidence collection plan JSON.")
    parser.add_argument("--output-json", default="", help="Optional output JSON path for the owner packets.")
    parser.add_argument("--output-md", default="", help="Optional output Markdown path for owner-readable packets.")
    parser.add_argument("--output-dir", default="", help="Optional directory for one Markdown packet per task.")
    args = parser.parse_args()
    plan = json.loads(Path(args.plan_json).read_text(encoding="utf-8"))
    packet = build_owner_packets(plan)
    validation = validate_owner_packets(packet)
    rendered_json = json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output_json:
        _atomic_write_text(args.output_json, rendered_json + "\n")
    if args.output_md:
        _atomic_write_text(args.output_md, render_owner_packets_markdown(packet))
    written_task_packets: list[str] = []
    if args.output_dir:
        written_task_packets = write_task_packets(packet, args.output_dir)
    print(json.dumps(validation, ensure_ascii=False, indent=2, sort_keys=True))
    if written_task_packets:
        print(json.dumps({"task_packet_count": len(written_task_packets), "task_packet_dir": args.output_dir}, ensure_ascii=False, indent=2, sort_keys=True))
    if not validation["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
