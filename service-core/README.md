# Service Core

`service-core` is the new Spring Boot 3.x modular monolith for PranaPulse's
core product capabilities.

## Scope

- `consent`: append-only consent ledger and privacy deletion-request ownership
- `auth`: local user accounts keyed by an external OIDC subject
- `social`: placeholder package for profiles, community, and relationship logic
- `business`: domain logic that stays in the core service, such as retention and
  streak mechanics
- `infrastructure`: cross-cutting concerns such as JWT verification

The existing FastAPI `service-intelligence` module remains the specialized
intelligence service for rPPG and signal-processing workflows during the
migration.

## Initial API Surface

- `GET /api/v1/auth/me`: provision or fetch the local core-user projection from
  the authenticated OIDC JWT
- `POST /api/v1/consent`: grant informed consent for wellness screening
- `POST /api/v1/consent/revoke`: revoke consent for the current user
- `POST /api/v1/consent/deletion-request`: request privacy deletion with a hold period
- `GET /api/v1/consent/status`: current consent/privacy status for the current user
- `GET /api/v1/business/vitality-streak`: fetch the current user's streak state
- `POST /api/v1/business/vitality-streak/check-ins`: register a check-in for the
  current user
- `GET /api/v1/social/connections`: list the current user's social connections
- `POST /api/v1/social/connections`: create a new connection request
- `POST /api/v1/social/connections/{connectionId}/accept`: accept an incoming
  connection request
- `POST /api/v1/social/connections/{connectionId}/decline`: decline an incoming
  connection request
- `POST /api/v1/scans/evaluations`: core-owned scan orchestration entrypoint that
  delegates compute-only analysis to `service-intelligence`
- `POST /api/v1/scans/sessions`: create a core-owned scan session
- `PUT /api/v1/scans/sessions/{sessionId}/complete`: complete a session through
  `service-intelligence`, then persist the result in the core schema
- `GET /api/v1/scans/sessions/{sessionId}`: fetch one core-owned session and its
  persisted result, if present
- `GET /api/v1/scans/history`: fetch paginated core-owned scan history with
  trend deltas
- `POST /api/v1/feedback`: record one post-scan feedback event for a completed
  core-owned scan session
- `GET /api/v1/feedback/sessions/{sessionId}`: fetch feedback already recorded
  for a core-owned session
- `POST /api/v1/reports/generate`: generate and persist a weekly vitality report
- `GET /api/v1/reports/latest`: fetch the latest generated vitality report
- `GET /api/v1/audit/logs`: list the immutable core-owned audit trail
- `HealthResultLifecycleService/EvaluateHealthResult`: gRPC contract for
  evaluating health-result lifecycle state snapshots

## Runtime Baseline

- Java 21
- Maven 3.9+
- PostgreSQL for local/dev/prod
- OIDC-compatible JWT issuer for the resource server
- dedicated `core` schema when sharing PostgreSQL with `service-intelligence`
- gRPC server on port `9090`

## Project-Local Java Selection

`service-core` ships with a lightweight [`mvnw`](/Users/satishjonnala/Documents/Data Team - AIML/github-repos/pranascan-mvp/service-core/mvnw)
launcher that keeps your global `~/.bash_profile` on Java 17, but switches this
module to Java 21 when available.

Usage:

```bash
cd service-core
./mvnw test
```

Behavior:

- sources `~/.bash_profile` to reuse your Maven installation
- prefers JDK 21 for this module
- falls back to another installed JDK 21+ if exact JDK 21 is not present
- leaves your global shell default unchanged

The test resources also pin Mockito to the subclass mock maker so local
`./mvnw test` runs do not depend on inline agent attachment.

## Key Environment Variables

- `CORE_DB_URL`
- `CORE_DB_USERNAME`
- `CORE_DB_PASSWORD`
- `APP_SECURITY_ISSUER_URI`
- `APP_SECURITY_JWK_SET_URI`
- `APP_SECURITY_REQUIRED_AUDIENCE`
- `APP_INTELLIGENCE_INTERNAL_TOKEN`
- `APP_INTELLIGENCE_GRPC_HOST`
- `APP_INTELLIGENCE_GRPC_PORT`

For the root polyglot-monolith compose flow, `service-core` runs against the
shared `pranascan` PostgreSQL database but isolates its tables under the
`core` schema to avoid collisions with `service-intelligence`.

## gRPC Support

`service-core` now includes server-side gRPC support via the grpc-spring
starter and generates stubs from `src/main/proto`.

Current contract:

- `HealthResultLifecycleService`
  - `EvaluateHealthResult`: resolves a sealed Java health-result state machine
    into `PENDING`, `VERIFIED`, or `EXPIRED`
- `ScanIntelligenceService`
  - `EvaluateScan`: compute-only scan evaluation contract covering rPPG, voice
    DSP, quality-gate output, vascular-age, anemia proxy, and `spo2`

`service-core` now consumes `ScanIntelligenceService/EvaluateScan` over gRPC for
the full compute-only scan payload.

## Ownership Migration

Phase 4 of the polyglot-monolith redesign is now in place:

- `service-core` owns the authenticated scan-evaluation API surface
- `service-core` now owns public scan-session creation, completion, and result persistence
- `service-core` now owns consent grants, revocations, privacy deletion requests, and consent gating
- `service-core` now owns scan history, weekly vitality reports, and the immutable audit log
- `service-core` now owns post-scan feedback for completed core sessions
- `service-intelligence` exposes internal compute-only gRPC contracts for
  `EvaluateScan`
- `service-intelligence` now runs as an internal compute-only service in the
  default runtime
