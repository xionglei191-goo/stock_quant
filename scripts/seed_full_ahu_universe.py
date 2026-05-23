from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models import CompanyPosition, Document, Evidence, IndustryChain, Issuer, MacroTheme, RightsTag, Security, SourceDefinition
from app.store import PostgreSQLStore
from app.utils import to_plain, utcnow


DEFAULT_DSN = "postgresql://ai_quant:ai_quant_dev_password@127.0.0.1:15432/ai_quant"
DEFAULT_ARTIFACT = Path("artifacts/full-ahu-universe.json")
EASTMONEY_SOURCE_ID = "eastmoney_ashare_company_list"
NASDAQ_SOURCE_ID = "nasdaq_trader_symbol_directory"
TDX_DIRECTORY_SOURCE_ID = "tdx_vipdoc_symbol_directory"
TAXONOMY_VERSION = "full-ahu-industry-chain-v1"
USER_AGENT = "ai-native-quant-org/0.1 local-research"


RIGHTS = RightsTag(
    license_class="public_company_directory_reference",
    training_allowed=False,
    redistribution_allowed=False,
    display_use="allowed",
    non_display_use="restricted",
    derived_data_use="restricted",
)


@dataclass(slots=True)
class UniverseCompany:
    symbol: str
    name: str
    market: str
    exchange: str
    currency: str
    country: str
    issuer_id: str
    security_id: str
    industry: str
    region: str = ""
    concepts: list[str] | None = None
    source_id: str = ""
    security_type: str = "common_stock"


ASHARE_CHAIN_TEMPLATES = {
    "银行": ("chain_sector_financial_services", "金融服务产业链", ["资金来源", "信贷投放", "财富管理", "产业融资"]),
    "证券": ("chain_sector_financial_services", "金融服务产业链", ["资金来源", "信贷投放", "财富管理", "产业融资"]),
    "保险": ("chain_sector_financial_services", "金融服务产业链", ["资金来源", "信贷投放", "财富管理", "产业融资"]),
    "电池": ("chain_sector_new_energy", "新能源与电力设备产业链", ["资源材料", "核心制造", "系统集成", "终端应用"]),
    "光伏": ("chain_sector_new_energy", "新能源与电力设备产业链", ["资源材料", "核心制造", "系统集成", "终端应用"]),
    "电力": ("chain_sector_new_energy", "新能源与电力设备产业链", ["资源材料", "核心制造", "系统集成", "终端应用"]),
    "汽车": ("chain_sector_auto_mobility", "汽车与智能出行产业链", ["零部件", "整车制造", "智能系统", "销售服务"]),
    "半导体": ("chain_sector_semiconductor_ai", "半导体与 AI 硬件产业链", ["设计/IP", "制造封测", "设备材料", "系统应用"]),
    "软件": ("chain_sector_digital_software", "数字软件与互联网产业链", ["基础设施", "平台软件", "行业应用", "终端服务"]),
    "通信": ("chain_sector_digital_software", "数字软件与互联网产业链", ["基础设施", "平台软件", "行业应用", "终端服务"]),
    "白酒": ("chain_sector_consumption", "消费品牌与渠道产业链", ["原料供应", "品牌制造", "渠道分销", "终端消费"]),
    "食品": ("chain_sector_consumption", "消费品牌与渠道产业链", ["原料供应", "品牌制造", "渠道分销", "终端消费"]),
    "医药": ("chain_sector_healthcare", "医药健康产业链", ["研发", "制造", "流通", "医疗消费"]),
    "医疗": ("chain_sector_healthcare", "医药健康产业链", ["研发", "制造", "流通", "医疗消费"]),
    "化学": ("chain_sector_materials", "基础材料与制造产业链", ["资源", "材料加工", "中间品", "下游制造"]),
    "有色": ("chain_sector_materials", "基础材料与制造产业链", ["资源", "材料加工", "中间品", "下游制造"]),
    "钢铁": ("chain_sector_materials", "基础材料与制造产业链", ["资源", "材料加工", "中间品", "下游制造"]),
    "机械": ("chain_sector_industrials", "工业设备与制造产业链", ["设备部件", "整机制造", "工程交付", "运维服务"]),
    "自动化": ("chain_sector_industrials", "工业设备与制造产业链", ["设备部件", "整机制造", "工程交付", "运维服务"]),
}

