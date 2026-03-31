# System Overview

## Purpose

PranaScan is a wellness-screening system built around a short front-camera scan
plus a short voice capture. It is intentionally framed as a wellness indicator
tool, not a medical device and not a diagnostic system.

The system currently serves four main jobs:

1. Capture a consented wellness scan on mobile.
2. Derive or accept wellness metrics for heart, breathing, and voice.
3. Persist a privacy-preserving scan record tied to a pseudonymous user ID.
4. Detect meaningful trend deviation over time and trigger a non-diagnostic
   follow-up reminder.

## Design Principles

### 1. Wellness, Not Diagnosis

- No API or UI surface should use diagnostic language.
- The only allowed alert string is `consider_lab_followup`.
- Result copy is framed as self-monitoring and follow-up guidance.

### 2. Privacy By Design

- User identity is a pseudonymous UUID, not PII.
- Consent is append-only.
- Audit is append-only.
- The current mobile path keeps raw video and audio on-device.
- The backend stores metric snapshots and quality metadata, not raw media.

### 3. Quality Gating Before Persistence

Every scan is evaluated against a shared set of quality thresholds before the
backend accepts it:

| Dimension | Current Threshold | Notes |
| --- | --- | --- |
| Lighting | `> 0.4` | Derived from JPEG heuristics on mobile |
| Motion | `>= 0.95` | Derived from frame-to-frame JPEG similarity |
| Face confidence | `> 0.8` | Mobile heuristic today, native detector later |
| Audio SNR | `> 15 dB` | Derived from real voice capture |

### 4. Hybrid Transition Architecture

The codebase is in a transition state between two modes:

| Concern | Current Mobile Path | Backend Capability |
| --- | --- | --- |
| rPPG | On-device in `mobile/src/utils/rppgProcessor.ts` | Legacy or fallback server-side processing still exists |
| Voice DSP | On-device in `mobile/src/utils/voiceProcessor.ts` | Legacy or fallback server-side processing still exists |
| Trend engine | Backend-owned | Backend-owned |
| Vascular age | Not shown in mobile UI | Computed and persisted by backend |
| Anemia screening | Not shown in mobile UI | Computed and persisted by backend |
| Alert delivery | No mobile role | Backend stub with cooldown and webhook delivery |

The important onboarding takeaway is this:

- The architecture target is edge-first.
- The mobile app largely follows that target now.
- The backend still preserves compatibility with older payload shapes.

## Runtime Architecture

```text
+----------------------- Mobile App ------------------------+
|                                                          |
|  ConsentScreen                                           |
|    -> useConsent                                         |
|    -> AsyncStorage pseudonymous user_id                  |
|    -> grantConsent / getConsentStatus                    |
|                                                          |
|  ScanScreen                                              |
|    -> createScanSession                                  |
|    -> CameraCapture                                      |
|         -> frameAnalyzer                                 |
|         -> rppgProcessor                                 |
|    -> VoiceCapture                                       |
|         -> voiceAnalyzer                                 |
|         -> voiceProcessor                                |
|    -> submit derived scalar metrics                      |
|                                                          |
|  ResultsScreen                                           |
|    -> getScanSession                                     |
|                                                          |
+-------------------------- HTTPS --------------------------+
                             |
                             v
+---------------------- FastAPI Backend --------------------+
| app.main                                                  |
|   - CORS                                                  |
|   - TimingMiddleware                                      |
|   - audit_log_middleware                                  |
|   - /auth, /consent, /scans, /audit routers              |
|                                                          |
| Scan completion pipeline                                  |
|   -> optional server-side rPPG fallback                  |
|   -> optional server-side voice fallback                 |
|   -> quality gate                                        |
|   -> trend baseline + cooldown                           |
|   -> webhook/log delivery stub                           |
|   -> vascular age heuristic                              |
|   -> anemia screening heuristic                          |
|   -> persist ScanResult                                  |
|                                                          |
+----------------------- Database --------------------------+
| consent_records | scan_sessions | scan_results | audit_logs |
+------------------------------------------------------------+
```

## Main System Components

### Mobile

- App shell: `mobile/App.tsx`
- API client and auth bootstrap: `mobile/src/api/client.ts`
- Consent flow: `mobile/src/screens/ConsentScreen.tsx`,
  `mobile/src/hooks/useConsent.ts`
- Scan orchestration: `mobile/src/screens/ScanScreen.tsx`,
  `mobile/src/hooks/useScan.ts`
- Camera capture: `mobile/src/components/CameraCapture.tsx`
- Voice capture: `mobile/src/components/VoiceCapture.tsx`
- On-device signal processing:
  `mobile/src/utils/frameAnalyzer.ts`,
  `mobile/src/utils/rppgProcessor.ts`,
  `mobile/src/utils/voiceAnalyzer.ts`,
  `mobile/src/utils/voiceProcessor.ts`

### Backend

- App bootstrap: `backend/app/main.py`
- Config: `backend/app/config.py`
- DB session and models: `backend/app/database.py`, `backend/app/models/*`
- Routers: `backend/app/routers/*`
- Middleware: `backend/app/middleware/*`
- Services: `backend/app/services/*`
- Migrations: `backend/migrations/*`

## Current End-To-End Flow

### Happy Path

1. Mobile bootstraps or loads a pseudonymous `user_id`.
2. User grants consent.
3. Mobile requests a JWT token for that `user_id`.
4. Mobile creates a scan session.
5. Camera step captures frames, derives quality metrics, and runs on-device rPPG.
6. Voice step records audio, derives SNR and runs on-device voice DSP.
7. Mobile submits scalar wellness indicators plus quality metadata.
8. Backend validates quality, computes trend state, cooldown, alert delivery,
   vascular age, and anemia heuristics.
9. Backend persists the scan result.
10. Mobile fetches and renders the result.

### Alternate Or Legacy Path

The backend still accepts:

- `frame_data` for server-side rPPG
- `audio_samples` for server-side voice DSP

This means future clients, old clients, or debugging tools can still use the
backend processing path even though the current mobile path is primarily
edge-first.

## Architectural Facts A New Engineer Should Know

### The app uses simple state-based navigation

The mobile app depends on React Navigation packages, but the runtime shell in
`mobile/App.tsx` currently uses a local screen state machine instead of a
navigation stack.

### The backend owns all persistence and historical logic

Mobile owns capture and first-pass processing. Backend owns:

- consent state
- audit trail
- scan session lifecycle
- long-term scan history
- trend baselines
- delivery stubs
- vascular-age heuristic
- anemia heuristic

### Current docs are not fully synchronized

There is drift between:

- older planning docs
- the original architecture doc
- the current runtime code

These design docs are intended to bridge that gap for onboarding.

## Important Gaps And Transition Areas

These are not theoretical gaps. They matter to engineers starting work now.

- The mobile UI does not currently render backend vascular-age or anemia fields.
- The audit middleware checks `request.state.user_id`, but the current auth path
  does not populate it, so audit rows may not reliably record the acting user.
- Consent routes require auth but currently use the `user_id` from the request
  body rather than enforcing that it matches the authenticated subject.
- The project still carries both edge-first and backend-fallback processing
  modes, so engineers need to be explicit about which path they are changing.
- Trend alerting, cooldown, and webhook delivery exist in code, but some status
  docs still describe them as incomplete.
