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
6. `docs/status/project-status.md`

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
It also references `service-intelligence/Dockerfile`, which is not currently present in the
repo, so treat compose as an intended path that still needs packaging cleanup.

## Local Setup

### Backend

```bash
cd service-intelligence
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
PYTHONPATH=service-intelligence python3 -m pytest -q
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

- `service-core/src/main/java/com/pranapulse/core/scan/*`
- `service-core/src/main/java/com/pranapulse/core/consent/*`
- `service-core/src/main/java/com/pranapulse/core/report/*`
- `service-core/src/main/java/com/pranapulse/core/infrastructure/intelligence/*`
- `service-intelligence/app/main.py`
- `service-intelligence/app/grpc_runtime.py`
- `service-intelligence/app/services/*`
- `service-intelligence/tests/*`

## Recommended First Tasks For A New Engineer

These are good starter tasks because they are high-signal and low ambiguity.

1. Extend the gRPC scan-intelligence contract without leaking product-domain
   concerns into `service-intelligence`.
2. Tighten `service-core` integration tests around consent, scan completion,
   and report generation.
3. Decide whether the remaining shared database boundary should be redesigned
   or kept as isolated schemas.
4. Keep the design docs synchronized with the current core-versus-intelligence
   ownership split.
5. Centralize shared thresholds so mobile and server-side quality logic cannot drift.

## Common Gotchas

### 1. Docs Drift

Older docs, handoffs, and backlog notes may describe earlier system states.
Use the code and the `docs/design/` set as your working reference.

### 2. Hybrid Signal Path

The mobile app is primarily capture-first, while server-side intelligence still
accepts `frame_data`, `audio_samples`, and raw media bytes for compute
fallbacks. Be explicit about which path your change affects.

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

The mobile client now reads `EXPO_PUBLIC_CORE_API_URL` for Spring-owned public
APIs and falls back to `http://localhost:8080`. Mobile auth is now a real OIDC
PKCE flow, so it also needs:

- `EXPO_PUBLIC_OIDC_ISSUER`
- `EXPO_PUBLIC_OIDC_CLIENT_ID`
- `EXPO_PUBLIC_OIDC_AUDIENCE`

That means:

- the `app.json` `extra.*ApiBaseUrl` values are not the active runtime source
- `localhost` only works in a simulator that can reach the host machine
- physical-device testing usually needs an explicit LAN URL
- the app no longer accepts a manually injected core bearer token at runtime

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
4. `docs/status/project-status.md`
5. older planning docs and handoff notes

## Definition Of A Safe Change In This Repo

A safe change usually means:

- privacy stance is preserved
- no diagnostic language is introduced
- thresholds stay consistent across mobile and backend
- tests are updated near the changed behavior
- schema changes are reflected in both backend and mobile where relevant
- any architecture drift is called out explicitly in code or docs
