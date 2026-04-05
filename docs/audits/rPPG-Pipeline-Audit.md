# PranaScan rPPG Pipeline — Implementation Audit Report
**Date:** 2026-04-05  
**Scope:** Prompts 1, 2 & 3 — Vision Camera upgrade, POS algorithm, validation harness, morphology processor, Deep Dive mode, Spring Core scan-type routing

---

## Executive Summary

| Area | Status | Notes |
|---|---|---|
| Vision Camera Frame Processor | ✅ Implemented | 30/60 FPS, RGB worklet, ROI extraction |
| Old JPEG capture removed | ✅ Removed | No `takePictureAsync` references remain |
| POS Algorithm (`rppg_processor.py`) | ✅ Implemented | Full multi-channel POS with bandpass, peak detection, RMSSD |
| `pos_processor.py` wrapper | ✅ Implemented | Backward-compatible alias to `rppg_processor` |
| Validation Harness | ✅ Implemented | `validate_rppg_reference.py` with MAE/RMSE/pass-fail |
| Morphology Processor | ✅ Implemented | APG, a-peak, d-peak, Stiffness Index via `scipy.signal` |
| Deep Dive UI mode | ✅ Implemented | Prompt text, back camera, torch, 60-second duration |
| `ScanType` in Spring Core DTO | ✅ Implemented | `ScanEvaluationRequest` carries `scanType`, routes to grpc |
| gRPC proxy routing | ✅ Implemented | `GrpcIntelligenceServiceGateway` maps `STANDARD`/`DEEP_DIVE` |
| FastAPI routing (POS vs Morphology) | ✅ Implemented | `scan_evaluation_service.py` branches on `scan_type` |
| **Bug — `ScanType.fromValue` null guard** | ⚠️ Bug | `value == null  value.isBlank()` — missing `\|\|` operator |
| CI action versions | ⚠️ Stale | `@v6` used on checkout/setup-python/setup-node/codecov (latest stable is v4) |
| `frameAnalyzer.ts` stale doc comment | ⚠️ Minor | Header still references the old JPEG/expo-camera approach |
| Service-Core build: `ScanEvaluationCommand` | ⚠️ Gap | `request.toCommand()` referenced in controller/gateway but no `.java` source found in repo — may be generated or missing |

---

## Prompt 1 — Vision Camera & POS Upgrade

### ✅ CameraCapture.tsx — Vision Camera Frame Processor
- **`react-native-vision-camera@^4.7.3`** and **`react-native-worklets-core@^1.6.3`** are declared in `package.json`.
- Imports: `Camera`, `runAtTargetFps`, `useCameraDevice`, `useCameraFormat`, `useCameraPermission`, `useFrameProcessor` — all from `react-native-vision-camera`. ✅
- `useFrameProcessor` worklet calls `extractCenterRoiAverage` then `emitTraceSample` via `Worklets.createRunOnJS`. ✅
- `pixelFormat="rgb"` passed to `<Camera>` with `enableBufferCompression={false}`. ✅
- `runAtTargetFps(preferredCameraFps, ...)` correctly throttles the worklet to the target FPS. ✅
- Centre ROI is a **100×100 pixel** region (`ROI_SIZE_PX = 100`) centred in the frame. ✅
- BGR/RGBA platform difference handled: `RGB_LAYOUT = Platform.OS === 'ios' ? 'bgra' : 'rgba'` with channel-swap logic. ✅
- The old JPEG path (`takePictureAsync`) has been fully removed. ✅

### ✅ POS Algorithm — `rppg_processor.py`
- `_extract_pos_waveform` implements the canonical POS projection: `s1 = G − B`, `s2 = −2R + G + B`, then `alpha`-weighted combination. ✅
- Multi-channel detrending applied before projection. ✅
- Butterworth bandpass (0.7–4.0 Hz, order 4) applied after POS. ✅
- Peak detection driven by dominant frequency from the periodogram (no hardcoded distance). ✅
- HR from mean IBI, RMSSD from `np.diff(ibi * 1000)`. ✅
- Respiratory rate estimated from low-frequency BVP envelope (0.1–0.5 Hz). ✅
- **No "green channel only"** code remains. ✅

### ✅ `pos_processor.py` wrapper
- Exists at `service-intelligence/app/services/pos_processor.py`.
- Thin compatibility wrapper that re-exports `process_rgb_traces` → `process_frames`. ✅

---

## Prompt 2 — Validation Harness

### ✅ `validate_rppg_reference.py`
Located at `service-intelligence/scripts/validate_rppg_reference.py`.

| Requirement | Status |
|---|---|
| Accepts `--trace-csv` (t_ms, r_mean, g_mean, b_mean) | ✅ |
| Accepts `--reference-csv` (timestamp_ms, hr_bpm) | ✅ |
| Sliding-window comparison with configurable stride | ✅ |
| MAE and RMSE computed | ✅ |
| `--threshold-bpm` defaulting to 5.0 | ✅ |
| Exit code `0` = pass, `1` = fail | ✅ |
| Optional JSON output via `--output-json` | ✅ |
| Timestamp normalisation by default, opt-out via flag | ✅ |
| Documentation in `docs/setup/rppg-reference-validation.md` | ✅ |

---

## Prompt 3 — Weekly Deep Dive (Contact PPG)

