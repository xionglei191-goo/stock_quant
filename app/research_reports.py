from __future__ import annotations

import hashlib
from pathlib import Path
import re
from typing import Any, Mapping


DEFAULT_REPORT_EXTENSIONS = {".pdf"}


INDUSTRY_KEYWORDS = [
    ("semiconductor", ["半导体", "芯片", "晶圆", "封测", "eda", "chip", "semiconductor"]),
    ("ai_compute", ["ai", "人工智能", "算力", "gpu", "大模型", "服务器", "数据中心"]),
    ("new_energy", ["新能源", "光伏", "储能", "锂电", "电池", "风电", "solar", "battery"]),
    ("automotive", ["汽车", "智能车", "电动车", "ev", "auto", "adas"]),
    ("pharma_healthcare", ["医药", "创新药", "医疗", "器械", "pharma", "biotech", "healthcare"]),
    ("consumer", ["消费", "食品", "饮料", "零售", "consumer", "retail"]),
    ("finance", ["银行", "保险", "券商", "金融", "bank", "insurance", "brokerage"]),
    ("real_estate", ["地产", "物业", "房地产", "real estate"]),
    ("materials_chemicals", ["化工", "材料", "有色", "钢铁", "煤炭", "chemical", "materials"]),
    ("internet_software", ["互联网", "软件", "云", "saas", "software", "internet"]),
    ("macro_strategy", ["宏观", "策略", "市场", "配置", "利率", "汇率", "macro", "strategy"]),
]

REPORT_TYPE_KEYWORDS = [
    ("company_update", ["公司", "点评", "更新", "跟踪", "深度", "覆盖", "update", "initiation", "company"]),
    ("earnings_review", ["业绩", "财报", "季报", "年报", "业绩快报", "earnings", "results"]),
    ("industry_report", ["行业", "产业", "赛道", "专题", "sector", "industry"]),
    ("macro_strategy", ["宏观", "策略", "配置", "market", "macro", "strategy"]),
    ("event_comment", ["事件", "点评", "政策", "公告", "会议", "comment", "policy"]),
]

TOPIC_KEYWORDS = [
    ("rating_or_target_price", ["评级", "目标价", "买入", "增持", "下调", "target price", "rating"]),
    ("earnings_forecast", ["盈利预测", "eps", "收入", "利润", "毛利", "revenue", "profit", "margin"]),
    ("valuation", ["估值", "pe", "pb", "dcf", "倍", "valuation"]),
    ("catalyst", ["催化", "订单", "放量", "新品", "政策", "并购", "m&a", "catalyst"]),
    ("supply_demand", ["供需", "库存", "产能", "价格", "涨价", "降价", "capacity", "price"]),
    ("risk", ["风险", "下行", "竞争", "监管", "uncertainty", "risk"]),
]

RISK_KEYWORDS = [
    ("competition_risk", ["竞争", "替代", "份额", "competition"]),
    ("policy_regulatory_risk", ["监管", "政策", "审批", "regulation", "policy"]),
    ("demand_risk", ["需求", "销量", "订单", "demand"]),
    ("margin_risk", ["毛利", "价格", "成本", "margin", "cost"]),
    ("financing_risk", ["融资", "负债", "现金流", "liquidity", "debt"]),
]

FINANCIAL_METRIC_KEYWORDS = [
    ("revenue", ["收入", "营收", "revenue", "sales"]),
    ("profit", ["利润", "净利", "profit", "net income"]),
    ("eps", ["eps", "每股收益"]),
    ("margin", ["毛利率", "净利率", "margin"]),
    ("valuation_multiple", ["pe", "pb", "ps", "估值", "倍"]),
    ("target_price", ["目标价", "target price"]),
]

REPORT_TYPE_NORMALIZATION = {
    "company_update": "update",
    "earnings_review": "earnings_review",
    "industry_report": "industry",
    "macro_strategy": "strategy",
    "event_comment": "event_comment",
    "unknown": "other",
}

