# Polyglot Monolith Ownership Migration

## Target Boundary

`service-core` should own:

- user identity and auth
- consent and deletion requests
- social graph and streaks
- public mobile-facing scan orchestration
- persistence for scan sessions, scan results, reports, and notifications

`service-intelligence` should own:

- rPPG computation
- voice DSP
- quality-gate evaluation
- derived wellness heuristics such as vascular-age and anemia proxies

## Sequential Migration Plan

### Phase 1

- `service-core` exposes `POST /api/v1/scans/evaluations`
- `service-intelligence` exposes a compute-only contract for `service-core`
- the internal contract does not persist user-facing state

### Phase 2

- move public scan-session creation and completion into `service-core`
- keep `service-intelligence` as an internal compute dependency only

### Phase 3

- move consent and privacy workflows fully into `service-core`
- deprecate legacy FastAPI auth and consent routes

### Phase 4

- move trend/report generation and delivery orchestration into `service-core`
- shrink `service-intelligence` persistence to technical metadata only, or remove it entirely

## Current State After Phase 4

- `service-core` owns scan evaluation, scan-session creation, completion, and session lookup
- `service-core` persists scan sessions and scan results in the `core` schema
- `service-core` owns consent grants, revocations, deletion requests, and consent gating for scan creation
- `service-core` owns scan history, trend deltas, vitality report generation, latest-report retrieval, and immutable audit logs
- `service-core` owns post-scan feedback for completed core-owned scan sessions
- `service-intelligence` exposes compute-only gRPC contracts for `service-core`
- `service-core` now consumes `ScanIntelligenceService/EvaluateScan` over gRPC
  for the full scan-evaluation payload
- `mobile` now performs real in-app OIDC login against the same issuer trusted by `service-core`
- the default `service-intelligence` runtime is internal compute only; mobile/public traffic no longer depends on FastAPI compatibility routes
- both services still share PostgreSQL, but their business ownership is now more explicit than before
