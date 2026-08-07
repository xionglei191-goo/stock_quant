from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML_PATH = ROOT / "app" / "static" / "index.html"
UI_MODULES_DIR = ROOT / "app" / "static" / "ui_modules"

REQUIRED_UI_MODULES = [
    "dashboard",
    "company",
    "graph",
    "market",
    "admin",
    "helpers",
]

REQUIRED_NAV_LABELS = [
    "总览",
    "公司情报",
    "兼容审批",
    "知识图谱",
    "风控合规",
]

REQUIRED_STATUS_LABELS = [
    "公司情报与市场综合分析平台",
    "服务检查中",
    "A股待载入",
    "美股待载入",
    "研究待载入",
    "验收待载入",
    "最新公司情报分析",
    "本地生产验收",
    "研报观点证据",
]

REQUIRED_TEXT_SNIPPETS = [
    "请选择单一证券后查看时间序列，当前结果是多证券横截面",
    "当前结果只有单日数据，无法生成时间序列 K 线",
    'formValue("mdSecurityId", "sec_000670")',
    "拖动平移 · 滚轮缩放",
    "data-kline-period",
    "data-target-ui-action",
    "relationshipActionsByLayer",
    "industryDirection",
    "产业方向",
    "industry_direction",
    "query.industry_direction",
    "relationshipType",
    "relationshipTypeDisplayLabel",
    "item.relationship_type ? relationshipTypeDisplayLabel",
    "function knowledgeGraphLinkLabel",
    "const edgeLabel = knowledgeGraphLinkLabel(link)",
    "relationshipTypeDisplayLabel(item.default_kind",
    "item.source_issuer_id || item.from_issuer_id || item.subject_id",
    "item.target_issuer_id || item.to_issuer_id || item.object_id",
    "Array.isArray(meta.aliases) ? meta.aliases.find((item) => item)",
    "item.ticker || item.symbol || alias || item.name",
    "function graphHoldingLabel",
    "13F 持仓 · ${holder}",
    'shareholder: "事实股东"',
    "股权表追溯",
    "holdingStatusLabel",
    'controller_candidate: "实控候选"',
    'customer_candidate: "客户候选"',
    'upstream_of: "上游关系"',
    'position: "产业链位置"',
    "高级详情 / 追溯信息",
    "关键发现",
    "下一步或证据",
    "公司情报完整追溯",
    "决策追溯",
    "调度追溯",
    "材料入库追溯",
    "今日数据状态",
    "今天看什么",
    "python3 scripts/daily_mainline_run.py --as-of-date YYYY-MM-DD",
    'data-action="run-daily-mainline"',
    'data-workspace-target="personal"',
    "个人研究桌面",
    "maintenance-only",
    'data-workspace-mode="personal"',
    "source_input_queue",
    "required_source_fields",
    "previewGraphSourceInputQueue",
    "图谱来源输入队列",
    "previewKnowledgeGraphSourceInputQueue",
    "knowledgeGraphSourceInputQueuePayload",
    "checkKnowledgeGraphDisplayQuality",
    "knowledgeGraphQualityCenterPayload",
    "renderKnowledgeGraphQualityGate",
    "graphQualityRemediationForCheck",
    "remediation_actions",
    "处理动作",
    "graphLayoutTargetForNode",
    'knowledgeGraphState.scope === "global"',
    "communityCenter.x * 0.72",
    "/api/graph/quality-center",
    "max_display_duplicate_edges",
    "展示质量待检查",
    "需来源输入",
    "等待来源输入",
]

