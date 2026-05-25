from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
from typing import Any, Mapping


DEFAULT_DSN = "postgresql://ai_quant:ai_quant_dev_password@127.0.0.1:15432/ai_quant"
DEFAULT_OUTPUT = "artifacts/research-report-asset-binding.json"

GENERIC_TERMS = {
    "AI",
    "API",
    "CEO",
    "CFO",
    "CPI",
    "CPU",
    "ETF",
    "EV",
    "FY",
    "GDP",
    "GPU",
    "HK",
    "IPO",
    "JPM",
    "MS",
    "OW",
    "PC",
    "PDF",
    "Q",
    "SEC",
    "TAM",
    "US",
}

COMPANY_ALIASES = {
    "AAPL": ["Apple", "Apple Inc", "苹果"],
    "MSFT": ["Microsoft", "微软"],
    "NVDA": ["NVIDIA", "Nvidia"],
    "TSLA": ["Tesla", "特斯拉"],
    "SPY": ["SPDR S&P 500", "S&P 500 ETF", "SPY"],
    "300750": ["宁德时代", "CATL"],
    "600519": ["贵州茅台", "Kweichow Moutai", "Moutai"],
    "000001": ["平安银行", "Ping An Bank"],
    "600000": ["浦发银行", "Shanghai Pudong Development Bank", "Pudong Development Bank"],
}

TOPIC_RULES = {
    "ai_compute": ["ai", "agentic", "gpu", "nvidia", "accelerator", "cloud", "算力", "人工智能"],
    "capex": ["capex", "capital expenditure", "data center", "数据中心", "资本开支"],
    "margin": ["margin", "gross margin", "profitability", "毛利", "利润率"],
    "revenue_growth": ["revenue", "sales", "growth", "demand", "收入", "营收", "增长", "需求"],
    "risk": ["risk", "headwind", "tariff", "weak", "decline", "风险", "压力", "下滑"],
    "valuation": ["valuation", "target price", "pe", "估值", "目标价"],
    "financial_metrics": ["eps", "ebit", "cash flow", "roe", "nim", "资产质量", "息差"],
}


def _connect(dsn: str) -> Any:
    try:
        import psycopg  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:
        raise RuntimeError("psycopg is required. Run inside the app container or install psycopg[binary].") from exc
    return psycopg.connect(dsn)


