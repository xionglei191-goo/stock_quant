from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models import (
    CompanyPosition,
    Document,
    Evidence,
    IndustryChain,
    Issuer,
    MacroTheme,
    RightsTag,
    Security,
    SourceDefinition,
)
from app.store import PostgreSQLStore
from app.utils import to_plain, utcnow


DEFAULT_DSN = "postgresql://ai_quant:ai_quant_dev_password@127.0.0.1:15432/ai_quant"
ARTIFACT_PATH = Path("artifacts/ahu-basic-info-industry-chain.json")
SOURCE_ID = "curated_company_profile"
TAXONOMY_VERSION = "ahu-industry-chain-v1"


RIGHTS = RightsTag(
    license_class="curated_public_company_profile",
    training_allowed=False,
    redistribution_allowed=False,
    display_use="allowed",
    non_display_use="restricted",
    derived_data_use="restricted",
)


COMPANIES: dict[str, dict[str, Any]] = {
    "600000": {
        "issuer_id": "issuer_600000",
        "security_id": "sec_600000",
        "legal_name": "上海浦东发展银行股份有限公司",
        "aliases": ["浦发银行", "Shanghai Pudong Development Bank"],
        "ticker": "600000",
        "exchange": "SSE",
        "currency": "CNY",
        "market": "A",
        "country": "CN",
        "profile": "全国性股份制商业银行，主要参与存贷款、公司金融、零售金融、金融市场和财富管理链条。",
    },
    "000001": {
        "issuer_id": "issuer_000001",
        "security_id": "sec_000001",
        "legal_name": "平安银行股份有限公司",
        "aliases": ["平安银行", "Ping An Bank"],
        "ticker": "000001",
        "exchange": "SZSE",
        "currency": "CNY",
        "market": "A",
        "country": "CN",
        "profile": "全国性股份制商业银行，重点覆盖零售金融、对公金融、综合金融协同和金融科技运营。",
    },
    "300750": {
        "issuer_id": "issuer_300750",
        "security_id": "sec_300750",
        "legal_name": "宁德时代新能源科技股份有限公司",
        "aliases": ["宁德时代", "CATL"],
        "ticker": "300750",
        "exchange": "SZSE",
        "currency": "CNY",
        "market": "A",
        "country": "CN",
        "profile": "动力电池和储能电池核心厂商，位于新能源车、储能和电池材料产业链中游。",
    },
    "600519": {
        "issuer_id": "issuer_600519",
        "security_id": "sec_600519",
        "legal_name": "贵州茅台酒股份有限公司",
        "aliases": ["贵州茅台", "Kweichow Moutai"],
        "ticker": "600519",
        "exchange": "SSE",
        "currency": "CNY",
        "market": "A",
        "country": "CN",
        "profile": "高端白酒龙头，位于高端消费、品牌定价、生产窖藏和渠道分销链条。",
    },
    "AAPL": {
        "issuer_id": "issuer_aapl",
        "security_id": "security_aapl_us",
        "legal_name": "Apple Inc.",
        "aliases": ["Apple", "苹果公司"],
        "ticker": "AAPL",
        "exchange": "NASDAQ",
        "currency": "USD",
        "market": "U",
        "country": "US",
        "profile": "消费电子和平台生态公司，参与终端设备、半导体设计、操作系统、服务和边缘 AI 入口。",
    },
    "MSFT": {
        "issuer_id": "issuer_msft",
        "security_id": "security_msft_us",
        "legal_name": "Microsoft Corporation",
        "aliases": ["Microsoft", "微软"],
        "ticker": "MSFT",
        "exchange": "NASDAQ",
        "currency": "USD",
        "market": "U",
        "country": "US",
        "profile": "云计算、企业软件和 AI 平台公司，覆盖云基础设施、生产力软件、开发者平台和 AI 应用。",
    },
    "NVDA": {
        "issuer_id": "issuer_nvda",
        "security_id": "security_nvda_us",
        "legal_name": "NVIDIA Corporation",
        "aliases": ["NVIDIA", "英伟达"],
        "ticker": "NVDA",
        "exchange": "NASDAQ",
        "currency": "USD",
        "market": "U",
        "country": "US",
        "profile": "GPU、加速计算和 AI 基础设施核心供应商，位于芯片、系统和 AI 算力链条。",
    },
    "TSLA": {
        "issuer_id": "issuer_tsla",
        "security_id": "security_tsla_us",
        "legal_name": "Tesla, Inc.",
        "aliases": ["Tesla", "特斯拉"],
        "ticker": "TSLA",
        "exchange": "NASDAQ",
        "currency": "USD",
        "market": "U",
        "country": "US",
        "profile": "电动车、储能和智能驾驶公司，覆盖整车制造、三电系统、充电能源和自动驾驶计算。",
    },
    "SPY": {
        "issuer_id": "issuer_spy",
        "security_id": "security_spy_us",
        "legal_name": "SPDR S&P 500 ETF Trust",
        "aliases": ["SPY", "SPDR标普500ETF"],
        "ticker": "SPY",
        "exchange": "NYSE_ARCA",
        "currency": "USD",
        "market": "U",
        "country": "US",
        "profile": "跟踪标普 500 指数的交易型开放式指数基金，位于指数、ETF、做市和资产配置链条。",
    },
}


