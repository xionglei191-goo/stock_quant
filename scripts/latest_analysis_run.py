from __future__ import annotations

import argparse
from datetime import date, timedelta
import json
from pathlib import Path
import re
import time
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DEFAULT_SYMBOLS = ["600000", "000001", "300750", "600519"]
DEFAULT_US_TICKERS = ["AAPL", "MSFT", "NVDA", "TSLA", "SPY"]
DEFAULT_SEMANTIC_TIMEOUT_SECONDS = 8.0


class ApiClient:
    def __init__(self, base_url: str, *, timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        *,
        role: str = "platform",
        actor: str = "latest_analysis_run",
        allow_error: bool = False,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        data = json.dumps(body or {}).encode("utf-8") if body is not None else None
        request = Request(
            f"{self.base_url}{path}",
            data=data,
            method=method,
            headers={"Content-Type": "application/json", "X-Role": role, "X-Actor": actor},
        )
        try:
            with urlopen(request, timeout=timeout or self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raw = exc.read().decode("utf-8")
            payload = json.loads(raw) if raw else {"success": False, "error": {"message": str(exc)}}
        except Exception as exc:
            payload = {"success": False, "error": {"message": str(exc), "type": type(exc).__name__}}
        if not payload.get("success"):
            if allow_error:
                return {"_error": payload.get("error") or payload}
            raise AssertionError(f"{method} {path} failed: {payload}")
        return payload["data"]


def _security_id(symbol: str) -> str:
    return f"sec_{symbol}"


def _issuer_id(symbol: str) -> str:
    return f"issuer_{symbol}"


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _pct(value: Any) -> str:
    return f"{_safe_float(value) * 100:.2f}%"


def _human_asset_name(label: str) -> str:
    names = {
        "600000": "浦发银行",
        "000001": "平安银行",
        "300750": "宁德时代",
        "600519": "贵州茅台",
        "AAPL": "Apple",
        "MSFT": "Microsoft",
        "NVDA": "NVIDIA",
        "TSLA": "Tesla",
        "SPY": "SPDR S&P 500 ETF",
    }
    return names.get(label, label)


def _clean_research_snippet(value: Any) -> str:
    text = str(value or "").replace("[TRUNCATED_FOR_CITATION_BOUNDARY]", " ")
    text = re.sub(r"\s+", " ", text).strip()
    for pattern in (
        r"^[_\s]*(research_report_citation|report_citation|citation|_citation|local_reference_citation|company_profile_industry_position)\.\s*",
        r"^page[_ -]?\d+[_ -]?(paragraph|para)?[_ -]?\d*[:.\s-]*",
    ):
        text = re.sub(pattern, "", text, flags=re.IGNORECASE).strip()
    return text


def _research_queries_for_assets(assets: list[dict[str, str]] | None) -> list[dict[str, str]]:
    query_by_label = {
        "600000": "600000 Shanghai Pudong Development Bank Pudong Dev Bank net interest margin asset quality risk",
        "000001": "000001 Ping An Bank retail banking non-performing loan net interest margin",
        "300750": "300750 CATL battery energy storage gross margin lithium",
        "600519": "600519 Kweichow Moutai baijiu wholesale price channel inventory",
        "AAPL": "Apple AAPL AI iPhone services revenue gross margin risk",
        "MSFT": "Microsoft MSFT Azure AI cloud capex margin",
        "NVDA": "NVIDIA NVDA GPU ASIC hyperscaler capex HBM",
        "TSLA": "Tesla TSLA EV margin China delivery energy storage",
        "SPY": "S&P 500 SPY US equity strategy AI capex risk",
    }
    queries: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(scope: str, query: str) -> None:
        query = re.sub(r"\s+", " ", query).strip()
        key = query.lower()
        if query and key not in seen:
            seen.add(key)
            queries.append({"scope": scope, "query": query})

    add("theme_ai_infrastructure", "NVIDIA GPU ASIC hyperscaler capex semiconductor AI server")
    add("theme_china_ai_chain", "China semiconductor AI server supply chain GPU")
    for asset in assets or []:
        label = str(asset.get("label") or asset.get("symbol") or asset.get("security_id") or "")
        if not label:
            continue
        add(label, query_by_label.get(label) or f"{label} {_human_asset_name(label)} revenue margin risk")
    return queries[:12]


def _normalize_ashare_symbol(value: Any) -> str:
    text = str(value or "").strip().lower()
    digits = re.sub(r"\D+", "", text)
    return digits[-6:] if len(digits) >= 6 else digits


def _asset_from_ashare_symbol(symbol: str) -> dict[str, str]:
    return {
        "label": symbol,
        "symbol": symbol,
        "security_id": _security_id(symbol),
        "issuer_id": _issuer_id(symbol),
        "source_id": "public_eod_market_data",
        "market": "A",
        "currency": "CNY",
        "industry": "A-share",
    }


def _asset_from_us_ticker(ticker: str) -> dict[str, str]:
    ticker = ticker.strip().upper()
    return {
        "label": ticker,
        "symbol": ticker,
        "security_id": f"security_{ticker.lower()}_us",
        "issuer_id": f"issuer_{ticker.lower()}",
        "source_id": "yahoo_chart_us_eod",
        "market": "U",
        "currency": "USD",
        "industry": "US equity",
    }


def _latest_market_snapshot(client: ApiClient, assets: list[dict[str, str]]) -> list[dict[str, Any]]:
    snapshots: list[dict[str, Any]] = []
    for asset in assets:
        data = client.request(
            "GET",
            "/api/market-data?"
            + urlencode(
                {
                    "security_id": asset["security_id"],
                    "source_id": asset["source_id"],
                    "data_type": "eod",
                    "limit": 1,
                }
            ),
            role="data_engineer",
        )
        rows = data.get("market_data", [])
        if rows:
            row = dict(rows[0])
            row["label"] = asset["label"]
            row["symbol"] = asset["symbol"]
            snapshots.append(row)
    return snapshots


def _return_window(latest_date: str, days: int = 45) -> tuple[str, str]:
    parsed = date.fromisoformat(latest_date)
    return (parsed - timedelta(days=days)).isoformat(), latest_date


def _pull_latest_data(client: ApiClient, symbols: list[str], *, research_root: str, latest_date: str) -> dict[str, Any]:
    start_date = (date.fromisoformat(latest_date) - timedelta(days=30)).isoformat()
    result: dict[str, Any] = {
        "source_boundary": "approved_public_local_free_sources_only",
        "ashare_recent": {},
        "supplemental": {},
        "research_reports": {},
        "errors": [],
    }
    for symbol in symbols:
        exchange = "sse" if symbol.startswith(("5", "6", "9")) else "szse"
        payload = {
            "issuer_id": _issuer_id(symbol),
            "security_id": _security_id(symbol),
            "security_code": symbol,
            "begin_date": start_date,
            "end_date": latest_date,
            "limit": 5,
            "exchange": exchange,
            "include_attachment": False,
        }
        response = client.request("POST", "/api/ingestion/ashare/recent", payload, role="data_engineer", allow_error=True, timeout=20.0)
        result["ashare_recent"][symbol] = response
        if "_error" in response:
            result["errors"].append({"source": "ashare_recent", "symbol": symbol, "error": response["_error"]})

    supplemental_calls = {
        "tencent_valuation_snapshot": {"symbols": symbols, "limit": len(symbols)},
        "eastmoney_research": {"stock_code": symbols[0], "limit": 5},
        "cninfo_announcements": {"stock_code": symbols[0], "start_date": start_date, "end_date": latest_date, "limit": 5},
        "dragon_tiger_list": {"limit": 5},
        "unlock_calendar": {"limit": 5},
    }
    for connector_id, payload in supplemental_calls.items():
        body = {"connector_id": connector_id, **payload}
        response = client.request("POST", "/api/connectors/astock/supplemental/fetch", body, role="data_engineer", allow_error=True, timeout=20.0)
        result["supplemental"][connector_id] = response
        if response.get("_error") or response.get("error"):
            result["errors"].append({"source": "supplemental", "connector_id": connector_id, "error": response.get("_error") or response.get("error")})

    result["research_reports"] = client.request(
        "POST",
        "/api/research-reports",
        {"limit": 200},
        role="data_engineer",
        allow_error=True,
    )
    return result


def _company_intelligence_overview(
    client: ApiClient,
    assets: list[dict[str, str]],
    *,
    limit: int = 10,
) -> dict[str, Any]:
    companies: list[dict[str, Any]] = []
    ready_count = 0
    attention_count = 0
    for asset in assets:
        symbol = str(asset.get("label") or asset.get("symbol") or "").strip()
        if not symbol:
            continue
        response = client.request(
            "GET",
            f"/api/company-intelligence/{symbol}",
            {"limit": limit},
            role="analyst",
            allow_error=True,
            timeout=20.0,
        )
        intelligence = response if isinstance(response, dict) else {}
        relationship_context = intelligence.get("relationships", {}).get("relationship_context", {}) if isinstance(intelligence.get("relationships"), dict) else {}
        section_counts = intelligence.get("section_counts", {}) if isinstance(intelligence.get("section_counts"), dict) else {}
        completeness = intelligence.get("completeness_verdict", {}) if isinstance(intelligence.get("completeness_verdict"), dict) else {}
        data_quality = intelligence.get("data_quality", {}) if isinstance(intelligence.get("data_quality"), dict) else {}
        next_actions = intelligence.get("next_actions") if isinstance(intelligence.get("next_actions"), list) else []
        summary = relationship_context.get("summary", {}) if isinstance(relationship_context.get("summary"), dict) else {}
        coverage_diagnostics = relationship_context.get("coverage_diagnostics", {}) if isinstance(relationship_context.get("coverage_diagnostics"), dict) else {}
        if completeness.get("is_complete"):
            ready_count += 1
        else:
            attention_count += 1
        companies.append(
            {
                "symbol": intelligence.get("symbol") or symbol,
                "status": intelligence.get("status") or "missing",
                "company_counts": {
                    "company_profiles": section_counts.get("company_profiles", 0),
                    "company_events": section_counts.get("company_events", 0),
                    "company_relationships": section_counts.get("company_relationships", 0),
                    "analysis_conclusions": section_counts.get("analysis_conclusions", 0),
                    "simulation_feedback_records": section_counts.get("simulation_feedback_records", 0),
                    "research_reports": section_counts.get("research_reports", 0),
                    "report_viewpoints": section_counts.get("report_viewpoints", 0),
                },
                "relationship_summary": {
                    "industry_related_companies_total": summary.get("industry_related_companies_total", 0),
                    "shareholder_related_companies_total": summary.get("shareholder_related_companies_total", 0),
                    "peer_companies": summary.get("peer_companies", 0),
                    "upstream_companies": summary.get("upstream_companies", 0),
                    "downstream_companies": summary.get("downstream_companies", 0),
                    "approved_ownership_relationships": summary.get("approved_ownership_relationships", 0),
                    "ownership_candidates": summary.get("ownership_candidates", 0),
                },
                "coverage_score": coverage_diagnostics.get("coverage_score", 0),
                "relationship_status": coverage_diagnostics.get("status", ""),
                "next_actions": next_actions[:3],
                "completeness_verdict": completeness,
                "data_quality": {
                    "profile_available": data_quality.get("profile_available", False),
                    "event_timeline_available": data_quality.get("event_timeline_available", False),
                    "relationship_graph_available": data_quality.get("relationship_graph_available", False),
                    "research_results_available": data_quality.get("research_results_available", False),
                    "simulation_feedback_available": data_quality.get("simulation_feedback_available", False),
                },
            }
        )
    companies.sort(key=lambda item: (item.get("status") == "missing", item.get("symbol") or ""))
    return {
        "schema_id": "latest-analysis-company-intelligence-v1",
        "status": "ready" if ready_count else ("watch" if companies else "missing"),
        "company_count": len(companies),
        "ready_count": ready_count,
        "needs_attention_count": attention_count,
        "companies": companies,
        "usage_boundary": "latest_analysis_company_intelligence_overview_is_local_research_only_no_broker_execution",
    }


def _research_evidence_audit(
    client: ApiClient,
    counts: dict[str, Any] | None = None,
    *,
    assets: list[dict[str, str]] | None = None,
    semantic_timeout_seconds: float = DEFAULT_SEMANTIC_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    if counts is None:
        metrics = client.request("GET", "/api/metrics", role="unknown", allow_error=True, timeout=5.0)
        counts = metrics.get("counts", {}) if isinstance(metrics, dict) else {}
    query_plan = _research_queries_for_assets(assets)
    semantic_runs = []
    semantic_candidates: list[dict[str, Any]] = []
    seen_candidates: set[str] = set()
    total_semantic_results = 0
    backend = ""
    for query_item in query_plan:
        semantic = client.request(
            "POST",
            "/api/search/semantic",
            {
                "q": query_item["query"],
                "resource_types": ["research_report", "evidence", "research_answer", "company_position"],
                "include_restricted": True,
                "limit": 8,
            },
            role="analyst",
            allow_error=True,
            timeout=semantic_timeout_seconds,
        )
        semantic_results = semantic.get("results", []) if isinstance(semantic, dict) else []
        total_semantic_results += len(semantic_results)
        if isinstance(semantic, dict) and semantic.get("backend"):
            backend = str(semantic.get("backend") or backend)
        semantic_runs.append(
            {
                "scope": query_item["scope"],
                "query": query_item["query"],
                "status": "failed" if isinstance(semantic, dict) and semantic.get("_error") else "passed",
                "backend": semantic.get("backend", "") if isinstance(semantic, dict) else "",
                "result_count": len(semantic_results),
                "error": semantic.get("_error", {}) if isinstance(semantic, dict) else {},
            }
        )
        for item in semantic_results:
            if item.get("resource_type") not in {"research_report", "evidence", "research_answer", "company_position"}:
                continue
            snippet = _clean_research_snippet(item.get("snippet", ""))
            title = _clean_research_snippet(item.get("title", ""))
            key = f"{item.get('resource_type')}:{item.get('resource_id')}:{snippet[:160]}"
            if key in seen_candidates:
                continue
            seen_candidates.add(key)
            semantic_candidates.append(
                {
                    "query": query_item["query"],
                    "scope": query_item["scope"],
                    "resource_type": item.get("resource_type"),
                    "resource_id": item.get("resource_id"),
                    "title": title,
                    "snippet": snippet,
                    "source_boundary": item.get("source_boundary", ""),
                    "risk_level": item.get("risk_level", ""),
                    "rights_tag": item.get("rights_tag", {}),
                    "score": item.get("score"),
                }
            )
    hotspot = client.request(
        "POST",
        "/api/hotspots/expand",
        {
            "query": "AI semiconductor GPU",
            "seed_chain_id": "chain_demo_electronics",
            "max_depth": 2,
            "include_restricted": True,
            "recall_limit": 20,
        },
        role="analyst",
        allow_error=True,
    )
    recall = hotspot.get("retrieval_recall", {}) if isinstance(hotspot, dict) else {}
    research_opinions = recall.get("research_opinions", []) if isinstance(recall, dict) else []
    research_opinion_samples = []
    for item in research_opinions[:20]:
        research_opinion_samples.append(
            {
                "resource_type": item.get("resource_type"),
                "resource_id": item.get("resource_id"),
                "title": _clean_research_snippet(item.get("title", "")),
                "snippet": _clean_research_snippet(item.get("snippet", "")),
                "source_boundary": item.get("source_boundary", ""),
            }
        )
    semantic_useful = _useful_research_samples(semantic_candidates, limit=40)
    hotspot_useful = _useful_research_samples(research_opinion_samples, limit=8)
    return {
        "status": "passed" if counts.get("research_reports", 0) > 0 and counts.get("evidence", 0) > 0 else "needs_data",
        "counts": {
            "research_reports": counts.get("research_reports", 0),
            "research_report_citation_evidence": counts.get("research_report_citation_evidence", 0),
            "total_evidence": counts.get("evidence", 0),
            "research_answers": counts.get("research_answers", 0),
        },
        "semantic_recall": {
            "status": "passed" if semantic_useful else "needs_review",
            "backend": backend,
            "result_count": total_semantic_results,
            "research_reference_count": len(semantic_candidates),
            "useful_sample_count": len(semantic_useful),
            "query_count": len(query_plan),
            "queries": semantic_runs,
            "samples": semantic_useful,
            "raw_samples": semantic_candidates[:12],
        },
        "hotspot_recall": {
            "status": "passed" if hotspot_useful else "needs_review",
            "research_opinion_count": len(research_opinions),
            "useful_sample_count": len(hotspot_useful),
            "samples": hotspot_useful,
            "raw_samples": research_opinion_samples[:8],
            "error": hotspot.get("_error", {}) if isinstance(hotspot, dict) else {},
        },
        "usage_boundary": "local_research_reports_are_opinion_reference_evidence_only_not_fact_source_training_data_or_trade_signal",
        "training_allowed": False,
        "fact_source_allowed": False,
        "live_trade_signal_allowed": False,
    }


def _days_between(start: str, end: str) -> int:
    try:
        return (date.fromisoformat(end) - date.fromisoformat(start)).days
    except ValueError:
        return 0


def _data_quality_assessment(analysis: dict[str, Any]) -> dict[str, Any]:
    snapshots = analysis.get("latest_snapshot") or []
    latest_market_date = str(analysis.get("latest_market_date") or "")
    latest_by_market: dict[str, str] = {}
    for row in snapshots:
        if not isinstance(row, dict):
            continue
        market = str(row.get("market") or "")
        as_of_date = str(row.get("as_of_date") or "")
        if market and as_of_date:
            latest_by_market[market] = max(latest_by_market.get(market, ""), as_of_date)

    stale_assets: list[dict[str, Any]] = []
    for row in snapshots:
        if not isinstance(row, dict):
            continue
        market = str(row.get("market") or "")
        as_of_date = str(row.get("as_of_date") or "")
        market_latest_date = latest_by_market.get(market, "")
        lag_days = _days_between(as_of_date, market_latest_date) if as_of_date and market_latest_date else 0
        if lag_days > 2:
            stale_assets.append(
                {
                    "label": row.get("label") or row.get("symbol") or row.get("security_id"),
                    "market": market,
                    "as_of_date": as_of_date,
                    "market_latest_date": market_latest_date,
                    "lag_days": lag_days,
                }
            )

    returns = analysis.get("returns") or {}
    insufficient_returns = []
    for label, item in returns.items():
        if not isinstance(item, dict):
            continue
        return_count = int(item.get("return_count") or item.get("observation_count") or 0)
        if return_count < 20:
            insufficient_returns.append({"label": label, "return_count": return_count})

    research_evidence = analysis.get("research_evidence") or {}
    semantic = research_evidence.get("semantic_recall") or {}
    hotspot = research_evidence.get("hotspot_recall") or {}
    useful_evidence_count = len(_useful_research_samples(semantic.get("samples") or [], limit=100)) + len(_useful_research_samples(hotspot.get("samples") or [], limit=100))

    issues: list[dict[str, Any]] = []
    if stale_assets:
        issues.append(
            {
                "severity": "high",
                "code": "stale_within_market",
                "issue": "stale_within_market",
                "message": "部分标的落后于同市场最新行情日期，不能进入组合层比较。",
                "affected_assets": stale_assets[:20],
            }
        )
    unique_market_dates = sorted({value for value in latest_by_market.values() if value})
    if len(unique_market_dates) > 1:
        issues.append(
            {
                "severity": "medium",
                "code": "cross_market_date_mismatch",
                "issue": "cross_market_date_mismatch",
                "message": "A股与美股最新行情日期不同；这是跨市场时区/交易日差异，组合比较需按市场分别解释。",
                "latest_by_market": latest_by_market,
            }
        )
    if insufficient_returns:
        issues.append(
            {
                "severity": "medium",
                "code": "short_return_window",
                "issue": "short_return_window",
                "message": "部分标的可用收益样本不足，波动和回撤统计稳定性有限。",
                "affected_assets": insufficient_returns[:20],
            }
        )
    if useful_evidence_count < 3:
        issues.append(
            {
                "severity": "high",
                "code": "weak_research_evidence",
                "issue": "weak_research_evidence",
                "message": "研报召回有效片段不足，不能把观点层输出当作投资结论。",
                "useful_evidence_count": useful_evidence_count,
            }
        )
    if research_evidence.get("fact_source_allowed") is False:
        issues.append(
            {
                "severity": "medium",
                "code": "research_is_opinion_only",
                "issue": "research_is_opinion_only",
                "message": "本地研报只允许作为观点参考，不允许替代公告、财报或行情事实源。",
            }
        )

    blocking = [item for item in issues if item["severity"] == "high"]
    return {
        "status": "needs_review" if blocking else "usable_with_warnings" if issues else "usable",
        "latest_by_market": latest_by_market,
        "stale_asset_count": len(stale_assets),
        "insufficient_return_asset_count": len(insufficient_returns),
        "useful_research_evidence_count": useful_evidence_count,
        "issues": issues,
        "decision_readiness": "not_actionable" if blocking else "research_only",
    }


def _useful_research_samples(samples: list[dict[str, Any]], *, limit: int = 5) -> list[dict[str, Any]]:
    blocked_terms = [
        "analyst certification",
        "important disclosures",
        "research analyst affiliations",
        "does and seeks to do business",
        "investment banking relationships",
        "see appendix",
        "for analyst certification",
        "important regulatory disclosures",
        "the 720:",
        "weekly kickstart",
        "strategy data gallery",
        "institutional 13f positioning",
        "global exposure guide",
        "positions of active long-only managers",
    ]
    evidence_markers = [
        " we ",
        " our ",
        " expect",
        " target",
        " driven",
        " growth",
        " margin",
        " risk",
        " demand",
        " price",
        " revenue",
        " capex",
        " investment",
        " supply",
        " wholesale",
        " interest",
        " loan",
        " roe",
        " decreased",
        " increased",
        " supports",
        " positive",
        " weaker",
        " strong",
        "公司",
        "产业链",
        "收入",
        "利润",
        "价格",
        "风险",
        "需求",
        "增长",
    ]
    useful: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in samples:
        if not isinstance(item, dict):
            continue
        snippet = _clean_research_snippet(item.get("snippet") or "")
        title = _clean_research_snippet(item.get("title") or "")
        lower = f"{title} {snippet}".lower()
        if len(snippet) < 60:
            continue
        if any(term in lower for term in blocked_terms):
            continue
        if re.fullmatch(r"[\w\s|:.,'’&()/-]{0,180}", snippet) and len(snippet.split()) < 14:
            continue
        if len(re.findall(r"[A-Za-z\u4e00-\u9fff]", snippet)) < 40:
            continue
        padded_lower = f" {lower} "
        if not any(marker in padded_lower for marker in evidence_markers):
            continue
        key = f"{item.get('resource_id')}:{snippet[:120]}"
        if key in seen:
            continue
        seen.add(key)
        useful.append(
            {
                "query": item.get("query", ""),
                "scope": item.get("scope", ""),
                "resource_type": item.get("resource_type"),
                "resource_id": item.get("resource_id"),
                "title": title,
                "snippet": snippet,
                "source_boundary": item.get("source_boundary", ""),
                "risk_level": item.get("risk_level", ""),
                "score": item.get("score"),
            }
        )
        if len(useful) >= limit:
            break
    return useful


def _all_useful_research_samples(analysis: dict[str, Any], *, limit: int = 200) -> list[dict[str, Any]]:
    research_evidence = analysis.get("research_evidence") or {}
    semantic = research_evidence.get("semantic_recall") or {}
    hotspot = research_evidence.get("hotspot_recall") or {}
    return _useful_research_samples((semantic.get("samples") or []) + (hotspot.get("samples") or []), limit=limit)


def _research_evidence_themes(sample: dict[str, Any]) -> list[str]:
    text = f"{sample.get('title', '')} {sample.get('snippet', '')}".lower()
    theme_rules = [
        ("AI/算力", [" ai ", "gpu", "server", "cloud", "hbm", "asic", "算力"]),
        ("Capex", ["capex", "capital expenditure", "investment"]),
        ("收入/利润率", ["revenue", "margin", "gross", "opm", "收入", "利润"]),
        ("价格/渠道", ["price", "wholesale", "channel", "moutai", "价格", "批价", "渠道"]),
        ("银行/NIM", ["interest", "loan", "roe", "asset quality", "nim", "不良", "息差"]),
        ("风险", ["risk", "tariff", "weaker", "decreased", "decline", "风险", "下滑"]),
        ("需求/供应链", ["demand", "supply", "supply chain", "shipment", "需求", "供应链"]),
    ]
    padded = f" {text} "
    themes = []
    for label, needles in theme_rules:
        if any(needle in padded for needle in needles):
            themes.append(label)
    return themes[:4]


def _research_samples_by_scope(analysis: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    by_scope: dict[str, list[dict[str, Any]]] = {}
    for sample in _all_useful_research_samples(analysis, limit=200):
        scope = str(sample.get("scope") or "")
        if not scope:
            continue
        by_scope.setdefault(scope, []).append(sample)
    return by_scope


def _ranked_evidence_samples_for_decision(analysis: dict[str, Any], recommendations: list[dict[str, Any]], *, limit: int = 6) -> list[dict[str, Any]]:
    samples = _all_useful_research_samples(analysis, limit=200)
    if not samples:
        return []
    preferred_scopes = [str(item.get("label") or "") for item in recommendations[:6] if item.get("label")]
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add_matching(scope: str) -> None:
        for sample in samples:
            if str(sample.get("scope") or "") != scope:
                continue
            key = f"{sample.get('resource_id')}:{sample.get('snippet', '')[:120]}"
            if key in seen:
                continue
            seen.add(key)
            selected.append(sample)
            return

    for scope in preferred_scopes:
        add_matching(scope)
        if len(selected) >= limit:
            return selected
    for scope in ("theme_ai_infrastructure", "theme_china_ai_chain"):
        add_matching(scope)
        if len(selected) >= limit:
            return selected
    for sample in samples:
        key = f"{sample.get('resource_id')}:{sample.get('snippet', '')[:120]}"
        if key in seen:
            continue
        seen.add(key)
        selected.append(sample)
        if len(selected) >= limit:
            break
    return selected


def _evidence_covered_scopes(analysis: dict[str, Any]) -> set[str]:
    return set(_research_samples_by_scope(analysis))


def _evidence_coverage_summary(analysis: dict[str, Any], recommendations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    samples_by_scope = _research_samples_by_scope(analysis)
    rows: list[dict[str, Any]] = []
    for item in recommendations:
        label = str(item.get("label") or "")
        samples = samples_by_scope.get(label, [])
        themes: list[str] = []
        for sample in samples:
            for theme in _research_evidence_themes(sample):
                if theme not in themes:
                    themes.append(theme)
        top_sample = samples[0] if samples else {}
        rows.append(
            {
                "label": label,
                "name": item.get("name", ""),
                "status": "direct_opinion_evidence" if samples else "missing_direct_evidence",
                "direct_sample_count": len(samples),
                "themes": themes[:4],
                "top_resource_id": top_sample.get("resource_id", ""),
                "top_snippet": _clean_research_snippet(top_sample.get("snippet", ""))[:220] if top_sample else "",
                "source_boundary": top_sample.get("source_boundary", "") if top_sample else "",
            }
        )
    return rows


def _evidence_watchlist(
    analysis: dict[str, Any],
    recommendations: list[dict[str, Any]],
    displayed_labels: set[str],
    *,
    limit: int = 6,
) -> list[dict[str, Any]]:
    samples_by_scope = _research_samples_by_scope(analysis)
    recommendation_by_label = {str(item.get("label") or ""): item for item in recommendations}
    rows: list[dict[str, Any]] = []
    for label, samples in samples_by_scope.items():
        if label.startswith("theme_") or label in displayed_labels or label not in recommendation_by_label:
            continue
        item = recommendation_by_label[label]
        themes: list[str] = []
        for sample in samples:
            for theme in _research_evidence_themes(sample):
                if theme not in themes:
                    themes.append(theme)
        top_sample = samples[0] if samples else {}
        rows.append(
            {
                "label": label,
                "name": item.get("name", ""),
                "stance": item.get("stance", ""),
                "action": item.get("action", ""),
                "as_of_date": item.get("as_of_date", ""),
                "total_return_pct": item.get("total_return_pct", 0),
                "candidate_weight_pct": item.get("candidate_weight_pct", 0),
                "direct_sample_count": len(samples),
                "themes": themes[:4],
                "top_resource_id": top_sample.get("resource_id", ""),
                "top_snippet": _clean_research_snippet(top_sample.get("snippet", ""))[:220] if top_sample else "",
                "source_boundary": top_sample.get("source_boundary", "") if top_sample else "",
                "reason": "研报有直接观点，但行情/组合模拟未进入前台候选。",
            }
        )
    rows.sort(key=lambda item: (int(item.get("direct_sample_count") or 0), abs(_safe_float(item.get("total_return_pct")))), reverse=True)
    return rows[:limit]


def _asset_rows_for_decision(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    assets = analysis.get("assets") or []
    returns = analysis.get("returns") or {}
    optimizer = analysis.get("portfolio_optimizer") or {}
    weights = optimizer.get("candidate_weights") or {}
    latest_snapshot = analysis.get("latest_snapshot") or []
    snapshot_by_label = {str(row.get("label") or row.get("symbol") or row.get("security_id")): row for row in latest_snapshot if isinstance(row, dict)}
    posterior_returns = optimizer.get("posterior_returns") or {}

    rows: list[dict[str, Any]] = []
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        label = str(asset.get("label") or asset.get("symbol") or asset.get("security_id"))
        security_id = str(asset.get("security_id") or "")
        ret = returns.get(label) or {}
        if ret.get("_error"):
            continue
        total_return = _safe_float(ret.get("total_return"))
        volatility = max(0.000001, _safe_float(ret.get("volatility")))
        max_drawdown = _safe_float(ret.get("max_drawdown"))
        weight = _safe_float(weights.get(security_id))
        posterior = _safe_float(posterior_returns.get(security_id))
        return_count = int(ret.get("return_count") or 0)
        momentum_score = total_return / volatility if volatility else 0.0
        rows.append(
            {
                "label": label,
                "name": _human_asset_name(label),
                "security_id": security_id,
                "market": asset.get("market") or "",
                "source_id": asset.get("source_id") or "",
                "as_of_date": snapshot_by_label.get(label, {}).get("as_of_date", ""),
                "close": snapshot_by_label.get(label, {}).get("close"),
                "total_return": total_return,
                "volatility": volatility,
                "max_drawdown": max_drawdown,
                "return_count": return_count,
                "candidate_weight": weight,
                "posterior_return": posterior,
                "momentum_score": momentum_score,
            }
        )
    return rows


def _supplemental_snapshot_by_label(data_pull: dict[str, Any]) -> dict[str, dict[str, Any]]:
    supplemental = data_pull.get("supplemental") or {}
    valuation = supplemental.get("tencent_valuation_snapshot") or {}
    snapshots: dict[str, dict[str, Any]] = {}
    for doc in valuation.get("documents") or []:
        if not isinstance(doc, dict):
            continue
        metadata = doc.get("metadata") or {}
        label = _normalize_ashare_symbol(metadata.get("symbol") or doc.get("title"))
        close = metadata.get("close")
        published_at = str(doc.get("published_at") or "")
        if len(published_at) >= 8 and published_at[:8].isdigit():
            as_of_date = f"{published_at[:4]}-{published_at[4:6]}-{published_at[6:8]}"
        else:
            as_of_date = published_at[:10]
        if not label or close in {None, ""}:
            continue
        snapshots[label] = {
            "label": label,
            "as_of_date": as_of_date,
            "close": _safe_float(close),
            "source_id": doc.get("source_id") or "tencent_valuation_snapshot",
            "source_boundary": metadata.get("source_boundary") or doc.get("source_boundary") or "manual_reference_or_supplemental_research_only",
            "automation_allowed": bool(metadata.get("automation_allowed", False)),
            "title": doc.get("title", ""),
        }
    return snapshots


def _attach_supplemental_observations(analysis: dict[str, Any], data_pull: dict[str, Any]) -> dict[str, Any]:
    snapshots = _supplemental_snapshot_by_label(data_pull)
    if not snapshots:
        return analysis
    latest_snapshot = analysis.get("latest_snapshot") or []
    official_by_label = {
        str(row.get("label") or row.get("symbol") or ""): row
        for row in latest_snapshot
        if isinstance(row, dict) and row.get("market") == "A"
    }
    observations = []
    for label, supplemental in sorted(snapshots.items()):
        official = official_by_label.get(label)
        if not official:
            continue
        official_close = _safe_float(official.get("close"))
        supplemental_close = _safe_float(supplemental.get("close"))
        price_change = (supplemental_close / official_close - 1.0) if official_close else 0.0
        observations.append(
            {
                "label": label,
                "official_as_of_date": official.get("as_of_date", ""),
                "official_close": official_close,
                "supplemental_as_of_date": supplemental.get("as_of_date", ""),
                "supplemental_close": supplemental_close,
                "supplemental_source_id": supplemental.get("source_id", ""),
                "source_boundary": supplemental.get("source_boundary", ""),
                "automation_allowed": supplemental.get("automation_allowed", False),
                "price_change_since_official_close": round(price_change, 6),
                "price_change_since_official_close_pct": round(price_change * 100, 2),
            }
        )
    return {
        **analysis,
        "supplemental_market_observations": {
            "status": "available" if observations else "missing",
            "usage_boundary": "manual_reference_or_supplemental_research_only_not_official_eod_not_trade_signal",
            "observations": observations,
        },
    }


def _recommendation_for_row(row: dict[str, Any], data_quality: dict[str, Any]) -> tuple[str, str, list[str]]:
    reasons: list[str] = []
    risks: list[str] = []
    total_return = _safe_float(row.get("total_return"))
    drawdown = _safe_float(row.get("max_drawdown"))
    volatility = _safe_float(row.get("volatility"))
    weight = _safe_float(row.get("candidate_weight"))
    return_count = int(row.get("return_count") or 0)
    latest_by_market = data_quality.get("latest_by_market", {}) if isinstance(data_quality.get("latest_by_market"), dict) else {}
    market_latest_date = str(latest_by_market.get(str(row.get("market") or "")) or "")
    market_lag_days = (
        _days_between(str(row.get("as_of_date")), market_latest_date)
        if row.get("as_of_date") and market_latest_date
        else 0
    )

    if data_quality.get("decision_readiness") == "not_actionable":
        if market_lag_days > 2:
            action = "stale_data_watch"
            stance = "数据滞后"
            risks.append("标的落后于同市场最新行情日期，组合层不能使用")
        elif total_return > 0.08 and drawdown < 0.1:
            action = "research_watch_positive"
            stance = "积极观察"
            reasons.append("单市场短期行情表现较强，但组合门禁未通过")
            risks.append("组合层数据质量门禁未通过")
        elif total_return < -0.04 or drawdown > 0.1:
            action = "risk_watch"
            stance = "风险观察"
            reasons.append("单市场短期表现偏弱或回撤较大")
            risks.append("组合层数据质量门禁未通过")
        else:
            action = "watch"
            stance = "观察"
            risks.append("组合层数据质量门禁未通过")
    elif total_return > 0.06 and drawdown < 0.08 and weight > 0.05:
        action = "research_long_candidate"
        stance = "研究候选"
        reasons.append("区间收益、回撤和模拟权重同时靠前")
    elif total_return > 0.02 and weight > 0.02:
        action = "watch"
        stance = "观察"
        reasons.append("价格动量为正，但还需要更多基本面和事件证据")
    elif total_return < -0.04 or drawdown > 0.1:
        action = "avoid_or_reduce_in_simulation"
        stance = "回避/降低模拟权重"
        reasons.append("区间收益或回撤表现偏弱")
    else:
        action = "neutral"
        stance = "中性"
        reasons.append("行情信号不够明确")

    if not reasons and action == "watch":
        reasons.append("当前只适合作为观察标的")
    if return_count < 20:
        risks.append("收益样本少于 20 个交易日")
    if volatility > 0.025:
        risks.append("短期波动较高")
    if market_lag_days > 2:
        risks.append(f"行情较同市场最新日期滞后 {market_lag_days} 天")

    return action, stance, risks


def _decision_summary(analysis: dict[str, Any], data_quality: dict[str, Any]) -> dict[str, Any]:
    rows = _asset_rows_for_decision(analysis)
    ranked = sorted(
        rows,
        key=lambda item: (
            _safe_float(item.get("candidate_weight")),
            _safe_float(item.get("posterior_return")),
            _safe_float(item.get("total_return")),
        ),
        reverse=True,
    )
    recommendations: list[dict[str, Any]] = []
    supplemental_by_label = {
        str(item.get("label")): item
        for item in (analysis.get("supplemental_market_observations") or {}).get("observations", [])
        if isinstance(item, dict) and item.get("label")
    }
    for row in ranked:
        action, stance, risks = _recommendation_for_row(row, data_quality)
        supplemental = supplemental_by_label.get(row["label"], {})
        supplemental_note = ""
        if supplemental:
            supplemental_note = (
                f"补充快照 {supplemental.get('supplemental_as_of_date')}: "
                f"{_safe_float(supplemental.get('supplemental_close')):.2f}, "
                f"较官方日线 { _safe_float(supplemental.get('price_change_since_official_close_pct')):+.2f}%"
            )
        recommendations.append(
            {
                "label": row["label"],
                "name": row["name"],
                "security_id": row["security_id"],
                "market": row["market"],
                "action": action,
                "stance": stance,
                "as_of_date": row["as_of_date"],
                "close": row["close"],
                "total_return": row["total_return"],
                "total_return_pct": round(row["total_return"] * 100, 2),
                "volatility_pct": round(row["volatility"] * 100, 2),
                "max_drawdown_pct": round(row["max_drawdown"] * 100, 2),
                "candidate_weight_pct": round(row["candidate_weight"] * 100, 2),
                "posterior_return_pct": round(row["posterior_return"] * 100, 2),
                "reasons": [
                    f"区间收益 {_pct(row['total_return'])}",
                    f"最大回撤 {_pct(row['max_drawdown'])}",
                    f"模拟权重 {_pct(row['candidate_weight'])}",
                ]
                + ([supplemental_note] if supplemental_note else []),
                "risks": risks,
                "evidence_status": "opinion_only" if analysis.get("research_evidence", {}).get("fact_source_allowed") is False else "mixed",
                "supplemental_snapshot": supplemental,
            }
        )

    evidence_samples = _ranked_evidence_samples_for_decision(analysis, recommendations, limit=6)
    covered_scopes = _evidence_covered_scopes(analysis)
    for item in recommendations[:6]:
        label = str(item.get("label") or "")
        if label and label not in covered_scopes:
            item.setdefault("risks", []).append("未召回到该标的的直接研报样本")
    evidence_coverage = _evidence_coverage_summary(analysis, recommendations[:6])
    evidence_watchlist = _evidence_watchlist(
        analysis,
        recommendations,
        {str(item.get("label") or "") for item in recommendations[:6]},
        limit=6,
    )
    top = recommendations[:3]
    red_flags = [issue["message"] for issue in data_quality.get("issues", [])]
    if not evidence_samples:
        red_flags.append("研报召回有效片段不足，目前主要依赖行情和组合模拟，结论可信度有限。")

    if data_quality.get("decision_readiness") == "not_actionable":
        headline = "当前系统只能做研究浏览，不能给出可执行投资建议。"
        issue_codes = {str(issue.get("code") or "") for issue in data_quality.get("issues", [])}
        positive = [item for item in recommendations if item["action"] == "research_watch_positive"]
        stale = [item for item in recommendations if item["action"] == "stale_data_watch"]
        if positive:
            if "cross_market_date_mismatch" in issue_codes:
                conclusion = f"单市场层面可先跟踪 {', '.join(item['label'] for item in positive[:4])}；跨市场日期不同，需按市场分别解释。"
            elif "stale_within_market" in issue_codes:
                conclusion = f"单市场层面可先跟踪 {', '.join(item['label'] for item in positive[:4])}；但部分标的落后于本市场最新日期，需补齐后再进入组合比较。"
            elif "weak_research_evidence" in issue_codes:
                conclusion = f"单市场层面可先跟踪 {', '.join(item['label'] for item in positive[:4])}；但研报事实证据门禁未通过，不能形成可执行建议。"
            else:
                conclusion = f"单市场层面可先跟踪 {', '.join(item['label'] for item in positive[:4])}；但仍需人工复核阻塞项后再进入组合决策。"
        elif stale:
            observed = [item for item in stale if item.get("supplemental_snapshot")]
            if observed:
                conclusion = f"A股官方日线滞后，但可用补充快照观察 {', '.join(item['label'] for item in observed[:4])}；仍需补齐正式日线后再比较。"
            else:
                conclusion = f"A股标的 {', '.join(item['label'] for item in stale[:4])} 行情滞后，先补齐日线后再比较。"
        else:
            conclusion = "数据质量或证据质量仍有阻塞项，建议先修复行情时效和研报召回质量。"
    elif top:
        names = "、".join(item["label"] for item in top)
        headline = f"当前可作为研究候选的是 {names}，但仍仅限模拟和人工复核。"
        conclusion = "结论来自短期行情、模拟组合和本地观点证据，不包含真实交易授权。"
    else:
        headline = "当前没有足够信息形成研究候选。"
        conclusion = "缺少有效收益样本或组合模拟结果。"

    return {
        "status": "needs_review" if data_quality.get("decision_readiness") == "not_actionable" else "research_only",
        "headline": headline,
        "conclusion": conclusion,
        "top_recommendations": recommendations[:6],
        "red_flags": red_flags[:8],
        "evidence_samples": evidence_samples,
        "evidence_coverage": evidence_coverage,
        "evidence_watchlist": evidence_watchlist,
        "usage_boundary": "research_summary_only_not_investment_advice_not_trade_signal",
    }


def _run_analysis(
    client: ApiClient,
    assets: list[dict[str, str]],
    latest_snapshot: list[dict[str, Any]],
    *,
    suffix: str,
    semantic_timeout_seconds: float = DEFAULT_SEMANTIC_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    latest_date = max(row["as_of_date"] for row in latest_snapshot)
    start_date, end_date = _return_window(latest_date)
    returns: dict[str, Any] = {}
    assets_by_label = {asset["label"]: asset for asset in assets}
    for asset in assets:
        response = client.request(
            "GET",
            "/api/market-data/returns?"
            + urlencode(
                {
                    "security_id": asset["security_id"],
                    "source_id": asset["source_id"],
                    "data_type": "eod",
                    "start_date": start_date,
                    "end_date": end_date,
                    "limit": 80,
                }
            ),
            role="CIO",
            allow_error=True,
        )
        returns[asset["label"]] = response

    valid_symbols = [asset["label"] for asset in assets if not returns.get(asset["label"], {}).get("_error") and returns.get(asset["label"], {}).get("return_count", 0) > 0]
    securities = []
    history = {}
    for symbol in valid_symbols:
        asset = assets_by_label[symbol]
        row = returns[symbol]
        securities.append(
            {
                "security_id": asset["security_id"],
                "market_weight": round(1.0 / max(1, len(valid_symbols)), 6),
                "volatility": max(0.01, _safe_float(row.get("volatility"))),
                "market": asset["market"],
                "industry": asset["industry"],
            }
        )
        history[asset["security_id"]] = [item["return"] for item in row.get("returns", [])][-20:]

    optimizer: dict[str, Any] = {}
    forward: dict[str, Any] = {}
    valuation: dict[str, Any] = {}
    if valid_symbols:
        proposal_id = f"pfp_latest_{suffix}"
        views = [
            {
                "security_id": assets_by_label[symbol]["security_id"],
                "expected_return": _safe_float(returns[symbol].get("total_return")),
                "confidence": 0.65,
            }
            for symbol in valid_symbols
        ]
        optimizer = client.request(
            "POST",
            "/api/portfolio/optimize",
            {
                "proposal_id": proposal_id,
                "risk_aversion": 2.5,
                "tau": 0.05,
                "securities": securities,
                "views": views,
                "constraints": {"max_weight": 0.45, "market_budget": {"A": 1.0, "U": 1.0}},
                "return_history": history,
            },
            role="CIO",
        )
        valuation_by_source = {}
        for source_id in sorted({assets_by_label[symbol]["source_id"] for symbol in valid_symbols}):
            source_symbols = [symbol for symbol in valid_symbols if assets_by_label[symbol]["source_id"] == source_id]
            valuation_by_source[source_id] = client.request(
                "POST",
                "/api/portfolio/valuation",
                {
                    "as_of_date": latest_date,
                    "source_id": source_id,
                    "cash": 100000.0 if source_id == "public_eod_market_data" else 10000.0,
                    "currency": "CNY" if source_id == "public_eod_market_data" else "USD",
                    "holdings": [
                        {"security_id": assets_by_label[symbol]["security_id"], "shares": 1000 if assets_by_label[symbol]["market"] == "A" else 10}
                        for symbol in source_symbols[:6]
                    ],
                    "groups": {assets_by_label[symbol]["security_id"]: {"industry": assets_by_label[symbol]["industry"]} for symbol in source_symbols},
                },
                role="CIO",
            )
        valuation = valuation_by_source
        forward = client.request(
            "POST",
            "/api/portfolio/forward-report",
            {
                "proposal_id": proposal_id,
                "start_date": start_date,
                "end_date": end_date,
                "benchmark_weights": {assets_by_label[symbol]["security_id"]: round(1.0 / len(valid_symbols), 8) for symbol in valid_symbols},
            },
            role="CIO",
            allow_error=True,
        )

    hotspot = client.request(
        "POST",
        "/api/hotspots/expand",
        {"query": "GPU AI", "seed_chain_id": "chain_demo_electronics", "max_depth": 2},
        role="analyst",
        allow_error=True,
    )
    dashboard = client.request("GET", "/api/dashboard/ceo", role="CEO", allow_error=True, timeout=15.0)
    dashboard_counts = dashboard.get("counts", {}) if isinstance(dashboard, dict) else {}
    # /api/metrics includes heavier governance scans; dashboard counts are enough for the
    # latest-analysis evidence summary and avoid turning transient metrics timeouts into
    # false "zero research data" conclusions.
    metrics_counts = dict(dashboard_counts)
    research_evidence = _research_evidence_audit(client, metrics_counts, assets=assets, semantic_timeout_seconds=semantic_timeout_seconds)
    company_intelligence = _company_intelligence_overview(client, assets, limit=min(10, len(assets) or 10))
    report_id = f"opr_latest_{suffix}"
    operating_report = client.request(
        "POST",
        "/api/operating-reports",
        {
            "report_id": report_id,
            "period": latest_date,
            "owner": "latest_analysis_run",
            "metrics": {
                "latest_market_date": latest_date,
                "analyzed_symbol_count": len(valid_symbols),
                "latest_analysis_total_return_avg": round(
                    sum(_safe_float(returns[s].get("total_return")) for s in valid_symbols) / max(1, len(valid_symbols)),
                    8,
                ),
            },
        },
        role="CEO",
        allow_error=True,
    )
    board_pack = {}
    if not operating_report.get("_error"):
        published = client.request(
            "POST",
            f"/api/operating-reports/{report_id}/publish",
            {"approver_role": "CEO", "user": "latest_analysis_run", "comment": "Latest local analysis run."},
            role="CEO",
            allow_error=True,
        )
        board_pack = client.request(
            "POST",
            f"/api/operating-reports/{report_id}/board-pack",
            {"format": "markdown", "include_content": False},
            role="CEO",
            allow_error=True,
        )
        operating_report = {"draft": operating_report, "published": published}

    return {
        "latest_market_date": latest_date,
        "window": {"start_date": start_date, "end_date": end_date},
        "latest_snapshot": latest_snapshot,
        "assets": assets,
        "returns": returns,
        "valid_symbols": valid_symbols,
        "portfolio_optimizer": optimizer,
        "portfolio_valuation": valuation,
        "portfolio_forward": forward,
        "hotspot": hotspot,
        "research_evidence": research_evidence,
        "company_intelligence": company_intelligence,
        "dashboard_counts": dashboard_counts,
        "metrics_counts": metrics_counts,
        "operating_report": operating_report,
        "board_pack": board_pack,
    }


def _enrich_analysis(analysis: dict[str, Any], data_pull: dict[str, Any]) -> dict[str, Any]:
    analysis = _attach_supplemental_observations(analysis, data_pull)
    data_quality = _data_quality_assessment(analysis)
    decision_summary = _decision_summary(analysis, data_quality)
    return {
        **analysis,
        "data_quality": data_quality,
        "decision_summary": decision_summary,
    }


def _markdown_report(result: dict[str, Any]) -> str:
    analysis = result["analysis"]
    decision = analysis.get("decision_summary") or {}
    data_quality = analysis.get("data_quality") or {}
    lines = [
        "# 最新本机分析报告",
        "",
        f"- 生成时间: {result['generated_at']}",
        f"- 最新行情日期: {analysis['latest_market_date']}",
        f"- 分析窗口: {analysis['window']['start_date']} 至 {analysis['window']['end_date']}",
        f"- 数据边界: {result['production_boundary']}",
        f"- 结论状态: {decision.get('status', '-')}",
        "",
        "## 结论",
        "",
        f"- {decision.get('headline', '暂无结论')}",
        f"- {decision.get('conclusion', '')}",
        f"- 数据质量: {data_quality.get('status', '-')}, 决策就绪: {data_quality.get('decision_readiness', '-')}",
        "",
        "## 候选与风险",
        "",
        "| 标的 | 动作 | 日期 | 区间收益 | 最大回撤 | 模拟权重 | 主要风险 |",
        "| --- | --- | --- | ---: | ---: | ---: | --- |",
    ]
    for item in decision.get("top_recommendations", []):
        lines.append(
            f"| {item.get('label')} | {item.get('stance')} | {item.get('as_of_date', '')} | "
            f"{_safe_float(item.get('total_return')):.2%} | {_safe_float(item.get('max_drawdown_pct')):.2f}% | "
            f"{_safe_float(item.get('candidate_weight_pct')):.2f}% | {'; '.join(item.get('risks') or ['-'])} |"
        )
    lines.extend(["", "## 关键红旗", ""])
    for flag in decision.get("red_flags", []) or ["暂无"]:
        lines.append(f"- {flag}")
    evidence_coverage = decision.get("evidence_coverage") or []
    if evidence_coverage:
        lines.extend(
            [
                "",
                "## 研报覆盖概览",
                "",
                "| 标的 | 状态 | 样本数 | 主题 | 代表片段 | 边界 |",
                "| --- | --- | ---: | --- | --- | --- |",
            ]
        )
        for item in evidence_coverage:
            themes = ", ".join(item.get("themes") or ["-"])
            snippet = _clean_research_snippet(item.get("top_snippet") or "")[:180].replace("|", "/")
            status = "有直接观点证据" if item.get("status") == "direct_opinion_evidence" else "缺直接研报样本"
            lines.append(
                f"| {item.get('label')} | {status} | {int(item.get('direct_sample_count') or 0)} | "
                f"{themes.replace('|', '/')} | {snippet or '-'} | {item.get('source_boundary', '') or '-'} |"
            )
    evidence_watchlist = decision.get("evidence_watchlist") or []
    if evidence_watchlist:
        lines.extend(
            [
                "",
                "## 研报观察池",
                "",
                "| 标的 | 研报样本 | 主题 | 区间收益 | 模拟权重 | 代表片段 |",
                "| --- | ---: | --- | ---: | ---: | --- |",
            ]
        )
        for item in evidence_watchlist:
            themes = ", ".join(item.get("themes") or ["-"]).replace("|", "/")
            snippet = _clean_research_snippet(item.get("top_snippet") or "")[:180].replace("|", "/")
            lines.append(
                f"| {item.get('label')} | {int(item.get('direct_sample_count') or 0)} | {themes} | "
                f"{_safe_float(item.get('total_return_pct')):.2f}% | {_safe_float(item.get('candidate_weight_pct')):.2f}% | "
                f"{snippet or '-'} |"
            )
    evidence_samples = decision.get("evidence_samples") or []
    if evidence_samples:
        lines.extend(
            [
                "",
                "## 研报证据样本",
                "",
                "| 范围 | 类型 | 标题 | 摘要 | 边界 |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for item in evidence_samples[:6]:
            title = _clean_research_snippet(item.get("title") or item.get("resource_id") or "-")
            snippet = _clean_research_snippet(item.get("snippet") or "")
            title = title[:80].replace("|", "/")
            snippet = snippet[:220].replace("|", "/")
            lines.append(
                f"| {item.get('scope') or '-'} | {item.get('resource_type') or '-'} | {title} | {snippet} | "
                f"{item.get('source_boundary', '')} |"
            )
    company_intelligence = analysis.get("company_intelligence") or {}
    company_intelligence_rows = company_intelligence.get("companies") or []
    if company_intelligence_rows:
        lines.extend(
            [
                "",
                "## 公司情报链路",
                "",
                "| 公司 | 状态 | 关系摘要 | 研究/反馈 | 下一步 |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for item in company_intelligence_rows:
            relationship_summary = item.get("relationship_summary") or {}
            counts = item.get("company_counts") or {}
            relationship_text = (
                f"产业链 {int(relationship_summary.get('industry_related_companies_total', 0))}"
                f" / 股东 {int(relationship_summary.get('shareholder_related_companies_total', 0))}"
            )
            research_feedback_text = f"结论 {int(counts.get('analysis_conclusions', 0))} / 反馈 {int(counts.get('simulation_feedback_records', 0))}"
            next_actions = item.get("next_actions") or []
            next_action = next_actions[0] if next_actions else {}
            next_text = next_action.get("label") or next_action.get("action") or "-"
            if next_action.get("endpoint"):
                next_text = f"{next_text} · {next_action['endpoint']}"
            lines.append(
                f"| {item.get('symbol')} | {item.get('status', '-')} | {relationship_text} | {research_feedback_text} | {next_text} |"
            )
    supplemental = analysis.get("supplemental_market_observations") or {}
    observations = supplemental.get("observations") or []
    if observations:
        lines.extend(
            [
                "",
                "## A股补充观察",
                "",
                "| 股票 | 官方日线 | 官方收盘 | 补充日期 | 补充价格 | 变化 | 边界 |",
                "| --- | --- | ---: | --- | ---: | ---: | --- |",
            ]
        )
        for item in observations:
            lines.append(
                f"| {item.get('label')} | {item.get('official_as_of_date')} | {_safe_float(item.get('official_close')):.2f} | "
                f"{item.get('supplemental_as_of_date')} | {_safe_float(item.get('supplemental_close')):.2f} | "
                f"{_safe_float(item.get('price_change_since_official_close_pct')):+.2f}% | {item.get('source_boundary', '')} |"
            )
    lines.extend(
        [
            "",
            "## 行情摘要",
            "",
            "| 股票 | 日期 | 收盘 | 区间收益 | 波动 | 最大回撤 |",
            "| --- | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    snapshot_by_symbol = {row.get("label") or row["security_id"]: row for row in analysis["latest_snapshot"]}
    for symbol in analysis["valid_symbols"]:
        snap = snapshot_by_symbol.get(symbol, {})
        ret = analysis["returns"].get(symbol, {})
        lines.append(
            f"| {symbol} | {snap.get('as_of_date', '')} | {_safe_float(snap.get('close')):.2f} | "
            f"{_safe_float(ret.get('total_return')):.2%} | {_safe_float(ret.get('volatility')):.2%} | {_safe_float(ret.get('max_drawdown')):.2%} |"
        )
    lines.extend(["", "## 组合模拟", ""])
    optimizer = analysis.get("portfolio_optimizer") or {}
    weights = optimizer.get("candidate_weights", {})
    if weights:
        for security_id, weight in sorted(weights.items(), key=lambda item: item[1], reverse=True):
            lines.append(f"- {security_id}: {float(weight):.2%}")
    forward = analysis.get("portfolio_forward") or {}
    if forward and not forward.get("_error"):
        lines.append(f"- 组合窗口收益: {_safe_float(forward.get('total_return')):.2%}")
        lines.append(f"- 组合波动: {_safe_float(forward.get('volatility')):.2%}")
        lines.append(f"- 组合最大回撤: {_safe_float(forward.get('max_drawdown')):.2%}")
    lines.extend(["", "## 新增数据", ""])
    pull = result["data_pull"]
    created = sum(len(v.get("created", [])) for v in pull.get("ashare_recent", {}).values() if isinstance(v, dict))
    skipped = sum(len(v.get("skipped", [])) for v in pull.get("ashare_recent", {}).values() if isinstance(v, dict))
    lines.append(f"- A 股公告: 新增 {created}，已存在/跳过 {skipped}")
    reports = pull.get("research_reports", {})
    lines.append(f"- 本地研报资产: count={reports.get('count', reports.get('indexed_count', 0))}")
    research_evidence = analysis.get("research_evidence", {})
    research_counts = research_evidence.get("counts", {})
    lines.append(
        f"- 研报观点证据: reports={research_counts.get('research_reports', 0)}, "
        f"citation_evidence={research_counts.get('research_report_citation_evidence', 0)}, "
        f"semantic_status={research_evidence.get('semantic_recall', {}).get('status', '-')}, "
        f"semantic_useful={research_evidence.get('semantic_recall', {}).get('useful_sample_count', 0)}, "
        f"hotspot_status={research_evidence.get('hotspot_recall', {}).get('status', '-')}"
    )
    for connector_id, row in pull.get("supplemental", {}).items():
        lines.append(f"- {connector_id}: count={row.get('count', 0)}, error={bool(row.get('_error') or row.get('error'))}")
    lines.extend(["", "## 风险提示", ""])
    counts = analysis.get("metrics_counts", {})
    lines.append(f"- open_alerts={counts.get('open_alerts', 0)}, open_exceptions={counts.get('open_exceptions', 0)}")
    lines.append("- 本报告只用于本机研究和模拟组合，不启用真实券商或自动下单。")
    return "\n".join(lines) + "\n"


def run_latest_analysis(
    base_url: str,
    *,
    symbols: list[str],
    us_tickers: list[str],
    research_root: str,
    output_dir: Path,
    timeout: float,
    semantic_timeout_seconds: float = DEFAULT_SEMANTIC_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    client = ApiClient(base_url, timeout=timeout)
    suffix = str(int(time.time()))
    health = client.request("GET", "/api/health", role="unknown")
    assets = [_asset_from_ashare_symbol(symbol) for symbol in symbols] + [_asset_from_us_ticker(ticker) for ticker in us_tickers]
    latest_snapshot = _latest_market_snapshot(client, assets)
    if not latest_snapshot:
        raise RuntimeError("no latest market data found for requested symbols")
    latest_date = max(row["as_of_date"] for row in latest_snapshot)
    data_pull = _pull_latest_data(client, symbols, research_root=research_root, latest_date=latest_date)
    analysis = _enrich_analysis(
        _run_analysis(client, assets, latest_snapshot, suffix=suffix, semantic_timeout_seconds=semantic_timeout_seconds),
        data_pull,
    )
    result = {
        "status": "passed",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "base_url": base_url,
        "symbols": symbols,
        "us_tickers": us_tickers,
        "health": health,
        "data_pull": data_pull,
        "analysis": analysis,
        "production_boundary": "local_research_and_simulated_portfolio_only_no_live_broker_no_automatic_order_execution",
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "latest-analysis.json"
    md_path = output_dir / "latest-analysis.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(_markdown_report(result), encoding="utf-8")
    result["artifacts"] = {"json": str(json_path), "markdown": str(md_path)}
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Pull latest approved data and generate the latest local analysis report.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    parser.add_argument("--us-tickers", default=",".join(DEFAULT_US_TICKERS))
    parser.add_argument("--research-root", default="/data/local/research_reports")
    parser.add_argument("--output-dir", default="artifacts/latest-analysis")
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--semantic-timeout-seconds", type=float, default=DEFAULT_SEMANTIC_TIMEOUT_SECONDS)
    args = parser.parse_args()
    symbols = [item.strip() for item in args.symbols.split(",") if item.strip()]
    us_tickers = [item.strip().upper() for item in args.us_tickers.split(",") if item.strip()]
    result = run_latest_analysis(
        args.base_url,
        symbols=symbols,
        us_tickers=us_tickers,
        research_root=args.research_root,
        output_dir=Path(args.output_dir),
        timeout=args.timeout,
        semantic_timeout_seconds=args.semantic_timeout_seconds,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
