# Mobile Design

## Mobile Role

The mobile app is the user-facing capture and orchestration layer. In the
current implementation it owns:

- pseudonymous user bootstrapping
- consent initiation
- scan-session initiation
- camera capture
- voice capture
- first-pass on-device signal processing
- local quality evaluation
- result retrieval and rendering

It does not own:

- historical baselines
- long-term persistence
- consent ledger truth
- audit
- alert cooldown or delivery

## Mobile Architecture Summary

### Runtime Shell

Entry point: `mobile/App.tsx`

Current navigation model:

- simple local state machine
- `consent -> scan -> results`

This is important because the app has React Navigation dependencies installed,
but they are not the active runtime navigation model today.

## Mobile Directory Map

### Screens

- `src/screens/ConsentScreen.tsx`
- `src/screens/ScanScreen.tsx`
- `src/screens/ResultsScreen.tsx`

### Components

- `src/components/CameraCapture.tsx`
- `src/components/VoiceCapture.tsx`
- `src/components/QualityGate.tsx`

### Hooks

- `src/hooks/useConsent.ts`
- `src/hooks/useScan.ts`
- `src/hooks/useQualityCheck.ts`

### API

- `src/api/client.ts`

### Signal Processing Utilities

- `src/utils/frameAnalyzer.ts`
- `src/utils/rppgProcessor.ts`
- `src/utils/voiceAnalyzer.ts`
- `src/utils/voiceProcessor.ts`

### Shared Types

- `src/types/index.ts`

## Consent Flow

### `useConsent`

Responsibilities:

- load or create a pseudonymous UUID in AsyncStorage
- fetch remote consent status if available
- fall back to cached consent state if remote fetch fails
- grant consent via API
- expose `hasActiveConsent`

### `ConsentScreen`

Responsibilities:

- present informed-consent copy
- gate progression behind an explicit checkbox
- auto-advance returning users who already have active consent

### Key Data Stored Locally

- OIDC session material in secure storage
- `@pranascan:consent_status`

## API Client And Auth Bootstrap

File: `mobile/src/api/client.ts`

Responsibilities:

- create a configured Axios instance
- attach the OIDC access token acquired through Expo AuthSession
- keep the current auth session in memory
- attach bearer tokens through an interceptor
- wrap consent and scan endpoints in typed helpers

### Important Behavior

- auth bootstrap is handled by `mobile/src/hooks/useOidcAuth.ts`
- `service-core` is the public backend for consent, scans, feedback, reports,
  social connections, streaks, and the planned Vitality Glow feed APIs
- the old FastAPI `/auth/token` bootstrap path is no longer part of the mobile runtime

## Scan Orchestration

### `useScan`

Responsibilities:

- create scan session
- track phase
- submit final payload
- fetch completed result
- centralize scan-related error state

### `ScanScreen`

Responsibilities:

- mount and immediately start the backend session
- show the camera step first
- transition to the voice step when camera capture completes
- merge camera and voice results into a final payload
- submit that payload and move to results

### Current Payload Behavior

The current mobile path is hybrid:

- `frame_data` is captured from Vision Camera centre-ROI RGB means and submitted on the main scan path
- aggregate RGB means are submitted as:
  - `frame_r_mean`
  - `frame_g_mean`
  - `frame_b_mean`
- `voice_jitter_pct`, `voice_shimmer_pct`, `audio_snr_db` come from on-device voice DSP
- camera-derived `hr_bpm`, `hrv_ms`, and `respiratory_rate` are produced server-side from the submitted `frame_data`
- `audio_samples` is intentionally omitted in the current path

That means the backend compatibility paths still exist, but the current mobile
client actively uses the `frame_data` path for camera-derived metrics.

## Camera Pipeline

### `CameraCapture`

Responsibilities:

- request camera permissions
- render a live camera preview using `react-native-vision-camera`
- stream centre-ROI RGB means from the frame processor at 30 FPS in Standard mode and up to 60 FPS in Deep Dive mode
- derive live quality metrics from those RGB samples
- keep a local `FrameSample[]`
- return capture and quality payloads to `ScanScreen`

### Quality Heuristics

Implemented in `frameAnalyzer.ts`:

- `computeLightingScoreFromRgb(sample)`
- `computeMotionScoreFromRgb(previous, current)`
- `computeFaceConfidenceFromRgb(sample, lighting, motion)`
- `buildFrameSampleFromRgb(sample, tMs)`
- `aggregateQualityMetrics(...)`
- `computeOverallQualityScore(...)`

Important detail:

- face detection is currently heuristic, not ML-based
- Deep Dive uses a lighting-and-motion proxy instead of selfie-style face confidence

### Local rPPG Utility

`rppgProcessor.ts` still exists in the mobile repo, but it is not the active
submitted camera path today. The live scan flow sends `frame_data` to the
backend, where POS or morphology processing runs server-side.

Utility algorithm in that module:

1. validate frame count and scan duration
2. upsample to 10 Hz
3. detrend
4. normalize
5. bandpass filter
6. detect peaks
7. compute HR
8. compute HRV
9. compute respiratory proxy

### Camera Output Contract

`CameraCapture` returns:

- `quality`
- `quality_score`
- `frame_data`
- `frame_r_mean`
- `frame_g_mean`
- `frame_b_mean`

`ScanScreen` submits `frame_data` in the main path today.

## Voice Pipeline

### `VoiceCapture`

Responsibilities:

- request microphone permission
- record a 5-second clip using `expo-av`
- update waveform bars from live metering
- extract replay samples
- compute SNR
- run on-device voice DSP

### `voiceAnalyzer.ts`

Responsibilities:

- convert metering dB to amplitude
- build waveform bars
- resample audio
- build fallback samples if replay extraction fails
- compute SNR

### `voiceProcessor.ts`

Responsibilities:

- derive jitter percentage
- derive shimmer percentage
- derive a local SNR estimate
- compute voiced fraction and flags

### Important Behavior

- current mobile flow does on-device voice DSP
- current mobile flow does not send `audio_samples`
- backend still supports `audio_samples` if another client uses that path

## Quality Gate Synchronization

The mobile app mirrors backend quality thresholds in `useQualityCheck.ts`.

This means threshold changes are cross-cutting changes. A new engineer changing
quality policy must update:

- backend config
- backend `quality_gate.py`
- mobile `useQualityCheck.ts`
- UI copy if the behavior is user-visible
- tests on both sides

## Results Rendering

### `ResultsScreen`

Responsibilities:

- fetch a completed session
- render metric cards
- display trend alert copy
- show backend flags

### Important Current Gap

The backend returns more fields than the mobile UI currently models or renders.

Backend response includes:

- vascular-age fields
- anemia-screening fields

Mobile `ScanResult` type does not currently include those fields, and the
current UI ignores them.

## Testing Layout

Mobile tests are organized by feature area:

- consent flow
- camera capture
- voice capture
- API client
- quality gate
- frame analyzer
- rPPG processor
- voice analyzer
- voice processor

These tests are executed in CI with Jest and TypeScript checks.

## Mobile Gotchas

- The app is not currently using React Navigation despite the dependency being installed.
- Token refresh is not implemented.
- Results types lag backend response shape.
- Comments and older docs in the repo may still describe an earlier backend-centric
  signal-processing flow. The current mobile implementation is more edge-first
  than those older docs suggest.
