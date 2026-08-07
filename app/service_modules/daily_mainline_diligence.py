"""每日主线自动尽调的内置 LLM 模板集（纯函数领域模块）。

设计参考 `.kiro/specs/project-usability-improvement/design.md` §4.3 与 §9（风险 3）：

- 三类内置模板：`candidate_diligence`（候选尽调）、`evidence_summary`（证据摘要）、
  `risk_challenge`（风险质询）（需求 4.1）。
- 每条模板 `status="approved"`、`prompt_version="daily-mainline-v1"`，因此编排调用既有
  `SystemService.run_llm_task` 时**不需要**传 `allow_unapproved` 绕过审批门（需求 4.7；
  design §9 风险 3 的落成要求）。
- `seed_specs` 只返回缺失模板的注册 payload，已存在则返回空列表，因此重复写入幂等
  （需求 4.2）。
- 写入通路复用既有 `SystemService.seed_default_llm_task_templates` 与既有路由
  `POST /api/llm/task-templates/seed`，本模块不新建 seed 通路，也不做 IO。

持久化边界（需求 4.7）：注册 payload 的键固定为 `TEMPLATE_PAYLOAD_FIELDS` 白名单，
凭据、签名 URL 与完整上游响应都不在白名单内，因此不可能随模板记录落盘；模板内容只含
prompt 文本与 schema 声明，不含任何密钥或上游响应体。

facade 接线注意（任务 10.1 消费本模块时）：

- `SystemService.register_llm_task_template` 在 `status="approved"` 时要求
  `approved_prompt_change_id` 指向一条已批准的 prompt change，payload 已带
  `baseline_prompt_change_id(template_id)` 作为该标识，facade 需先创建并批准同 id 的
  baseline prompt change（既有 `seed_default_llm_task_templates` 循环已是该模式）。
- 既有 seed 循环把 `prompt_version` 覆盖为 change_id，接线时必须保留 payload 自带的
  `prompt_version`（`item.get("prompt_version") or change_id`），否则本模块声明的
  `daily-mainline-v1` 会被改写。
- `run_llm_task` 只在 payload 显式带 `role` 时校验 `allowed_roles`；沿用既有内部调用方
  写法传 `role=DEFAULT_TEMPLATE_ROLE`（"分析师"），不要传 actor（`system` 不在
  `allowed_roles` 内会被拒）。
- 每类任务需要的 prompt 变量由 `required_variables(task_type)` 给出；`_render_llm_prompt`
  对未解析变量抛 `ValidationError`，facade 必须把这些变量全部填齐。

观点组装（任务 4.2，`build_viewpoint`）：

- 证据绑定只认调用方传入的**已存在**证据记录（`evidence` 与 `section=
  "research_report_citation"` 的研报引用证据），LLM 自称引用但不在候选集内的标识一律不绑定
  （需求 1.6）。
- 没有可绑定证据 → `diligence_status="unsupported"`、`partition="pending_evidence"`，不进主
  清单分区（需求 1.7）。
- 来源含研报（或含任何非事实来源）→ `source_layer="viewpoint"` 且 `fact_field_writes == []`；
  事实字段写入的来源类型恒为 `FACT_FIELD_SOURCE_TYPES` 的子集（需求 1.8）。
- 观点携带 `llm_task_run_id` / `template_id` / `prompt_version` / `model`（需求 1.5），文本只
  保留摘要（`MAX_SUMMARY_CHARS` 截断），**不复制** `LLMTaskRun.output` 的完整上游响应
  （需求 4.7）。
- `llm_output_text` 不可靠：非 JSON、带 ``` 围栏、JSON 混在自然语言里、空串都有降级路径，
  见 `parse_llm_output` 与 `PARSE_STATUSES`。
"""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from .daily_mainline_artifact import MAX_SUMMARY_LENGTH, is_sensitive_key, redact, truncate_text

PROMPT_VERSION = "daily-mainline-v1"
"""三类内置模板共用的 prompt 版本标识（需求 4.3 的 lineage 由 model + prompt_version 承载）。"""

TEMPLATE_STATUS = "approved"
"""seed 即 approved：编排不经 `allow_unapproved` 绕过审批门（design §9 风险 3）。"""

TASK_TYPES: tuple[str, ...] = ("candidate_diligence", "evidence_summary", "risk_challenge")

DEFAULT_TEMPLATE_ROLE = "分析师"
"""内部调用建议传入的模板角色，与既有 `run_llm_task` 调用方写法一致。"""

BASELINE_CHANGE_LEVEL = "baseline"
"""baseline prompt change 的 change_level，与既有 seed 循环一致。"""

DEFAULT_FALLBACK_CHAIN: tuple[str, ...] = ("rule_summary", "manual_review")
"""与既有模板一致：上游失败走 fallback 并落 `LLMTaskRun`，成功计数只认 `succeeded`。"""

DEFAULT_MAX_LATENCY_MS = 60000
"""SLA 上限。网关默认超时 120s，取 60s 既保留 SLA 信号又不让正常慢调用刷满复核队列。"""

