# Handoff: T-463 Company Profile Assertion Conflict Review

## Metadata

- Status: DONE
- Owner group: Data and Evidence
- Reviewer groups: Product and UI, Platform and Quality
- Last updated: 2026-06-25
- Last agent: Codex
- Branch/worktree: local workspace, main
- Related task: T-463

## Status

- Status: DONE
- Owner group: Data and Evidence
- Reviewer groups: Product and UI, Platform and Quality
- Last updated: 2026-06-25
- Last agent: Codex
- Branch/worktree: main / `/home/xionglei/Project/sotck_quant`

## Objective

Add conservative conflict handling for company profile field assertions so new official/IR field evidence cannot overwrite existing company profile facts until reviewed.

## Background

T-460 added field-level company profile assertions, and T-461 added a local official/IR material inbox. Those capabilities let the system store field-specific evidence, but replacement behavior was still too aggressive for a long-lived company database: a newer official/IR extraction could overwrite an existing profile field without first recording the disagreement.

## Problem Statement

The company database needs to preserve factual provenance across time. If two governed sources provide different values for the same company profile field, the platform should not silently overwrite the current profile. It should store the new value as a reviewable conflict candidate, keep the old active value until a human or reviewed workflow approves the replacement, and leave an audit trail that explains which assertion superseded which.

## Expected Deliverables

- Extend `CompanyProfileFieldAssertion` with conflict and resolution metadata.
- Detect conflicting field assertions during official/IR profile field extraction.
- Keep conflict candidates out of active `Issuer` / `CompanyProfile` facts until review approval.
- Add a review API for approve, supersede and reject actions.
- Expose assertion status counters for review queues and future UI.
- Update API/data-structure docs, roadmap and handoff records.
- Cover the behavior with focused regression tests and default local checks.

## Scope

- In scope: profile field assertion model fields, extraction conflict detection, review API, docs, roadmap, focused regression test.
- Out of scope: UI review queue, batch review operations, external data downloads, real broker or live trading integrations.

## Current Findings

- `CompanyProfileFieldAssertion` already had `supersedes`, `review_status` and `assertion_status`, so conflict handling could extend the existing object instead of adding a new table.
- `extract_company_profile_fields` already gates sources to official/IR/company/governed records, preserving the boundary that research reports cannot become fact assertions.
- The initial implementation needed one safety fix: conflict candidates must not merge their source/evidence into active company profiles before approval.
- Persistence needed to account for assertion-only writes, because a conflict candidate can be recorded without updating any profile field.

## Proposed Work Plan

1. Add conflict metadata to field assertions.
2. Detect active assertion value conflicts before applying field candidates.
3. Store conflicting candidates with `conflict_candidate` / `needs_review`.
4. Add review API routes and service method.
5. Apply approved values and supersede old assertions only after review.
6. Update docs, roadmap and handoff.
7. Run focused and default validation.

## Validation Plan

- Run Python compile for app, tests and scripts.
- Run focused regression for field assertion conflicts.
- Run full unittest suite.
- Run UI static check to ensure static contracts still pass.
- Run security check.
- Run handoff validation.
- Run `git diff --check` before commit.

## Current State

- Completed: conflicting field extraction creates `conflict_candidate` / `needs_review` assertions without mutating active company profile fields.
- Completed: review API supports `approve`, `supersede`, and `reject`.
- Completed: approving a conflict applies the new field value and marks old assertions `superseded`.
- Completed: assertion query returns status counters and conflict/superseded counts.
- Blocked: none.

## Dependencies

- T-456 company profile deep-field coverage audit.
- T-457 official/IR profile field extraction.
- T-460 company profile field assertions.
- T-461 local company material inbox.
- T-462 company intelligence completeness verdict.

## Blockers

- None.

## Files Touched

- `app/models.py`: added `conflicts_with` and `resolved_by` to `CompanyProfileFieldAssertion`.
- `app/services.py`: added assertion conflict detection, review action, safe assertion persistence, and status counters.
- `app/api.py`: added review routes under `company-profiles` and `company-database` aliases.
- `tests/test_system.py`: added regression coverage for conflict candidate, approval, superseded assertion and coverage audit behavior.
- `tasks/todo.md`: added T-463 completion entry.
- `docs/api-contracts.md`: documented review endpoint, conflict semantics and new response counters.
- `docs/data-structure-design.md`: documented assertion conflict and resolution fields.
- `docs/README.md`: updated document index for T-463.
- `docs/agent-handoffs/README.md`: added T-463 to related tasks.

## Commands Run

```bash
python3 -m py_compile app/*.py tests/*.py scripts/*.py
python3 -m unittest tests.test_system.SystemServiceTests.test_company_profile_field_assertion_conflict_requires_review_before_replacement
python3 -m unittest discover -s tests
python3 scripts/ui_static_check.py
python3 scripts/security_check.py .
```

Result:

- Passed: py_compile completed with no output.
- Passed: focused conflict review regression, 1 test.
- Passed: full unittest suite, 245 tests.
- Passed: UI static check.
- Passed: security check, 179 files checked, no findings.

## Evidence

Commands run:

```bash
python3 -m py_compile app/*.py tests/*.py scripts/*.py
python3 -m unittest tests.test_system.SystemServiceTests.test_company_profile_field_assertion_conflict_requires_review_before_replacement
python3 -m unittest discover -s tests
python3 scripts/ui_static_check.py
python3 scripts/security_check.py .
```

Result:

- Passed: Python compile.
- Passed: focused conflict review regression.
- Passed: full unittest suite, 245 tests.
- Passed: UI static check.
- Passed: security check.

## Decisions

- Conflict candidates are stored as provenance records but do not update `Issuer` or `CompanyProfile` until review approval.
- Any recorded assertion, including a conflict candidate with no profile update, now triggers dirty marking and store commit.
- Research reports remain opinion/attention sources only and cannot generate profile fact assertions.

## Risks and Open Questions

- No UI queue exists yet for reviewing `conflict_candidate` assertions; reviewers must call the API directly for now.
- Field-level source priority rules remain simple; future work can add deterministic priority scoring by source type and freshness.

## Artifacts

- None. This task changed code, tests and docs only.

## Handoff Checklist

- [x] Model fields added.
- [x] Extraction conflict detection added.
- [x] Conflict candidates kept out of active profile facts before approval.
- [x] Review API added.
- [x] Focused regression test added.
- [x] API/data-structure docs updated.
- [x] Roadmap updated.
- [x] Handoff created.

## Acceptance Checklist

- [x] Code changes completed
- [x] Tests/checks run or explicitly skipped with reason
- [x] Docs/contracts updated if applicable
- [x] `tasks/todo.md` status updated if roadmap state changed

## Next Steps

1. Add a company workbench review queue for `conflict_candidate` assertions.
2. Add batch approve/reject support after a visible review queue exists.
3. Add configurable source priority and freshness rules for field replacement suggestions.

## Next Recommended Action

Add a visible company workbench queue for `conflict_candidate` assertions so analysts can approve or reject field replacements without calling the API manually.
