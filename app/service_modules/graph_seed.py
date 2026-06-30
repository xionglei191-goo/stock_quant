from __future__ import annotations

from typing import Any, Protocol

from app.errors import ConflictError
from app.utils import to_plain


class KnowledgeGraphSeedService(Protocol):
    store: Any

    def seed_default_sources(self, *, actor: str = "system") -> list[Any]: ...
    def register_source(self, payload: dict[str, Any], *, actor: str = "system") -> Any: ...
    def register_issuer(self, payload: dict[str, Any], *, actor: str = "system") -> Any: ...
    def register_security(self, payload: dict[str, Any], *, actor: str = "system") -> Any: ...
    def ingest_document(self, payload: dict[str, Any], *, actor: str = "system") -> Any: ...
    def register_industry_chain(self, payload: dict[str, Any], *, actor: str = "system") -> Any: ...
    def register_company_position(self, chain_id: str, payload: dict[str, Any], *, actor: str = "system") -> Any: ...
    def register_company_relationship(self, payload: dict[str, Any], *, actor: str = "system") -> Any: ...
    def register_company_event(self, payload: dict[str, Any], *, actor: str = "system") -> Any: ...
    def register_structured_research_report(self, payload: dict[str, Any], *, actor: str = "system") -> Any: ...
    def register_report_viewpoint(self, payload: dict[str, Any], *, actor: str = "system") -> Any: ...
    def register_13f_holding(self, payload: dict[str, Any], *, actor: str = "system") -> Any: ...


OBSIDIAN_GRAPH_COMPANIES: list[dict[str, Any]] = [
    {"issuer_id": "issuer_aapl", "security_id": "security_aapl_us", "ticker": "AAPL", "legal_name": "Apple Inc.", "country": "US", "market": "U", "exchange": "NASDAQ", "currency": "USD"},
    {"issuer_id": "issuer_nvda", "security_id": "security_nvda_us", "ticker": "NVDA", "legal_name": "NVIDIA Corporation", "country": "US", "market": "U", "exchange": "NASDAQ", "currency": "USD"},
    {"issuer_id": "issuer_msft", "security_id": "security_msft_us", "ticker": "MSFT", "legal_name": "Microsoft Corporation", "country": "US", "market": "U", "exchange": "NASDAQ", "currency": "USD"},
    {"issuer_id": "issuer_tsm", "security_id": "security_tsm_us", "ticker": "TSM", "legal_name": "Taiwan Semiconductor Manufacturing Company Limited", "country": "TW", "market": "U", "exchange": "NYSE", "currency": "USD"},
    {"issuer_id": "issuer_asml", "security_id": "security_asml_us", "ticker": "ASML", "legal_name": "ASML Holding N.V.", "country": "NL", "market": "U", "exchange": "NASDAQ", "currency": "USD"},
    {"issuer_id": "issuer_avgo", "security_id": "security_avgo_us", "ticker": "AVGO", "legal_name": "Broadcom Inc.", "country": "US", "market": "U", "exchange": "NASDAQ", "currency": "USD"},
    {"issuer_id": "issuer_600519", "security_id": "sec_600519", "ticker": "600519", "legal_name": "贵州茅台酒股份有限公司", "country": "CN", "market": "A", "exchange": "SSE", "currency": "CNY"},
    {"issuer_id": "issuer_600809", "security_id": "sec_600809", "ticker": "600809", "legal_name": "山西汾酒股份有限公司", "country": "CN", "market": "A", "exchange": "SSE", "currency": "CNY"},
]


