"""内置 LLM 模板集（任务 4.1）与观点组装 / 来源分层（任务 4.2）的单元测试。

任务 4.1 覆盖需求 4.1（三类任务模板）、4.2（幂等写入）、4.7（prompt 版本 + 持久化字段不含
凭据），并对 design §9 风险 3 做落成验证：模板 seed 即 `approved`，编排调用既有
`SystemService.run_llm_task` 时不需要传 `allow_unapproved`。

任务 4.2 覆盖需求 1.5（观点携带 LLM 运行与模板 lineage）、1.6（绑定已存在证据标识）、
1.7（无证据 → unsupported + 待补证据分区）、1.8（研报只进观点层，事实字段来源限定）。
"""

from __future__ import annotations

import json
import unittest

from app.service_modules.daily_mainline_artifact import is_sensitive_key, viewpoint_summary
from app.service_modules.daily_mainline_diligence import (
    BUILTIN_TEMPLATES,
    DEFAULT_TEMPLATE_ROLE,
    DEFAULT_USAGE_BOUNDARY,
    FACT_FIELD_SOURCE_TYPES,
    MAX_SUMMARY_CHARS,
    PROMPT_VERSION,
    TASK_TYPES,
    TEMPLATE_PAYLOAD_FIELDS,
    TEMPLATE_STATUS,
    VIEWPOINT_SCHEMA_ID,
    BASELINE_CHANGE_LEVEL,
    baseline_prompt_change_id,
    build_viewpoint,
    builtin_template,
    classify_evidence_source,
    content_variables,
    required_variables,
    seed_specs,
    template_ids,
)
from app.errors import ComplianceGateError
from app.llm_gateway import LLMGateway
from tests.support import SystemServiceTestBase


def _walk_keys(payload: object) -> list[str]:
    keys: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            keys.append(str(key))
            keys.extend(_walk_keys(value))
    elif isinstance(payload, (list, tuple)):
        for item in payload:
            keys.extend(_walk_keys(item))
    return keys


class BuiltinTemplateContractTests(unittest.TestCase):
    def test_task_types_are_exactly_the_three_daily_mainline_tasks(self) -> None:
        self.assertEqual(TASK_TYPES, ("candidate_diligence", "evidence_summary", "risk_challenge"))
        self.assertEqual(tuple(template["task_type"] for template in BUILTIN_TEMPLATES), TASK_TYPES)
        self.assertEqual(
            template_ids(),
            ("tpl_daily_candidate_diligence", "tpl_daily_evidence_summary", "tpl_daily_risk_challenge"),
        )

    def test_every_template_is_approved_with_the_daily_mainline_prompt_version(self) -> None:
        self.assertEqual(TEMPLATE_STATUS, "approved")
        self.assertEqual(PROMPT_VERSION, "daily-mainline-v1")
        for template in BUILTIN_TEMPLATES:
            with self.subTest(template_id=template["template_id"]):
                self.assertEqual(template["status"], "approved")
                self.assertEqual(template["prompt_version"], PROMPT_VERSION)
                self.assertTrue(template["prompt_version"].strip())

    def test_template_fields_stay_inside_the_registration_contract(self) -> None:
        prompt_names = set()
        for template in BUILTIN_TEMPLATES:
            with self.subTest(template_id=template["template_id"]):
                self.assertIn(template["provider"], {"openai", "anthropic"})
                self.assertIn(template["risk_level"], {"low", "medium", "high", "critical"})
                self.assertEqual(template["fallback_chain"], ["rule_summary", "manual_review"])
                self.assertIn(DEFAULT_TEMPLATE_ROLE, template["allowed_roles"])
                self.assertNotIn("system", template["allowed_roles"])
                self.assertGreater(template["max_latency_ms"], 0)
                self.assertTrue(template["data_domains"])
                self.assertTrue(template["output_schema"]["required"])
                self.assertNotIn("model", template)
                prompt_names.add(template["prompt_name"])
        self.assertEqual(len(prompt_names), len(BUILTIN_TEMPLATES))

    def test_prompt_placeholders_match_declared_input_variables(self) -> None:
        expected = {
            "candidate_diligence": (
                "ticker",
                "market",
                "security_id",
                "as_of_date",
                "selection_reason",
                "trigger_digest",
                "completeness_digest",
                "evidence_digest",
            ),
            "evidence_summary": ("ticker", "as_of_date", "evidence_digest"),
            "risk_challenge": ("ticker", "as_of_date", "viewpoint_summary", "evidence_digest"),
        }
        for template in BUILTIN_TEMPLATES:
            task_type = template["task_type"]
            with self.subTest(task_type=task_type):
                self.assertEqual(required_variables(task_type), expected[task_type])
                self.assertEqual(
                    set(content_variables(template["content"])),
                    set(required_variables(task_type)),
                )

    def test_templates_declare_research_only_boundary_in_prompt(self) -> None:
        for template in BUILTIN_TEMPLATES:
            with self.subTest(template_id=template["template_id"]):
                self.assertIn("usage_boundary", template["output_schema"]["required"])
                self.assertIn("不输出思维链", template["content"])
        diligence = builtin_template("candidate_diligence")
        challenge = builtin_template("risk_challenge")
        self.assertIn("不得输出买入、卖出、仓位、目标价或实盘操作建议", diligence["content"])
        self.assertIn("不得输出买入、卖出、仓位、目标价或实盘操作建议", challenge["content"])
        self.assertFalse(diligence["output_schema"]["acceptance_thresholds"]["trade_recommendation_allowed"])

    def test_builtin_template_lookup_returns_a_copy(self) -> None:
        first = builtin_template("tpl_daily_evidence_summary")
        first["content"] = "mutated"
        first["input_schema"]["required"].append("injected")
        self.assertEqual(builtin_template("evidence_summary")["content"], BUILTIN_TEMPLATES[1]["content"])
        self.assertEqual(required_variables("evidence_summary"), ("ticker", "as_of_date", "evidence_digest"))
        with self.assertRaises(KeyError):
            builtin_template("unknown_task")


