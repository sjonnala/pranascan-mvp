# Current Project Status — March 9, 2026

This assessment is based on the checked-in codebase and compared against the original execution plan in [sprint-plan.md](./sprint-plan.md). Where status logs and implementation disagree, the code is treated as the source of truth.

## Summary

- Overall completion against the MVP execution plan: about **45%**
- Strongest areas: foundation, backend APIs, privacy flow, audit logging, and mobile shell screens
- Largest gaps: true end-to-end mobile/backend integration, edge/on-device processing alignment, advanced health modules, ABHA integration, OpenClaw delivery, and Week 4 launch hardening

## Milestone Status Against `sprint-plan.md`

| Plan Window | Planned Focus | Current Status | Notes |
|---|---|---|---|
| Week 1 (Days 1-7) | Foundation and scanning core | Partial | D1 complete; D2 mostly complete; D3 partial; D5 not started; D7 partial |
| Week 2 (Days 8-14) | Analysis layer and privacy architecture | Partial | Consent, audit, first-pass rPPG, and first-pass backend voice DSP exist; vascular age, anemia screening, and latency validation are still pending |
| Week 3 (Days 15-21) | ABHA integration and agentic trend layer | Partial | Multi-metric 15% trend alerting is now implemented; ABHA adapter, OpenClaw daemon, messaging integration, and weekly report implementation are still absent |
| Week 4 (Days 22-30) | Validation, hardening, and pilot launch | Not started | No bench-test, beta, audit, or rollout-readiness evidence found in the repo |

## Completed

- Foundation and delivery setup are in place: repo structure, Docker, backend/mobile separation, and GitHub Actions CI.
- Consent and privacy flow are implemented with grant, revoke, deletion request, and status endpoints.
- Audit logging is implemented and protected behind authenticated access.
- Backend scan workflow exists for session creation, completion, result storage, history lookup, quality-gate enforcement, and trend alert persistence.
- JWT auth issuance, refresh, and protected backend route enforcement are implemented with backend tests.
- Mobile API auth is now wired end-to-end for the current app flow: the client requests bearer tokens for the active pseudonymous user and attaches them to protected consent and scan requests.
- Mobile shell flow exists for consent, camera step, voice step, scan orchestration, and results display.
- The mobile camera step uses `expo-camera` and forwards sampled `frame_data` for backend processing.
- The mobile voice step now records real microphone input, derives real `audio_samples`, and submits a real client-side SNR signal for backend voice DSP.
- First-pass backend processing services exist for rPPG and voice DSP.
- Multi-metric backend trend alerting now uses a 7-day rolling baseline, a 3-scan minimum baseline requirement, and the PRD-aligned **15%** deviation threshold.

## In Progress / Partial

- Environment checks exist for lighting and motion, but face confidence is still a proxy.
- rPPG extraction exists for HR, HRV, and respiratory-rate proxy, but it currently runs on the backend from frame summaries instead of on-device as described in the architecture and sprint plan.
- End-to-end integration is still partial because auth, voice capture, and trend alerting are now wired, but environment-check parity and architecture-aligned edge processing are still incomplete.

## Pending Items

### Week 2 scope still open

- Vascular age mapping
- Anemia screening from conjunctiva imaging
- True edge-processing alignment with the architecture
- Validated sub-15-second end-to-end latency on target devices

### Week 3 scope still open

- ABHA/ABDM integration
- OpenClaw background agent
- Weekly vitality report generation
- WhatsApp or Telegram delivery integration

### Week 4 scope still open

- Accuracy bench testing
- Skin-tone calibration audit for Fitzpatrick Types 3-6
- Security audit and hardening
- Bug bash and edge-case validation
- Closed beta onboarding and feedback instrumentation
- Go/no-go review for rollout readiness

## Key Risks Blocking MVP Completion

- Mobile auth is now wired for the current app flow, but token refresh and longer-lived session hardening are still not implemented.
- The architecture promises edge-first processing, but the implemented signal-processing path is still backend-centric.
- The mobile voice path now depends on `expo-av` sample extraction after recording; if native audio sample callbacks are unavailable, the client falls back to metering-derived samples instead of full PCM.
- The trend engine now matches the 15% multi-metric baseline rule, but alert cooldown/suppression and delivery automation are still not implemented.
- Advanced health features in the PRD are still absent: skin-tone calibration, vascular age, anemia screening, and ABHA sync.

## Assumptions and Caveats

- This assessment is based on the current codebase plus the initial plan from [sprint-plan.md](./sprint-plan.md).
- The repo contains timeline inconsistencies across documents. For example, [daily-status.md](./daily-status.md) references March 8, 2026 and March 9, 2026, while [sprint-2.1-backlog.md](./sprint-2.1-backlog.md) is dated March 23, 2026 to April 5, 2026. This status ignores those conflicting dates and scores implemented scope only.
- Mobile lint, typecheck, and Jest validation were re-run successfully on March 9, 2026 for the auth, voice, and trend items. Backend pytest still could not be collected in this workspace because `pytest_asyncio` is missing from the local Python environment.
