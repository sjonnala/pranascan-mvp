# PranaScan Design Docs

This folder is the engineering-facing design set for the current codebase.
It is meant to help a new engineer get productive without reverse-engineering
the repo from scratch.

## Read In This Order

1. [system-overview.md](./system-overview.md)
   Start here for the current architecture, system boundaries, and design principles.

2. [component-workflows.md](./component-workflows.md)
   Read this next for the main runtime flows: consent, scan, result retrieval,
   trend alerting, and failure handling.

3. [backend-design.md](./backend-design.md)
   Use this to understand the FastAPI app, router boundaries, services,
   middleware, data model, and extension points.

4. [mobile-design.md](./mobile-design.md)
   Use this to understand the React Native app shell, screen flow, hooks,
   on-device signal processing, and payload construction.

5. [data-contracts.md](./data-contracts.md)
   Use this as the API and schema reference for request/response models and
   persisted tables.

6. [engineering-onboarding.md](./engineering-onboarding.md)
   Use this as the practical setup and development guide: local run commands,
   test strategy, common gotchas, and recommended first tasks.

## What These Docs Treat As Source Of Truth

These design docs are based on the current checked-in code, not just the plan
docs. That matters because the repo is in a transition state:

- The original architecture docs describe a fully edge-first system.
- The current mobile app mostly follows that edge-first path.
- The backend still supports legacy or fallback server-side processing for
  `frame_data` and `audio_samples`.
- Additional backend features such as vascular-age estimation, anemia-screening
  heuristics, alert cooldown, and webhook-based alert delivery now exist in code,
  even if older planning docs do not consistently reflect them.

## Current High-Level Truth

The current implementation is best described as a hybrid system:

- Mobile performs the primary camera and voice signal processing on-device.
- Backend remains the authoritative API, persistence, consent ledger, audit
  trail, trend engine, alerting surface, and place where secondary heuristics
  such as vascular age and anemia screening are computed.
- The backend still accepts raw derived feature streams (`frame_data`,
  `audio_samples`) when clients choose to use that path, but the current mobile
  flow mostly submits final scalar indicators instead.

## Intended Audience

- New engineers onboarding to the repo
- Existing contributors adding features across mobile and backend
- Tech leads reviewing current architecture and implementation drift
- QA or product engineers who need a code-grounded system map

## Related Docs

- [../architecture/overview.md](../architecture/overview.md)
  Original architecture direction and privacy model.

- [../status/project-status.md](../status/project-status.md)
  Progress assessment versus the sprint plan.

- [../planning/sprint-plan.md](../planning/sprint-plan.md)
  Original execution plan and staged rollout targets.
