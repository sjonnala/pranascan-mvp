# PranaScan MVP

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
| Backend | FastAPI (Python 3.11), Pydantic v2 |
| Database | PostgreSQL + SQLAlchemy 2.0 + Alembic |
| Auth | JWT (python-jose) |
| CI | GitHub Actions |

## Quick Start

### Recommended Local Setup

Use Podman Desktop for PostgreSQL and run backend/mobile directly on your machine. See [docs/setup/local-podman-postgres-setup.md](docs/setup/local-podman-postgres-setup.md) for the full flow.

### PostgreSQL via Podman

```bash
./scripts/start-postgres-podman.sh
```

### Backend

```bash
cd backend
cp .env.example .env          # fill in DB_URL, SECRET_KEY
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload
```

### Mobile

```bash
cd mobile
cp .env.example .env
npm install
npx expo start
```

### Important Mobile Note

For a physical phone, set `EXPO_PUBLIC_API_URL` in `mobile/.env` to your machine LAN IP instead of `localhost`.

## API Overview

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/consent` | Record informed consent |
| POST | `/api/v1/consent/revoke` | Revoke consent |
| POST | `/api/v1/consent/deletion-request` | Request data deletion (30-day hold) |
| GET | `/api/v1/consent/status` | Current consent status |
| POST | `/api/v1/scans/sessions` | Start scan session |
| PUT | `/api/v1/scans/sessions/{id}/complete` | Submit scan results |
| GET | `/api/v1/scans/sessions/{id}` | Fetch session |
| GET | `/api/v1/scans/history` | Scan history with trend deltas |
| GET | `/api/v1/audit/logs` | Immutable audit trail |

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
