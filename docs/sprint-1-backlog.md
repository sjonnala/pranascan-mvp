# Sprint 1 Backlog

## S1 — Project Scaffolding & CI

**Acceptance criteria:**
- Monorepo structure with `mobile/`, `backend/`, `docs/`, `.github/`
- `docker-compose.yml` boots Postgres + backend
- CI runs lint + tests on push/PR

## S2 — Consent & Privacy Flow (Backend)

**Endpoints:**
- `POST /api/v1/consent` — Record consent with version + purpose
- `POST /api/v1/consent/revoke` — Append revocation record
- `POST /api/v1/consent/deletion-request` — Request deletion (30-day hold)
- `GET /api/v1/consent/status` — Current consent state

**Acceptance criteria:**
- Consent records are append-only (no UPDATE/DELETE on table)
- Deletion requests soft-delete with `deletion_scheduled_at = now + 30 days`
- Active consent required for scan session creation (enforced in router)

## S3 — Scan Session API (Backend)

**Endpoints:**
- `POST /api/v1/scans/sessions` — Create session (checks active consent)
- `PUT /api/v1/scans/sessions/{id}/complete` — Submit results
- `GET /api/v1/scans/sessions/{id}` — Fetch single session
- `GET /api/v1/scans/history` — Paginated history with trend_delta

**Result fields:** `hr_bpm`, `hrv_ms`, `respiratory_rate`, `voice_jitter_pct`, `voice_shimmer_pct`, `quality_score`, `flags`, `trend_alert`

**Acceptance criteria:**
- Quality gate validation on result submission
- `trend_alert` computed from 7-day rolling average
- No diagnostic language in any response field

## S4 — Audit Log API

**Endpoints:**
- `GET /api/v1/audit/logs` — Paginated audit trail

**Middleware:**
- Every request auto-logged (method, path, user_id, status_code, duration_ms)
- Audit records immutable — no update/delete

## S5 — Mobile Consent Screen

**Acceptance criteria:**
- Plain-language consent text (no legalese)
- Checkbox + "I Agree" CTA
- Stores consent token via `useConsent` hook
- Cannot proceed to scan without consent

## S6 — Mobile Camera Capture + Quality Gate

**Acceptance criteria:**
- 30s countdown with live preview
- Real-time quality indicator (lighting, face detection, motion)
- Rejects scan if any gate fails
- Simulated rPPG output for Sprint 1 (real algo in Sprint 2)

## S7 — Mobile Voice Capture

**Acceptance criteria:**
- 5s recording with animated waveform
- SNR check before submission
- Returns jitter/shimmer estimates

## S8 — Mobile Scan Orchestrator

**Acceptance criteria:**
- Sequences: Consent → Camera → Voice → Submit → Results
- Progress indicator
- Error states handled gracefully
- Results screen shows wellness indicators with no diagnostic language
