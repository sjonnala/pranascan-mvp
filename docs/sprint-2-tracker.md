# PranaScan — Sprint 2 Tracker

**Last updated:** 2026-03-10 18:30 UTC  
**Branch:** `main` | **Status:** All checks green

---

## Sprint 2 Exit Criteria

| Criterion | Status |
|---|---|
| S2-01 through S2-06 complete | ✅ **DONE** |
| CI green on main | ✅ |
| Demo flow: Consent → Capture → Real processing → Result → Baseline/deviation | ✅ |

---

## Story Status

| ID | Story | SP | Status | Key Commits |
|---|---|---:|---|---|
| S2-01 | Real camera capture pipeline | 5 | ✅ Done | `73e68ec` |
| S2-02 | rPPG v1 processing (no simulation) | 8 | ✅ Done | `0794e79`, `73a1ffb`, `04955d8` |
| S2-03 | Voice DSP v1 (no simulation) | 5 | ✅ Done | `6110c53`, `56e2259` |
| S2-04 | JWT auth enforcement | 5 | ✅ Done | `a53dcc6`, `46a28f9`, `5345634` |
| S2-05 | Baseline + 15% deviation engine | 5 | ✅ Done | `b1632a6`, `5495dc2` |
| S2-06 | ABHA adapter with sandbox mock + feature flag | 3 | ✅ Done | `HEAD` (this session) |
| S2-07 | Latency/perf hardening + observability | 3 | ✅ Done | `8a75af7` |

**Total: 34 SP — Sprint COMPLETE ✅**

---

## Beyond Sprint Scope (completed this sprint)

| Commit | What |
|---|---|
| `dc95499` | Vascular age heuristic v1 (D11) |
| `e5516f0` | Anemia screening color heuristic v1 (D12) |
| `21886eb` | Weekly vitality report — generate, store, deliver (D20) |
| `f9eeb83` | Security hardening — headers, rate limiting, DPDP checklist (D25) |

---

## S2-06 ABHA Adapter — Implementation Summary

**Feature flag:** `ABHA_ENABLED` (default `False`) — safe to deploy without activating.  
**Sandbox flag:** `ABHA_SANDBOX` (default `True`) — no real ABDM HTTP calls until explicitly disabled.

### New files
- `backend/app/models/abha.py` — `AbhaLink`, `AbhaSyncRecord` DB models
- `backend/app/schemas/abha.py` — Pydantic request/response schemas (ABHA ID validation)
- `backend/app/services/abha_adapter.py` — Adapter service: link/unlink/sync, sandbox mock, FHIR payload builder
- `backend/app/routers/abha.py` — REST router: POST/DELETE `/abha/link`, GET `/abha/status`, POST `/abha/sync/{session_id}`
- `backend/tests/test_abha.py` — 23 tests covering all endpoints + adapter unit tests

### Modified files
- `backend/app/config.py` — Added `abha_enabled`, `abha_sandbox`, `abha_gateway_url`, `abha_client_id`, `abha_client_secret`
- `backend/app/main.py` — Wired ABHA router + imported model to register tables
- `backend/migrations/env.py` — Added `abha` to model imports for Alembic
- `backend/tests/test_abha.py` — (ruff-autoformatted)

### API Endpoints
| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/abha/link` | Link ABHA ID (validates 14-digit format) |
| DELETE | `/api/v1/abha/link` | Unlink ABHA account (soft delete) |
| GET | `/api/v1/abha/status` | Link status + last sync info |
| POST | `/api/v1/abha/sync/{session_id}` | Manual sync of completed scan to ABDM |

### Sandbox behaviour
- Returns `status="skipped_disabled"` when `ABHA_ENABLED=false`
- Returns `status="skipped_no_link"` when enabled but no active link
- Returns `status="success"` + `gateway_ref="SANDBOX-<uuid>"` in sandbox mode
- FHIR R4 Observation bundle built locally, logged; no HTTP call made
- Live mode raises `NotImplementedError` until ABDM HIU/HIP registration complete

---

## Validation (2026-03-10)

```
python3 -m ruff check .          → All checks passed!
PYTHONPATH=backend pytest -q     → 156 passed in 7.30s
npx eslint src/ --ext .ts,.tsx   → (clean)
npx tsc --noEmit                 → (clean)
npm test -- --watchAll=false     → 116 passed, 9 suites
```

---

## Next Sprint Candidates (Sprint 3)

| Priority | Item | Notes |
|---|---|---|
| 1 | **Skin-tone calibration (Fitzpatrick 3–6)** | D5 / D24 — primary accuracy risk |
| 2 | **Accuracy bench testing** | D22 — 20-person controlled session vs finger-clip oximeter |
| 3 | **Face confidence: expo-face-detector** | Replace JPEG heuristic proxy (deferred from S2-04) |
| 4 | **Live ABDM sync implementation** | After HIU/HIP registration approved |
| 5 | **WhatsApp/Telegram alert delivery** | Replace stub delivery in delivery_service.py |
| 6 | **Closed beta onboarding** | 50 users — D27 target |
