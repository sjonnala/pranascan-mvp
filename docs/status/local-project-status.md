# Local Project Status

_Local reference analysis based on the current pulled repo state and git history through 2026-03-10. This file is intended for cross-comparison against generated status docs._

## Scope and Method

- Source of truth: checked-in code under `backend/`, `mobile/`, `agent/`, and migrations/tests.
- Planning baseline: `docs/planning/prd.md`, `docs/architecture/overview.md`, `docs/planning/sprint-plan.md`, and sprint backlog/tracker docs.
- History baseline: full `git log --reverse --stat`.
- When docs and code disagree, this file treats the code as the source of truth.

## Summary

- Estimated completion against `docs/planning/sprint-plan.md`: **about 80%**
- Strongest completed areas:
  - backend foundation, consent, auth, audit, and security plumbing
  - mobile end-to-end capture flow with on-device rPPG and on-device voice DSP
  - trend engine, cooldown, delivery hooks, weekly report generation, and OpenClaw agent plumbing
  - ABHA sandbox integration, vascular-age heuristic, anemia proxy heuristic, and skin-tone calibration
- Largest remaining gaps:
  - empirical validation work from Week 4
  - pilot / beta / feedback instrumentation work
  - WhatsApp delivery and production-grade operational hardening
  - docs drift and repo hygiene issues, including unresolved merge markers in `README.md`

## Milestone Status Against `docs/planning/sprint-plan.md`

| Plan Window | Planned Focus | Local Status | Notes |
|---|---|---|---|
| Week 1 (Days 1-7) | Foundation and scanning core | **Complete** | D1, D2, D3, D5, and D7 all have code and tests or implementation evidence in the repo. |
| Week 2 (Days 8-14) | Analysis layer and privacy architecture | **Mostly complete** | D8, D9, D10, D11, D13 are implemented. D12 is heuristic rather than full conjunctiva CV. D14 has harness/test coverage but not proven target-device validation evidence. |
| Week 3 (Days 15-21) | ABHA integration and agentic trend layer | **Mostly complete** | D15, D17, D18, D19, and D20 have real code paths. D21 internal pilot is not evidenced from code or docs. |
| Week 4 (Days 22-30) | Validation, hardening, and pilot launch | **Partial** | D25 has meaningful code/test coverage. D26 is committed as WIP. D22, D24 empirical audit, D27, D28, and D30 are still open. |

## Completed

- **Repo and delivery foundation**
  - Backend/mobile split, Docker Compose, GitHub Actions CI, Alembic migrations, async SQLAlchemy models, and baseline tests were established early and remain intact.
- **Privacy, consent, and auth**
  - JWT issuance, refresh, protected-route enforcement, consent grant/revoke/status/deletion, and audit logging are all implemented.
- **Mobile end-to-end scan shell**
  - Consent flow, scan orchestration, results display, camera capture, and voice capture are present in the mobile app.
- **Edge-first mobile signal processing**
  - On-device `rppgProcessor` computes HR, HRV, and respiratory-rate proxy from camera-derived frame samples.
  - On-device `voiceProcessor` computes jitter and shimmer from captured microphone samples.
  - Current `ScanScreen` submits derived metrics rather than raw frame/audio streams on the main path.
- **Quality and trend engine**
  - Quality-gate enforcement exists on backend and mobile.
  - Multi-metric rolling-baseline deviation logic is implemented at the PRD-aligned 15% threshold.
  - Alert cooldown is implemented with a 48-hour suppression window.
- **Advanced wellness modules**
  - Skin-tone calibration service is present and applied in backend fallback rPPG processing.
  - Vascular-age heuristic is implemented and persisted in scan results.
  - Anemia wellness proxy is implemented and persisted in scan results.
- **Integration and agent layer**
  - ABHA link/status/sync endpoints and adapter scaffolding are implemented behind config flags.
  - Weekly vitality report generation, storage, and latest-report retrieval are implemented.
  - Delivery service supports structured logging, webhook delivery, and Telegram delivery.
  - Internal agent trigger and agent-runner flow are implemented for scheduled / OpenClaw-driven automation.
- **Security and verification surface**
  - Security headers and per-user scan rate limiting are implemented.
  - The repo now contains broad test coverage across auth, consent, scan flow, rPPG, voice DSP, delivery, vitality reports, ABHA, agent flow, security, skin tone, and demo E2E flow.

## In Progress / Partial

- **D12 anemia screening is not a full conjunctiva CV model**
  - Current implementation is a confidence-gated color heuristic based on aggregated frame-channel means.
  - This materially advances the feature, but it is not yet the palpebral-conjunctiva computer-vision module described in the PRD.
- **D14 latency validation is implemented as instrumentation + tests, not proven field validation**
  - Timing middleware and a validation harness exist.
  - The repo does not show measured results on the target device matrix from the sprint plan.
- **D15 ABHA is sandbox/mock integration, not production certification**
  - Good for MVP scaffolding and functional flow.
  - Production ABDM registration and real gateway proof are still outside the checked-in evidence.
- **D19 agentic delivery is partially complete**
  - Telegram and webhook delivery are implemented.
  - WhatsApp delivery and richer preference management are still absent.
- **D25 security is strong at code level, but not a formal audit artifact**
  - Security headers, rate limiting, and tests exist.
  - A formal security review report is not present in the repo.
- **D26 bug-bash work is committed but unfinished**
  - The latest handoff documents quality-gate severity tiers, accented-vowel accommodation, occlusion hinting, and transient-motion recovery as implemented.
  - The same handoff explicitly says tests and final doc updates for that work were still pending.

## Pending

### Week 4 / launch-readiness gaps

- D22 controlled bench accuracy test against finger-clip oximeter / Polar H10
- D24 empirical skin-tone accuracy audit for Fitzpatrick 5-6
- D27 closed beta onboarding and cohort execution
- D28 in-app feedback instrumentation and NPS loop
- D30 KPI review, rollout decision, and post-MVP lock

### Product / ops gaps still visible in code

- WhatsApp delivery path
- production-ready ABHA / ABDM operational proof
- more complete user channel / notification preferences
- stronger session lifecycle hardening on mobile, including token refresh behavior
- cleanup of stale docs and README merge conflict

## Code vs Plan Drift

- `docs/status/project-status.md` materially underestimates current completion. It still describes ABHA, weekly reports, delivery automation, vascular age, anemia, edge processing, and security hardening as missing or partial when those areas now have code.
- `docs/status/daily-status.md` only reflects very early work and no longer represents the repo.
- `docs/architecture/overview.md` describes the correct edge-first direction, but the actual code is now a hybrid architecture:
  - main mobile flow is edge-first
  - backend still supports fallback processing paths for `frame_data` and `audio_samples`
- `README.md` currently contains unresolved merge markers, so it is not reliable as an onboarding status source until cleaned.

## Risks

- The highest-value remaining work is no longer core feature scaffolding. It is validation, rollout readiness, and evidence quality.
- Some implemented modules are heuristics or sandbox-grade integrations rather than clinically or operationally validated systems.
- The latest D26 commit is explicitly WIP with tests pending, so the current branch should not be treated as fully stabilized.

## Assumptions and Caveats

- This local analysis covers **all relevant commits in the repo history**, not only commits clearly attributable to OpenClaw, because authorship naming is mixed across `PranaScan Dev` and `satjonna`.
- I did **not** rerun the full validation suite for this documentation-only pass.
- The latest handoff states the D26 WIP commit was not yet pushed at the time of that handoff; however, it exists in the current pulled repo and is therefore included in this assessment.
