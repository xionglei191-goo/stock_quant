from __future__ import annotations

from datetime import date
import hashlib
from pathlib import Path
import re
from typing import Any, Mapping, Protocol

from ..research_reports import iter_report_files


class ResearchReportLike(Protocol):
    report_id: str
    document_id: str
    broker: str
    source_id: str
    title: str
    file_name: str
    year: int
    month: int
    status: str
    issuer_id: str
    security_id: str
    industry: str
    event_ids: list[str]


class DocumentLike(Protocol):
    issuer_id: str
    security_id: str
    body: str


class DisclosureEventLike(Protocol):
    event_id: str
    issuer_id: str
    security_id: str
    document_id: str


def verify_report_content_sha256(file_path: str, expected_sha256: str) -> str:
    """Verify an operator-supplied content identity against the local report."""

    expected = str(expected_sha256 or "").strip().lower()
    if not expected:
        return ""
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ValueError("content_sha256 must be a lowercase SHA-256 digest")
    path = Path(file_path)
    if not path.is_file():
        raise ValueError("research report file is unavailable for content identity verification")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    actual = digest.hexdigest()
    if actual != expected:
        raise ValueError("content_sha256 does not match the registered research report file")
    return actual


def select_research_report_files(
    root: Path,
    *,
    extensions: set[str],
    limit: int,
    relative_paths: list[str] | None = None,
) -> list[Path]:
    """Select report files without allowing a batch request to widen its scope."""

    resolved_root = root.expanduser().resolve()
    if relative_paths is None:
        return iter_report_files(resolved_root, extensions=extensions, limit=limit)
    if not relative_paths:
        raise ValueError("relative_paths must contain at least one file")
    if len(relative_paths) > limit:
        raise ValueError("relative_paths exceeds the scan limit")

    selected: list[Path] = []
    seen: set[str] = set()
    for value in relative_paths:
        raw = str(value)
        relative = Path(raw)
        normalized = relative.as_posix()
        if (
            not raw
            or raw != normalized
            or relative.is_absolute()
            or any(part in {"", ".", ".."} for part in relative.parts)
        ):
            raise ValueError("relative_paths must contain normalized relative paths")
        if normalized in seen:
            raise ValueError("relative_paths must be unique")
        seen.add(normalized)
        candidate = resolved_root / relative
        try:
            resolved = candidate.resolve(strict=True)
        except OSError as exc:
            raise ValueError("relative_paths contains an unavailable file") from exc
        if resolved != candidate.absolute() or resolved_root not in resolved.parents:
            raise ValueError("relative_paths cannot traverse symlinks or escape root_path")
        if not resolved.is_file() or resolved.suffix.lower() not in extensions:
            raise ValueError("relative_paths contains a non-report file")
        selected.append(resolved)
    return selected


def research_report_batch_state(store: Any, report_ids: list[str]) -> dict[str, Any]:
    """Return an opaque, read-only execution snapshot for an exact report batch."""

    if not report_ids or len(report_ids) > 1000 or len(set(report_ids)) != len(report_ids):
        raise ValueError("report_ids must contain 1-1000 unique IDs")
    rows: list[dict[str, Any]] = []
    missing: list[str] = []
    reports: dict[str, Any] = {}
    document_ids: set[str] = set()
    for report_id in report_ids:
        report = store.research_reports.get(report_id)
        if report is None:
            missing.append(report_id)
            continue
        reports[report_id] = report
        if report.document_id:
            document_ids.add(report.document_id)
    evidence_counts = {document_id: 0 for document_id in document_ids}
    for item in store.evidence.values():
        if item.document_id in evidence_counts and item.section == "research_report_citation":
            evidence_counts[item.document_id] += 1
    manual_review_documents = {
        item.document_id
        for item in store.manual_reviews.values()
        if item.document_id in document_ids and item.status in {"open", "in_review"}
    }
    for report_id in report_ids:
        report = reports.get(report_id)
        if report is None:
            continue
        document = store.documents.get(report.document_id) if report.document_id else None
        rows.append(
            {
                "report_id": report.report_id,
                "document_id": report.document_id,
                "content_sha256": report.content_sha256,
                "document_content_sha256": document.content_sha256 if document else "",
                "status": report.status,
                "evidence_count": evidence_counts.get(report.document_id, 0),
                "manual_review": report.document_id in manual_review_documents,
            }
        )
    return {"report_ids": report_ids, "missing_report_ids": missing, "reports": rows}


