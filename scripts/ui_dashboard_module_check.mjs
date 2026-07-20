import { createDashboardRuntime } from "../app/static/ui_modules/dashboard.mjs";

const elements = new Map();
const element = (id) => {
  if (!elements.has(id)) elements.set(id, { id, className: "", innerHTML: "", textContent: "", value: "" });
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
