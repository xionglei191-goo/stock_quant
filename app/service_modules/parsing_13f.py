"""Pure SEC 13F information-table parsing helpers.

Extracted from ``SystemService`` per the SystemService Modularization ADR
(evidence/ingestion domain). Every function is a deterministic transform of its
arguments only: none touch the store, audit log, permissions, or network. The
stateful entry points (``_13f_information_table_text``,
``_13f_entity_mapping_for_row``, ``_13f_security_for_row``) stay in
``SystemService`` because they read ``self.store`` / fetch over the network.
``SystemService`` keeps the same method names as thin facades delegating here.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any, Mapping

from ..errors import ValidationError
from .normalizers import normalize_cusip


def find_information_table_start(text: str) -> int:
    for match in re.finditer(r"<([A-Za-z0-9_]+:)?informationTable\b", text):
        return match.start()
    return -1


def find_information_table_end(text: str) -> int:
    match = re.search(r"</([A-Za-z0-9_]+:)?informationTable\s*>", text)
    return match.end() if match else -1


def xml_local_name(tag: Any) -> str:
    value = str(tag)
    if "}" in value:
        value = value.rsplit("}", maxsplit=1)[-1]
    if ":" in value:
        value = value.rsplit(":", maxsplit=1)[-1]
    return value


def xml_child_text(element: ET.Element, local_name: str) -> str:
    for child in element.iter():
        if child is element:
            continue
        if xml_local_name(child.tag) == local_name:
            return (child.text or "").strip()
    return ""


def float_from_text(value: Any) -> float:
    text = str(value or "").replace(",", "").strip()
    if not text:
        return 0.0
    if text.startswith("(") and text.endswith(")"):
        text = f"-{text[1:-1]}"
    try:
        return float(text)
    except ValueError as exc:
        raise ValidationError(f"expected numeric value, got {value!r}") from exc


def voting_authority(element: ET.Element) -> str:
    sole = xml_child_text(element, "Sole")
    shared = xml_child_text(element, "Shared")
    none = xml_child_text(element, "None")
    parts = []
    if sole:
        parts.append(f"sole={sole}")
    if shared:
        parts.append(f"shared={shared}")
    if none:
        parts.append(f"none={none}")
    return ";".join(parts)


def parse_information_rows(text: str) -> list[dict[str, Any]]:
    normalized = str(text or "").strip()
    if not normalized:
        raise ValidationError("13F information table body is empty")
    start = find_information_table_start(normalized)
    if start > 0:
        normalized = normalized[start:]
        end = find_information_table_end(normalized)
        if end > 0:
            normalized = normalized[:end]
    try:
        root = ET.fromstring(normalized.encode("utf-8"))
    except ET.ParseError as exc:
        raise ValidationError(f"invalid 13F information table XML: {exc}") from exc
    info_tables = [element for element in root.iter() if xml_local_name(element.tag).lower() == "infotable"]
    rows: list[dict[str, Any]] = []
    for index, element in enumerate(info_tables):
        raw_value = xml_child_text(element, "value")
        shares = float_from_text(xml_child_text(element, "sshPrnamt"))
        value_usd = float_from_text(raw_value) * 1000.0
        put_call = xml_child_text(element, "putCall")
        row = {
            "name_of_issuer": xml_child_text(element, "nameOfIssuer"),
            "title_of_class": xml_child_text(element, "titleOfClass"),
            "cusip": normalize_cusip(xml_child_text(element, "cusip")),
            "figi": xml_child_text(element, "figi"),
            "value_thousands": float_from_text(raw_value),
            "value_usd": value_usd,
            "shares": shares,
            "share_type": xml_child_text(element, "sshPrnamtType"),
            "put_call": put_call,
            "investment_discretion": xml_child_text(element, "investmentDiscretion"),
            "other_manager": xml_child_text(element, "otherManager"),
            "voting_authority": voting_authority(element),
            "row_number": index + 1,
        }
        if not row["cusip"] and not row["figi"] and not row["name_of_issuer"]:
            continue
        if put_call:
            row["derivative_flag"] = True
        rows.append(row)
    if not rows:
        raise ValidationError("13F information table contains no infoTable rows")
    return rows


def mapping_overrides(values: Any) -> dict[str, Mapping[str, Any]]:
    if isinstance(values, Mapping):
        iterable = values.values()
    elif isinstance(values, list):
        iterable = values
    else:
        iterable = []
    mappings: dict[str, Mapping[str, Any]] = {}
    for item in iterable:
        if not isinstance(item, Mapping):
            continue
        cusip = normalize_cusip(str(item.get("cusip", "")))
        figi = str(item.get("figi", "")).strip().upper()
        if cusip:
            mappings[cusip] = item
        if figi:
            mappings[figi] = item
    return mappings


def holding_payload(row: Mapping[str, Any], payload: Mapping[str, Any]) -> dict[str, Any]:
    report_period = str(row["report_period"])
    filer_cik = str(row.get("filer_cik", ""))
    issuer_id = str(row["issuer_id"])
    security_id = str(row["security_id"])
    cusip = str(row.get("cusip", ""))
    holding_id = str(payload.get("holding_id", "")).strip()
    if not holding_id:
        raw = f"13f_{issuer_id}_{security_id}_{report_period}_{filer_cik}_{cusip}_{row.get('row_number', '')}"
        holding_id = re.sub(r"[^A-Za-z0-9_-]+", "_", raw).strip("_").lower()
    return {
        "holding_id": holding_id,
        "issuer_id": issuer_id,
        "security_id": security_id,
        "source_id": str(row.get("source_id", payload.get("source_id", "sec_edgar"))),
        "filer_cik": filer_cik,
        "filer_name": str(row.get("filer_name", "")),
        "report_period": report_period,
        "shares": float(row.get("shares", 0.0) or 0.0),
        "value_usd": float(row.get("value_usd", 0.0) or 0.0),
        "voting_authority": str(row.get("voting_authority", "")),
    }


def unmapped_row(row: Mapping[str, Any], *, index: int) -> dict[str, Any]:
    return {
        "index": index,
        "name_of_issuer": row.get("name_of_issuer", ""),
        "title_of_class": row.get("title_of_class", ""),
        "cusip": row.get("cusip", ""),
        "figi": row.get("figi", ""),
        "value_usd": row.get("value_usd", 0.0),
        "shares": row.get("shares", 0.0),
        "reason": "missing_cusip_figi_issuer_security_mapping",
    }