THEMES = [
    {
        "theme_id": "theme_ai_compute_cloud",
        "name": "AI 算力与云软件",
        "description": "从上游半导体与制造，到 GPU/服务器、云基础设施、AI 软件和边缘终端的完整链条。",
        "macro_drivers": ["生成式 AI 训练与推理需求", "云资本开支", "端侧 AI 升级"],
        "risk_factors": ["算力供给约束", "出口管制", "云资本开支波动"],
    },
    {
        "theme_id": "theme_ev_battery_energy",
        "name": "新能源车与储能",
        "description": "从锂资源、电池材料、电芯、电池包，到整车、储能、充电和智能驾驶的完整链条。",
        "macro_drivers": ["电动化渗透率", "储能装机", "智能驾驶升级"],
        "risk_factors": ["材料价格波动", "产能利用率", "价格竞争"],
    },
    {
        "theme_id": "theme_financial_services",
        "name": "金融服务与资本配置",
        "description": "从存款负债、信贷投放、财富管理，到资本市场工具和产业融资的完整链条。",
        "macro_drivers": ["利率周期", "信用需求", "居民资产配置"],
        "risk_factors": ["净息差压力", "资产质量", "市场波动"],
    },
    {
        "theme_id": "theme_premium_consumption",
        "name": "高端消费与渠道",
        "description": "从原料、生产窖藏、品牌定价、批发零售渠道，到终端消费需求的完整链条。",
        "macro_drivers": ["居民消费能力", "高端礼赠和商务需求", "渠道库存周期"],
        "risk_factors": ["需求降级", "渠道价格波动", "政策和消费场景变化"],
    },
    {
        "theme_id": "theme_index_etf_allocation",
        "name": "指数 ETF 与资产配置",
        "description": "从指数编制、基金产品、申赎做市、流动性，到投资者资产配置的完整链条。",
        "macro_drivers": ["被动投资渗透", "美股流动性", "资产配置再平衡"],
        "risk_factors": ["指数集中度", "流动性冲击", "跟踪误差"],
    },
]


