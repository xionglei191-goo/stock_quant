"""Pure context-assembly and prompt helpers for the personal ask assistant.

Stateless functions only: the ``SystemService.ask`` facade owns IO (store
reads via ``company_intelligence``, LLM gateway call, audit) and delegates the
context shaping, prompt construction and rule-based fallback here, per
AGENTS.md service-module boundary.

Layering discipline (project red line): facts/events precede opinions, and
opinions precede simulation feedback. The assembled context therefore lists the
fact layer (company profile, latest market snapshot, financial snapshot,
recent events) before the opinion layer (research report viewpoints), and every
viewpoint carries its ``opinion_only_not_fact_source`` boundary. Research
reports are never presented as a fact/truth source.

No new data source and no new metric is introduced here: the input is the
payload already produced by ``SystemService.company_intelligence``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

# Keep prompt context bounded so a single question never ships an unbounded
# blob to the gateway. These are display/prompt caps, not data limits.
MAX_VIEWPOINTS = 5
MAX_EVENTS = 6
MAX_FINANCIAL_METRICS = 8

USAGE_BOUNDARY = (
    "personal_research_assistant_only_no_broker_execution_"
    "reports_are_opinion_reference_not_fact_or_training_source"
)

SYSTEM_INSTRUCTION = (
    "你是一个个人投研助手。只依据下面提供的【已知资料】用中文回答问题，"
    "不要编造资料里没有的数字或事实。资料分事实层（公司资料、行情、财务、事件）"
    "和观点层（研报观点）：事实层可作为依据；研报观点只是参考立场，"
    "不能当作事实真相或交易指令。如果资料不足以回答，直说“现有资料不足”，"
    "并指出还缺哪一类信息。不要给出下单、买卖时点等真实交易建议——本系统仅做纸面研究。"
)


def _clean(value: Any) -> str:
    text = "" if value is None else str(value).strip()
    return " ".join(text.split())


def _first_present(mapping: Mapping[str, Any], keys: Sequence[str]) -> str:
    for key in keys:
        value = _clean(mapping.get(key))
        if value:
            return value
    return ""


def _section(payload: Mapping[str, Any], name: str) -> dict[str, Any]:
    section = payload.get(name)
    return section if isinstance(section, Mapping) else {}


def _rows(section: Mapping[str, Any], name: str) -> list[dict[str, Any]]:
    rows = section.get(name)
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, Mapping)]


def build_context(intelligence: Mapping[str, Any]) -> dict[str, Any]:
    """Shape ``company_intelligence`` output into a compact, layered context.

    Returns a plain dict with a ``fact_layer`` block, an ``opinion_layer`` list
    of viewpoints (each carrying its rights boundary), the union of referenced
    ``evidence_ids``, a ``resolved`` flag and a ``coverage`` summary. Fact layer
    is always listed before opinion layer to honour the fact-before-opinion red
    line.
    """
    profile_section = _section(intelligence, "company_profile")
    facts_section = _section(intelligence, "facts_and_events")
    research_section = _section(intelligence, "research_results")

    profile = profile_section.get("profile") if isinstance(profile_section.get("profile"), Mapping) else {}
    issuer = profile_section.get("issuer") if isinstance(profile_section.get("issuer"), Mapping) else {}
    profile = profile or {}
    issuer = issuer or {}

    display_name = _first_present(profile, ["display_name", "legal_name"]) or _first_present(issuer, ["display_name", "legal_name"])
    fact_layer: dict[str, Any] = {
        "display_name": display_name,
        "sector": _first_present(profile, ["sector"]),
        "industry": _first_present(profile, ["industry"]),
        "business_summary": _first_present(profile, ["business_summary"]),
        "latest_market_snapshot": facts_section.get("latest_market_snapshot") if isinstance(facts_section.get("latest_market_snapshot"), Mapping) else {},
        "latest_market_freshness": facts_section.get("latest_market_freshness") if isinstance(facts_section.get("latest_market_freshness"), Mapping) else {},
        "latest_financial_snapshot": facts_section.get("latest_financial_snapshot") if isinstance(facts_section.get("latest_financial_snapshot"), Mapping) else {},
        "financial_metrics": _rows(facts_section, "financial_metrics")[:MAX_FINANCIAL_METRICS],
        "recent_events": (_rows(facts_section, "company_events") + _rows(facts_section, "disclosure_events"))[:MAX_EVENTS],
    }

    evidence_ids: list[str] = []
    seen_evidence: set[str] = set()

    opinion_layer: list[dict[str, Any]] = []
    for viewpoint in _rows(research_section, "report_viewpoints")[:MAX_VIEWPOINTS]:
        entry = {
            "statement": _clean(viewpoint.get("statement")),
            "stance": _clean(viewpoint.get("stance")),
            "rating": _clean(viewpoint.get("rating")),
            "target_price": viewpoint.get("target_price"),
            "catalysts": [_clean(item) for item in viewpoint.get("catalysts", []) if _clean(item)],
            "risks": [_clean(item) for item in viewpoint.get("risks", []) if _clean(item)],
            "rights_boundary": "opinion_only_not_fact_source",
        }
        opinion_layer.append(entry)
        for evidence_id in viewpoint.get("evidence_ids", []):
            cleaned = _clean(evidence_id)
            if cleaned and cleaned not in seen_evidence:
                seen_evidence.add(cleaned)
                evidence_ids.append(cleaned)

    for evidence_row in _rows(facts_section, "evidence"):
        cleaned = _clean(evidence_row.get("evidence_id"))
        if cleaned and cleaned not in seen_evidence:
            seen_evidence.add(cleaned)
            evidence_ids.append(cleaned)

    coverage = profile_section.get("coverage_summary") if isinstance(profile_section.get("coverage_summary"), Mapping) else {}
    resolution = intelligence.get("resolution") if isinstance(intelligence.get("resolution"), Mapping) else {}

    return {
        "symbol": _clean(intelligence.get("symbol")),
        "resolved": bool(resolution.get("matched")) and _clean(intelligence.get("status")) == "available",
        "fact_layer": fact_layer,
        "opinion_layer": opinion_layer,
        "evidence_ids": evidence_ids,
        "coverage": dict(coverage),
        "usage_boundary": USAGE_BOUNDARY,
    }


def _render_market_snapshot(snapshot: Mapping[str, Any]) -> str:
    if not snapshot:
        return "（无行情记录）"
    parts = []
    as_of = _clean(snapshot.get("as_of_date"))
    if as_of:
        parts.append(f"截至 {as_of}")
    for label, key in (("收盘", "close"), ("涨跌", "adjusted_close"), ("成交量", "volume"), ("成交额", "amount")):
        value = snapshot.get(key)
        if value not in (None, "", 0, 0.0):
            parts.append(f"{label} {value}")
    return "；".join(parts) if parts else "（行情字段为空）"


def build_prompt(question: str, context: Mapping[str, Any]) -> str:
    """Compose the user-turn prompt: instruction + layered known facts + question."""
    fact_layer = context.get("fact_layer") if isinstance(context.get("fact_layer"), Mapping) else {}
    opinion_layer = context.get("opinion_layer") if isinstance(context.get("opinion_layer"), list) else []
    lines: list[str] = [SYSTEM_INSTRUCTION, "", "【已知资料】"]

    symbol = _clean(context.get("symbol"))
    name = _clean(fact_layer.get("display_name"))
    header = " ".join(part for part in [name, f"({symbol})" if symbol else ""] if part).strip()
    lines.append(f"标的：{header or symbol or '未指定'}")

    if not context.get("resolved"):
        lines.append("（本地库未匹配到该标的的结构化记录，以下资料可能为空）")

    sector = _clean(fact_layer.get("sector"))
    industry = _clean(fact_layer.get("industry"))
    if sector or industry:
        lines.append(f"行业：{'/'.join(part for part in [sector, industry] if part)}")
    business = _clean(fact_layer.get("business_summary"))
    if business:
        lines.append(f"业务简介：{business}")

    lines.append("")
    lines.append("事实层——最新行情：" + _render_market_snapshot(fact_layer.get("latest_market_snapshot") or {}))

    financial = fact_layer.get("latest_financial_snapshot") or {}
    if isinstance(financial, Mapping) and financial:
        lines.append("事实层——最新财务快照：" + ", ".join(f"{k}={v}" for k, v in list(financial.items())[:8]))

    events = fact_layer.get("recent_events") or []
    if events:
        lines.append("事实层——近期事件：")
        for event in events:
            when = _clean(event.get("occurred_at"))
            title = _first_present(event, ["title", "event_type", "summary"])
            lines.append(f"  - {when} {title}".rstrip())

    if opinion_layer:
        lines.append("")
        lines.append("观点层——研报观点（仅供参考，不是事实真相）：")
        for viewpoint in opinion_layer:
            statement = _clean(viewpoint.get("statement"))
            rating = _clean(viewpoint.get("rating"))
            stance = _clean(viewpoint.get("stance"))
            tag = "/".join(part for part in [stance, rating] if part)
            lines.append(f"  - [{tag or '观点'}] {statement}".rstrip())

    lines.append("")
    lines.append(f"【问题】{_clean(question)}")
    return "\n".join(lines)


def rule_based_answer(question: str, context: Mapping[str, Any]) -> str:
    """Deterministic fallback used when the LLM gateway is not configured.

    It never fabricates: it just reflects back the facts and opinions that are
    on hand so the user still gets a useful, sourced summary offline.
    """
    fact_layer = context.get("fact_layer") if isinstance(context.get("fact_layer"), Mapping) else {}
    opinion_layer = context.get("opinion_layer") if isinstance(context.get("opinion_layer"), list) else []
    name = _clean(fact_layer.get("display_name")) or _clean(context.get("symbol")) or "该标的"

    if not context.get("resolved"):
        return (
            f"现有资料不足：本地库没有匹配到「{_clean(context.get('symbol')) or question}」的结构化记录。"
            "可以先导入该标的的公司资料、行情或研报，再来提问。"
        )

    lines = [f"关于{name}，根据本地已知资料："]
    snapshot = fact_layer.get("latest_market_snapshot") or {}
    if snapshot:
        lines.append("- 最新行情：" + _render_market_snapshot(snapshot))
    business = _clean(fact_layer.get("business_summary"))
    if business:
        lines.append(f"- 业务：{business}")
    events = fact_layer.get("recent_events") or []
    if events:
        first = events[0]
        lines.append(f"- 最近事件：{_clean(first.get('occurred_at'))} {_first_present(first, ['title', 'event_type', 'summary'])}".rstrip())
    if opinion_layer:
        vp = opinion_layer[0]
        lines.append(f"- 研报观点（仅参考）：{_clean(vp.get('statement'))}")

    if len(lines) == 1:
        lines.append("- 目前只匹配到标的身份，尚无行情/财务/研报明细。")
    lines.append("（LLM 未配置，以上为本地资料直出，未做自然语言推理。）")
    return "\n".join(lines)
