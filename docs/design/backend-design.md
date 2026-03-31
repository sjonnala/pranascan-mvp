# Backend Design

## Backend Role

The backend is the system of record for all persisted application state.
Even when the mobile app performs signal processing locally, the backend still
owns:

- authentication
- consent ledger
- scan session lifecycle
- scan result persistence
- quality enforcement
- trend baselines and alert evaluation
- cooldown logic
- alert delivery stub
- vascular-age heuristic
- anemia-screening heuristic
- audit trail

## Technology Stack

- FastAPI
- SQLAlchemy 2 async
- Alembic
- PostgreSQL in docker and CI
- SQLite in test fixtures
- JWT via `python-jose`

## Backend Directory Map

### App Bootstrap

- `backend/app/main.py`
- `backend/app/config.py`
- `backend/app/database.py`

### Routers

- `backend/app/routers/auth.py`
- `backend/app/routers/consent.py`
- `backend/app/routers/scan.py`
- `backend/app/routers/audit.py`

### Middleware

- `backend/app/middleware/auth.py`
- `backend/app/middleware/audit_log.py`
- `backend/app/middleware/timing.py`

### Services

- `auth_service.py`
- `consent_service.py`
- `quality_gate.py`
- `rppg_processor.py`
- `voice_processor.py`
- `trend_engine.py`
- `delivery_service.py`
- `vascular_age.py`
- `anemia_screen.py`
- `audit_service.py`

### Models And Schemas

- models:
  - `audit.py`
  - `consent.py`
  - `scan.py`
- schemas:
  - `auth.py`
  - `consent.py`
  - `scan.py`
  - `audit.py`

## Application Bootstrap

### Startup

`backend/app/main.py` configures:

- FastAPI app metadata and disclaimer
- CORS
- timing middleware
- audit middleware
- router registration under `/api/v1`
- a startup lifespan hook

### Lifespan Behavior

The default schema-management path is Alembic migrations across environments.

`create_all_tables()` remains available only as an explicit local escape hatch
when `AUTO_CREATE_TABLES=true` is set for a throwaway database.

## Middleware Order

Current middleware layering in `main.py`:

1. `CORSMiddleware`
2. `TimingMiddleware`
3. `audit_log_middleware` via `BaseHTTPMiddleware`

### Timing Middleware

Responsibilities:

- measures request duration
- adds `X-Process-Time-Ms`
- logs slow requests relative to `settings.latency_target_ms`

### Audit Middleware

Responsibilities:

- logs nearly every request/response cycle to `audit_logs`
- skips `/`, `/health`, and `/api/v1/audit/*`
- never blocks the main request if audit persistence fails

Known issue:

- user attribution is incomplete because the request state is not currently
  populated by the auth dependency.

## Router Responsibilities

### `/auth`

File: `backend/app/routers/auth.py`

Endpoints:

- `POST /auth/token`
- `POST /auth/refresh`
- `GET /auth/me`

Purpose:

- create access and refresh tokens
- decode the acting subject

Current model:

- development-style token issuance based on `user_id`
- no password, OTP, or identity proof yet

### `/consent`

File: `backend/app/routers/consent.py`

Endpoints:

- `POST /consent`
- `POST /consent/revoke`
- `POST /consent/deletion-request`
- `GET /consent/status`

Purpose:

- append consent events
- compute current consent state

Important caveat:

- the write routes require auth but currently rely on `body.user_id`
  rather than enforcing a strict match to the authenticated subject

### `/scans`

File: `backend/app/routers/scan.py`

Endpoints:

- `POST /scans/sessions`
- `PUT /scans/sessions/{id}/complete`
- `GET /scans/sessions/{id}`
- `GET /scans/history`

Purpose:

- create scan sessions
- accept final scan payloads
- compute derived backend-only heuristics
- persist results
- provide retrieval and history views

### `/audit`

File: `backend/app/routers/audit.py`

Endpoint:

- `GET /audit/logs`

Purpose:

- read-only access to immutable audit data

## Scan Completion Pipeline

`complete_scan_session()` is the most important backend flow.

### Step 1. Load And Validate Session

- session must exist
- session must belong to authenticated user
- session must still be `initiated`

### Step 2. Optional Server-Side rPPG

If `frame_data` is present:

- backend builds frame samples
- runs `process_frames()`
- overrides incoming HR, HRV, and respiratory rate if extraction succeeds

This path exists for compatibility and fallback.

### Step 3. Optional Server-Side Voice DSP

If `audio_samples` is present:

- backend normalizes samples
- runs `process_audio()`
- may override incoming voice jitter, shimmer, and SNR

This path also exists for compatibility and fallback.

### Step 4. Quality Gate

`run_quality_gate()` rejects the scan if thresholds fail.

If rejected:

- session becomes `rejected`
- no `ScanResult` is written
- response returns `422`

### Step 5. Trend Engine

The trend engine:

- builds prior 7-day metric averages
- requires at least 3 prior values per metric
- evaluates deviation against a 15% threshold
- returns only `consider_lab_followup` or `None`

### Step 6. Cooldown And Delivery

If a trend alert would fire:

- the router checks for recent prior alerts in the cooldown window
- if cooldown is active, the alert is suppressed
- if not suppressed, `deliver_alert()` is called

Current delivery implementation:

- always logs a structured alert event
- optionally POSTs to `settings.alert_webhook_url`
- never blocks the scan if webhook delivery fails

### Step 7. Secondary Heuristics

The router then computes:

- vascular-age estimate from HR and HRV
- anemia-screening wellness label from aggregate RGB means and environment confidence

These values are persisted in `scan_results`.

### Step 8. Persistence

The router creates a `ScanResult`, updates the `ScanSession` to `completed`,
sets `completed_at`, flushes, refreshes, and returns the typed response model.

## Persistence Model

### `consent_records`

Purpose:

- append-only ledger of consent actions

Important fields:

- `user_id`
- `action`
- `consent_version`
- `purpose`
- `created_at`
- `deletion_scheduled_at`
- `deleted_at`

### `scan_sessions`

Purpose:

- lifecycle wrapper around a single scan attempt

Important fields:

- `id`
- `user_id`
- `status`
- `device_model`
- `app_version`
- `created_at`
- `completed_at`

### `scan_results`

Purpose:

- immutable metric snapshot associated to exactly one session

Important fields:

- wellness metrics:
  - `hr_bpm`
  - `hrv_ms`
  - `respiratory_rate`
  - `voice_jitter_pct`
  - `voice_shimmer_pct`
- quality:
  - `quality_score`
  - `lighting_score`
  - `motion_score`
  - `face_confidence`
  - `audio_snr_db`
- workflow and reasoning:
  - `flags`
  - `trend_alert`
- secondary heuristics:
  - `vascular_age_estimate`
  - `vascular_age_confidence`
  - `hb_proxy_score`
  - `anemia_wellness_label`
  - `anemia_confidence`

### `audit_logs`

Purpose:

- append-only operational record of request activity

Important fields:

- `user_id`
- `action`
- `http_method`
- `http_path`
- `http_status`
- `duration_ms`
- `ip_address`
- `user_agent`
- `detail`

## DB Session Pattern

`get_db()` yields an async session and commits automatically after the request
dependency returns successfully.

This means router code usually:

- adds rows
- flushes
- refreshes
- returns

The dependency then commits at the end of the request.

## Test Architecture

### Local Test Pattern

`backend/tests/conftest.py` provides:

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
