"""Store-backed, read-only graph traceability reporting."""

from __future__ import annotations

from typing import Any, Mapping

from ..models import DecisionPack, ResearchAnswer, ThesisCard


class GraphTraceabilityReporting:
    """Build traceability rows from an explicitly injected store."""

    def __init__(self, store: Any) -> None:
        self.store = store

    @staticmethod
    def _bounded_limit(value: Any, max_value: int = 100) -> int:
        return max(1, min(max_value, int(value)))

    @staticmethod
    def _truthy(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() not in {"", "0", "false", "no", "off"}
        return bool(value)

    def graph_traceability_report(self, filters: Mapping[str, Any] | None = None) -> dict[str, Any]:
        filters = filters or {}
        issuer_id = str(filters.get("issuer_id", "")).strip()
        include_details = self._truthy(filters.get("include_details", True))
        limit = self._bounded_limit(filters.get("limit", 100), 1000)
        theses = [item for item in self.store.theses.values() if not issuer_id or item.issuer_id == issuer_id]
        answers = [item for item in self.store.research_answers.values() if not issuer_id or item.issuer_id == issuer_id]
        decisions = self._decisions_for_issuer(issuer_id) if issuer_id else list(self.store.decisions.values())
        thesis_rows = [self._thesis_traceability_row(item) for item in sorted(theses, key=lambda row: row.thesis_id)]
        decision_rows = [self._decision_traceability_row(item) for item in sorted(decisions, key=lambda row: row.decision_id)]
        answer_rows = [self._answer_traceability_row(item) for item in sorted(answers, key=lambda row: row.answer_id)]

        def rate(rows: list[dict[str, Any]]) -> float:
            if not rows:
                return 1.0
            return round(sum(1 for row in rows if row["traceable"]) / len(rows), 4)

        details = {
            "theses": thesis_rows[:limit],
            "decisions": decision_rows[:limit],
            "research_answers": answer_rows[:limit],
        } if include_details else {}
        return {
            "issuer_id": issuer_id,
            "traceability_rate": rate(thesis_rows + decision_rows + answer_rows),
            "thesis_traceability_rate": rate(thesis_rows),
            "decision_traceability_rate": rate(decision_rows),
            "research_answer_traceability_rate": rate(answer_rows),
            "counts": {
                "theses": len(thesis_rows),
                "decisions": len(decision_rows),
                "research_answers": len(answer_rows),
                "untraceable_theses": sum(1 for row in thesis_rows if not row["traceable"]),
                "untraceable_decisions": sum(1 for row in decision_rows if not row["traceable"]),
                "untraceable_research_answers": sum(1 for row in answer_rows if not row["traceable"]),
            },
            "details": details,
        }

    def _decisions_for_issuer(self, issuer_id: str) -> list[DecisionPack]:
        if not issuer_id:
            return list(self.store.decisions.values())
        decisions: list[DecisionPack] = []
        for decision in self.store.decisions.values():
            for signal_id in decision.signal_ids:
                signal = self.store.signals.get(signal_id)
                thesis = self.store.theses.get(signal.thesis_id) if signal else None
                if thesis and thesis.issuer_id == issuer_id:
                    decisions.append(decision)
                    break
        return decisions

    def _thesis_traceability_row(self, thesis: ThesisCard) -> dict[str, Any]:
        linked_evidence = [self.store.evidence[evidence_id] for evidence_id in thesis.evidence_ids if evidence_id in self.store.evidence]
        document_ids = sorted({item.document_id for item in linked_evidence if item.document_id in self.store.documents})
        missing_evidence_ids = [evidence_id for evidence_id in thesis.evidence_ids if evidence_id not in self.store.evidence]
        missing_document_ids = sorted({item.document_id for item in linked_evidence if item.document_id not in self.store.documents})
        issues: list[str] = []
        if not thesis.evidence_ids:
            issues.append("missing_evidence_ids")
        if missing_evidence_ids:
            issues.append("missing_evidence_records")
        if missing_document_ids:
            issues.append("missing_source_documents")
        if not document_ids:
            issues.append("missing_document_backlink")
        return {
            "resource_type": "thesis",
            "resource_id": thesis.thesis_id,
            "issuer_id": thesis.issuer_id,
            "title": thesis.hypothesis,
            "evidence_ids": list(thesis.evidence_ids),
            "linked_evidence_ids": [item.evidence_id for item in linked_evidence],
            "document_ids": document_ids,
            "missing_evidence_ids": missing_evidence_ids,
            "missing_document_ids": missing_document_ids,
            "traceable": not issues,
            "issues": issues,
        }

    def _decision_traceability_row(self, decision: DecisionPack) -> dict[str, Any]:
        signal_ids = list(decision.signal_ids)
        linked_signals = [self.store.signals[signal_id] for signal_id in signal_ids if signal_id in self.store.signals]
        missing_signal_ids = [signal_id for signal_id in signal_ids if signal_id not in self.store.signals]
        thesis_rows: list[dict[str, Any]] = []
        missing_thesis_ids: list[str] = []
        for signal in linked_signals:
            thesis = self.store.theses.get(signal.thesis_id)
            if thesis is None:
                missing_thesis_ids.append(signal.thesis_id)
                continue
            thesis_rows.append(self._thesis_traceability_row(thesis))
        evidence_ids = sorted({evidence_id for row in thesis_rows for evidence_id in row["linked_evidence_ids"]})
        document_ids = sorted({document_id for row in thesis_rows for document_id in row["document_ids"]})
        issues: list[str] = []
        if not signal_ids:
            issues.append("missing_signal_ids")
        if missing_signal_ids:
            issues.append("missing_signal_records")
        if missing_thesis_ids:
            issues.append("missing_thesis_records")
        if not thesis_rows:
            issues.append("missing_thesis_backlink")
        if any(not row["traceable"] for row in thesis_rows):
            issues.append("untraceable_thesis")
        if not evidence_ids or not document_ids:
            issues.append("missing_evidence_or_document_path")
        return {
            "resource_type": "decision",
            "resource_id": decision.decision_id,
            "approval_state": decision.approval_state,
            "signal_ids": signal_ids,
            "thesis_ids": [row["resource_id"] for row in thesis_rows],
            "evidence_ids": evidence_ids,
            "document_ids": document_ids,
            "missing_signal_ids": missing_signal_ids,
            "missing_thesis_ids": sorted(set(missing_thesis_ids)),
            "traceable": not issues,
            "issues": issues,
        }

    def _answer_traceability_row(self, answer: ResearchAnswer) -> dict[str, Any]:
        evidence = [self.store.evidence[evidence_id] for evidence_id in answer.evidence_ids if evidence_id in self.store.evidence]
        evidence_document_ids = {item.document_id for item in evidence}
        missing_evidence_ids = [evidence_id for evidence_id in answer.evidence_ids if evidence_id not in self.store.evidence]
        missing_document_ids = [document_id for document_id in answer.source_document_ids if document_id not in self.store.documents]
        issues: list[str] = []
        if not answer.evidence_ids or missing_evidence_ids:
            issues.append("missing_evidence_records")
        if not answer.source_document_ids or missing_document_ids:
            issues.append("missing_source_documents")
        if answer.source_document_ids and not set(answer.source_document_ids).issubset(evidence_document_ids):
            issues.append("source_document_not_backed_by_evidence")
        if not answer.english_source_text.strip():
            issues.append("missing_english_source_text")
        return {
            "resource_type": "research_answer",
            "resource_id": answer.answer_id,
            "issuer_id": answer.issuer_id,
            "question": answer.question,
            "evidence_ids": list(answer.evidence_ids),
            "linked_evidence_ids": [item.evidence_id for item in evidence],
            "document_ids": list(answer.source_document_ids),
            "missing_evidence_ids": missing_evidence_ids,
            "missing_document_ids": missing_document_ids,
            "traceable": not issues,
            "issues": issues,
        }