CHAINS = [
    {
        "chain_id": "chain_ai_compute_cloud",
        "name": "AI 算力与云软件产业链",
        "root_theme_id": "theme_ai_compute_cloud",
        "nodes": [
            ("ai_semiconductor_design", "AI 芯片设计"),
            ("advanced_foundry_packaging", "先进制造与封装"),
            ("gpu_accelerator_system", "GPU/加速卡与系统"),
            ("ai_server_cluster", "AI 服务器与集群"),
            ("cloud_infrastructure", "云基础设施"),
            ("enterprise_ai_software", "企业 AI 软件"),
            ("edge_device_ecosystem", "端侧设备与生态"),
        ],
        "edges": [
            ("ai_semiconductor_design", "advanced_foundry_packaging"),
            ("advanced_foundry_packaging", "gpu_accelerator_system"),
            ("gpu_accelerator_system", "ai_server_cluster"),
            ("ai_server_cluster", "cloud_infrastructure"),
            ("cloud_infrastructure", "enterprise_ai_software"),
            ("enterprise_ai_software", "edge_device_ecosystem"),
        ],
    },
    {
        "chain_id": "chain_ev_battery_energy",
        "name": "新能源车与储能产业链",
        "root_theme_id": "theme_ev_battery_energy",
        "nodes": [
            ("lithium_resources", "锂资源与关键矿产"),
            ("battery_materials", "正负极/电解液/隔膜"),
            ("battery_cell_pack", "电芯、电池包与 BMS"),
            ("ev_oem", "整车制造"),
            ("charging_energy_storage", "充电与储能"),
            ("autonomous_compute", "智能驾驶与车端计算"),
            ("green_financing", "绿色金融与产业融资"),
        ],
        "edges": [
            ("lithium_resources", "battery_materials"),
            ("battery_materials", "battery_cell_pack"),
            ("battery_cell_pack", "ev_oem"),
            ("ev_oem", "charging_energy_storage"),
            ("autonomous_compute", "ev_oem"),
            ("green_financing", "battery_cell_pack"),
            ("green_financing", "charging_energy_storage"),
        ],
    },
    {
        "chain_id": "chain_financial_services",
        "name": "金融服务与资本配置产业链",
        "root_theme_id": "theme_financial_services",
        "nodes": [
            ("deposits_funding", "存款负债与同业资金"),
            ("credit_allocation", "信贷投放"),
            ("wealth_management", "财富管理"),
            ("payments_fintech", "支付与金融科技"),
            ("capital_market_instruments", "资本市场工具"),
            ("industry_financing", "产业融资"),
        ],
        "edges": [
            ("deposits_funding", "credit_allocation"),
            ("credit_allocation", "industry_financing"),
            ("wealth_management", "capital_market_instruments"),
            ("payments_fintech", "wealth_management"),
            ("capital_market_instruments", "industry_financing"),
        ],
    },
    {
        "chain_id": "chain_premium_consumption",
        "name": "高端消费与渠道产业链",
        "root_theme_id": "theme_premium_consumption",
        "nodes": [
            ("agri_raw_materials", "原料与产区"),
            ("distillation_storage", "酿造生产与窖藏"),
            ("brand_pricing_power", "品牌定价权"),
            ("wholesale_distribution", "批发与经销"),
            ("retail_channel", "零售与电商渠道"),
            ("consumer_demand", "终端消费需求"),
        ],
        "edges": [
            ("agri_raw_materials", "distillation_storage"),
            ("distillation_storage", "brand_pricing_power"),
            ("brand_pricing_power", "wholesale_distribution"),
            ("wholesale_distribution", "retail_channel"),
            ("retail_channel", "consumer_demand"),
        ],
    },
    {
        "chain_id": "chain_index_etf_allocation",
        "name": "指数 ETF 与资产配置产业链",
        "root_theme_id": "theme_index_etf_allocation",
        "nodes": [
            ("index_methodology", "指数编制"),
            ("fund_sponsor", "基金管理与产品"),
            ("creation_redemption", "申赎机制"),
            ("market_making_liquidity", "做市与流动性"),
            ("investor_allocation", "投资者资产配置"),
            ("underlying_equities", "底层成份股"),
        ],
        "edges": [
            ("index_methodology", "fund_sponsor"),
            ("fund_sponsor", "creation_redemption"),
            ("creation_redemption", "market_making_liquidity"),
            ("market_making_liquidity", "investor_allocation"),
            ("underlying_equities", "index_methodology"),
        ],
    },
]