class SeedSpecsTests(unittest.TestCase):
    def test_missing_templates_yield_registration_payloads_in_declaration_order(self) -> None:
        specs = seed_specs([])

        self.assertEqual([spec["template_id"] for spec in specs], list(template_ids()))
        for spec in specs:
            with self.subTest(template_id=spec["template_id"]):
                self.assertEqual(spec["status"], "approved")
                self.assertEqual(spec["prompt_version"], PROMPT_VERSION)
                self.assertEqual(
                    spec["approved_prompt_change_id"],
                    baseline_prompt_change_id(spec["template_id"]),
                )
                self.assertLessEqual(set(spec), set(TEMPLATE_PAYLOAD_FIELDS))

    def test_seed_is_idempotent_for_existing_and_partial_template_sets(self) -> None:
        self.assertEqual(seed_specs(template_ids()), [])
        # Mapping 也可以直接传（迭代取键），facade 可以直接给 store.llm_task_templates
        self.assertEqual(seed_specs({template_id: object() for template_id in template_ids()}), [])

        partial = seed_specs(["tpl_daily_candidate_diligence"])
        self.assertEqual(
            [spec["template_id"] for spec in partial],
            ["tpl_daily_evidence_summary", "tpl_daily_risk_challenge"],
        )

        applied = set(template_ids())
        repeated = [seed_specs(applied) for _ in range(3)]
        self.assertEqual(repeated, [[], [], []])

    def test_repeated_seed_after_applying_specs_changes_nothing(self) -> None:
        registry: dict[str, dict[str, object]] = {}
        for _ in range(3):
            for spec in seed_specs(registry):
                registry[str(spec["template_id"])] = spec

        self.assertEqual(sorted(registry), sorted(template_ids()))
        self.assertEqual({spec["prompt_version"] for spec in registry.values()}, {PROMPT_VERSION})
        self.assertEqual({spec["status"] for spec in registry.values()}, {"approved"})

    def test_specs_are_copies_and_carry_no_sensitive_or_upstream_fields(self) -> None:
        specs = seed_specs([])
        specs[0]["content"] = "mutated"
        specs[0]["input_schema"]["required"].append("injected")
        self.assertEqual(seed_specs([])[0]["content"], BUILTIN_TEMPLATES[0]["content"])
        self.assertEqual(
            seed_specs([])[0]["input_schema"]["required"],
            BUILTIN_TEMPLATES[0]["input_schema"]["required"],
        )

        for spec in seed_specs([]):
            with self.subTest(template_id=spec["template_id"]):
                sensitive = [key for key in _walk_keys(spec) if is_sensitive_key(key)]
                self.assertEqual(sensitive, [])
                serialized = json.dumps(spec, ensure_ascii=False)
                self.assertNotIn("Bearer ", serialized)
                for excluded in ("api_key", "raw_response", "response", "output"):
                    self.assertNotIn(excluded, _walk_keys(spec))


