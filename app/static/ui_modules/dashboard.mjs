export const moduleDomain = "dashboard";
export const scaffoldOnly = false;

export function createDashboardRuntime({
  $,
  api,
  boundaryLabel,
  documentTypeLabel,
  metaLine,
  pct,
  rawPct,
  renderAdvancedTrace,
  renderPersonalIntelligenceSummary,
  rows,
  setText,
  shortPath,
  signedPct,
  sourceLabel,
  statusLabel,
  toneForNumber,
  userEntityLabel,
}) {
  function dataHealthStatusClass(value) {
    const normalized = String(value || "").toLowerCase();
    if (["healthy", "success", "ok", "available", "ready"].includes(normalized)) return "ok";
    if (["failed", "missing", "stale"].includes(normalized)) return "block";
    return "warn";
  }

  function dataHealthNextActionLabel(item = {}) {
    const actions = item.next_actions || [];
    if (actions.length) return actions.map((action) => statusLabel(action.action || action.endpoint || "下一步")).join(" / ");
    return statusLabel(item.next_action || "monitor_next_refresh");
  }

  function renderDataHealthRows(targetId, sources = []) {
    $(targetId).innerHTML = rows(sources, "暂无来源健康摘要", (item) => {
      const evidence = item.evidence || {};
      const facts = [];
      if (evidence.market_data_count !== undefined) facts.push(`行情 ${evidence.market_data_count}`);
      if (evidence.research_report_assets !== undefined) facts.push(`研报 ${evidence.research_report_assets}`);
      if (evidence.disclosure_events !== undefined) facts.push(`披露 ${evidence.disclosure_events}`);
      if (evidence.company_profiles !== undefined) facts.push(`画像 ${evidence.company_profiles}`);
      if (evidence.simulation_feedback_count !== undefined) facts.push(`反馈 ${evidence.simulation_feedback_count}`);
      if (item.pending_count) facts.push(`待处理 ${item.pending_count}`);
      const judgment = facts.join(" · ") || boundaryLabel(item.usage_boundary);
      return `<tr>
        <td>${item.label || statusLabel(item.source_key || item.domain || "来源")}</td>
        <td>${judgment}</td>
        <td><span class="badge ${dataHealthStatusClass(item.status)}">${statusLabel(item.status || item.freshness_level || "")}</span></td>
        <td>${dataHealthNextActionLabel(item)}${renderAdvancedTrace("来源健康追溯", item)}</td>
      </tr>`;
    });
  }

  function renderDataHealthSummary(data = {}) {
    const summary = data.summary || {};
    const sources = data.sources || [];
    const overallStatus = summary.failure_count ? "需要处理" : (summary.pending_count ? "有待补项" : "健康");
    setText("dataHealthOverallStatus", overallStatus);
    setText("dataHealthFailureCount", `${summary.failure_count || 0}`);
    setText("dataHealthPendingCount", `${summary.pending_count || 0}`);
    setText("dataHealthRunCount", `${data.run_count || 0}`);
    setText("sourceHealthOverallStatus", overallStatus);
    setText("sourceHealthFailureCount", `${summary.failure_count || 0}`);
    setText("sourceHealthPendingCount", `${summary.pending_count || 0}`);
    setText("sourceHealthRunCount", `${data.run_count || 0}`);
    renderDataHealthRows("dataHealthRows", sources);
    renderDataHealthRows("sourceHealthRows", sources);
  }

  async function loadDataHealthSummary() {
    const { data } = await api("/api/data-health/summary", { role: "analyst" });
    renderDataHealthSummary(data || {});
    return data;
  }

  function renderLatestAnalysis(data) {
    const window = data.window || {};
    $("analysisStatus").textContent = data.status ? statusLabel(data.status) : "可用";
    $("analysisMeta").textContent = `${window.start_date || "-"} 至 ${window.end_date || data.latest_market_date || "-"} · ${data.generated_at || "本地产物"}`;
    const dailyInsight = data.daily_insight || {};
    const dailySummary = dailyInsight.actionable_research_summary || {};
    const directWatchItems = dailySummary.direct_report_watch_items || [];
    const companyRecentActivity = dailySummary.company_recent_activity_items || dailyInsight.research_and_events?.company_recent_activity || [];
    const companyIntelligence = data.company_intelligence || {};
    const companyIntelligenceRows = companyIntelligence.companies || [];
    const decision = data.decision_summary || {};
    const quality = data.data_quality || {};
    $("decisionHeadline").textContent = dailySummary.headline || decision.headline || "当前没有可用结论";
    $("decisionConclusion").textContent = dailySummary.headline
      ? `每日证据门禁: ${dailySummary.direct_report_evidence_company_count || 0} 个标的有直接研报证据 · 行情日期 ${dailyInsight.market_freshness?.map((item) => `${item.market}:${item.latest_date || "-"}`).join(" / ") || data.latest_market_date || "-"}`
      : (decision.conclusion || `数据质量: ${statusLabel(quality.status || "missing")}`);
    const recommendations = directWatchItems.length ? directWatchItems.map((item) => ({
      label: item.ticker,
      name: item.issuer_name,
      market: item.market,
      stance: "直接研报证据",
      reasons: [item.research_readout || `${item.report_count || 0} 份研报 / ${item.evidence_count || 0} 条证据`],
      risks: [`产业链: ${item.chain || "-"}`, `节点: ${(item.nodes || []).slice(0, 2).join(", ") || "-"}`],
      evidence_status: item.evidence_status,
      total_return_pct: null,
      security_id: item.security_id || ""
    })) : (decision.top_recommendations || []);
    $("decisionRecommendationRows").innerHTML = recommendations.length ? recommendations.slice(0, 4).map((item) => `
      <div class="recommendation-row" data-action="open-security" data-security-id="${item.security_id || ""}" data-label="${item.label || ""}" title="点击查看行情数据">
        <div>
          <strong>${item.label || "-"}</strong>
          <span class="small-note">${item.name || item.market || "-"} · ${statusLabel(item.stance || item.action)}</span>
        </div>
        <div>
          <span class="small-note">${(item.reasons || []).slice(0, 2).join(" · ") || "暂无理由"}</span>
          <span class="small-note">${(item.risks || []).slice(0, 2).join(" · ") || statusLabel(item.evidence_status || "")}</span>
        </div>
        <div class="metric ${toneForNumber(item.total_return_pct)}">${signedPct(item.total_return_pct)}</div>
      </div>
    `).join("") : `<span class="small-note">暂无研究候选</span>`;
    const insightGates = dailyInsight.quality_gates || {};
    const flags = dailySummary.abnormal_headline
      ? [
        dailySummary.abnormal_headline,
        `typed-only K线=${insightGates.typed_only_market_data ? "通过" : "失败"} · 直接证据=${insightGates.direct_report_evidence_company_count || 0}/${insightGates.min_direct_evidence_companies || 0}`
      ]
      : (decision.red_flags || (quality.issues || []).map((item) => item.message));
    $("decisionFlagRows").innerHTML = flags.length ? flags.slice(0, 5).map((item) => `<div class="flag-row">${item}</div>`).join("") : `<div class="flag-row">当前未发现阻塞性红旗，但仍只限本机研究和模拟组合。</div>`;
    $("companyRecentActivityCount").textContent = `${dailySummary.company_recent_activity_count || dailyInsight.research_and_events?.company_recent_activity_count || companyRecentActivity.length || 0}`;
    $("companyRecentReportCount").textContent = `${companyRecentActivity.reduce((sum, item) => sum + (item.activity_count || 0), 0)}`;
    $("companyRecentEvidenceCount").textContent = `${companyRecentActivity.reduce((sum, item) => sum + (item.evidence_count || 0), 0)}`;
    $("companyRecentActivityGate").textContent = insightGates.has_company_recent_activity ? "通过" : "待补";
    $("companyRecentActivityGate").className = `badge ${insightGates.has_company_recent_activity ? "ok" : "warn"}`;
    $("companyRecentActivityRows").innerHTML = rows(companyRecentActivity, "暂无公司级近期活动", (item) => `
      <tr data-action="${item.issuer_id ? "open-company" : "open-security"}" data-issuer-id="${item.issuer_id || ""}" data-security-id="${item.security_id || ""}" data-label="${item.ticker || ""}" title="点击载入主体图谱">
        <td>${item.ticker || "-"}${metaLine("公司", item.issuer_name || "")}</td>
        <td>${item.chain || "-"}${metaLine("节点", (item.nodes || []).slice(0, 3).join(", ") || "-")}</td>
        <td>${(item.latest_market?.as_of_date || "-")}${metaLine("收盘", item.latest_market?.close ?? "")}${metaLine("涨跌", signedPct(item.latest_market?.one_day_return))}</td>
        <td>${item.activity_summary || "-"}</td>
      </tr>
    `);
    $("companyIntelligenceRows").innerHTML = rows(companyIntelligenceRows, "暂无公司情报链路", (item) => {
      const counts = item.company_counts || {};
      const relationships = item.relationship_summary || {};
      const nextAction = (item.next_actions || [])[0] || {};
      const coverage = item.coverage_score == null ? "-" : pct(item.coverage_score);
      const statusTone = item.status === "missing" ? "warn" : item.status === "available" || item.status === "ready" ? "ok" : "block";
      const formed = [
        `画像 ${counts.company_profiles || 0}`,
        `事件 ${counts.company_events || 0}`,
        `关系 ${counts.company_relationships || 0}`,
        `结论 ${counts.analysis_conclusions || 0}`,
        `反馈 ${counts.simulation_feedback_records || 0}`
      ].join(" · ");
      const relationText = [
        `产业链 ${relationships.industry_related_companies_total || 0}`,
        `股东 ${relationships.shareholder_related_companies_total || 0}`,
        `事实股权 ${relationships.approved_ownership_relationships || 0}`,
        `候选 ${relationships.ownership_candidates || 0}`
      ].join(" · ");
      const next = nextAction.label || nextAction.reason || "继续补齐链路";
      return `<tr data-action="open-company-intel" data-symbol="${item.symbol || ""}" title="点击载入公司情报"><td>${item.symbol || "-"}</td><td><span class="badge ${statusTone}">${statusLabel(item.status || "")}</span>${metaLine("完整度", coverage)}${metaLine("关系", item.relationship_status || "-")}</td><td>${formed}${metaLine("链路", relationText)}</td><td>${next}${nextAction.endpoint ? metaLine("动作", nextAction.endpoint) : ""}</td></tr>`;
    });
    $("companyIntelCount").textContent = `${companyIntelligence.company_count || companyIntelligenceRows.length || 0}`;
    $("companyIntelReadyCount").textContent = `${companyIntelligence.ready_count || 0}`;
    $("companyIntelAttentionCount").textContent = `${companyIntelligence.needs_attention_count || 0}`;
    $("companyIntelArtifact").textContent = shortPath(data.artifact_path || "");
    const topReturns = (data.returns || []).slice().sort((a, b) => Math.abs(b.total_return_pct || 0) - Math.abs(a.total_return_pct || 0)).slice(0, 9);
    $("analysisReturns").innerHTML = topReturns.length ? topReturns.map((item) => `
      <div class="return-tile" data-action="open-security" data-security-id="${item.security_id || ""}" data-label="${item.label || ""}" title="点击查看行情数据">
        <strong>${item.label}</strong>
        <div class="number ${toneForNumber(item.total_return_pct)}">${signedPct(item.total_return_pct)}</div>
        <span class="small-note">${item.market || "-"} · ${sourceLabel(item.source_id)} · ${item.end_date || "-"}</span>
      </div>
    `).join("") : `<div class="return-tile"><strong>无分析结果</strong><span class="small-note">${data.message || "请先运行最新分析脚本"}</span></div>`;

    const weights = (data.weights || []).filter((item) => Number(item.weight_pct || 0) > 0.01).slice(0, 8);
    $("analysisWeights").innerHTML = weights.length ? weights.map((item) => `
      <div class="weight-row" data-action="open-security" data-security-id="${item.security_id || ""}" data-label="${item.label || ""}" title="点击查看行情数据">
        <strong>${item.label}</strong>
        <div class="bar"><span style="width:${Math.max(1, Math.min(100, item.weight_pct || 0))}%"></span></div>
        <span>${rawPct(item.weight_pct)}</span>
      </div>
    `).join("") : `<span class="small-note">暂无组合权重</span>`;
    const portfolioFlags = data.portfolio?.review_flags || [];
    $("portfolioBoundary").textContent = data.portfolio?.simulation_only === false ? "需要复核" : "仅模拟";
    $("portfolioFlags").textContent = portfolioFlags.length ? portfolioFlags.map((item) => item.flag || item.message).join(" · ") : "组合建议仅用于研究与回放。";
    if (data.portfolio?.proposal_id) {
      $("portfolioProposalId").value = data.portfolio.proposal_id;
    }

    const researchEvidence = data.research_evidence || {};
    const researchCounts = researchEvidence.counts || {};
    const semanticRecall = researchEvidence.semantic_recall || {};
    const hotspotRecall = researchEvidence.hotspot_recall || {};
    $("researchReportCount").textContent = `${researchCounts.research_reports || data.counts?.research_reports || 0}`;
    $("researchCitationCount").textContent = `${researchCounts.research_report_citation_evidence || data.counts?.research_report_citation_evidence || 0}`;
    $("researchSemanticStatus").textContent = statusLabel(semanticRecall.status || "not_run");
    $("researchHotspotStatus").textContent = statusLabel(hotspotRecall.status || "not_run");
    const researchRows = [...(semanticRecall.samples || []), ...(hotspotRecall.samples || [])].slice(0, 8);
    $("researchEvidenceRows").innerHTML = rows(researchRows, "暂无研报观点证据召回", (item) => `
      <tr data-action="open-research" data-resource-id="${item.resource_id || ""}" data-title="${item.title || ""}" data-snippet="${(item.snippet || "").replace(/"/g, "&quot;")}" title="点击进入研究工作台检索">
        <td>${documentTypeLabel(item.resource_type || item.document_type || "-")}</td>
        <td>${item.title || userEntityLabel(item.resource_id, "研究资料")}${renderAdvancedTrace("资料追溯", item)}</td>
        <td>${boundaryLabel(item.source_boundary) || statusLabel(item.risk_level)}</td>
        <td>${(item.snippet || "").slice(0, 180)}</td>
      </tr>
    `);

    $("analysisSources").innerHTML = (data.source_summary || []).map((item) => `
      <div class="source-row" data-action="open-ingestion" title="点击查看数据接入">
        <div>
          <strong>${sourceLabel(item.source_id)}</strong>
          <div class="small-note">${(item.markets || []).join(", ") || "-"} · ${(item.license_classes || []).join(", ") || "-"}</div>
        </div>
        <span class="badge ok">${item.asset_count} · ${item.latest_date || "-"}</span>
      </div>
    `).join("") || `<span class="small-note">暂无来源摘要</span>`;

    const supplementalObservations = data.supplemental_market_observations?.observations || [];
    $("supplementalObservationRows").innerHTML = rows(supplementalObservations, "暂无补充观察", (item) => `
      <tr data-action="open-security" data-security-id="sec_${item.label || ""}" data-label="${item.label || ""}" title="点击查看正式行情">
        <td>${item.label || "-"}</td>
        <td>${item.official_as_of_date || "-"}${metaLine("收盘", item.official_close ?? "")}</td>
        <td>${item.supplemental_as_of_date || "-"}${metaLine("快照", item.supplemental_close ?? "")}${metaLine("变化", signedPct(item.price_change_since_official_close_pct))}</td>
        <td>${boundaryLabel(item.source_boundary)}</td>
      </tr>
    `);

    const acceptance = data.business_acceptance || {};
    $("acceptanceStatus").textContent = acceptance.passed ? "通过" : acceptance.artifact_path ? "存在失败项" : "未执行";
    $("acceptanceChecks").textContent = `${acceptance.check_count || 0}`;
    $("acceptanceFailed").textContent = `${acceptance.failed_count || 0}`;
    $("analysisArtifact").textContent = shortPath(data.artifact_path);

    const snapshots = data.snapshots || [];
    const latestA = snapshots.filter((item) => item.market === "A").map((item) => item.as_of_date).sort().pop();
    const latestU = snapshots.filter((item) => item.market === "U").map((item) => item.as_of_date).sort().pop();
    $("chipAshare").textContent = `A股 ${latestA || "-"}`;
    $("chipUs").textContent = `美股 ${latestU || "-"}`;
    $("chipAcceptance").textContent = acceptance.passed ? `验收 ${acceptance.check_count || 0}/${acceptance.check_count || 0}` : `验收失败 ${acceptance.failed_count || 0}`;
    $("chipAcceptance").className = acceptance.passed ? "chip green" : "chip warn";
    renderPersonalIntelligenceSummary(data.personal_intelligence || {}, data.personal_intelligence_artifact_path || "");
  }

  const currentModules = new Set((document.body.dataset.uiRuntimeModules || "").split(",").filter(Boolean));
  currentModules.add(moduleDomain);
  document.body.dataset.uiRuntimeModules = [...currentModules].sort().join(",");

  return {
    dataHealthNextActionLabel,
    dataHealthStatusClass,
    loadDataHealthSummary,
    renderLatestAnalysis,
    renderDataHealthRows,
    renderDataHealthSummary,
  };
}