TEMPLATE_PAYLOAD_FIELDS: tuple[str, ...] = (
    "template_id",
    "task_type",
    "prompt_name",
    "prompt_version",
    "content",
    "status",
    "approved_prompt_change_id",
    "provider",
    "fallback_chain",
    "data_domains",
    "allowed_roles",
    "risk_level",
    "input_schema",
    "output_schema",
    "max_latency_ms",
)
"""注册 payload 的字段白名单（需求 4.7：白名单外的键一律不进模板记录）。

`model` 有意留空不传：`run_llm_task` 会退回 `llm_gateway.default_model`，避免模板把
本机模型名写死。
"""

BUILTIN_TEMPLATES: tuple[dict[str, Any], ...] = (
    {
        "template_id": "tpl_daily_candidate_diligence",
        "task_type": "candidate_diligence",
        "prompt_name": "daily_candidate_diligence",
        "prompt_version": PROMPT_VERSION,
        "status": TEMPLATE_STATUS,
        "provider": "openai",
        "risk_level": "medium",
        "fallback_chain": list(DEFAULT_FALLBACK_CHAIN),
        "data_domains": ["public_market_data", "public_filing", "local_research_reference"],
        "allowed_roles": ["分析师", "海外研究负责人", "PM", "CIO"],
        "max_latency_ms": DEFAULT_MAX_LATENCY_MS,
        "content": (
            "你是本机每日主线研究助手，正在对当日异动候选做首轮尽调。\n"
            "候选：{{ticker}}（{{market}} 市场，标的 {{security_id}}）\n"
            "数据日期：{{as_of_date}}\n"
            "入选理由：{{selection_reason}}\n"
            "触发指标：{{trigger_digest}}\n"
            "公司建档完整度：{{completeness_digest}}\n"
            "可绑定证据（每行含 evidence_id 与出处）：\n"
            "{{evidence_digest}}\n\n"
            "硬性规则：\n"
            "- 不输出思维链或内部推理，只给可审计结论。\n"
            "- 每条判断必须引用上面列出的 evidence_id；缺证据写 needs_evidence，"
            "不得编造数字、链接、日期、份额或客户关系。\n"
            "- 研报与二手摘要只能作为观点线索，不得当作事实真相源。\n"
            "- 只做研究辅助，不得输出买入、卖出、仓位、目标价或实盘操作建议。\n"
            "只输出 JSON，字段为 viewpoint_summary、key_drivers、evidence_ids、"
            "open_questions、next_verification_tasks、usage_boundary。"
        ),
        "input_schema": {
            "required": [
                "ticker",
                "market",
                "security_id",
                "as_of_date",
                "selection_reason",
                "trigger_digest",
                "completeness_digest",
                "evidence_digest",
            ],
            "source_boundary": "evidence_backed",
        },
        "output_schema": {
            "required": [
                "viewpoint_summary",
                "key_drivers",
                "evidence_ids",
                "open_questions",
                "next_verification_tasks",
                "usage_boundary",
            ],
            "acceptance_thresholds": {
                "min_evidence_ids": 1,
                "max_unlinked_claims": 0,
                "human_review_required": True,
                "trade_recommendation_allowed": False,
            },
        },
    },
    {
        "template_id": "tpl_daily_evidence_summary",
        "task_type": "evidence_summary",
        "prompt_name": "daily_evidence_summary",
        "prompt_version": PROMPT_VERSION,
        "status": TEMPLATE_STATUS,
        "provider": "openai",
        "risk_level": "medium",
        "fallback_chain": list(DEFAULT_FALLBACK_CHAIN),
        "data_domains": ["public_filing", "local_research_reference"],
        "allowed_roles": ["分析师", "海外研究负责人", "CIO", "风险/合规"],
        "max_latency_ms": DEFAULT_MAX_LATENCY_MS,
        "content": (
            "你是证据摘要助手，只负责把已抽取的证据整理成可回链摘要。\n"
            "标的：{{ticker}}\n"
            "数据日期：{{as_of_date}}\n"
            "证据清单（每行含 evidence_id、来源类型与片段）：\n"
            "{{evidence_digest}}\n\n"
            "硬性规则：\n"
            "- 不输出思维链；每条摘要句都要标出其 evidence_id。\n"
            "- 严格区分事实与观点：官方披露与行情数据入 fact_claims，"
            "研报与二手材料入 viewpoint_claims。\n"
            "- 不得引入证据清单之外的信息，不得改写其中的数字或日期。\n"
            "- 单条引用片段不超过 1200 字符，摘要不得用于模型训练。\n"
            "只输出 JSON，字段为 evidence_summary、cited_evidence_ids、fact_claims、"
            "viewpoint_claims、usage_boundary。"
        ),
        "input_schema": {
            "required": ["ticker", "as_of_date", "evidence_digest"],
            "source_boundary": "public_or_local_reference",
        },
        "output_schema": {
            "required": [
                "evidence_summary",
                "cited_evidence_ids",
                "fact_claims",
                "viewpoint_claims",
                "usage_boundary",
            ],
            "acceptance_thresholds": {
                "min_cited_evidence_ids": 1,
                "max_citation_chars": 1200,
                "must_separate_fact_inference": True,
                "training_allowed": False,
            },
        },
    },
    {
        "template_id": "tpl_daily_risk_challenge",
        "task_type": "risk_challenge",
        "prompt_name": "daily_risk_challenge",
        "prompt_version": PROMPT_VERSION,
        "status": TEMPLATE_STATUS,
        "provider": "openai",
        "risk_level": "high",
        "fallback_chain": list(DEFAULT_FALLBACK_CHAIN),
        "data_domains": ["public_filing", "public_market_data", "local_research_reference"],
        "allowed_roles": ["分析师", "PM", "CIO", "风险/合规"],
        "max_latency_ms": DEFAULT_MAX_LATENCY_MS,
        "content": (
            "你是反方研究员，对当日候选观点做风险质询。\n"
            "标的：{{ticker}}\n"
            "数据日期：{{as_of_date}}\n"
            "待质询观点：{{viewpoint_summary}}\n"
            "证据清单（每行含 evidence_id）：\n"
            "{{evidence_digest}}\n\n"
            "硬性规则：\n"
            "- 不输出思维链；至少给出 2 条可验证的证伪条件。\n"
            "- 每条质询都要指向具体证据缺口或数据矛盾，并标注需要人工复核的项。\n"
            "- 不得把研报观点、二手线索或推断升级为已确认事实。\n"
            "- 只做研究辅助，不得输出买入、卖出、仓位、目标价或实盘操作建议。\n"
            "只输出 JSON，字段为 falsifiers、evidence_gaps、risk_flags、"
            "human_review_items、usage_boundary。"
        ),
        "input_schema": {
            "required": ["ticker", "as_of_date", "viewpoint_summary", "evidence_digest"],
            "source_boundary": "evidence_backed",
        },
        "output_schema": {
            "required": [
                "falsifiers",
                "evidence_gaps",
                "risk_flags",
                "human_review_items",
                "usage_boundary",
            ],
            "acceptance_thresholds": {
                "min_falsifiers": 2,
                "min_evidence_gaps": 1,
                "human_review_required": True,
                "max_unlinked_claims": 0,
            },
        },
    },
)

