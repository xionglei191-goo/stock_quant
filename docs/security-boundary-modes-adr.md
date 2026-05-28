# Security Boundary Modes ADR

- Status: active
- Owner group: Governance, Security, and Compliance
- Last updated: 2026-05-28
- Related tasks: T-428
- Scope: local/staging/non-local production access control baseline
- Non-goals: broker integration, live execution enablement

## Context

Current local workflow uses `X-Role` request headers for low-friction single-machine operation. This is acceptable for local tooling but insufficient for non-local deployments.

## Decision

Introduce explicit deployment mode and auth mode boundaries:

1. Local mode (`AI_QUANT_DEPLOYMENT_MODE=local`): allow `X-Role` header workflow.
2. Non-local modes (`staging`/`preprod`/`production`): reject startup when auth mode remains header-based.
3. Production-safe auth modes (planned rollout): `service-token`, `jwt`, `oidc`.

Implemented guard:

- `app/server.py` validates startup mode.
- If deployment mode is non-local and `AI_QUANT_AUTH_MODE` is `x-role-header`/`header`/`none`, startup fails fast.

## Role/Auth Mapping Plan

1. Map service identity -> internal role set.
2. Derive effective role from verified token claims, not request header.
3. Persist auth subject, auth mode, and policy decision in audit payload.

## Pre-Release Checks For Non-Local Deployments

1. Auth mode is token/JWT/OIDC, not header-only.
2. Permission matrix exported and reviewed.
3. Red-team replay includes privilege escalation attempts and 403/audit validation.
4. Secret rotation metadata present and no secret literal persistence.

## Red-Team Script Task Split

1. Token spoof and missing-signature rejection tests.
2. Cross-role access matrix replay (allowed/denied baseline).
3. Audit completeness checks (subject, role, resource, action, decision, trace).
4. Incident notification route validation for repeated denied access.
