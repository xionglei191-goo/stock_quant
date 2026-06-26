from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.api import ApiRouter
from app.llm_gateway import LLMGateway
from app.models import Evidence, MarketDataPoint, RightsTag
from app.services import SystemService


DEFAULT_ARTIFACT_PREFIX = "artifact://local/chokepoint-quality"
DEFAULT_OUTPUT_DIR = ROOT / "artifacts/chokepoint-quality-package"
DEFAULT_MANUAL_REVIEW_BASELINE = ROOT / "docs/examples/chokepoint-manual-review-baseline.jsonl"
DEFAULT_SAMPLES: list[dict[str, Any]] = [
    {
        "sample_id": "cpq_nuclear_haleu",
        "topic": "核燃料链 HALEU 供给瓶颈",
        "theme": "核能 / 核燃料链",
        "ticker": "CCJ",
        "chokepoint_node": "非俄转化、浓缩、HALEU",
        "playbook": "nuclear",
        "review_labels": [
            {"label_id": "core_supply_constraint", "statement": "HALEU non-Russian supply remains constrained.", "expected_layer": "inferred"},
            {"label_id": "needs_official_award_check", "statement": "DOE funding and award cadence still need official confirmation.", "expected_layer": "unknown"},
        ],
    },
    {
        "sample_id": "cpq_power_grid",
        "topic": "AI 数据中心电力与并网瓶颈",
        "theme": "AI 数据中心电力",
        "ticker": "VRT",
        "chokepoint_node": "并网时滞、变压器、配电扩容",
        "playbook": "power",
        "review_labels": [
            {"label_id": "grid_connection_delay", "statement": "Grid interconnection delays can constrain AI campus expansion.", "expected_layer": "confirmed"},
            {"label_id": "pricing_misread", "statement": "Market pricing gap still requires manual valuation review.", "expected_layer": "unknown"},
        ],
    },
    {
        "sample_id": "cpq_cpo_optics",
        "topic": "CPO / 光模块高速互连瓶颈",
        "theme": "CPO / 光模块",
        "ticker": "AVGO",
        "chokepoint_node": "硅光良率、封装产能、交换芯片配套",
        "playbook": "semis",
        "review_labels": [
            {"label_id": "yield_risk", "statement": "CPO yield and packaging ramp remain gating variables.", "expected_layer": "inferred"},
            {"label_id": "customer_adoption", "statement": "Customer adoption timing is still speculative.", "expected_layer": "speculative"},
        ],
    },
    {
        "sample_id": "cpq_pharma_approval",
        "topic": "药械审批与产能放量瓶颈",
        "theme": "创新药 / 医疗器械审批",
        "ticker": "MRK",
        "chokepoint_node": "审批节奏、CMC 放量、支付准入",
        "playbook": "healthcare",
        "review_labels": [
            {"label_id": "approval_timeline", "statement": "Approval timeline requires regulatory source confirmation.", "expected_layer": "unknown"},
            {"label_id": "capacity_release", "statement": "CMC capacity release can be a real bottleneck.", "expected_layer": "inferred"},
        ],
    },
    {
        "sample_id": "cpq_rare_materials",
        "topic": "稀缺材料与高纯前驱体瓶颈",
        "theme": "稀缺材料",
        "ticker": "ALB",
        "chokepoint_node": "高纯度前驱体、提纯周期、环保许可",
        "playbook": "materials",
        "review_labels": [
            {"label_id": "purification_cycle", "statement": "Purification cycle limits fast supply response.", "expected_layer": "confirmed"},
            {"label_id": "permit_dependency", "statement": "Permit dependency needs local jurisdiction verification.", "expected_layer": "unknown"},
        ],
    },
]

RIGHTS_TAG_DICT = {
    "license_class": "public",
    "training_allowed": False,
    "redistribution_allowed": False,
    "display_use": "allowed",
    "non_display_use": "restricted",
    "derived_data_use": "restricted",
}
RIGHTS_TAG = RightsTag.from_dict(RIGHTS_TAG_DICT)