_VARIABLE_PATTERN = re.compile(r"\{\{\s*([A-Za-z0-9_.-]+)\s*\}\}")


def template_ids() -> tuple[str, ...]:
    """内置模板标识，按 `BUILTIN_TEMPLATES` 声明顺序。"""

    return tuple(str(template["template_id"]) for template in BUILTIN_TEMPLATES)


def builtin_template(task_type_or_id: str) -> dict[str, Any]:
    """按 `task_type` 或 `template_id` 取一条内置模板的副本；未命中抛 `KeyError`。"""

    key = str(task_type_or_id).strip()
    for template in BUILTIN_TEMPLATES:
        if key in {str(template["task_type"]), str(template["template_id"])}:
            return copy.deepcopy(template)
    raise KeyError(f"unknown builtin daily mainline template: {task_type_or_id}")


def required_variables(task_type_or_id: str) -> tuple[str, ...]:
    """该模板 prompt 需要的变量名（与 `content` 中的 `{{var}}` 占位符一致）。

    `SystemService._render_llm_prompt` 对未解析占位符抛 `ValidationError`，facade 用本函数
    确认变量填齐即可，无需再解析 prompt 文本。
    """

    template = builtin_template(task_type_or_id)
    return tuple(str(name) for name in template["input_schema"]["required"])


def content_variables(content: str) -> tuple[str, ...]:
    """prompt 文本中出现的占位符变量名（去重，按首次出现顺序）。"""

    seen: list[str] = []
    for name in _VARIABLE_PATTERN.findall(str(content or "")):
        if name not in seen:
            seen.append(name)
    return tuple(seen)


def baseline_prompt_change_id(template_id: str) -> str:
    """内置模板对应的 baseline prompt change 标识（沿用既有 seed 循环的命名）。"""

    return f"pr_{str(template_id).strip()}_baseline"


def _registration_payload(template: Mapping[str, Any]) -> dict[str, Any]:
    """把一条内置模板投影为 `register_llm_task_template` 可直接消费的 payload。

    只保留 `TEMPLATE_PAYLOAD_FIELDS` 白名单字段并深拷贝嵌套结构，因此返回值既不携带
    白名单外的键（需求 4.7），调用方修改返回值也不会污染模块常量。
    """

    template_id = str(template["template_id"])
    payload: dict[str, Any] = {}
    for field in TEMPLATE_PAYLOAD_FIELDS:
        if field == "approved_prompt_change_id":
            payload[field] = baseline_prompt_change_id(template_id)
            continue
        if field in template:
            payload[field] = copy.deepcopy(template[field])
    return payload


def seed_specs(existing_template_ids: Iterable[str]) -> list[dict[str, Any]]:
    """只返回缺失模板的注册 payload，已存在则返回空列表（幂等，需求 4.2）。

    参数：
        existing_template_ids: 已存在的模板标识集合。传 `store.llm_task_templates`
            这类 Mapping 也可以（迭代取键）。

    返回：
        按 `BUILTIN_TEMPLATES` 声明顺序排列的注册 payload 列表；三条模板全部存在时为空
        列表，因此连续调用 N 次的写入效果与调用一次相同。
    """

    existing = {str(item).strip() for item in (existing_template_ids or ())}
    return [
        _registration_payload(template)
        for template in BUILTIN_TEMPLATES
        if str(template["template_id"]) not in existing
    ]