US_NAME_CHAIN_TEMPLATES = {
    "bank": ("chain_us_financial_services", "美股金融服务产业链", ["funding", "credit", "capital_markets", "wealth"]),
    "financial": ("chain_us_financial_services", "美股金融服务产业链", ["funding", "credit", "capital_markets", "wealth"]),
    "software": ("chain_us_software_cloud", "美股软件与云产业链", ["infrastructure", "platform", "application", "customer"]),
    "semiconductor": ("chain_us_semiconductor_ai", "美股半导体与 AI 硬件产业链", ["design", "manufacturing", "systems", "applications"]),
    "technology": ("chain_us_software_cloud", "美股软件与云产业链", ["infrastructure", "platform", "application", "customer"]),
    "pharmaceutical": ("chain_us_healthcare", "美股医药健康产业链", ["research", "manufacturing", "distribution", "care"]),
    "biotechnology": ("chain_us_healthcare", "美股医药健康产业链", ["research", "manufacturing", "distribution", "care"]),
    "energy": ("chain_us_energy_materials", "美股能源与材料产业链", ["resource", "processing", "transport", "end_market"]),
    "mining": ("chain_us_energy_materials", "美股能源与材料产业链", ["resource", "processing", "transport", "end_market"]),
    "automotive": ("chain_us_auto_mobility", "美股汽车与出行产业链", ["components", "vehicle", "software", "services"]),
    "retail": ("chain_us_consumer", "美股消费与零售产业链", ["sourcing", "brand", "distribution", "consumer"]),
    "food": ("chain_us_consumer", "美股消费与零售产业链", ["sourcing", "brand", "distribution", "consumer"]),
}


