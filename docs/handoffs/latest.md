# PranaScan Handoff — 2026-03-11 04:40 UTC

## 1. Branch + Status

- **Branch:** `main`
- **Status:** local `main` includes the post-merge D26/D28 state plus the latest Week 4 onboarding and delivery follow-up work
- **Latest shipped milestone in code:** D27 closed beta onboarding flow
- **Latest milestone commits:**
  - `4f7eafc` — D26 bug bash hardening
  - `8d26fee` — D28 feedback instrumentation
  - `a04051b` — s2-14 WhatsApp delivery channel scaffold
  - `(current change set)` — D27 closed beta onboarding flow

---

## 2. Current Delivered Scope

### Core product path

- Consent, revoke, deletion request, and audit logging
- Authenticated mobile-to-backend scan flow
- Real mobile camera capture and real mobile voice capture
- On-device-derived inputs for backend wellness processing
- rPPG v1, voice DSP v1, baseline + multi-metric 15% deviation engine
- ABHA adapter scaffold, Telegram + WhatsApp delivery scaffolds, weekly vitality report, beta onboarding, and OpenClaw background agent

### Week 4 milestones complete in code

- **D25** security hardening
- **D26** bug bash hardening
- **D27** closed beta onboarding
- **D28** feedback instrumentation
- **S2-14 follow-up** WhatsApp delivery scaffold

### Still pending / externally gated

- **D22** bench validation vs reference devices
- **D24** empirical skin-tone audit evidence
- **D30** go/no-go KPI review
- WhatsApp sender/template approval and production credentials
- ABHA sandbox / production credential follow-up

---

## 3. D27 — Closed Beta Onboarding

### Backend

- **`backend/app/models/beta.py`**
  - added `beta_invites` and `beta_enrollments` persistence models
- **`backend/app/schemas/beta.py`**
  - added invite redeem and beta status contracts
- **`backend/app/routers/beta.py`**
  - added authenticated endpoints:
    - `GET /api/v1/beta/status`
    - `POST /api/v1/beta/redeem`
  - validates active, unexpired, under-capacity invite codes
  - keeps redeem idempotent for already-enrolled users
- **`backend/app/main.py`**
  - registers the beta router and beta models
  - seeds a reusable invite automatically when `BETA_SEED_INVITE_CODE` is configured for local/dev use
- **`backend/migrations/versions/006_add_beta_onboarding.py`**
  - adds invite and enrollment tables

### Mobile

- **`mobile/src/screens/BetaOnboardingScreen.tsx`**
  - added pre-consent closed-beta gate with invite-code entry
- **`mobile/src/hooks/useBetaAccess.ts`**
  - resolves the pseudonymous user ID, fetches beta status, caches it locally, and redeems invite codes
- **`mobile/src/api/client.ts`**
  - added beta status and redeem endpoints with auth bootstrapping
- **`mobile/App.tsx`**
  - app flow now starts with beta onboarding and advances to consent only after enrollment or when gating is disabled
- **`mobile/src/utils/identity.ts`**
  - shared user ID creation/persistence for onboarding and consent flows

### Tests added / updated

- **`backend/tests/test_beta.py`**
  - disabled-feature status
  - successful enrollment
  - invalid, expired, and exhausted invite handling
  - idempotent redeem for already-enrolled users
- **`mobile/__tests__/BetaOnboardingScreen.test.tsx`**
  - render, disabled state, redeem flow, auto-advance, loading, and error cases
- **`mobile/__tests__/apiClient.test.ts`**
  - beta status + redeem auth wiring

### Remaining constraints for this slice

- closed-beta invites still need to be provisioned in the target environment
- the current implementation supports invite-code gating, not full cohort-management tooling
- production rollout will still need recipient communications and recruitment operations outside the repo

---

## 4. WhatsApp Delivery Scaffold — What Was Built

### Backend

- **`backend/app/config.py`**
  - added feature-flagged WhatsApp Cloud API settings:
    - `whatsapp_enabled`
    - `whatsapp_access_token`
    - `whatsapp_phone_number_id`
    - `whatsapp_recipient_phone`
    - `whatsapp_api_version`
- **`backend/app/services/delivery_service.py`**
  - added `_whatsapp_configured()` guard
  - added `_send_whatsapp()` Cloud API transport
  - alerts now attempt WhatsApp delivery after log/webhook/Telegram when enabled
  - weekly vitality reports now attempt WhatsApp delivery when enabled
  - long WhatsApp report payloads are truncated safely to the text-message limit

### Tests added / updated

- **`backend/tests/test_delivery.py`**
  - alert delivery through WhatsApp
  - WhatsApp failure swallowing for alerts
  - feature-flag skip behavior
  - report delivery through WhatsApp
  - report truncation for WhatsApp text limits