VIEWPOINT_SCHEMA_ID = "daily-mainline-viewpoint-v1"
"""观点 payload 的结构标识，供清单读模型与 artifact 断言使用。"""

FACT_FIELD_SOURCE_TYPES: tuple[str, ...] = ("official_disclosure", "market_data")
"""事实字段写入允许的来源类型（需求 1.8）。研报与任何二手来源都不在其中。"""

RESEARCH_REPORT_SOURCE_TYPE = "research_report"
MANUAL_REFERENCE_SOURCE_TYPE = "manual_reference"
UNKNOWN_SOURCE_TYPE = "unknown"

VIEWPOINT_SOURCE_TYPES: tuple[str, ...] = (
    RESEARCH_REPORT_SOURCE_TYPE,
    MANUAL_REFERENCE_SOURCE_TYPE,
    UNKNOWN_SOURCE_TYPE,
)
"""只能进观点层的来源类型：研报、人工参考，以及无法归类的来源（保守归入观点层）。"""

SOURCE_TYPES: tuple[str, ...] = FACT_FIELD_SOURCE_TYPES + VIEWPOINT_SOURCE_TYPES

SOURCE_LAYER_FACT = "fact"
SOURCE_LAYER_VIEWPOINT = "viewpoint"
SOURCE_LAYERS: tuple[str, ...] = (SOURCE_LAYER_FACT, SOURCE_LAYER_VIEWPOINT)

DILIGENCE_STATUS_GENERATED = "generated"
DILIGENCE_STATUS_UNSUPPORTED = "unsupported"
DILIGENCE_STATUS_FAILED = "failed"

PARTITION_RESEARCHABLE = "researchable"
PARTITION_PENDING_EVIDENCE = "pending_evidence"

REASON_EVIDENCE_MISSING = "evidence_missing"
REASON_LLM_CALL_FAILED = "llm_call_failed"
"""条目级原因码，取值沿用 design §5 错误处理表，使 `daily_mainline.build_next_actions` 能直接给出下一步动作。"""

EVIDENCE_BINDING_CITED = "cited"
EVIDENCE_BINDING_CANDIDATE_FALLBACK = "candidate_fallback"
EVIDENCE_BINDING_NONE = "none"
EVIDENCE_BINDING_MODES: tuple[str, ...] = (
    EVIDENCE_BINDING_CITED,
    EVIDENCE_BINDING_CANDIDATE_FALLBACK,
    EVIDENCE_BINDING_NONE,
)

PARSE_STATUS_PARSED = "parsed"
PARSE_STATUS_SALVAGED = "salvaged"
PARSE_STATUS_UNPARSED = "unparsed"
PARSE_STATUSES: tuple[str, ...] = (PARSE_STATUS_PARSED, PARSE_STATUS_SALVAGED, PARSE_STATUS_UNPARSED)

PARSE_REASON_EMPTY = "llm_output_empty"
PARSE_REASON_NOT_JSON = "llm_output_not_json"
PARSE_REASON_NOT_JSON_OBJECT = "llm_output_not_json_object"
PARSE_REASON_RECOVERED = "llm_output_json_recovered"

MAX_SUMMARY_CHARS = MAX_SUMMARY_LENGTH
"""摘要长度上限，与 artifact 的 `MAX_SUMMARY_LENGTH` 对齐，避免落盘时二次截断。"""

MAX_LIST_ITEMS = 8
MAX_LIST_ITEM_CHARS = 300
MAX_FACT_FIELD_WRITES = 12
MAX_TARGET_FIELD_CHARS = 120
MAX_EVIDENCE_ID_CHARS = 200
MAX_UNVERIFIED_EVIDENCE_IDS = 10
_MAX_JSON_RECOVERY_ATTEMPTS = 5

DEFAULT_USAGE_BOUNDARY = "research_reference_only_paper_only_no_broker_execution"

VIEWPOINT_LIST_FIELDS: tuple[str, ...] = ("key_drivers", "open_questions", "next_verification_tasks")
"""`candidate_diligence` 输出中需要保留的结构化列表字段（每条截断、条数有上限）。"""

CANDIDATE_IDENTITY_FIELDS: tuple[str, ...] = ("security_id", "issuer_id", "ticker", "market", "as_of_date")

_SUMMARY_TEXT_KEYS: tuple[str, ...] = (
    "viewpoint_summary",
    "evidence_summary",
    "summary",
    "conclusion",
)
_CITED_EVIDENCE_KEYS: tuple[str, ...] = ("evidence_ids", "cited_evidence_ids", "evidence_id")
_EVIDENCE_ID_KEYS: tuple[str, ...] = (
    "evidence_id",
    "citation_evidence_id",
    "research_report_citation_evidence_id",
    "id",
)
_EVIDENCE_EXISTENCE_KEYS: tuple[str, ...] = ("exists", "existing", "is_existing", "found")
_EXPLICIT_SOURCE_KEYS: tuple[str, ...] = (
    "source_type",
    "evidence_source_type",
    "source_kind",
    "collection",
)
_SOURCE_HEURISTIC_KEYS: tuple[str, ...] = (
    "section",
    "collection",
    "document_type",
    "data_domain",
    "bbox",
    "object_uri",
    "locator",
    "document_id",
    "source_id",
)
_FACT_FIELD_NAME_KEYS: tuple[str, ...] = (
    "target_field",
    "fact_field",
    "field",
    "field_name",
    "metric",
    "name",
)
_CLAIM_EVIDENCE_KEYS: tuple[str, ...] = ("evidence_ids", "evidence_id", "cited_evidence_ids")
_CLAIM_SOURCE_KEYS: tuple[str, ...] = ("source_type", "evidence_source_type", "source")
_LIST_ENTRY_TEXT_KEYS: tuple[str, ...] = (
    "text",
    "claim",
    "driver",
    "question",
    "task",
    "summary",
    "description",
    "label",
)