RATING_KEYWORDS = [
    ("buy", ["买入", "强烈推荐", "strong buy", "buy"]),
    ("outperform", ["增持", "推荐", "跑赢", "优于大市", "overweight", "outperform", "positive"]),
    ("hold", ["持有", "hold"]),
    ("neutral", ["中性", "neutral", "market perform"]),
    ("underperform", ["减持", "跑输", "underperform", "underweight"]),
    ("sell", ["卖出", "sell"]),
]

VALUATION_METHOD_KEYWORDS = [
    ("DCF", ["dcf", "现金流折现"]),
    ("SOTP", ["sotp", "分部估值"]),
    ("P/E", ["p/e", "pe", "市盈率"]),
    ("P/B", ["p/b", "pb", "市净率"]),
    ("P/S", ["p/s", "ps", "市销率"]),
    ("EV/EBITDA", ["ev/ebitda", "企业价值"]),
]

FORECAST_LABELS = {
    "eps": ["eps", "每股收益"],
    "revenue": ["revenue", "sales", "收入", "营收"],
    "net_income": ["net income", "净利润", "归母净利润", "利润"],
    "gross_margin": ["gross margin", "毛利率"],
}


def safe_source_part(value: str) -> str:
    safe = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return safe or "unknown"


def _match_keywords(text: str, rules: list[tuple[str, list[str]]]) -> list[str]:
    lowered = text.lower()
    matched: list[str] = []
    for label, keywords in rules:
        if any(keyword.lower() in lowered for keyword in keywords):
            matched.append(label)
    return matched


def _normalize_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _first_float(patterns: list[str], text: str) -> float:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            raw = match.group(1).replace(",", "")
            try:
                return float(raw)
            except ValueError:
                continue
    return 0.0


def _extract_currency(text: str) -> str:
    lowered = text.lower()
    if "hk$" in lowered or "港元" in text or "hkd" in lowered:
        return "HKD"
    if "$" in text or "美元" in text or "usd" in lowered:
        return "USD"
    if "元" in text or "人民币" in text or "cny" in lowered or "rmb" in lowered:
        return "CNY"
    return ""


def _extract_rating(text: str, fallback_sentiment: str) -> str:
    lowered = text.lower()
    for rating, keywords in RATING_KEYWORDS:
        if any(keyword.lower() in lowered for keyword in keywords):
            return rating
    if fallback_sentiment == "positive":
        return "outperform"
    if fallback_sentiment == "negative":
        return "underperform"
    if fallback_sentiment == "neutral":
        return "neutral"
    return "not_rated"


