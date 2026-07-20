# Handoff: T-575 Maintenance Risk Rebaseline

## Metadata

- Task ID: T-575
- Status: DONE
- Owner group: PM / Release Coordination
- Reviewer groups: Platform and Quality; Governance, Security, and Compliance
- Last updated: 2026-07-17
- Last agent: Codex `/root/t575_impl`
- Branch/worktree: shared current worktree

## Status

- Status: DONE
- Owner group: PM / Release Coordination
- Last updated: 2026-07-17
- Last agent: Codex `/root/t575_impl`
- Branch/worktree: shared current worktree

## Objective

Align canonical product metadata and documentation with the local-first company intelligence product, replace the stale test-isolation warning, and establish a lifecycle-based maintenance risk baseline without changing product behavior or roadmap status.

## Scope

- In scope: package description, canonical document metadata, test-isolation guidance, maintenance-risk lifecycle, roadmap index, and modularization ADR status.
- Out of scope: `tasks/todo.md`, runtime code, tests, API/storage/UI contracts, artifact deletion, and implementation of later maintenance tasks.

## Background

T-424 completed test isolation, but `AGENTS.md` still described it as unfinished. The package description retained the old virtual-fund MVP framing, the document index stopped at T-503, the risk register mixed historical product assumptions with current risks, and the modularization ADR did not record T-570/T-571.

## Problem Statement

Conflicting canonical metadata and undated operational facts increase onboarding and release-review risk. The absence of lifecycle fields also made active local maintenance risks indistinguishable from compatibility concerns and external production evidence blockers.

## Expected Deliverables

- Current product description without a package rename.
- Canonical metadata and dated volatile facts in primary documents.
- Lifecycle-based risk register with compatibility and external blockers separated.
- Roadmap document index through T-573.
- Modularization ADR through T-571 plus future explicit-store-injection direction.
- Passing document validation and a complete handoff.

## Current Findings

- T-424's handoff and README confirm direct tests are isolated by default.
- T-570 and T-571 extracted 34 pure helpers and reduced `app/services.py` from 33,921 to 33,499 lines at the dated 2026-07-10 baseline.
- `tasks/todo.md` classifies 17 remaining non-local release items as external evidence blockers rather than missing local code.

## Proposed Work Plan

1. Reconcile product and test metadata against completed handoffs.
2. Rebuild the risk register around current ownership and lifecycle.
3. Update the document index and ADR without claiming future implementation complete.
4. Validate TOML, Markdown links, handoff structure, and whitespace.

## Validation Plan

Run TOML parsing, `scripts/check_markdown_links.py`, `scripts/check_handoffs.py`, and `git diff --check`. Runtime suites are not required because no production code or behavior changes.

## Dependencies

- T-424 test-isolation handoff.
- T-570 and T-571 extraction handoffs.
- `tasks/todo.md` as the authoritative status and external-blocker source.

## Blockers

- None.

## Handoff Checklist

- [x] Documentation and metadata changes completed.
- [x] Product, paper-only, and non-local evidence boundaries preserved.
- [x] Validation commands run and results captured.
- [x] No roadmap status edited outside the parent PM owner.

## Current State

- Completed: package description updated while retaining `ai-native-quant-org`; core document metadata and dated artifact facts added; risks split into active maintenance, compatibility, and non-local external-evidence sections; modularization ADR updated through T-571 with an explicit-store-injection direction.
- In progress: none for T-575.
- Not started: enforcement of document metadata and artifact retention belongs to later, separate tasks.
- Blocked: none.

## Files Touched

- `pyproject.toml`: replaced the obsolete virtual-quant-fund MVP description; package name unchanged.
- `AGENTS.md`: replaced the pre-T-424 isolation caveat with the completed isolation baseline and retained clean-env as a diagnostic.
- `README.md`: added canonical metadata and dated volatile local artifact facts.
- `docs/README.md`: added canonical metadata and grouped the roadmap index through T-573.
- `docs/risk-register.md`: introduced risk lifecycle fields and separated current maintenance risks, compatibility-module risks, and 17 non-local external-evidence blockers.
- `docs/systemservice-modularization-adr.md`: recorded T-570/T-571 results and future explicit `store` injection direction without claiming stateful extraction complete.
- `docs/agent-handoffs/2026-07-17-T-575-maintenance-risk-rebaseline.md`: records scope, decisions, validation, and remaining risks.

## Evidence

```bash
python3 -c 'import tomllib; tomllib.load(open("pyproject.toml", "rb"))'
python3 scripts/check_markdown_links.py
python3 scripts/check_handoffs.py
git diff --check
```

Result:

- Passed: TOML parse, Markdown link check, handoff validation, and diff whitespace check.
- Failed: none.
- PM integration: `make local-ci` passed on 2026-07-17 with 353 tests plus UI static, security, Markdown, handoff, and canonical metadata gates.

## Decisions

- Retain the published package identifier `ai-native-quant-org`; renaming it requires a separate dependency and deployment impact audit.
- Treat artifact counts and readiness results in README as dated local snapshots whose own generated timestamps control freshness.
- Keep investment-committee, sign-off, execution-intent, and organizational release behavior as compatibility/operations modules rather than active product risks.
- Classify the 17 remaining non-local release items as external evidence dependencies; coordination packets and local artifacts cannot close them.
- Future stateful modules should receive the narrow `store` dependency explicitly, not the complete `SystemService`; this is direction only, not an implementation claim.

## Risks and Open Questions

- The risk register references planned maintenance task IDs T-574 and T-576-T-579; `tasks/todo.md` remains the sole authority for their creation and status and is intentionally owned by the parent PM agent.
- Existing historical documents outside the canonical set may still lack metadata. A later structural gate should start with the explicitly scoped canonical files rather than rewriting history.

## Artifacts

- No artifact generated. T-575 consumes existing local-only artifact paths only as dated documentation references; none is acceptable for a non-local production release gate.

## Next Steps

1. PM updates `tasks/todo.md` with the maintenance-risk task statuses and owners.
2. Platform implements the stateful workflow extraction with explicit store injection and facade parity tests.
3. Platform adds metadata and artifact-retention gates as separate, focused changes.

## SystemService Growth Freeze Review

- New `SystemService` business logic added: no; neither `app/services.py` nor production code was touched.
- Domain module decision: T-575 documents explicit `store` injection as the direction for a future stateful extraction and does not implement or claim that extraction.
- Focused regression: not applicable to this documentation-only task; T-570/T-571 handoffs record their completed facade regressions.
- API schema, storage schema, UI behavior, paper-only, and no-broker boundaries changed: no.

## Next Recommended Action

The parent PM agent should integrate this rebaseline, update `tasks/todo.md` as the sole roadmap owner, and keep subsequent implementation tasks in separate change sets.