def fetch_json(url: str, *, referer: str = "") -> dict[str, Any]:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json,text/plain,*/*"}
    if referer:
        headers["Referer"] = referer
    last_error: Exception | None = None
    for attempt in range(1, 5):
        try:
            with urlopen(Request(url, headers=headers), timeout=30) as response:
                return json.loads(response.read().decode("utf-8", errors="replace"))
        except Exception as exc:
            last_error = exc
            time.sleep(min(8, attempt * 1.5))
    raise RuntimeError(f"fetch_json failed after retries: {url}: {last_error}") from last_error


def fetch_text(url: str) -> str:
    last_error: Exception | None = None
    for attempt in range(1, 5):
        try:
            with urlopen(Request(url, headers={"User-Agent": USER_AGENT}), timeout=30) as response:
                return response.read().decode("utf-8", errors="replace")
        except Exception as exc:
            last_error = exc
            time.sleep(min(8, attempt * 1.5))
    raise RuntimeError(f"fetch_text failed after retries: {url}: {last_error}") from last_error


def fetch_ashare_companies(*, limit: int = 0) -> list[UniverseCompany]:
    fields = "f12,f14,f13,f100,f102,f103"
    fs = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81,m:0+t:83"
    page_size = 500
    page = 1
    rows: list[UniverseCompany] = []
    while True:
        params = {
            "pn": page,
            "pz": page_size,
            "po": 1,
            "np": 1,
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": 2,
            "invt": 2,
            "fid": "f3",
            "fs": fs,
            "fields": fields,
        }
        payload = fetch_json(
            f"https://push2.eastmoney.com/api/qt/clist/get?{urlencode(params)}",
            referer="https://quote.eastmoney.com/center/gridlist.html",
        )
        data = payload.get("data") or {}
        diff = data.get("diff") or []
        if not diff:
            break
        for item in diff:
            code = str(item.get("f12") or "").strip()
            name = str(item.get("f14") or "").strip()
            if not code or not name:
                continue
            market_code = str(item.get("f13") or "")
            exchange = "SSE" if market_code == "1" else "SZSE" if market_code == "0" else "BSE"
            industry = _clean_dash(item.get("f100")) or "未分类行业"
            concepts = [part.strip() for part in str(item.get("f103") or "").split(",") if part.strip() and part.strip() != "-"]
            rows.append(
                UniverseCompany(
                    symbol=code,
                    name=name,
                    market="A",
                    exchange=exchange,
                    currency="CNY",
                    country="CN",
                    issuer_id=f"issuer_{code}",
                    security_id=f"sec_{code}",
                    industry=industry,
                    region=_clean_dash(item.get("f102")),
                    concepts=concepts[:12],
                    source_id=EASTMONEY_SOURCE_ID,
                )
            )
            if limit and len(rows) >= limit:
                return rows
        total = int(data.get("total") or len(rows))
        if len(rows) >= total:
            break
        page += 1
    return rows


def fetch_tdx_ashare_companies(path: str | Path, *, limit: int = 0) -> list[UniverseCompany]:
    root = Path(path)
    if not root.exists():
        raise RuntimeError(f"TDX vipdoc path not found: {root}")
    rows: list[UniverseCompany] = []
    seen: set[str] = set()
    for file_path in sorted(root.glob("**/*.day")):
        symbol = re.sub(r"\D+", "", file_path.stem)[-6:]
        if not symbol or symbol in seen:
            continue
        prefix = file_path.stem[:2].lower()
        exchange = "SSE" if prefix == "sh" else "SZSE" if prefix == "sz" else "BSE" if prefix == "bj" else _infer_ashare_exchange(symbol)
        security_type = _infer_ashare_security_type(symbol)
        industry = "待补行业" if security_type == "common_stock" else "非公司类证券"
        rows.append(
            UniverseCompany(
                symbol=symbol,
                name=f"{symbol}（待补名称）",
                market="A",
                exchange=exchange,
                currency="CNY",
                country="CN",
                issuer_id=f"issuer_{symbol}",
                security_id=f"sec_{symbol}",
                industry=industry,
                region="",
                concepts=["name_pending", "tdx_vipdoc"],
                source_id=TDX_DIRECTORY_SOURCE_ID,
                security_type=security_type,
            )
        )
        seen.add(symbol)
        if limit and len(rows) >= limit:
            break
    return rows


def company_to_dict(company: UniverseCompany) -> dict[str, Any]:
    return {
        "symbol": company.symbol,
        "name": company.name,
        "market": company.market,
        "exchange": company.exchange,
        "currency": company.currency,
        "country": company.country,
        "issuer_id": company.issuer_id,
        "security_id": company.security_id,
        "industry": company.industry,
        "region": company.region,
        "concepts": company.concepts or [],
        "source_id": company.source_id,
        "security_type": company.security_type,
    }


def company_from_dict(row: dict[str, Any]) -> UniverseCompany:
    return UniverseCompany(
        symbol=str(row["symbol"]),
        name=str(row["name"]),
        market=str(row["market"]),
        exchange=str(row["exchange"]),
        currency=str(row["currency"]),
        country=str(row["country"]),
        issuer_id=str(row["issuer_id"]),
        security_id=str(row["security_id"]),
        industry=str(row.get("industry", "")),
        region=str(row.get("region", "")),
        concepts=[str(item) for item in row.get("concepts", [])],
        source_id=str(row.get("source_id", "")),
        security_type=str(row.get("security_type", "common_stock")),
    )