def _extract_analyst_names(text: str) -> list[str]:
    names: list[str] = []
    patterns = [
        r"(?:分析师|研究员|署名)[:：]\s*([^\n。；;]+)",
        r"(?:analysts?|authors?)[:：]\s*([^\n。；;]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        raw = re.split(r"(?:评级|目标价|当前价|核心假设|投资逻辑|rating|target price)[:：]", match.group(1), maxsplit=1, flags=re.IGNORECASE)[0]
        raw = re.sub(r"\b(SAC|SFC|CE)\b.*$", "", raw, flags=re.IGNORECASE)
        for item in re.split(r"[,，、/&和]+", raw):
            name = _normalize_spaces(item)
            if 1 < len(name) <= 40 and not re.search(r"\d", name):
                names.append(name)
    return list(dict.fromkeys(names))


def _extract_label_items(text: str, labels: list[str], *, limit: int = 5) -> list[str]:
    items: list[str] = []
    label_pattern = "|".join(re.escape(label) for label in labels)
    pattern = rf"(?:{label_pattern})[:：]\s*([^\n。]+)"
    for match in re.finditer(pattern, text, flags=re.IGNORECASE):
        raw = match.group(1)
        for part in re.split(r"[；;、,，]", raw):
            item = _normalize_spaces(part)
            item = re.sub(r"^(包括|主要为|为)\s*", "", item)
            if 2 <= len(item) <= 90:
                items.append(item)
            if len(items) >= limit:
                break
        if len(items) >= limit:
            break
    return list(dict.fromkeys(items))


def _keyword_fallback_items(text: str, keywords: list[str], *, prefix: str, limit: int = 3) -> list[str]:
    lowered = text.lower()
    items: list[str] = []
    for keyword in keywords:
        if keyword.lower() in lowered:
            items.append(f"{prefix}: {keyword}")
        if len(items) >= limit:
            break
    return items


def _extract_valuation_method(text: str) -> str:
    lowered = text.lower()
    methods: list[str] = []
    for label, keywords in VALUATION_METHOD_KEYWORDS:
        matched = False
        for keyword in keywords:
            keyword_lower = keyword.lower()
            if re.fullmatch(r"[a-z/]+", keyword_lower):
                pattern = rf"(?<![a-z]){re.escape(keyword_lower)}(?![a-z])"
                matched = bool(re.search(pattern, lowered))
            else:
                matched = keyword_lower in lowered
            if matched:
                break
        if matched:
            methods.append(label)
    return "+".join(methods[:3])


def _extract_target_price_horizon(text: str) -> str:
    lowered = text.lower()
    if re.search(r"12\s*(个月|月|m|months?)", lowered):
        return "12m"
    if re.search(r"6\s*(个月|月|m|months?)", lowered):
        return "6m"
    if re.search(r"3\s*(个月|月|m|months?)", lowered):
        return "3m"
    if "长期" in text or "long term" in lowered:
        return "long_term"
    return "unknown"


def _extract_forecasts(text: str, *, target_price: float, currency: str, horizon: str) -> list[dict[str, Any]]:
    forecasts: list[dict[str, Any]] = []
    if target_price:
        forecasts.append(
            {
                "forecast_type": "target_price",
                "period": horizon,
                "forecast_value": target_price,
                "unit": "price",
                "currency": currency,
            }
        )
    for forecast_type, labels in FORECAST_LABELS.items():
        label_pattern = "|".join(re.escape(label) for label in labels)
        pattern = rf"(20\d{{2}})[E年\s]*(?:[^。；;\n]{{0,36}})(?:{label_pattern})[^0-9\-]{{0,12}}(-?\d+(?:\.\d+)?)"
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            value = float(match.group(2))
            unit = "%" if forecast_type == "gross_margin" else ""
            if forecast_type in {"revenue", "net_income"}:
                unit = "reported_currency"
            forecasts.append(
                {
                    "forecast_type": forecast_type,
                    "period": match.group(1),
                    "forecast_value": value,
                    "unit": unit,
                    "currency": currency if forecast_type in {"revenue", "net_income"} else "",
                }
            )
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, float]] = set()
    for item in forecasts:
        key = (str(item["forecast_type"]), str(item["period"]), float(item["forecast_value"]))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped[:10]