OBSIDIAN_GRAPH_CHAIN: dict[str, Any] = {
    "chain_id": "chain_obsidian_ai_device_network",
    "name": "AI 端侧设备与算力产业链",
    "nodes": [
        {"node_id": "equipment", "name": "半导体设备", "level": "upstream", "category": "equipment"},
        {"node_id": "foundry", "name": "晶圆代工", "level": "upstream", "category": "foundry"},
        {"node_id": "accelerator", "name": "AI 加速器", "level": "midstream", "category": "compute"},
        {"node_id": "connectivity", "name": "连接与定制芯片", "level": "midstream", "category": "connectivity"},
        {"node_id": "edge_device", "name": "端侧设备", "level": "downstream", "category": "device"},
        {"node_id": "cloud_service", "name": "云与应用服务", "level": "downstream", "category": "service"},
    ],
    "edges": [
        {"source_node_id": "equipment", "target_node_id": "foundry", "relation_type": "upstream_of", "confidence": 0.82},
        {"source_node_id": "foundry", "target_node_id": "accelerator", "relation_type": "upstream_of", "confidence": 0.84},
        {"source_node_id": "foundry", "target_node_id": "connectivity", "relation_type": "upstream_of", "confidence": 0.78},
        {"source_node_id": "accelerator", "target_node_id": "cloud_service", "relation_type": "downstream_of", "confidence": 0.8},
        {"source_node_id": "connectivity", "target_node_id": "edge_device", "relation_type": "downstream_of", "confidence": 0.76},
        {"source_node_id": "edge_device", "target_node_id": "cloud_service", "relation_type": "downstream_of", "confidence": 0.66},
    ],
    "taxonomy_version": "obsidian-knowledge-network-seed-v1",
    "source_refs": ["local://knowledge-graph-seed/obsidian"],
}


OBSIDIAN_GRAPH_POSITIONS: list[dict[str, Any]] = [
    {"position_id": "pos_obsidian_aapl_edge_device", "issuer_id": "issuer_aapl", "security_id": "security_aapl_us", "node_ids": ["edge_device", "cloud_service"], "role": "端侧设备与服务生态", "data_quality": "local_seed_needs_review"},
    {"position_id": "pos_obsidian_nvda_accelerator", "issuer_id": "issuer_nvda", "security_id": "security_nvda_us", "node_ids": ["accelerator"], "role": "AI 加速器核心供应商", "data_quality": "local_seed_needs_review"},
    {"position_id": "pos_obsidian_msft_cloud", "issuer_id": "issuer_msft", "security_id": "security_msft_us", "node_ids": ["cloud_service"], "role": "云与应用服务平台", "data_quality": "local_seed_needs_review"},
    {"position_id": "pos_obsidian_tsm_foundry", "issuer_id": "issuer_tsm", "security_id": "security_tsm_us", "node_ids": ["foundry"], "role": "先进制程晶圆代工", "data_quality": "local_seed_needs_review"},
    {"position_id": "pos_obsidian_asml_equipment", "issuer_id": "issuer_asml", "security_id": "security_asml_us", "node_ids": ["equipment"], "role": "先进半导体设备", "data_quality": "local_seed_needs_review"},
    {"position_id": "pos_obsidian_avgo_connectivity", "issuer_id": "issuer_avgo", "security_id": "security_avgo_us", "node_ids": ["connectivity", "accelerator"], "role": "连接与定制芯片", "data_quality": "local_seed_needs_review"},
    {"position_id": "pos_obsidian_600519_baijiu", "issuer_id": "issuer_600519", "security_id": "sec_600519", "node_ids": ["edge_device"], "role": "消费龙头对照样本", "data_quality": "local_seed_needs_review"},
    {"position_id": "pos_obsidian_600809_baijiu_peer", "issuer_id": "issuer_600809", "security_id": "sec_600809", "node_ids": ["edge_device"], "role": "消费同类公司对照样本", "data_quality": "local_seed_needs_review"},
]


OBSIDIAN_GRAPH_13F_HOLDINGS: list[dict[str, Any]] = [
    {"holding_id": "hold_obsidian_vanguard_aapl", "issuer_id": "issuer_aapl", "security_id": "security_aapl_us", "filer_cik": "0000102909", "filer_name": "Vanguard Group Inc.", "shares": 1320000000, "value_usd": 250000000000},
    {"holding_id": "hold_obsidian_vanguard_nvda", "issuer_id": "issuer_nvda", "security_id": "security_nvda_us", "filer_cik": "0000102909", "filer_name": "Vanguard Group Inc.", "shares": 210000000, "value_usd": 180000000000},
    {"holding_id": "hold_obsidian_vanguard_msft", "issuer_id": "issuer_msft", "security_id": "security_msft_us", "filer_cik": "0000102909", "filer_name": "Vanguard Group Inc.", "shares": 640000000, "value_usd": 280000000000},
    {"holding_id": "hold_obsidian_berkshire_aapl", "issuer_id": "issuer_aapl", "security_id": "security_aapl_us", "filer_cik": "0001067983", "filer_name": "Berkshire Hathaway Inc.", "shares": 790000000, "value_usd": 150000000000},
    {"holding_id": "hold_obsidian_berkshire_tsm", "issuer_id": "issuer_tsm", "security_id": "security_tsm_us", "filer_cik": "0001067983", "filer_name": "Berkshire Hathaway Inc.", "shares": 60000000, "value_usd": 10000000000},
]