# 显式来源标识 → 归一化来源类型。键为小写去空白后的取值。
_SOURCE_TYPE_ALIASES: dict[str, str] = {
    # 官方披露（含交易所 / 公司 IR / 财报）
    "official_disclosure": "official_disclosure",
    "official": "official_disclosure",
    "official_filing": "official_disclosure",
    "official_financial_report": "official_disclosure",
    "public_filing": "official_disclosure",
    "filing": "official_disclosure",
    "sec_filing": "official_disclosure",
    "disclosure": "official_disclosure",
    "disclosure_event": "official_disclosure",
    "exchange_disclosure": "official_disclosure",
    "issuer_disclosure": "official_disclosure",
    "public_company_disclosure": "official_disclosure",
    "company_ir": "official_disclosure",
    "company_official": "official_disclosure",
    "annual_report": "official_disclosure",
    "interim_report": "official_disclosure",
    "financial_report": "official_disclosure",
    "financial_snapshot": "official_disclosure",
    "prospectus": "official_disclosure",
    # 行情数据
    "market_data": "market_data",
    "public_market_data": "market_data",
    "eod_market_data": "market_data",
    "public_or_local_market_data": "market_data",
    "market_quote": "market_data",
    "quote": "market_data",
    "price_data": "market_data",
    "tdx_vipdoc": "market_data",
    # 研报与二手研究
    "research_report": RESEARCH_REPORT_SOURCE_TYPE,
    "research_reports": RESEARCH_REPORT_SOURCE_TYPE,
    "research_report_citation": RESEARCH_REPORT_SOURCE_TYPE,
    "research_report_citation_evidence": RESEARCH_REPORT_SOURCE_TYPE,
    "local_research_reference": RESEARCH_REPORT_SOURCE_TYPE,
    "research_reference": RESEARCH_REPORT_SOURCE_TYPE,
    "broker_research": RESEARCH_REPORT_SOURCE_TYPE,
    "sell_side_research": RESEARCH_REPORT_SOURCE_TYPE,
    "third_party_research": RESEARCH_REPORT_SOURCE_TYPE,
    "analyst_report": RESEARCH_REPORT_SOURCE_TYPE,
    # 人工参考
    "manual_reference": MANUAL_REFERENCE_SOURCE_TYPE,
    "manual": MANUAL_REFERENCE_SOURCE_TYPE,
    "manual_review": MANUAL_REFERENCE_SOURCE_TYPE,
}

# 子串启发式规则，按声明顺序命中（研报优先，避免研报里提到“披露”被误判为事实来源）。
_SOURCE_HEURISTICS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("research_report", "research://", "broker", "analyst", "研报", "券商"), RESEARCH_REPORT_SOURCE_TYPE),
    (("market_data", "vipdoc", "eod", "quote", "kline", "行情"), "market_data"),
    (("disclosure", "filing", "annual_report", "interim_report", "prospectus", "公告", "披露"), "official_disclosure"),
    (("manual_reference", "manual_", "人工"), MANUAL_REFERENCE_SOURCE_TYPE),
)


def _as_list(value: Any) -> list[Any]:
    """把任意取值规整为列表（`None` → 空列表，Mapping / 标量 → 单元素列表）。"""

    if value is None:
        return []
    if isinstance(value, Mapping):
        return [value]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)
    return [value]


def _compact_text(value: Any) -> str:
    """折叠空白后的单行文本（摘要与列表条目都按单行呈现）。"""

    return " ".join(str(value or "").split())


def _first_text(source: Mapping[str, Any], keys: Iterable[str]) -> str:
    for key in keys:
        if is_sensitive_key(key):
            continue
        candidate = source.get(key)
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return ""


def normalize_source_type(value: Any) -> str:
    """把任意来源标识归一化到 `SOURCE_TYPES`；无法归类返回 `unknown`。"""

    text = str(value or "").strip().lower()
    if not text:
        return UNKNOWN_SOURCE_TYPE
    if text in _SOURCE_TYPE_ALIASES:
        return _SOURCE_TYPE_ALIASES[text]
    for tokens, source_type in _SOURCE_HEURISTICS:
        if any(token in text for token in tokens):
            return source_type
    return UNKNOWN_SOURCE_TYPE


