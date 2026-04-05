# Architectural Audit — PranaScan MVP

**Date:** 2026-04-05
**Scope:** Validate implementation against the Hybrid PPG Wellness Strategy
**Auditor:** GitHub Copilot (AI-assisted)

---

## Checkpoint 1: Acquisition Integrity (Mobile Layer)

**Files audited:**
- `mobile/src/components/CameraCapture.tsx` (644 lines)
- `mobile/src/utils/frameAnalyzer.ts` (374 lines)
- `mobile/src/types/index.ts` (170 lines)

---

### 1.1 FPS Mode Toggling (Standard 30 FPS vs Deep Dive 60 FPS)

**Verdict: ✅ PASS — correctly implemented with graceful fallback**

| Property | Standard (Facial rPPG) | Deep Dive (Contact PPG) |
|---|---|---|
| Camera | `front` | `back` |
| Target FPS | 30 | 60 (if device supports) |
| Fallback FPS | — | 30 (automatic) |
| Duration | 30 seconds | 60 seconds |
| Torch | `off` | `on` |
| ROI mode | Full RGB | Red-only (`redOnly=true`) |

**Evidence (CameraCapture.tsx lines 141–148):**
```typescript
const device = useCameraDevice(scanType === 'deep_dive' ? 'back' : 'front');
const preferredCameraFps =
  scanType === 'deep_dive' && device?.formats.some((format) => format.maxFps >= DEEP_DIVE_CAMERA_FPS)
    ? DEEP_DIVE_CAMERA_FPS
    : STANDARD_CAMERA_FPS;
```

The code probes `device.formats` for 60 FPS support before requesting it. If no format supports ≥60 FPS, it gracefully falls back to 30 FPS. The `useCameraFormat` hook then selects the best matching format. The `<Camera>` component receives `fps={preferredCameraFps}` directly (line 401).

**Strength:** The fallback is device-aware, not hardcoded. Low-end Android devices that lack 60 FPS back-camera support will still produce a valid (albeit lower-resolution) contact-PPG trace.

---

### 1.2 frameProcessor Worklet — `runAtTargetFps` Usage

**Verdict: ⚠️ DEBT — functional but subtle timing concern**

**Evidence (CameraCapture.tsx lines 292–309):**
```typescript
const frameProcessor = useFrameProcessor(
  (frame) => {
    'worklet';
    if (!isScanning) { return; }
    runAtTargetFps(preferredCameraFps, () => {
      'worklet';
      const roiAverage = extractCenterRoiAverage(frame, isDeepDive);
      if (!roiAverage) { return; }
      emitTraceSample(roiAverage.rMean, roiAverage.gMean, roiAverage.bMean);
    });
  },
  [emitTraceSample, isScanning, isDeepDive, preferredCameraFps],
);
```

**What works:**
- `runAtTargetFps` correctly throttles the worklet callback to the target FPS.
- The `'worklet'` directive is present on both the outer and inner callbacks — required by react-native-vision-camera's Reanimated worklet bridge.
- `extractCenterRoiAverage` runs inside the worklet, so pixel reads happen on the camera thread without a JS-bridge round-trip.
- `emitTraceSample` uses `Worklets.createRunOnJS()` to safely bridge back to the JS thread.

