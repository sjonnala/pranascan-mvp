# Architectural & Tech Stack Review — PranaScan MVP

**Date:** 2026-04-06
**Scope:** Full architecture and tech stack critical review
**Auditor:** Principal Engineer (AI-assisted)

---

## Executive Summary

PranaScan is a privacy-first health wellness screening application. The architecture is a **polyglot, multi-service system** composed of a Spring Boot Java service, a Python FastAPI compute service, a React Native mobile app, and Keycloak for identity. Inter-service communication between the two backend services is gRPC. The codebase is at a mature MVP stage with real-world production concerns already addressed (audit trails, consent management, schema migrations, skin-tone calibration). Several meaningful concerns exist and are detailed below.

---

## Tech Stack

### Languages
- **Java 21** — `service-core` (Spring Boot 3.3.5)
- **Python 3.11** — `service-intelligence` (FastAPI), `agent/`, `scripts/`
- **TypeScript / React Native** — `mobile/` (Expo 54, React 19.1)

### Frameworks and Libraries

**service-core (Java)**
- Spring Boot 3.3.5 (`web`, `data-jpa`, `security`, `oauth2-resource-server`, `actuator`, `validation`)
- Flyway 9.x (schema migrations)
- Hibernate / JPA (ORM)
- grpc-server-spring-boot-starter 3.1.0 / gRPC 1.63.0
- protobuf 3.23.4
- PostgreSQL JDBC driver; H2 for tests
- Spring Security (JWT/OAuth2 resource server)
- JUnit 5, Mockito, MockMvc

**service-intelligence (Python)**
- FastAPI 0.111.0 + Uvicorn 0.29.0
- SQLAlchemy 2.0.30 async + asyncpg 0.29.0
- Alembic 1.13.1 (migrations)
- Pydantic v2 / pydantic-settings
- grpcio 1.63.0 + protobuf 5.26.1
- NumPy ≥ 1.26, SciPy ≥ 1.12 (DSP algorithms)
- aiosqlite 0.20.0 (SQLite test support)
- Pytest + pytest-asyncio, pytest-cov, ruff, black

**mobile (TypeScript)**
- Expo 54 + Expo Router 6
- React 19.1 / React Native 0.81.5
- expo-auth-session 7 (OIDC/PKCE)
- expo-secure-store (token persistence)
- react-native-vision-camera 4.7.3
- react-native-worklets-core 1.6.3 (camera frame worklets)
- expo-av 16 (audio)
- Axios 1.7 (HTTP client)
- Jest / jest-expo, @testing-library/react-native

### Infrastructure
- Docker Compose (local dev orchestration)
- Keycloak 26.1 (identity provider)
- PostgreSQL 16-alpine

---

## Services

| Service | Language | Role |
|---------|----------|------|
| `service-core` | Java 21 / Spring Boot | Product-facing REST API. Manages users, consent, scan sessions, scan results, streak, reports, feedback, social connections. Calls `service-intelligence` for compute. |
| `service-intelligence` | Python 3.11 / FastAPI | Internal compute engine. Exposes a gRPC endpoint consumed only by `service-core`. Runs rPPG, voice DSP, quality gate, vascular age, anemia screen, skin-tone calibration. |
| `Keycloak` | External (container) | OIDC IdP. Issues JWTs for the mobile client. `service-core` validates JWTs as an OAuth2 resource server. |
| `db` | PostgreSQL 16 | Single database. `service-core` uses the `core` schema (Flyway). `service-intelligence` has its own Alembic migration chain on the same instance. |
| `agent` | Python CLI | Background job agent. Runs the `run_agent_cycle` function. Generates weekly vitality reports, sends Telegram alerts. Designed to run as cron. |
| `backend/` | Python / FastAPI | **Appears to be a legacy precursor** to `service-intelligence`. Has its own 8-migration Alembic chain. Not wired into docker-compose. Status: ambiguous dead code. |

---

## Inter-Service Communication

```
Mobile App
    │  HTTPS REST (Axios, Bearer JWT)
    ▼
service-core (port 8080)
    │  gRPC plaintext (port 50051, x-internal-service-token header)
    ▼
service-intelligence
    │  async SQLAlchemy
    ▼
PostgreSQL (shared db service)
```

- service-core also exposes a gRPC server on port 9090 (`HealthResultLifecycleService`) with no known consumer.
- `agent/` can import service-intelligence modules directly or call its HTTP endpoint.
- Mobile talks only to service-core; never directly to service-intelligence.

---

## Authentication & Authorization