def fetch_universe_cache(path: str | Path, *, a_limit: int = 0, us_limit: int = 0, include_etf: bool = False) -> dict[str, Any]:
    ashare = fetch_ashare_companies(limit=a_limit)
    us = fetch_us_companies(limit=us_limit, include_etf=include_etf)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_ids": [EASTMONEY_SOURCE_ID, NASDAQ_SOURCE_ID],
        "ashare_count": len(ashare),
        "us_count": len(us),
        "companies": [company_to_dict(company) for company in ashare + us],
    }
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def fetch_us_companies(*, limit: int = 0, include_etf: bool = False) -> list[UniverseCompany]:
    urls = [
        ("https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt", "NASDAQ"),
        ("https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt", "OTHER"),
    ]
    rows: list[UniverseCompany] = []
    seen: set[str] = set()
    for url, source_exchange in urls:
        text = fetch_text(url)
        lines = [line for line in text.splitlines() if line and not line.startswith("File Creation Time")]
        reader = csv.DictReader(lines, delimiter="|")
        for item in reader:
            symbol = str(item.get("Symbol") or item.get("ACT Symbol") or "").strip()
            if not symbol or symbol in seen:
                continue
            if str(item.get("Test Issue") or "").upper() == "Y":
                continue
            is_etf = str(item.get("ETF") or "").upper() == "Y"
            if is_etf and not include_etf:
                continue
            name = str(item.get("Security Name") or "").strip()
            if not name or _is_us_non_company_security(symbol, name):
                continue
            exchange = _us_exchange_label(str(item.get("Exchange") or source_exchange), source_exchange)
            industry = _infer_us_industry(name)
            safe = _safe_id(symbol.lower())
            rows.append(
                UniverseCompany(
                    symbol=symbol,
                    name=name,
                    market="U",
                    exchange=exchange,
                    currency="USD",
                    country="US",
                    issuer_id=f"issuer_us_{safe}",
                    security_id=f"security_us_{safe}",
                    industry=industry,
                    source_id=NASDAQ_SOURCE_ID,
                    security_type="etf" if is_etf else "listed_company",
                )
            )
            seen.add(symbol)
            if limit and len(rows) >= limit:
                return rows
    return rows


def _clean_dash(value: Any) -> str:
    text = str(value or "").strip()
    return "" if text == "-" else text


def _safe_id(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _stable_slug(value: str, *, prefix: str = "", max_len: int = 48) -> str:
    safe = _safe_id(value)
    if safe:
        return f"{prefix}{safe[:max_len]}"
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}{digest}"


def _infer_ashare_exchange(symbol: str) -> str:
    if symbol.startswith(("60", "68", "90", "50", "51", "52", "56", "58", "11")):
        return "SSE"
    if symbol.startswith(("00", "20", "30", "12", "15", "16", "18", "39")):
        return "SZSE"
    if symbol.startswith(("43", "83", "87", "92")):
        return "BSE"
    return "A"


def _infer_ashare_security_type(symbol: str) -> str:
    if symbol.startswith(("60", "68", "00", "001", "002", "003", "30", "43", "83", "87", "92")):
        return "common_stock"
    if symbol.startswith(("11", "12")):
        return "convertible_bond"
    if symbol.startswith(("15", "16", "50", "51", "52", "53", "56", "58")):
        return "fund_or_etf"
    if symbol.startswith(("13", "18", "39", "88", "89", "99")):
        return "index_or_board_series"
    if symbol.startswith(("20", "90")):
        return "b_share"
    return "other_security"


def _is_us_non_company_security(symbol: str, name: str) -> bool:
    lower = f"{symbol} {name}".lower()
    blocked = [" warrant", " right", " unit", " notes due", " preferred stock", "depositary shares", " fund", " etf", " etn"]
    return any(term in lower for term in blocked)


def _us_exchange_label(value: str, source_exchange: str) -> str:
    mapping = {
        "Q": "NASDAQ",
        "G": "NASDAQ_GLOBAL_MARKET",
        "S": "NASDAQ_CAPITAL_MARKET",
        "N": "NYSE",
        "A": "NYSE_AMERICAN",
        "P": "NYSE_ARCA",
        "Z": "CBOE_BZX",
        "V": "IEX",
    }
    return mapping.get(value, "NASDAQ" if source_exchange == "NASDAQ" else value or "US")


