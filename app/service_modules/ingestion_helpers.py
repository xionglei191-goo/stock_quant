"""Pure ingestion / source-governance helpers.

Extracted from ``SystemService`` per the SystemService Modularization ADR
(ingestion domain). Every function is a deterministic transform of its
arguments only: none touch the store, audit log, permissions, or any
``SystemService`` state. ``SystemService`` keeps the same method names as thin
facades delegating here.

Deliberately left in ``SystemService``:
- ``_canonical_source_id`` (depends on the module-level ``SOURCE_ID_ALIASES``
  constant; delegating would create an import cycle).
- ``_mark_schedule_retry`` (mutates the passed-in schedule object in place).
"""

from __future__ import annotations

import re
from datetime import timedelta
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from ..models import Document, SourceDefinition, SourceReviewRecord
from ..research_reports import safe_source_part
from ..utils import new_id, utcnow


def source_governance_gaps(source: SourceDefinition) -> list[str]:
    gaps: list[str] = []
    if not source.retention_policy:
        gaps.append("missing_retention_policy")
    if source.cache_ttl_days < 0:
        gaps.append("invalid_cache_ttl_days")
    if source.source_type in {"public_market_data", "public_web", "local_reference", "third_party_connector"} and not (source.provenance_ref or source.source_tos_uri):
        gaps.append("missing_provenance_ref")
    if source.source_type in {"public_web", "third_party_connector"} and not source.robots_policy:
        gaps.append("missing_robots_policy")
    if not source.usage_scope:
        gaps.append("missing_usage_scope")
    if not source.collection_method:
        gaps.append("missing_collection_method")
    if source.field_mapping and not source.field_whitelist:
        gaps.append("missing_field_whitelist")
    if source.risk_level not in {"green", "yellow", "red"}:
        gaps.append("invalid_risk_level")
    if source.rights_tag.training_allowed and source.risk_level != "green":
        gaps.append("training_allowed_on_non_green_source")
    return gaps


def default_source_review_owner_role(source: SourceDefinition) -> str:
    if source.source_type in {"regulatory", "exchange", "public_market_data", "public_web", "third_party_connector"}:
        return "数据工程"
    if source.source_type in {"company_ir", "local_reference", "manual_reference"}:
        return "风险/合规"
    return "平台负责人"


def next_source_review_due_at(reviewed_at: Any, cadence: str) -> Any:
    cadence = str(cadence or "quarterly").strip().lower()
    days_by_cadence = {
        "monthly": 30,
        "quarterly": 90,
        "semiannual": 182,
        "semi-annually": 182,
        "annual": 365,
        "yearly": 365,
    }
    days = days_by_cadence.get(cadence, 90)
    return reviewed_at + timedelta(days=days)


def source_initial_review_due_at(source: SourceDefinition, as_of: Any) -> Any:
    if source.last_reviewed_at:
        return next_source_review_due_at(source.last_reviewed_at, source.review_cadence)
    return as_of


def source_review_overdue(review: SourceReviewRecord | None) -> bool:
    return bool(review and review.next_review_due_at and review.next_review_due_at < utcnow())


def research_report_source_id(broker: str) -> str:
    return f"local_research_{safe_source_part(broker)}"


def sec_document_id(filing: Any) -> str:
    metadata = filing.metadata or {}
    accession_no = str(metadata.get("accession_no", "")).replace("-", "")
    primary_doc = str(metadata.get("primary_doc", "index")).rsplit("/", maxsplit=1)[-1]
    raw = f"sec_{accession_no}_{primary_doc}"
    return "doc_" + re.sub(r"[^A-Za-z0-9_-]+", "_", raw).strip("_").lower()


def ashare_document_id(filing: Any) -> str:
    basename = str(filing.source_uri or filing.title or new_id("ashare")).rsplit("/", maxsplit=1)[-1]
    raw = f"ashare_{basename}"
    return "doc_" + re.sub(r"[^A-Za-z0-9_-]+", "_", raw).strip("_").lower()


def hkex_document_id(filing: Any) -> str:
    basename = str(filing.source_uri or filing.title or new_id("hkex")).rsplit("/", maxsplit=1)[-1]
    raw = f"hkex_{basename}"
    return "doc_" + re.sub(r"[^A-Za-z0-9_-]+", "_", raw).strip("_").lower()


def source_publicness(documents: list[Document]) -> str:
    licenses = {document.rights_tag.license_class.lower() for document in documents}
    if licenses and all(item == "public" or item.startswith("public_") for item in licenses):
        return "public"
    if any("private" in item or "restricted" in item for item in licenses):
        return "restricted"
    return ",".join(sorted(licenses)) or "unknown"


def sanitize_source_uri(source_uri: str) -> str:
    value = str(source_uri or "").strip()
    if not value:
        return ""
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.netloc:
        return value
    sensitive_keys = {"access_token", "api_key", "apikey", "auth", "key", "password", "secret", "signature", "token"}
    query = []
    for key, item_value in parse_qsl(parsed.query, keep_blank_values=True):
        query.append((key, "REDACTED" if key.lower() in sensitive_keys else item_value))
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, urlencode(query, doseq=True), ""))


def next_schedule_run(cadence: str) -> Any:
    now = utcnow()
    seconds = {
        "manual": 0,
        "hourly": 3600,
        "daily": 86400,
        "weekly": 604800,
    }.get(cadence, 0)
    if seconds <= 0:
        return now
    return now + timedelta(seconds=seconds)
