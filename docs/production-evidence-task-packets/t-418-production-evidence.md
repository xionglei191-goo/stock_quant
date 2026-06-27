# Production Evidence Task Packet: T-418

- Status: blocked_external_evidence
- Owner role: NLP/ML 负责人
- Owner group: PM / Release Coordination
- Last updated: 2026-06-27
- Related task: T-418
- Scope: collect real external staging/production evidence for this task
- Non-goals: local-only release approval, generating or fabricating evidence, broker integration, automatic trading

## Objective

Collect and archive the external evidence required to unblock `T-418` for non-local production closure.

## Readiness Endpoint

- `/api/llm/readiness-report`

## External Blockers

- real model quality evaluation
- fallback comparison at scale
- LLM gateway smoke
- budget sync artifact

## Required Artifact Fields

- `real_model_quality_uri`
- `fallback_quality_uri`
- `llm_gateway_smoke_uri`
- `budget_sync_evidence_uri`

## URI Template

- `real_model_quality_uri`: `s3://<production-evidence-bucket>/<release-id>/T-418/real_model_quality_uri`
- `fallback_quality_uri`: `s3://<production-evidence-bucket>/<release-id>/T-418/fallback_quality_uri`
- `llm_gateway_smoke_uri`: `s3://<production-evidence-bucket>/<release-id>/T-418/llm_gateway_smoke_uri`
- `budget_sync_evidence_uri`: `s3://<production-evidence-bucket>/<release-id>/T-418/budget_sync_evidence_uri`

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