| Layer | Mechanism |
|-------|-----------|
| Mobile → service-core | OIDC Authorization Code + PKCE via Keycloak; `expo-auth-session`; token in `expo-secure-store` |
| service-core JWT validation | Spring Security OAuth2 resource server; `NimbusJwtDecoder` against Keycloak JWK endpoint; custom `AudienceValidator` requiring `pranapulse-core` audience |
| service-core → service-intelligence | Shared secret header `x-internal-service-token`; verified in gRPC interceptor |

---

## Testing

| Layer | Framework | Notes |
|-------|-----------|-------|
| service-core | JUnit 5, Mockito, MockMvc | `@SpringBootTest` with H2; JWT mocked via `SecurityMockMvcRequestPostProcessors.jwt()` |
| service-intelligence | Pytest + pytest-asyncio | Covers rPPG, voice DSP, quality gate, anemia, skin tone, vascular age, gRPC contract; CI runs against real PostgreSQL |
| mobile | Jest / jest-expo | `axios-mock-adapter` for API mocking |

---

## CI/CD

Single workflow: `.github/workflows/ci.yml`. Triggers on push/PR to `main` and `develop`.

| Job | Status |
|-----|--------|
| service-intelligence lint (ruff + black) | ✓ |
| service-intelligence tests (pytest + coverage) | ✓ |
| mobile lint (tsc + ESLint) | ✓ |
| mobile tests (Jest + coverage) | ✓ |
| **service-core build + tests** | **MISSING** |

No CD pipeline exists — no deployment, container registry push, or staging automation.

---

## Critical Issues

### 1. gRPC transport is plaintext — no mTLS

Both services negotiate an unencrypted gRPC channel:

- `service-intelligence/app/grpc_runtime.py:155` — `add_insecure_port`
- `service-core/.../IntelligenceServiceConfig.java:21` — `usePlaintext()`

In any cloud deployment where services cross network zones, this transmits health data in the clear. The shared secret header is not a substitute for transport security.

**Fix:** Add mTLS with cert rotation, or tunnel behind a service mesh (Linkerd/Istio). At minimum, enforce TLS at the Docker network boundary in all non-local environments.

---

### 2. Internal service token has insecure defaults and no rotation

`dev-internal-service-token` is hardcoded in:
- `service-intelligence/app/config.py`
- `service-core/src/main/resources/application.yml`
- docker-compose environment block

There is no rotation mechanism. A misconfigured deployment ships this default to production.

**Fix:** Enforce a startup assertion that rejects the default string outside the `dev` Spring profile. Long-term: replace with mTLS client certs or SPIFFE/SVID.

---

### 3. `service-core` is entirely absent from CI

The primary product-facing service — handling auth, consent, DPDP compliance, scan sessions — has no Maven build or test job in CI. Regressions are invisible to the pipeline.

**Fix:** Add a `service-core-test` job to `ci.yml` running `mvn verify` with the H2 test profile.

---

### 4. Data purger crashes at runtime

`scripts/run_data_purger.py:8` imports `SessionLocal` from `app.database`, but `service-intelligence/app/database.py` only defines `AsyncSessionLocal`. This import fails at runtime.

**Fix:** Update the script to use `AsyncSessionLocal` with an `async` entry point, or create a sync helper specifically for script use.

---

### 5. Unbounded scan result query + N+1 in `TrendAnalysisService`

`service-core/.../TrendAnalysisService.java:32–58` issues an unbounded `findByUser_IdOrderByCreatedAtAsc` returning all `ScanResult` records for a user. Combined with `@ElementCollection(fetch = EAGER)` on `flags` and `warnings` (`ScanResult.java:79,89`), every result load triggers two additional join queries.

**Fix:** Scope the query to a rolling window using `Pageable`. Switch `flags` and `warnings` to lazy loading, or join-fetch only when explicitly needed.

---

## High-Priority Concerns

### 6. Keycloak realm config has production-unsafe defaults

`keycloak/pranapulse-realm.json:6` has:
- `"sslRequired": "none"` — tokens issued over plaintext HTTP
- `"bruteForceProtected": false` — credential stuffing trivially possible
- Seeded test user `testuser@pranapulse.dev` / `testpassword`

**Fix:** Make realm config environment-specific. Production realm must have `sslRequired: external`, `bruteForceProtected: true`, and no seeded test users. Provision via Keycloak admin API, not a bundled JSON file.

---

### 7. Write transaction on every authenticated request

`AuthenticatedUserService.getOrProvisionUser(jwt)` calls `userRepository.save(user)` on every request including read-only GETs, updating `last_login_at` and user fields unconditionally.

**Fix:** Dirty-check user fields before saving. Only write when values have changed. Cache the provisioned user within the request context.

---

### 8. No rate limiting or request throttling

Neither service has rate limiting. rPPG and voice DSP are computationally expensive — burst traffic against `POST /api/v1/scans/evaluations` will saturate service-intelligence.