### ✅ `morphology_processor.py`
- Uses `scipy.signal.savgol_filter` to compute the **second derivative (APG)** of the smoothed pulse cycle. ✅
- `_compute_stiffness_index` locates **a-peak** (first systolic maximum) and **d-peak** (late systolic minimum → following maximum pattern) via a state machine traversal of APG extrema. ✅
- **Stiffness Index** = `height_m / delta_t_s`. ✅
- HR and RMSSD derived from peak timestamps as per POS processor. ✅
- `user_height_cm` passed in; `"height_required_for_stiffness_index"` flag emitted if absent. ✅
- Requires min 300 frames / 20 s temporal span / 30 FPS — appropriate for a 60-second scan. ✅

### ✅ ScanScreen.tsx — Deep Dive UI Mode
- Mode selector with `'standard'` / `'deep_dive'` `ScanType` options. ✅
- Deep Dive card description: **"Cover the camera and flash with your thumb for a 60-second contact-PPG scan."** ✅
- `deepDivePrompt` text: **"Cover the camera and flash with your thumb."** ✅
- Height input (`TextInput`) shown only in Deep Dive mode; required before scan starts. ✅
- `scanType` passed to `CameraCapture` and `buildPayload`. ✅
- Deep Dive skips voice step and submits immediately after camera. ✅
- `user_height_cm` included in the payload when `scanType === 'deep_dive'`. ✅

### ✅ CameraCapture.tsx — Deep Dive camera behaviour
- `useCameraDevice('back')` selected when `scanType === 'deep_dive'`. ✅
- `torch={isDeepDive ? 'on' : 'off'}` on `<Camera>`. ✅
- `DEEP_DIVE_SCAN_DURATION_MS = 60_000` (60 seconds). ✅
- `DEEP_DIVE_CAMERA_FPS = 60`; gracefully falls back to 30 if device doesn't support 60. ✅
- When `isDeepDive`, `extractCenterRoiAverage(frame, true)` samples the **Red channel only**. ✅
- In-scan instruction text: **"Cover the camera and flash with your thumb."** ✅

### ✅ Spring Core `ScanEvaluationRequest` — `scanType` field
- `ScanEvaluationRequest` record contains `ScanType scanType`. ✅
- `ScanType` enum has `STANDARD` and `DEEP_DIVE` values. ✅
- `toCommand()` maps `scanType` into the command object. ✅
- `GrpcIntelligenceServiceGateway.toGrpcScanType()` maps `DEEP_DIVE → SCAN_TYPE_DEEP_DIVE`. ✅
- `user_height_cm` field present on the DTO and forwarded via gRPC builder. ✅

### ✅ FastAPI Routing (POS vs Morphology)
- `_scan_result_submit_from_proto` in `grpc_runtime.py` calls `_scan_type_from_proto` which maps `SCAN_TYPE_DEEP_DIVE → ScanType.DEEP_DIVE`. ✅
- `scan_evaluation_service._apply_server_side_rppg` branches on `submission.scan_type == "deep_dive"` → calls `process_morphology_frames`; otherwise calls `process_frames` (POS). ✅

---

## Issues Found

### 🐛 Bug — `ScanType.java` missing `||` operator (line 22)

**File:** `service-core/src/main/java/com/pranapulse/core/scan/domain/ScanType.java`

```java
// CURRENT (broken) — will not compile
if (value == null  value.isBlank()) {

// SHOULD BE
if (value == null || value.isBlank()) {
```

This is a **compile-time syntax error**. The Java build will fail unless this was introduced by a display/copy artifact from the terminal read. **Verify and fix before merging.**

---

### ⚠️ Gap — `ScanEvaluationCommand` source not found in repo

`ScanEvaluationRequest.toCommand()` and `GrpcIntelligenceServiceGateway.evaluate(ScanEvaluationCommand command)` both reference a `ScanEvaluationCommand` type that has no `.java` source file under `service-core/src/main/java/`. It could be:
- A compiled-only class checked in under `target/` (bad practice), or
- A record defined inline inside another file not yet read.

**Action required:** Confirm the class exists or create it. The DTO-to-command mapping in `ScanEvaluationRequest.toCommand()` already contains the full field list, so it's likely a missing top-level record file.

---

### ⚠️ CI Workflow — Action version pins are non-existent (`@v6`)

**File:** `.github/workflows/ci.yml`

All four actions reference `@v6`, which does **not exist** as of April 2026:

| Action | Used | Latest Stable |
|---|---|---|
| `actions/checkout` | `@v6` | `@v4` |
| `actions/setup-python` | `@v6` | `@v4` |
| `actions/setup-node` | `@v6` | `@v4` |
| `codecov/codecov-action` | `@v6` | `@v4` |

These will cause CI to fail with "version not found". Fix to `@v4` across the board.

---

### ⚠️ Minor — `frameAnalyzer.ts` stale JSDoc header

The top-of-file comment block still says:

> *"expo-camera v15 (SDK 51) does not expose per-pixel access in JS. We capture low-quality JPEG frames via takePictureAsync…"*

This is the **old approach** — the file now supplies RGB-trace utilities that feed the Vision Camera worklet. The implementation itself is correct; only the module-level documentation is stale.

---

## Summary of Fixes Required

| Priority | File | Fix |
|---|---|---|
| 🔴 **P0** | `ScanType.java` | Add missing `\|\|` on line 22 |
| 🔴 **P0** | `ScanEvaluationCommand.java` | Confirm file exists or create it |
| 🟡 **P1** | `.github/workflows/ci.yml` | Change all `@v6` → `@v4` |
| 🟢 **P2** | `frameAnalyzer.ts` | Update stale JSDoc header |
