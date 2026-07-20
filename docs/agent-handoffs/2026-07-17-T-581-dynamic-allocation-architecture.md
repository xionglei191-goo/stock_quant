# Handoff: T-581 Dynamic Allocation Architecture

## Metadata

- Status: DONE
- Owner group: Research and AI Workflows
- Reviewer groups: Data and Evidence; Platform and Quality; Product and UI; Governance, Security, and Compliance
- Last updated: 2026-07-17
- Last agent: Codex
- Branch/worktree: current worktree (dirty before task)

## Objective

Translate the dynamic asset allocation report and user requirements into an implementation architecture that fits the existing local-first platform, preserves point-in-time evidence and paper-only boundaries, and can proceed through Phase 1 without training models.

## Scope

- In scope: repository layout, database design, core class contracts, API/UI boundary, roadmap, and Phase 1 implementation plan.
- Out of scope: dependency installation, schema migration, ingestion, factor calculation, model training, backtesting, Streamlit implementation, broker connectivity, and live execution.

## Background

The user supplied a deep report and an explicit seven-phase build request. The repository already contains market data, portfolio simulation, audit, SQLite/PostgreSQL adapters, a static `/ui` workbench, and strict service-growth and paper-only rules.

## Problem Statement

The requested standalone directory shape would duplicate existing platform capabilities and risk splitting storage, audit, API, and model logic. The system also needs explicit controls for macro release timing, data revisions, ETF pre-inception history, missing factors, and Kelly estimation uncertainty before implementation begins.

## Expected Deliverables

- An active architecture document covering directory, database, core classes, roadmap, and Phase 1.
- A roadmap task for the architecture and separate TODO tasks for each implementation phase.
- A document-index entry and reproducible handoff.
- No runtime or schema behavior change in this task.

## Current Findings

- Existing `market_data_bars`, portfolio APIs and audit records can be reused.
- High-volume PIT observations, factor values and backtest points need typed tables.
- Streamlit should consume the platform API and must not become a second calculation/store layer.
- Forward PE, FCF yield and survivorship-safe breadth sources are not yet source-governed.
- SGOV and HYG cannot provide authentic history for all requested stress periods; explicit proxies are required.

## Proposed Work Plan

1. T-582: implement PIT contracts, typed repository, providers and data health only.
2. T-583: implement eight explainable factor families.
3. T-584: implement the rule regime, five allocation buckets and first walk-forward backtest.
4. T-585 through T-588: compare HMM/Markov switching and ML, add fractional Kelly, build Streamlit, then run paper-only feedback.

## Validation Plan

- Validate required document metadata and all handoff sections.
- Run Markdown whitespace checks.
- Confirm task IDs and handoff filenames do not collide with concurrent work.
- Defer unit/UI/security suites because no executable code, API, schema or UI changed.

## Risks

- Source rights and PIT coverage remain unresolved for several requested factors.
- Phase 1 typed storage must coexist with current PostgreSQL lazy market-data behavior and SQLite persistence.
- Main `/ui` to Streamlit navigation and deployment should be finalized only after the API stabilizes.
- Missing data must not be silently mapped to a neutral score.

## Dependencies

- Existing `MarketDataPoint`, portfolio simulation APIs, stores and audit contracts.
- Source governance for every automated external series.
- T-580 was allocated concurrently to local artifact cleanup, so this architecture uses T-581.

## Blockers

- None for architecture completion.
- Automated use of ungoverned valuation and historical breadth data is blocked until an authoritative PIT source is approved.

## Handoff Checklist

- [x] Architecture document created
- [x] Roadmap updated without overwriting concurrent task IDs
- [x] Document index updated
- [x] Runtime changes intentionally excluded
- [x] Paper-only/no-broker boundary recorded
- [x] Validation results recorded

## Evidence

Commands run:

```bash
rg -n "dynamic allocation and portfolio terms" tasks/todo.md docs README.md app tests scripts pyproject.toml
sed -n '<relevant ranges>' tasks/todo.md docs/README.md docs/system-architecture.md docs/api-contracts.md
sed -n '<relevant ranges>' docs/portfolio-construction-spec.md app/models.py app/store.py pyproject.toml app/static/index.html app/server.py
python3 scripts/check_handoffs.py
python3 scripts/check_doc_metadata.py
git diff --check
```

Result:

- Passed: repository/architecture inspection and canonical document metadata validation.
- Failed initially: handoff validation found the repository template lagged behind the validator; this record was expanded to the validator's required sections and rerun.
- Not run: code/unit/UI/security suites because this task changes design documents and roadmap only.
- `docs/dynamic-asset-allocation-architecture.md`: manually authored active architecture, local repository document, generated 2026-07-17, owner Research and AI Workflows, no sensitive data, not acceptable as non-local production release evidence.
- `docs/动态资产配置与因子模型深度报告.docx`: user-provided local-only research input, not modified, not a release gate artifact.

## SystemService Growth Freeze Review

- New `SystemService` business logic added: no.
- Domain module decision: future behavior belongs under `app/dynamic_allocation/`; the facade may only delegate for API compatibility.
- Focused regression: none in T-581 because no facade changed; T-582 must add domain/facade equivalence if it adds a facade.
- API schema, storage schema, UI behavior, or paper-only/no-broker boundaries changed: no; this document defines future contracts only.

## Next Recommended Action

1. Start T-582 with PIT DTO/config and SQLite/PostgreSQL repository contract tests.
2. Validate and register the first public/local sources before enabling provider execution.
3. Keep factor, model and Streamlit work out of Phase 1 until vintage and freshness gates pass.
