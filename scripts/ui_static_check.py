from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML_PATH = ROOT / "app" / "static" / "index.html"

REQUIRED_NAV_LABELS = [
    "总览",
    "数据中台",
    "研究工作台",
    "智能体协作",
    "策略实验室",
    "投委会",
    "知识图谱",
    "风控合规",
]

REQUIRED_STATUS_LABELS = [
    "服务检查中",
    "A股待载入",
    "美股待载入",
    "研究待载入",
    "验收待载入",
    "最新投研分析",
    "本地生产验收",
    "研报观点证据",
]

REQUIRED_IDS = [
    "metrics",
    "analysisMeta",
    "analysisStatus",
    "analysisReturns",
    "analysisWeights",
    "portfolioBoundary",
    "portfolioFlags",
    "analysisSources",
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
    "issuerBox",
    "securityRows",
    "researchRows",
    "graphChainCount",
    "graphPositionCount",
    "graphTaskCount",
    "graphEdgeCount",
    "graphPortfolioCount",
    "graphFactCount",
    "graphDecisionCount",
    "graphChainRows",
    "graphChainNodeRows",
    "graphCompanyPositionRows",
    "graphResearchTaskRows",
    "graphPortfolioRows",
    "graphFactRows",
    "graphDecisionRows",
    "graphEdgeRows",
    "documentRows",
    "entityMappingValidAt",
    "entityMappingRecordedAt",
    "entityMappingStatus",
    "entityMappingTotal",
    "entityMappingAccuracy",
    "entityMappingVersionCoverage",
    "entityMappingOverlapCount",
    "entityMappingLowConfidence",
    "entityMappingRows",
    "entityMappingIssueRows",
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
    "promptChangeRows",
    "llmRuns",
    "llmErrorRate",
    "llmCost",
    "llmBudgetUsed",
    "permissionAllowed",
    "permissionDenied",
    "permissionRedAllowed",
    "permissionRuleCount",
    "permissionDomainCount",
    "permissionRows",
    "decisionBox",
    "intentBox",
    "decisionSignerRole",
    "decisionSignerUser",
    "decisionSignComment",
    "exceptionSeverity",
    "exceptionReason",
    "decisionApprovalState",
    "decisionSignatureCount",
    "committeeOpenExceptions",
    "committeePendingDecisions",
    "committeeApprovalBoundary",
    "decisionSignatureRows",
    "committeeExceptionRows",
    "portfolioProposalId",
    "portfolioCommitteeDecision",
    "portfolioCommitteeMember",
    "portfolioFeedbackStart",
    "portfolioFeedbackEnd",
    "portfolioFeedbackProposal",
    "portfolioFeedbackStatus",
    "portfolioFeedbackDecision",
    "portfolioFeedbackBoundary",
    "portfolioFeedbackReturn",
    "portfolioProposalBox",
    "portfolioFeedbackBox",
    "replayCompareRows",
    "replayCompareCount",
    "replayVarianceCount",
    "replayLatestId",
    "replayReviewCount",
    "replayContinueCount",
    "marketDataRows",
    "manualReferenceRows",
    "holdingRows",
    "extractionBox",
    "scheduleBox",
    "playbooksBox",
    "reportsBox",
    "schedulesBox",
    "sourceReviewRows",
    "sourceReviewOwnerRows",
    "sourceReviewNotificationRows",
    "cpConclusionStatus",
    "cpConclusionScore",
    "cpConclusionConfidence",
    "cpConclusionTaskCount",
    "cpConclusionBox",
    "refreshCpConclusion",
]

REQUIRED_JS_FUNCTIONS = [
    "loadDashboard",
    "renderLatestAnalysis",
    "openTab",
    "openSecurityContext",
    "openResearchContext",
    "openCompanyContext",
    "openPortfolioContext",
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
    "renderChokepointConclusion",
    "finalizeChokepointRun",
]

REQUIRED_INTERACTION_MARKERS = [
    'data-action="open-security"',
    'data-action="open-research"',
    'data-action="open-company"',
    'data-action="open-hotspot"',
    'data-action="open-ingestion"',
    'document.addEventListener("click"',
]


def validate_ui_html(path: str | Path = HTML_PATH, *, run_node: bool = True) -> dict[str, object]:
    html_path = Path(path)
    html = html_path.read_text(encoding="utf-8")
    missing_nav = [label for label in REQUIRED_NAV_LABELS if label not in html]
    missing_status = [label for label in REQUIRED_STATUS_LABELS if label not in html]
    missing_ids = [item_id for item_id in REQUIRED_IDS if f'id="{item_id}"' not in html]
    missing_functions = [name for name in REQUIRED_JS_FUNCTIONS if f"function {name}(" not in html and f"async function {name}(" not in html]
    missing_interactions = [marker for marker in REQUIRED_INTERACTION_MARKERS if marker not in html]
    failures = {
        "nav": missing_nav,
        "status": missing_status,
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
    if any(failures.values()):
        raise AssertionError(json.dumps(failures, ensure_ascii=False, sort_keys=True))
    return {
        "path": str(html_path),
        "nav_labels": len(REQUIRED_NAV_LABELS),
        "status_labels": len(REQUIRED_STATUS_LABELS),
        "required_ids": len(REQUIRED_IDS),
        "required_functions": len(REQUIRED_JS_FUNCTIONS),
        "interaction_markers": len(REQUIRED_INTERACTION_MARKERS),
        "node_check": script_check,
    }


def _extract_script(html: str) -> str:
    start = html.index("<script>") + len("<script>")
    end = html.index("</script>", start)
    return html[start:end]


def main() -> None:
    print(json.dumps(validate_ui_html(), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