def _write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value:
        try:
            loaded = json.loads(value)
            return dict(loaded) if isinstance(loaded, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _safe_identifier(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", value.strip()).strip("_").lower()


def _normalize_title(value: Any) -> str:
    text = str(value or "")
    text = text.replace("，", ",").replace("（", "(").replace("）", ")")
    return re.sub(r"\s+", " ", text).strip()


def _token_pattern(token: str) -> re.Pattern[str]:
    escaped = re.escape(token)
    if re.fullmatch(r"\d{6}", token):
        return re.compile(rf"(?<!\d){escaped}(?!\d)")
    return re.compile(rf"(?<![A-Za-z0-9]){escaped}(?:\.[A-Za-z]{{1,4}})?(?![A-Za-z0-9])", re.IGNORECASE)


def _topic_tags(text: str) -> list[str]:
    lowered = f" {text.lower()} "
    tags = []
    for topic, needles in TOPIC_RULES.items():
        if any(needle.lower() in lowered for needle in needles):
            tags.append(topic)
    return tags


def _sentiment(text: str) -> str:
    lowered = f" {text.lower()} "
    positive = sum(1 for token in ["positive", "strong", "better", "beat", "upgrade", "growth", "improving", "利好", "上调", "强劲"] if token in lowered)
    negative = sum(1 for token in ["negative", "weak", "risk", "miss", "downgrade", "decline", "pressure", "利空", "下调", "疲弱", "压力"] if token in lowered)
    return "positive" if positive > negative else "negative" if negative > positive else "mixed"


def _risk_tags(text: str) -> list[str]:
    lowered = f" {text.lower()} "
    rules = {
        "capex_pressure": ["capex", "capital expenditure", "资本开支"],
        "margin_pressure": ["margin pressure", "gross margin", "毛利", "利润率"],
        "tariff_policy": ["tariff", "关税"],
        "demand_slowdown": ["weak demand", "slowdown", "decline", "需求疲软", "下滑"],
        "valuation_risk": ["valuation", "target price", "估值"],
    }
    return [label for label, needles in rules.items() if any(needle in lowered for needle in needles)]


def _financial_metric_tags(text: str) -> list[str]:
    lowered = f" {text.lower()} "
    rules = {
        "revenue": ["revenue", "sales", "收入", "营收"],
        "margin": ["margin", "gross margin", "毛利", "利润率"],
        "eps": ["eps", "earnings per share"],
        "ebit": ["ebit", "operating income"],
        "cash_flow": ["cash flow", "free cash flow", "现金流"],
        "roe": ["roe"],
        "nim": ["nim", "net interest margin", "息差"],
    }
    return [label for label, needles in rules.items() if any(needle in lowered for needle in needles)]


def _fetch_all(cursor: Any, sql: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    cursor.execute(sql, params)
    return [tuple(row) for row in cursor.fetchall()]


def _load_securities(cursor: Any, *, market: str = "", tickers: set[str] | None = None) -> list[dict[str, Any]]:
    clauses = ["s.collection = 'securities'", "COALESCE(s.payload->>'status', 'active') = 'active'"]
    params: list[Any] = []
    if market:
        clauses.append("s.payload->>'market' = %s")
        params.append(market)
    rows = _fetch_all(
        cursor,
        f"""
        SELECT
            s.item_id,
            s.payload,
            i.payload
        FROM ai_quant.records AS s
        LEFT JOIN ai_quant.records AS i
          ON i.collection = 'issuers'
         AND i.item_id = s.payload->>'issuer_id'
        WHERE {' AND '.join(clauses)}
        """,
        tuple(params),
    )
    by_ticker: dict[str, dict[str, Any]] = {}
    for item_id, security_payload, issuer_payload in rows:
        sec = _payload(security_payload)
        issuer = _payload(issuer_payload)
        ticker = str(sec.get("ticker") or "").strip().upper()
        if not ticker or ticker in GENERIC_TERMS:
            continue
        if tickers and ticker not in tickers:
            continue
        current = {
            "security_id": str(sec.get("security_id") or item_id),
            "issuer_id": str(sec.get("issuer_id") or ""),
            "ticker": ticker,
            "market": str(sec.get("market") or ""),
            "exchange": str(sec.get("exchange") or ""),
            "legal_name": str(issuer.get("legal_name") or sec.get("ticker") or ticker),
            "aliases": [str(item) for item in (issuer.get("aliases") or []) if str(item).strip()],
        }
        existing = by_ticker.get(ticker)
        if existing is None:
            by_ticker[ticker] = current
            continue
        # Prefer the IDs used by Yahoo/TDX market data and seeded company positions.
        if current["security_id"].endswith("_us") or current["security_id"].startswith("sec_"):
            by_ticker[ticker] = current
    return list(by_ticker.values())


def _load_positions(cursor: Any, security_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not security_ids:
        return {}
    rows = _fetch_all(
        cursor,
        """
        SELECT item_id, payload
        FROM ai_quant.records
        WHERE collection = 'company_positions'
          AND payload->>'security_id' = ANY(%s)
        ORDER BY item_id
        """,
        (security_ids,),
    )
    positions: dict[str, dict[str, Any]] = {}
    for item_id, payload in rows:
        doc = _payload(payload)
        security_id = str(doc.get("security_id") or "")
        if security_id and security_id not in positions:
            positions[security_id] = {"position_id": str(item_id), **doc}
    return positions


def _asset_matchers(securities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    matchers = []
    for sec in securities:
        ticker = str(sec["ticker"]).upper()
        terms = [ticker]
        terms.extend(COMPANY_ALIASES.get(ticker, []))
        legal_name = str(sec.get("legal_name") or "")
        cleaned_name = re.sub(r"\b(Common Stock|Ordinary Shares|Class A|Inc\.?|Corporation|Corp\.?|Ltd\.?|Limited)\b", "", legal_name, flags=re.IGNORECASE)
        if cleaned_name and cleaned_name.upper() != ticker:
            terms.append(cleaned_name.strip())
        terms.extend(str(item) for item in sec.get("aliases") or [])
        normalized_terms = []
        seen = set()
        for term in terms:
            term = _normalize_title(term)
            if len(term) < 2 or term.lower() in seen:
                continue
            seen.add(term.lower())
            normalized_terms.append(term)
        matchers.append({**sec, "terms": normalized_terms})
    return matchers


def _matches_for_text(text: str, matchers: list[dict[str, Any]], *, max_matches: int) -> list[dict[str, Any]]:
    matches = []
    for matcher in matchers:
        matched_terms = []
        for term in matcher["terms"]:
            if _token_pattern(str(term).upper()).search(text) if re.fullmatch(r"[A-Za-z0-9]{1,8}", str(term)) else re.search(re.escape(str(term)), text, flags=re.IGNORECASE):
                matched_terms.append(term)
        if not matched_terms:
            continue
        confidence = 0.95 if matcher["ticker"] in {term.upper() for term in matched_terms} else 0.82
        matches.append(
            {
                "security_id": matcher["security_id"],
                "issuer_id": matcher["issuer_id"],
                "ticker": matcher["ticker"],
                "market": matcher["market"],
                "exchange": matcher["exchange"],
                "legal_name": matcher["legal_name"],
                "matched_terms": matched_terms[:5],
                "confidence": confidence,
                "method": "title_ticker_alias_rule",
            }
        )
    matches.sort(key=lambda item: (item["confidence"], len(item["matched_terms"])), reverse=True)
    deduped = []
    seen = set()
    for item in matches:
        if item["security_id"] in seen:
            continue
        seen.add(item["security_id"])
        deduped.append(item)
        if len(deduped) >= max_matches:
            break
    return deduped


def _binding_for_match(match: Mapping[str, Any], positions: Mapping[str, dict[str, Any]]) -> dict[str, Any]:
    position = positions.get(str(match.get("security_id") or ""), {})
    return {
        **dict(match),
        "position_id": position.get("position_id", ""),
        "chain_id": position.get("chain_id", ""),
        "node_ids": position.get("node_ids", []),
        "position_role": position.get("role", ""),
    }


def _update_payload(cursor: Any, collection: str, item_id: str, payload: Mapping[str, Any]) -> None:
    cursor.execute(
        """
        UPDATE ai_quant.records
        SET payload = %s::jsonb,
            updated_at = now()
        WHERE collection = %s
          AND item_id = %s
        """,
        (json.dumps(payload, ensure_ascii=False, sort_keys=True), collection, item_id),
    )


def build_research_report_asset_binding(args: argparse.Namespace) -> dict[str, Any]:
    started_at = datetime.now(timezone.utc).isoformat()
    target_tickers = {item.strip().upper() for item in str(args.tickers or "").split(",") if item.strip()}
    updated_reports = []
    updated_documents = 0
    updated_evidence = 0
    unmatched_samples = []

    with _connect(args.dsn) as connection:
        with connection.cursor() as cursor:
            securities = _load_securities(cursor, market=args.market, tickers=target_tickers or None)
            positions = _load_positions(cursor, [item["security_id"] for item in securities])
            matchers = _asset_matchers(securities)
            reports = _fetch_all(
                cursor,
                """
                SELECT item_id, payload
                FROM ai_quant.records
                WHERE collection = 'research_reports'
                ORDER BY COALESCE(payload->>'indexed_at', ''), item_id
                LIMIT %s
                """,
                (args.limit,),
            )
            for item_id, raw_payload in reports:
                report = _payload(raw_payload)
                text = _normalize_title(f"{report.get('title', '')} {report.get('file_name', '')}")
                matches = [_binding_for_match(item, positions) for item in _matches_for_text(text, matchers, max_matches=args.max_matches_per_report)]
                if not matches:
                    if len(unmatched_samples) < 20:
                        unmatched_samples.append({"report_id": report.get("report_id") or item_id, "title": report.get("title", "")})
                    continue
                document_id = str(report.get("document_id") or "")
                primary = matches[0]
                topic_tags = _topic_tags(text)
                risk_tags = _risk_tags(text)
                financial_metric_tags = _financial_metric_tags(text)
                report_update = {
                    **report,
                    "asset_matches": matches,
                    "asset_binding": {
                        "status": "matched",
                        "matched_at": datetime.now(timezone.utc).isoformat(),
                        "method": "title_ticker_alias_rule",
                        "match_count": len(matches),
                    },
                    "security_id": primary["security_id"] if len(matches) == 1 else str(report.get("security_id") or ""),
                    "issuer_id": primary["issuer_id"] if len(matches) == 1 else str(report.get("issuer_id") or ""),
                    "chain_id": primary.get("chain_id", ""),
                    "node_ids": primary.get("node_ids", []),
                    "evidence_topics": topic_tags,
                    "risk_tags": risk_tags,
                    "financial_metric_tags": financial_metric_tags,
                    "viewpoint": {
                        "sentiment": _sentiment(text),
                        "topics": topic_tags,
                        "risks": risk_tags,
                        "financial_metrics": financial_metric_tags,
                    },
                }
                if not args.dry_run:
                    _update_payload(cursor, "research_reports", str(item_id), report_update)
                evidence_rows = _fetch_all(
                    cursor,
                    """
                    SELECT item_id, payload
                    FROM ai_quant.records
                    WHERE collection = 'evidence'
                      AND payload->>'document_id' = %s
                    """,
                    (document_id,),
                )
                evidence_count_for_report = 0
                for evidence_item_id, raw_evidence in evidence_rows:
                    evidence = _payload(raw_evidence)
                    evidence_text = _normalize_title(f"{evidence.get('canonical_text', '')} {evidence.get('span_text', '')}")
                    merged_text = f"{text} {evidence_text}"
                    evidence_topics = _topic_tags(merged_text)
                    evidence_update = {
                        **evidence,
                        "assets": matches,
                        "security_id": primary["security_id"] if len(matches) == 1 else "",
                        "issuer_id": primary["issuer_id"] if len(matches) == 1 else "",
                        "chain_id": primary.get("chain_id", ""),
                        "node_ids": primary.get("node_ids", []),
                        "evidence_topics": evidence_topics,
                        "risk_tags": _risk_tags(merged_text),
                        "financial_metric_tags": _financial_metric_tags(merged_text),
                        "viewpoint": {
                            "sentiment": _sentiment(merged_text),
                            "topics": evidence_topics,
                        },
                    }
                    if not args.dry_run:
                        _update_payload(cursor, "evidence", str(evidence_item_id), evidence_update)
                    evidence_count_for_report += 1
                if document_id:
                    document_rows = _fetch_all(
                        cursor,
                        "SELECT item_id, payload FROM ai_quant.records WHERE collection = 'documents' AND item_id = %s",
                        (document_id,),
                    )
                    for document_item_id, raw_document in document_rows:
                        document = _payload(raw_document)
                        document_update = {
                            **document,
                            "asset_matches": matches,
                            "security_id": primary["security_id"] if len(matches) == 1 else str(document.get("security_id") or ""),
                            "issuer_id": primary["issuer_id"] if len(matches) == 1 else str(document.get("issuer_id") or ""),
                            "chain_id": primary.get("chain_id", ""),
                            "node_ids": primary.get("node_ids", []),
                        }
                        if not args.dry_run:
                            _update_payload(cursor, "documents", str(document_item_id), document_update)
                        updated_documents += 1
                updated_evidence += evidence_count_for_report
                updated_reports.append(
                    {
                        "report_id": report.get("report_id") or item_id,
                        "document_id": document_id,
                        "title": report.get("title", ""),
                        "matches": matches,
                        "evidence_count": evidence_count_for_report,
                        "topic_tags": topic_tags,
                        "risk_tags": risk_tags,
                        "financial_metric_tags": financial_metric_tags,
                    }
                )
            if not args.dry_run:
                connection.commit()

    return {
        "status": "passed",
        "dry_run": bool(args.dry_run),
        "started_at": started_at,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "market": args.market,
        "ticker_filter": sorted(target_tickers),
        "security_count": len(securities),
        "report_scan_limit": args.limit,
        "matched_report_count": len(updated_reports),
        "updated_document_count": updated_documents,
        "updated_evidence_count": updated_evidence,
        "direct_evidence_ready": updated_evidence > 0,
        "updated_reports": updated_reports[: args.artifact_limit],
        "updated_reports_truncated": max(0, len(updated_reports) - args.artifact_limit),
        "unmatched_samples": unmatched_samples,
        "production_boundary": "local_research_report_asset_binding_viewpoint_evidence_only_not_fact_source_or_trade_signal",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Bind local research reports and citation evidence to securities, issuers, industry-chain positions, topics, risks, and financial metric tags.")
    parser.add_argument("--dsn", default=DEFAULT_DSN)
    parser.add_argument("--market", default="U", choices=["", "A", "U"])
    parser.add_argument("--tickers", default="AAPL,MSFT,NVDA,TSLA,SPY,300750,600519,000001,600000")
    parser.add_argument("--limit", type=int, default=20000)
    parser.add_argument("--max-matches-per-report", type=int, default=3)
    parser.add_argument("--artifact-limit", type=int, default=200)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = build_research_report_asset_binding(args)
    _write_json(args.output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if result["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": str(exc), "error_type": type(exc).__name__}, ensure_ascii=False), file=sys.stderr)
        raise
