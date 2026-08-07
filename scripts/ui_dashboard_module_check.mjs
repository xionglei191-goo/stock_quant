import { createDashboardRuntime } from "../app/static/ui_modules/dashboard.mjs";

const elements = new Map();
const element = (id) => {
  if (!elements.has(id)) elements.set(id, {
    id,
    className: "",
    disabled: false,
    hidden: false,
    innerHTML: "",
    textContent: "",
    value: "",
  });
  return elements.get(id);
};

globalThis.document = { body: { dataset: {} } };
let personalSummaryCalls = 0;
const rows = (items, empty, mapper) => items?.length ? items.map(mapper).join("") : `<tr><td>${empty}</td></tr>`;
const pct = (value) => `${Math.round((value || 0) * 100)}%`;
const signedPct = (value) => value == null ? "-" : `${Number(value) > 0 ? "+" : ""}${Number(value)}%`;

const runtime = createDashboardRuntime({
  $: element,
  api: async () => ({ data: {} }),
  boundaryLabel: (value) => value || "-",
  documentTypeLabel: (value) => value || "-",
  escapeHtml: (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[char])),
  metaLine: (label, value) => value ? `<span>${label}: ${value}</span>` : "",
  pct,
  rawPct: (value) => value == null ? "-" : `${value}%`,
  renderAdvancedTrace: () => "<details>trace</details>",
  renderPersonalIntelligenceSummary: () => { personalSummaryCalls += 1; },
  rows,
  setText: (id, value) => { element(id).textContent = value; },
  shortPath: (value) => String(value || "-").split("/").slice(-2).join("/"),
  signedPct,
  sourceLabel: (value) => value || "-",
  statusLabel: (value) => value || "-",
  toneForNumber: (value) => Number(value) >= 0 ? "up" : "down",
  userEntityLabel: (value, fallback = "-") => value || fallback,
});

runtime.renderDailyMainline({
  status: "partial",
  run_id: "dmrun_fixture",
  as_of_date: "2026-07-18",
  generated_at: "2026-07-18T12:00:00Z",
  progress: { current_stage: "run_auto_diligence", completed_count: 2, total_count: 4 },
  stages: [
    { stage: "scan_market_disturbance", status: "passed", reason_code: "" },
    { stage: "build_candidate_pool", status: "passed", reason_code: "" },
    { stage: "run_auto_diligence", status: "failed", reason_code: "llm_gateway_unavailable" },
    { stage: "build_daily_queue", status: "skipped", reason_code: "upstream_failed" },
  ],
  items: [{
    item_id: "dmitem_aapl",
    rank: 1,
    ticker: "AAPL",
    security_id: "sec_aapl",
    market: "U",
    selection_reason: "单日涨跌幅触发",
    trigger_metric: "one_day_return",
    trigger_value: 0.08,
    completeness_status: "complete",
    evidence_ids: ["evi_aapl"],
    missing_layers: [],
  }],
  pending_evidence_items: [{
    item_id: "dmitem_nvda",
    rank: 2,
    ticker: "NVDA",
    security_id: "sec_nvda",
    market: "U",
    selection_reason: "成交量放大",
    completeness_status: "partial",
    missing_layers: ["official_disclosure"],
    diligence_reason_code: "evidence_missing",
  }],
});

runtime.renderLatestAnalysis({
  status: "usable",
  window: { start_date: "2026-07-01", end_date: "2026-07-18" },
  generated_at: "2026-07-18T12:00:00Z",
  decision_summary: {
    headline: "Fixture research conclusion",
    conclusion: "Evidence remains paper-only.",
    red_flags: [],
    top_recommendations: [{ label: "AAPL", name: "Apple", stance: "watch", reasons: ["fixture"], risks: ["valuation"], total_return_pct: 3.2, security_id: "sec_aapl" }],
  },
  data_quality: { status: "usable", issues: [] },
  returns: [{ label: "AAPL", market: "U", total_return_pct: 3.2, security_id: "sec_aapl", source_id: "public_eod_market_data", end_date: "2026-07-18" }],
  weights: [{ label: "AAPL", weight_pct: 25, security_id: "sec_aapl" }],
  portfolio: { simulation_only: true, proposal_id: "proposal_fixture", review_flags: [] },
  research_evidence: { counts: { research_reports: 1, research_report_citation_evidence: 2 }, semantic_recall: { status: "available", samples: [] }, hotspot_recall: { status: "not_run", samples: [] } },
  source_summary: [{ source_id: "public_eod_market_data", markets: ["U"], license_classes: ["public"], asset_count: 1, latest_date: "2026-07-18" }],
  supplemental_market_observations: { observations: [] },
  business_acceptance: { passed: true, check_count: 4, failed_count: 0 },
  snapshots: [{ market: "A", as_of_date: "2026-07-17" }, { market: "U", as_of_date: "2026-07-18" }],
  personal_intelligence: { status: "usable", companies: [] },
  artifact_path: "/tmp/latest-analysis.json",
});

const assertions = {
  daily_mainline_status: element("dailyMainlineStatus").textContent === "partial",
  daily_mainline_rows: element("dailyMainlineRows").innerHTML.includes("AAPL") && element("dailyMainlineRows").innerHTML.includes("加入关注池"),
  daily_mainline_pending: element("dailyMainlinePending").hidden === false && element("dailyMainlinePendingRows").innerHTML.includes("NVDA"),
  daily_mainline_failure: element("dailyMainlineFailure").hidden === false
    && element("dailyMainlineFailure").textContent.includes("自动尽调")
    && element("dailyMainlineFailure").textContent.includes("llm_gateway_unavailable"),
  headline: element("decisionHeadline").textContent === "Fixture research conclusion",
  return_tile: element("analysisReturns").innerHTML.includes("AAPL") && element("analysisReturns").innerHTML.includes('data-action="open-security"'),
  weight: element("analysisWeights").innerHTML.includes("25%"),
  research: element("researchReportCount").textContent === "1" && element("researchCitationCount").textContent === "2",
  source: element("analysisSources").innerHTML.includes("public_eod_market_data"),
  market_dates: element("chipAshare").textContent === "A股 2026-07-17" && element("chipUs").textContent === "美股 2026-07-18",
  acceptance: element("chipAcceptance").textContent === "验收 4/4",
  personal_summary: personalSummaryCalls === 1,
  runtime_marker: document.body.dataset.uiRuntimeModules === "dashboard",
};

const failed = Object.entries(assertions).filter(([, passed]) => !passed).map(([name]) => name);
if (failed.length) throw new Error(`dashboard fixture assertions failed: ${failed.join(", ")}`);
console.log(JSON.stringify({ status: "passed", assertions: Object.keys(assertions), assertion_count: Object.keys(assertions).length }));
