# PranaPulse Monorepo

**30-second wellness selfie + voice screening for proactive professionals in India.**

> PranaScan is a wellness indicator tool. It does not diagnose, treat, or replace medical advice.
> Always consult a qualified healthcare professional for any health concerns.

---

## What It Does

- **Camera scan (30s):** Captures facial video for heart rate (HR) and HRV estimation via rPPG
- **Voice scan (5s):** Records a sustained vowel for jitter/shimmer/respiratory proxy
- **Privacy-first:** All signal processing happens on-device; only anonymised metrics reach the server
- **Trend awareness:** Detects week-over-week shifts and suggests lab/doctor follow-up (never diagnoses)

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Mobile | React Native (Expo SDK 51), TypeScript |
| Service Intelligence | FastAPI (Python 3.11), Pydantic v2 |
| Service Core | Spring Boot 3.x, Java 21 |
| Database | PostgreSQL + SQLAlchemy 2.0 + Alembic |
| Auth | OIDC/JWT in `service-core`, Expo AuthSession PKCE in `mobile` |
| CI | GitHub Actions |

## Monorepo Layout

```text
pranapulse-monorepo/
├── service-intelligence/
│   ├── app/
│   ├── alembic/
│   └── requirements.txt
├── service-core/
│   ├── src/main/java/com/pranapulse/core/
│   └── pom.xml
├── mobile/
├── agent/
├── docs/
└── docker-compose.yml
```

## Quick Start

### Recommended Local Setup

Use Podman Desktop for PostgreSQL and run the repo as a polyglot monolith:

- `service-intelligence` for FastAPI rPPG and intelligence workflows
- `service-core` for Spring Boot business logic
- `mobile` for the Expo client
- shared PostgreSQL container with isolated schemas: `public` for `service-intelligence`, `core` for `service-core`
- phase 4 boundary shift: `service-core` owns public auth projection, consent/privacy workflows, scan evaluation, scan-session orchestration, scan history, reporting, and audit, and calls `service-intelligence` over an internal compute-only contract

See [docs/setup/local-podman-postgres-setup.md](docs/setup/local-podman-postgres-setup.md) for the current Python/mobile setup flow.

### Polyglot Monolith via Compose

```bash
docker compose up --build
```

This boots:

- `db` on `localhost:5433`
- `service-intelligence` on `localhost:8000`
- `service-core` REST on `localhost:8080`
- `service-core` gRPC on `localhost:9090`

`service-core` keeps JWT OIDC verification enabled. Authenticated calls require a reachable OIDC issuer configured through `APP_SECURITY_ISSUER_URI`, `APP_SECURITY_JWK_SET_URI`, and `APP_SECURITY_REQUIRED_AUDIENCE`.

### PostgreSQL via Podman

```bash
./scripts/start-postgres-podman.sh
```

### Service Intelligence

```bash
cd service-intelligence
cp .env.example .env          # fill in DATABASE_URL and INTERNAL_SERVICE_TOKEN
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload
```

### Service Core

```bash
cd service-core
./mvnw test
./mvnw spring-boot:run
```

### Mobile

```bash
cd mobile
cp .env.example .env
npm install
npx expo start
```

### Important Mobile Note

For local mobile development, point the app at `service-core` and configure the
same OIDC issuer that backs Spring Security:

- `EXPO_PUBLIC_CORE_API_URL=http://<your-host>:8080`
- `EXPO_PUBLIC_OIDC_ISSUER=http://<your-host>:8081/realms/pranapulse`
- `EXPO_PUBLIC_OIDC_CLIENT_ID=pranapulse-mobile`
- `EXPO_PUBLIC_OIDC_AUDIENCE=pranapulse-core`

For a physical phone, replace `localhost` with your machine LAN IP. The Expo
app now performs the OIDC login flow in-app, so there is no manual access-token
environment variable anymore.

## API Overview

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/auth/me` | Core-owned authenticated user projection |
| POST | `/api/v1/consent` | Core-owned informed consent grant |
| POST | `/api/v1/consent/revoke` | Core-owned consent revocation |
| POST | `/api/v1/consent/deletion-request` | Core-owned privacy deletion request |
| GET | `/api/v1/consent/status` | Core-owned consent/privacy status |
| POST | `/api/v1/scans/evaluations` | Core-owned scan evaluation entrypoint |
| POST | `/api/v1/scans/sessions` | Core-owned scan session creation |
| PUT | `/api/v1/scans/sessions/{id}/complete` | Core-owned scan completion and persistence |
| GET | `/api/v1/scans/sessions/{id}` | Core-owned session lookup |
| GET | `/api/v1/scans/history` | Core-owned scan history with trend deltas |
| POST | `/api/v1/feedback` | Core-owned post-scan feedback submission |
| GET | `/api/v1/feedback/sessions/{id}` | Core-owned session feedback lookup |
| POST | `/api/v1/reports/generate` | Core-owned weekly vitality report generation |
| GET | `/api/v1/reports/latest` | Core-owned latest vitality report |
| GET | `/api/v1/audit/logs` | Core-owned immutable audit trail |

## Key Constraints

- **No diagnostic language** — outputs are "wellness indicators"
- **Quality gates** — scans rejected below lighting/motion/audio thresholds
- **Audit logs immutable** — append-only, no deletes
- **Consent records append-only** — full history preserved
- **Post-scan latency < 15 s**

## Implementation Notes

- [docs/README.md](docs/README.md) — documentation index by purpose
- [docs/architecture/overview.md](docs/architecture/overview.md) — system architecture and execution model
- [docs/planning/sprint-plan.md](docs/planning/sprint-plan.md) — original MVP plan and milestone breakdown
- [docs/planning/sprint-2-tracker.md](docs/planning/sprint-2-tracker.md) — current tracker for delivered Sprint 2 and follow-on milestones
- [docs/handoffs/latest.md](docs/handoffs/latest.md) — latest engineering handoff and recommended next slice

## Current Status

See [docs/status/project-status.md](docs/status/project-status.md) for the current completion assessment against the MVP plan.