**Fix:** Add rate limiting at the API gateway layer, or within Spring via Bucket4j/resilience4j. Apply stricter limits to the evaluation endpoint than read-only endpoints.

---

### 9. No silent token refresh on mobile

The 5-minute access token lifetime causes mid-session 401 errors. `useOidcAuth` only refreshes on app launch.

**Fix:** Add a response interceptor in `mobile/src/api/client.ts` that catches 401, proactively refreshes the token via `expo-auth-session`, and retries the original request.

---

## Medium-Priority Concerns

### 10. `backend/` is ambiguous dead code

`/backend/` contains a second FastAPI service with its own 8-migration Alembic chain, OTP, ABHA, and user models — not wired into docker-compose. This creates confusion about canonical service ownership and could conflict with `service-intelligence`'s Alembic chain on the same database.

**Fix:** Delete if superseded. Move to a feature branch if planned future work.

---

### 11. `ScanType` comparisons use raw string literals

`service-intelligence/.../scan_evaluation_service.py:51,84` compares `submission.scan_type == "standard"` instead of `== ScanType.STANDARD`. Works today because `ScanType` is a `StrEnum`, but will silently break on any value refactor.

**Fix:** Use enum constants throughout.

---

### 12. Orphan gRPC server on port 9090

`HealthResultLifecycleGrpcService` is fully implemented and exposed on `service-core:9090` but nothing in the codebase consumes it — not mobile, not agent, not service-intelligence.

**Fix:** Document the intended consumer explicitly, or remove the service and close the port.

---

### 13. `ScanEvaluationController` appears redundant

`POST /api/v1/scans/evaluations` and `PUT /api/v1/scans/sessions/:id/complete` both accept evaluation payloads. The mobile client uses only the session path.

**Fix:** Clarify intent. If the evaluations endpoint is not a deliberate bypass route, consolidate to one path with clear semantics.

---

## Architecture-Level Observations

### Two migration tools on one database

Flyway (`service-core`) and Alembic (`service-intelligence`) both target the same PostgreSQL instance with no coordination between them. A future feature crossing the service boundary requires carefully synchronised migrations across two toolchains.

**Recommendation:** Enforce strict schema namespacing (the `core` schema is a good start). Consider standardising on one migration tool long-term, or introduce a migration sequencing convention.

### No CD pipeline and no production deployment config

Docker Compose is suitable for local dev only. There are no Kubernetes manifests, Helm charts, Terraform, or container registry push steps in CI.

**Recommendation:** Before beta: add image build+push CI jobs, secrets injection via a vault (not `.env` files), and a defined deployment target. Retrofitting this at launch is painful.

### Polyglot split is justified but carries maintenance cost

The Java/Python split makes sense — the DSP compute workloads genuinely benefit from NumPy/SciPy, and future ML model integration will require Python. However, this doubles operational complexity (two runtimes, two ORM/migration tools, two CI configs, gRPC proto contract maintenance). The proto contract has no schema registry or automated compatibility checking.

**Recommendation:** Add a proto linting step to CI (e.g., `buf lint` + `buf breaking`) to catch contract regressions before they reach runtime.

---

## Summary Priority Table

| Priority | Issue | Location |
|----------|-------|----------|
| **Critical** | gRPC plaintext, no mTLS | `grpc_runtime.py:155`, `IntelligenceServiceConfig.java:21` |
| **Critical** | service-core absent from CI | `.github/workflows/ci.yml` |
| **Critical** | Data purger crashes at runtime (wrong import) | `scripts/run_data_purger.py:8` |
| **Critical** | Insecure internal token defaults, no rotation | `config.py`, `application.yml` |
| **High** | Unbounded scan result query + N+1 pattern | `TrendAnalysisService.java:32-58`, `ScanResult.java:79,89` |
| **High** | Keycloak prod-unsafe defaults + test user in realm | `pranapulse-realm.json:6` |
| **High** | Write transaction on every GET request | `AuthenticatedUserService` |
| **High** | No rate limiting on compute endpoints | Both services |
| **High** | No mobile silent token refresh | `mobile/src/api/client.ts` |
| **Medium** | Dead `backend/` service with conflicting Alembic chain | `backend/` |
| **Medium** | Raw string ScanType comparison | `scan_evaluation_service.py:51,84` |
| **Medium** | Orphan gRPC server on port 9090 with no consumer | `HealthResultLifecycleGrpcService` |
| **Medium** | Redundant `ScanEvaluationController` endpoint | `ScanEvaluationController` |
| **Low** | No CD pipeline or production deployment config | `.github/workflows/` |
| **Low** | Two migration tools on one database, no coordination | Flyway + Alembic |
| **Low** | No proto linting or breaking-change detection | Proto definitions |