OBSIDIAN_GRAPH_DOCUMENT_RIGHTS: dict[str, Any] = {
    "license_class": "public",
    "training_allowed": False,
    "redistribution_allowed": False,
    "display_use": "allowed",
    "non_display_use": "restricted",
    "derived_data_use": "restricted",
}


OBSIDIAN_GRAPH_SOURCE: dict[str, Any] = {
    "source_id": "obsidian_knowledge_graph_seed",
    "source_type": "local_seed",
    "description": "Local seed notes for Obsidian-style knowledge graph acceptance; not production evidence.",
    "risk_level": "green",
    "allowed_document_types": ["company_note", "theme_note"],
    "provenance_ref": "local://knowledge-graph-seed/obsidian",
    "usage_scope": "local_graph_acceptance_only_not_training_not_redistribution",
    "rights_tag": OBSIDIAN_GRAPH_DOCUMENT_RIGHTS,
}


OBSIDIAN_GRAPH_DOCUMENTS: list[dict[str, Any]] = [
    {
        "document_id": "doc_obsidian_aapl_ai_device_note",
        "issuer_id": "issuer_aapl",
        "security_id": "security_aapl_us",
        "document_type": "company_note",
        "source_id": "obsidian_knowledge_graph_seed",
        "source_type": "local_seed",
        "source_uri": "local://knowledge-graph-seed/apple-ai-device-note",
        "rights_tag": OBSIDIAN_GRAPH_DOCUMENT_RIGHTS,
        "title": "Apple AI device ecosystem knowledge note",
        "body": "Local seed note: Apple connects edge devices, cloud services, silicon supply, and 13F holder context. Opinion and fact layers stay separated.",
        "published_at": "2026-06-29T00:00:00Z",
        "language": "en",
        "chain_id": "chain_obsidian_ai_device_network",
        "node_ids": ["edge_device", "cloud_service"],
    },
    {
        "document_id": "doc_obsidian_aapl_supply_chain_note",
        "issuer_id": "issuer_aapl",
        "security_id": "security_aapl_us",
        "document_type": "company_note",
        "source_id": "obsidian_knowledge_graph_seed",
        "source_type": "local_seed",
        "source_uri": "local://knowledge-graph-seed/apple-supply-chain-note",
        "rights_tag": OBSIDIAN_GRAPH_DOCUMENT_RIGHTS,
        "title": "Apple upstream supply-chain knowledge note",
        "body": "Local seed note: Apple edge-device analysis should connect to upstream foundry, connectivity, and accelerator ecosystem nodes instead of remaining a one-company note.",
        "published_at": "2026-06-29T00:00:00Z",
        "language": "en",
        "chain_id": "chain_obsidian_ai_device_network",
        "node_ids": ["foundry", "connectivity", "accelerator"],
    },
    {
        "document_id": "doc_obsidian_nvda_accelerator_note",
        "issuer_id": "issuer_nvda",
        "security_id": "security_nvda_us",
        "document_type": "company_note",
        "source_id": "obsidian_knowledge_graph_seed",
        "source_type": "local_seed",
        "source_uri": "local://knowledge-graph-seed/nvidia-accelerator-note",
        "rights_tag": OBSIDIAN_GRAPH_DOCUMENT_RIGHTS,
        "title": "NVIDIA accelerator ecosystem knowledge note",
        "body": "Local seed note: NVIDIA maps to AI accelerator demand, foundry dependencies, connectivity peers, and holder-network overlap.",
        "published_at": "2026-06-29T00:00:00Z",
        "language": "en",
        "chain_id": "chain_obsidian_ai_device_network",
        "node_ids": ["accelerator"],
    },
    {
        "document_id": "doc_obsidian_msft_cloud_note",
        "issuer_id": "issuer_msft",
        "security_id": "security_msft_us",
        "document_type": "company_note",
        "source_id": "obsidian_knowledge_graph_seed",
        "source_type": "local_seed",
        "source_uri": "local://knowledge-graph-seed/microsoft-cloud-note",
        "rights_tag": OBSIDIAN_GRAPH_DOCUMENT_RIGHTS,
        "title": "Microsoft cloud service knowledge note",
        "body": "Local seed note: Microsoft is the downstream cloud-service node connected to AI infrastructure demand and Vanguard same-holder context.",
        "published_at": "2026-06-29T00:00:00Z",
        "language": "en",
        "chain_id": "chain_obsidian_ai_device_network",
        "node_ids": ["cloud_service"],
    },
]


