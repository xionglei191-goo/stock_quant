from __future__ import annotations

import re
from typing import Any, Callable, Mapping


SourceTypeResolver = Callable[[str], str]


def normalized_key(value: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "_", str(value).strip().lower()).strip("_")


def entity_key(value: str) -> str:
    normalized = normalized_key(value)
    for suffix in ["_inc", "_corp", "_co", "_ltd", "_limited", "_company", "_集团", "_股份有限公司", "_有限公司"]:
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)].strip("_")
    return normalized or "unknown"


def _unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(str(item) for item in items if str(item).strip()))


def source_quality_type(source_id: str) -> str:
    value = str(source_id).strip().lower()
    if "research" in value or "broker" in value:
        return "broker_research"
    if "manual" in value:
        return "manual_reference"
    if "local" in value:
        return "local_reference"
    if "ir" in value:
        return "company_ir"
    if "sec" in value or "regulatory" in value or "exchange" in value:
        return "regulatory"
    if "official" in value:
        return "official_public"
    return "unknown"


def source_quality(record: Any, *, record_type: str, source_type_resolver: SourceTypeResolver) -> dict[str, Any]:
    score = 0.2
    factors: list[str] = ["base_local_record"]
    confidence = float(getattr(record, "confidence", 0.0) or 0.0)
    score += min(0.2, max(0.0, confidence) * 0.2)
    if getattr(record, "evidence_ids", []):
        score += 0.2
        factors.append("has_evidence_backlink")
    if getattr(record, "document_ids", []):
        score += 0.1
        factors.append("has_document_backlink")
    source_types = [source_type_resolver(source_id) for source_id in getattr(record, "source_ids", [])]
    if any(source_type in {"regulatory", "company_ir", "company_official", "official_public", "exchange_disclosure", "issuer_disclosure", "public_company_disclosure"} for source_type in source_types):
        score += 0.25
        factors.append("official_or_public_company_source")
    if any(source_type in {"broker_research", "research", "local_research_reports"} for source_type in source_types):
        score -= 0.1
        factors.append("research_opinion_source")
    if any(source_type in {"local_reference", "manual_reference", "news", "curated_public_profile"} for source_type in source_types):
        score -= 0.15
        factors.append("manual_or_reference_source")
    fact_status = str(getattr(record, "fact_status", "")).strip()
    if fact_status == "verified":
        score += 0.15
        factors.append("verified_fact_status")
    elif fact_status == "opinion_signal":
        score -= 0.1
        factors.append("opinion_signal_not_fact")
    review_status = str(getattr(record, "review_status", "")).strip()
    if review_status == "approved":
        score += 0.2
        factors.append("approved_review")
    elif review_status == "auto_generated":
        score += 0.05
        factors.append("auto_generated")
    elif review_status in {"rejected", "merged"}:
        score -= 0.25
        factors.append(f"{review_status}_record")
    score = round(max(0.0, min(1.0, score)), 4)
    level = "high" if score >= 0.75 else ("medium" if score >= 0.5 else "low")
    explanation = quality_explanation(score=score, level=level, factors=factors, source_types=source_types)
    return {
        "record_type": record_type,
        "score": score,
        "level": level,
        "factors": _unique(factors),
        "source_types": _unique(source_types),
        "explanation": explanation,
        "next_action": quality_next_action(level),
        "usage_boundary": "source_quality_is_local_provenance_score_not_investment_rating",
    }


def source_quality_type(source_id: str) -> str:
    value = str(source_id).strip().lower()
    if "research" in value or "broker" in value:
        return "broker_research"
    if "manual" in value:
        return "manual_reference"
    if "local" in value:
        return "local_reference"
    if "ir" in value:
        return "company_ir"
    if "sec" in value or "regulatory" in value or "exchange" in value:
        return "regulatory"
    if "official" in value:
        return "official_public"
    return "unknown"


def record_source_quality(record: Any, *, record_type: str, source_type_lookup: SourceTypeResolver) -> dict[str, Any]:
    return source_quality(record, record_type=record_type, source_type_resolver=source_type_lookup)


def quality_explanation(*, score: float, level: str, factors: list[str], source_types: list[str]) -> str:
    source_text = ", ".join(_unique(source_types)) or "来源待补"
    factor_text = ", ".join(_unique(factors[:4])) or "基础本地记录"
    return f"{level} provenance score {round(score, 4)} from {source_text}; factors: {factor_text}"


