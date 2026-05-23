#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.utils import new_id, utcnow


DEFAULT_DSN = "postgresql://ai_quant:ai_quant_dev_password@127.0.0.1:15432/ai_quant"

SENSITIVE_CONTACT_PATTERNS = [
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("cn_mobile", re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")),
    ("cn_id", re.compile(r"(?<!\d)\d{17}[\dXx](?!\w)")),
    (
        "secret_literal",
        re.compile(r"\b(api[_-]?key|access[_-]?token|bearer[_-]?token|secret|signature)\b\s*[:=]\s*['\"]?([A-Za-z0-9_\-./+=]{8,})", re.IGNORECASE),
    ),
]


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def mask_sensitive_value(match: re.Match[str], *, finding_type: str) -> str:
    value = match.group(0)
    if finding_type == "secret_literal":
        key = match.group(1) if match.lastindex else "secret"
        return f"{key}=***REDACTED***"
    if finding_type == "email" and "@" in value:
        local, domain = value.split("@", 1)
        local_mask = f"{local[:1]}***" if local else "***"
        if "." in domain:
            domain_head, domain_tail = domain.rsplit(".", 1)
            domain = f"{domain_head[:1]}***.{domain_tail}"
        else:
            domain = "***"
        return f"{local_mask}@{domain}"
    if finding_type == "cn_mobile" and len(value) >= 7:
        return f"{value[:3]}****{value[-4:]}"
    if finding_type == "cn_id" and len(value) >= 8:
        return f"{value[:4]}**********{value[-4:]}"
    return "***REDACTED***"


def redact_text(text: str) -> tuple[str, dict[str, int]]:
    redacted = text
    counts: dict[str, int] = {}
    for finding_type, pattern in SENSITIVE_CONTACT_PATTERNS:
        matches = list(pattern.finditer(redacted))
        if not matches:
            continue
        counts[finding_type] = counts.get(finding_type, 0) + len(matches)
        redacted = pattern.sub(lambda item, finding_type=finding_type: mask_sensitive_value(item, finding_type=finding_type), redacted)
    return redacted, counts


def merge_counts(target: dict[str, int], increment: dict[str, int]) -> None:
    for key, value in increment.items():
        target[key] = target.get(key, 0) + int(value)


def is_local_research_payload(payload: dict[str, Any]) -> bool:
    rights_tag = payload.get("rights_tag")
    if isinstance(rights_tag, dict) and rights_tag.get("license_class") == "local_research_reference":
        return True
    return str(payload.get("source_id", "")) == "local_research_unknown"


def load_records(cursor: Any, collection: str) -> list[tuple[str, dict[str, Any]]]:
    cursor.execute(
        """
        SELECT item_id, payload
        FROM ai_quant.records
        WHERE collection = %s
        ORDER BY item_id
        """,
        (collection,),
    )
    rows: list[tuple[str, dict[str, Any]]] = []
    for item_id, payload in cursor.fetchall():
        if isinstance(payload, str):
            payload = json.loads(payload)
        rows.append((str(item_id), dict(payload)))
    return rows


def run_redaction(*, dsn: str, output: Path, dry_run: bool = False) -> dict[str, Any]:
    try:
        import psycopg  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:
        raise RuntimeError("psycopg is required: python -m pip install 'psycopg[binary]>=3.1'") from exc

    started_at = utc_iso()
    totals = {
        "documents_scanned": 0,
        "documents_updated": 0,
        "evidence_scanned": 0,
        "evidence_updated": 0,
        "research_answers_scanned": 0,
        "research_answers_updated": 0,
    }
    redaction_counts: dict[str, int] = {}
    local_research_document_ids: set[str] = set()
    audit_event_id = ""
    audit_timestamp = utcnow()

    with psycopg.connect(dsn) as connection:
        with connection.cursor() as cursor:
            document_updates: list[tuple[str, str]] = []
            for item_id, payload in load_records(cursor, "documents"):
                if not is_local_research_payload(payload):
                    continue
                local_research_document_ids.add(str(payload.get("document_id") or item_id))
                totals["documents_scanned"] += 1
                body = str(payload.get("body", ""))
                redacted, counts = redact_text(body)
                if redacted == body:
                    continue
                payload["body"] = redacted
                merge_counts(redaction_counts, counts)
                document_updates.append((json.dumps(payload, ensure_ascii=False, sort_keys=True), item_id))
            totals["documents_updated"] = len(document_updates)

            evidence_updates: list[tuple[str, str]] = []
            for item_id, payload in load_records(cursor, "evidence"):
                if str(payload.get("document_id", "")) not in local_research_document_ids:
                    continue
                totals["evidence_scanned"] += 1
                changed = False
                combined_counts: dict[str, int] = {}
                for field_name in ("span_text", "canonical_text"):
                    text = str(payload.get(field_name, ""))
                    redacted, counts = redact_text(text)
                    if redacted != text:
                        payload[field_name] = redacted
                        changed = True
                        merge_counts(combined_counts, counts)
                if not changed:
                    continue
                merge_counts(redaction_counts, combined_counts)
                evidence_updates.append((json.dumps(payload, ensure_ascii=False, sort_keys=True), item_id))
            totals["evidence_updated"] = len(evidence_updates)

            answer_updates: list[tuple[str, str]] = []
            for item_id, payload in load_records(cursor, "research_answers"):
                source_document_ids = {str(value) for value in payload.get("source_document_ids", []) if str(value)}
                if not source_document_ids.intersection(local_research_document_ids):
                    continue
                totals["research_answers_scanned"] += 1
                changed = False
                combined_counts: dict[str, int] = {}
                for field_name in ("english_source_text", "chinese_summary"):
                    text = str(payload.get(field_name, ""))
                    redacted, counts = redact_text(text)
                    if redacted != text:
                        payload[field_name] = redacted
                        changed = True
                        merge_counts(combined_counts, counts)
                if not changed:
                    continue
                merge_counts(redaction_counts, combined_counts)
                answer_updates.append((json.dumps(payload, ensure_ascii=False, sort_keys=True), item_id))
            totals["research_answers_updated"] = len(answer_updates)

            if not dry_run:
                audit_event_id = new_id("evt")
                for payload_json, item_id in document_updates:
                    cursor.execute(
                        "UPDATE ai_quant.records SET payload = %s::jsonb, updated_at = now() WHERE collection = 'documents' AND item_id = %s",
                        (payload_json, item_id),
                    )
                for payload_json, item_id in evidence_updates:
                    cursor.execute(
                        "UPDATE ai_quant.records SET payload = %s::jsonb, updated_at = now() WHERE collection = 'evidence' AND item_id = %s",
                        (payload_json, item_id),
                    )
                for payload_json, item_id in answer_updates:
                    cursor.execute(
                        "UPDATE ai_quant.records SET payload = %s::jsonb, updated_at = now() WHERE collection = 'research_answers' AND item_id = %s",
                        (payload_json, item_id),
                    )
                cursor.execute(
                    """
                    INSERT INTO ai_quant.audit_log (
                        event_id, actor, action, resource_type, resource_id, source,
                        version, model_version, prompt_version, approval_state,
                        trace_id, payload, timestamp
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                    """,
                    (
                        audit_event_id,
                        "local_research_sensitive_redaction",
                        "redact_local_research_sensitive_contacts",
                        "research_reports",
                        "local_research_reference_pool",
                        "local_research_unknown",
                        "local-sensitive-redaction-v1",
                        "",
                        "",
                        "completed",
                        "",
                        json.dumps(
                            {
                                "event_id": audit_event_id,
                                "actor": "local_research_sensitive_redaction",
                                "action": "redact_local_research_sensitive_contacts",
                                "resource_type": "research_reports",
                                "resource_id": "local_research_reference_pool",
                                "source": "local_research_unknown",
                                "version": "local-sensitive-redaction-v1",
                                "model_version": "",
                                "prompt_version": "",
                                "approval_state": "completed",
                                "trace_id": "",
                                "timestamp": audit_timestamp.isoformat(),
                            },
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                        audit_timestamp,
                    ),
                )
                connection.commit()

    result = {
        "status": "passed",
        "started_at": started_at,
        "completed_at": utc_iso(),
        "dry_run": dry_run,
        "totals": totals,
        "redaction_counts": redaction_counts,
        "source_scope": "local_research_reference_text_only",
        "raw_files_modified": False,
        "audit_event_id": audit_event_id,
        "usage_boundary": "redacts cached local research citation text for data-security audit; original local files remain unchanged",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Redact sensitive contact values from cached local research report citation text.")
    parser.add_argument("--dsn", default=DEFAULT_DSN)
    parser.add_argument("--output", type=Path, default=Path("artifacts/local-research-sensitive-redaction.json"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run_redaction(dsn=args.dsn, output=args.output, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