def research_report_month_date(report: ResearchReportLike) -> date | None:
    try:
        year = int(report.year)
        month = int(report.month or 1)
        if not 1 <= month <= 12:
            return None
        return date(year, month, 1)
    except (TypeError, ValueError):
        return None


def research_report_mapping_row(
    report: ResearchReportLike,
    *,
    document: DocumentLike | None,
    disclosure_events: list[DisclosureEventLike],
    include_candidate_events: bool,
) -> dict[str, Any]:
    issuer_id = report.issuer_id or (document.issuer_id if document else "")
    security_id = report.security_id or (document.security_id if document else "")
    candidate_event_ids: list[str] = []
    if include_candidate_events and (issuer_id or security_id):
        for event in disclosure_events:
            if issuer_id and event.issuer_id != issuer_id:
                continue
            if security_id and event.security_id and event.security_id != security_id:
                continue
            if report.document_id and event.document_id == report.document_id:
                continue
            candidate_event_ids.append(event.event_id)
    event_ids = list(dict.fromkeys(str(item) for item in report.event_ids if str(item).strip()))
    candidate_event_ids = list(dict.fromkeys(candidate_event_ids))
    linked_event_count = len(event_ids) + len([item for item in candidate_event_ids if item not in event_ids])
    issues: list[str] = []
    if not issuer_id:
        issues.append("missing_issuer_mapping")
    if not security_id:
        issues.append("missing_security_mapping")
    if not report.industry:
        issues.append("missing_industry_mapping")
    if not event_ids and not candidate_event_ids:
        issues.append("missing_event_mapping")
    return {
        "report_id": report.report_id,
        "document_id": report.document_id,
        "broker": report.broker,
        "source_id": report.source_id,
        "title": report.title,
        "file_name": report.file_name,
        "year": report.year,
        "month": report.month,
        "status": report.status,
        "issuer_id": issuer_id,
        "security_id": security_id,
        "industry": report.industry,
        "event_ids": event_ids,
        "candidate_event_ids": candidate_event_ids,
        "linked_event_count": linked_event_count,
        "mapped": bool(issuer_id or security_id or report.industry or linked_event_count),
        "issues": issues,
        "source_boundary": "local_reference_research_report",
        "usage_boundary": "local_reference_only_not_training_or_fact_source",
    }


def research_report_viewpoint_row(
    report: ResearchReportLike,
    *,
    document: DocumentLike | None,
    report_text: str,
) -> dict[str, Any]:
    text = f"{report.title} {report.file_name} {document.body if document else ''} {report_text}"
    normalized = text.lower()
    topic_terms = [
        topic
        for topic, keywords in {
            "revenue": ["revenue", "sales", "收入", "营收"],
            "margin": ["margin", "gross margin", "毛利", "利润率"],
            "guidance": ["guidance", "outlook", "指引", "展望"],
            "risk": ["risk", "headwind", "风险", "压力"],
            "valuation": ["valuation", "target price", "估值", "目标价"],
            "capital_return": ["buyback", "dividend", "回购", "分红"],
            "management": ["management", "ceo", "cfo", "管理层"],
        }.items()
        if any(keyword in normalized for keyword in keywords)
    ]
    positive_hits = sum(1 for token in ("positive", "upgrade", "beat", "bullish", "strong", "上调", "利好", "强劲") if token in normalized)
    negative_hits = sum(1 for token in ("negative", "downgrade", "miss", "bearish", "weak", "下调", "利空", "疲弱") if token in normalized)
    sentiment = "positive" if positive_hits > negative_hits else "negative" if negative_hits > positive_hits else "mixed"
    return {
        "report_id": report.report_id,
        "document_id": report.document_id,
        "broker": report.broker,
        "source_id": report.source_id,
        "title": report.title,
        "file_name": report.file_name,
        "year": report.year,
        "month": report.month,
        "issuer_id": report.issuer_id or (document.issuer_id if document else ""),
        "security_id": report.security_id or (document.security_id if document else ""),
        "industry": report.industry,
        "topic_terms": topic_terms,
        "sentiment": sentiment,
        "sentiment_hits": {"positive": positive_hits, "negative": negative_hits},
        "usage_boundary": "local_reference_only_not_training_or_fact_source",
    }