def classify_evidence_source(record: Mapping[str, Any] | None) -> str:
    """判定一条证据记录的来源类型（`SOURCE_TYPES` 之一）。

    判定顺序：显式来源键（`source_type` / `collection` 等）→ 结构键的子串启发式
    （`section="research_report_citation"` 是研报引用证据的既有标记，见
    `SystemService._research_report_citation_evidence`）→ `unknown`。

    无法归类一律返回 `unknown`，因而只会落到观点层，不会污染事实字段（需求 1.8）。
    """

    if not isinstance(record, Mapping):
        return UNKNOWN_SOURCE_TYPE
    for key in _EXPLICIT_SOURCE_KEYS:
        resolved = normalize_source_type(record.get(key))
        if resolved != UNKNOWN_SOURCE_TYPE:
            return resolved
    for key in _SOURCE_HEURISTIC_KEYS:
        value = record.get(key)
        if value is None:
            continue
        text = str(value).lower()
        for tokens, source_type in _SOURCE_HEURISTICS:
            if any(token in text for token in tokens):
                return source_type
    return UNKNOWN_SOURCE_TYPE


def _evidence_record_exists(record: Mapping[str, Any]) -> bool:
    """调用方传入的证据默认视为存储中已存在；显式 `exists=False` 的记录不绑定。"""

    for key in _EVIDENCE_EXISTENCE_KEYS:
        if key in record:
            return bool(record.get(key))
    return True


def _evidence_id(record: Mapping[str, Any]) -> str:
    text = _first_text(record, _EVIDENCE_ID_KEYS)
    return text[:MAX_EVIDENCE_ID_CHARS]


def available_evidence(evidence_candidates: Sequence[Mapping[str, Any]] | None) -> dict[str, str]:
    """已存在证据标识 → 来源类型（按传入顺序去重）。"""

    available: dict[str, str] = {}
    for record in _as_list(evidence_candidates):
        if not isinstance(record, Mapping) or not _evidence_record_exists(record):
            continue
        evidence_id = _evidence_id(record)
        if not evidence_id or evidence_id in available:
            continue
        available[evidence_id] = classify_evidence_source(record)
    return available


def _cited_evidence_ids(payload: Mapping[str, Any]) -> list[str]:
    """LLM 输出自称引用的证据标识（去重保序，未做存在性校验）。"""

    cited: list[str] = []
    for key in _CITED_EVIDENCE_KEYS:
        for entry in _as_list(payload.get(key)):
            if isinstance(entry, Mapping):
                candidate = _evidence_id(entry)
            else:
                candidate = str(entry or "").strip()[:MAX_EVIDENCE_ID_CHARS]
            if candidate and candidate not in cited:
                cited.append(candidate)
    return cited


def _extract_json_object(text: str) -> dict[str, Any] | None:
    """从自然语言里捞出第一个可解析的 JSON 对象（括号配对扫描，跳过字符串字面量）。"""

    attempts = 0
    for start, char in enumerate(text):
        if char != "{":
            continue
        attempts += 1
        if attempts > _MAX_JSON_RECOVERY_ATTEMPTS:
            return None
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            current = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif current == "\\":
                    escaped = True
                elif current == '"':
                    in_string = False
                continue
            if current == '"':
                in_string = True
            elif current == "{":
                depth += 1
            elif current == "}":
                depth -= 1
                if depth == 0:
                    try:
                        parsed = json.loads(text[start : index + 1])
                    except (TypeError, ValueError):
                        break
                    if isinstance(parsed, Mapping):
                        return dict(parsed)
                    break
    return None


_FENCE_PATTERN = re.compile(r"^```[A-Za-z0-9_-]*\s*|\s*```$")


def parse_llm_output(llm_output_text: Any) -> dict[str, Any]:
    """健壮解析 LLM 输出文本（LLM 输出不可靠，因此每条降级路径都显式命名）。

    返回 `{"payload", "text", "parse_status", "parse_reason_code"}`：

    - `payload`：解析出的对象（已剔除敏感键并截断长文本），解析失败时为空 dict；
    - `text`：折叠空白后的原始文本，供摘要降级使用；
    - `parse_status`：`parsed`（直接是合法 JSON 对象）/ `salvaged`（去 ``` 围栏或从
      自然语言中捞出 JSON 对象；JSON 合法但不是对象也归此类）/ `unparsed`（空串或完全不是 JSON）；
    - `parse_reason_code`：`""` / `llm_output_json_recovered` / `llm_output_not_json_object` /
      `llm_output_not_json` / `llm_output_empty`。
    """

    if isinstance(llm_output_text, Mapping):
        payload = redact(dict(llm_output_text), max_text_length=MAX_SUMMARY_CHARS)
        return {
            "payload": payload if isinstance(payload, dict) else {},
            "text": "",
            "parse_status": PARSE_STATUS_PARSED,
            "parse_reason_code": "",
        }

    raw = str(llm_output_text or "")
    stripped = raw.strip()
    compact = _compact_text(raw)
    if not stripped:
        return {
            "payload": {},
            "text": "",
            "parse_status": PARSE_STATUS_UNPARSED,
            "parse_reason_code": PARSE_REASON_EMPTY,
        }

    unfenced = _FENCE_PATTERN.sub("", stripped).strip()
    status = PARSE_STATUS_PARSED if unfenced == stripped else PARSE_STATUS_SALVAGED
    reason = "" if status == PARSE_STATUS_PARSED else PARSE_REASON_RECOVERED

    parsed: Any = None
    try:
        parsed = json.loads(unfenced)
    except (TypeError, ValueError):
        recovered = _extract_json_object(stripped)
        if recovered is None:
            return {
                "payload": {},
                "text": compact,
                "parse_status": PARSE_STATUS_UNPARSED,
                "parse_reason_code": PARSE_REASON_NOT_JSON,
            }
        parsed = recovered
        status = PARSE_STATUS_SALVAGED
        reason = PARSE_REASON_RECOVERED

    if not isinstance(parsed, Mapping):
        return {
            "payload": {},
            "text": compact,
            "parse_status": PARSE_STATUS_SALVAGED,
            "parse_reason_code": PARSE_REASON_NOT_JSON_OBJECT,
        }

    payload = redact(dict(parsed), max_text_length=MAX_SUMMARY_CHARS)
    return {
        "payload": payload if isinstance(payload, dict) else {},
        "text": compact,
        "parse_status": status,
        "parse_reason_code": reason,
    }