def quality_next_action(level: str) -> str:
    if level == "high":
        return "保留为可信候选，人工复核后可进入事实层"
    if level == "medium":
        return "补充证据或人工复核后再提升"
    return "不要自动提升，先补官方来源或拒绝"


def event_is_review_candidate(event: Any) -> bool:
    classification_status = str((getattr(event, "metadata", {}) or {}).get("classification_status", ""))
    candidate_status = str((getattr(event, "metadata", {}) or {}).get("candidate_status", ""))
    return getattr(event, "review_status", "") == "needs_review" or classification_status.endswith("needs_review") or candidate_status == "candidate"


def event_review_score(event: Any, *, source_quality_row: Mapping[str, Any] | None = None, source_type_lookup: SourceTypeResolver | None = None, source_quality: Mapping[str, Any] | None = None) -> float:
    if source_quality_row is None:
        source_quality_row = source_quality
    if source_quality_row is None:
        source_quality_row = record_source_quality(event, record_type="company_event", source_type_lookup=source_type_lookup or source_quality_type)
    score = 0.2
    score += min(0.25, max(0.0, float(getattr(event, "confidence", 0.0) or 0.0)) * 0.25)
    score += min(0.35, max(0.0, float(source_quality_row.get("score", 0.0) or 0.0)) * 0.35)
    backlink_count = len(getattr(event, "evidence_ids", [])) + len(getattr(event, "document_ids", [])) + len(getattr(event, "source_ids", []))
    score += min(0.15, backlink_count * 0.04)
    source_layer = str((getattr(event, "metadata", {}) or {}).get("source_layer", ""))
    if source_layer in {"official_disclosure_text_classification", "disclosure_event", "company_ir"}:
        score += 0.08
    if getattr(event, "fact_status", "") == "opinion_signal":
        score -= 0.08
    if getattr(event, "review_status", "") == "approved":
        score += 0.08
    if getattr(event, "review_status", "") == "rejected":
        score -= 0.15
    return min(1.0, max(0.0, score))


def event_review_recommendation(event: Any, source_quality_row: Mapping[str, Any] | None = None, *, source_type_lookup: SourceTypeResolver | None = None) -> dict[str, Any]:
    source_quality_row = source_quality_row or record_source_quality(event, record_type="company_event", source_type_lookup=source_type_lookup or source_quality_type)
    score = event_review_score(event, source_quality_row=source_quality_row)
    return review_recommendation(event, record_kind="event", is_candidate=event_is_review_candidate(event), source_quality_row=source_quality_row, score=score)


def relationship_is_review_candidate(relationship: Any) -> bool:
    relationship_type = str(getattr(relationship, "relationship_type", "") or "")
    candidate_status = str((getattr(relationship, "metadata", {}) or {}).get("candidate_status", ""))
    return relationship_type.endswith("_candidate") or getattr(relationship, "review_status", "") == "needs_review" or candidate_status == "candidate"


def relationship_review_score(relationship: Any, *, source_quality_row: Mapping[str, Any] | None = None, source_type_lookup: SourceTypeResolver | None = None, source_quality: Mapping[str, Any] | None = None) -> float:
    if source_quality_row is None:
        source_quality_row = source_quality
    if source_quality_row is None:
        source_quality_row = record_source_quality(relationship, record_type="company_relationship", source_type_lookup=source_type_lookup or source_quality_type)
    score = 0.2
    score += min(0.25, max(0.0, float(getattr(relationship, "confidence", 0.0) or 0.0)) * 0.25)
    score += min(0.35, max(0.0, float(source_quality_row.get("score", 0.0) or 0.0)) * 0.35)
    backlink_count = len(getattr(relationship, "evidence_ids", [])) + len(getattr(relationship, "document_ids", [])) + len(getattr(relationship, "source_ids", []))
    score += min(0.15, backlink_count * 0.04)
    source_layer = str((getattr(relationship, "metadata", {}) or {}).get("source_layer", ""))
    relationship_type = str(getattr(relationship, "relationship_type", ""))
    if source_layer in {"official_disclosure_candidate", "public_company_disclosure_candidate"}:
        score += 0.08
    if "research" in source_layer or relationship_type.startswith("institution_coverage"):
        score -= 0.08
    if getattr(relationship, "review_status", "") == "approved":
        score += 0.08
    if getattr(relationship, "review_status", "") == "rejected" or getattr(relationship, "relationship_status", "") == "inactive":
        score -= 0.15
    return min(1.0, max(0.0, score))


