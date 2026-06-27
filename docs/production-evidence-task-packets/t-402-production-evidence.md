# Production Evidence Task Packet: T-402

- Status: blocked_external_evidence
- Owner role: NLP/ML 负责人
- Owner group: PM / Release Coordination
- Last updated: 2026-06-27
- Related task: T-402
- Scope: collect real external staging/production evidence for this task
- Non-goals: local-only release approval, generating or fabricating evidence, broker integration, automatic trading

## Objective

Collect and archive the external evidence required to unblock `T-402` for non-local production closure.

## Readiness Endpoint

- `/api/benchmarks/{benchmark_id}/readiness-report`

## External Blockers

- 300-500 real CN filing/report samples
- English SEC sample set
- human annotation manual
- OCR bbox/table cell gold labels
- summary quality samples
- regression baseline report

## Required Artifact Fields

- `sample_manifest_uri`
- `chinese_sample_set_uri`
- `english_sample_set_uri`
- `annotation_manual_uri`
- `bbox_gold_uri`
- `table_cell_gold_uri`
- `summary_quality_uri`
- `regression_baseline_uri`

## URI Template

- `sample_manifest_uri`: `s3://<production-evidence-bucket>/<release-id>/T-402/sample_manifest_uri`
- `chinese_sample_set_uri`: `s3://<production-evidence-bucket>/<release-id>/T-402/chinese_sample_set_uri`
- `english_sample_set_uri`: `s3://<production-evidence-bucket>/<release-id>/T-402/english_sample_set_uri`
- `annotation_manual_uri`: `s3://<production-evidence-bucket>/<release-id>/T-402/annotation_manual_uri`
- `bbox_gold_uri`: `s3://<production-evidence-bucket>/<release-id>/T-402/bbox_gold_uri`
- `table_cell_gold_uri`: `s3://<production-evidence-bucket>/<release-id>/T-402/table_cell_gold_uri`
- `summary_quality_uri`: `s3://<production-evidence-bucket>/<release-id>/T-402/summary_quality_uri`
- `regression_baseline_uri`: `s3://<production-evidence-bucket>/<release-id>/T-402/regression_baseline_uri`

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
