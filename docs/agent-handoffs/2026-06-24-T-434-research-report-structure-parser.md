# Handoff: T-434 Research Report Structure Parser

## Metadata

- Status: DONE
- Owner group: Data and Evidence
- Last updated: 2026-06-24
- Last agent: Codex
- Branch/worktree: local workspace, branch not assumed
- Related task: T-434

## Objective

完善研报解析、分类和结构化落库链路，让已扫描的本地研报资产可以自动生成结构化研报、研报观点、预测和分析师画像。研报仍只作为关注度信号、观点样本库和可靠性复盘来源，不进入事实真相源、训练源或真实交易链路。

## Scope

- Add a lightweight rule parser for local research report metadata and available text.
- Add an API route to structure existing `ResearchReportAsset` rows into first-class viewpoint objects.
- Add a guarded UI entry for dry-run preview and explicit execution from the company intelligence workbench.
- Keep the change local-first, deterministic, idempotent, and paper/research-only.
- Update tests, API docs, roadmap notes, and this handoff.
- Out of scope: LLM extraction, large library batch execution, real trading, broker integration, or treating research reports as facts.

## Background

The product direction is now a company intelligence and market analysis platform. Research reports are intended to narrow the watchlist, preserve sell-side viewpoints, and support analyst reliability reviews. Before this pass, the project had research report assets, citation evidence, and first-class structured report models, but the automatic bridge from asset/text to structured viewpoints was thin.

## Problem Statement

Users could scan and extract local research report assets, and they could manually create `ResearchReport`, `ReportViewpoint`, and `ReportForecast` objects. However, there was no direct endpoint to transform existing report assets and citation text into those structured objects, which made the running platform feel like it had not really parsed or classified reports.

## Expected Deliverables

- `infer_structured_report_fields()` extracts report type, rating, target price, current price, analyst names, assumptions, forecasts, valuation method, catalysts, and risks.
- `POST /api/research-reports/structure` structures selected local report assets.
- Repeated runs skip existing structured reports by default.
- `dry_run=true` previews output without writing.
- `force=true` rebuilds deterministic child viewpoints and forecasts for the same report.
- `/ui` supports small-batch research report structure preview and explicit execution.
- Generated objects retain `opinion_only_not_fact_source`.
- Focused parser and service tests prove the end-to-end path.

## Current Findings

- The parser can classify Chinese/English title and text signals, including target price and EPS forecast samples.
- The service writes `ResearchReport`, `ReportViewpoint`, `ReportForecast`, and `AnalystProfile`.
- The UI company intelligence view renders structured reports, viewpoints, and forecasts once they exist in the store.
- The company intelligence view includes a guarded research report structure panel with `dry_run` preview, batch limit, keyword fallback, optional `force`, and explicit execution.

## Proposed Work Plan

1. Treat this pass as the T-434 parser and API completion layer.
2. Treat the UI panel as the first safe operator entry for small-batch structuring.
3. Use bounded API/UI batches for real local-library structuring after mapping quality is checked.

## Validation Plan

- Compile touched Python files and the broader app/test/script surface.
- Run parser unit tests.
- Run focused structure endpoint test.
- Run the existing research report governance/mapping/viewpoint report test.
- Run UI static and browser interaction acceptance for the guarded dry-run preview.
- Run handoff validation, security check, and optionally full unit discovery before commit.

## Risks

- Rule extraction is conservative and will be metadata-only for scanned PDFs until OCR/text extraction runs.
- Company mapping still depends on prior `ingest_research_report` issuer/security binding or reliable filters.
- Analyst reliability scoring still needs later actual-value review; this task creates forecast samples but does not verify realization.
- The endpoint can process many reports if called with a high limit; operators should start with dry-run or small batches.

## Dependencies

- Existing `ResearchReportAsset`, `Document`, `Evidence`, `ResearchReport`, `ReportViewpoint`, `ReportForecast`, and `AnalystProfile` models.
- Existing local report scan, ingest, and text extraction flows.
- Existing store commit behavior for SQLite/PostgreSQL/InMemory backends.

## Blockers

- None for the parser/API completion layer.

## Handoff Checklist

- [x] Parser added.
- [x] API route added.
- [x] Idempotent service behavior added.
- [x] Guarded UI dry-run/execute entry added.
- [x] Tests added.
- [x] API docs updated.
- [x] Roadmap updated.
- [x] Handoff added.
- [x] Full unit discovery run after final handoff formatting.