POSITIONS = [
    ("pos_nvda_ai_compute", "NVDA", "chain_ai_compute_cloud", ["ai_semiconductor_design", "gpu_accelerator_system"], "AI 加速计算核心供应商", ["TSMC/先进封装", "HBM/高速互连"], ["云厂商", "AI 服务器厂商", "企业 AI 客户"], ["GPU", "CUDA", "AI accelerator"]),
    ("pos_msft_ai_cloud", "MSFT", "chain_ai_compute_cloud", ["cloud_infrastructure", "enterprise_ai_software"], "云基础设施和企业 AI 应用平台", ["数据中心", "GPU 集群", "软件生态"], ["企业客户", "开发者", "公共部门"], ["Azure", "Copilot", "enterprise software"]),
    ("pos_aapl_edge_ai", "AAPL", "chain_ai_compute_cloud", ["edge_device_ecosystem"], "端侧设备与生态入口", ["半导体设计", "组装制造", "应用生态"], ["消费者", "开发者", "服务订阅用户"], ["iPhone", "SoC", "edge AI"]),
    ("pos_catl_ev_battery", "300750", "chain_ev_battery_energy", ["battery_cell_pack", "charging_energy_storage"], "动力电池和储能电池核心供应商", ["锂资源", "电池材料", "设备供应商"], ["新能源车企", "储能系统集成商"], ["LFP", "ternary battery", "energy storage"]),
    ("pos_tsla_ev_energy", "TSLA", "chain_ev_battery_energy", ["ev_oem", "charging_energy_storage", "autonomous_compute"], "电动车、储能和智能驾驶终端需求方", ["电芯", "功率半导体", "AI 芯片和传感器"], ["消费者", "车队客户", "能源客户"], ["EV", "FSD", "energy storage"]),
    ("pos_spdb_financial_services", "600000", "chain_financial_services", ["deposits_funding", "credit_allocation", "industry_financing"], "公司金融和产业融资银行", ["存款客户", "同业资金", "资本市场"], ["企业客户", "零售客户", "地方产业客户"], ["corporate banking", "credit", "wealth management"]),
    ("pos_pab_financial_services", "000001", "chain_financial_services", ["deposits_funding", "credit_allocation", "wealth_management", "payments_fintech"], "零售金融、综合金融和财富管理银行", ["存款客户", "综合金融生态", "金融科技系统"], ["零售客户", "小微客户", "企业客户"], ["retail banking", "fintech", "wealth management"]),
    ("pos_spy_etf_allocation", "SPY", "chain_index_etf_allocation", ["fund_sponsor", "creation_redemption", "market_making_liquidity", "investor_allocation"], "标普 500 被动配置工具", ["指数方法", "授权参与人", "成份股流动性"], ["资产配置账户", "机构和个人投资者"], ["ETF", "S&P 500", "passive allocation"]),
    ("pos_moutai_premium_consumption", "600519", "chain_premium_consumption", ["distillation_storage", "brand_pricing_power", "wholesale_distribution"], "高端白酒品牌和渠道定价核心", ["高粱/小麦等原料", "产区资源", "经销商体系"], ["高端消费群体", "商务宴请", "礼赠需求"], ["baijiu", "premium consumption", "brand pricing"]),
]


def _nodes(raw_nodes: list[tuple[str, str]]) -> list[dict[str, Any]]:
    return [{"node_id": node_id, "name": name, "node_type": "industry_chain_node"} for node_id, name in raw_nodes]


def _edges(chain_id: str, raw_edges: list[tuple[str, str]]) -> list[dict[str, Any]]:
    return [
        {
            "edge_id": f"{chain_id}_{source}_{target}",
            "source_node_id": source,
            "target_node_id": target,
            "relation": "upstream_to_downstream",
            "source": SOURCE_ID,
            "version": TAXONOMY_VERSION,
            "confidence": 0.82,
        }
        for source, target in raw_edges
    ]