OBSIDIAN_GRAPH_EVENTS: list[dict[str, Any]] = [
    {
        "event_id": "event_obsidian_aapl_on_device_ai",
        "issuer_id": "issuer_aapl",
        "security_id": "security_aapl_us",
        "event_type": "product_strategy",
        "title": "Apple on-device AI ecosystem watch",
        "summary": "Local seed event connecting Apple edge-device position to cloud-service and silicon supply-chain questions.",
        "occurred_at": "2026-06-29T00:00:00Z",
        "source_ids": ["obsidian_knowledge_graph_seed"],
        "document_ids": ["doc_obsidian_aapl_ai_device_note", "doc_obsidian_aapl_supply_chain_note"],
        "impact_tags": ["edge_device", "cloud_service", "ai_device"],
        "affected_entities": [{"issuer_id": "issuer_nvda"}, {"issuer_id": "issuer_tsm"}, {"issuer_id": "issuer_msft"}],
        "confidence": 0.62,
        "fact_status": "local_seed_reference",
        "review_status": "needs_review",
        "metadata": {"source_layer": "obsidian_knowledge_graph_seed", "chain_id": "chain_obsidian_ai_device_network"},
    },
    {
        "event_id": "event_obsidian_nvda_accelerator_demand",
        "issuer_id": "issuer_nvda",
        "security_id": "security_nvda_us",
        "event_type": "demand_signal",
        "title": "NVIDIA accelerator demand watch",
        "summary": "Local seed event connecting accelerator demand to foundry capacity, cloud service demand, and same-holder network context.",
        "occurred_at": "2026-06-29T00:00:00Z",
        "source_ids": ["obsidian_knowledge_graph_seed"],
        "document_ids": ["doc_obsidian_nvda_accelerator_note"],
        "impact_tags": ["accelerator", "foundry", "cloud_service"],
        "affected_entities": [{"issuer_id": "issuer_tsm"}, {"issuer_id": "issuer_msft"}, {"issuer_id": "issuer_aapl"}],
        "confidence": 0.62,
        "fact_status": "local_seed_reference",
        "review_status": "needs_review",
        "metadata": {"source_layer": "obsidian_knowledge_graph_seed", "chain_id": "chain_obsidian_ai_device_network"},
    },
]


