# Production Evidence Task Packet: T-406

- Status: blocked_external_evidence
- Owner role: 数据工程
- Owner group: PM / Release Coordination
- Last updated: 2026-06-27
- Related task: T-406
- Scope: collect real external staging/production evidence for this task
- Non-goals: local-only release approval, generating or fabricating evidence, broker integration, automatic trading

## Objective

Collect and archive the external evidence required to unblock `T-406` for non-local production closure.

## Readiness Endpoint

- `/api/entity-mappings/readiness-report`

## External Blockers

- ADR/Chinese ADR real batch mapping evidence
- entity page browser acceptance
- Neo4j external sync evidence
- Qdrant external sync evidence

## Required Artifact Fields

- `batch_mapping_artifact_uri`
- `entity_page_acceptance_uri`
- `neo4j_sync_artifact_uri`
- `qdrant_sync_artifact_uri`

## URI Template

- `batch_mapping_artifact_uri`: `s3://<production-evidence-bucket>/<release-id>/T-406/batch_mapping_artifact_uri`
- `entity_page_acceptance_uri`: `s3://<production-evidence-bucket>/<release-id>/T-406/entity_page_acceptance_uri`
- `neo4j_sync_artifact_uri`: `s3://<production-evidence-bucket>/<release-id>/T-406/neo4j_sync_artifact_uri`
- `qdrant_sync_artifact_uri`: `s3://<production-evidence-bucket>/<release-id>/T-406/qdrant_sync_artifact_uri`

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
