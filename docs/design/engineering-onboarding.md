# Engineering Onboarding

## Goal Of This Guide

This guide is for engineers who want to start making changes safely within the
first day. It focuses on:

- how to run the system
- how to test the system
- how the repo is organized
- what to trust
- what to be careful with

## First Reading Pass

Read these in order:

1. `docs/design/system-overview.md`
2. `docs/design/component-workflows.md`
3. `docs/design/backend-design.md`
4. `docs/design/mobile-design.md`
5. `docs/design/data-contracts.md`
6. `docs/project-status.md`

## Local Prerequisites

### Backend

- Python 3.11
- virtualenv or equivalent
- PostgreSQL if running outside tests

### Mobile

- Node 20 or compatible
- npm
- Expo tooling
- iOS Simulator or Android Emulator or physical device

### Docker Option

`docker-compose.yml` currently brings up:

- PostgreSQL
- backend

It does not run the mobile app.
It also references `backend/Dockerfile`, which is not currently present in the
repo, so treat compose as an intended path that still needs packaging cleanup.

## Local Setup

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload
```

### Mobile

```bash
cd mobile
npm install
npx expo start
```

### Full Backend Stack With Docker

```bash
docker compose up --build
```

## Test And Validation Commands

### Backend

```bash
python3 -m ruff check .
PYTHONPATH=backend python3 -m pytest -q
```

### Mobile

```bash
cd mobile
npx eslint src/ --ext .ts,.tsx
npx tsc --noEmit
npm test -- --watchAll=false
```

### CI

GitHub Actions currently runs:

- backend lint and formatting checks
- backend pytest against PostgreSQL
- mobile TypeScript and ESLint
- mobile Jest

## How To Choose Where To Work

### Work In Mobile When

- capture behavior changes
- UI copy changes
- permission flow changes
- quality feedback changes
- on-device signal-processing changes
- API payload-shape changes at the client boundary

### Work In Backend When

- auth changes
- consent-policy changes
- persistence-model changes
- trend logic changes
- delivery changes
- vascular-age or anemia heuristics change
- API contract changes

### Work In Both When

- thresholds change
- new metrics are added
- a backend response field becomes user-visible
- privacy policy changes alter what may be sent over the network

## Repo Areas That Matter Most

### Mobile First

- `mobile/App.tsx`
- `mobile/src/screens/*`
- `mobile/src/components/*`
- `mobile/src/hooks/*`
- `mobile/src/api/client.ts`
- `mobile/src/utils/*`
- `mobile/src/types/index.ts`

### Backend First

- `backend/app/main.py`
- `backend/app/config.py`
- `backend/app/routers/*`
- `backend/app/services/*`
- `backend/app/models/*`
- `backend/app/schemas/*`
- `backend/tests/*`

## Recommended First Tasks For A New Engineer

These are good starter tasks because they are high-signal and low ambiguity.

1. Sync mobile `ScanResult` types and `ResultsScreen` with backend vascular-age
   and anemia fields.
2. Harden consent routes so `body.user_id` must match the authenticated subject.
3. Populate `request.state.user_id` so audit rows can attribute the acting user.
4. Decide whether the repo is officially edge-first now, then remove or clearly
   quarantine stale fallback docs and comments.
5. Centralize shared thresholds so mobile and backend cannot drift.

## Common Gotchas

### 1. Docs Drift

Older docs, handoffs, and backlog notes may describe earlier system states.
Use the code and the `docs/design/` set as your working reference.

### 2. Hybrid Signal Path

The mobile app is now mostly edge-first, but the backend still supports
server-side processing for `frame_data` and `audio_samples`.
Be explicit about which path your change affects.

### 3. Threshold Changes Are Cross-Cutting

Quality thresholds live in more than one place.

At minimum check:

- backend config
- backend quality gate
- mobile quality evaluation
- tests
- user-facing copy

### 4. Backend Test Environment

Local backend tests use in-memory SQLite fixtures, but CI runs PostgreSQL.
Be careful with SQL or migration changes that behave differently across both.

### 5. Missing Dev Dependencies

If backend pytest fails at import time, check that you installed both:

- `requirements.txt`
- `requirements-dev.txt`

The test suite needs packages such as `pytest-asyncio`.

### 6. Mobile API Base URL

The mobile client reads `EXPO_PUBLIC_API_URL` in `src/api/client.ts` and falls
back to `http://localhost:8000`.

That means:

- the `app.json` `extra.apiBaseUrl` value is not the active runtime source
- `localhost` only works in a simulator that can reach the host machine
- physical-device testing usually needs an explicit LAN URL

## Practical Change Recipes

### Add A New Response Field To Results

1. add or confirm backend model field
2. add or confirm backend response schema field
3. persist it in the scan router
4. add backend tests
5. add TypeScript type field
6. render it in `ResultsScreen`
7. add mobile tests if it affects UI

### Add A New Quality Rule

1. add config value in backend
2. update `run_quality_gate()`
3. update mobile `evaluateQuality()`
4. update `QualityGate` copy if needed
5. add or update tests on both sides

### Add A New Scan Heuristic

1. add a dedicated backend service if it is backend-owned
2. keep it non-diagnostic in naming and copy
3. decide whether it runs:
   - on-device
   - on backend
   - both for compatibility
4. persist it in `ScanResult`
5. expose it to the UI only if product wants it surfaced

## What To Trust

Trust, in this order:

1. current code
2. tests that still match current code
3. `docs/design/*`
4. `docs/project-status.md`
5. older planning docs and handoff notes

## Definition Of A Safe Change In This Repo

A safe change usually means:

- privacy stance is preserved
- no diagnostic language is introduced
- thresholds stay consistent across mobile and backend
- tests are updated near the changed behavior
- schema changes are reflected in both backend and mobile where relevant
- any architecture drift is called out explicitly in code or docs
