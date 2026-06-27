# Production Evidence Task Packet: T-421

- Status: blocked_external_evidence
- Owner role: 风险/合规
- Owner group: PM / Release Coordination
- Last updated: 2026-06-27
- Related task: T-421
- Scope: collect real external staging/production evidence for this task
- Non-goals: local-only release approval, generating or fabricating evidence, broker integration, automatic trading

## Objective

Collect and archive the external evidence required to unblock `T-421` for non-local production closure.

## Readiness Endpoint

- `/api/governance/security-readiness-report`

## External Blockers

- external KMS/secret manager evidence
- external API key least privilege review
- object store/search external delete executor evidence

## Required Artifact Fields

- `secret_manager_evidence_uri`
- `least_privilege_policy_uri`
- `external_delete_evidence_uri`
- `permission_review_uri`

## URI Template

- `secret_manager_evidence_uri`: `s3://<production-evidence-bucket>/<release-id>/T-421/secret_manager_evidence_uri`
- `least_privilege_policy_uri`: `s3://<production-evidence-bucket>/<release-id>/T-421/least_privilege_policy_uri`
- `external_delete_evidence_uri`: `s3://<production-evidence-bucket>/<release-id>/T-421/external_delete_evidence_uri`
- `permission_review_uri`: `s3://<production-evidence-bucket>/<release-id>/T-421/permission_review_uri`

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