def _entry_text(entry: Any) -> str:
    if isinstance(entry, Mapping):
        text = _first_text(entry, _LIST_ENTRY_TEXT_KEYS)
        if text:
            return text
        cleaned = redact(dict(entry), max_text_length=MAX_LIST_ITEM_CHARS)
        try:
            return json.dumps(cleaned, ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError):
            return str(cleaned)
    return str(entry or "")


def _projected_list(value: Any) -> list[str]:
    """列表字段投影：折叠空白、单条截断、条数上限（避免整份上游响应被搬进观点）。"""

    items: list[str] = []
    for entry in _as_list(value):
        text = truncate_text(_compact_text(_entry_text(entry)), max_length=MAX_LIST_ITEM_CHARS)
        if text and text not in items:
            items.append(text)
        if len(items) >= MAX_LIST_ITEMS:
            break
    return items


def _summary_text(payload: Mapping[str, Any], *, fallback_text: str) -> str:
    """观点摘要：优先取结构化摘要字段，缺失时降级为原始文本截断。"""

    text = _first_text(payload, _SUMMARY_TEXT_KEYS)
    if not text:
        text = fallback_text
    return truncate_text(_compact_text(text), max_length=MAX_SUMMARY_CHARS)


def _claim_evidence_ids(claim: Mapping[str, Any]) -> list[str]:
    ids: list[str] = []
    for key in _CLAIM_EVIDENCE_KEYS:
        for entry in _as_list(claim.get(key)):
            candidate = (
                _evidence_id(entry)
                if isinstance(entry, Mapping)
                else str(entry or "").strip()[:MAX_EVIDENCE_ID_CHARS]
            )
            if candidate and candidate not in ids:
                ids.append(candidate)
    return ids


def fact_field_writes(
    fact_claims: Any,
    *,
    bound_sources: Mapping[str, str],
    source_layer: str,
) -> list[dict[str, Any]]:
    """事实字段写入清单，来源类型恒为 `FACT_FIELD_SOURCE_TYPES` 的子集（需求 1.8）。

    `source_layer != "fact"`（即绑定证据里含研报或任何非事实来源）时恒返回空列表。
    单条写入需要目标字段名与至少一条事实来源证据；声明来源无法归一化到
    `FACT_FIELD_SOURCE_TYPES` 的 claim 直接丢弃。
    """

    if source_layer != SOURCE_LAYER_FACT:
        return []
    fact_evidence_ids = [
        evidence_id
        for evidence_id, source_type in bound_sources.items()
        if source_type in FACT_FIELD_SOURCE_TYPES
    ]
    if not fact_evidence_ids:
        return []

    writes: list[dict[str, Any]] = []
    seen_fields: set[str] = set()
    for claim in _as_list(fact_claims):
        if not isinstance(claim, Mapping):
            continue
        target_field = truncate_text(
            _compact_text(_first_text(claim, _FACT_FIELD_NAME_KEYS)),
            max_length=MAX_TARGET_FIELD_CHARS,
        )
        if not target_field or target_field in seen_fields:
            continue
        claim_ids = [
            evidence_id for evidence_id in _claim_evidence_ids(claim) if evidence_id in fact_evidence_ids
        ]
        evidence_ids = claim_ids or list(fact_evidence_ids)
        declared = _first_text(claim, _CLAIM_SOURCE_KEYS)
        source_type = normalize_source_type(declared) if declared else bound_sources[evidence_ids[0]]
        if source_type not in FACT_FIELD_SOURCE_TYPES:
            continue
        writes.append(
            {
                "target_field": target_field,
                "source_type": source_type,
                "evidence_ids": evidence_ids,
            }
        )
        seen_fields.add(target_field)
        if len(writes) >= MAX_FACT_FIELD_WRITES:
            break
    return writes