class SeedSpecsApprovalGateTests(SystemServiceTestBase):
    """风险 3 落成验证：seed 即 approved，`run_llm_task` 无需 `allow_unapproved`。"""

    def _register_builtin_templates(self) -> None:
        for spec in seed_specs(self.service.store.llm_task_templates):
            change_id = str(spec["approved_prompt_change_id"])
            self.service.create_prompt_change(
                {
                    "request_id": change_id,
                    "prompt_name": spec["prompt_name"],
                    "change_level": BASELINE_CHANGE_LEVEL,
                    "requested_by": "analyst",
                    "content": spec["content"],
                },
                actor="analyst",
            )
            self.service.approve_prompt_change(change_id, actor="risk", approved=True)
            self.service.register_llm_task_template(dict(spec), actor="analyst")

    def test_registered_templates_keep_status_and_prompt_version(self) -> None:
        self._register_builtin_templates()

        for template_id in template_ids():
            with self.subTest(template_id=template_id):
                stored = self.service.store.llm_task_templates[template_id]
                self.assertEqual(stored.status, "approved")
                self.assertEqual(stored.prompt_version, PROMPT_VERSION)
                self.assertEqual(stored.approved_prompt_change_id, baseline_prompt_change_id(template_id))
                self.assertEqual(stored.model, "")

        self.assertEqual(seed_specs(self.service.store.llm_task_templates), [])

    def test_run_llm_task_passes_the_approval_gate_without_allow_unapproved(self) -> None:
        self._register_builtin_templates()
        self.service.llm_gateway = LLMGateway(
            api_key="local-test-key",
            default_model="qwen3.6-plus",
            http_send=lambda _request, _timeout: json.dumps(
                {"choices": [{"message": {"content": "{\"viewpoint_summary\": \"ok\"}"}}]}
            ).encode("utf-8"),
        )

        run = self.service.run_llm_task(
            {
                "template_id": "tpl_daily_candidate_diligence",
                "role": DEFAULT_TEMPLATE_ROLE,
                "variables": {
                    "ticker": "DEMO",
                    "market": "A",
                    "security_id": "sec_001",
                    "as_of_date": "2026-07-24",
                    "selection_reason": "涨跌幅异常",
                    "trigger_digest": "one_day_return=0.101 >= 0.07",
                    "completeness_digest": "partial: financial_snapshot",
                    "evidence_digest": "ev_001 | 官方披露 | 营收同比 +12%",
                },
            },
            actor="analyst",
        )

        self.assertEqual(run.status, "succeeded")
        self.assertEqual(run.template_id, "tpl_daily_candidate_diligence")
        self.assertEqual(run.task_type, "candidate_diligence")
        self.assertEqual(run.prompt_version, PROMPT_VERSION)
        self.assertEqual(run.model, "qwen3.6-plus")
        self.assertGreater(run.estimated_input_tokens, 0)

    def test_unapproved_template_still_blocks_so_the_gate_is_real(self) -> None:
        spec = dict(seed_specs([])[0])
        spec["status"] = "draft"
        spec.pop("approved_prompt_change_id", None)
        self.service.register_llm_task_template(spec, actor="analyst")

        with self.assertRaises(ComplianceGateError):
            self.service.run_llm_task(
                {"template_id": "tpl_daily_candidate_diligence", "variables": {}},
                actor="analyst",
            )


