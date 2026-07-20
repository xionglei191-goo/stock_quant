# Handoff: T-578 Local Artifact Retention

## Metadata

- Status: DONE
- Owner group: Platform and Quality
- Reviewer groups: PM / Release Coordination
- Last updated: 2026-07-17
- Last agent: Codex
- Branch/worktree: main

## Objective

Stop browser acceptance runs from persisting Chromium profiles inside local evidence directories, and provide a dry-run-first retention audit for known temporary output without deleting current evidence.

## Scope

- In scope: Chromium profile lifecycle, local artifact inventory/retention CLI, focused safety tests, Make target, artifact governance documentation.
- Out of scope: deleting current files, cleaning TDX/research/object-store data, changing non-local release evidence policy.

## Background

The ignored `artifacts/` tree uses about 2.3 GB. Much of the largest acceptance output comes from reusable Chromium profiles; `data/artifacts/staging-ui` also contains repeated local captures. These are local disk concerns rather than Git history growth.

## Problem Statement

Browser user-data directories survived acceptance runs, while the repository had policy prose but no executable inventory, retention window, or deletion safety checks.

## Expected Deliverables

- Temporary, uniquely named Chromium profiles with cleanup in `finally` paths.
- A local-only audit CLI that performs no deletion by default.
- Safety regression for retention window, tracked/reference protection, latest retention, and symlinks.
- A non-destructive `make artifact-audit` entry point.

## Current Findings

- The first dry-run discovered 601 known profile/staging directories and classified 547 as eligible under the default 14-day/two-latest policy.
- The dry-run deleted zero paths and reclaimed zero bytes.
- Four root example artifacts are Git tracked; the retention tool protects all tracked descendants rather than relying only on filename conventions.

## Proposed Work Plan

1. Completed browser profile lifecycle changes in both acceptance runners that create user-data directories.
2. Completed the audit/retention CLI and focused tests.
3. Completed governance and Make target documentation.
4. Leave any real deletion for a separately approved operator action after reviewing the dry-run report.

## Validation Plan

Run focused unit tests and compilation, execute the real repository audit without `--execute`, then include the full repository quality gate in PM integration.

## Risks

- The inventory intentionally covers only known browser profiles and staging UI generations; other ignored local output is reported by normal disk tooling but not deleted by this command.
- Evidence references are protected by exact repository-relative path text; renamed or externally referenced evidence still requires operator review.

## Dependencies

- Python standard library and local Git metadata only.
- No external service, broker, or production environment dependency.

## Blockers

- None for the implementation. Actual deletion remains intentionally unapproved.

## Handoff Checklist

- [x] Code changes completed
- [x] Tests/checks run or explicitly skipped with reason
- [x] Docs/contracts updated if applicable
- [x] `tasks/todo.md` status updated by PM integration

## Evidence

Commands run:

```bash
python3 -m unittest tests.test_local_artifact_retention
python3 -m py_compile scripts/local_artifact_retention.py scripts/ui_interaction_acceptance.py scripts/ui_research_workbench_matrix.py tests/test_local_artifact_retention.py
python3 scripts/local_artifact_retention.py --target all --output /tmp/t578-artifact-audit.json
git diff --check -- scripts/local_artifact_retention.py scripts/ui_interaction_acceptance.py scripts/ui_research_workbench_matrix.py tests/test_local_artifact_retention.py Makefile
```

Result:

- Passed: 4 focused tests, compilation, dry-run audit, whitespace validation.
- Failed: none.
- Not run: browser-level acceptance, because no local server was started for this maintenance-only task.
- PM integration: `make local-ci` passed on 2026-07-17 with 353 tests plus UI static, security, Markdown, handoff, and canonical metadata gates.
- Artifact: `/tmp/t578-artifact-audit.json`; producer `scripts/local_artifact_retention.py`; generated 2026-07-17; local-only; contains path/size/mtime inventory and no secrets; not acceptable for non-local release gates.

## Next Recommended Action

1. Run the full local quality gate after all parallel tasks have finished.
2. Review `/tmp/t578-artifact-audit.json` before considering an explicit cleanup command.
3. Keep destructive retention outside automated CI.