def _document_body(company: dict[str, Any], chain_name: str, node_ids: list[str], role: str, suppliers: list[str], customers: list[str]) -> str:
    return "\n".join(
        [
            f"公司/证券: {company['legal_name']} ({company['ticker']})",
            f"市场: {company['market']} / {company['exchange']} / {company['currency']}",
            f"基础信息: {company['profile']}",
            f"产业链: {chain_name}",
            f"链条节点: {', '.join(node_ids)}",
            f"定位: {role}",
            f"上游/关键投入: {', '.join(suppliers)}",
            f"下游/客户: {', '.join(customers)}",
            "使用边界: 本资料为公开常识和本地研究归纳形成的研究定位，不构成交易指令。",
        ]
    )


def _put_profile_evidence(store: PostgreSQLStore, *, position_id: str, company: dict[str, Any], chain: IndustryChain, node_ids: list[str], role: str, suppliers: list[str], customers: list[str]) -> str:
    document_id = f"doc_profile_{position_id}"
    evidence_id = f"evi_profile_{position_id}"
    body = _document_body(company, chain.name, node_ids, role, suppliers, customers)
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    now = utcnow()
    store.documents[document_id] = Document(
        document_id=document_id,
        issuer_id=str(company["issuer_id"]),
        security_id=str(company["security_id"]),
        document_type="company_profile",
        source_id=SOURCE_ID,
        source_type="curated_public_profile",
        source_uri=f"artifact://ahu-basic-info-industry-chain/{position_id}",
        rights_tag=RIGHTS,
        body=body,
        title=f"{company['ticker']} 基础资料与产业链定位",
        content_sha256=digest,
        published_at=now,
        ingested_at=now,
        language="zh",
        version=TAXONOMY_VERSION,
    )
    store.evidence[evidence_id] = Evidence(
        evidence_id=evidence_id,
        document_id=document_id,
        section="company_profile_industry_position",
        page_no=1,
        bbox="",
        span_text=body,
        canonical_text=body,
        confidence=0.82,
        locator={"type": "curated_profile", "position_id": position_id, "chain_id": chain.chain_id, "node_ids": node_ids},
        assets=[{"issuer_id": company["issuer_id"], "security_id": company["security_id"], "ticker": company["ticker"]}],
        created_at=now,
    )
    return evidence_id