REQUIRED_IDS = [
    "metrics",
    "dailyMainlinePanel",
    "runDailyMainline",
    "dailyMainlineAsOf",
    "dailyMainlineGeneratedAt",
    "dailyMainlineStatus",
    "dailyMainlineProgress",
    "dailyMainlineFailure",
    "dailyMainlineRows",
    "dailyMainlinePending",
    "dailyMainlinePendingRows",
    "dailyMainlineEmpty",
    "analysisMeta",
    "analysisStatus",
    "analysisReturns",
    "analysisWeights",
    "portfolioBoundary",
    "portfolioFlags",
    "analysisSources",
    "dataHealthOverallStatus",
    "dataHealthFailureCount",
    "dataHealthPendingCount",
    "dataHealthRunCount",
    "dataHealthRows",
    "personalIntelStatus",
    "personalIntelCompanyCount",
    "personalIntelReadyCount",
    "personalIntelAttentionCount",
    "personalIntelArtifact",
    "personalIntelRows",
    "personalLoopStatus",
    "personalLoopDataIssues",
    "personalLoopFeedbackItems",
    "personalLoopGraphIssues",
    "personalLoopRows",
    "acceptanceStatus",
    "acceptanceChecks",
    "acceptanceFailed",
    "analysisArtifact",
    "researchReportCount",
    "researchCitationCount",
    "researchSemanticStatus",
    "researchHotspotStatus",
    "researchEvidenceRows",
    "marketRows",
    "crowding",
    "eventWall",
    "riskRows",
    "graphIssuer",
    "sysHealth",
    "companyIntelReportLimit",
    "companyIntelReportQuery",
    "companyIntelReportForce",
    "companyIntelVerdictStatus",
    "companyIntelVerdictScore",
    "companyIntelFactReadiness",
    "companyIntelAnalysisReadiness",
    "companyIntelFeedbackReadiness",
    "companyIntelFactFieldMissing",
    "companyIntelPersonalVerdict",
    "companyIntelPersonalEvent",
    "companyIntelPersonalViewpoint",
    "companyIntelPersonalFeedback",
    "companyIntelVerdictRows",
    "companyIntelGuidanceStatus",
    "companyIntelMissingCount",
    "companyIntelNextActionCount",
    "companyIntelMissingRows",
    "companyIntelNextActionRows",
    "companyIntelBuildLimit",
    "companyIntelAdvancedMaintenance",
    "companyIntelBatchSize",
    "companyIntelBatchStructureReports",
    "companyIntelProfileFieldList",
    "companyIntelProfileRequireEvidence",
    "companyIntelProfileRefreshExisting",
    "auditCompanyCoverage",
    "previewCompanyBatchBuild",
    "runCompanyBatchBuild",
    "loadCompanyBuildRuns",
    "loadCompanyCoverageTrends",
    "auditCompanyProfileFieldCoverage",
    "previewCompanyProfileFieldExtract",
    "runCompanyProfileFieldExtract",
    "loadCompanyProfileAssertionConflicts",
    "previewCompanyIntelCycle",
    "runCompanyIntelCycle",
    "loadCompanyIntelCycleRuns",
    "companyIntelPackageRootPath",
    "companyIntelPackageManifestGlob",
    "companyIntelPackageScanLimit",
    "previewCompanyPackageImport",
    "runCompanyPackageImport",
    "loadCompanyPackageImportRuns",
    "companyIntelPackageManifestOutputRoot",
    "previewCompanyPackageMaterialManifests",
    "runCompanyPackageMaterialManifests",
    "loadCompanyMaterialPending",
    "companyIntelMaterialRootPath",
    "companyIntelMaterialManifestGlob",
    "companyIntelMaterialScanLimit",
    "previewCompanyMaterialInbox",
    "runCompanyMaterialInbox",
    "previewCompanyQualityReconcile",
    "runCompanyQualityReconcile",
    "previewCompanyReportRealization",
    "runCompanyReportRealization",
    "companyIntelCoverageScore",
    "companyIntelCoverageMissing",
    "companyIntelBatchBuildStatus",
    "companyIntelRunHistoryStatus",
    "companyIntelRunHistoryCount",
    "companyIntelRunHistoryDelta",
    "companyIntelTrendStatus",
    "companyIntelTrendDelta",
    "companyIntelTrendMissingDelta",
    "companyIntelRunRows",
    "companyIntelTrendRows",
    "companyIntelProfileFieldCoverageStatus",
    "companyIntelProfileFieldCoverageScore",
    "companyIntelProfileFieldMissingCount",
    "companyIntelProfileFieldExtractStatus",
    "companyIntelProfileFieldCandidateCount",
    "companyIntelProfileFieldUpdatedCount",
    "companyIntelProfileAssertionReviewStatus",
    "companyIntelProfileAssertionConflictCount",
    "companyIntelProfileAssertionSupersededCount",
    "companyIntelProfileAssertionRecommendationStatus",
    "companyIntelProfileAssertionReviewNote",
    "batchApproveCompanyProfileAssertions",
    "batchRejectCompanyProfileAssertions",
    "companyIntelPackageImportStatus",
    "companyIntelPackagePlannedCount",
    "companyIntelPackageImportedCount",
    "companyIntelPackageInvalidCount",
    "companyIntelPackageRunHistoryStatus",
    "companyIntelPackageRunHistoryCount",
    "companyIntelPackageRunHistoryLatest",
    "companyIntelPackageManifestExportStatus",
    "companyIntelPackageManifestWrittenCount",
    "companyIntelMaterialPendingStatus",
    "companyIntelMaterialPendingCount",
    "companyIntelMaterialInboxStatus",
    "companyIntelMaterialPlannedCount",
    "companyIntelMaterialIngestedCount",
    "companyIntelOwnershipRootPath",
    "companyIntelOwnershipFiles",
    "companyIntelOwnershipDefaultKind",
    "previewCompanyOwnershipImport",
    "runCompanyOwnershipImport",
    "companyIntelOwnershipManifestGlob",
    "companyIntelOwnershipManifestOutputPath",
    "previewCompanyOwnershipManifest",
    "previewCompanyOwnershipImportFromManifest",
    "runCompanyOwnershipManifest",
    "companyIntelOwnershipImportStatus",
    "companyIntelOwnershipCandidateCount",
    "companyIntelOwnershipFileCount",
    "companyIntelOwnershipManifestStatus",
    "companyIntelOwnershipManifestFileCount",
    "companyIntelQualityReconcileStatus",
    "companyIntelEventDuplicateCount",
    "companyIntelRelationshipDuplicateCount",
    "companyIntelEntityMergeCandidateCount",
    "companyIntelSourceQualityCount",
    "previewGraphSourceQueue",
    "companyIntelGraphSourceQueueStatus",
    "companyIntelGraphSourceQueueLayerCount",
    "companyIntelGraphSourceQueueTargetCount",
    "companyIntelGraphSourceQueueUniqueTargetCount",
    "companyIntelRealizationStatus",
    "companyIntelRealizationUpdated",
    "companyIntelCycleStatus",
    "companyIntelCycleDelta",
    "companyIntelCycleFeedbackCount",
    "companyIntelCycleRunHistoryStatus",
    "companyIntelCycleRunHistoryCount",
    "companyIntelCycleRunRows",
    "companyIntelCoverageRows",
    "companyIntelProfileFieldRows",
    "companyIntelProfileFieldExtractRows",
    "companyIntelPackageImportRows",
    "companyIntelPackageImportRunRows",
    "companyIntelPackageManifestRows",
    "companyIntelMaterialPendingRows",
    "companyIntelMaterialInboxRows",
    "companyIntelOwnershipImportRows",
    "companyIntelOwnershipManifestRows",
    "companyIntelGraphSourceQueueRows",
    "companyIntelProfileAssertionReviewRows",
    "companyIntelQualityReconcileRows",
    "companyIntelOperationBox",
    "companyIntelEventReviewStatus",
    "companyIntelEventCandidateCount",
    "companyIntelEventRecommendationStatus",
    "companyIntelEventMergeTarget",
    "companyIntelEventTypeOverride",
    "companyIntelEventReviewNote",
    "batchApproveCompanyEvents",
    "batchRejectCompanyEvents",
    "companyIntelEventReviewRows",
    "companyIntelRelationshipMergeTarget",
    "companyIntelRelationshipReviewNote",
    "batchApproveCompanyRelationships",
    "batchRejectCompanyRelationships",
    "companyIntelRelationshipReviewStatus",
    "companyIntelRelationshipCandidateCount",
    "companyIntelRelationshipRecommendationStatus",
    "companyIntelRelationshipReviewRows",
    "previewCompanyReportStructure",
    "runCompanyReportStructure",
    "companyIntelReportStructureStatus",
    "companyIntelReportStructuredCount",
    "companyIntelReportViewpointCount",
    "companyIntelReportSkippedCount",
    "companyIntelReportMetadataOnlyCount",
    "companyIntelReportStructureRows",
    "companyIntelReportStructureBox",
    "secSingleTicker",
    "secSingleCik",
    "secSingleForms",
    "secSingleLimit",
    "secSingleSourceMode",
    "secSingleWorkflow",
    "secSingleDocumentId",
    "secSingleSignal",
    "secSingleSimulationMode",
    "secSingleStageRows",
    "secSingleEvidenceRows",
    "secSingleAnswerBox",
    "filingQaDocumentId",
    "filingQaQuestion",
    "filingQaEvidenceLimit",
    "filingQaAnswerId",
    "filingQaReviewStatus",
    "filingQaModelStatus",
    "filingQaSourceLink",
    "filingQaBoundary",
    "filingQaAnswerBox",
    "filingQaSourceBox",
    "filingQaEvidenceRows",
    "filingQaAuditRows",
    "hotspotQuery",
    "hotspotChainId",
    "hotspotDepth",
    "hotspotLexiconCount",
    "hotspotNodeCount",
    "hotspotCandidateCount",
    "hotspotTaskCount",
    "hotspotBoundary",
    "hotspotNodeRows",
    "hotspotCandidateRows",
    "hotspotEvidenceLayerRows",
    "hotspotTaskRows",
    "secSingleDecisionBox",
    "secSingleSimulationBox",
    "searchRows",
]

