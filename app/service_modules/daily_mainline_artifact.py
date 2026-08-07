"""Daily mainline run artifact payload construction, redaction and file naming.

Pure functions only (design §4.10). The module builds the ``local-only`` evidence
payload for one daily mainline orchestration run, strips credentials / signed URLs /
raw upstream responses, and derives the artifact file name. Writing bytes to disk
stays in the ``SystemService`` facade so this module keeps no IO and no state.

Boundary: the artifact is always ``local-only`` local evidence and is never eligible
for a non-local production release gate, regardless of caller input.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from ..utils import parse_datetime


ARTIFACT_SCHEMA_ID = "daily-mainline-run-artifact-v1"
ARTIFACT_OWNER_GROUP = "product_and_ui"
ARTIFACT_CLASSIFICATION = "local-only"
ARTIFACT_DIR = "artifacts/daily-mainline"
ARTIFACT_FILENAME_PREFIX = "daily-mainline"

SENSITIVE_KEY_PATTERNS = (
    "api_key",
    "authorization",
    "token",
    "secret",
    "signature",
    "x-amz-",
    "raw_response",
)
REDACTED_MARKER = "[redacted]"

MAX_TEXT_LENGTH = 2000
MAX_SUMMARY_LENGTH = 600
TRUNCATION_SUFFIX = "...[truncated]"

ITEM_FIELDS = (
    "item_id",
    "run_id",
    "security_id",
    "issuer_id",
    "ticker",
    "market",
    "rank",
    "selection_reason",
    "trigger_metric",
    "trigger_value",
    "as_of_date",
    "completeness_status",
    "missing_layers",
    "partition",
    "evidence_ids",
    "research_answer_id",
    "llm_task_run_id",
    "template_id",
    "review_status",
    "diligence_status",
    "diligence_reason_code",
)
VIEWPOINT_SUMMARY_FIELDS = (
    "source_layer",
    "fact_field_writes",
    "template_id",
    "prompt_version",
    "model",
    "llm_task_run_id",
    "evidence_ids",
    "diligence_status",
    "diligence_reason_code",
)
VIEWPOINT_TEXT_FIELDS = ("summary", "summary_text", "text", "viewpoint_text", "output_text")

_FILENAME_SAFE_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")


def utc_iso(moment: datetime | None = None) -> str:
    """Return a UTC ISO 8601 timestamp (offset form, parseable by ``fromisoformat``)."""

    if moment is None:
        moment = datetime.now(timezone.utc)
    elif moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).isoformat()


def is_sensitive_key(key: Any) -> bool:
    """Case-insensitive substring match of a mapping key against sensitive patterns."""

    normalized = str(key).lower()
    return any(pattern in normalized for pattern in SENSITIVE_KEY_PATTERNS)


def truncate_text(value: Any, *, max_length: int = MAX_TEXT_LENGTH) -> str:
    text = str(value or "")
    if max_length <= 0 or len(text) <= max_length:
        return text
    keep = max(0, max_length - len(TRUNCATION_SUFFIX))
    return f"{text[:keep]}{TRUNCATION_SUFFIX}"


def redact(payload: Any, *, max_text_length: int = MAX_TEXT_LENGTH) -> Any:
    """Recursively drop sensitive keys and truncate over-long text.

    Mapping keys whose lower-cased form contains any ``SENSITIVE_KEY_PATTERNS``
    substring are removed entirely (not masked in place) so no credential value,
    signed URL or raw upstream response body reaches the artifact file.
    """

    if isinstance(payload, Mapping):
        cleaned: dict[str, Any] = {}
        for key, value in payload.items():
            if is_sensitive_key(key):
                continue
            cleaned[str(key)] = redact(value, max_text_length=max_text_length)
        return cleaned
    if isinstance(payload, str):
        return truncate_text(payload, max_length=max_text_length)
    if isinstance(payload, (bytes, bytearray)):
        return REDACTED_MARKER
    if isinstance(payload, datetime):
        return utc_iso(payload)
    if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, bytearray)):
        return [redact(item, max_text_length=max_text_length) for item in payload]
    if isinstance(payload, (set, frozenset)):
        return [redact(item, max_text_length=max_text_length) for item in sorted(payload, key=str)]
    return payload


def viewpoint_summary(viewpoint: Mapping[str, Any] | None) -> dict[str, Any]:
    """Keep the viewpoint summary text plus lineage fields; drop upstream payloads."""

    if not isinstance(viewpoint, Mapping):
        return {}
    summary_text = ""
    for field in VIEWPOINT_TEXT_FIELDS:
        candidate = viewpoint.get(field)
        if isinstance(candidate, str) and candidate.strip():
            summary_text = candidate.strip()
            break
    summary: dict[str, Any] = {"summary": truncate_text(summary_text, max_length=MAX_SUMMARY_LENGTH)}
    for field in VIEWPOINT_SUMMARY_FIELDS:
        if field in viewpoint and not is_sensitive_key(field):
            summary[field] = redact(viewpoint.get(field), max_text_length=MAX_SUMMARY_LENGTH)
    return summary


def stage_summary(stage: Mapping[str, Any] | None) -> dict[str, Any]:
    """Normalize one stage record to the artifact stage contract."""

    source = stage if isinstance(stage, Mapping) else {}
    summary = {
        "stage": str(source.get("stage") or ""),
        "status": str(source.get("status") or ""),
        "started_at": str(source.get("started_at") or ""),
        "finished_at": str(source.get("finished_at") or ""),
        "record_count": _as_int(source.get("record_count")),
        "reason_code": str(source.get("reason_code") or ""),
    }
    return summary


def item_summary(item: Mapping[str, Any] | None) -> dict[str, Any]:
    """Project one queue item to artifact fields, viewpoint reduced to its summary."""

    source = item if isinstance(item, Mapping) else {}
    summary: dict[str, Any] = {}
    for field in ITEM_FIELDS:
        if field in source:
            summary[field] = redact(source.get(field), max_text_length=MAX_SUMMARY_LENGTH)
    summary["viewpoint"] = viewpoint_summary(source.get("viewpoint"))
    return summary


def artifact_payload(
    *,
    run: Mapping[str, Any],
    items: Sequence[Mapping[str, Any]],
    producer_command: str,
    environment: str,
    generated_at: datetime | str | None = None,
) -> dict[str, Any]:
    """Build the ``daily-mainline-run-artifact-v1`` payload for one run.

    ``classification`` and ``production_release_gate_eligible`` are module constants:
    callers cannot promote a local run artifact into non-local release evidence
    (requirement 6.3). ``paper_only`` / ``live_execution_allowed`` carry the project
    boundary declaration in the same way.
    """

    source = run if isinstance(run, Mapping) else {}
    stages = [stage_summary(stage) for stage in _as_sequence(source.get("stages"))]
    queue_items = [item_summary(item) for item in _as_sequence(items)]
    payload = {
        "schema_id": ARTIFACT_SCHEMA_ID,
        "run_id": str(source.get("run_id") or ""),
        "run_date": str(source.get("run_date") or ""),
        "status": str(source.get("status") or ""),
        "generated_at": _resolve_generated_at(generated_at),
        "producer_command": truncate_text(producer_command, max_length=MAX_SUMMARY_LENGTH),
        "environment": truncate_text(environment, max_length=MAX_SUMMARY_LENGTH),
        "owner_group": ARTIFACT_OWNER_GROUP,
        "classification": ARTIFACT_CLASSIFICATION,
        "contains_sensitive_data": False,
        "production_release_gate_eligible": False,
        "acceptable_for_non_local_release": False,
        "counts": {
            "candidate_count": _as_int(source.get("candidate_count")),
            "queue_count": _as_int(source.get("queue_count")),
            "unsupported_count": _as_int(source.get("unsupported_count")),
            "item_count": len(queue_items),
            "stage_count": len(stages),
        },
        "failure_reason_codes": [str(code) for code in _as_sequence(source.get("failure_reason_codes"))],
        "next_actions": redact(list(_as_sequence(source.get("next_actions"))), max_text_length=MAX_SUMMARY_LENGTH),
        "stages": stages,
        "items": queue_items,
        "paper_only": True,
        "live_execution_allowed": False,
    }
    return payload


def artifact_filename(*, run_date: Any, run_id: Any) -> str:
    """``daily-mainline-{run_date}-{run_id}.json`` (run_id keeps same-day runs apart)."""

    date_token = _filename_token(run_date, fallback="unknown-date")
    run_token = _filename_token(run_id, fallback="unknown-run")
    return f"{ARTIFACT_FILENAME_PREFIX}-{date_token}-{run_token}.json"


def artifact_path(*, run_date: Any, run_id: Any, artifact_dir: str = ARTIFACT_DIR) -> str:
    """POSIX-style relative artifact path under the configured artifact directory."""

    directory = str(artifact_dir or ARTIFACT_DIR).replace("\\", "/").rstrip("/")
    filename = artifact_filename(run_date=run_date, run_id=run_id)
    return f"{directory}/{filename}" if directory else filename


def _resolve_generated_at(value: datetime | str | None) -> str:
    """Always emit UTC ISO 8601; unparseable caller input falls back to now."""

    if isinstance(value, datetime):
        return utc_iso(value)
    if isinstance(value, str) and value.strip():
        try:
            return utc_iso(parse_datetime(value.strip()))
        except (TypeError, ValueError):
            return utc_iso()
    return utc_iso()


def _as_sequence(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        return [value]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)
    return [value]


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _filename_token(value: Any, *, fallback: str) -> str:
    text = str(value or "").strip()
    token = "".join(char if char in _FILENAME_SAFE_CHARS else "_" for char in text).strip("_")
    return token or fallback
