"""Pure evidence-locator, bbox, and numeric-extraction helpers.

Extracted from ``SystemService`` per the SystemService Modularization ADR
(evidence domain, batch 2). Every function is a deterministic transform of its
arguments only: none touch the store, audit log, permissions, or any
``SystemService`` state. ``SystemService`` keeps the same method names as thin
facades delegating here.

Deliberately left in ``SystemService``:
- ``_evidence_is_official_public`` (reads ``self.store``).
- ``_bbox_gold_label_validation`` (larger orchestration over evidence sets).
- ``_normalize_gold_bbox`` (already a facade over ``normalizers``).
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Mapping

from ..models import Evidence
from .normalizers import normalize_gold_bbox


def evidence_source_pages(source_text: str, parsed_pages: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    pages: dict[int, dict[str, Any]] = {}
    for index, page_text in enumerate(source_text.split("\f"), start=1):
        pages[index] = {"page_no": index, "markdown": page_text, "layout_items": [], "tables": [], "assets": []}
    for page in parsed_pages:
        page_no = int(page.get("page_no") or len(pages) + 1)
        merged = dict(pages.get(page_no, {"page_no": page_no, "markdown": ""}))
        merged.update(page)
        pages[page_no] = merged
    return pages


def evidence_locator(
    *,
    document_id: str,
    page_no: int,
    chunk_index: int,
    chunk: str,
    source_pages: Mapping[int, Mapping[str, Any]],
    locator_source: str,
) -> dict[str, Any]:
    page = source_pages.get(page_no, {})
    page_text = str(page.get("markdown", ""))
    layout_item = best_layout_item(chunk, page.get("layout_items", []), chunk_index=chunk_index)
    bbox = dict(layout_item.get("bbox", {})) if isinstance(layout_item.get("bbox"), Mapping) else {}
    tables = matching_locator_tables(chunk, page.get("tables", []))
    assets = [dict(item) for item in page.get("assets", []) if isinstance(item, Mapping)]
    scheme = "ocr_bbox_span_v1" if bbox or tables or assets else "page_chunk_v1"
    return {
        "scheme": scheme,
        "document_id": document_id,
        "page_no": page_no,
        "chunk_index": chunk_index,
        "source": locator_source,
        "span": chunk_span(page_text, chunk),
        "bbox": bbox,
        "layout_type": str(layout_item.get("type", "")) if layout_item else "",
        "layout_confidence": float(layout_item.get("confidence", 0.0) or 0.0) if layout_item else 0.0,
        "tables": tables,
        "assets": assets,
        "legacy_bbox": f"page={page_no};chunk={chunk_index}",
    }


def chunk_span(page_text: str, chunk: str) -> dict[str, Any]:
    start = page_text.find(chunk) if page_text else -1
    if start < 0:
        compact_page = re.sub(r"\s+", " ", page_text)
        compact_chunk = re.sub(r"\s+", " ", chunk).strip()
        start = compact_page.find(compact_chunk) if compact_page and compact_chunk else -1
        return {
            "start": max(0, start),
            "end": max(0, start) + len(compact_chunk) if start >= 0 else len(chunk),
            "length": len(chunk),
            "matched": start >= 0,
            "text_sha256": hashlib.sha256(chunk.encode("utf-8")).hexdigest(),
        }
    return {
        "start": start,
        "end": start + len(chunk),
        "length": len(chunk),
        "matched": True,
        "text_sha256": hashlib.sha256(chunk.encode("utf-8")).hexdigest(),
    }


def best_layout_item(chunk: str, layout_items: Any, *, chunk_index: int) -> dict[str, Any]:
    if not isinstance(layout_items, list):
        return {}
    candidates = [dict(item) for item in layout_items if isinstance(item, Mapping)]
    if not candidates:
        return {}
    scored = [(text_overlap_score(chunk, str(item.get("text", ""))), item) for item in candidates]
    scored.sort(key=lambda item: item[0], reverse=True)
    if scored and scored[0][0] > 0:
        return scored[0][1]
    if 0 <= chunk_index - 1 < len(candidates):
        return candidates[chunk_index - 1]
    return {}


def text_overlap_score(left: str, right: str) -> float:
    left_norm = re.sub(r"\s+", " ", left).strip().lower()
    right_norm = re.sub(r"\s+", " ", right).strip().lower()
    if not left_norm or not right_norm:
        return 0.0
    if left_norm in right_norm or right_norm in left_norm:
        return min(len(left_norm), len(right_norm)) / max(1, max(len(left_norm), len(right_norm)))
    left_terms = set(re.findall(r"[\w一-鿿]+", left_norm))
    right_terms = set(re.findall(r"[\w一-鿿]+", right_norm))
    return len(left_terms & right_terms) / max(1, len(left_terms | right_terms))


def matching_locator_tables(chunk: str, tables: Any) -> list[dict[str, Any]]:
    if not isinstance(tables, list):
        return []
    matched: list[dict[str, Any]] = []
    for table in tables:
        if not isinstance(table, Mapping):
            continue
        table_copy = dict(table)
        cells = [dict(cell) for cell in table_copy.get("cells", []) if isinstance(cell, Mapping)] if isinstance(table_copy.get("cells", []), list) else []
        cell_text = " ".join(str(cell.get("text", "")) for cell in cells)
        if cells and (text_overlap_score(chunk, cell_text) > 0 or len(tables) == 1):
            table_copy["cells"] = cells
            matched.append(table_copy)
    return matched


def evidence_has_structured_locator(evidence: Evidence) -> bool:
    return isinstance(evidence.locator, Mapping) and bool(evidence.locator.get("scheme"))


def evidence_has_real_bbox(evidence: Evidence) -> bool:
    bbox = evidence.locator.get("bbox", {}) if isinstance(evidence.locator, Mapping) else {}
    return isinstance(bbox, Mapping) and {"x", "y", "width", "height"}.issubset(bbox.keys())


def evidence_table_cell_count(evidence: Evidence) -> int:
    tables = evidence.locator.get("tables", []) if isinstance(evidence.locator, Mapping) else []
    if not isinstance(tables, list):
        return 0
    return sum(len(table.get("cells", [])) for table in tables if isinstance(table, Mapping) and isinstance(table.get("cells", []), list))


def evidence_table_cell_bbox_count(evidence: Evidence) -> int:
    tables = evidence.locator.get("tables", []) if isinstance(evidence.locator, Mapping) else []
    if not isinstance(tables, list):
        return 0
    count = 0
    for table in tables:
        if not isinstance(table, Mapping):
            continue
        cells = table.get("cells", [])
        if not isinstance(cells, list):
            continue
        for cell in cells:
            bbox = cell.get("bbox", {}) if isinstance(cell, Mapping) else {}
            if isinstance(bbox, Mapping) and bbox:
                count += 1
    return count


def evidence_bbox(evidence: Evidence) -> dict[str, Any]:
    bbox = evidence.locator.get("bbox", {}) if isinstance(evidence.locator, Mapping) else {}
    if isinstance(bbox, Mapping) and bbox:
        return normalize_gold_bbox(bbox)
    return {}


def bbox_iou(left: Mapping[str, Any], right: Mapping[str, Any]) -> float:
    if not left or not right:
        return 0.0
    left_x1 = float(left.get("x", 0) or 0)
    left_y1 = float(left.get("y", 0) or 0)
    left_x2 = left_x1 + float(left.get("width", 0) or 0)
    left_y2 = left_y1 + float(left.get("height", 0) or 0)
    right_x1 = float(right.get("x", 0) or 0)
    right_y1 = float(right.get("y", 0) or 0)
    right_x2 = right_x1 + float(right.get("width", 0) or 0)
    right_y2 = right_y1 + float(right.get("height", 0) or 0)
    intersection_width = max(0.0, min(left_x2, right_x2) - max(left_x1, right_x1))
    intersection_height = max(0.0, min(left_y2, right_y2) - max(left_y1, right_y1))
    intersection = intersection_width * intersection_height
    left_area = max(0.0, left_x2 - left_x1) * max(0.0, left_y2 - left_y1)
    right_area = max(0.0, right_x2 - right_x1) * max(0.0, right_y2 - right_y1)
    union = left_area + right_area - intersection
    return intersection / union if union > 0 else 0.0


def extract_number_by_alias(
    payload: Any,
    aliases: set[str],
    *,
    percent_as_ratio: bool = False,
    skip_keys: set[str] | None = None,
) -> float | None:
    skip_keys = skip_keys or set()
    if isinstance(payload, list):
        for item in payload:
            value = extract_number_by_alias(item, aliases, percent_as_ratio=percent_as_ratio, skip_keys=skip_keys)
            if value is not None:
                return value
        return None
    if not isinstance(payload, Mapping):
        return coerce_float(payload, percent_as_ratio=percent_as_ratio)
    normalized_aliases = {normalized_metric_key(alias) for alias in aliases}
    for key, value in payload.items():
        if normalized_metric_key(str(key)) in normalized_aliases:
            number = coerce_float(value, percent_as_ratio=percent_as_ratio)
            if number is not None:
                return number
    for key, value in payload.items():
        if str(key) in skip_keys:
            continue
        if isinstance(value, Mapping) or isinstance(value, list):
            number = extract_number_by_alias(value, aliases, percent_as_ratio=percent_as_ratio, skip_keys=skip_keys)
            if number is not None:
                return number
    return None


def coerce_float(value: Any, *, percent_as_ratio: bool = False) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    text = str(value).strip()
    if not text or text in {"-", "--", "None", "null"}:
        return None
    multiplier = 1.0
    if text.startswith("(") and text.endswith(")"):
        multiplier = -1.0
        text = text[1:-1]
    is_percent = text.endswith("%")
    text = text.replace(",", "").replace("$", "").replace("¥", "").replace("￥", "").replace("%", "")
    try:
        number = float(text) * multiplier
    except ValueError:
        return None
    if is_percent and percent_as_ratio:
        return number / 100.0
    return number


def normalized_metric_key(value: str) -> str:
    return re.sub(r"[\s_\-:/]+", "", value.strip().lower())


def string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in re.split(r"[,;/，；]+", value) if item.strip()]
    if isinstance(value, list | tuple | set):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []
