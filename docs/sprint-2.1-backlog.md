# PranaScan — Sprint 2 Backlog
Sprint window: March 23, 2026 to April 5, 2026  
Sprint goal: Replace simulated health processing with real v1 pipelines, enforce backend auth, and ship ABHA-ready integration scaffolding.

## Scope In
- Real mobile camera capture pipeline
- Real rPPG v1 extraction (HR, HRV, RR proxy)
- Real voice DSP v1 (jitter, shimmer)
- JWT auth enforcement for backend APIs
- Baseline + 15% deviation alert engine
- ABHA adapter with sandbox mock + feature flag

## Scope Out
- Clinical claims or diagnosis features
- Production ABHA certification
- Full teleconsult/lab booking integrations

## Story Backlog

| Pri | ID | Story | SP | Acceptance Criteria |
|---|---|---|---:|---|
| 1 | S2-01 | Replace placeholder camera with real capture pipeline | 5 | Front camera preview + 30s recording works on device; quality-gate inputs are real; tests added |
| 2 | S2-02 | Implement rPPG v1 processing (no simulation) | 8 | HR/HRV/RR proxy computed from recorded frames; confidence score emitted; quality-gate blocks low-quality runs |
| 3 | S2-03 | Implement voice DSP v1 (no simulation) | 5 | 5s sustained vowel analyzed for jitter/shimmer + confidence; low SNR blocked; tests added |
| 4 | S2-04 | Enforce JWT auth on backend routes | 5 | Protected APIs reject unauthenticated requests; token validation middleware active; auth tests pass |
| 5 | S2-05 | Baseline + 15% deviation engine | 5 | Baseline from first 5 valid scans over 7 days; deviation formula applied; alert cooldown + suppression rules tested |
| 6 | S2-06 | ABHA adapter with sandbox mock + feature flag | 3 | Adapter interface implemented; mock sandbox flow works; toggle via config/env; no prod calls by default |
| 7 | S2-07 | Latency/perf hardening + observability | 3 | End-to-end post-scan latency measured; p95 under target on test device class; metrics/logs added |

Total: 34 SP

## Non-Functional Gates
- Post-scan analysis latency target: < 15s (mid-range Android test device)
- No diagnostic language in UI/messages
- Raw audio/video stays on-device; only metadata sent to backend
- Quality gate must hard-stop bad captures

## Definition of Done (per story)
1. Code implemented and documented.
2. All checks pass with raw command output captured:
   - `python3 -m ruff check .`
   - `PYTHONPATH=backend python3 -m pytest -q backend/tests`
   - `cd mobile && npm ci && npx eslint src/ --ext .ts,.tsx && npx tsc --noEmit && npm test -- --watchAll=false`
3. `docs/daily-status.md` updated with progress/blockers.
4. Commit created after passing checks.

## Sprint Exit Criteria
- S2-01 through S2-06 complete
- CI green on main
- Demo flow works: Consent -> Capture -> Real processing -> Result -> Baseline/deviation status