def _infer_us_industry(name: str) -> str:
    lower = name.lower()
    for keyword, (_chain_id, chain_name, _nodes) in US_NAME_CHAIN_TEMPLATES.items():
        if keyword in lower:
            return chain_name
    return "美股上市公司"


def _chain_for_company(company: UniverseCompany) -> tuple[str, str, list[str]]:
    if company.market == "A":
        text = f"{company.industry} {company.name} {' '.join(company.concepts or [])}"
        for keyword, template in ASHARE_CHAIN_TEMPLATES.items():
            if keyword in text:
                return template
        chain_id = f"chain_ashare_industry_{_stable_slug(company.industry)}"
        return chain_id, f"A股{company.industry}产业链", ["上游资源", "核心制造/服务", "渠道/交付", "终端需求"]
    lower = f"{company.industry} {company.name}".lower()
    for keyword, template in US_NAME_CHAIN_TEMPLATES.items():
        if keyword in lower:
            return template
    return "chain_us_listed_companies", "美股上市公司通用产业链", ["inputs", "operations", "distribution", "customers"]


def _node_for_company(company: UniverseCompany, nodes: list[str]) -> str:
    text = f"{company.name} {company.industry}".lower()
    if company.market == "A":
        if any(term in text for term in ["银行", "证券", "保险"]):
            return nodes[min(1, len(nodes) - 1)]
        if any(term in text for term in ["销售", "商贸", "零售", "连锁"]):
            return nodes[min(2, len(nodes) - 1)]
        return nodes[min(1, len(nodes) - 1)]
    if any(term in text for term in ["retail", "stores", "market"]):
        return nodes[min(2, len(nodes) - 1)]
    return nodes[min(1, len(nodes) - 1)]


def _upsert_sources(store: PostgreSQLStore, now: datetime) -> None:
    store.sources[EASTMONEY_SOURCE_ID] = SourceDefinition(
        source_id=EASTMONEY_SOURCE_ID,
        source_type="public_web",
        rights_tag=RIGHTS,
        description="Eastmoney public A-share company list fields for local company directory, industry, region, and concept tags.",
        risk_level="yellow",
        field_whitelist=["code", "name", "exchange", "industry", "region", "concepts"],
        retention_policy="refresh_incrementally_or_monthly",
        cache_ttl_days=30,
        provenance_ref="https://push2.eastmoney.com/api/qt/clist/get",
        usage_scope="local_research_company_directory_and_industry_chain_seed_only",
        collection_method="public_web_api",
        robots_policy="periodic_review_required",
        last_reviewed_at=now,
        review_cadence="quarterly",
        review_owner="数据工程",
        review_owner_role="数据工程",
        source_tos_uri="https://www.eastmoney.com/",
    )
    store.sources[NASDAQ_SOURCE_ID] = SourceDefinition(
        source_id=NASDAQ_SOURCE_ID,
        source_type="public_directory",
        rights_tag=RIGHTS,
        description="Nasdaq Trader symbol directory for US listed securities; used as local US company universe seed.",
        risk_level="green",
        field_whitelist=["symbol", "security_name", "exchange", "etf", "test_issue"],
        retention_policy="refresh_incrementally_or_monthly",
        cache_ttl_days=30,
        provenance_ref="https://www.nasdaqtrader.com/dynamic/SymDir/",
        usage_scope="local_research_company_directory_and_industry_chain_seed_only",
        collection_method="public_text_directory",
        robots_policy="reviewed_public_directory",
        last_reviewed_at=now,
        review_cadence="quarterly",
        review_owner="数据工程",
        review_owner_role="数据工程",
        source_tos_uri="https://www.nasdaqtrader.com/",
    )
    store.sources[TDX_DIRECTORY_SOURCE_ID] = SourceDefinition(
        source_id=TDX_DIRECTORY_SOURCE_ID,
        source_type="local_reference",
        rights_tag=RIGHTS,
        description="Local TDX vipdoc daily file symbols used as the A-share full security universe when public name directory is unavailable.",
        risk_level="green",
        field_whitelist=["symbol", "exchange", "security_type", "name_pending"],
        retention_policy="refresh_when_tdx_vipdoc_is_replaced",
        cache_ttl_days=30,
        provenance_ref="local://data/local/tdx/vipdoc",
        usage_scope="local_research_security_directory_seed_only_name_industry_pending",
        collection_method="local_tdx_vipdoc_file_discovery",
        robots_policy="not_applicable_local_file",
        last_reviewed_at=now,
        review_cadence="quarterly",
        review_owner="数据工程",
        review_owner_role="数据工程",
        source_tos_uri="https://www.tdx.com.cn/article/vipdata.html",
    )