CANDIDATE = {
    "rank": 1,
    "security_id": "sec_600519",
    "issuer_id": "iss_600519",
    "ticker": "600519",
    "market": "A",
    "as_of_date": "2026-07-24",
    "selection_reason": "涨跌幅异常",
}

OFFICIAL_EVIDENCE = {
    "evidence_id": "evi_doc1_0",
    "document_id": "doc1",
    "section": "annual_report_disclosure",
    "span_text": "营收同比增长 12%",
}
MARKET_EVIDENCE = {
    "evidence_id": "evi_market_0",
    "source_type": "public_market_data",
    "span_text": "2026-07-24 收盘 +10.07%",
}
REPORT_EVIDENCE = {
    "evidence_id": "evi_doc2_research_0",
    "document_id": "doc2",
    "section": "research_report_citation",
    "bbox": "research_report://doc2;chunk=0",
    "span_text": "券商预计出货量翻倍",
}


def _viewpoint(
    llm_output_text: str,
    evidence_candidates: list[dict[str, object]],
    *,
    candidate: dict[str, object] | None = None,
) -> dict[str, object]:
    return build_viewpoint(
        candidate=CANDIDATE if candidate is None else candidate,
        llm_output_text=llm_output_text,
        evidence_candidates=evidence_candidates,
        llm_task_run_id="llmrun_daily_1",
        template_id="tpl_daily_candidate_diligence",
        prompt_version=PROMPT_VERSION,
        model="qwen3.6-plus",
    )


class BuildViewpointEvidenceBindingTests(unittest.TestCase):
    """需求 1.5 / 1.6 / 1.7：lineage 携带、证据绑定与待补证据分区。"""

    def test_cited_existing_evidence_binds_and_carries_llm_lineage(self) -> None:
        viewpoint = _viewpoint(
            json.dumps(
                {
                    "viewpoint_summary": "高端产品占比提升带动毛利率",
                    "key_drivers": ["高端产品占比提升", {"driver": "渠道库存回落"}],
                    "open_questions": ["提价能否延续"],
                    "next_verification_tasks": ["核对渠道库存披露"],
                    "evidence_ids": ["evi_doc1_0"],
                    "usage_boundary": "research_reference_only",
                },
                ensure_ascii=False,
            ),
            [OFFICIAL_EVIDENCE, MARKET_EVIDENCE],
        )

        self.assertEqual(viewpoint["schema_id"], VIEWPOINT_SCHEMA_ID)
        self.assertEqual(viewpoint["evidence_ids"], ["evi_doc1_0"])
        self.assertEqual(viewpoint["evidence_binding_mode"], "cited")
        self.assertEqual(viewpoint["diligence_status"], "generated")
        self.assertEqual(viewpoint["diligence_reason_code"], "")
        self.assertEqual(viewpoint["partition"], "researchable")
        self.assertEqual(viewpoint["review_status"], "pending")
        self.assertEqual(viewpoint["llm_task_run_id"], "llmrun_daily_1")
        self.assertEqual(viewpoint["template_id"], "tpl_daily_candidate_diligence")
        self.assertEqual(viewpoint["prompt_version"], PROMPT_VERSION)
        self.assertEqual(viewpoint["model"], "qwen3.6-plus")
        self.assertEqual(viewpoint["security_id"], "sec_600519")
        self.assertEqual(viewpoint["as_of_date"], "2026-07-24")
        self.assertEqual(viewpoint["key_drivers"], ["高端产品占比提升", "渠道库存回落"])
        self.assertEqual(viewpoint["open_questions"], ["提价能否延续"])
        self.assertEqual(viewpoint["next_verification_tasks"], ["核对渠道库存披露"])
        self.assertEqual(viewpoint["usage_boundary"], "research_reference_only")

    def test_cited_ids_outside_the_candidate_set_are_never_bound(self) -> None:
        viewpoint = _viewpoint(
            json.dumps(
                {
                    "viewpoint_summary": "观点",
                    "evidence_ids": ["evi_doc1_0", "evi_不存在", "evi_编造_2"],
                },
                ensure_ascii=False,
            ),
            [OFFICIAL_EVIDENCE],
        )

        self.assertEqual(viewpoint["evidence_ids"], ["evi_doc1_0"])
        self.assertEqual(viewpoint["unverified_cited_evidence_ids"], ["evi_不存在", "evi_编造_2"])
        self.assertEqual(viewpoint["diligence_status"], "generated")

    def test_uncited_output_falls_back_to_the_supplied_evidence_candidates(self) -> None:
        viewpoint = _viewpoint(
            json.dumps({"viewpoint_summary": "没有给出引用的观点"}, ensure_ascii=False),
            [OFFICIAL_EVIDENCE, REPORT_EVIDENCE],
        )

        self.assertEqual(viewpoint["evidence_ids"], ["evi_doc1_0", "evi_doc2_research_0"])
        self.assertEqual(viewpoint["evidence_binding_mode"], "candidate_fallback")
        self.assertEqual(viewpoint["partition"], "researchable")

    def test_without_bindable_evidence_the_viewpoint_is_unsupported(self) -> None:
        viewpoint = _viewpoint(
            json.dumps({"viewpoint_summary": "无证据支撑的观点", "evidence_ids": ["evi_编造"]}, ensure_ascii=False),
            [],
        )

        self.assertEqual(viewpoint["evidence_ids"], [])
        self.assertEqual(viewpoint["evidence_binding_mode"], "none")
        self.assertEqual(viewpoint["diligence_status"], "unsupported")
        self.assertEqual(viewpoint["diligence_reason_code"], "evidence_missing")
        self.assertEqual(viewpoint["partition"], "pending_evidence")
        self.assertEqual(viewpoint["source_layer"], "viewpoint")
        self.assertEqual(viewpoint["fact_field_writes"], [])

    def test_records_flagged_as_not_existing_are_not_bindable(self) -> None:
        viewpoint = _viewpoint(
            json.dumps({"viewpoint_summary": "观点", "evidence_ids": ["evi_doc1_0"]}, ensure_ascii=False),
            [dict(OFFICIAL_EVIDENCE, exists=False)],
        )

        self.assertEqual(viewpoint["evidence_ids"], [])
        self.assertEqual(viewpoint["diligence_status"], "unsupported")
        self.assertEqual(viewpoint["partition"], "pending_evidence")