def _atomic_write_text(path: str | Path, text: str) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_name(f".{output_path.name}.tmp")
    tmp_path.write_text(text, encoding="utf-8")
    tmp_path.replace(output_path)


def _json_dump(path: str | Path, payload: Mapping[str, Any] | list[Any]) -> None:
    _atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def _artifact_uri(prefix: str, name: str) -> str:
    return f"{prefix.rstrip('/')}/{name}"


def _safe_id(value: str) -> str:
    lowered = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return lowered or "sample"


def _count_by_key(rows: Iterable[Mapping[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        label = str(row.get(key, "") or "unknown")
        counts[label] = counts.get(label, 0) + 1
    return dict(sorted(counts.items()))


def _load_manual_review_rows(
    manual_review_input: str | Path | Mapping[str, Any] | Iterable[Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    if manual_review_input is None:
        return []
    if isinstance(manual_review_input, Mapping):
        rows = manual_review_input.get("rows", manual_review_input)
        if isinstance(rows, Mapping):
            return [dict(rows)]
        if isinstance(rows, Iterable) and not isinstance(rows, (str, bytes)):
            return [dict(item) for item in rows if isinstance(item, Mapping)]
        return []
    if isinstance(manual_review_input, Iterable) and not isinstance(manual_review_input, (str, bytes, Path)):
        return [dict(item) for item in manual_review_input if isinstance(item, Mapping)]

    input_path = Path(manual_review_input)
    if not input_path.exists():
        raise FileNotFoundError(f"manual review input not found: {input_path}")
    if input_path.suffix.lower() == ".jsonl":
        rows = []
        for raw_line in input_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if isinstance(payload, Mapping):
                rows.append(dict(payload))
        return rows
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    if isinstance(payload, Mapping):
        rows = payload.get("rows", [])
        if isinstance(rows, Iterable) and not isinstance(rows, (str, bytes)):
            return [dict(item) for item in rows if isinstance(item, Mapping)]
        return [dict(payload)]
    if isinstance(payload, list):
        return [dict(item) for item in payload if isinstance(item, Mapping)]
    return []


def _seed_sample_context(service: SystemService, sample: Mapping[str, Any], *, actor: str) -> None:
    ticker = str(sample.get("ticker", "")).strip().upper() or "DEMO"
    security_id = f"sec_{_safe_id(ticker)}"
    issuer_id = f"issuer_{_safe_id(ticker)}"
    topic_slug = _safe_id(str(sample.get("sample_id", sample.get("topic", ticker))))
    service.register_issuer(
        {
            "issuer_id": issuer_id,
            "legal_name": f"{ticker} chokepoint sample issuer",
            "market": ["U"],
            "country": "mixed",
        },
        actor=actor,
    )
    service.register_security(
        {
            "security_id": security_id,
            "issuer_id": issuer_id,
            "ticker": ticker,
            "market": "U",
            "currency": "USD",
        },
        actor=actor,
    )
    service.store.market_data[f"md_{topic_slug}"] = MarketDataPoint(
        data_id=f"md_{topic_slug}",
        security_id=security_id,
        market="U",
        as_of_date="2026-05-27",
        open=100.0,
        high=103.0,
        low=98.0,
        close=101.5,
        adjusted_close=101.5,
        volume=100000,
        source_id="public_eod_market_data",
        data_type="eod",
        rights_tag=RIGHTS_TAG,
    )
    theme = str(sample.get("theme", sample.get("topic", "")))
    node = str(sample.get("chokepoint_node", ""))
    service.ingest_document(
        {
            "document_id": f"doc_fact_{topic_slug}",
            "issuer_id": issuer_id,
            "security_id": security_id,
            "source_id": "sec_edgar",
            "source_type": "regulatory",
            "document_type": "10-K",
            "source_uri": f"https://example.invalid/chokepoint/{topic_slug}/official",
            "title": f"{theme} official fact sample",
            "body": f"{theme} official fact context. {node} is discussed in a public filing with source-backed risk notes.",
            "rights_tag": RIGHTS_TAG_DICT,
        },
        actor=actor,
    )
    service.ingest_document(
        {
            "document_id": f"doc_opinion_{topic_slug}",
            "issuer_id": issuer_id,
            "security_id": security_id,
            "source_id": "local_research_reports",
            "source_type": "local_reference",
            "document_type": "research",
            "source_uri": f"research-report://{topic_slug}",
            "title": f"{theme} research opinion sample",
            "body": f"Research opinion: {node} may remain constrained and requires manual follow-up.",
            "rights_tag": {
                "license_class": "local_research_reference",
                "training_allowed": False,
                "redistribution_allowed": False,
                "display_use": "restricted",
                "non_display_use": "restricted",
                "derived_data_use": "restricted",
            },
        },
        actor=actor,
    )
    service.store.evidence[f"evi_fact_{topic_slug}"] = Evidence(
        evidence_id=f"evi_fact_{topic_slug}",
        document_id=f"doc_fact_{topic_slug}",
        section="regulatory_fact",
        page_no=1,
        bbox=f"https://example.invalid/chokepoint/{topic_slug}/official#page=1",
        span_text=f"{theme} official evidence for chokepoint verification.",
        canonical_text=f"{theme} official evidence for chokepoint verification.",
        confidence=0.9,
    )
    service.store.evidence[f"evi_opinion_{topic_slug}"] = Evidence(
        evidence_id=f"evi_opinion_{topic_slug}",
        document_id=f"doc_opinion_{topic_slug}",
        section="research_report_citation",
        page_no=1,
        bbox=f"research-report://{topic_slug};chunk=0",
        span_text=f"Opinion only: {node} may remain constrained.",
        canonical_text=f"Opinion only: {node} may remain constrained.",
        confidence=0.7,
    )


def _build_stubbed_gateway() -> LLMGateway:
    def fake_send(request, timeout):
        body = json.loads(request.data.decode("utf-8"))
        prompt = body["messages"][-1]["content"]
        if "来源台账" in prompt:
            content = (
                "事实编号 | 事实陈述 | URL | 发布日期 | 来源类型 | confirmed/inferred/speculative/unknown | 置信度 | 下一步验证\n"
                "1 | Official filing confirms a constrained chokepoint node | https://example.invalid/source-ledger | 2026-05-20 | regulatory | confirmed | high | verify the latest filing\n"
                "2 | Market pricing gap still needs manual verification | https://example.invalid/pricing-gap | 2026-05-18 | exchange | inferred | medium | build valuation task\n"
                "3 | Unknown capacity expansion timing |  | unknown | unknown | unknown | low | needs_verification"
            )
        elif "事实审计" in prompt:
            content = (
                "事实审计结论：1 条 confirmed 来源可回链；1 条 inferred 需要估值复核；"
                "1 条 unknown 仍需 P0 官方来源补证，不构成投资建议。"
            )
        elif "问题窄化" in prompt:
            content = "子问题 A | chokepoint 为供给约束 | confirmed\n子问题 B | chokepoint 为审批节奏 | unknown"
        elif "价值链映射" in prompt:
            content = "终端需求 | 系统/组件 | chokepoint 节点 | 关键玩家 | confirmed\nAI 负载 | 电力与冷却 | 并网与配电 | utility / equipment | confirmed"
        elif "Chokepoint 排名" in prompt:
            content = "1 | chokepoint node concentration high | confirmed\n2 | customer switching cost medium | inferred"
        elif "Thesis 草稿" in prompt:
            content = "核心论点：confirmed bottleneck exists. 催化剂：审批/合同。风险：替代路径。证伪条件：供给释放快于需求。"
        elif "验证与证伪" in prompt:
            content = "P0: verify official source URL\nP1: unknown capacity release date\n反方：替代路径存在，仍待验证"
        else:
            content = "规则结论：confirmed 与 unknown 并存，保持 research only。"
        return json.dumps({"id": "chatcmpl_cpq", "choices": [{"message": {"content": content}}]}).encode("utf-8")

    return LLMGateway(
        base_url="https://llm.example.test",
        api_key="test-key",
        default_model="qwen3.6-plus",
        http_send=fake_send,
    )


def _build_service(samples: Iterable[Mapping[str, Any]], *, actor: str) -> SystemService:
    service = SystemService()
    service.seed_default_sources(actor=actor)
    service.llm_gateway = _build_stubbed_gateway()
    for sample in samples:
        _seed_sample_context(service, sample, actor=actor)
    return service


def _manual_review_seed(sample: Mapping[str, Any], run: Mapping[str, Any]) -> dict[str, Any]:
    labels = []
    conclusion = run.get("conclusion", {}) if isinstance(run.get("conclusion"), Mapping) else {}
    unknowns = conclusion.get("unknowns", []) if isinstance(conclusion, Mapping) else []
    open_issues = conclusion.get("open_issues", []) if isinstance(conclusion, Mapping) else []
    for item in sample.get("review_labels", []):
        labels.append(
            {
                "label_id": str(item.get("label_id", "")),
                "statement": str(item.get("statement", "")),
                "expected_layer": str(item.get("expected_layer", "unknown")),
                "manual_status": "pending_manual_review",
                "notes": "",
            }
        )
    return {
        "sample_id": sample.get("sample_id", ""),
        "topic": sample.get("topic", ""),
        "expected_labels": labels,
        "detected_unknown_count": len(unknowns) if isinstance(unknowns, list) else 0,
        "detected_open_issue_count": len(open_issues) if isinstance(open_issues, list) else 0,
        "usage_boundary": "manual_labels_are_local_only_research_quality_annotations",
    }


def _merge_manual_review(
    seed: Mapping[str, Any],
    provided_reviews: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    merged = dict(seed)
    review_rows = [item for item in provided_reviews if isinstance(item, Mapping)]
    if not review_rows:
        merged["review_status"] = "seed_only"
        merged["manual_issue_counts"] = {}
        merged["closed_label_count"] = 0
        merged["label_count"] = len(merged.get("expected_labels", [])) if isinstance(merged.get("expected_labels"), list) else 0
        return merged

    latest = dict(review_rows[-1])
    labels = merged.get("expected_labels", [])
    label_rows = [dict(item) for item in labels if isinstance(item, Mapping)] if isinstance(labels, list) else []
    overrides = latest.get("expected_labels", latest.get("labels", []))
    override_map: dict[str, Mapping[str, Any]] = {}
    if isinstance(overrides, list):
        for item in overrides:
            if not isinstance(item, Mapping):
                continue
            label_id = str(item.get("label_id", "")).strip()
            if label_id:
                override_map[label_id] = item
    merged_labels: list[dict[str, Any]] = []
    closed_count = 0
    for item in label_rows:
        label_id = str(item.get("label_id", "")).strip()
        override = dict(override_map.get(label_id, {}))
        combined = dict(item)
        combined.update({key: value for key, value in override.items() if key != "label_id"})
        status = str(combined.get("manual_status", "pending_manual_review"))
        if status not in {"pending_manual_review", "confirmed", "inferred", "speculative", "unknown", "dismissed"}:
            status = "pending_manual_review"
            combined["manual_status"] = status
        if status != "pending_manual_review":
            closed_count += 1
        merged_labels.append(combined)

    merged["expected_labels"] = merged_labels
    merged["review_status"] = str(latest.get("review_status", "completed_manual_review" if closed_count == len(merged_labels) and merged_labels else "partial_manual_review"))
    merged["reviewer"] = latest.get("reviewer", "")
    merged["reviewed_at"] = latest.get("reviewed_at", "")
    merged["review_notes"] = latest.get("review_notes", "")
    merged["manual_issue_counts"] = _count_by_key(
        [item for item in latest.get("manual_issues", []) if isinstance(item, Mapping)] if isinstance(latest.get("manual_issues"), list) else [],
        "issue_type",
    )
    merged["manual_label_status_counts"] = _count_by_key(merged_labels, "manual_status")
    merged["manual_issues"] = [dict(item) for item in latest.get("manual_issues", []) if isinstance(item, Mapping)] if isinstance(latest.get("manual_issues"), list) else []
    merged["closed_label_count"] = closed_count
    merged["label_count"] = len(merged_labels)
    return merged


def _issue_summary(run: Mapping[str, Any]) -> dict[str, int]:
    issues = run.get("issues", [])
    if not isinstance(issues, list):
        return {}
    return _count_by_key([item for item in issues if isinstance(item, Mapping)], "severity")


def _step_digest(step: Mapping[str, Any]) -> dict[str, Any]:
    quality = step.get("evidence_quality", {}) if isinstance(step.get("evidence_quality"), Mapping) else {}
    return {
        "step_id": step.get("step_id", ""),
        "label": step.get("label", ""),
        "status": step.get("status", ""),
        "summary": step.get("summary", ""),
        "url_count": int(quality.get("url_count", 0) or 0),
        "confirmed_count": int(quality.get("confirmed_count", 0) or 0),
        "inferred_count": int(quality.get("inferred_count", 0) or 0),
        "speculative_count": int(quality.get("speculative_count", 0) or 0),
        "unknown_count": int(quality.get("unknown_count", 0) or 0),
        "fallback_used": bool(quality.get("fallback_used")),
    }


def _sample_result(sample: Mapping[str, Any], run: Mapping[str, Any]) -> dict[str, Any]:
    steps = run.get("steps", []) if isinstance(run.get("steps"), list) else []
    conclusion = run.get("conclusion", {}) if isinstance(run.get("conclusion"), Mapping) else {}
    verification = conclusion.get("verification_tasks", {}) if isinstance(conclusion, Mapping) else {}
    quality = conclusion.get("evidence_quality_summary", {}) if isinstance(conclusion, Mapping) else {}
    return {
        "sample_id": sample.get("sample_id", ""),
        "run_id": run.get("run_id", ""),
        "topic": sample.get("topic", ""),
        "theme": sample.get("theme", ""),
        "chokepoint_node": sample.get("chokepoint_node", ""),
        "status": run.get("status", ""),
        "current_step": run.get("current_step", ""),
        "automation_allowed": run.get("automation_allowed", False),
        "live_execution_allowed": run.get("live_execution_allowed", False),
        "conclusion_status": conclusion.get("status", ""),
        "thesis_strength_score": conclusion.get("thesis_strength_score", 0),
        "confidence": conclusion.get("confidence", ""),
        "step_status_counts": _count_by_key([step for step in steps if isinstance(step, Mapping)], "status"),
        "step_output_digest": [_step_digest(step) for step in steps if isinstance(step, Mapping)],
        "issue_counts": _issue_summary(run),
        "verification_task_counts": {
            "created_count": int(verification.get("created_count", 0) or 0),
            "existing_count": int(verification.get("existing_count", 0) or 0),
        },
        "evidence_quality_summary": quality,
        "unknowns": conclusion.get("unknowns", [])[:8] if isinstance(conclusion.get("unknowns"), list) else [],
        "open_issues": conclusion.get("open_issues", [])[:8] if isinstance(conclusion.get("open_issues"), list) else [],
        "manual_review_seed": _manual_review_seed(sample, run),
        "usage_boundary": conclusion.get("usage_boundary", "research_only_not_investment_advice"),
    }


def _build_summary(
    samples: list[Mapping[str, Any]],
    results: list[Mapping[str, Any]],
    review_rows: list[Mapping[str, Any]],
    artifact_prefix: str,
) -> dict[str, Any]:
    sample_count = len(samples)
    result_count = len(results)
    automation_ok = all(item.get("automation_allowed") is False for item in results)
    live_execution_ok = all(item.get("live_execution_allowed") is False for item in results)
    conclusion_status_counts = _count_by_key(results, "conclusion_status")
    run_status_counts = _count_by_key(results, "status")
    verification_created = sum(int((item.get("verification_task_counts") or {}).get("created_count", 0) or 0) for item in results)
    verification_existing = sum(int((item.get("verification_task_counts") or {}).get("existing_count", 0) or 0) for item in results)
    open_issue_total = sum(sum(int(value) for key, value in (item.get("issue_counts") or {}).items() if key in {"warn", "block"}) for item in results)
    quality_rows = [item.get("evidence_quality_summary", {}) for item in results if isinstance(item.get("evidence_quality_summary"), Mapping)]
    url_total = sum(int(row.get("url_count", 0) or 0) for row in quality_rows)
    confirmed_total = sum(int(row.get("confirmed_count", 0) or 0) for row in quality_rows)
    unknown_total = sum(int(row.get("unknown_count", 0) or 0) for row in quality_rows)
    fallback_total = sum(int(row.get("fallback_step_count", 0) or 0) for row in quality_rows)
    review_steps_total = sum(int(row.get("review_steps", 0) or 0) for row in quality_rows)
    completed_steps_total = sum(int(row.get("completed_steps", 0) or 0) for row in quality_rows)
    total_steps = sum(int(row.get("total_steps", 0) or 0) for row in quality_rows)
    runs_with_urls = sum(1 for row in quality_rows if int(row.get("url_count", 0) or 0) > 0)
    runs_with_confirmed = sum(1 for row in quality_rows if int(row.get("confirmed_count", 0) or 0) > 0)
    runs_with_verification = sum(
        1
        for item in results
        if int((item.get("verification_task_counts") or {}).get("created_count", 0) or 0)
        + int((item.get("verification_task_counts") or {}).get("existing_count", 0) or 0)
        > 0
    )
    runs_with_fallback = sum(1 for row in quality_rows if int(row.get("fallback_step_count", 0) or 0) > 0)
    runs_with_unknowns = sum(1 for row in quality_rows if int(row.get("unknown_count", 0) or 0) > 0)
    review_count = len(review_rows)
    total_review_labels = sum(int(item.get("label_count", 0) or 0) for item in review_rows)
    closed_review_labels = sum(int(item.get("closed_label_count", 0) or 0) for item in review_rows)
    samples_with_completed_review = sum(
        1
        for item in review_rows
        if str(item.get("review_status", "")) in {"partial_manual_review", "completed_manual_review"}
    )
    manual_issue_rows: list[dict[str, Any]] = []
    manual_label_status_rows: list[dict[str, Any]] = []
    for item in review_rows:
        issue_counts = item.get("manual_issue_counts", {})
        if isinstance(issue_counts, Mapping):
            for issue_type, count in issue_counts.items():
                manual_issue_rows.extend([{"issue_type": issue_type}] * int(count or 0))
        label_status_counts = item.get("manual_label_status_counts", {})
        if isinstance(label_status_counts, Mapping):
            for manual_status, count in label_status_counts.items():
                manual_label_status_rows.extend([{"manual_status": manual_status}] * int(count or 0))
    manual_issue_counts = _count_by_key(manual_issue_rows, "issue_type")
    manual_label_status_counts = _count_by_key(manual_label_status_rows, "manual_status")
    boundary_violations = 0
    for item in results:
        if item.get("usage_boundary") != "research_only_not_investment_advice":
            boundary_violations += 1
    quality_baseline = {
        "sample_count": sample_count,
        "run_result_count": result_count,
        "url_coverage_rate": round(runs_with_urls / max(1, result_count), 4),
        "confirmed_run_rate": round(runs_with_confirmed / max(1, result_count), 4),
        "unknown_run_rate": round(runs_with_unknowns / max(1, result_count), 4),
        "avg_unknowns_per_run": round(unknown_total / max(1, result_count), 4),
        "verification_task_generation_rate": round(runs_with_verification / max(1, result_count), 4),
        "avg_verification_tasks_per_run": round((verification_created + verification_existing) / max(1, result_count), 4),
        "manual_review_close_rate": round(closed_review_labels / max(1, total_review_labels), 4),
        "manual_review_sample_coverage_rate": round(samples_with_completed_review / max(1, sample_count), 4),
        "manual_review_issue_count": sum(manual_issue_counts.values()),
        "fallback_rate": round(runs_with_fallback / max(1, result_count), 4),
        "boundary_violation_rate": round(boundary_violations / max(1, result_count), 4),
        "review_step_rate": round(review_steps_total / max(1, total_steps), 4),
        "completed_step_rate": round(completed_steps_total / max(1, total_steps), 4),
        "avg_urls_per_run": round(url_total / max(1, result_count), 4),
        "avg_confirmed_per_run": round(confirmed_total / max(1, result_count), 4),
        "automation_boundary_ok": automation_ok,
        "live_execution_boundary_ok": live_execution_ok,
    }
    ready = sample_count >= 5 and result_count == sample_count and automation_ok and live_execution_ok
    return {
        "status": "generated",
        "sample_count": sample_count,
        "run_result_count": result_count,
        "ready_for_local_baseline": ready,
        "run_status_counts": run_status_counts,
        "conclusion_status_counts": conclusion_status_counts,
        "open_issue_total": open_issue_total,
        "manual_review_summary": {
            "review_row_count": review_count,
            "sample_coverage_count": samples_with_completed_review,
            "label_count": total_review_labels,
            "closed_label_count": closed_review_labels,
            "review_status_counts": _count_by_key(review_rows, "review_status"),
            "label_status_counts": manual_label_status_counts,
            "issue_counts": manual_issue_counts,
        },
        "quality_baseline": quality_baseline,
        "artifact_uris": {
            "sample_manifest_uri": _artifact_uri(artifact_prefix, "sample-manifest.json"),
            "run_results_uri": _artifact_uri(artifact_prefix, "run-results.json"),
            "manual_review_seed_uri": _artifact_uri(artifact_prefix, "manual-review-seed.json"),
            "quality_summary_uri": _artifact_uri(artifact_prefix, "quality-summary.json"),
        },
        "usage_boundary": "local_only_chokepoint_quality_package_for_research_readiness_not_production_release",
    }


def build_local_chokepoint_quality_package(
    *,
    output_dir: str | Path,
    artifact_prefix: str = DEFAULT_ARTIFACT_PREFIX,
    samples: Iterable[Mapping[str, Any]] | None = None,
    manual_review_input: str | Path | Mapping[str, Any] | Iterable[Mapping[str, Any]] | None = None,
    actor: str = "chokepoint_quality_package",
) -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    sample_rows = [dict(item) for item in (samples or DEFAULT_SAMPLES)]
    manual_review_rows = _load_manual_review_rows(manual_review_input)
    manual_review_by_sample: dict[str, list[dict[str, Any]]] = {}
    for row in manual_review_rows:
        sample_id = str(row.get("sample_id", "")).strip()
        if not sample_id:
            continue
        manual_review_by_sample.setdefault(sample_id, []).append(dict(row))
    service = _build_service(sample_rows, actor=actor)
    router = ApiRouter(service)

    manifest_rows: list[dict[str, Any]] = []
    result_rows: list[dict[str, Any]] = []
    review_rows: list[dict[str, Any]] = []
    for index, sample in enumerate(sample_rows, start=1):
        sample_id = str(sample.get("sample_id", f"cpq_{index:02d}"))
        run_id = str(sample.get("run_id", f"cprun_{sample_id}"))
        create_payload = {
            "run_id": run_id,
            "topic": sample.get("topic", ""),
            "ticker": sample.get("ticker", ""),
            "theme": sample.get("theme", sample.get("topic", "")),
            "chokepoint_node": sample.get("chokepoint_node", ""),
            "playbook": sample.get("playbook", "generic"),
            "mode": sample.get("mode", "strict"),
        }
        created = router.dispatch("POST", "/api/chokepoint/runs", create_payload, actor=actor, role="analyst")
        if not created.success:
            raise RuntimeError(f"failed to create run {run_id}: {created.error}")
        executed = router.dispatch(
            "POST",
            f"/api/chokepoint/runs/{run_id}/run",
            {"step_limit": 7, "role": "分析师", "max_tokens": 600},
            actor=actor,
            role="analyst",
        )
        if not executed.success:
            raise RuntimeError(f"failed to execute run {run_id}: {executed.error}")
        run = dict(executed.data)
        result = _sample_result(sample, run)
        manifest_rows.append(
            {
                "sample_id": sample_id,
                "run_id": run_id,
                "topic": sample.get("topic", ""),
                "theme": sample.get("theme", ""),
                "ticker": sample.get("ticker", ""),
                "chokepoint_node": sample.get("chokepoint_node", ""),
                "playbook": sample.get("playbook", "generic"),
                "status": run.get("status", ""),
                "conclusion_status": run.get("conclusion", {}).get("status", "") if isinstance(run.get("conclusion"), Mapping) else "",
                "usage_boundary": "local_only_sample_manifest_for_chokepoint_quality_package",
            }
        )
        result_rows.append(result)
        review_rows.append(_merge_manual_review(result["manual_review_seed"], manual_review_by_sample.get(sample_id, [])))

    summary = _build_summary(manifest_rows, result_rows, review_rows, artifact_prefix)
    _json_dump(output_path / "sample-manifest.json", {"samples": manifest_rows, "sample_count": len(manifest_rows), "usage_boundary": "local_only_sample_manifest_for_chokepoint_quality_package"})
    _json_dump(output_path / "run-results.json", {"runs": result_rows, "run_count": len(result_rows), "usage_boundary": "local_only_chokepoint_run_results"})
    _json_dump(output_path / "manual-review-seed.json", {"rows": review_rows, "row_count": len(review_rows), "usage_boundary": "local_only_manual_review_seed"})
    _json_dump(output_path / "quality-summary.json", summary)

    package = {
        "status": "generated",
        "output_dir": str(output_path),
        "sample_count": len(manifest_rows),
        "run_result_count": len(result_rows),
        "ready_for_local_baseline": summary["ready_for_local_baseline"],
        "manual_review_ready_for_local_baseline": (
            summary["manual_review_summary"]["sample_coverage_count"] >= len(manifest_rows)
            and summary["manual_review_summary"]["label_count"] > 0
            and summary["manual_review_summary"]["closed_label_count"] == summary["manual_review_summary"]["label_count"]
        ),
        "quality_baseline": summary["quality_baseline"],
        "manual_review_summary": summary["manual_review_summary"],
        "artifacts": {
            "sample_manifest": str(output_path / "sample-manifest.json"),
            "run_results": str(output_path / "run-results.json"),
            "manual_review_seed": str(output_path / "manual-review-seed.json"),
            "quality_summary": str(output_path / "quality-summary.json"),
        },
        "artifact_uris": summary["artifact_uris"],
        "production_boundary": "local-only chokepoint quality package; not valid as external staging or production release evidence",
    }
    _json_dump(output_path / "quality-package.json", package)
    return package


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a local-only chokepoint research quality package with repeatable sample runs.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--artifact-prefix", default=DEFAULT_ARTIFACT_PREFIX)
    parser.add_argument("--manual-review-input", default=None)
    parser.add_argument(
        "--use-bundled-manual-review-baseline",
        action="store_true",
        help="Use the versioned local-only manual review baseline under docs/examples when no explicit input is provided.",
    )
    args = parser.parse_args()
    manual_review_input = args.manual_review_input
    if args.use_bundled_manual_review_baseline and manual_review_input is None:
        manual_review_input = DEFAULT_MANUAL_REVIEW_BASELINE

    result = build_local_chokepoint_quality_package(
        output_dir=args.output_dir,
        artifact_prefix=args.artifact_prefix,
        manual_review_input=manual_review_input,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