### What remains outside this code slice

- real Meta Business credentials
- approved sender and any template/policy requirements for production rollout
- destination/recipient preference management beyond the single configured recipient

---

## 5. D28 — What Was Built

### Backend

- **`backend/app/models/feedback.py`**
  - new `scan_feedback` model with one record per completed scan session
- **`backend/app/schemas/feedback.py`**
  - request/response contracts for feedback submit + fetch
- **`backend/app/routers/feedback.py`**
  - authenticated feedback endpoints:
    - `POST /api/v1/feedback`
    - `GET /api/v1/feedback/sessions/{session_id}`
  - enforces ownership, completed-session requirement, and one-feedback-per-session
- **`backend/migrations/versions/005_add_scan_feedback.py`**
  - migration for the feedback table
- **`backend/app/main.py` and `backend/migrations/env.py`**
  - router/model registration

### Mobile

- **`mobile/src/screens/ResultsScreen.tsx`**
  - added post-scan feedback UI:
    - usefulness prompt
    - optional NPS score
    - optional note
  - existing feedback now renders as a thank-you summary instead of re-showing the form
- **`mobile/src/api/client.ts`**
  - feedback submit + per-session retrieval
  - results retrieval can re-bootstrap auth with `userId` when needed
- **`mobile/src/types/index.ts`**
  - feedback types and aligned quality-flag unions
- **`mobile/App.tsx`**
  - passes `userId` into `ResultsScreen`

### Tests added / updated

- **`backend/tests/test_feedback.py`**
  - create, duplicate rejection, completed-session enforcement, owner-only access, auth requirement
- **`mobile/__tests__/ResultsScreen.test.tsx`**
  - feedback prompt render, submission flow, existing-feedback thank-you state
- **`mobile/__tests__/apiClient.test.ts`**
  - feedback auth + `404 -> null` retrieval behavior

---

## 6. D26 — Hardening That Landed Before D28

- `quality_gate.py`
  - warning tiers for borderline lighting, face confidence, and audio SNR
  - motion remains a hard gate
- `voice_processor.py`
  - accented vowel accommodation for high-SNR, low-voiced-fraction samples
- `frameAnalyzer.ts`
  - occlusion hint detection and transient motion handling
- tests expanded in backend + mobile to cover these edge cases

---

## 7. Validation

```text
python3 -m ruff check .                         → All checks passed!
DEBUG=false PYTHONPATH=backend python3 -m pytest -q
                                                → 252 passed, 186 warnings in 7.11s
cd mobile && npx eslint src/ --ext .ts,.tsx    → clean
cd mobile && npx tsc --noEmit                  → clean
cd mobile && npm test -- --watchAll=false      → 151 passed, 11 suites
```

### Notes

- The local shell still has `DEBUG=release`, so Python validation is run with `DEBUG=false`.
- Mobile Jest still prints the existing `act(...)` warning from `ConsentScreen.test.tsx` and now the new beta screen test path, but the suite passes.
- Local comparison docs remain intentionally untracked:
  - `docs/local-project-status.md`
  - `docs/local-daily-status.md`
  - `docs/design/`

---

## 8. Recommended Next Slice

### Best next code-only milestone

**D30 go/no-go KPI template**

Why this next:
- D22 and D24 remain externally validation-heavy.
- D27 is now complete.
- WhatsApp channel scaffolding is now done; the remaining WhatsApp work is credential/policy activation rather than core implementation.
- D30 is the next remaining repo-native artifact that can be completed without waiting on external bench/audit sessions.

Suggested scope:
1. add a rollout KPI template under `docs/`
2. capture Week 4 exit criteria, blockers, and current evidence sources
3. map each KPI to the repo artifact or external validation source that proves it
4. leave D22/D24 explicitly marked as pending evidence
5. update `docs/sprint-2-tracker.md` and this handoff in the same change set

---

## 9. Resume Prompt

```text
Resume PranaScan on main after D27 closed beta onboarding.

Current state:
- D26 bug bash hardening is complete.
- D27 closed beta onboarding is complete.
- D28 feedback instrumentation is complete.
- WhatsApp delivery scaffold is complete behind feature flags.
- Local comparison docs remain untracked and should stay local-only.

Validation baseline:
- ruff clean
- backend pytest: 252 passed
- mobile eslint clean
- mobile tsc clean
- mobile jest: 151 passed

User-side context:
- external validation milestones will be handled later after local build/deploy
- ABHA sandbox creds are pending
- WhatsApp Business API credentials are not ready yet
- ignore the global DEBUG env issue for now

Recommended next slice:
- D30 go/no-go KPI template

Execution style:
- keep commits milestone-scoped, matching the existing repo history
- update tracker + handoff in the same change set
- do not stage local-only docs unless explicitly requested
```
