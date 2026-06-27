# Production Evidence Task Packet: T-408

- Status: blocked_external_evidence
- Owner role: CIO
- Owner group: Research and AI Workflows / Portfolio
- Last updated: 2026-06-27
- Related task: T-408
- Scope: collect real external staging/production evidence for this task
- Non-goals: local-only release approval, generating or fabricating evidence, broker integration, automatic trading

## Objective

Collect and archive the external evidence required to unblock `T-408` for non-local production closure.

## Readiness Endpoint

- `/api/portfolio/attribution/readiness-report`

## External Blockers

- performance reconciliation
- NAV/ledger reconciliation
- board pack artifact
- large replay acceptance

## Required Artifact Fields

- `performance_reconciliation_uri`
- `ledger_extract_uri`
- `board_pack_uri`
- `strategy_replay_uri`

## URI Template

- `performance_reconciliation_uri`: `s3://<production-evidence-bucket>/<release-id>/T-408/performance_reconciliation_uri`
- `ledger_extract_uri`: `s3://<production-evidence-bucket>/<release-id>/T-408/ledger_extract_uri`
- `board_pack_uri`: `s3://<production-evidence-bucket>/<release-id>/T-408/board_pack_uri`
- `strategy_replay_uri`: `s3://<production-evidence-bucket>/<release-id>/T-408/strategy_replay_uri`

## Collection Procedure

- Reconcile simulated portfolio performance against NAV/ledger extracts using paper-only data.
- Generate the board pack and replay evidence from the same immutable ledger snapshot.
- Confirm the packet contains no broker connection, order placement, or live execution artifact.

## Minimum Artifact Contents

- Performance and NAV/ledger reconciliation with variance explanation.
- Board pack artifact and strategy replay acceptance.
- Paper-only boundary statement and reviewer sign-off.

## Reviewer Routing

- Governance, Security, and Compliance

## Source And Boundary Rules

- Evidence must come from the declared external staging/production environment.
- Preserve local-first and paper-only boundaries; do not include broker credentials, live order execution, or automatic trading evidence.
- Redact secrets, tokens, signed URLs, private keys, and personal credentials before archiving.
- Restricted or boundary-unclear research content may be metadata/manual-reference evidence only, not training data or automated fact evidence.

## Acceptance

- Every URI is a concrete external staging/production archive URI.
- No URI is local-only, demo, localhost, `file://`, `local://`, or `artifact://staging-local`.
- Artifact inventory records sha256, size, environment, producer, owner, retention, and immutable/object-lock metadata.
- The filled evidence plan passes `scripts/production_evidence_plan_check.py --require-filled-uris`.
- The strict release gate passes before any task status is changed to DONE.

## Commands

```bash
python3 scripts/production_evidence_plan_check.py artifacts/production-evidence-collection-plan.json --require-filled-uris
python3 scripts/production_artifact_inventory_check.py artifacts/production-artifact-inventory.json --plan artifacts/production-evidence-collection-plan.json --evidence-package artifacts/readiness-evidence-package.json --manifest artifacts/production-closure-manifest.json
python3 scripts/production_release_gate.py --plan artifacts/production-evidence-collection-plan.json --evidence-package artifacts/readiness-evidence-package.json --artifact-inventory artifacts/production-artifact-inventory.json --artifact-bundle-root artifacts/production-evidence-bundle --manifest-output artifacts/production-closure-manifest.json
```
