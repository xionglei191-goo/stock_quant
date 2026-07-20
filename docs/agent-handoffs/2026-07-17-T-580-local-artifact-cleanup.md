# Handoff: T-580 Local Artifact Cleanup

## Metadata

- Status: DONE
- Owner group: Platform and Quality
- Reviewer groups: PM / Release Coordination
- Last updated: 2026-07-17
- Last agent: Codex
- Branch/worktree: main

## Objective

Execute the T-578 retention policy against currently eligible local browser and staging UI temporary output, then verify that protected evidence and tracked templates remain intact.

## Scope

- In scope: expired Chromium profile directories and expired `data/artifacts/staging-ui` generations selected by the retention tool.
- Out of scope: TDX data, research reports, object-store data, Git-tracked/example artifacts, current references, symlinks, and unrelated untracked documents.

## Background

T-578 introduced a dry-run-first retention tool and identified a large set of ignored browser/staging directories. The user explicitly approved cleaning all paths that satisfy those safety rules.

## Problem Statement

The local artifact tree still occupied about 2.3 GB even though most historical browser profile data and staging captures were temporary and reproducible.

## Expected Deliverables

- A successful execute-mode report.
- A post-clean dry-run with no remaining eligible paths.
- Preserved tracked templates and persistent data boundaries.
- Recorded before/after disk usage.

## Current Findings

- Pre-clean: 605 discovered paths, 547 eligible paths.
- Execute: 547 directories deleted; 2,280,372,239 bytes reclaimed (about 2.12 GiB).
- Post-clean: 58 protected/recent paths discovered; zero eligible paths.
- Disk use after cleanup: `artifacts/` about 285 MB; `data/artifacts/` about 25 MB.

## Proposed Work Plan

1. Completed a fresh pre-clean dry-run.
2. Completed explicit execute-mode cleanup.
3. Completed post-clean audit and Git/template verification.
4. Leave the retained paths in place until they age beyond policy or a later reviewed policy changes.

## Validation Plan

Compare pre/execute/post reports, inspect disk usage, list tracked artifacts, and confirm source worktree status is unchanged apart from the active maintenance implementation.

## Risks

- Deleted paths were ignored, local-only, reproducible temporary output and cannot be restored from Git.
- Recent and referenced paths remain and may become eligible in a future retention run.

## Dependencies

- T-578 retention CLI and protection rules.
- User authorization to perform the explicit destructive cleanup.

## Blockers

- None.

## Handoff Checklist

- [x] Cleanup completed
- [x] Post-clean validation completed
- [x] Artifact boundaries recorded
- [x] `tasks/todo.md` status updated

## Evidence

Commands run:

```bash
python3 scripts/local_artifact_retention.py --target all --output /tmp/ai-quant-artifact-cleanup-pre.json
python3 scripts/local_artifact_retention.py --target all --execute --output /tmp/ai-quant-artifact-cleanup-result.json
python3 scripts/local_artifact_retention.py --target all --output /tmp/ai-quant-artifact-cleanup-post.json
du -h -d 1 artifacts
du -h -d 2 data/artifacts
git status --short --branch
git ls-files artifacts
```

Result:

- Passed: pre-clean audit, execute cleanup, post-clean audit, disk inspection, Git template verification.
- Failed: none.
- Not run: code tests, because this task changes only ignored local output and task/handoff documentation.
- `/tmp/ai-quant-artifact-cleanup-pre.json`: retention-tool pre-clean inventory; generated 2026-07-17; local machine; local-only; path/size/mtime metadata; no secrets expected; not acceptable for non-local release gates.
- `/tmp/ai-quant-artifact-cleanup-result.json`: retention-tool deletion record; generated 2026-07-17; local machine; local-only; path/size/mtime metadata; no secrets expected; not acceptable for non-local release gates.
- `/tmp/ai-quant-artifact-cleanup-post.json`: retention-tool post-clean inventory; generated 2026-07-17; local machine; local-only; path/size/mtime metadata; no secrets expected; not acceptable for non-local release gates.

## Next Recommended Action

1. Keep using `make artifact-audit` periodically.
2. Review every future candidate report before passing `--execute`.
3. Do not add destructive retention to automated CI.
