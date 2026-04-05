# PranaScan Design Docs

This folder is the engineering-facing design set for the current codebase.
It is meant to help a new engineer get productive without reverse-engineering
the repo from scratch.

## Read In This Order

1. [system-overview.md](./system-overview.md)
   Start here for the current architecture, system boundaries, and design principles.

2. [component-workflows.md](./component-workflows.md)
   Read this next for the current runtime flows: OIDC login, consent, scan
   orchestration, gRPC intelligence evaluation, result retrieval, and audit.

3. [backend-design.md](./backend-design.md)
   Use this to understand the current backend split: Spring Boot
   `service-core` as the product-facing system of record and FastAPI
   `service-intelligence` as the internal compute service.

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

These design docs are based on the current checked-in code, not just older plan
docs. The repo has already crossed the main architecture boundary:

- `service-core` owns product-facing auth, consent, scan orchestration,
  reporting, feedback, and audit.
- `service-intelligence` is now compute-only by default and serves an internal
  gRPC contract to `service-core`.
- Historical FastAPI public routes and OTP/JWT auth code have been removed from
  the active runtime.

## Current High-Level Truth

The current implementation is best described as a polyglot monolith:

- Mobile performs capture plus the OIDC login flow.
- `service-core` is the public backend and source of truth for persisted
  product state.
- `service-intelligence` handles rPPG, quality gating, and derived heuristics
  behind the private gRPC `EvaluateScan` boundary.

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