OBSIDIAN_GRAPH_STRUCTURED_REPORTS: list[dict[str, Any]] = [
    {
        "research_report_id": "srr_obsidian_aapl_ai_device",
        "document_id": "doc_obsidian_aapl_ai_device_note",
        "title": "Apple AI device ecosystem thesis note",
        "institution_id": "local_seed_research",
        "institution_name": "Local Seed Research",
        "analyst_ids": ["analyst_obsidian_seed"],
        "analyst_names": ["Obsidian Seed Analyst"],
        "issuer_id": "issuer_aapl",
        "security_id": "security_aapl_us",
        "covered_entities": [{"issuer_id": "issuer_aapl", "security_id": "security_aapl_us"}],
        "report_type": "theme_note",
        "language": "en",
        "source_id": "local_research_reports",
        "source_uri": "local://knowledge-graph-seed/apple-ai-device-thesis",
        "rights_boundary": "opinion_only_not_fact_source",
        "published_at": "2026-06-29T00:00:00Z",
        "rating": "not_rated",
        "summary": "Local seed opinion: Apple is a downstream edge-device and service ecosystem node, with upstream sensitivity to accelerator, foundry, and connectivity capacity.",
        "parser_status": "parsed",
        "realization_status": "pending",
    },
    {
        "research_report_id": "srr_obsidian_nvda_accelerator",
        "document_id": "doc_obsidian_nvda_accelerator_note",
        "title": "NVIDIA accelerator ecosystem thesis note",
        "institution_id": "local_seed_research",
        "institution_name": "Local Seed Research",
        "analyst_ids": ["analyst_obsidian_seed"],
        "analyst_names": ["Obsidian Seed Analyst"],
        "issuer_id": "issuer_nvda",
        "security_id": "security_nvda_us",
        "covered_entities": [{"issuer_id": "issuer_nvda", "security_id": "security_nvda_us"}],
        "report_type": "theme_note",
        "language": "en",
        "source_id": "local_research_reports",
        "source_uri": "local://knowledge-graph-seed/nvidia-accelerator-thesis",
        "rights_boundary": "opinion_only_not_fact_source",
        "published_at": "2026-06-29T00:00:00Z",
        "rating": "not_rated",
        "summary": "Local seed opinion: NVIDIA is a central accelerator node linked to foundry supply, connectivity peers, cloud-service demand, and holder concentration context.",
        "parser_status": "parsed",
        "realization_status": "pending",
    },
]


OBSIDIAN_GRAPH_VIEWPOINTS: list[dict[str, Any]] = [
    {
        "viewpoint_id": "vp_obsidian_aapl_device_cloud",
        "research_report_id": "srr_obsidian_aapl_ai_device",
        "issuer_id": "issuer_aapl",
        "security_id": "security_aapl_us",
        "viewpoint_type": "industry_position",
        "stance": "constructive",
        "statement": "Apple should be explored as an edge-device and cloud-service demand node rather than as an isolated listed security.",
        "core_assumptions": ["edge_device demand matters", "cloud_service attachment matters", "upstream silicon capacity matters"],
        "catalysts": ["on-device AI feature adoption", "services attach-rate expansion"],
        "risks": ["supply constraints", "weak device replacement cycle"],
        "notes": "Local seed opinion layer; not a trading signal.",
    },
    {
        "viewpoint_id": "vp_obsidian_nvda_foundry_cloud",
        "research_report_id": "srr_obsidian_nvda_accelerator",
        "issuer_id": "issuer_nvda",
        "security_id": "security_nvda_us",
        "viewpoint_type": "industry_position",
        "stance": "constructive",
        "statement": "NVIDIA should be explored through accelerator demand, foundry upstream constraints, and cloud-service downstream adoption.",
        "core_assumptions": ["accelerator demand stays strong", "foundry capacity remains strategic", "cloud service demand links to accelerator utilization"],
        "catalysts": ["AI infrastructure capex", "new accelerator cycles"],
        "risks": ["capacity bottlenecks", "cloud demand digestion"],
        "notes": "Local seed opinion layer; not a trading signal.",
    },
]


def _record(operation: str, record_id: str, status: str, row: Any | None = None) -> dict[str, Any]:
    return {"operation": operation, "id": record_id, "status": status, "record": to_plain(row) if row is not None else {}}


def _register_once(operations: list[dict[str, Any]], operation: str, record_id: str, callback: Any) -> None:
    try:
        row = callback()
    except ConflictError:
        operations.append(_record(operation, record_id, "already_exists"))
        return
    operations.append(_record(operation, record_id, "created", row))