def _upsert_company_records(store: PostgreSQLStore, company: UniverseCompany, chain: IndustryChain, node_id: str, now: datetime, *, evidence: bool) -> None:
    existing_issuer = store.issuers.get(company.issuer_id)
    store.issuers[company.issuer_id] = Issuer(
        issuer_id=company.issuer_id,
        legal_name=company.name,
        aliases=[],
        market=[company.market],
        country=company.country,
        status="active",
        created_at=getattr(existing_issuer, "created_at", now),
        updated_at=now,
    )
    store.securities[company.security_id] = Security(
        security_id=company.security_id,
        issuer_id=company.issuer_id,
        ticker=company.symbol,
        exchange=company.exchange,
        currency=company.currency,
        market=company.market,
        status="active",
    )
    position_id = f"pos_{company.market.lower()}_{_safe_id(company.symbol.lower())}_industry"
    evidence_ids: list[str] = []
    if evidence:
        document_id = f"doc_{company.market.lower()}_{_safe_id(company.symbol.lower())}_profile"
        evidence_id = f"evi_{company.market.lower()}_{_safe_id(company.symbol.lower())}_profile"
        body = "\n".join(
            [
                f"公司/证券: {company.name} ({company.symbol})",
                f"市场/交易所: {company.market} / {company.exchange}",
                f"行业: {company.industry}",
                f"地区: {company.region or company.country}",
                f"概念/标签: {', '.join(company.concepts or [])}",
                f"产业链: {chain.name}",
                f"产业链节点: {node_id}",
                "使用边界: 公开目录和本地归类生成的基础资料，用于研究图谱和产业链覆盖，不构成交易指令。",
            ]
        )
        store.documents[document_id] = Document(
            document_id=document_id,
            issuer_id=company.issuer_id,
            security_id=company.security_id,
            document_type="company_profile",
            source_id=company.source_id,
            source_type="public_directory",
            source_uri=f"artifact://full-ahu-universe/{company.market}/{company.symbol}",
            rights_tag=RIGHTS,
            body=body,
            title=f"{company.symbol} 基础资料与产业链定位",
            content_sha256=hashlib.sha256(body.encode("utf-8")).hexdigest(),
            published_at=now,
            ingested_at=now,
            language="zh" if company.market == "A" else "en",
            version=TAXONOMY_VERSION,
        )
        store.evidence[evidence_id] = Evidence(
            evidence_id=evidence_id,
            document_id=document_id,
            section="company_directory_industry_position",
            page_no=1,
            bbox="",
            span_text=body,
            canonical_text=body,
            confidence=0.72 if company.market == "A" else 0.64,
            locator={"type": "full_universe_directory", "market": company.market, "symbol": company.symbol, "chain_id": chain.chain_id, "node_id": node_id},
            assets=[{"issuer_id": company.issuer_id, "security_id": company.security_id, "ticker": company.symbol}],
            created_at=now,
        )
        evidence_ids = [evidence_id]
    store.company_positions[position_id] = CompanyPosition(
        position_id=position_id,
        issuer_id=company.issuer_id,
        security_id=company.security_id,
        chain_id=chain.chain_id,
        node_ids=[node_id],
        role=f"{company.industry}公司/证券的产业链节点参与者",
        positioning_summary=f"{company.name}归入“{chain.name}”的“{node_id}”节点。",
        revenue_exposure={"type": "directory_classification", "industry": company.industry, "concepts": company.concepts or []},
        profit_exposure={"type": "directory_classification", "sensitivity": "requires_financial_statement_backfill"},
        capacity={"type": "directory_seed", "status": "basic_profile_seeded"},
        customers=["待由公告/研报/财报继续细分"],
        suppliers=["待由公告/研报/财报继续细分"],
        competitors=[],
        technology_tags=(company.concepts or [])[:8],
        valuation_metrics={"currency": company.currency, "market": company.market, "exchange": company.exchange},
        event_refs=[f"artifact://full-ahu-universe/{company.market}/{company.symbol}"],
        evidence_ids=evidence_ids,
        data_quality="complete" if evidence else "partial",
        created_at=now,
    )