class BuildViewpointSourceLayerTests(unittest.TestCase):
    """需求 1.8：研报只进观点层，事实字段写入来源限定官方披露 / 行情。"""

    def test_fact_field_source_types_are_official_disclosure_and_market_data(self) -> None:
        self.assertEqual(FACT_FIELD_SOURCE_TYPES, ("official_disclosure", "market_data"))

    def test_research_report_source_forces_the_viewpoint_layer_without_fact_writes(self) -> None:
        viewpoint = _viewpoint(
            json.dumps(
                {
                    "viewpoint_summary": "研报推断的份额提升",
                    "evidence_ids": ["evi_doc2_research_0", "evi_doc1_0"],
                    "fact_claims": [{"field": "market_share", "source_type": "official_disclosure"}],
                    "viewpoint_claims": ["券商预计出货量翻倍"],
                },
                ensure_ascii=False,
            ),
            [OFFICIAL_EVIDENCE, REPORT_EVIDENCE],
        )

        self.assertIn("research_report", viewpoint["source_types"])
        self.assertEqual(viewpoint["source_layer"], "viewpoint")
        self.assertEqual(viewpoint["fact_field_writes"], [])

    def test_fact_sources_allow_writes_limited_to_fact_field_source_types(self) -> None:
        viewpoint = _viewpoint(
            json.dumps(
                {
                    "viewpoint_summary": "官方披露与行情支撑的事实",
                    "evidence_ids": ["evi_doc1_0", "evi_market_0"],
                    "fact_claims": [
                        {"field": "revenue_yoy", "evidence_ids": ["evi_doc1_0"], "source_type": "public_filing"},
                        {"target_field": "last_close", "evidence_ids": ["evi_market_0"]},
                        {"field": "revenue_yoy", "evidence_ids": ["evi_doc1_0"]},
                        {"value": "缺少字段名"},
                    ],
                },
                ensure_ascii=False,
            ),
            [OFFICIAL_EVIDENCE, MARKET_EVIDENCE],
        )

        self.assertEqual(viewpoint["source_layer"], "fact")
        self.assertEqual(sorted(viewpoint["source_types"]), ["market_data", "official_disclosure"])
        writes = viewpoint["fact_field_writes"]
        self.assertEqual([write["target_field"] for write in writes], ["revenue_yoy", "last_close"])
        self.assertEqual(
            {write["source_type"] for write in writes} - set(FACT_FIELD_SOURCE_TYPES),
            set(),
        )
        self.assertEqual(writes[0]["evidence_ids"], ["evi_doc1_0"])
        self.assertEqual(writes[1]["evidence_ids"], ["evi_market_0"])

    def test_unclassifiable_source_stays_out_of_the_fact_layer(self) -> None:
        viewpoint = _viewpoint(
            json.dumps(
                {
                    "viewpoint_summary": "来源不明的观点",
                    "evidence_ids": ["evi_unknown_0"],
                    "fact_claims": [{"field": "revenue_yoy"}],
                },
                ensure_ascii=False,
            ),
            [{"evidence_id": "evi_unknown_0", "span_text": "没有来源标记"}],
        )

        self.assertEqual(viewpoint["source_types"], ["unknown"])
        self.assertEqual(viewpoint["source_layer"], "viewpoint")
        self.assertEqual(viewpoint["fact_field_writes"], [])

    def test_fact_claims_declaring_a_non_fact_source_are_dropped(self) -> None:
        viewpoint = _viewpoint(
            json.dumps(
                {
                    "viewpoint_summary": "事实层里混入研报口径",
                    "evidence_ids": ["evi_doc1_0"],
                    "fact_claims": [
                        {"field": "market_share", "source_type": "broker_research"},
                        {"field": "revenue_yoy", "source_type": "official_disclosure"},
                    ],
                },
                ensure_ascii=False,
            ),
            [OFFICIAL_EVIDENCE],
        )

        self.assertEqual(viewpoint["source_layer"], "fact")
        self.assertEqual(
            [write["target_field"] for write in viewpoint["fact_field_writes"]],
            ["revenue_yoy"],
        )

    def test_evidence_source_classification_normalizes_known_markers(self) -> None:
        cases = {
            "official_disclosure": ({"source_type": "public_filing"}, {"section": "annual_report_disclosure"}),
            "market_data": ({"source_type": "public_market_data"}, {"section": "eod_quote"}),
            "research_report": (
                {"section": "research_report_citation"},
                {"bbox": "research_report://doc2;chunk=3"},
                {"collection": "research_report_citation_evidence"},
            ),
            "unknown": ({}, {"section": "财务附注"}, {"evidence_id": "evi_1"}),
        }
        for expected, records in cases.items():
            for record in records:
                with self.subTest(expected=expected, record=record):
                    self.assertEqual(classify_evidence_source(record), expected)


