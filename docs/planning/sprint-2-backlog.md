# Sprint 2 Backlog — PranaScan MVP

**Sprint window:** March 9–22, 2026  
**Goal:** Replace simulations with real first-pass algorithms; enforce JWT auth; wire real camera preview.

---

## Velocity baseline
Sprint 1 delivered 38 story points in 1 session. Sprint 2 targets 34 points.

---

## Stories

### S2-1 · JWT Auth — Backend (5 pts)
**Priority:** P0  
**Depends on:** Sprint 1 backend  
**Description:**  
Implement JWT token issuance and enforce authentication on all protected routes.

**Acceptance Criteria:**
- `POST /api/v1/auth/token` — issue JWT for a user_id (dev: no password; prod: password/OTP)
- `POST /api/v1/auth/refresh` — refresh an expiring token
- `GET /api/v1/auth/me` — decode current token, return user info
- All scan + audit routes protected by `Depends(require_auth)`
- Consent routes: POST consent/revoke/deletion require auth; GET /status public
- 401 returned for missing/invalid/expired tokens
- Existing tests updated to pass a valid JWT header
- New tests: `test_auth.py` — token issue, expired token, tampered token, missing auth

**Files changed:**
- `app/routers/auth.py` (new)
- `app/middleware/auth.py` (new — `require_auth` dependency)
- `app/schemas/auth.py` (new)
- `app/routers/scan.py` — add `Depends(require_auth)`
- `app/routers/audit.py` — add `Depends(require_auth)`
- `app/routers/consent.py` — selectively add auth
- `app/main.py` — register auth router
- `tests/test_auth.py` (new)
- `tests/conftest.py` — add `auth_headers` fixture

---

### S2-2 · rPPG First-Pass Algorithm — Backend (8 pts)
**Priority:** P0  
**Depends on:** S2-1  
**Description:**  
Replace `simulateRppgProcessing()` with a real first-pass rPPG pipeline that runs server-side on extracted frame metadata (luminance time-series). The mobile client sends a compact JSON payload of per-frame RGB means (not raw video).

**Approach:**
- Client sends `frame_data`: array of `{t_ms, r_mean, g_mean, b_mean}` (one per frame, ~30fps × 30s = ~900 samples)
- Backend: `app/services/rppg_processor.py`
  - Green-channel bandpass filter (0.7–4.0 Hz, i.e. 42–240 bpm)
  - Peak detection → HR estimate
  - RMSSD computation → HRV estimate
  - Respiratory proxy: low-freq envelope of rPPG signal (0.1–0.5 Hz)
- Result replaces simulated values in `ScanResultSubmit`

**Acceptance Criteria:**
- `rppg_processor.py` processes a 900-sample synthetic signal and returns HR in [40–200] bpm range
- HRV computed via RMSSD from RR intervals
- Respiratory rate in [5–40] bpm range
- Unit tests with a synthetic sine-wave signal at 1 Hz (60 bpm) → HR within ±5 bpm
- All existing scan tests pass
- ruff clean

**Files changed:**
- `app/services/rppg_processor.py` (new)
- `app/schemas/scan.py` — add `frame_data` field to `ScanResultSubmit`
- `tests/test_rppg.py` (new)

---

### S2-3 · Voice DSP First-Pass — Backend (5 pts)
**Priority:** P0  
**Depends on:** S2-1  
**Description:**  
Replace `simulateVoiceAnalysis()` with real jitter/shimmer computation from audio amplitude envelope sent by the client.

**Approach:**
- Client sends `audio_samples`: array of amplitude values (normalized -1.0 to 1.0), sampled at 44100 Hz, 5s recording = 220,500 samples (downsample to 4410 before sending)
- Backend: `app/services/voice_processor.py`
  - F0 estimation via zero-crossing rate (proxy; real F0 tracking in Sprint 3)
  - Jitter: cycle-to-cycle period variation = std(period)/mean(period) × 100
  - Shimmer: cycle-to-cycle amplitude variation = std(amp)/mean(amp) × 100
  - SNR proxy: ratio of voiced energy to total energy