def relationship_review_recommendation(relationship: Any, source_quality_row: Mapping[str, Any] | None = None, *, source_type_lookup: SourceTypeResolver | None = None) -> dict[str, Any]:
    source_quality_row = source_quality_row or record_source_quality(relationship, record_type="company_relationship", source_type_lookup=source_type_lookup or source_quality_type)
    score = relationship_review_score(relationship, source_quality_row=source_quality_row)
    return review_recommendation(relationship, record_kind="graph", is_candidate=relationship_is_review_candidate(relationship), source_quality_row=source_quality_row, score=score)


def review_recommendation(
    record: Any,
    *,
    record_kind: str,
    is_candidate: bool,
    source_quality_row: Mapping[str, Any],
    score: float,
) -> dict[str, Any]:
    evidence_count = len(getattr(record, "evidence_ids", []))
    document_count = len(getattr(record, "document_ids", []))
    source_count = len(getattr(record, "source_ids", []))
    if not is_candidate:
        action = "already_reviewed_or_not_candidate"
        reason = f"{record_kind}_is_not_pending_review_candidate"
        next_action = "无需前台处理，必要时查看高级追溯"
    elif score >= (0.74 if record_kind == "event" else 0.72):
        action = "prefer_approve_after_review"
        reason = f"candidate_{record_kind}_has_strong_source_quality_or_evidence_backlinks"
        next_action = "核对证据后批准进入可信层"
    elif score <= 0.38:
        action = "prefer_reject_or_request_evidence"
        reason = f"candidate_{record_kind}_has_weak_source_quality_or_missing_backlinks"
        next_action = "补充官方证据，否则拒绝或合并"
    else:
        action = "manual_review_required"
        reason = f"candidate_{record_kind}_score_is_mixed"
        next_action = "人工比较来源、实体和时间线后决定"
    explanation = f"{reason}; source quality {round(float(source_quality_row.get('score', 0.0) or 0.0), 4)}; evidence {evidence_count}, documents {document_count}, sources {source_count}"
    return {
        "recommended_action": action,
        "candidate_score": round(score, 4),
        "source_quality_score": round(float(source_quality_row.get("score", 0.0) or 0.0), 4),
        "evidence_count": evidence_count,
        "document_count": document_count,
        "source_count": source_count,
        "evidence_summary": f"证据 {evidence_count} · 文档 {document_count} · 来源 {source_count}",
        "reason": reason,
        "explanation": explanation,
        "next_action": next_action,
        "boundary": f"recommendation_is_for_human_{record_kind}_review_not_investment_advice",
    }


def record_source_quality(record: Any, *, record_type: str, source_type_lookup: SourceTypeResolver | None = None) -> dict[str, Any]:
    return source_quality(record, record_type=record_type, source_type_resolver=source_type_lookup or source_quality_type)


def event_is_review_candidate(event: Any) -> bool:
    classification_status = str((getattr(event, "metadata", {}) or {}).get("classification_status", ""))
    candidate_status = str((getattr(event, "metadata", {}) or {}).get("candidate_status", ""))
    return getattr(event, "review_status", "") == "needs_review" or classification_status.endswith("needs_review") or candidate_status == "candidate"


def event_review_recommendation(event: Any, source_quality_row: Mapping[str, Any] | None = None, *, source_type_lookup: SourceTypeResolver | None = None) -> dict[str, Any]:
    source_quality_row = source_quality_row or record_source_quality(event, record_type="company_event", source_type_lookup=source_type_lookup)
    score = event_review_score(event, source_quality_row=source_quality_row)
    return review_recommendation(record=event, record_kind="event", is_candidate=event_is_review_candidate(event), source_quality_row=source_quality_row, score=score)


def relationship_is_review_candidate(relationship: Any) -> bool:
    relationship_type = str(getattr(relationship, "relationship_type", "") or "")
    candidate_status = str((getattr(relationship, "metadata", {}) or {}).get("candidate_status", ""))
    return relationship_type.endswith("_candidate") or getattr(relationship, "review_status", "") == "needs_review" or candidate_status == "candidate"


def relationship_review_recommendation(relationship: Any, source_quality_row: Mapping[str, Any] | None = None, *, source_type_lookup: SourceTypeResolver | None = None) -> dict[str, Any]:
    source_quality_row = source_quality_row or record_source_quality(relationship, record_type="company_relationship", source_type_lookup=source_type_lookup)
    score = relationship_review_score(relationship, source_quality_row=source_quality_row)
    return review_recommendation(record=relationship, record_kind="graph", is_candidate=relationship_is_review_candidate(relationship), source_quality_row=source_quality_row, score=score)
