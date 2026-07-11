"""Pure company-profile field extraction helpers.

Extracted from ``SystemService`` per the SystemService Modularization ADR
(evidence domain). Every function is a deterministic transform of its text
argument(s) only: none touch the store, audit log, permissions, or any
``SystemService`` state. ``SystemService`` keeps the same method names as thin
facades delegating here.
"""

from __future__ import annotations

import re
from typing import Any

from .normalizers import unique_strings


def extract_field_value(field_name: str, text: str) -> Any:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return None
    if field_name == "business_summary":
        return business_summary(normalized)
    if field_name == "products":
        return products(normalized)
    if field_name == "website_url":
        return profile_url(normalized, kind="website")
    if field_name == "ir_url":
        return profile_url(normalized, kind="ir")
    if field_name == "headquarters":
        return headquarters(normalized)
    if field_name == "employee_count":
        return employee_count(normalized)
    if field_name == "management":
        return management(normalized)
    if field_name == "key_customers":
        return named_list(normalized, kind="customers")
    if field_name == "key_suppliers":
        return named_list(normalized, kind="suppliers")
    if field_name in {"country", "region", "sector", "industry"}:
        return labeled_text(field_name, normalized)
    if field_name == "period":
        return period(normalized)
    if field_name in {"revenue", "net_income", "gross_margin", "cash", "debt"}:
        return numeric_field(field_name, normalized)
    return None

