from __future__ import annotations

import re
from typing import Any, Mapping

from app.utils import to_plain


GRAPH_NODE_ID_CANDIDATES = [
    "id",
    "data_id",
    "issuer_id",
    "security_id",
    "card_id",
    "document_id",
    "evidence_id",
    "thesis_id",
    "signal_id",
    "decision_id",
    "intent_id",
    "proposal_id",
    "mapping_id",
    "snapshot_id",
    "holding_id",
    "event_id",
    "replay_id",
    "action_id",
    "challenger_id",
    "review_id",
    "exception_id",
    "task_id",
    "relationship_id",
    "research_report_id",
    "viewpoint_id",
    "forecast_id",
    "analyst_id",
    "score_id",
    "observation_id",
    "analysis_conclusion_id",
    "simulation_feedback_id",
]


def graph_node_identity(collection: str, row: Mapping[str, Any]) -> str:
    candidates = [
        f"{collection[:-1]}_id" if collection.endswith("s") else f"{collection}_id",
        *GRAPH_NODE_ID_CANDIDATES,
    ]
    for key in candidates:
        value = str(row.get(key, "")).strip()
        if value:
            return value
    return ""


def neo4j_label(collection: str) -> str:
    return "".join(part.capitalize() for part in collection.split("_"))


def neo4j_relationship_type(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_]+", "_", value).strip("_").upper()
    return normalized or "RELATED_TO"


def neo4j_properties(values: Mapping[str, Any], defaults: Mapping[str, Any]) -> dict[str, Any]:
    props = {str(key): to_plain(value) for key, value in values.items()}
    props.update(defaults)
    return props