class BuildViewpointOutputParsingTests(unittest.TestCase):
    """LLM 输出不可靠时的降级路径与“摘要不复制完整上游响应”边界（需求 1.5、4.7）。"""

    def test_fenced_json_is_salvaged(self) -> None:
        viewpoint = _viewpoint(
            '```json\n{"viewpoint_summary": "围栏包裹的 JSON", "evidence_ids": ["evi_doc1_0"]}\n```',
            [OFFICIAL_EVIDENCE],
        )

        self.assertEqual(viewpoint["parse_status"], "salvaged")
        self.assertEqual(viewpoint["parse_reason_code"], "llm_output_json_recovered")
        self.assertEqual(viewpoint["summary"], "围栏包裹的 JSON")
        self.assertEqual(viewpoint["evidence_ids"], ["evi_doc1_0"])

    def test_json_embedded_in_prose_is_salvaged(self) -> None:
        viewpoint = _viewpoint(
            '结论如下：{"viewpoint_summary": "夹在自然语言里的 JSON", "evidence_ids": ["evi_doc1_0"]} 以上。',
            [OFFICIAL_EVIDENCE],
        )

        self.assertEqual(viewpoint["parse_status"], "salvaged")
        self.assertEqual(viewpoint["summary"], "夹在自然语言里的 JSON")
        self.assertEqual(viewpoint["evidence_ids"], ["evi_doc1_0"])

    def test_non_json_output_degrades_to_a_plain_text_summary(self) -> None:
        viewpoint = _viewpoint("这是一段不是 JSON 的自然语言观点。\n换行也要折叠。", [OFFICIAL_EVIDENCE])

        self.assertEqual(viewpoint["parse_status"], "unparsed")
        self.assertEqual(viewpoint["parse_reason_code"], "llm_output_not_json")
        self.assertEqual(viewpoint["summary"], "这是一段不是 JSON 的自然语言观点。 换行也要折叠。")
        self.assertEqual(viewpoint["diligence_status"], "generated")
        self.assertEqual(viewpoint["partition"], "researchable")
        self.assertEqual(viewpoint["fact_field_writes"], [])
        self.assertEqual(viewpoint["usage_boundary"], DEFAULT_USAGE_BOUNDARY)

    def test_empty_output_keeps_the_candidate_but_records_the_failure(self) -> None:
        viewpoint = _viewpoint("   \n  ", [OFFICIAL_EVIDENCE])

        self.assertEqual(viewpoint["summary"], "")
        self.assertEqual(viewpoint["parse_reason_code"], "llm_output_empty")
        self.assertEqual(viewpoint["diligence_status"], "failed")
        self.assertEqual(viewpoint["diligence_reason_code"], "llm_call_failed")
        self.assertEqual(viewpoint["partition"], "researchable")
        self.assertEqual(viewpoint["evidence_ids"], ["evi_doc1_0"])

    def test_summary_keeps_no_full_upstream_response_and_no_credentials(self) -> None:
        long_text = "极长的上游响应正文。" * 800
        viewpoint = _viewpoint(
            json.dumps(
                {
                    "viewpoint_summary": long_text,
                    "key_drivers": [long_text for _ in range(50)],
                    "evidence_ids": ["evi_doc1_0"],
                    "api_key": "sk-local-secret-value",
                    "raw_response": {"choices": [{"message": {"content": long_text}}]},
                },
                ensure_ascii=False,
            ),
            [OFFICIAL_EVIDENCE],
        )

        self.assertLessEqual(len(str(viewpoint["summary"])), MAX_SUMMARY_CHARS)
        self.assertLessEqual(len(viewpoint["key_drivers"]), 8)
        serialized = json.dumps(viewpoint, ensure_ascii=False)
        self.assertNotIn("sk-local-secret-value", serialized)
        self.assertNotIn(long_text, serialized)
        self.assertEqual([key for key in _walk_keys(viewpoint) if is_sensitive_key(key)], [])
        self.assertNotIn("raw_response", _walk_keys(viewpoint))

    def test_inputs_are_not_mutated_and_artifact_summary_stays_compatible(self) -> None:
        candidate = dict(CANDIDATE)
        evidence = [dict(OFFICIAL_EVIDENCE), dict(REPORT_EVIDENCE)]
        output_text = json.dumps(
            {"viewpoint_summary": "研报线索需人工复核", "evidence_ids": ["evi_doc2_research_0"]},
            ensure_ascii=False,
        )

        viewpoint = _viewpoint(output_text, evidence, candidate=candidate)

        self.assertEqual(candidate, CANDIDATE)
        self.assertEqual(evidence, [dict(OFFICIAL_EVIDENCE), dict(REPORT_EVIDENCE)])

        summary = viewpoint_summary(viewpoint)
        self.assertEqual(summary["summary"], "研报线索需人工复核")
        self.assertEqual(summary["source_layer"], "viewpoint")
        self.assertEqual(summary["fact_field_writes"], [])
        self.assertEqual(summary["llm_task_run_id"], "llmrun_daily_1")
        self.assertEqual(summary["template_id"], "tpl_daily_candidate_diligence")
        self.assertEqual(summary["prompt_version"], PROMPT_VERSION)
        self.assertEqual(summary["evidence_ids"], ["evi_doc2_research_0"])
        self.assertEqual(summary["diligence_status"], "generated")


if __name__ == "__main__":  # pragma: no cover - manual runs
    unittest.main()
