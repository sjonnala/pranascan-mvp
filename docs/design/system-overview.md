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

- Public API and persistence: `service-core/*`
- Core scan/intelligence gateway:
  `service-core/src/main/java/com/pranapulse/core/infrastructure/intelligence/*`
- Intelligence app bootstrap: `service-intelligence/app/main.py`
- Intelligence gRPC server: `service-intelligence/app/grpc_runtime.py`
- Intelligence middleware and services:
  `service-intelligence/app/middleware/*`,
  `service-intelligence/app/services/*`
- Intelligence migrations: `service-intelligence/alembic/*`

## Current End-To-End Flow

### Happy Path

1. Mobile completes OIDC login and stores the core access token.
2. User grants consent through `service-core`.
3. Mobile creates a scan session through `service-core`.
4. Camera step captures frames, derives quality metrics, and runs on-device rPPG.
5. Voice step records audio, derives SNR, and runs on-device voice DSP.
6. Mobile submits scalar wellness indicators plus optional raw media data.
7. `service-core` calls `service-intelligence` over gRPC for `EvaluateScan`.
8. `service-intelligence` validates quality and computes derived heuristics.
9. `service-core` persists the result, trend state, and related product history.
10. Mobile fetches and renders the core-owned result.

### Alternate Or Legacy Path

The intelligence contract still accepts:

- `frame_data` for server-side rPPG
- `audio_samples` for server-side voice DSP

This means future clients or debugging tools can still use server-side compute
fallbacks even though the current mobile path is primarily capture-first.

## Architectural Facts A New Engineer Should Know

### The app uses simple state-based navigation

The mobile app depends on React Navigation packages, but the runtime shell in
`mobile/App.tsx` currently uses a local screen state machine instead of a
navigation stack.

### `service-core` owns persistence and history

Mobile owns capture and authentication UX. `service-core` owns:

- consent state
- audit trail
- scan session lifecycle
- long-term scan history
- trend baselines
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

- The project still carries both capture-first and server-side fallback compute
  modes, so engineers need to be explicit about which path they are changing.
- The remaining shared database boundary is a transition area even though
  ownership has moved to `service-core`.
- Historical status and handoff docs still describe earlier FastAPI public API
  phases; treat them as archive material, not live design truth.