def seed_obsidian_knowledge_graph(service: KnowledgeGraphSeedService, *, actor: str = "system") -> dict[str, Any]:
    service.seed_default_sources(actor=actor)
    operations: list[dict[str, Any]] = []
    _register_once(operations, "source", OBSIDIAN_GRAPH_SOURCE["source_id"], lambda: service.register_source(OBSIDIAN_GRAPH_SOURCE, actor=actor))

    for company in OBSIDIAN_GRAPH_COMPANIES:
        issuer_payload = {
            "issuer_id": company["issuer_id"],
            "legal_name": company["legal_name"],
            "aliases": [company["ticker"]],
            "market": [company["market"]],
            "country": company["country"],
            "status": "active",
        }
        _register_once(operations, "issuer", company["issuer_id"], lambda payload=issuer_payload: service.register_issuer(payload, actor=actor))
        security_payload = {
            "security_id": company["security_id"],
            "issuer_id": company["issuer_id"],
            "ticker": company["ticker"],
            "exchange": company["exchange"],
            "currency": company["currency"],
            "market": company["market"],
            "status": "active",
        }
        _register_once(operations, "security", company["security_id"], lambda payload=security_payload: service.register_security(payload, actor=actor))

    _register_once(operations, "industry_chain", OBSIDIAN_GRAPH_CHAIN["chain_id"], lambda: service.register_industry_chain(OBSIDIAN_GRAPH_CHAIN, actor=actor))

    for document in OBSIDIAN_GRAPH_DOCUMENTS:
        _register_once(operations, "document", document["document_id"], lambda payload=document: service.ingest_document(payload, actor=actor))

    for position in OBSIDIAN_GRAPH_POSITIONS:
        _register_once(
            operations,
            "company_position",
            position["position_id"],
            lambda payload=position: service.register_company_position(OBSIDIAN_GRAPH_CHAIN["chain_id"], payload, actor=actor),
        )

    for company in OBSIDIAN_GRAPH_COMPANIES:
        relationship_id = f"rel_obsidian_listing_{company['ticker'].lower()}"
        relationship_payload = {
            "relationship_id": relationship_id,
            "issuer_id": company["issuer_id"],
            "security_id": company["security_id"],
            "subject_type": "company",
            "subject_id": company["issuer_id"],
            "object_type": "security",
            "object_id": company["security_id"],
            "relationship_type": "listed_security",
            "relationship_status": "active",
            "review_status": "auto_generated",
            "confidence": 0.95,
            "metadata": {"source_layer": "obsidian_knowledge_graph_seed"},
        }
        _register_once(operations, "company_relationship", relationship_id, lambda payload=relationship_payload: service.register_company_relationship(payload, actor=actor))

    for event in OBSIDIAN_GRAPH_EVENTS:
        _register_once(operations, "company_event", event["event_id"], lambda payload=event: service.register_company_event(payload, actor=actor))

    for report in OBSIDIAN_GRAPH_STRUCTURED_REPORTS:
        _register_once(operations, "structured_research_report", report["research_report_id"], lambda payload=report: service.register_structured_research_report(payload, actor=actor))

    for viewpoint in OBSIDIAN_GRAPH_VIEWPOINTS:
        _register_once(operations, "report_viewpoint", viewpoint["viewpoint_id"], lambda payload=viewpoint: service.register_report_viewpoint(payload, actor=actor))

    for holding in OBSIDIAN_GRAPH_13F_HOLDINGS:
        payload = {
            **holding,
            "source_id": "sec_edgar",
            "report_period": "2026-03-31",
            "voting_authority": "shared",
        }
        _register_once(operations, "institutional_holding", holding["holding_id"], lambda row=payload: service.register_13f_holding(row, actor=actor))

    return {
        "status": "seeded",
        "schema_id": "obsidian-knowledge-graph-seed-result-v1",
        "operation_count": len(operations),
        "created_count": sum(1 for item in operations if item["status"] == "created"),
        "already_exists_count": sum(1 for item in operations if item["status"] == "already_exists"),
        "focus_symbols": ["AAPL", "NVDA", "MSFT", "600519"],
        "relationship_dimensions": ["industry_peer", "upstream_of", "downstream_of", "institutional_same_holder", "listed_security", "document_event_viewpoint"],
        "operations": operations,
        "usage_boundary": "local_seed_for_explorable_knowledge_graph_only_no_broker_no_trade_execution",
    }
