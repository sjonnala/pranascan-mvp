# Component Workflows

This document explains how the main components collaborate at runtime.

## 1. Consent Workflow

### Components Involved

- `mobile/App.tsx`
- `mobile/src/screens/ConsentScreen.tsx`
- `mobile/src/hooks/useConsent.ts`
- `mobile/src/api/client.ts`
- `backend/app/routers/consent.py`
- `backend/app/services/consent_service.py`
- `backend/app/models/consent.py`

### Sequence

```text
App
  -> ConsentScreen
     -> useConsent
        -> AsyncStorage: load or create user_id
        -> GET /api/v1/consent/status
        -> if already active: auto-advance to ScanScreen

User taps "I Agree"
  -> useConsent.grantUserConsent()
     -> POST /api/v1/auth/token
     -> POST /api/v1/consent
     -> GET /api/v1/consent/status
     -> cache consent status in AsyncStorage
  -> App transitions to ScanScreen
```

### Important Behavior

- Consent status is persisted locally so the app can recover gracefully.
- The backend stores consent as an append-only ledger.
- Active consent is derived from the latest meaningful consent action.
- Deletion requests are modeled as a consent-ledger event with a scheduled date.

## 2. Scan Session Workflow

### Components Involved

- `mobile/src/screens/ScanScreen.tsx`
- `mobile/src/hooks/useScan.ts`
- `mobile/src/api/client.ts`
- `backend/app/routers/scan.py`
- `backend/app/models/scan.py`

### Sequence

```text
ScanScreen mount
  -> useScan.startScan(userId)
     -> POST /api/v1/scans/sessions
     -> backend returns session_id
  -> UI enters camera step
```

### Backend Responsibilities During Session Creation

- Requires active consent
- Ignores spoofable `user_id` in the request body and uses the authenticated subject
- Persists a `scan_sessions` row with status `initiated`

## 3. Camera Workflow

### Components Involved

- `mobile/src/components/CameraCapture.tsx`
- `mobile/src/utils/frameAnalyzer.ts`
- `mobile/src/utils/rppgProcessor.ts`
- `mobile/src/hooks/useQualityCheck.ts`
- `mobile/src/components/QualityGate.tsx`

### Sequence

```text
CameraCapture.startScan()
  -> request camera permission if needed
  -> start 30s timer
  -> capture low-quality JPEG frame every 500ms
  -> derive lighting, motion, face-confidence heuristics
  -> emit live quality metrics to ScanScreen
  -> build FrameSample list
  -> after 30s run on-device rPPG
  -> return CameraResult to ScanScreen
```

### What CameraCapture Produces

- `hr_bpm`
- `hrv_ms`
- `respiratory_rate`
- `quality_score`
- `quality` object for lighting, motion, face confidence, audio placeholder
- `frame_data` retained in memory on device
- aggregate RGB means:
  - `frame_r_mean`
  - `frame_g_mean`
  - `frame_b_mean`

### Quality Feedback Loop

- `CameraCapture` emits `QualityMetrics`
- `useQualityCheck` converts metrics into flags and overall score
- `QualityGate` renders real-time pass/fail cues
- The backend re-evaluates the submitted quality metadata before persisting

## 4. Voice Workflow

### Components Involved

- `mobile/src/components/VoiceCapture.tsx`
- `mobile/src/utils/voiceAnalyzer.ts`
- `mobile/src/utils/voiceProcessor.ts`

### Sequence

```text
VoiceCapture.startRecording()
  -> request microphone permission if needed
  -> start 5s recording with metering
  -> update waveform bars from live metering
  -> stop recording
  -> extract PCM-like frames from replay callback
  -> if extraction fails, synthesize fallback samples from metering
  -> compute SNR
  -> run on-device voice DSP
  -> return jitter, shimmer, snr to ScanScreen
```

### What VoiceCapture Produces

- `voice_jitter_pct`
- `voice_shimmer_pct`
- `audio_snr_db`
- `passed_snr`

### Important Privacy Detail

The current mobile flow does not send `audio_samples` to the backend. It sends
only derived scalar indicators.

The backend still supports `audio_samples` for legacy or compatibility clients.

## 5. Result Submission Workflow

### Components Involved

- `mobile/src/screens/ScanScreen.tsx`
- `mobile/src/hooks/useScan.ts`
- `backend/app/routers/scan.py`
- backend services:
  - `quality_gate.py`
  - `trend_engine.py`
  - `delivery_service.py`
  - `vascular_age.py`
  - `anemia_screen.py`

### Sequence

```text
ScanScreen.handleVoiceComplete()
  -> merges CameraResult + VoiceResult
  -> evaluates final quality flags
  -> builds ScanResultPayload
  -> submits payload via PUT /api/v1/scans/sessions/{id}/complete

Backend complete_scan_session()
  -> load session and verify ownership
  -> optional server-side rPPG fallback if frame_data present
  -> optional server-side voice DSP fallback if audio_samples present
  -> quality gate
  -> trend baseline evaluation
  -> cooldown suppression
  -> alert delivery stub
  -> vascular-age heuristic
  -> anemia-screening heuristic
  -> persist ScanResult
  -> mark session completed
  -> return result
```

## 6. Results Workflow

### Components Involved

- `mobile/src/screens/ResultsScreen.tsx`
- `mobile/src/api/client.ts`
- `backend/app/routers/scan.py`

### Sequence

```text
ResultsScreen mount
  -> GET /api/v1/scans/sessions/{id}
  -> render result cards
  -> show trend notice if trend_alert == consider_lab_followup
```

### Important Current Limitation

The backend response includes additional fields such as:

- `vascular_age_estimate`
- `vascular_age_confidence`
- `hb_proxy_score`
- `anemia_wellness_label`
- `anemia_confidence`

The current mobile `ScanResult` TypeScript type and `ResultsScreen` do not yet
render those fields.

## 7. Trend Alert Workflow

### Components Involved

- `backend/app/services/trend_engine.py`
- `backend/app/services/delivery_service.py`
- `backend/app/routers/scan.py`

### Sequence

```text
Current scan arrives
  -> compute prior 7-day per-metric averages
  -> require at least 3 prior samples per metric
  -> compute absolute deviation percentage
  -> if any tracked metric deviates >= 15%:
       trend_alert = consider_lab_followup
  -> check cooldown window
  -> suppress if recent alert already exists
  -> if still active:
       deliver alert via structured log
       optionally POST to configured webhook
```

### Metrics Currently Tracked By Trend Engine

- `hr_bpm`
- `hrv_ms`
- `respiratory_rate`
- `voice_jitter_pct`
- `voice_shimmer_pct`

## 8. Audit Workflow

### Components Involved

- `backend/app/middleware/audit_log.py`
- `backend/app/models/audit.py`
- `backend/app/routers/audit.py`

### Sequence

```text
Any request except /health, /, /api/v1/audit/*
  -> request handled normally
  -> middleware writes audit row after response
  -> failures in audit logging are swallowed
```

### Important Caveat

The middleware currently reads `request.state.user_id`, but the auth dependency
does not populate that field. New engineers should treat user attribution in
the audit log as incomplete until that is fixed.