REQUIRED_JS_FUNCTIONS = [
    "loadDashboard",
    "renderDailyMainline",
    "loadDailyMainlineQueue",
    "runDailyMainline",
    "addDailyMainlineWatchlist",
    "dataHealthStatusClass",
    "dataHealthNextActionLabel",
    "renderDataHealthRows",
    "renderDataHealthSummary",
    "loadDataHealthSummary",
    "renderLatestAnalysis",
    "openTab",
    "openSecurityContext",
    "openResearchContext",
    "openCompanyContext",
    "seedDemo",
    "loadEntity",
    "renderEntityMappings",
    "renderEntityMappingQuality",
    "loadEntityMappings",
    "loadEntityMappingQuality",
    "createPromptChange",
    "approvePromptChange",
    "loadPromptChanges",
    "loadPermissionMatrix",
    "renderSecSingleNameResult",
    "renderFilingQaResult",
    "renderCompanyReportStructure",
    "renderPersonalIntelligenceSummary",
    "makeGraphModel",
    "renderKnowledgeGraphExplorer",
    "setupKnowledgeGraphControls",
    "setKnowledgeGraphActiveFilters",
    "renderKnowledgeGraphFilterChips",
    "selectKnowledgeGraphNode",
    "renderKnowledgeGraphInspector",
    "startKnowledgeGraphAnimation",
    "tickKnowledgeGraphLayout",
    "updateKnowledgeGraphSvgPositions",
    "structureCompanyReports",
    "renderCompanyIntelCompletenessVerdict",
    "renderCompanyIntelGuidance",
    "runCompanyIntelGuidanceAction",
    "recommendedGraphQueryAttrs",
    "runRelationshipBackfillAction",
    "renderCompanyCoverageAudit",
    "auditCompanyCoverage",
    "renderCompanyProfileFieldCoverage",
    "auditCompanyProfileFieldCoverage",
    "renderCompanyProfileFieldExtraction",
    "companyIntelProfileAssertionPayload",
    "renderCompanyProfileAssertionConflicts",
    "selectedCompanyProfileAssertionIds",
    "loadCompanyProfileAssertionConflicts",
    "reviewCompanyProfileFieldAssertion",
    "batchReviewCompanyProfileFieldAssertions",
    "extractCompanyProfileFields",
    "companyPackageImportPayload",
    "renderCompanyPackageImport",
    "companyPackageImportRunsPayload",
    "renderCompanyPackageImportRuns",
    "loadCompanyPackageImportRuns",
    "companyPackageMaterialManifestPayload",
    "companyPackageImportRunIdForManifestExport",
    "renderCompanyPackageMaterialManifests",
    "exportCompanyPackageMaterialManifests",
    "importCompanyPackage",
    "companyMaterialInboxPayload",
    "companyOwnershipImportPayload",
    "renderCompanyOwnershipImport",
    "ownershipReviewPayloadFromImport",
    "shouldUseLatestOwnershipManifest",
    "importCompanyOwnershipTables",
    "companyOwnershipManifestPayload",
    "renderCompanyOwnershipManifest",
    "generateCompanyOwnershipManifest",
    "previewCompanyOwnershipImportFromManifest",
    "renderCompanyMaterialInbox",
    "ingestCompanyMaterialInbox",
    "renderCompanyDatabaseQualityReconcile",
    "reconcileCompanyDatabaseQuality",
    "renderCompanyBatchBuild",
    "buildCompanyDatabaseBatch",
    "retryCompanyBuildRun",
    "renderCompanyBuildRunHistory",
    "loadCompanyBuildRuns",
    "companyIntelCoverageTrendPayload",
    "renderCompanyCoverageTrends",
    "loadCompanyCoverageTrends",
    "renderCompanyReportRealization",
    "updateCompanyReportRealization",
    "companyIntelCyclePayload",
    "renderCompanyIntelPersonalSummary",
    "renderCompanyIntelligenceCycle",
    "renderCompanyIntelligenceCycleRuns",
    "loadCompanyIntelligenceCycleRuns",
    "runCompanyIntelligenceCycle",
    "renderCompanyMaterialPending",
    "loadCompanyMaterialPending",
    "renderCompanyEventReview",
    "selectedCompanyEventIds",
    "reviewCompanyEvent",
    "batchReviewCompanyEvents",
    "renderCompanyRelationshipReview",
    "selectedCompanyRelationshipIds",
    "reviewCompanyRelationship",
    "batchReviewCompanyRelationships",
    "runSecSingleName",
    "runFilingQa",
    "renderHotspotExpansion",
    "runHotspotExpansion",
    "runSearch",
    "loadDecision",
    "renderDecisionGovernance",
    "renderCommitteeRisk",
    "loadCommitteeRisk",
    "signDecision",
    "createException",
    "loadIntent",
    "loadPortfolioProposal",
    "renderPortfolioFeedback",
    "runPortfolioFeedback",
    "compareReplays",
    "addMarketData",
    "loadMarketData",
    "isInternalIdentifier",
    "userEntityLabel",
    "userStatusLabel",
    "userSummaryLine",
    "renderReadableObjectSummary",
    "renderAdvancedPre",
    "renderAdvancedTrace",
    "renderActionableRows",
    "renderInsightTable",
    "klinePeriodLabel",
    "klinePeriodKey",
    "normalizeKlinePoints",
    "aggregateKlinePoints",
    "klineVisiblePoints",
    "updateKlineViewState",
    "movingAverage",
    "enabledMovingAverages",
    "setupKlineMaControls",
    "setKlinePeriod",
    "zoomKline",
    "resetKlineView",
    "shiftKlineWindow",
    "setupKlineViewControls",
    "renderKlineChart",
    "createManualReference",
    "loadManualReferences",
    "add13fHolding",
    "update13fCrowding",
    "load13fHoldings",
    "runExtraction",
    "createSchedule",
    "runSchedules",
    "loadIncidents",
    "loadSourceReviews",
    "notifySourceReviews",
]

