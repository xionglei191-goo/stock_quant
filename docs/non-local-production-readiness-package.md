# Non-Local Production Readiness Package

- Status: active
- Owner group: Governance, Security, and Compliance
- Last updated: 2026-06-27
- Related tasks: T-499
- Scope: non-local staging/production readiness plan, evidence template, and boundary matrix
- Non-goals: real broker integration, automatic trading, schema migration, or replacing local personal operation

## Purpose

This package defines the gap between local personal use and a non-local organizational release. The system remains local-first and paper-only. Non-local release can only proceed after authentication, secrets, storage, search, audit, monitoring, backup, and release evidence are proven with external staging or production artifacts.

Local-only artifacts, screenshots, logs, `artifact://local-*`, `artifact://staging-local`, `file://`, `local://`, and localhost URLs are useful development evidence, but they are not production release evidence.

## Boundary Decision

Facts:

- Local personal mode may keep the low-friction `X-Role` workflow.
- Non-local staging, preproduction, and production must not run with header-only or unauthenticated access.
- Portfolio and feedback flows remain paper-only.
- The system does not connect to real brokers and does not place orders.
- Readiness scripts may exercise simulated orders only.

Decision:

- `local` mode is optimized for personal research and local operations.
- `staging` and `production` require token/JWT/OIDC-style identity, reviewed permission matrix, external artifact storage, immutable audit evidence, and release gate validation.
- Production sign-off consumes evidence; it must not generate or infer missing evidence from local files.

## Deployment Mode Matrix

| Area | Local personal | Non-local staging | Production |
| --- | --- | --- | --- |
| Auth | `X-Role` allowed | token/JWT/OIDC required | token/JWT/OIDC required |
| Permissions | role header plus local audit | exported permission matrix and red-team replay | signed approval of matrix and replay evidence |
| Secrets | local env allowed, no committed secrets | secret manager or metadata-only rotation proof | managed secret store, rotation evidence, access audit |
| State store | SQLite or local PostgreSQL | external PostgreSQL with backup drill | production PostgreSQL with backup/restore evidence |
| Object store | local filesystem or MinIO | external archive/object store | immutable/object-lock evidence archive |
| Search/vector/graph | local backend acceptable | external OpenSearch/Qdrant/Neo4j readiness | monitored external services with recovery evidence |
| Trace/audit | local trace IDs and audit logs | trace subject, role, action, decision, resource | retained audit stream with incident workflow |
| Monitoring | optional local health checks | OTel/log/metric alert drill | SLO dashboards, alert routing, incident record |
| Evidence URI | local-only accepted for personal use | external staging artifact URI required | production or approved release archive URI required |
| Trading boundary | paper-only | paper-only | paper-only |

## Required Evidence Template

Each non-local release candidate needs a filled evidence package with the following fields. Every URI must be a concrete external artifact URI and must point to an immutable object or an archived report.

| Evidence field | Owner group | Required proof | Accepted URI examples | Rejected examples |
| --- | --- | --- | --- | --- |
| `auth_mode_review` | Governance, Security, and Compliance | non-header auth mode, role mapping, denied startup proof for unsafe mode | `s3://.../T-499/auth-mode-review.json` | `artifact://local-auth.json` |
| `permission_red_team` | Governance, Security, and Compliance | allowed/denied role replay, 403 and audit evidence | `s3://.../T-499/permission-red-team.json` | `http://127.0.0.1:8000/ui` |
| `secret_governance` | Governance, Security, and Compliance | secret manager reference, rotation metadata, no secret literal persistence | `s3://.../T-499/secret-governance.json` | `.env` |
| `backup_restore_drill` | Platform and Quality | restore drill report, RPO/RTO, checksum evidence | `s3://.../T-499/backup-restore.json` | `artifacts/local-production-audit.json` |
| `source_authorization_audit` | Data and Evidence | source rights review, restricted content exclusion, frozen connector list | `s3://.../T-499/source-authorization.json` | `artifact://demo/source.json` |
| `artifact_inventory` | PM / Release Coordination | sha256, size, environment, producer, owner, retention, immutability | `s3://.../T-499/artifact-inventory.json` | `file:///tmp/inventory.json` |
| `monitoring_alert_drill` | Platform and Quality | OTel/log/metric alert and incident workflow evidence | `s3://.../T-499/monitoring-alert.json` | `artifact://staging-local/otel.json` |
| `release_gate_result` | PM / Release Coordination | filled plan, readiness package, manifest check, release gate output | `s3://.../T-499/release-gate.json` | `artifact://local-release-gate.json` |
| `paper_only_boundary_review` | Research and AI Workflows | no-broker/no-auto-trading/paper-only evidence and test result | `s3://.../T-499/paper-boundary.json` | broker account screenshots |

## API And Backend Boundary Checklist

Before non-local release:

1. `AI_QUANT_DEPLOYMENT_MODE` is `staging`, `preprod`, or `production`.
2. `AI_QUANT_AUTH_MODE` is not `x-role-header`, `header`, or `none`.
3. Every sensitive API action records subject, role, resource, action, decision, and trace ID.
4. Object store, search backend, graph/vector backend, and state store are explicitly configured for the target mode.
5. Local fallback backends are disabled or documented as non-release blockers.
6. Release evidence package includes the exact API base URL and artifact inventory.
7. Simulated feedback and portfolio paths keep `paper_only=true` and do not call broker endpoints.

## Release Gate Sequence

1. Generate or update the external evidence collection plan.
2. Fill all artifact URI templates with concrete external archive URIs.
3. Validate the filled plan with `--require-filled-uris`.
4. Validate readiness evidence package and artifact inventory.
5. Generate the production closure manifest from the filled plan.
6. Run the release gate.
7. Only after the release gate passes, produce approval notes and update release task status.

Recommended commands:

```bash
python3 scripts/production_evidence_plan_check.py artifacts/production-evidence-collection-plan.json --require-filled-uris
python3 scripts/readiness_evidence_package_check.py artifacts/readiness-evidence-package.json --output artifacts/readiness-evidence-package-validation.json
python3 scripts/production_artifact_inventory_check.py artifacts/production-artifact-inventory.json --plan artifacts/production-evidence-collection-plan.json --evidence-package artifacts/readiness-evidence-package.json --manifest artifacts/production-closure-manifest.json
python3 scripts/production_release_gate.py --plan artifacts/production-evidence-collection-plan.json --evidence-package artifacts/readiness-evidence-package.json --artifact-inventory artifacts/production-artifact-inventory.json --artifact-bundle-root artifacts/production-evidence-bundle --manifest-output artifacts/production-closure-manifest.json
```

## Open Work After T-499

- Replace template evidence with real external staging or production artifacts when a non-local deployment exists.
- Wire the readiness package into organization approval workflow.
- Decide whether staging and production require separate artifact buckets and KMS keys.
- Add live incident drills only after the target deployment environment exists.
