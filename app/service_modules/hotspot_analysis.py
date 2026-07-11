"""Pure hotspot-expansion helpers (research/AI workflows domain).

Extracted from ``SystemService`` per the SystemService Modularization ADR.
These are deterministic functions of their arguments only (candidate ranking,
evidence-layer / boundary summaries, lexicon matching). They hold no
``SystemService`` state; ``SystemService`` keeps the same method names as thin
facades that delegate here.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Mapping

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..models import HotspotLexicon


def rank_candidates(
    *,
    query: str,
    company_positions: list[dict[str, Any]],
    data_coverage: list[dict[str, Any]],
    retrieval_recall: dict[str, list[dict[str, Any]]],
    matched_lexicons: "list[HotspotLexicon]",
) -> dict[str, Any]:
    terms = {term.lower() for term in re.findall(r"[\w\u4e00-\u9fff]+", query)}
    for lexicon in matched_lexicons:
        terms.update(term.lower() for term in lexicon.terms)
        for key, values in lexicon.synonyms.items():
            terms.add(str(key).lower())
            terms.update(str(value).lower() for value in values)
    coverage_by_position = {row["position_id"]: row for row in data_coverage}
    recall_by_issuer: dict[str, int] = {}
    for bucket in retrieval_recall.values():
        if not isinstance(bucket, list):
            continue
        for row in bucket:
            issuer_id = str(row.get("issuer_id", ""))
            if issuer_id:
                recall_by_issuer[issuer_id] = recall_by_issuer.get(issuer_id, 0) + 1
    candidates: list[dict[str, Any]] = []
    for position in company_positions:
        text = " ".join(
            [
                str(position.get("role", "")),
                str(position.get("positioning_summary", "")),
                " ".join(str(item) for item in position.get("technology_tags", [])),
            ]
        ).lower()
        term_hits = sorted(term for term in terms if term and term in text)
        term_score = min(1.0, len(term_hits) / max(1, min(len(terms), 6)))
        coverage = coverage_by_position.get(position.get("position_id", ""), {})
        coverage_score = float(coverage.get("coverage_ratio", 0.0) or 0.0)
        evidence_score = 1.0 if coverage.get("linked_evidence_ids") else 0.0
        recall_score = min(1.0, recall_by_issuer.get(str(position.get("issuer_id", "")), 0) / 3)
        data_quality = str(position.get("data_quality", "needs_review"))
        quality_score = {"verified": 1.0, "complete": 0.9, "partial": 0.55, "needs_review": 0.25}.get(data_quality, 0.35)
        rank_score = round(term_score * 0.25 + coverage_score * 0.25 + evidence_score * 0.2 + recall_score * 0.2 + quality_score * 0.1, 6)
        candidates.append(
            {
                "position_id": position.get("position_id", ""),
                "issuer_id": position.get("issuer_id", ""),
                "security_id": position.get("security_id", ""),
                "chain_id": position.get("chain_id", ""),
                "node_ids": position.get("node_ids", []),
                "rank_score": rank_score,
                "score_components": {
                    "term_score": round(term_score, 4),
                    "coverage_score": round(coverage_score, 4),
                    "evidence_score": round(evidence_score, 4),
                    "recall_score": round(recall_score, 4),
                    "quality_score": round(quality_score, 4),
                },
                "matched_terms": term_hits,
                "explanation": "term match + data coverage + evidence link + public recall + data quality",
            }
        )
    candidates.sort(key=lambda item: item["rank_score"], reverse=True)
    return {
        "ranker": "local_hotspot_chain_coverage_evidence_score",
        "candidate_count": len(candidates),
        "candidates": candidates,
        "adapter_recommendation": {
            "llm_rerank_trigger": "use LLM rerank only after public recall, evidence layers, and company positioning coverage are available",
            "inputs": ["matched_lexicons", "retrieval_recall", "evidence_layers", "data_coverage"],
        },
    }


def boundary_summary(expansion: Mapping[str, Any]) -> dict[str, Any]:
    layers = expansion.get("evidence_layers", {})
    if not isinstance(layers, Mapping):
        layers = {}
    facts = [item for item in layers.get("facts", []) if isinstance(item, Mapping)]
    opinions = [item for item in layers.get("opinions", []) if isinstance(item, Mapping)]
    inferences = [item for item in layers.get("inferences", []) if isinstance(item, Mapping)]
    needs_verification = [item for item in layers.get("needs_verification", []) if isinstance(item, Mapping)]
    inference_flags = [
        item
        for item in inferences
        if item.get("needs_verification") is True
        or item.get("automation_allowed") is False
        or "not_fact" in str(item.get("source_boundary", ""))
    ]
    fact_resources = {str(item.get("resource_id", "")) for item in facts if item.get("resource_id")}
    inference_resources = {str(item.get("resource_id", "")) for item in inferences if item.get("resource_id")}
    overlap = sorted(fact_resources & inference_resources)
    return {
        "facts_have_source_or_evidence": all(item.get("evidence_ids") or item.get("source_uri") or item.get("resource_type") in {"document", "evidence"} for item in facts),
        "opinions_have_boundary": all(item.get("source_refs") or item.get("source_boundary") or item.get("resource_type") == "macro_theme" for item in opinions),
        "inferences_need_verification": len(inference_flags) == len(inferences) if inferences else False,
        "needs_verification_count": len(needs_verification),
        "fact_inference_overlap": overlap,
        "separated_layers": bool(facts) and bool(opinions) and bool(inferences) and bool(needs_verification) and not overlap,
    }


def layer_summary(expansion: Mapping[str, Any]) -> dict[str, Any]:
    layers = expansion.get("evidence_layers", {})
    if not isinstance(layers, Mapping):
        layers = {}
    counts = {
        "facts": len(layers.get("facts", [])) if isinstance(layers.get("facts", []), list) else 0,
        "opinions": len(layers.get("opinions", [])) if isinstance(layers.get("opinions", []), list) else 0,
        "inferences": len(layers.get("inferences", [])) if isinstance(layers.get("inferences", []), list) else 0,
        "needs_verification": len(layers.get("needs_verification", [])) if isinstance(layers.get("needs_verification", []), list) else 0,
    }
    counts["present_layer_count"] = sum(1 for value in counts.values() if value > 0)
    recall = expansion.get("retrieval_recall", {})
    if isinstance(recall, Mapping):
        counts["public_recall_count"] = len(recall.get("public_facts", [])) if isinstance(recall.get("public_facts", []), list) else 0
        counts["research_opinion_recall_count"] = len(recall.get("research_opinions", [])) if isinstance(recall.get("research_opinions", []), list) else 0
        counts["inference_recall_count"] = len(recall.get("inferences", [])) if isinstance(recall.get("inferences", []), list) else 0
        counts["market_signal_recall_count"] = len(recall.get("market_signals", [])) if isinstance(recall.get("market_signals", []), list) else 0
    return counts


def lexicon_matches(lexicon: "HotspotLexicon", query: str) -> bool:
    terms = [lexicon.name, *lexicon.terms]
    for key, values in lexicon.synonyms.items():
        terms.append(key)
        terms.extend(values)
    lowered_terms = [str(item).lower() for item in terms]
    return any(query in item or item in query for item in lowered_terms if item)