def business_summary(text: str) -> str:
    patterns = [
        r"(?:business summary|business overview|company overview)[:：]?\s*([^。.;\n]{20,320})",
        r"(?:主要从事|主营业务(?:为|是|包括)?|公司主要从事)[:：]?\s*([^。.;\n]{8,260})",
        r"(?:is engaged in|engages in|focuses on|provides|manufactures|supplies)[:：]?\s*([^。.;\n]{12,260})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return clean_text(match.group(1), max_chars=280)
    return ""

def products(text: str) -> list[str]:
    patterns = [
        r"(?:products include|products are|product portfolio includes)[:：]?\s*([^。.;\n]{4,180})",
        r"(?:主要产品(?:包括|为)?|产品包括|产品为)[:：]?\s*([^。.;\n]{3,180})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        raw = clean_text(match.group(1), max_chars=180)
        parts = re.split(r"[,，、;/；]|\band\b|\band\s+", raw, flags=re.IGNORECASE)
        products = [part.strip(" -:：()（）") for part in parts if 1 < len(part.strip(" -:：()（）")) <= 60]
        return unique_strings(products)[:12]
    return []

def profile_url(text: str, *, kind: str) -> str:
    if kind == "ir":
        labels = ["investor relations", "IR website", "IR site", "investors", "投资者关系", "投资者关系网站"]
    else:
        labels = ["official website", "website", "corporate website", "公司官网", "官方网站", "官网"]
    label_expr = "|".join(re.escape(label) for label in labels)
    pattern = rf"(?:{label_expr})[:：\s]*(https?://[^\s,，;；。)）]+|www\.[^\s,，;；。)）]+)"
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match and kind == "website" and not re.search(r"(?:investor relations|\bir\b|investors|投资者关系)", text, flags=re.IGNORECASE):
        match = re.search(r"\b(https?://(?:www\.)?[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?:/[^\s,，;；。)）]*)?)", text)
    if not match:
        return ""
    url = match.group(1).strip(" <>[]()（）,，.;；。")
    if url.startswith("www."):
        url = f"https://{url}"
    return url[:240]

def headquarters(text: str) -> str:
    patterns = [
        r"(?:headquarters|headquartered at|headquartered in|principal executive offices)[:：]?\s*([^。.;\n]{4,160})",
        r"(?:总部地址|总部位于|办公地址|注册地址)[:：]?\s*([^。.;\n]{4,160})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return clean_text(match.group(1), max_chars=160)
    return ""

def employee_count(text: str) -> int | None:
    patterns = [
        r"(?:employees|full-time employees|employee count|headcount)[^\d]{0,40}(\d[\d,]*(?:\.\d+)?)\s*(million|thousand|people|employees)?",
        r"(?:员工人数|雇员|职工人数|员工总数)[^\d]{0,20}(\d[\d,]*(?:\.\d+)?)\s*(万人|万名|人|名)?",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        value = parse_number(match.group(1), str(match.group(2) or ""))
        if value is None:
            continue
        return int(round(value))
    return None

def management(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    patterns = [
        r"\b(CEO|Chief Executive Officer|CFO|Chief Financial Officer|Chairman|President)\b\s*(?:is|:|：)?\s*([A-Z][A-Za-z'-]+(?:\s+(?!(?:CEO|CFO|Chief|Chairman|President)\b)[A-Z][A-Za-z'-]+){0,3})",
        r"(董事长|总经理|首席执行官|财务总监|总裁|CEO|CFO)[:：为是\s]*([\u4e00-\u9fff]{2,8})",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            role = clean_text(match.group(1), max_chars=80)
            name = clean_text(match.group(2), max_chars=80)
            if role and name:
                rows.append({"role": role, "name": name})
    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        key = (row["role"].lower(), row["name"].lower())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped[:12]

def named_list(text: str, *, kind: str) -> list[str]:
    if kind == "customers":
        patterns = [
            r"(?:customers include|major customers include|key customers include)[:：]?\s*([^。.;\n]{3,220})",
            r"(?:主要客户(?:包括|为)?|客户包括|核心客户包括)[:：]?\s*([^。.;\n]{2,220})",
        ]
    else:
        patterns = [
            r"(?:suppliers include|major suppliers include|key suppliers include)[:：]?\s*([^。.;\n]{3,220})",
            r"(?:主要供应商(?:包括|为)?|供应商包括|核心供应商包括)[:：]?\s*([^。.;\n]{2,220})",
        ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        raw = clean_text(match.group(1), max_chars=220)
        parts = re.split(r"[,，、;/；]|\band\b|\b及\b|\b和\b", raw, flags=re.IGNORECASE)
        values = [part.strip(" -:：()（）") for part in parts if 1 < len(part.strip(" -:：()（）")) <= 80]
        return unique_strings(values)[:16]
    return []

def labeled_text(field_name: str, text: str) -> str:
    labels = {
        "country": ["country", "所在国家", "注册国家"],
        "region": ["region", "headquartered in", "总部位于", "所在地"],
        "sector": ["sector", "板块", "所属板块"],
        "industry": ["industry", "行业", "所属行业"],
    }
    label_expr = "|".join(re.escape(label) for label in labels[field_name])
    match = re.search(rf"(?:{label_expr})[:：]?\s*([A-Za-z\u4e00-\u9fff][A-Za-z\u4e00-\u9fff\s\-]{1,50})", text, flags=re.IGNORECASE)
    if not match:
        return ""
    return clean_text(match.group(1), max_chars=60)

def period(text: str) -> str:
    match = re.search(r"(FY\s?20\d{2}|20\d{2}\s?Q[1-4]|20\d{2}\s?H[12]|20\d{2}年(?:一季报|半年报|三季报|年报|年度|季度))", text, flags=re.IGNORECASE)
    return match.group(1).replace(" ", "") if match else ""

def numeric_field(field_name: str, text: str) -> float | None:
    keywords = {
        "revenue": ["revenue", "sales", "operating revenue", "营业收入", "营收"],
        "net_income": ["net income", "net profit", "profit attributable", "净利润", "归母净利润"],
        "gross_margin": ["gross margin", "毛利率"],
        "cash": ["cash and equivalents", "cash", "现金及现金等价物", "货币资金"],
        "debt": ["total debt", "debt", "有息负债", "总债务"],
    }
    keyword_expr = "|".join(re.escape(item) for item in keywords[field_name])
    pattern = rf"(?:{keyword_expr})[^\d\-]{{0,30}}([-+]?\d[\d,]*(?:\.\d+)?)\s*(%|percent|percentage points|billion|million|thousand|亿元|亿|万元|万|元|美元|人民币)?"
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return None
    raw_number = match.group(1)
    unit = str(match.group(2) or "")
    return parse_number(raw_number, unit, percentage=field_name == "gross_margin")

def parse_number(raw_number: str, unit: str, *, percentage: bool = False) -> float | None:
    try:
        value = float(str(raw_number).replace(",", ""))
    except ValueError:
        return None
    unit_lower = unit.lower()
    if percentage or unit_lower in {"%", "percent", "percentage points"}:
        return round(value / 100, 6) if value > 1 else round(value, 6)
    if "billion" in unit_lower:
        value *= 1_000_000_000
    elif "million" in unit_lower:
        value *= 1_000_000
    elif "thousand" in unit_lower:
        value *= 1_000
    elif "亿" in unit:
        value *= 100_000_000
    elif "万" in unit:
        value *= 10_000
    return round(value, 4)

def clean_text(value: str, *, max_chars: int) -> str:
    cleaned = re.sub(r"\s+", " ", str(value)).strip(" \t\r\n-:：,，.;。")
    return cleaned[:max_chars].rstrip(" ,，.;。")