**Acceptance Criteria:**
- `voice_processor.py` processes a synthetic 440 Hz sine wave at 4410 Hz sample rate
- Jitter < 1% on pure sine (expected ~0%)
- Shimmer < 1% on pure sine (expected ~0%)
- SNR > 30 dB on pure sine signal
- Unit tests with pure sine + noisy sine inputs
- ruff clean

**Files changed:**
- `app/services/voice_processor.py` (new)
- `app/schemas/scan.py` — add `audio_samples` field to `ScanResultSubmit`
- `tests/test_voice.py` (new)

---

### S2-4 · Mobile — Real Camera Preview (5 pts)
**Priority:** P1  
**Depends on:** Sprint 1 mobile  
**Description:**  
Replace the placeholder `<View>` camera preview in `CameraCapture.tsx` with real `expo-camera` `CameraView`. Extract per-frame RGB means from the camera feed to send as `frame_data`.

**Note:** Full on-device rPPG processing deferred to Sprint 3 (needs native module). This story wires real camera + frame extraction; the extracted frame means are sent to the backend for processing (S2-2).

**Acceptance Criteria:**
- `CameraView` renders with front-facing camera
- Permission request shown if camera not granted
- Frame interval sampling: capture 1 frame every 33ms via `onCameraReady` + `takePictureAsync` or `useCameraPermissions` + `ref`
- Frame RGB means computed in JS (use image pixel sample)
- `frame_data` accumulated during 30s scan, sent as part of session complete payload
- Quality overlay: real luminance from frame mean (not simulated)
- Falls back to simulated data with clear warning if permission denied

**Files changed:**
- `mobile/src/components/CameraCapture.tsx` — replace simulation with real camera
- `mobile/src/hooks/useQualityCheck.ts` — wire real luminance input
- `mobile/__tests__/CameraCapture.test.tsx` (new)

---

### S2-5 · Mobile — Real Voice Capture + DSP Client (5 pts)
**Priority:** P1  
**Depends on:** S2-3, S2-4  
**Description:**  
Replace simulated voice analysis with real `expo-av` recording + amplitude extraction. Downsample to 4410 Hz and send `audio_samples` to backend.

**Acceptance Criteria:**
- `expo-av` `Audio.Recording` used for 5s capture
- Recording permissions requested
- Amplitude samples extracted from recording buffer (use `getStatusAsync` metering)
- SNR proxy computed client-side (silence ratio check)
- `audio_samples` sent as part of `ScanResultSubmit` payload
- VU meter reflects real audio level (not simulated)
- Guidance: "Please find a quieter space" shown when SNR fails — never diagnostic language
- Falls back gracefully if permission denied

**Files changed:**
- `mobile/src/components/VoiceCapture.tsx` — replace simulation with real capture
- `mobile/__tests__/VoiceCapture.test.tsx` (new)

---

### S2-6 · Daily Status + Changelog Update (1 pt)
**Priority:** P2  
**Depends on:** none  
**Description:**  
Update `docs/status/daily-status.md` with Sprint 2 progress. Update `docs/planning/sprint-1-backlog.md` with actual completion status.

**Acceptance Criteria:**
- `daily-status.md` has a dated Sprint 2 section
- All story statuses accurate

---

## Story Map

```
S2-1 JWT Auth ─────────────────────────────── P0
    └── S2-2 rPPG Algorithm ────────────────── P0
    └── S2-3 Voice DSP ─────────────────────── P0
S2-4 Real Camera Preview ──────────────────── P1
    └── S2-5 Real Voice Capture ────────────── P1
S2-6 Docs/Status ──────────────────────────── P2
```

## Definition of Done
- [ ] Code written and ruff/ESLint clean
- [ ] Tests written and passing
- [ ] No diagnostic language anywhere
- [ ] Committed with `feat(s2-N):` prefix

## Sprint 2 Total: 29 story points
