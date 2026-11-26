# PranaScan Enterprise Standards (AGENTS.md)

This document serves as the global context and "Soul" for all agents working on the PranaScan project. Follow these rules strictly to ensure high-fidelity, consistent, and production-ready outputs.

## 🎯 Vision
**30-second wellness selfie + voice screening for proactive professionals in India.**  
We deliver "Wellness Indicators," not medical diagnoses. Priority is on privacy, speed, and premium editorial aesthetics.

## 🏗️ Tech Stack (Canonical)

### Backend (Service Core & Intelligence)
- **Language**: Java 21 / Python 3.11
- **Framework**: Spring Boot 3.x (Modular Monolith) / FastAPI
- **Architecture**: Domain-Driven Design (DDD). Modules = Bounded Contexts.
- **Database**: PostgreSQL (PostGIS / Vector extensions as needed).
- **Security**: OIDC / JWT (Spring Security).
- **Communication**: REST + OpenAPI 3.

### Frontend & Mobile
- **Mobile**: React Native with Expo (SDK 51), TypeScript.
- **Navigation**: Expo Router (File-based).
- **Styling**: Tailwind CSS (NativeWind) + "The Living Breath" Design System.
- **State**: Zustand (App State) + TanStack Query (Server State).
- **Design Rule**: **"The No-Line Rule"** — No borders, use elevation, soft shadows, and color blocking to define regions.

## 🛡️ Code Guidelines
- **Strict TypeScript**: No `any`. Use interfaces for all data structures.
- **DDD Modeling**: Implement domain models (Entities, Value Objects) before infrastructure.
- **Test-First**: Minimum 80% coverage for domain logic. Unit tests for every new feature.
- **Narrative-First**: UI components must support narrative wellness insights, not just raw metrics.

## 🔄 Multi-Agent Workflow
1. **Orchestrator**: Break down high-level intent into atomic Task IDs.
2. **Researcher**: Resolve unknowns in `service-intelligence` or hardware limits.
3. **PM**: Write the `DESIGN.md` spec with clear Acceptance Criteria.
4. **Engineer**: Build, test, and doc decisions.
5. **Security/QA**: Validate against these standards before PR closure.