REQUIRED_INTERACTION_MARKERS = [
    'data-action="run-daily-mainline"',
    'data-action="add-daily-watchlist"',
    'data-action="open-security"',
    'data-action="open-research"',
    'data-action="open-company"',
    'data-action="open-hotspot"',
    'data-action="open-ingestion"',
    'data-action="review-company-profile-assertion"',
    'data-action="review-company-event"',
    'data-action="review-company-relationship"',
    'data-action="run-relationship-backfill-action"',
    'data-evidence="${escapeHtml(item.evidence || "")}"',
    "setIndustryNetworkTrace",
    "industryRelationshipTraceAttrs",
    'data-industry-direction="${direction}"',
    "institutionalHolderKey",
    'data-institutional-holder-key="${item.holder_key || item.holder_id || ""}"',
    'data-ownership-holder-key="${item.holder_key || item.object_id || ""}"',
    "summary.shareholder_related_companies_total ??",
    "shareholderRelatedElement.dataset.networkTotal",
    'data-action="retry-company-build-run"',
    "data-company-profile-assertion-select",
    "data-company-event-select",
    "data-company-relationship-select",
    'document.addEventListener("click"',
]


def validate_ui_html(path: str | Path = HTML_PATH, *, run_node: bool = True) -> dict[str, object]:
    html_path = Path(path)
    html = html_path.read_text(encoding="utf-8")
    runtime_source = "\n".join(
        (UI_MODULES_DIR / f"{module_name}.mjs").read_text(encoding="utf-8")
        for module_name in REQUIRED_UI_MODULES
        if (UI_MODULES_DIR / f"{module_name}.mjs").exists()
    )
    missing_nav = [label for label in REQUIRED_NAV_LABELS if label not in html]
    missing_status = [label for label in REQUIRED_STATUS_LABELS if label not in html]
    missing_text = [snippet for snippet in REQUIRED_TEXT_SNIPPETS if snippet not in html]
    missing_ids = [item_id for item_id in REQUIRED_IDS if f'id="{item_id}"' not in html]
    missing_functions = [name for name in REQUIRED_JS_FUNCTIONS if f"function {name}(" not in html and f"async function {name}(" not in html]
    missing_interactions = [marker for marker in REQUIRED_INTERACTION_MARKERS if marker not in html and marker not in runtime_source]
    failures = {
        "nav": missing_nav,
        "status": missing_status,
        "text": missing_text,
        "ids": missing_ids,
        "functions": missing_functions,
        "interactions": missing_interactions,
    }
    script_check = "skipped"
    if run_node and shutil.which("node"):
        script = _extract_script(html)
        script_path = html_path.with_suffix(".ui-check.js")
        try:
            script_path.write_text(script, encoding="utf-8")
            subprocess.run(["node", "--check", str(script_path)], check=True, capture_output=True, text=True)
            script_check = "passed"
        finally:
            script_path.unlink(missing_ok=True)
    module_result = validate_ui_module_scaffold(run_node=run_node)
    if any(failures.values()):
        raise AssertionError(json.dumps(failures, ensure_ascii=False, sort_keys=True))
    return {
        "path": str(html_path),
        "nav_labels": len(REQUIRED_NAV_LABELS),
        "status_labels": len(REQUIRED_STATUS_LABELS),
        "text_snippets": len(REQUIRED_TEXT_SNIPPETS),
        "required_ids": len(REQUIRED_IDS),
        "required_functions": len(REQUIRED_JS_FUNCTIONS),
        "interaction_markers": len(REQUIRED_INTERACTION_MARKERS),
        "ui_module_scaffold": module_result,
        "node_check": script_check,
    }