def seed_full_universe(
    dsn: str,
    *,
    a_limit: int = 0,
    us_limit: int = 0,
    include_etf: bool = False,
    with_evidence: bool = True,
    universe_cache: str = "",
    ashare_source: str = "eastmoney",
    tdx_path: str = "data/local/tdx/vipdoc",
) -> dict[str, Any]:
    now = utcnow()
    if universe_cache:
        cached = json.loads(Path(universe_cache).read_text(encoding="utf-8"))
        companies = [company_from_dict(row) for row in cached.get("companies", [])]
        ashare = [company for company in companies if company.market == "A"]
        us = [company for company in companies if company.market == "U"]
    else:
        if ashare_source == "tdx":
            ashare = fetch_tdx_ashare_companies(tdx_path, limit=a_limit)
        else:
            ashare = fetch_ashare_companies(limit=a_limit)
        us = fetch_us_companies(limit=us_limit, include_etf=include_etf)
        companies = ashare + us
    store = PostgreSQLStore(dsn)
    _upsert_sources(store, now)

    chain_templates: dict[str, tuple[str, list[str]]] = {}
    company_chain: dict[str, tuple[str, list[str]]] = {}
    for company in companies:
        chain_id, chain_name, nodes = _chain_for_company(company)
        chain_templates.setdefault(chain_id, (chain_name, nodes))
        company_chain[company.security_id] = (chain_id, nodes)

    for chain_id, (chain_name, nodes) in chain_templates.items():
        theme_id = f"theme_{chain_id.replace('chain_', '')}"
        store.macro_themes[theme_id] = MacroTheme(
            theme_id=theme_id,
            name=chain_name.replace("产业链", ""),
            description=f"{chain_name}全量基础目录自动归类主题。",
            trigger_type="full_universe_seed",
            as_of_date=str(now.date()),
        source_refs=[EASTMONEY_SOURCE_ID, NASDAQ_SOURCE_ID, TDX_DIRECTORY_SOURCE_ID],
            macro_drivers=["行业景气", "供需变化", "资本开支", "政策和流动性"],
            risk_factors=["目录归类误差", "行业更新滞后", "缺少精细客户/供应商数据"],
            confidence=0.68,
            created_at=now,
        )
        node_rows = [{"node_id": f"{chain_id}_{_stable_slug(node, prefix='node_')}", "name": node, "node_type": "industry_chain_node"} for node in nodes]
        edge_rows = []
        for idx in range(len(node_rows) - 1):
            edge_rows.append(
                {
                    "edge_id": f"{node_rows[idx]['node_id']}_{node_rows[idx+1]['node_id']}",
                    "source_node_id": node_rows[idx]["node_id"],
                    "target_node_id": node_rows[idx + 1]["node_id"],
                    "relation": "upstream_to_downstream",
                    "source": "full_universe_directory_seed",
                    "version": TAXONOMY_VERSION,
                    "confidence": 0.68,
                }
            )
        store.industry_chains[chain_id] = IndustryChain(
            chain_id=chain_id,
            name=chain_name,
            root_theme_id=theme_id,
            nodes=node_rows,
            edges=edge_rows,
            taxonomy_version=TAXONOMY_VERSION,
            source_refs=[EASTMONEY_SOURCE_ID, NASDAQ_SOURCE_ID, TDX_DIRECTORY_SOURCE_ID],
            created_at=now,
        )

    chain_node_lookup = {
        chain_id: {node["name"]: node["node_id"] for node in chain.nodes}
        for chain_id, chain in store.industry_chains.items()
        if chain.taxonomy_version == TAXONOMY_VERSION
    }
    for index, company in enumerate(companies, start=1):
        chain_id, nodes = company_chain[company.security_id]
        node_name = _node_for_company(company, nodes)
        node_id = chain_node_lookup[chain_id][node_name]
        _upsert_company_records(store, company, store.industry_chains[chain_id], node_id, now, evidence=with_evidence)
        if index % 1000 == 0:
            print(json.dumps({"progress": index, "total": len(companies)}, ensure_ascii=False), flush=True)

    store.commit()

    by_market: dict[str, int] = {}
    by_chain: dict[str, int] = {}
    for company in companies:
        by_market[company.market] = by_market.get(company.market, 0) + 1
        chain_id, _nodes = company_chain[company.security_id]
        by_chain[chain_id] = by_chain.get(chain_id, 0) + 1

    return {
        "generated_at": now.isoformat(),
        "taxonomy_version": TAXONOMY_VERSION,
        "source_ids": [EASTMONEY_SOURCE_ID, NASDAQ_SOURCE_ID, TDX_DIRECTORY_SOURCE_ID],
        "company_count": len(companies),
        "ashare_count": len(ashare),
        "us_count": len(us),
        "industry_chain_count": len(chain_templates),
        "position_count": len(companies),
        "evidence_count": len(companies) if with_evidence else 0,
        "by_market": by_market,
        "by_chain": dict(sorted(by_chain.items(), key=lambda item: (-item[1], item[0]))),
        "usage_boundary": "full_universe_basic_directory_and_industry_chain_seed_only_no_real_trading",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed full A-share and US-listed company universe with basic info and industry-chain positions.")
    parser.add_argument("--dsn", default=os.environ.get("AI_QUANT_POSTGRES_DSN") or os.environ.get("AI_QUANT_DATABASE_URL") or DEFAULT_DSN)
    parser.add_argument("--artifact", default=str(DEFAULT_ARTIFACT))
    parser.add_argument("--a-limit", type=int, default=0)
    parser.add_argument("--us-limit", type=int, default=0)
    parser.add_argument("--include-etf", action="store_true")
    parser.add_argument("--no-evidence", action="store_true")
    parser.add_argument("--fetch-only", action="store_true", help="Only fetch public company directory cache; do not write PostgreSQL.")
    parser.add_argument("--universe-cache", default="", help="Read companies from a previously fetched JSON cache.")
    parser.add_argument("--ashare-source", choices=["eastmoney", "tdx"], default="eastmoney")
    parser.add_argument("--tdx-path", default=os.environ.get("AI_QUANT_TDX_VIPDOC_PATH") or "data/local/tdx/vipdoc")
    args = parser.parse_args()

    if args.fetch_only:
        result = fetch_universe_cache(
            args.artifact,
            a_limit=args.a_limit,
            us_limit=args.us_limit,
            include_etf=args.include_etf,
        )
        print(json.dumps({"artifact": args.artifact, "ashare_count": result["ashare_count"], "us_count": result["us_count"], "company_count": len(result["companies"])}, ensure_ascii=False))
        return

    result = seed_full_universe(
        args.dsn,
        a_limit=args.a_limit,
        us_limit=args.us_limit,
        include_etf=args.include_etf,
        with_evidence=not args.no_evidence,
        universe_cache=args.universe_cache,
        ashare_source=args.ashare_source,
        tdx_path=args.tdx_path,
    )
    artifact = Path(args.artifact)
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"artifact": str(artifact), **result}, ensure_ascii=False))


if __name__ == "__main__":
    main()