def build_viewpoint(
    *,
    candidate: Mapping[str, Any],
    llm_output_text: str,
    evidence_candidates: Sequence[Mapping[str, Any]],
    llm_task_run_id: str,
    template_id: str,
    prompt_version: str,
    model: str,
) -> dict[str, Any]:
    """组装一条候选的尽调观点（纯函数，不做 IO、不读存储、不改入参）。

    参数：
        candidate: 候选池条目（`daily_mainline_scan.build_candidate_pool` 的输出元素）。
            只读取 `CANDIDATE_IDENTITY_FIELDS` 用于标识回链。
        llm_output_text: LLM 输出文本，facade 用既有 `SystemService._llm_output_text(run.output)`
            提取。允许不是合法 JSON：解析失败时摘要降级为原始文本截断，见 `parse_llm_output`。
        evidence_candidates: **已存在**的证据记录（`evidence` 与 `section=
            "research_report_citation"` 的研报引用证据）。本模块不访问存储，因此调用方必须
            只传存储中真实存在的记录；用于测试的“不存在”记录可显式带 `exists=False`。
        llm_task_run_id / template_id / prompt_version / model: 观点 lineage（需求 1.5、4.3）。

    返回：
        观点 dict。facade（任务 10.1）把 `evidence_ids` / `partition` / `diligence_status` /
        `diligence_reason_code` / `llm_task_run_id` / `template_id` / `review_status` 同步到
        `DailyMainlineQueueItem` 同名字段，整个 dict 存入 `DailyMainlineQueueItem.viewpoint`。

    判定：
        - 绑定证据 = LLM 自称引用 ∩ 传入的已存在证据；交集为空但候选证据非空时退化为绑定全部
          候选证据（`evidence_binding_mode="candidate_fallback"`），自称引用但不存在的标识只记入
          `unverified_cited_evidence_ids`，不进 `evidence_ids`（需求 1.6）。
        - 无可绑定证据 → `diligence_status="unsupported"`、`diligence_reason_code="evidence_missing"`、
          `partition="pending_evidence"`（需求 1.7）。
        - 有证据但没有任何可用摘要文本（空响应）→ `diligence_status="failed"`、
          `diligence_reason_code="llm_call_failed"`，候选保留在 `researchable` 分区（design §5：
          单候选级失败不升级为阶段失败）。
        - `source_layer="fact"` 当且仅当绑定证据非空且全部来源类型 ∈ `FACT_FIELD_SOURCE_TYPES`；
          含研报或含无法归类来源一律 `viewpoint` 且 `fact_field_writes == []`（需求 1.8）。
    """

    source = candidate if isinstance(candidate, Mapping) else {}
    parsed = parse_llm_output(llm_output_text)
    payload: Mapping[str, Any] = parsed["payload"]

    available = available_evidence(evidence_candidates)
    cited = _cited_evidence_ids(payload)
    bound_ids = [evidence_id for evidence_id in cited if evidence_id in available]
    unverified = [evidence_id for evidence_id in cited if evidence_id not in available]

    if bound_ids:
        binding_mode = EVIDENCE_BINDING_CITED
    elif available:
        binding_mode = EVIDENCE_BINDING_CANDIDATE_FALLBACK
        bound_ids = list(available)
    else:
        binding_mode = EVIDENCE_BINDING_NONE

    bound_sources = {evidence_id: available[evidence_id] for evidence_id in bound_ids}
    source_layer = (
        SOURCE_LAYER_FACT
        if bound_ids and all(value in FACT_FIELD_SOURCE_TYPES for value in bound_sources.values())
        else SOURCE_LAYER_VIEWPOINT
    )
    writes = fact_field_writes(
        payload.get("fact_claims"),
        bound_sources=bound_sources,
        source_layer=source_layer,
    )
    summary = _summary_text(payload, fallback_text=str(parsed["text"]))

    if not bound_ids:
        diligence_status = DILIGENCE_STATUS_UNSUPPORTED
        diligence_reason_code = REASON_EVIDENCE_MISSING
        partition = PARTITION_PENDING_EVIDENCE
    elif not summary:
        diligence_status = DILIGENCE_STATUS_FAILED
        diligence_reason_code = REASON_LLM_CALL_FAILED
        partition = PARTITION_RESEARCHABLE
    else:
        diligence_status = DILIGENCE_STATUS_GENERATED
        diligence_reason_code = ""
        partition = PARTITION_RESEARCHABLE

    viewpoint: dict[str, Any] = {
        "schema_id": VIEWPOINT_SCHEMA_ID,
        "summary": summary,
        "usage_boundary": truncate_text(
            _compact_text(_first_text(payload, ("usage_boundary",)) or DEFAULT_USAGE_BOUNDARY),
            max_length=MAX_LIST_ITEM_CHARS,
        ),
        "source_layer": source_layer,
        "source_types": sorted(set(bound_sources.values())),
        "fact_field_writes": writes,
        "evidence_ids": list(bound_ids),
        "evidence_sources": [
            {"evidence_id": evidence_id, "source_type": bound_sources[evidence_id]}
            for evidence_id in bound_ids
        ],
        "evidence_binding_mode": binding_mode,
        "unverified_cited_evidence_ids": unverified[:MAX_UNVERIFIED_EVIDENCE_IDS],
        "diligence_status": diligence_status,
        "diligence_reason_code": diligence_reason_code,
        "partition": partition,
        "review_status": "pending",
        "llm_task_run_id": str(llm_task_run_id or ""),
        "template_id": str(template_id or ""),
        "prompt_version": str(prompt_version or ""),
        "model": str(model or ""),
        "parse_status": str(parsed["parse_status"]),
        "parse_reason_code": str(parsed["parse_reason_code"]),
    }
    for field in CANDIDATE_IDENTITY_FIELDS:
        viewpoint[field] = str(source.get(field) or "")
    for field in VIEWPOINT_LIST_FIELDS:
        viewpoint[field] = _projected_list(payload.get(field))
    return viewpoint