def _extract_script(html: str) -> str:
    match = re.search(r'<script>(?P<script>.*?)</script>', html, re.DOTALL)
    if not match:
        raise AssertionError("/ui main runtime script is missing")
    return match.group("script")


def validate_ui_module_scaffold(*, run_node: bool = True) -> dict[str, object]:
    manifest_path = UI_MODULES_DIR / "manifest.json"
    missing_files = [str(manifest_path.relative_to(ROOT))] if not manifest_path.exists() else []
    missing_files.extend(
        str((UI_MODULES_DIR / f"{module_name}.mjs").relative_to(ROOT))
        for module_name in REQUIRED_UI_MODULES
        if not (UI_MODULES_DIR / f"{module_name}.mjs").exists()
    )
    if missing_files:
        raise AssertionError(json.dumps({"ui_modules": missing_files}, ensure_ascii=False, sort_keys=True))

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_domains = manifest.get("module_domains", [])
    missing_domains = [module_name for module_name in REQUIRED_UI_MODULES if module_name not in manifest_domains]
    runtime_modules = manifest.get("runtime_modules", [])
    scaffold_modules = manifest.get("scaffold_modules", [])
    invalid_partition = sorted(set(runtime_modules).intersection(scaffold_modules))
    missing_partition = [module_name for module_name in REQUIRED_UI_MODULES if module_name not in runtime_modules + scaffold_modules]
    required_runtime_modules = ["dashboard", "helpers"]
    missing_runtime_modules = [module_name for module_name in required_runtime_modules if module_name not in runtime_modules]
    if manifest.get("runtime_loaded") is not True or missing_runtime_modules or missing_domains or invalid_partition or missing_partition:
        raise AssertionError(
            json.dumps(
                {
                    "ui_module_manifest": {
                        "runtime_loaded": manifest.get("runtime_loaded"),
                        "missing_domains": missing_domains,
                        "missing_runtime_modules": missing_runtime_modules,
                        "invalid_partition": invalid_partition,
                        "missing_partition": missing_partition,
                    }
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )

    module_node_check = "skipped"
    if run_node and shutil.which("node"):
        for module_name in REQUIRED_UI_MODULES:
            subprocess.run(
                ["node", "--check", str(UI_MODULES_DIR / f"{module_name}.mjs")],
                check=True,
                capture_output=True,
                text=True,
            )
        module_node_check = "passed"

    html = HTML_PATH.read_text(encoding="utf-8")
    helper_import = 'import("/ui_modules/helpers.mjs")'
    helper_source = (UI_MODULES_DIR / "helpers.mjs").read_text(encoding="utf-8")
    dashboard_import = 'import("/ui_modules/dashboard.mjs")'
    dashboard_source = (UI_MODULES_DIR / "dashboard.mjs").read_text(encoding="utf-8")
    required_helper_exports = ["installNavigation"]
    missing_helper_exports = [
        name for name in required_helper_exports
        if f"export function {name}(" not in helper_source and f"export const {name} =" not in helper_source
    ]
    navigation_selector = 'document.querySelectorAll("[data-open]").forEach((button) => {'
    navigation_extracted = navigation_selector in helper_source and navigation_selector not in html
    dashboard_functions = [
        "dailyMainlineStatusClass",
        "renderDailyMainline",
        "loadDailyMainlineQueue",
        "runDailyMainline",
        "addDailyMainlineWatchlist",
        "dataHealthStatusClass",
        "dataHealthNextActionLabel",
        "renderDataHealthRows",
        "renderDataHealthSummary",
        "loadDataHealthSummary",
        "renderLatestAnalysis",
    ]
    dashboard_extracted = all(f"function {name}(" in dashboard_source for name in dashboard_functions)
    direct_dashboard_wrappers = [
        "renderDailyMainline",
        "dataHealthStatusClass",
        "dataHealthNextActionLabel",
        "renderDataHealthRows",
        "renderDataHealthSummary",
        "renderLatestAnalysis",
    ]
    ready_dashboard_wrappers = [
        "loadDailyMainlineQueue",
        "runDailyMainline",
        "addDailyMainlineWatchlist",
        "loadDataHealthSummary",
    ]
    dashboard_wrappers = all(f"return dashboardRuntime.{name}(" in html for name in direct_dashboard_wrappers)
    dashboard_wrappers = dashboard_wrappers and all(
        f"return runtime.{name}(" in html for name in ready_dashboard_wrappers
    )
    if (
        helper_import not in html
        or dashboard_import not in html
        or missing_helper_exports
        or "export const scaffoldOnly = false" not in helper_source
        or "export const scaffoldOnly = false" not in dashboard_source
        or not navigation_extracted
        or not dashboard_extracted
        or not dashboard_wrappers
    ):
        raise AssertionError(
            json.dumps(
                {
                    "ui_module_runtime": {
                        "helper_import": helper_import in html,
                        "dashboard_import": dashboard_import in html,
                        "missing_helper_exports": missing_helper_exports,
                        "helpers_runtime": "export const scaffoldOnly = false" in helper_source,
                        "navigation_extracted": navigation_extracted,
                        "dashboard_extracted": dashboard_extracted,
                        "dashboard_wrappers": dashboard_wrappers,
                    }
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )

    return {
        "manifest": str(manifest_path.relative_to(ROOT)),
        "modules": len(REQUIRED_UI_MODULES),
        "runtime_loaded": manifest.get("runtime_loaded"),
        "runtime_modules": runtime_modules,
        "node_check": module_node_check,
    }


def main() -> None:
    print(json.dumps(validate_ui_html(), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
