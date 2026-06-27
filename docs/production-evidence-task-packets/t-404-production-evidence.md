# Production Evidence Task Packet: T-404

- Status: blocked_external_evidence
- Owner role: 平台负责人
- Owner group: PM / Release Coordination
- Last updated: 2026-06-27
- Related task: T-404
- Scope: collect real external staging/production evidence for this task
- Non-goals: local-only release approval, generating or fabricating evidence, broker integration, automatic trading

## Objective

Collect and archive the external evidence required to unblock `T-404` for non-local production closure.

## Readiness Endpoint

- `/api/governance/storage-readiness-report`

## External Blockers

- PostgreSQL/S3/OpenSearch real environment smoke
- capacity and latency baseline
- backup restore drill

## Required Artifact Fields

- `postgres_smoke_uri`
- `s3_smoke_uri`
- `opensearch_smoke_uri`
- `capacity_baseline_uri`
- `backup_restore_uri`
- `least_privilege_policy_uri`

## URI Template

- `postgres_smoke_uri`: `s3://<production-evidence-bucket>/<release-id>/T-404/postgres_smoke_uri`
- `s3_smoke_uri`: `s3://<production-evidence-bucket>/<release-id>/T-404/s3_smoke_uri`
- `opensearch_smoke_uri`: `s3://<production-evidence-bucket>/<release-id>/T-404/opensearch_smoke_uri`
- `capacity_baseline_uri`: `s3://<production-evidence-bucket>/<release-id>/T-404/capacity_baseline_uri`
- `backup_restore_uri`: `s3://<production-evidence-bucket>/<release-id>/T-404/backup_restore_uri`
- `least_privilege_policy_uri`: `s3://<production-evidence-bucket>/<release-id>/T-404/least_privilege_policy_uri`

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