## Evidence

- `app/research_reports.py`: `infer_structured_report_fields()` and supporting extraction helpers.
- `app/services.py`: `structure_research_reports()` plus deterministic IDs and analyst profile handling.
- `app/api.py`: `POST /api/research-reports/structure`.
- `tests/test_research_reports.py`: parser coverage.
- `tests/test_system.py`: scan -> ingest -> extract -> structure -> query coverage and idempotency.
- `docs/api-contracts.md`: endpoint contract.
- `tasks/todo.md`: T-434 completion note.
- `app/static/index.html`: company intelligence report-structure panel and button handlers.
- `scripts/ui_static_check.py`: required IDs/functions for the new panel.
- `scripts/ui_interaction_acceptance.py`: browser dry-run preview check.

Commands run:

```bash
python3 -m py_compile app/research_reports.py app/services.py app/api.py tests/test_research_reports.py tests/test_system.py
python3 -m unittest tests.test_research_reports
python3 -m unittest tests.test_system.SystemServiceTests.test_research_report_structure_endpoint_writes_viewpoints_and_forecasts
python3 -m py_compile app/*.py tests/*.py scripts/*.py
python3 -m unittest tests.test_system.SystemServiceTests.test_research_report_structure_endpoint_writes_viewpoints_and_forecasts tests.test_system.SystemServiceTests.test_research_report_governance_mapping_and_viewpoint_reports
python3 scripts/check_handoffs.py
python3 -m unittest tests.test_system.SystemServiceTests.test_research_report_structure_endpoint_writes_viewpoints_and_forecasts tests.test_system.SystemServiceTests.test_research_report_governance_report_flags_stale_and_single_source_bias
python3 scripts/security_check.py .
python3 scripts/ui_static_check.py
python3 -m unittest discover -s tests
python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-report-structure --timeout 60
python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8766 --output-dir artifacts/ui-interaction-acceptance-report-structure --timeout 60
docker compose restart ai-quant-org
curl -sS -X POST http://127.0.0.1:8000/api/research-reports/structure -H 'Content-Type: application/json' -H 'X-Role: analyst' -H 'X-Actor: codex' --data '{"q":"SPCX","limit":2,"dry_run":true,"execute":false}'
```

Results:

- Passed: focused py_compile.
- Passed: broad py_compile.
- Passed: parser tests after tightening valuation and analyst extraction regex.
- Passed: focused T-434 system test after tightening analyst extraction regex.
- Failed: first parser test misclassified `EPS` as `P/S`; fixed with stricter valuation token matching.
- Failed: first focused system run included `评级：买入` in the second analyst name; fixed by stopping analyst extraction at downstream labels.
- Passed: corrected focused T-434 plus existing governance/mapping/viewpoint test, 2 tests.
- Passed: final handoff validation, 10 markdown files.
- Passed: security check, `ok=true`, `findings=[]`.
- Passed: UI static check, `node_check=passed`.
- Passed: full unit discovery, 214 tests.
- Passed: browser interaction acceptance against a clean current-worktree in-memory server on `127.0.0.1:8766`, `check_count=9`, `failure_count=0`, including `company_report_structure_preview_dry_run`.
- Passed: after `docker compose restart ai-quant-org`, `127.0.0.1:8000` loaded the new route and returned successful dry-run JSON for `POST /api/research-reports/structure`.
- Failed: one validation command referenced a non-existent old test method name; rerun with the correct method passed.
- Failed: first handoff validation used the shorter template; this handoff was rewritten to the repository's extended required structure.
- Failed: browser interaction acceptance against the pre-restart `127.0.0.1:8000` because that long-running process had not loaded the new `/api/research-reports/structure` route; a direct curl returned `route not found`, then the same acceptance passed against fresh current code on `127.0.0.1:8766` and the app container was restarted.
- Not run: `make local-ci` as a single command; its relevant component checks were run directly for this task.

Artifacts:

- `artifacts/ui-interaction-acceptance-report-structure/ui-interaction-acceptance.json`: local-only browser acceptance for the guarded report-structure preview.
- This handoff is local-only project coordination evidence.

## Next Recommended Action

For the real local library, run `POST /api/research-reports/structure` or the UI panel in bounded batches after mapping quality is checked.
