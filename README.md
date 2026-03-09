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

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env          # fill in DB_URL, SECRET_KEY
alembic upgrade head
uvicorn app.main:app --reload
```

### Mobile

```bash
cd mobile
npm install
npx expo start
```

### Docker (full stack)

```bash
docker compose up --build
```

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

## Sprint 1 (Mar 9–22, 2026)

See [docs/sprint-1-plan.md](docs/sprint-1-plan.md) and [docs/sprint-1-backlog.md](docs/sprint-1-backlog.md).

## Current Status

See [docs/project-status.md](docs/project-status.md) for a code-based completion assessment against the original MVP execution plan in [docs/sprint-plan.md](docs/sprint-plan.md).
