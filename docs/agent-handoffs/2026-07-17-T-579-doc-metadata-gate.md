# Handoff: T-579 Canonical Document Metadata Gate

## Metadata

- Task ID: T-579
- Status: DONE
- Owner group: Platform and Quality
- Reviewer groups: PM / Release Coordination
- Last updated: 2026-07-17
- Last agent: Codex `/root/t579_impl`
- Branch/worktree: shared current worktree

## Status

- Status: DONE
- Owner group: Platform and Quality
- Last updated: 2026-07-17
- Last agent: Codex `/root/t579_impl`
- Branch/worktree: shared current worktree

## Objective

Enforce the T-575 metadata header on the five canonical project documents with a narrow, deterministic local CI gate.

## Scope

- In scope: one structural validator, focused unit tests, and Makefile integration.
- Out of scope: document prose, historical documents, runtime code, and roadmap status.

## Background

T-575 established a common metadata header for the canonical project entry points. Without automated validation, later edits could silently remove ownership, freshness, task, or scope context.

## Problem Statement

Canonical metadata was documented but not enforced. A narrow allowlist is needed so enforcement does not trigger a repository-wide historical-document rewrite.

## Expected Deliverables

- Validate a title and six required metadata fields on five explicitly listed documents.
- Restrict status to the four documented lifecycle values.
- Produce stable human-readable failures and a nonzero exit status.
- Run the check in `make local-ci`.

## Current Findings

- All five allowlisted documents currently use the same H1 followed by metadata-list structure.
- Existing check scripts return an integer from `main` and print a concise pass/fail summary.
- The Makefile already contains the T-578 `artifact-audit` target, which remains unchanged.

## Proposed Work Plan

1. Parse only the leading title and metadata block.
2. Validate the explicit allowlist and controlled status vocabulary.
3. Cover valid, missing-field, and invalid-status behavior with unit tests.
4. Add the validator to local CI.

## Validation Plan

Run the focused unit test, the validator directly, Python compilation, handoff validation, and whitespace validation.

## Risks

- The parser intentionally ignores body prose and documents outside the allowlist.
- Metadata date syntax and task-reference syntax are not validated in this first narrow gate.

## Dependencies

- T-575 canonical document metadata baseline.
- Existing `make local-ci` command ordering.

## Blockers

- None.

## Handoff Checklist

- [x] Validator and focused tests added.
- [x] Local CI integration added without removing artifact retention tooling.
- [x] Canonical documents and roadmap left to their designated owners.
- [x] Parent PM agent updated roadmap status after integration review.

## Evidence

```bash
python3 -m unittest tests.test_doc_metadata -v
python3 scripts/check_doc_metadata.py
python3 -m py_compile scripts/check_doc_metadata.py tests/test_doc_metadata.py
python3 scripts/check_handoffs.py
git diff --check
```

Result:

- Passed: 3 focused unit tests; 5 canonical documents; Python compilation; 153 handoff documents; whitespace validation.
- Failed: none.
- PM integration: `make local-ci` passed on 2026-07-17 with 353 tests plus UI static, security, Markdown, handoff, and canonical metadata gates.

## Next Recommended Action

The parent PM agent should review the allowlist and validation output, then update the T-579 roadmap status as the sole roadmap owner.