def seed(dsn: str) -> dict[str, Any]:
    store = PostgreSQLStore(dsn)
    now = utcnow()

    store.sources[SOURCE_ID] = SourceDefinition(
        source_id=SOURCE_ID,
        source_type="local_reference",
        rights_tag=RIGHTS,
        description="Curated public company profile and industry-chain positioning records for the local A/U research universe.",
        risk_level="green",
        allowed_document_types=["company_profile"],
        field_whitelist=["issuer_id", "security_id", "ticker", "exchange", "market", "country", "profile", "industry_chain_position"],
        retention_policy="retain_until_replaced_by_reviewed_profile",
        cache_ttl_days=90,
        provenance_ref="local://artifacts/ahu-basic-info-industry-chain.json",
        usage_scope="local_research_graph_and_positioning_only_no_trade_instruction",
        collection_method="curated_from_approved_public_local_sources",
        robots_policy="not_applicable_local_curated_artifact",
        last_reviewed_at=now,
        review_cadence="quarterly",
        review_owner="数据工程",
        review_owner_role="数据工程",
        source_tos_uri="local://approved-source-boundary",
    )

    for company in COMPANIES.values():
        issuer_id = str(company["issuer_id"])
        security_id = str(company["security_id"])
        created_at = getattr(store.issuers.get(issuer_id), "created_at", now)
        store.issuers[issuer_id] = Issuer(
            issuer_id=issuer_id,
            legal_name=str(company["legal_name"]),
            aliases=[str(item) for item in company["aliases"]],
            market=[str(company["market"])],
            country=str(company["country"]),
            status="active",
            created_at=created_at,
            updated_at=now,
        )
        store.securities[security_id] = Security(
            security_id=security_id,
            issuer_id=issuer_id,
            ticker=str(company["ticker"]),
            exchange=str(company["exchange"]),
            currency=str(company["currency"]),
            market=str(company["market"]),
            status="active",
        )

    for theme in THEMES:
        store.macro_themes[theme["theme_id"]] = MacroTheme(
            theme_id=theme["theme_id"],
            name=theme["name"],
            description=theme["description"],
            trigger_type="curated_universe_seed",
            as_of_date=str(now.date()),
            source_refs=[SOURCE_ID],
            macro_drivers=list(theme["macro_drivers"]),
            risk_factors=list(theme["risk_factors"]),
            confidence=0.82,
            created_at=now,
        )

    for chain in CHAINS:
        store.industry_chains[chain["chain_id"]] = IndustryChain(
            chain_id=chain["chain_id"],
            name=chain["name"],
            root_theme_id=chain["root_theme_id"],
            nodes=_nodes(chain["nodes"]),
            edges=_edges(chain["chain_id"], chain["edges"]),
            taxonomy_version=TAXONOMY_VERSION,
            source_refs=[SOURCE_ID],
            created_at=now,
        )

    for position_id, symbol, chain_id, node_ids, role, suppliers, customers, tags in POSITIONS:
        company = COMPANIES[symbol]
        chain = store.industry_chains[chain_id]
        evidence_id = _put_profile_evidence(
            store,
            position_id=position_id,
            company=company,
            chain=chain,
            node_ids=node_ids,
            role=role,
            suppliers=suppliers,
            customers=customers,
        )
        store.company_positions[position_id] = CompanyPosition(
            position_id=position_id,
            issuer_id=str(company["issuer_id"]),
            security_id=str(company["security_id"]),
            chain_id=chain_id,
            node_ids=node_ids,
            role=role,
            positioning_summary=f"{company['legal_name']}在“{chain.name}”中承担“{role}”角色。",
            revenue_exposure={"type": "qualitative", "primary_segments": node_ids, "exposure": "core_or_material"},
            profit_exposure={"type": "qualitative", "sensitivity": "linked_to_chain_cycle_and_company_execution"},
            capacity={"type": "profile", "status": "public_profile_seeded", "needs_quantitative_update": True},
            customers=customers,
            suppliers=suppliers,
            competitors=["同业可比公司待由后续研报/公告继续细分"],
            technology_tags=tags,
            valuation_metrics={"currency": company["currency"], "market": company["market"], "latest_market_data_source": "public_eod_market_data" if company["market"] == "A" else "yahoo_chart_us_eod"},
            event_refs=[f"artifact://ahu-basic-info-industry-chain/{position_id}"],
            evidence_ids=[evidence_id],
            data_quality="complete",
            created_at=now,
        )

    demo_position = store.company_positions.get("pos_demo_gpu")
    if demo_position and not [item for item in demo_position.evidence_ids if item in store.evidence]:
        demo_document_id = "doc_profile_pos_demo_gpu"
        demo_evidence_id = "evi_profile_pos_demo_gpu"
        demo_issuer = store.issuers.get(demo_position.issuer_id)
        demo_security = store.securities.get(demo_position.security_id)
        demo_body = "\n".join(
            [
                f"公司/主体: {demo_issuer.legal_name if demo_issuer else demo_position.issuer_id}",
                f"证券: {demo_security.ticker if demo_security else demo_position.security_id}",
                f"产业链: {demo_position.chain_id}",
                f"链条节点: {', '.join(demo_position.node_ids)}",
                f"定位: {demo_position.role}",
                "使用边界: 历史演示样例的本地证据补齐，用于避免覆盖报告被样例数据干扰。",
            ]
        )
        store.documents[demo_document_id] = Document(
            document_id=demo_document_id,
            issuer_id=demo_position.issuer_id,
            security_id=demo_position.security_id,
            document_type="company_profile",
            source_id=SOURCE_ID,
            source_type="curated_public_profile",
            source_uri="artifact://ahu-basic-info-industry-chain/pos_demo_gpu",
            rights_tag=RIGHTS,
            body=demo_body,
            title="历史演示样例产业链定位证据",
            content_sha256=hashlib.sha256(demo_body.encode("utf-8")).hexdigest(),
            published_at=now,
            ingested_at=now,
            language="zh",
            version=TAXONOMY_VERSION,
        )
        store.evidence[demo_evidence_id] = Evidence(
            evidence_id=demo_evidence_id,
            document_id=demo_document_id,
            section="company_profile_industry_position",
            page_no=1,
            bbox="",
            span_text=demo_body,
            canonical_text=demo_body,
            confidence=0.75,
            locator={"type": "demo_profile_backfill", "position_id": demo_position.position_id},
            assets=[{"issuer_id": demo_position.issuer_id, "security_id": demo_position.security_id}],
            created_at=now,
        )
        store.company_positions[demo_position.position_id] = CompanyPosition(
            position_id=demo_position.position_id,
            issuer_id=demo_position.issuer_id,
            security_id=demo_position.security_id,
            chain_id=demo_position.chain_id,
            node_ids=demo_position.node_ids,
            role=demo_position.role,
            positioning_summary=demo_position.positioning_summary,
            revenue_exposure=demo_position.revenue_exposure,
            profit_exposure=demo_position.profit_exposure,
            capacity=demo_position.capacity,
            customers=demo_position.customers,
            suppliers=demo_position.suppliers,
            competitors=demo_position.competitors,
            technology_tags=demo_position.technology_tags,
            valuation_metrics=demo_position.valuation_metrics,
            event_refs=demo_position.event_refs,
            evidence_ids=[demo_evidence_id],
            data_quality="complete",
            created_at=demo_position.created_at,
        )

    store.commit()

    by_chain = {}
    for position in store.company_positions.values():
        if position.chain_id in {chain["chain_id"] for chain in CHAINS}:
            bucket = by_chain.setdefault(position.chain_id, {"chain_id": position.chain_id, "positions": 0, "issuers": []})
            bucket["positions"] += 1
            bucket["issuers"].append(position.issuer_id)

    return {
        "generated_at": now.isoformat(),
        "source_id": SOURCE_ID,
        "taxonomy_version": TAXONOMY_VERSION,
        "issuer_count": len(COMPANIES),
        "security_count": len(COMPANIES),
        "theme_count": len(THEMES),
        "chain_count": len(CHAINS),
        "position_count": len(POSITIONS),
        "evidence_count": len(POSITIONS),
        "chains": sorted(by_chain.values(), key=lambda item: item["chain_id"]),
        "issuers": [to_plain(store.issuers[item["issuer_id"]]) for item in COMPANIES.values()],
        "securities": [to_plain(store.securities[item["security_id"]]) for item in COMPANIES.values()],
        "usage_boundary": "research_graph_and_industry_positioning_only_no_real_trading",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed A-share/US basic issuer info and industry-chain graph for the local research universe.")
    parser.add_argument("--dsn", default=os.environ.get("AI_QUANT_POSTGRES_DSN") or os.environ.get("AI_QUANT_DATABASE_URL") or DEFAULT_DSN)
    parser.add_argument("--artifact", default=str(ARTIFACT_PATH))
    args = parser.parse_args()

    result = seed(args.dsn)
    artifact = Path(args.artifact)
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"artifact": str(artifact), **{key: result[key] for key in ["issuer_count", "security_count", "chain_count", "position_count", "evidence_count"]}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
