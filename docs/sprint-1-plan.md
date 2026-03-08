# Sprint 1 Plan — PranaScan MVP

**Sprint window:** March 9–22, 2026 (2 weeks)
**Goal:** Deliver a production-like increment with full consent flow, scan session API, audit logging, and mobile screens.

## Sprint Goal

> "A user can open the app, grant informed consent, complete a guided scan (camera + voice), and receive wellness indicator results — with every action immutably logged."

## Stories

| ID | Story | Points | Owner |
|----|-------|--------|-------|
| S1 | Project scaffolding & CI | 3 | Infra |
| S2 | Consent & Privacy Flow (backend) | 5 | Backend |
| S3 | Scan Session API (backend) | 8 | Backend |
| S4 | Audit Log API | 3 | Backend |
| S5 | Mobile Consent Screen | 5 | Mobile |
| S6 | Mobile Camera Capture + Quality Gate | 8 | Mobile |
| S7 | Mobile Voice Capture | 5 | Mobile |
| S8 | Mobile Scan Orchestrator | 5 | Mobile |

**Total:** 42 points

## Definition of Done

- [ ] All acceptance criteria met
- [ ] Unit tests written and passing
- [ ] No diagnostic language in any output
- [ ] Ruff + Black pass (backend)
- [ ] ESLint + TypeScript pass (mobile)
- [ ] CI pipeline green
- [ ] Code reviewed and merged to `develop`

## Risks

| Risk | Mitigation |
|------|-----------|
| rPPG accuracy on low-end devices | Quality gate rejects poor-signal scans |
| DPDP compliance gaps | Consent flow reviewed against DPDP Act 2023 |
| Latency > 15s | On-device processing budget enforced in QualityGate |
| Voice capture noise | SNR gate > 15dB rejects noisy environments |
