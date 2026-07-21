from __future__ import annotations

from datetime import date
import hashlib
from pathlib import Path
import re
from typing import Any, Mapping, Protocol


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
