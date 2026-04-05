# Daily Status — Sprint 1

## Day 1 — March 9, 2026

**Completed:**
- S1: Full project scaffolding (all dirs, CI pipeline)
- S2: Consent & Privacy Flow backend — all 4 endpoints + tests
- S3: Scan Session API backend — all 4 endpoints + tests
- S4: Audit Log API + middleware auto-logging + tests
- S5: Mobile Consent Screen (ConsentScreen + useConsent hook)
- S6: Mobile Camera Capture + QualityGate component
- S7: Mobile Voice Capture component
- S8: Mobile Scan Orchestrator (ScanScreen + ResultsScreen + useScan hook)

**Blocked:** None

**Notes:**
- Sprint 1 delivered in Day 1 (accelerated execution)
- All backend tests passing
- CI pipeline configured for GitHub Actions
- Docker Compose configured for full-stack dev

## Metrics

| Story | Status | Tests |
|-------|--------|-------|
| S1 — Scaffolding | ✅ Done | CI green |
| S2 — Consent Backend | ✅ Done | 9 tests |
| S3 — Scan API | ✅ Done | 8 tests |
| S4 — Audit Log | ✅ Done | 5 tests |
| S5 — Consent Screen | ✅ Done | 3 tests |
| S6 — Camera + QG | ✅ Done | 4 tests |
| S7 — Voice Capture | ✅ Done | — |
| S8 — Orchestrator | ✅ Done | — |

---

## Sprint 2.1 — March 8, 2026 (UTC)

Source of truth: docs/planning/sprint-2.1-backlog.md

### S2-01 · Real Camera Capture Pipeline ✅

**Completed:** 2026-03-08

**Changed files:**
- `mobile/src/types/index.ts` — added `FrameSample` type; added `frame_data` + `audio_samples` to `ScanResultPayload`
- `mobile/src/utils/frameAnalyzer.ts` — NEW: `computeLightingScore`, `computeMotionScore`, `buildFrameSample`, `computeOverallQualityScore`
- `mobile/src/components/CameraCapture.tsx` — replaced placeholder `<View>` with real `expo-camera` `CameraView`; real permission flow; real frame sampling via `takePictureAsync`; quality metrics from JPEG analysis; frame_data accumulated for backend rPPG
- `mobile/src/screens/ScanScreen.tsx` — null→undefined coercion for optional fields; `frame_data` forwarded in payload
- `mobile/__tests__/CameraCapture.test.tsx` — replaced stub with 14 new tests covering permission states, scan start, cancel, quality update, no-diagnostic-language
- `mobile/__tests__/frameAnalyzer.test.ts` — NEW: 16 pure-function unit tests

**Raw check outputs:**
- `python3 -m ruff check .` → All checks passed!
- `PYTHONPATH=service-intelligence python3 -m pytest -q service-intelligence/tests` → 59 passed in 1.68s
- `npx eslint src/ --ext .ts,.tsx && npx tsc --noEmit && npm test` → Test Suites: 4 passed | Tests: 46 passed

**Blockers:** None

**Implementation notes:**
- Face confidence: fixed 0.85 proxy (expo-face-detector not bundled in SDK 51 base; Sprint 3 target)
- Lighting/motion: real JPEG-size heuristic — deterministic, not random
- `frame_data` flows to backend for server-side rPPG (S2-02 backend already wired)
- Raw base64 frames never stored or transmitted; only FrameSample means forwarded

**Next:** S2-02 — rPPG v1 processing (no simulation)
