# Backend Design

## Backend Role

The repo now uses a split backend with clear ownership:

- `service-core` is the public backend and system of record.
- `service-intelligence` is an internal compute service behind gRPC.

`service-core` owns:

- OIDC/JWT verification and authenticated user projection
- consent/privacy workflows
- scan session lifecycle and result persistence
- trend history, reporting, feedback, and audit

`service-intelligence` owns:

- rPPG and voice-derived compute helpers
- quality gating
- vascular-age and anemia heuristics
- the internal `ScanIntelligenceService/EvaluateScan` contract
- operational HTTP health/root endpoints plus lightweight audit logging

## Technology Stack

- `service-core`: Spring Boot 3.x, Java 21, Spring Security, Spring Data JPA, Flyway
- `service-intelligence`: FastAPI, SQLAlchemy 2 async, Alembic, gRPC Python
- Shared PostgreSQL with isolated schemas during migration
- OIDC for mobile-to-core auth
- gRPC for core-to-intelligence compute calls

## Directory Map

### Service Core

- `service-core/src/main/java/com/pranapulse/core/auth`
- `service-core/src/main/java/com/pranapulse/core/consent`
- `service-core/src/main/java/com/pranapulse/core/scan`
- `service-core/src/main/java/com/pranapulse/core/report`
- `service-core/src/main/java/com/pranapulse/core/audit`
- `service-core/src/main/java/com/pranapulse/core/infrastructure/intelligence`

### Service Intelligence

- `service-intelligence/app/main.py`
- `service-intelligence/app/grpc_runtime.py`
- `service-intelligence/app/config.py`
- `service-intelligence/app/database.py`
- `service-intelligence/app/middleware/audit_log.py`
- `service-intelligence/app/services/quality_gate.py`
- `service-intelligence/app/services/rppg_processor.py`
- `service-intelligence/app/services/voice_processor.py`
- `service-intelligence/app/services/vitals_extraction.py`
- `service-intelligence/app/services/vascular_age.py`
- `service-intelligence/app/services/anemia_screen.py`
- `service-intelligence/app/services/scan_evaluation_service.py`

## Runtime Bootstrap

### Service Core

`service-core` starts the public REST API, validates JWTs from the configured
OIDC issuer, applies Flyway migrations for the `core` schema, and calls
`service-intelligence` over gRPC for scan evaluation.

### Service Intelligence

`service-intelligence/app/main.py` starts a small FastAPI app with:

- `/`
- `/health`
- audit logging middleware
- a lifespan hook that can auto-create tables only for throwaway local setups
- a background gRPC server serving `ScanIntelligenceService`

The FastAPI runtime no longer mounts public auth, consent, scan, report, or
feedback routers.

## Data Ownership

Persisted product truth belongs in `service-core`:

- users
- consent ledger
- scan sessions and scan results
- social graph and streaks
- feedback
- reports
- audit records

`service-intelligence` persistence is now limited to operational concerns such
as its HTTP audit middleware and any future compute-side technical metadata.

## Extension Points

Add new product-facing features to `service-core` when they require:

- authenticated mobile access
- new tables in the core domain
- user-visible reporting or history
- policy or consent checks

Add new compute features to `service-intelligence` when they are:

- pure signal-processing or scoring logic
- model-serving or heuristic steps
- internal-only helpers for `EvaluateScan`

## Notes For Contributors

- If you are looking for public product APIs, start in `service-core`, not in
  `service-intelligence`.
- If you need to change scan compute behavior, follow the `EvaluateScan`
  request/response contract first and then update the matching core gateway.
- The remaining FastAPI database objects are no longer the source of truth for
  users, consent, scan history, reports, or feedback.

### Local Test Pattern

`service-intelligence/tests/conftest.py` provides:

- in-memory SQLite database
- per-test schema creation and teardown
- `httpx.AsyncClient` against the FastAPI app
- JWT auth headers for two test users

### CI Test Pattern

GitHub Actions runs backend tests against PostgreSQL, not SQLite.

That is important because:

- local unit and API tests are fast
- CI is closer to production persistence behavior

## Extension Points

### Add A New Backend Metric

Typical path:

1. extend `ScanResult` model
2. create Alembic migration
3. extend `ScanResultSubmit` or `ScanResultResponse`
4. compute the value in a service or router
5. persist it in `ScanResult`
6. add unit tests and router integration tests
7. expose it to mobile types and UI if user-visible

### Add A New Router

Typical path:

1. define schema models
2. implement service layer first
3. add router file
4. include router in `app.main`
5. add auth or no-auth policy explicitly
6. add tests

### Add Background Or External Delivery

Current alert delivery is synchronous and intentionally lightweight.

If you need production-grade messaging:

- keep `deliver_alert()` non-blocking
- move external delivery to a queue or job worker
- preserve the non-diagnostic copy contract

## Known Backend Gotchas

- Audit user attribution is incomplete because `request.state.user_id` is not set.
- Consent write routes do not currently bind the body `user_id` to the auth subject.
- The scan router currently mixes orchestration and domain logic; future refactors
  may want a dedicated scan orchestration service.
- Tests use SQLite locally but PostgreSQL in CI.
- The backend still supports legacy processing inputs even though the current
  mobile flow is mostly edge-first.