**Concern (DEBT):**
- `runAtTargetFps(preferredCameraFps, ...)` means the throttle target equals the camera's native FPS. This is effectively a no-op throttle — every frame will be processed. This is **correct for signal integrity** (no deliberate downsampling), but the naming is misleading. If the camera delivers frames faster than `preferredCameraFps` (e.g., some devices burst to 33 FPS when targeting 30), the throttle will silently drop the excess. This is acceptable but undocumented.
- When Deep Dive falls back to 30 FPS (device doesn't support 60), `preferredCameraFps` is 30, so both the camera and the throttle run at 30. The morphology processor server-side (`morphology_processor.py`) expects `TARGET_FS = 60.0` and resamples up from native rate, so this path is handled.

| Issue | Severity | Detail |
|---|---|---|
| `runAtTargetFps` is a no-op when target == camera FPS | **DEBT** | Not a bug — but should be documented. Consider removing the throttle wrapper when target equals camera FPS to avoid confusion. |

---

### 1.3 Dropped-Frame Detection & HRV Aliasing Guards

**Verdict: 🔴 FEATURE_GAP — no dropped-frame detection exists on-device**

**Analysis:**

There is **no mechanism** in CameraCapture.tsx to detect or compensate for dropped frames. The current pipeline works as follows:

1. Each frame processed by the worklet gets a timestamp via `Date.now() - scanStartRef.current` (line 257 in `handleTraceSample`).
2. Frames are pushed to `frameDataRef.current` unconditionally.
3. The array is sent as-is to the backend.

**Risks:**

| Risk | Impact | Likelihood |
|---|---|---|
| Thermal throttling on low-end Android reduces actual FPS mid-scan | Irregular timestamp spacing → aliased HRV | Medium-High |
| GC pauses on JS thread delay `handleTraceSample` | Timestamps jitter by 10–50ms | Medium |
| Camera frame drops under load (background apps, OS interrupts) | Missing samples in the trace | Medium |

**Mitigating factors already present:**
- The server-side processors (`rppg_processor.py` line 176, `morphology_processor.py` line 121) **do resample** the irregular trace onto a regular timeline via `np.interp`. This means irregular spacing is partially handled.
- The server validates `timestamps_s` ordering and rejects traces with `diffs <= 0`.
- The server checks minimum temporal span (`MIN_TEMPORAL_SPAN_S = 8s` for standard, `20s` for morphology).

**What's missing:**

| Gap | Severity | Recommendation |
|---|---|---|
| No on-device frame-drop counter or warning | **FEATURE_GAP** | Add a dropped-frame heuristic: if `elapsed_since_last_frame > 2 * expected_interval`, increment a counter. Surface as a quality flag (`frame_drops_detected`) when count exceeds threshold. |
| No timestamp jitter smoothing on-device | **FEATURE_GAP** | Consider using `frame.timestamp` (nanosecond hardware timestamp from Vision Camera) instead of `Date.now()` to eliminate JS-thread jitter. This is the single highest-impact improvement for HRV accuracy. |
| No client-side effective-FPS metric sent to backend | **DEBT** | Compute `actual_fps = frame_count / scan_duration` and include it in the payload so the server can flag low-FPS scans. |

---

### 1.4 ROI Extraction — RGBA vs BGRA Pixel Layout Handling

**Verdict: ⚠️ DEBT — partially correct, with a mismatch concern**

**Evidence (CameraCapture.tsx lines 49, 83, 112–114):**
```typescript
const RGB_LAYOUT: 'rgba' | 'bgra' = Platform.OS === 'ios' ? 'bgra' : 'rgba';

// In extractCenterRoiAverage worklet:
if (frame.pixelFormat !== 'rgb' || ...) { return null; }
// ...
const r = RGB_LAYOUT === 'bgra' ? data[offset + 2] : data[offset];
const g = data[offset + 1];
const b = RGB_LAYOUT === 'bgra' ? data[offset] : data[offset + 2];
```

**What works:**
- Platform-aware layout detection: iOS uses BGRA, Android uses RGBA.
- The channel extraction logic correctly swaps R and B indices for BGRA.
- Green channel (offset + 1) is always in position 1 for both layouts — correct.
- The `bytesPerPixel` calculation (`Math.max(3, Math.round(frame.bytesPerRow / frame.width))`) handles row padding correctly.

**Concerns:**

| Issue | Severity | Detail |
|---|---|---|
| `pixelFormat` guard checks for `'rgb'` but the Camera is configured with `pixelFormat="rgb"` while the actual layout handling assumes `rgba`/`bgra` (4 bytes per pixel) | **DEBT** | Vision Camera's `pixelFormat="rgb"` on iOS actually delivers BGRA buffers in practice. The `bytesPerRow / width` calculation self-corrects to 4 bytes per pixel, so this works — but the `pixelFormat !== 'rgb'` guard string is fragile. If a future Vision Camera version changes the reported `pixelFormat` string, all frames would be silently discarded (return null). Add a fallback or log. |
| `RGB_LAYOUT` is a module-level constant, not derived from `frame.pixelFormat` at runtime | **DEBT** | If a device reports a different format than expected for its platform, the channel swap would be wrong. Safer to derive layout from the frame metadata. |
| Deep Dive `redOnly` mode sets all three channels to the red value | **PASS** | When `redOnly=true`, `rTotal/gTotal/bTotal` all receive the red channel value. This is intentional — contact PPG uses only the red-derived signal. The green/blue values are placeholders for the FrameSample struct. Correct for the morphology pipeline which only reads `frame.r_mean`. |

---

### 1.5 Additional Observations

| Item | Severity | Detail |
|---|---|---|
| ROI size is fixed at 100×100 px regardless of resolution | **DEBT** | At 1280×720, a 100px ROI covers ~1.4% of the frame. This is sufficient for forehead POS but may be suboptimal for thumb contact (where the entire frame is the signal). Consider making ROI size proportional to frame dimensions for Deep Dive. |
| `AUDIO_SNR_DEFAULT = 20.0` is hardcoded for all camera results | **DEBT** | Camera capture has no microphone access. The default 20.0 dB is injected as the audio_snr_db value. This is a placeholder that could inflate the quality gate score. Should be `null` and handled server-side. |
| `toArrayBuffer()` called on every frame in the worklet | **DEBT** | This allocates a new buffer per frame. At 30 FPS that's 30 allocations/second. Not a correctness issue but could cause GC pressure on low-end devices, contributing to the timestamp jitter described in §1.3. |
| Legacy JPEG functions retained in `frameAnalyzer.ts` | **DEBT** | Lines 103–200+ contain deprecated `computeLightingScore`, `computeMotionScore`, `buildFrameSample`, `computeFaceConfidence` functions. Marked `@deprecated` but still compiled into the bundle. Dead code that should be removed. |

---

### Checkpoint 1 Summary Table

| ID | Finding | Severity | File | Line(s) |
|---|---|---|---|---|
| ACQ-01 | FPS toggling between 30/60 with device-aware fallback | ✅ PASS | CameraCapture.tsx | 141–148 |
| ACQ-02 | `runAtTargetFps` is functional but acts as no-op throttle | **DEBT** | CameraCapture.tsx | 300 |
| ACQ-03 | No dropped-frame detection on-device | **FEATURE_GAP** | CameraCapture.tsx | 253–260 |
| ACQ-04 | No hardware timestamp usage — `Date.now()` adds JS-thread jitter to HRV | **FEATURE_GAP** | CameraCapture.tsx | 257 |
| ACQ-05 | `pixelFormat` guard string `'rgb'` is fragile | **DEBT** | CameraCapture.tsx | 83 |
| ACQ-06 | `RGB_LAYOUT` is compile-time, not runtime-derived from frame | **DEBT** | CameraCapture.tsx | 49 |
| ACQ-07 | RGBA/BGRA channel extraction logic is correct | ✅ PASS | CameraCapture.tsx | 112–114 |
| ACQ-08 | Deep Dive `redOnly` mode correctly isolates red channel | ✅ PASS | CameraCapture.tsx | 115–118 |
| ACQ-09 | Fixed 100×100 ROI regardless of resolution/scan type | **DEBT** | CameraCapture.tsx | 93–94 |
| ACQ-10 | `AUDIO_SNR_DEFAULT=20.0` hardcoded placeholder | **DEBT** | CameraCapture.tsx | 48 |
| ACQ-11 | Per-frame `toArrayBuffer()` GC pressure | **DEBT** | CameraCapture.tsx | 101 |
| ACQ-12 | Legacy JPEG functions still in bundle | **DEBT** | frameAnalyzer.ts | 103–200+ |
| ACQ-13 | No client-side effective-FPS metric in payload | **DEBT** | CameraCapture.tsx | — |

**Blockers: 0 | Feature Gaps: 2 | Debt: 9 | Pass: 3**

> **Highest-priority recommendation:** Replace `Date.now()` with Vision Camera's hardware `frame.timestamp` for timestamping. This single change would eliminate JS-thread jitter from HRV inter-beat interval measurements — the most accuracy-sensitive metric in the entire pipeline.

---

## Checkpoint 2: Algorithmic Correctness (POS + Morphology)

**Clarification on the cited literature:** Gerard de Haan and Vincent Jeanne's *Robust pulse-rate from chrominance-based rPPG* was published in **October 2013** and describes the **CHROM** method, not POS. The **POS** method ("Plane-Orthogonal-to-Skin") was introduced later by Wang et al., first online in **2016** and published in **July 2017**. The audit below therefore checks the implementation against both: the cited **2013 CHROM paper** and the **2017 POS paper** that matches the code comments.

---

### 2.1 POS Projection Math

**Verdict: 🔴 BLOCKER — `rppg_processor.py` is not paper-correct POS, and it is not CHROM either**

**Evidence in code:**
- `extract_bvp()` detrends the entire RGB trace before projection (`rppg_processor.py` lines 181–183).
- `_extract_pos_waveform()` then computes `channel_mean = np.mean(rgb, axis=0)` on that detrended signal and divides by it (`rppg_processor.py` lines 247–250).
- The code uses the POS-style projection axes `G-B` and `G+B-2R`, but only once over the full trace (`rppg_processor.py` lines 252–257).

**Why this is a blocker:**
- POS requires **temporal normalization on the raw RGB trace inside a sliding window**, then projection, `alpha` tuning, and **overlap-add** of each window. The current code performs a **single global pass** with no sliding window and no overlap-add.
- After `signal.detrend`, each channel mean is approximately zero. Dividing by that near-zero mean is not the POS normalization step; it makes the normalization depend on floating-point residue rather than a meaningful skin-tone baseline.
- If the intent was to implement the cited de Haan & Jeanne **2013** paper, that paper is **CHROM**, which uses a different chrominance formulation after skin-tone standardization/white balancing. This code does not implement that path either.

**Conclusion:** The current processor should not be described as "paper-correct POS" or "per de Haan & Jeanne 2013." It is a hybrid approximation with a broken normalization order.

---

### 2.2 Cardiac Band Filter

**Verdict: No issue filed**

- `HR_LOW_HZ = 0.7` and `HR_HIGH_HZ = 4.0` correspond to **42–240 BPM** (`rppg_processor.py` lines 67–68).
- The implementation uses a **4th-order Butterworth** and `signal.filtfilt`, so the filter is broad enough for adult cardiac-band capture and zero-phase in application (`rppg_processor.py` lines 260–277).
- This does **not** rescue the projection/normalization blocker above, but the band edges themselves are reasonable.

---

### 2.3 APG Source Path

**Verdict: ⚠️ DEBT — runtime APG is derived from real contact-PPG, but landmark extraction is still heuristic**

**What the code actually does:**
- The Deep Dive server path passes real `submission.frame_data` into `process_morphology_frames()` (`scan_evaluation_service.py` lines 83–99).
- `_prepare_signal()` reads the recorded `frame.r_mean` trace directly and resamples/filter it into a pulse waveform (`morphology_processor.py` lines 98–130).
- `_compute_stiffness_index()` computes the second derivative using `savgol_filter(..., deriv=2)` on an averaged pulse cycle (`morphology_processor.py` lines 215–222).

**Audit call:**
- There is **no production synthetic waveform fallback** in `morphology_processor.py`.
- However, the APG is computed from an **averaged, resampled 200-point template** (`morphology_processor.py` lines 178–201), and the `a/b/c/d` landmarks are assigned by a **hard-coded extrema state machine** (`morphology_processor.py` lines 224–247).
- So the runtime path is using real contact-PPG data, but the morphology extraction is still a heuristic surrogate rather than a validated beat-level fiducial detector.

---

### 2.4 Morphology Validation Surface

**Verdict: 🟠 FEATURE_GAP — morphology correctness is only regression-tested on synthetic waveforms**

**Evidence:**
- `tests/test_morphology_processor.py` generates `_synthetic_contact_frames()` from Gaussian-like systolic/reflected/diastolic components (`test_morphology_processor.py` lines 11–37).
- All positive-path morphology assertions (`stiffness_index is not None`, HR near 66 BPM) use those synthetic frames (`test_morphology_processor.py` lines 40–55).

**Why this matters:**
- The runtime path does use real recorded contact-PPG.
- But the repo currently contains **no recorded thumb-contact PPG fixtures** and **no gold-standard stiffness-index comparison** that exercises the APG/SI logic on real-world data.
- That means the evidence base for morphology correctness is synthetic only.

---

### 2.5 Stiffness Index Validity

**Verdict: 🔴 BLOCKER — `height / delta_t` is not physiologically valid with the current `delta_t` definition**

**What the literature defines:**
- The classical PPG **stiffness index (SI)** is body height divided by the **time between the systolic peak and the diastolic/reflected peak** of the original digital volume pulse.
- APG/SDPPG literature treats the **a, b, c, d, e waves** as second-derivative landmarks and typically uses **amplitude ratios** such as `b/a`, `c/a`, `d/a`, `e/a`, or an aging index derived from those ratios.

**What the code computes instead:**
- `_compute_stiffness_index()` finds APG extrema, labels the first positive extremum as `a`, then walks a heuristic max/min sequence until it assigns a later negative extremum as `d` (`morphology_processor.py` lines 224–247).
- It then computes `delta_t_s = (d_index - a_index) / cycle_fs` and returns `height_m / delta_t_s` (`morphology_processor.py` lines 252–257).

**Why this is a blocker:**
- The numerator `height` is only physiologically meaningful for classical SI when the denominator is the **systolic-to-reflected-wave transit time** on the original PPG/DVP contour.
- The current denominator is an **APG a-to-d interval on an averaged second-derivative waveform**, which is a different construct and not the standard SI definition.
- In other words, the exported field named `stiffness_index` is not literature-grounded SI as implemented today.

---

### Checkpoint 2 Summary Table

| ID | Finding | Severity | File | Line(s) |
|---|---|---|---|---|
| ALG-01 | Claimed POS implementation is not faithful to published POS/CHROM processing | **BLOCKER** | `rppg_processor.py` | 181–183, 247–257 |
| ALG-02 | Detrend-before-normalize divides by near-zero channel means | **BLOCKER** | `rppg_processor.py` | 181–183, 247–250 |
| ALG-03 | APG is computed from real contact-PPG at runtime, but only via averaged-cycle heuristic landmarking | **DEBT** | `morphology_processor.py` | 178–257 |
| ALG-04 | Morphology regression coverage is synthetic-only; no real thumb-contact fixture/gold reference in repo | **FEATURE_GAP** | `test_morphology_processor.py` | 11–55 |
| ALG-05 | `stiffness_index` uses APG `a→d` timing instead of classical DVP systolic→reflected-wave timing | **BLOCKER** | `morphology_processor.py` | 224–257 |

**Blockers: 3 | Feature Gaps: 1 | Debt: 1**

---

### Sources

- [de Haan & Jeanne, *Robust pulse-rate from chrominance-based rPPG* (IEEE TBME, 2013)](https://research.tue.nl/nl/publications/robust-pulse-rate-from-chrominance-based-rppg/)
- [Wang et al., *Algorithmic principles of remote-PPG* (early online 2016; published July 1, 2017)](https://research.tue.nl/en/publications/algorithmic-principles-of-remote-ppg/)
- [Wu & Chen, *Calculation of an Improved Stiffness Index Using Decomposed Radial Pulse and Digital Volume Pulse Signals* (2022)](https://pmc.ncbi.nlm.nih.gov/articles/PMC9694699/)
- [Takazawa et al., *Vascular age estimated by the second derivative of photoplethysmogram* (1999)](https://www.jstage.jst.go.jp/article/jat1973/26/11-12/26_11-12_313/_article)

---

## Checkpoint 3: Data Contract & Proxy Trace (`frame_data`)

**Trace audited:** `ScanScreen.tsx` → mobile API client → `ScanSessionController` / `ScanEvaluationRequest` → `GrpcIntelligenceServiceGateway` → `grpc_runtime.py` → `scan_evaluation_service.py`

---

### 3.1 End-to-End Trace Result

**Verdict: No issue filed**

For the current happy path, `frame_data` is forwarded end-to-end without any explicit truncation or downsampling:

- Mobile capture appends every sampled frame into `frameDataRef.current` and forwards the collected array unchanged on completion (`CameraCapture.tsx` lines 203, 230, 245–259, 300–306).
- `ScanScreen.buildPayload()` copies `capturedCameraResult.frame_data` directly into the request body (`ScanScreen.tsx` lines 64–90).
- The mobile API client sends that payload verbatim in the `PUT /scans/sessions/{sessionId}/complete` call (`client.ts` lines 126–135).
- Spring binds `frame_data` to `frameData`, validates it, and maps each element 1:1 into `ScanEvaluationCommand.FrameSample` (`ScanEvaluationRequest.java` lines 16–18, 44–58, 80–86).
- The gRPC gateway maps each Java frame 1:1 into protobuf `FrameSample` (`GrpcIntelligenceServiceGateway.java` lines 49–58).
- Python reconstructs each protobuf frame 1:1 into `FrameSampleSchema`, then into runtime `FrameSample` objects (`grpc_runtime.py` lines 53–84; `scan_evaluation_service.py` lines 80–85).

There is no evidence in this path of `slice`, `subList`, sampling, or payload trimming applied to `frame_data`.

---

### 3.2 Deep Dive Reuses an RGB Contract for a Red-Only Signal

**Verdict: ⚠️ DEBT — the shared `FrameSample` schema is mode-dependent and semantically overloaded**

**Evidence:**
- `FrameSample` is defined everywhere as `{t_ms, r_mean, g_mean, b_mean}` / `FrameSample { t_ms, r_mean, g_mean, b_mean }` (`mobile/src/types/index.ts` lines 142–146; `scan_intelligence.proto` lines 19–24; `scan.py` lines 8–14).
- In Deep Dive mode, the mobile capture path intentionally writes the red value into all three channels: `gTotal += redOnly ? redOnlyValue : g` and `bTotal += redOnly ? redOnlyValue : b` (`CameraCapture.tsx` lines 117–119).

**Why this matters:**
- The transport contract claims RGB means, but in Deep Dive only `r_mean` is a real channel measurement.
- The current morphology pipeline is safe because it only reads `frame.r_mean`.
- Any future downstream consumer that assumes `g_mean` and `b_mean` are true green/blue values will silently read fabricated data.

**Recommendation:** Either split the schema by scan type (`RgbFrameSample` vs `ContactPpgSample`) or explicitly document in the contract that Deep Dive sends red duplicated into all channels.

---

### 3.3 `flags` Vocabulary Is Inconsistent Across Layers

**Verdict: ⚠️ DEBT — mobile/public contracts allow values that Python ingress rejects**

**Evidence:**
- The mobile `QualityFlag` union includes server-side processing flags such as `low_signal_quality`, `height_required_for_stiffness_index`, `insufficient_cycles_for_morphology`, and `morphology_peaks_not_found` (`mobile/src/types/index.ts` lines 56–71).
- Spring and protobuf accept `flags` as unconstrained strings (`ScanEvaluationRequest.java` line 32; `scan_intelligence.proto` line 45).
- Python ingress restricts request `flags` to a smaller whitelist and rejects anything else (`scan.py` lines 69–88).

**Why this matters:**
- The current UI only emits quality-gate flags from `evaluateQuality()`, so the present app flow stays inside the Python whitelist.
- But the declared cross-layer schema is inconsistent: a caller following the mobile type definition could legally send a value that the Python service rejects.
- Because `_scan_result_submit_from_proto()` does not catch Pydantic validation errors (`grpc_runtime.py` lines 39–40), such a mismatch would surface as an internal service failure rather than a clean `INVALID_ARGUMENT`.

**Recommendation:** Define a single shared request-flag enum across mobile, Spring, protobuf comments, and Python validation, or stop validating request `flags` against a stricter list than the upstream contracts declare.

---

### 3.4 Max `frame_data` Size by Layer

**Verdict: 🟠 FEATURE_GAP — the element-count cap exists, but the transport-size contract is not explicitly specified end-to-end**

| Layer | Effective / explicit limit | Evidence |
|---|---|---|
| Mobile capture | No hard array cap in code. Effective count is duration × target FPS: ~900 frames for Standard (30 s × 30 FPS), ~3600 for Deep Dive (60 s × 60 FPS), with up to ~200 ms timer slop from the countdown interval. | `CameraCapture.tsx` lines 40–44, 151, 300, 325–330 |
| Mobile HTTP client | No request-body size cap configured in code; only a `15_000 ms` timeout. | `client.ts` lines 27–30 |
| Spring REST ingress | `@Size(max = 4000)` on `frameData`. This is the first explicit element-count guard in the public API. | `ScanEvaluationRequest.java` line 18 |
| Protobuf / gRPC request schema | No count cap in `.proto`; `repeated FrameSample frame_data = 1`. | `scan_intelligence.proto` line 27 |
| service-core gRPC client | No message-size override configured on the `ManagedChannelBuilder`. | `IntelligenceServiceConfig.java` lines 17–22 |
| service-intelligence gRPC server | No message-size override configured on `grpc.aio.server(...)`. | `grpc_runtime.py` lines 147–159 |
| Python domain schema | `max_length=4000` on `frame_data`, mirroring Spring. | `scan.py` lines 37–41 |

**Measured payload sizes (local measurement):**
- 3600-frame protobuf request: ~136.8 KB
- 4000-frame protobuf request: ~152.1 KB
- 4000-frame JSON request body: ~255.6 KB

**Interpretation:**
- The current Standard and Deep Dive capture modes stay comfortably below the explicit 4000-frame cap.
- The repo does **not** define an end-to-end byte-size budget for `frame_data`; it defines only an element-count budget in Spring and Pydantic.
- Because the mobile layer and gRPC transport do not share a formal max-frame constant, any future increase in scan duration or FPS could break at REST validation without any compile-time signal.

**Recommendation:** Promote `4000` into a documented shared contract constant and add a client-side guard/assertion for `frame_data.length`.

---

### Checkpoint 3 Summary Table

| ID | Finding | Severity | File | Line(s) |
|---|---|---|---|---|
| DCT-01 | No transport-layer downsampling or truncation found in the current `frame_data` path | — | — | — |
| DCT-02 | Deep Dive uses red-only samples but still populates `g_mean`/`b_mean`, overloading the RGB contract | **DEBT** | `CameraCapture.tsx` | 117–119 |
| DCT-03 | `flags` schema differs across mobile types, Spring/proto, and Python validation | **DEBT** | `mobile/src/types/index.ts`, `scan.py` | 56–71; 69–88 |
| DCT-04 | No explicit repo-wide transport-size contract; only Spring/Pydantic cap `frame_data` at 4000 items | **FEATURE_GAP** | `ScanEvaluationRequest.java`, `scan.py` | 18; 37–41 |

**Blockers: 0 | Feature Gaps: 1 | Debt: 2**

---

## Checkpoint 4: Wizard-of-Oz / Scaffolding Gap Analysis

**Scope audited:** `vitals_extraction.py`, `vascular_age.py`, `anemia_screen.py`, `skin_tone.py`, plus any fallback path in `scan_evaluation_service.py` that bypasses the normal signal pipeline.

---

### 4.1 `vitals_extraction.py` — Media Bytes to HR/HRV/SpO2

**Verdict: 🔴 BLOCKER — raw-media vitals extraction is explicit scaffolding, not real physiological extraction**

**Answer to the SpO2 question:** `spo2` is **not** computed from a real red/infrared ratio-of-ratios. There is **no IR channel** anywhere in this module.

**Evidence in code:**
- The module states that the stack does **not yet decode raw image/video bytes into per-frame RGB summaries** and instead derives a **stable synthetic rPPG waveform** from the media payload (`vitals_extraction.py` lines 31–35).
- `extract_vitals_from_media()` converts the byte payload into a NumPy array, builds **synthetic frame samples**, runs the regular rPPG processor on them, and then falls back to `_fallback_heart_rate()` / `_fallback_hrv()` if needed (`vitals_extraction.py` lines 40–46).
- `_build_synthetic_frame_samples()` uses `SYNTHETIC_FPS = 7.5`, `SYNTHETIC_DURATION_S = 12.0`, SHA-256-seeded RNG, sinusoid/harmonic synthesis, and byte-texture interpolation to fabricate an RGB waveform (`vitals_extraction.py` lines 13–15, 55–103).
- `_estimate_spo2()` uses a **red/blue mean ratio**, payload standard-deviation “stability,” and an rPPG quality bonus to synthesize an SpO2-like value (`vitals_extraction.py` lines 117–128).

**Why this is a blocker:**
- SpO2 estimation requires a physically meaningful optical model and typically a red/IR pulsatile ratio-of-ratios. This implementation has neither.
- The output is deterministic and bounded, but it is still derived from **payload-byte statistics plus synthetic waveform scaffolding**, not from a real photoplethysmography or oximetry pipeline.

**Tests reinforce the scaffolding intent:** `test_vitals_extraction.py` only checks that the output is deterministic and within broad bounds (`test_vitals_extraction.py` lines 6–15).

---

### 4.2 Raw-Media Fallback Bypasses the Real Signal Pipeline

**Verdict: 🔴 BLOCKER — the internal media-bytes path can inject scaffolded vitals into the main evaluation flow**

**Evidence in code:**
- `grpc_runtime.py` calls `extract_vitals_from_media(media_bytes)` whenever `image_bytes` or `video_bytes` is present (`grpc_runtime.py` lines 27–40).
- `scan_evaluation_service._apply_extracted_vitals()` then writes `spo2` directly and backfills `hr_bpm` / `hrv_ms` if those were missing from the submission (`scan_evaluation_service.py` lines 141–156).

**Why this matters:**
- The normal signal path is `frame_data -> rPPG/morphology processors`.
- The media-bytes path is different: it can still populate vitals even though the raw media is not actually decoded into real per-frame physiological features.
- That is a true Wizard-of-Oz bypass still living inside the production service boundary.

---

### 4.3 `vascular_age.py` — Population Brackets vs Pulse-Wave Morphology

**Verdict: 🟠 FEATURE_GAP — morphology-based vascular-age modeling is not implemented**

**Answer to the vascular-age question:** yes, the current implementation is a **population-bracket lookup from HR + HRV**, not a real pulse-wave morphology model.

**Evidence in code:**
- The function signature accepts only `hr_bpm` and `hrv_ms` (`vascular_age.py` lines 53–56).
- The model uses hardcoded `_BRACKETS` of age midpoint, HR mean/std, and HRV mean/std (`vascular_age.py` lines 22–33).
- It computes a standardized distance to each bracket and returns the best matching midpoint with confidence `1 / (1 + distance)` (`vascular_age.py` lines 73–97).
- `scan_evaluation_service.py` calls it with only `processed_submission.hr_bpm` and `processed_submission.hrv_ms` (`scan_evaluation_service.py` lines 46–49).

**Why this is a feature gap:**
- No pulse-wave contour, APG, reflected-wave timing, stiffness index, or any other morphology feature enters this estimator.
- The intended “vascular age from pulse-wave morphology” capability is therefore still missing.

**Tests reinforce this:** `test_vascular_age.py` asserts mapping to predefined age brackets from HR/HRV inputs, not from waveform features (`test_vascular_age.py` lines 19–56).

---

### 4.4 `anemia_screen.py` — Conjunctival Imaging vs RGB Channel Ratios

**Verdict: 🟠 FEATURE_GAP — the Hb proxy is not based on real conjunctival imaging**

**Answer to the anemia question:** it is **just RGB channel ratios plus quality gating**, not a conjunctival imaging model.

**Evidence in code:**
- The module explicitly says **no image data ever reaches this function**; it operates only on scalar means (`anemia_screen.py` lines 14–15).
- `screen_anemia()` receives `r_mean`, `g_mean`, `b_mean`, `lighting_score`, and `motion_score` and computes `hb_proxy_score` from `r_fraction = r / (r + g + b)` with fixed thresholds (`anemia_screen.py` lines 41–47, 91–126).
- The call site in `scan_evaluation_service.py` passes `frame_r_mean`, `frame_g_mean`, and `frame_b_mean` from the processed submission, not a conjunctival ROI or image crop (`scan_evaluation_service.py` lines 50–58).

**Why this is a feature gap:**
- There is no conjunctival localization, no segmentation, no pallor analysis on image regions, and no computer-vision model.
- The current implementation is a confidence-gated color heuristic over aggregate frame means.

**Tests reinforce this:** `test_anemia_screen.py` codifies “high red => high score” and “low red => low score” behavior directly (`test_anemia_screen.py` lines 27–52, 84–113).

---

### 4.5 `skin_tone.py` — Real ITA Estimation, Placeholder Calibration Factors

**Verdict: ⚠️ DEBT — skin-tone estimation is real enough, but the correction table is an MVP approximation**

**Answer to the skin-tone question:** the calibration factors are **not** derived from a real checked-in Diverse-rPPG dataset. They are hardcoded placeholder approximations.

**Evidence in code:**
- The module says the calibration is a **“linear approximation for MVP”** and that full production calibration still requires the **licensed Diverse-rPPG 2026 dataset** plus multi-channel POS/CHROM processing (`skin_tone.py` lines 25–35).
- `_CALIBRATION` is a hand-authored table of `hr_factor`, `quality_weight`, and `confidence` keyed by Fitzpatrick type (`skin_tone.py` lines 84–98).
- `apply_skin_tone_calibration()` directly multiplies HR/HRV and shifts quality score using those constants (`skin_tone.py` lines 262–279).
- `estimate_from_frames()` falls back to `Type 4, ITA 15.0` when no frames are provided (`skin_tone.py` lines 208–215).

**Why this is debt rather than a blocker:**
- The ITA / Fitzpatrick estimation path is a real deterministic color-space transform from RGB means, not random scaffolding.
- The problem is the **correction layer**: it modifies outputs using hardcoded, unvalidated constants and a fallback default skin type.

**Tests reinforce this:** `test_skin_tone.py` checks the fixed HR correction behavior for Types 5–6 and the empty-frame fallback (`test_skin_tone.py` lines 102–105, 145–151).

---

### 4.6 Scaffolding Pattern in the Test Surface

**Verdict: 🟠 FEATURE_GAP — the tests mostly validate deterministic heuristics, not physiological validity**

Across these modules, the tests confirm:
- deterministic/bounded synthetic vitals (`test_vitals_extraction.py` lines 6–15)
- hardcoded age-bracket lookup (`test_vascular_age.py` lines 19–56)
- RGB-ratio anemia scoring (`test_anemia_screen.py` lines 27–52)
- hardcoded skin-tone correction factors (`test_skin_tone.py` lines 135–151)

That is useful regression coverage, but it is not validation against real pulse oximetry, real vascular-aging morphology labels, real conjunctival datasets, or real Diverse-rPPG calibration data.

---

### Checkpoint 4 Summary Table

| ID | Finding | Severity | File | Line(s) |
|---|---|---|---|---|
| WOZ-01 | `extract_vitals_from_media()` fabricates a synthetic RGB waveform from raw bytes and derives `spo2` from red/blue heuristics, not real red/IR oximetry | **BLOCKER** | `vitals_extraction.py` | 27–46, 55–128 |
| WOZ-02 | Raw `image_bytes` / `video_bytes` path can inject scaffolded vitals into the main evaluation flow | **BLOCKER** | `grpc_runtime.py`, `scan_evaluation_service.py` | 27–40; 141–156 |
| WOZ-03 | `vascular_age.py` is HR/HRV population-bracket matching, not pulse-wave morphology analysis | **FEATURE_GAP** | `vascular_age.py` | 22–33, 53–97 |
| WOZ-04 | `anemia_screen.py` is an RGB-ratio heuristic over aggregate frame means, not real conjunctival imaging analysis | **FEATURE_GAP** | `anemia_screen.py`, `scan_evaluation_service.py` | 41–126; 50–58 |
| WOZ-05 | `skin_tone.py` uses hardcoded per-type calibration factors and an empty-frame fallback default | **DEBT** | `skin_tone.py` | 25–35, 84–98, 208–215, 229–279 |
| WOZ-06 | Test coverage validates deterministic heuristics rather than physiological truth against real datasets/devices | **FEATURE_GAP** | `test_vitals_extraction.py`, `test_vascular_age.py`, `test_anemia_screen.py`, `test_skin_tone.py` | 6–15; 19–56; 27–52; 135–151 |

**Blockers: 2 | Feature Gaps: 3 | Debt: 1**

---

## Checkpoint 5: Validation Readiness

**Scope audited:** `service-intelligence/scripts/validate_accuracy.py`, `docs/planning/`, and adjacent validation docs for benchmark-harness completeness.

---

### 5.1 `validate_accuracy.py` — HR / HRV Comparison Logic

**Verdict: ⚠️ DEBT — the harness performs a real sliding-window comparison, but it is still coarse rather than validation-grade**

**Answer to the ECG comparison question:** yes, the script does compare service-intelligence HR / HRV outputs against a supplied ECG/reference CSV. It is not a stub. It loads the trace CSV and gold CSV, normalizes timestamps by default, runs the server-side processors on each trace window, and computes HR / HRV MAE and RMSE against the gold window averages.

**Evidence in code:**
- The script expects `--trace-csv` with `t_ms,r_mean,g_mean,b_mean` and `--ecg-csv` with `timestamp_ms,hr_bpm,hrv_rmssd_ms[,stiffness_index]` (`validate_accuracy.py` lines 31–42, 392–409).
- `run_comparison()` slices both streams into time windows, calls `process_frames()` for `standard` or `process_morphology_frames()` for `deep_dive`, and compares pipeline outputs against `fmean(...)` of the gold values in the same window (`validate_accuracy.py` lines 221–288).
- `build_report()` computes per-metric MAE / RMSE and overall pass/fail (`validate_accuracy.py` lines 313–344).

**Why this is debt instead of a blocker:**
- The core comparison path is real and usable for coarse benchmarking.
- But the script does **not** derive HR / RMSSD from raw ECG waveforms or beat annotations itself; it assumes those metrics are already pre-computed in the gold CSV.
- It also uses simple window averaging, with no drift correction, no explicit low-quality-window exclusion, and no per-window skip accounting even though `windows_attempted` and `windows_used` are reported separately but set to the same value (`validate_accuracy.py` lines 335–338).

---

### 5.2 Standard vs Deep Dive Support

**Verdict: 🔴 BLOCKER for Deep Dive overall validation, ⚠️ DEBT for data-shape ergonomics**

**Answer to the scan-type question:** yes, the script has explicit support for both `standard` and `deep_dive` modes.

**Evidence in code:**
- `--mode` is restricted to `standard` or `deep_dive` (`validate_accuracy.py` lines 396–399).
- `standard` routes to `process_frames()` and `deep_dive` routes to `process_morphology_frames()` (`validate_accuracy.py` lines 246–258).

**Limits of that support:**
- In `deep_dive`, the harness still expects an RGB-shaped trace CSV (`r_mean`, `g_mean`, `b_mean`) even though the morphology processor only consumes `r_mean` (`validate_accuracy.py` lines 150–171; `morphology_processor.py` lines 98–100). That is awkward but workable by duplicating the red channel.
- More importantly, the script includes `stiffness_index` in deep-dive scoring (`validate_accuracy.py` lines 264–269, 326, 373–374), but the underlying `stiffness_index` implementation is already a known algorithmic blocker from Checkpoint 2. That means the harness can execute `deep_dive`, but its overall Deep Dive pass/fail is not physiologically trustworthy as long as SI remains mislabeled.
- `--height-cm` is only warned about, not enforced, so Deep Dive runs can silently skip SI validation while still reporting an overall result (`validate_accuracy.py` lines 452–453).

---

### 5.3 Dataset / Benchmark Artifact Readiness

**Verdict: 🟠 FEATURE_GAP — no benchmark dataset or reproducible acquisition pack is checked in**

**Answer to the dataset question:** I found **no checked-in benchmark dataset** for `validate_accuracy.py`.

**Evidence in repo:**
- A repo-wide search found no ECG / benchmark CSV fixtures outside dependency directories.
- `d30-go-no-go-kpi-template.md` explicitly says HR and HRV accuracy are blocked because there is **“No bench-test evidence checked into repo”** and **“No checked-in benchmark dataset/results”** (`d30-go-no-go-kpi-template.md` lines 32–33, 50).
- `docs/handoffs/latest.md` lists “place to store raw benchmark results and summary artifacts in the repo” as an unblocking input for D22 (`latest.md` lines 243–247).

**What does exist:**
- `docs/setup/rppg-reference-validation.md` documents the older `validate_rppg_reference.py` POS-only HR harness, not the newer `validate_accuracy.py` multi-metric harness (`rppg-reference-validation.md` lines 1–48).
- The planning docs describe the intended devices and evidence, but not an acquisition SOP for producing the exact CSVs consumed by `validate_accuracy.py`.

---

### 5.4 D30 KPI Template Coverage

**Verdict: 🟠 FEATURE_GAP identified clearly in planning docs**

**Answer to the KPI-template question:** yes, `d30-go-no-go-kpi-template.md` explicitly identifies the accuracy-validation gap.

**Evidence in doc:**
- The current recommendation is `No-go` partly because **D22 accuracy bench testing** evidence is still missing (`d30-go-no-go-kpi-template.md` lines 8–12).
- The KPI table marks both HR accuracy and HRV accuracy as **Blocked** due to missing bench-test evidence (`d30-go-no-go-kpi-template.md` lines 32–33).
- The exit-criteria table marks **Accuracy validation** as **Not met** because there is **“No checked-in benchmark dataset/results”** (`d30-go-no-go-kpi-template.md` line 50).
- The “Required Inputs Before Go Decision Can Flip” section asks for a reusable artifact under `docs/` containing the benchmark results (`d30-go-no-go-kpi-template.md` lines 72–80).

So the planning artifact is correctly flagging the readiness gap; the missing piece is the empirical dataset and an operator-ready harness workflow.

---

### 5.5 Missing Readiness Pieces Around the Harness

**Verdict: 🟠 FEATURE_GAP — implementation exists, but validation operations are not fully packaged**

Remaining gaps that prevent calling the harness “ready”:
- `validate_accuracy.py` is not referenced anywhere else in the repo outside its own file, so operators are still pointed at the older POS-only validation script.
- I found no dedicated tests for `validate_accuracy.py`.
- There is no checked-in example fixture pair for `trace-csv` and `ecg-csv`.
- There is no documented convention for timestamp synchronization, clock-offset correction, or drift handling between capture and reference devices.
- There is no benchmark-results folder structure or manifest under `docs/` or `service-intelligence/benchmarks/`.

---

### Checkpoint 5 Summary Table

| ID | Finding | Severity | File | Line(s) |
|---|---|---|---|---|
| VAL-01 | `validate_accuracy.py` performs a real sliding-window HR / HRV comparison against a supplied ECG/reference CSV, but it is coarse and not beat-aligned or drift-aware | **DEBT** | `validate_accuracy.py` | 221–344 |
| VAL-02 | `deep_dive` mode exists, but its overall pass/fail includes the already-invalid `stiffness_index` metric, so Deep Dive validation is not fully trustworthy | **BLOCKER** | `validate_accuracy.py`, `morphology_processor.py` | 246–269, 326, 373–374; 204–257 |
| VAL-03 | Deep Dive still requires an RGB-shaped trace CSV even though the morphology path only uses the red channel | **DEBT** | `validate_accuracy.py`, `morphology_processor.py` | 150–171; 98–100 |
| VAL-04 | No benchmark dataset or result artifact is checked into the repo for the new accuracy harness | **FEATURE_GAP** | `d30-go-no-go-kpi-template.md`, `latest.md` | 32–33, 50, 72–80; 243–247 |
| VAL-05 | Repo documentation still points operators to `validate_rppg_reference.py`; `validate_accuracy.py` has no companion setup doc or acquisition SOP | **FEATURE_GAP** | `rppg-reference-validation.md`, `validate_accuracy.py` | 1–48; 1–67 |
| VAL-06 | `d30-go-no-go-kpi-template.md` correctly identifies the missing accuracy-validation evidence and blocks rollout on it | **FEATURE_GAP** | `d30-go-no-go-kpi-template.md` | 8–12, 32–33, 50, 72–80 |
| VAL-07 | No dedicated tests were found for `validate_accuracy.py` | **FEATURE_GAP** | — | — |

**Blockers: 1 | Feature Gaps: 4 | Debt: 2**
