# D30 Go/No-Go KPI Review — March 11, 2026

This document is the Week 4 rollout review artifact for the PranaScan MVP. It maps the planned MVP exit criteria from [sprint-plan.md](./sprint-plan.md) to the current codebase, validation evidence, and the remaining non-repo blockers required before a broader rollout.

## Current Recommendation

**Recommendation: No-go for broader rollout today.**

Why:
- Core product flows are implemented and locally validated in code.
- Critical rollout evidence is still missing for **D22 accuracy bench testing** and **D24 skin-tone audit validation**.
- External activation dependencies are still open for **ABHA sandbox/production readiness** and **WhatsApp Business credentials / sender approval**.
- Closed beta onboarding is now implemented, so a limited internal or invitation-only beta can proceed once invites and deployment are ready.

## Decision Scope

This review is for:
- engineering readiness
- product/ops readiness visible in the repo
- evidence already captured in code, tests, and docs

This review does **not** claim completion for:
- medical-grade validation
- regulatory certification
- production credential issuance
- beta cohort recruitment execution

## KPI Scorecard

| KPI | Target From Plan | Current Evidence | Status | Notes |
|---|---|---|---|---|
| HR accuracy | ±5% vs finger-clip oximeter | No bench-test evidence checked into repo | Blocked | Requires D22 controlled session data |
| HRV accuracy | ±15% vs Polar H10 | No bench-test evidence checked into repo | Blocked | Requires D22 controlled session data |
| Scan completion rate | ≥85% of initiated scans complete | No deployed telemetry or cohort usage data | Blocked | Can only be measured after beta deployment |
| 2-scans/week retention | ≥40% of beta users | No beta cohort telemetry yet | Blocked | Depends on D27 rollout execution, not just code |
| At-risk alert → lab booking conversion | ≥10% | No live conversion instrumentation or partner workflow evidence | Blocked | Product/ops metric, not proven in repo |
| Post-scan latency | <15s on Snapdragon 680+ | Latency instrumentation + harness implemented; local tests exist | Partial | Still needs target-device validation evidence |

## Exit Criteria Review

| Area | Target | Evidence Source | Current State |
|---|---|---|---|
| Consent + privacy | Explicit opt-in, revocation, deletion path, audit trail | [backend/app/routers/consent.py](../backend/app/routers/consent.py), [backend/app/routers/audit.py](../backend/app/routers/audit.py) | Met in code |
| Auth enforcement | Protected backend routes and mobile bearer-token flow | [backend/app/routers/auth.py](../backend/app/routers/auth.py), [mobile/src/api/client.ts](../mobile/src/api/client.ts) | Met in code |
| Camera + voice capture | Real mobile capture path | [mobile/src/screens/ScanScreen.tsx](../mobile/src/screens/ScanScreen.tsx), [mobile/src/components/VoiceCapture.tsx](../mobile/src/components/VoiceCapture.tsx) | Met in code |
| Trend engine | 3-scan baseline + 15% deviation rule | [backend/app/services/trend_engine.py](../backend/app/services/trend_engine.py) | Met in code |
| Alert/report delivery | Telegram + WhatsApp scaffolds | [backend/app/services/delivery_service.py](../backend/app/services/delivery_service.py) | Partial; credentials still external |
| Closed beta gate | Invite-based onboarding before consent | [backend/app/routers/beta.py](../backend/app/routers/beta.py), [mobile/src/screens/BetaOnboardingScreen.tsx](../mobile/src/screens/BetaOnboardingScreen.tsx) | Met in code |
| Feedback loop | Post-scan usefulness + NPS | [backend/app/routers/feedback.py](../backend/app/routers/feedback.py), [mobile/src/screens/ResultsScreen.tsx](../mobile/src/screens/ResultsScreen.tsx) | Met in code |
| Accuracy validation | Bench evidence for HR/HRV | No checked-in benchmark dataset/results | Not met |
| Skin-tone audit | Fitzpatrick 5-6 empirical evidence | No checked-in audit results | Not met |

## Local Validation Snapshot

Latest local engineering validation for the checked-in repo state:

```text
python3 -m ruff check .                         → All checks passed!
DEBUG=false PYTHONPATH=backend python3 -m pytest -q
                                                → 252 passed, 186 warnings in 7.11s
cd mobile && npx eslint src/ --ext .ts,.tsx    → clean
cd mobile && npx tsc --noEmit                  → clean
cd mobile && npm test -- --watchAll=false      → 151 passed, 11 suites
```

Interpretation:
- engineering regression coverage is strong enough for continued internal iteration
- automated tests do **not** replace D22 bench accuracy evidence or D24 fairness/audit evidence

## Required Inputs Before Go Decision Can Flip

### D22 bench accuracy

- 20-person controlled scan session
- reference devices:
  - finger-clip oximeter
  - Polar H10 or equivalent HRV reference
- results recorded in a reusable artifact:
  - CSV, notebook output, or markdown summary under `docs/`

### D24 skin-tone audit

- participant or dataset coverage across Fitzpatrick 5-6
- documented error bounds and failure cases
- final audit summary checked into `docs/`

### Delivery / ecosystem activation

- WhatsApp Business API credentials
- approved sender / template path
- ABHA sandbox credentials and production-readiness proof

### Beta operations

- deployed environment for invitation-only beta
- seeded invite codes or configured `BETA_SEED_INVITE_CODE`
- recruited cohort and onboarding comms

## Suggested Go/No-Go Meeting Agenda

1. Review KPI scorecard above and mark each item `Met`, `Partial`, or `Blocked`.
2. Review D22 and D24 evidence quality, not just existence.
3. Confirm that beta invites, deployment environment, and support path are ready.
4. Decide one of:
   - `No-go` for broader rollout
   - `Go` for invitation-only beta
   - `Go` for broader rollout
5. Lock the post-MVP backlog based on the decision.

## Current Decision Log

| Date | Recommendation | Reason |
|---|---|---|
| March 11, 2026 | No-go for broader rollout | Missing D22 bench evidence, D24 audit evidence, and external activation credentials |

## Post-MVP Backlog Candidates

- production token refresh + session-hardening on mobile
- richer recipient preference management for delivery channels
- invite management tooling for beta operations
- device-class latency evidence pack
- production ABHA certification workflow
- empirical fairness / accuracy reporting automation
