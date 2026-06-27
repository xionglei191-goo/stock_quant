# Production Evidence Task Packet: T-407

- Status: blocked_external_evidence
- Owner role: 平台负责人
- Owner group: PM / Release Coordination
- Last updated: 2026-06-27
- Related task: T-407
- Scope: collect real external staging/production evidence for this task
- Non-goals: local-only release approval, generating or fabricating evidence, broker integration, automatic trading

## Objective

Collect and archive the external evidence required to unblock `T-407` for non-local production closure.

## Readiness Endpoint

- `/api/readiness/ui-report`

## External Blockers

- non-local real-volume UI workflow acceptance
- desktop/mobile cross-browser matrix artifact

## Required Artifact Fields

- `browser_acceptance_uri`
- `screenshot_manifest_uri`
- `cross_browser_matrix_uri`
- `real_data_workflow_uri`
- `visual_overflow_review_uri`
- `access_control_review_uri`

## URI Template

- `browser_acceptance_uri`: `s3://<production-evidence-bucket>/<release-id>/T-407/browser_acceptance_uri`
- `screenshot_manifest_uri`: `s3://<production-evidence-bucket>/<release-id>/T-407/screenshot_manifest_uri`
- `cross_browser_matrix_uri`: `s3://<production-evidence-bucket>/<release-id>/T-407/cross_browser_matrix_uri`
- `real_data_workflow_uri`: `s3://<production-evidence-bucket>/<release-id>/T-407/real_data_workflow_uri`
- `visual_overflow_review_uri`: `s3://<production-evidence-bucket>/<release-id>/T-407/visual_overflow_review_uri`
- `access_control_review_uri`: `s3://<production-evidence-bucket>/<release-id>/T-407/access_control_review_uri`

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
