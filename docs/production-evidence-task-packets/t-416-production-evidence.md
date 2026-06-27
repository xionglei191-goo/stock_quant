# Production Evidence Task Packet: T-416

- Status: blocked_external_evidence
- Owner role: 数据工程
- Owner group: Data and Evidence
- Last updated: 2026-06-27
- Related task: T-416
- Scope: collect real external staging/production evidence for this task
- Non-goals: local-only release approval, generating or fabricating evidence, broker integration, automatic trading

## Objective

Collect and archive the external evidence required to unblock `T-416` for non-local production closure.

## Readiness Endpoint

- `/api/connectors/astock/verification-readiness`

## External Blockers

- connector endpoint availability artifacts
- endpoint stability artifacts
- rate-limit/quota verification
- license/TOS reviews
- field sample artifacts for every approved connector

## Required Artifact Fields

- `endpoint_artifact_uri`
- `stability_artifact_uri`
- `rate_limit_artifact_uri`
- `license_review_uri`
- `field_sample_uri`

## URI Template

- `endpoint_artifact_uri`: `s3://<production-evidence-bucket>/<release-id>/T-416/endpoint_artifact_uri`
- `stability_artifact_uri`: `s3://<production-evidence-bucket>/<release-id>/T-416/stability_artifact_uri`
- `rate_limit_artifact_uri`: `s3://<production-evidence-bucket>/<release-id>/T-416/rate_limit_artifact_uri`
- `license_review_uri`: `s3://<production-evidence-bucket>/<release-id>/T-416/license_review_uri`
- `field_sample_uri`: `s3://<production-evidence-bucket>/<release-id>/T-416/field_sample_uri`

## Collection Procedure

- Verify every approved A-stock connector endpoint and record license/TOS owner review.
- Use the approved connector list: baidu_concepts, cninfo_announcements, dragon_tiger_list, eastmoney_research, tencent_valuation_snapshot, ths_hot_topics, unlock_calendar.
- Capture endpoint availability, stability, rate-limit/quota behavior, and field sample artifacts.

## Minimum Artifact Contents

- Endpoint availability and stability artifacts for every approved connector.
- Rate-limit/quota verification and license/TOS review.
- Field sample artifact with connector id, timestamp, and schema version.

## Reviewer Routing

- Governance, Security, and Compliance
- Platform and Quality

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
