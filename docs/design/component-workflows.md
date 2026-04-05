# Component Workflows

This document explains how the main components collaborate at runtime.

## 1. OIDC Login Workflow

### Components Involved

- `mobile/src/screens/AuthScreen.tsx`
- `mobile/src/hooks/useOidcAuth.ts`
- `mobile/src/auth/coreAuthSession.ts`
- `mobile/src/api/client.ts`
- OIDC provider
- `service-core`

### Sequence

```text
App
  -> AuthScreen
     -> useOidcAuth.signIn()
        -> Expo AuthSession PKCE flow
        -> OIDC authorize endpoint
        -> OIDC token exchange
        -> secure-store access token
        -> GET /api/v1/auth/me on service-core
  -> App transitions to consent or scan flow
```

### Important Behavior

- Mobile no longer bootstraps a local `user_id`.
- Mobile no longer calls legacy FastAPI OTP/JWT auth paths.
- `service-core` accepts only OIDC-issued bearer tokens with the configured audience.

## 2. Consent Workflow

### Components Involved

- `mobile/src/screens/ConsentScreen.tsx`
- `mobile/src/hooks/useConsent.ts`
- `mobile/src/api/client.ts`
- `service-core` consent endpoints

### Sequence

```text
ConsentScreen mount
  -> GET /api/v1/consent/status on service-core
  -> if already active: advance to ScanScreen

User taps "I Agree"
  -> POST /api/v1/consent on service-core
  -> GET /api/v1/consent/status
  -> App transitions to ScanScreen
```

### Important Behavior

- Consent is core-owned and derived from the authenticated subject.
- Consent status is still cached locally for UX recovery, not for authority.

## 3. Scan Session Workflow

### Components Involved

- `mobile/src/screens/ScanScreen.tsx`
- `mobile/src/hooks/useScan.ts`
- `mobile/src/api/client.ts`
- `service-core` scan endpoints

### Sequence

```text
ScanScreen mount
  -> useScan.startScan()
     -> POST /api/v1/scans/sessions on service-core
     -> service-core returns session_id
  -> UI enters camera step
```

### Backend Responsibilities During Session Creation

- Requires active core-owned consent
- Derives the user from the bearer token
- Persists a core-owned `scan_sessions` row with status `initiated`

## 4. Camera Workflow

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
- `service-core` forwards the submitted metrics to `service-intelligence` for server-side validation before persisting

## 5. Voice Workflow

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

The intelligence contract still supports `audio_samples` and raw media bytes as
optional compute inputs.

## 6. Result Submission Workflow

### Components Involved

- `mobile/src/screens/ScanScreen.tsx`
- `mobile/src/hooks/useScan.ts`
- `service-core` scan controller/service
- `service-intelligence/app/grpc_runtime.py`
- compute helpers:
  - `quality_gate.py`
  - `rppg_processor.py`
  - `voice_processor.py`
  - `vascular_age.py`
  - `anemia_screen.py`

### Sequence

```text
ScanScreen.handleVoiceComplete()
  -> merges CameraResult + VoiceResult
  -> evaluates final quality flags
  -> builds ScanResultPayload
  -> submits payload via PUT /api/v1/scans/sessions/{id}/complete on service-core

service-core completeScan()
  -> load session and verify ownership
  -> call ScanIntelligenceService/EvaluateScan over gRPC
  -> service-intelligence runs quality gate + compute heuristics
  -> service-core persists ScanResult
  -> service-core updates trend/history/report views
  -> mark session completed
  -> return core-owned result
```

## 7. Results Workflow

### Components Involved

- `mobile/src/screens/ResultsScreen.tsx`
- `mobile/src/api/client.ts`
- `service-core` scan/report endpoints

### Sequence

```text
ResultsScreen mount
  -> GET /api/v1/scans/sessions/{id} on service-core
  -> render result cards
  -> optionally fetch history/report views from service-core
```

## 8. Intelligence Compute Workflow

### Components Involved

- `service-core/src/main/java/com/pranapulse/core/infrastructure/intelligence/GrpcIntelligenceServiceGateway.java`
- `service-intelligence/app/grpc_runtime.py`
- `service-intelligence/app/services/scan_evaluation_service.py`

### Sequence

```text
service-core
  -> open gRPC channel to service-intelligence
  -> send EvaluateScan request with x-internal-service-token metadata

service-intelligence
  -> validate internal token
  -> derive vitals from raw media bytes when present
  -> optionally use frame_data/audio_samples fallback paths
  -> run quality gate
  -> compute vascular-age and anemia heuristics
  -> return compute-only response to service-core
```

## 9. Audit Workflow

### Components Involved

- `service-core` audit endpoints and request logging
- `service-intelligence/app/middleware/audit_log.py`
- `service-intelligence/app/models/audit.py`

### Sequence

```text
Mobile request to service-core
  -> core request logged to core audit trail
  -> if scan evaluation needed, core calls service-intelligence over gRPC

Operational HTTP request to service-intelligence (/ or /health)
  -> request handled normally
  -> audit middleware writes best-effort audit row
  -> failures in audit logging are swallowed
```

### Important Caveat

`service-intelligence` audit rows are operational, not end-user product truth.
The authoritative audit surface is the core-owned audit model in `service-core`.