def infer_structured_report_fields(
    *,
    title: str,
    broker: str = "",
    year: str = "",
    month: str = "",
    text: str = "",
    industry: str = "",
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = metadata or {}
    searchable = _normalize_spaces(f"{title}\n{text}")
    classification_text = _normalize_spaces(f"{broker} {title} {industry} {searchable[:4000]}")
    path_viewpoint = dict(metadata.get("viewpoint", {})) if isinstance(metadata.get("viewpoint"), Mapping) else {}
    sentiment = str(path_viewpoint.get("sentiment") or "unknown")
    report_type_raw = str(path_viewpoint.get("report_type") or metadata.get("report_type") or "")
    if not report_type_raw:
        matches = _match_keywords(classification_text, REPORT_TYPE_KEYWORDS)
        report_type_raw = matches[0] if matches else "unknown"
    report_type = REPORT_TYPE_NORMALIZATION.get(report_type_raw, report_type_raw if report_type_raw != "unknown" else "other")
    industry_candidates = list(metadata.get("industry_candidates", [])) if isinstance(metadata.get("industry_candidates"), list) else []
    if not industry and industry_candidates:
        industry = str(industry_candidates[0])
    if not industry:
        industries = _match_keywords(classification_text, INDUSTRY_KEYWORDS)
        industry = industries[0] if industries else ""
    topic_terms = list(metadata.get("evidence_topics", [])) if isinstance(metadata.get("evidence_topics"), list) else []
    topic_terms = list(dict.fromkeys(topic_terms + _match_keywords(classification_text, TOPIC_KEYWORDS)))
    risk_tags = list(metadata.get("risk_tags", [])) if isinstance(metadata.get("risk_tags"), list) else []
    risk_tags = list(dict.fromkeys(risk_tags + _match_keywords(classification_text, RISK_KEYWORDS)))
    financial_metric_tags = list(metadata.get("financial_metric_tags", [])) if isinstance(metadata.get("financial_metric_tags"), list) else []
    financial_metric_tags = list(dict.fromkeys(financial_metric_tags + _match_keywords(classification_text, FINANCIAL_METRIC_KEYWORDS)))

    rating = _extract_rating(classification_text, sentiment)
    target_price = _first_float(
        [
            r"(?:目标价|目标价格|合理价值|合理价|target price|tp)[^0-9$¥￥]{0,16}[$¥￥]?\s*([0-9][0-9,]*(?:\.\d+)?)",
            r"[$¥￥]\s*([0-9][0-9,]*(?:\.\d+)?)\s*(?:目标价|target price)",
        ],
        classification_text,
    )
    current_price = _first_float(
        [
            r"(?:当前价|现价|收盘价|current price|last price)[^0-9$¥￥]{0,16}[$¥￥]?\s*([0-9][0-9,]*(?:\.\d+)?)",
        ],
        classification_text,
    )
    currency = _extract_currency(classification_text)
    horizon = _extract_target_price_horizon(classification_text)
    upside_downside_pct = round(((target_price - current_price) / current_price) * 100, 4) if target_price and current_price else 0.0
    valuation_method = _extract_valuation_method(classification_text)
    analysts = _extract_analyst_names(f"{title}\n{text}")

    core_assumptions = _extract_label_items(classification_text, ["核心假设", "主要假设", "投资逻辑", "核心观点", "core assumptions", "investment thesis"])
    if not core_assumptions:
        core_assumptions = _keyword_fallback_items(classification_text, ["收入", "营收", "margin", "毛利", "订单", "capacity"], prefix="keyword")
    catalysts = _extract_label_items(classification_text, ["催化剂", "催化因素", "短期催化", "catalysts", "drivers"])
    if not catalysts:
        catalysts = _keyword_fallback_items(classification_text, ["订单", "新品", "政策", "并购", "放量", "price"], prefix="catalyst_keyword")
    risks = _extract_label_items(classification_text, ["风险提示", "主要风险", "风险", "risks"])
    if not risks:
        risks = _keyword_fallback_items(classification_text, [tag for _label, terms in RISK_KEYWORDS for tag in terms], prefix="risk_keyword")
    forecasts = _extract_forecasts(classification_text, target_price=target_price, currency=currency, horizon=horizon)

    if target_price:
        viewpoint_type = "target_price"
    elif rating != "not_rated":
        viewpoint_type = "rating"
    elif valuation_method:
        viewpoint_type = "valuation"
    elif risks and sentiment == "negative":
        viewpoint_type = "risk"
    else:
        viewpoint_type = "core_assumption" if core_assumptions else "other"

    statement_parts = []
    if rating != "not_rated":
        statement_parts.append(f"rating={rating}")
    if target_price:
        statement_parts.append(f"target_price={target_price:g}{currency or ''}")
    if report_type != "other":
        statement_parts.append(f"type={report_type}")
    if topic_terms:
        statement_parts.append(f"topics={','.join(topic_terms[:4])}")
    statement = "Structured research-report viewpoint"
    if statement_parts:
        statement += ": " + "; ".join(statement_parts)

    return {
        "report_type": report_type,
        "language": "zh" if re.search(r"[\u4e00-\u9fff]", classification_text) else "en",
        "industry": industry,
        "topic_terms": topic_terms,
        "risk_tags": risk_tags,
        "financial_metric_tags": financial_metric_tags,
        "sentiment": sentiment if sentiment in {"positive", "negative", "neutral"} else "uncertain",
        "rating": rating,
        "target_price": target_price,
        "current_price": current_price,
        "target_price_currency": currency,
        "target_price_horizon": horizon,
        "upside_downside_pct": upside_downside_pct,
        "valuation_method": valuation_method,
        "analyst_names": analysts,
        "core_assumptions": core_assumptions,
        "catalysts": catalysts,
        "risks": risks,
        "forecasts": forecasts,
        "viewpoint_type": viewpoint_type,
        "statement": statement,
        "parser_status": "parsed" if text.strip() else "metadata_only",
        "published_year": year,
        "published_month": month,
    }


def classify_report_metadata(path: Path, root: Path) -> dict[str, Any]:
    relative_text = str(path.relative_to(root))
    searchable = f"{relative_text} {path.stem}"
    industries = _match_keywords(searchable, INDUSTRY_KEYWORDS)
    report_types = _match_keywords(searchable, REPORT_TYPE_KEYWORDS)
    topics = _match_keywords(searchable, TOPIC_KEYWORDS)
    risk_tags = _match_keywords(searchable, RISK_KEYWORDS)
    financial_metric_tags = _match_keywords(searchable, FINANCIAL_METRIC_KEYWORDS)
    lowered = searchable.lower()
    if any(term in lowered for term in ["买入", "增持", "推荐", "看好", "positive", "buy", "overweight", "outperform"]):
        sentiment = "positive"
    elif any(term in lowered for term in ["卖出", "减持", "下调", "看空", "negative", "sell", "underperform"]):
        sentiment = "negative"
    elif any(term in lowered for term in ["中性", "持有", "neutral", "hold"]):
        sentiment = "neutral"
    else:
        sentiment = "unknown"
    return {
        "industry": industries[0] if industries else "",
        "industry_candidates": industries,
        "report_type": report_types[0] if report_types else "unknown",
        "evidence_topics": topics,
        "risk_tags": risk_tags,
        "financial_metric_tags": financial_metric_tags,
        "viewpoint": {
            "sentiment": sentiment,
            "classification_source": "path_and_title_keywords",
            "report_type": report_types[0] if report_types else "unknown",
            "topic_terms": topics,
        },
    }


def infer_report_metadata(path: Path, root: Path) -> dict[str, Any]:
    relative = path.relative_to(root)
    parts = relative.parts
    broker = parts[0] if len(parts) > 1 else "unknown"
    year = ""
    month = ""
    for part in parts:
        if not year and re.fullmatch(r"20\d{2}|19\d{2}", part):
            year = part
            continue
        if year and not month:
            match = re.search(r"(0?[1-9]|1[0-2])", part)
            if match:
                month = match.group(1).zfill(2)
                break
    title = path.stem.strip() or path.name
    classification = classify_report_metadata(path, root)
    return {
        "broker": broker,
        "year": year,
        "month": month,
        "title": title,
        "relative_path": str(relative),
        **classification,
    }


def report_id_for_path(path: Path) -> str:
    digest = hashlib.sha256(str(path.resolve()).encode("utf-8")).hexdigest()[:16]
    return f"rr_{digest}"


def cheap_fingerprint(path: Path, root: Path) -> str:
    stat = path.stat()
    payload = f"{path.relative_to(root)}|{stat.st_size}|{int(stat.st_mtime)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def content_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iter_report_files(root: Path, *, extensions: set[str] | None = None, limit: int = 1000) -> list[Path]:
    extensions = {item.lower() for item in (extensions or DEFAULT_REPORT_EXTENSIONS)}
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in extensions:
            continue
        files.append(path)
        if len(files) >= limit:
            break
    return sorted(files)
