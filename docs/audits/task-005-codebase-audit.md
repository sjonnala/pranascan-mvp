# Codebase Audit Report: PranaScan (task-005)

**Date:** 2026-04-05
**Auditor:** ENG Agent
**Scope:** Reassess completion and identify remaining gaps after tasks 002, 003, and 004, based on `pranascan` project context and decisions.

---

## 1. Overall Assessment

The `pranascan` project has a well-defined set of `Project Decisions` that clearly outline its purpose, technical stack, architecture, and critical compliance requirements. The confirmed API surface (`[API] Confirmed API surface`) serves as an excellent blueprint for the backend implementation.

Without direct access to the codebase (`pranascan-mvp` repo), this audit focuses on validating the conceptual completeness against these decisions and identifying areas where specific implementation details would require thorough verification. It is assumed that tasks 002, 003, and 004 laid some foundational work, but the exact scope of those tasks is not available. Therefore, this audit covers the entire `[API]` surface and other key `[DECISIONS]`.

**Current Status (Conceptual):** The project has a solid strategic foundation. The backend API surface is well-defined, and the architectural decisions regarding on-device processing and privacy are clear.

**Key Remaining Gaps (Conceptual):** The primary gaps likely lie in the granular implementation of complex features such as robust data anonymization, the 30-day data deletion hold, trend delta calculations, and comprehensive testing across all layers.

---

## 2. Backend Audit (FastAPI - Python 3.11)

### 2.1. API Endpoints - Status and Gaps

The `[API] Confirmed API surface` lists the following endpoints. For each, we assess its conceptual status and highlight critical audit points for implementation:

#### 2.1.1. Consent Management
*   **`POST /api/v1/consent`**
    *   **Status:** Essential for initial user engagement and DPDP compliance.
    *   **Audit Focus:**
        *   Verification of a `ConsentRecord` database model (user_id, timestamp, version, consent_text_hash, status='GRANTED').
        *   Ensuring the record is append-only, preserving a full history of consent grants.
        *   Input validation for consent data.
        *   Authentication of the user making the request.
*   **`POST /api/v1/consent/revoke`**
    *   **Status:** Critical for DPDP compliance.
    *   **Audit Focus:**
        *   Verification that this creates a *new* `ConsentRecord` with `status='REVOKED'`, rather than modifying an existing one, to maintain the append-only history.
        *   Impact on data processing: ensure no new scans are accepted after revocation, and existing data is handled according to revocation policy (e.g., anonymized/deleted as per policy).
*   **`POST /api/v1/consent/deletion-request`**
    *   **Status:** High priority for DPDP compliance and data subject rights.
    *   **Audit Focus:**
        *   Verification of a mechanism to mark user data for deletion (e.g., a `deletion_requested_at` timestamp on user or data records, or a separate `DeletionRequest` table).
        *   Crucially, verify the implementation of the **30-day hold period**. This typically requires a background job or scheduled task that processes deletion requests only after the hold period.
        *   Confirmation that data is not immediately purged upon request.
        *   Clarity on what data is deleted (e.g., all personally identifiable links, or the anonymized metrics too).
*   **`GET /api/v1/consent/status`**
    *   **Status:** Necessary for the mobile app to display current consent status.
    *   **Audit Focus:**
        *   Verification that it retrieves the *latest* consent record for the authenticated user.
        *   Ensuring efficient database query for the most recent status.

#### 2.1.2. Scan Session Management
*   **`POST /api/v1/scans/sessions`**
    *   **Status:** Initiates the core user flow.
    *   **Audit Focus:**
        *   Verification of a `ScanSession` database model (session_id, user_id, start_time, status='INITIATED').
        *   Ensuring a unique session ID is generated and returned.
        *   Pre-conditions: User must have active consent.
*   **`PUT /api/v1/scans/sessions/{id}/complete`**
    *   **Status:** Accepts processed scan results from the mobile app.
    *   **Audit Focus:**
        *   Verification of `ScanResult` database model (session_id, HR, HRV, jitter, shimmer, quality_status, rejection_reason, **anonymized_user_id**, timestamp).
        *   **CRITICAL:** Verification of the **anonymization strategy** for `anonymized_user_id`. How is the user linked for history retrieval but anonymized for storage? This requires careful design (e.g., a consistent, non-reversible hash derived from the user's actual ID, or a pseudonymisation service).
        *   Input validation for all submitted metrics and quality flags.
        *   Ensuring the session status in `ScanSession` is updated to 'COMPLETED' or 'FAILED' based on `quality_status`.
*   **`GET /api/v1/scans/sessions/{id}`**
    *   **Status:** Retrieves details for a specific scan session.
    *   **Audit Focus:**
        *   Verification of correct data retrieval and authorization (only owner can view).
        *   Ensuring the response includes both session details and associated scan results.

#### 2.1.3. Data Retrieval
*   **`GET /api/v1/scans/history`**
    *   **Status:** Provides the core value proposition of trend monitoring.
    *   **Audit Focus:**
        *   Verification of data aggregation logic to retrieve all relevant `ScanResult` entries for the authenticated user (via `anonymized_user_id`).
        *   **CRITICAL:** Verification of the **trend delta calculation logic** (e.g., week-over-week deltas as per `[PRODUCT]` decision). This requires careful implementation to avoid off-by-one errors or incorrect period comparisons.
        *   Pagination or filtering capabilities for large history sets.
*   **`GET /api/v1/audit/logs`**
    *   **Status:** Essential for compliance and operational transparency.
    *   **Audit Focus:**
        *   Verification of an `AuditLog` database model (user_id, action, timestamp, details).
        *   Ensuring that all sensitive actions (consent changes, scan submissions, deletion requests, authentication events) are logged.
        *   **CRITICAL:** Verification that audit logs are **append-only and immutable**. No updates or deletes should be possible.
        *   Access control: who can view audit logs (e.g., only authorized administrators, or users for their own actions).

### 2.2. Data Models & Database (PostgreSQL + SQLAlchemy + Alembic) - Status and Gaps

*   **Status:** The `[STACK]` decision confirms PostgreSQL, SQLAlchemy, and Alembic. This is a robust choice.
*   **Audit Focus:**
    *   **Schema Design:** Verify the existence and correctness of models for `User`, `ConsentRecord`, `ScanSession`, `ScanResult`, `AuditLog`, and potentially `Pseudonym` if a separate anonymization layer is used.
    *   **Relationships:** Ensure foreign key relationships are correctly defined (e.g., `ScanSession` to `User`, `ScanResult` to `ScanSession`).
    *   **Constraints:** Verify unique constraints (e.g., `session_id`) and non-null constraints are applied where appropriate.
    *   **Immutability:** Confirm that `ConsentRecord` and `AuditLog` tables are designed to be append-only (e.g., no `UPDATE` operations, only `INSERT`).
    *   **Alembic Migrations:** Verify that all schema changes are managed via Alembic migrations and that the migration history is clean and reversible.

### 2.3. Core Logic & Architecture - Status and Gaps

*   **Anonymization Strategy:**
    *   **Status:** Explicitly stated as a core architectural principle (`[ARCHITECTURE]`).
    *   **Audit Focus:** This is arguably the most critical and complex piece. Verification of the exact mechanism for anonymizing metrics while retaining the ability to link them to a user for their history *without storing PII directly with metrics*. This could involve:
        *   One-way hashing of user IDs for `anonymized_user_id`.
        *   A `Pseudonym` service that maps internal user IDs to anonymized IDs.
        *   Clear separation of concerns for PII vs. anonymized data.
*   **Data Deletion Process (30-day hold):**
    *   **Status:** Defined in `[COMPLIANCE]`.
    *   **Audit Focus:** Verification of the background worker or scheduled task responsible for processing deletion requests after the 30-day period. This includes testing the idempotency and reliability of the deletion process.
*   **Trend Delta Calculation:**
    *   **Status:** Defined in `[PRODUCT]` and required for `/api/v1/scans/history`.
    *   **Audit Focus:** Verification of the algorithm for calculating week-over-week deltas, including edge cases (e.g., first scan, gaps in data, partial weeks).
*   **Immutability (Consent, Audit Logs):**
    *   **Status:** Defined in `[ARCHITECTURE]` and `[COMPLIANCE]`.
    *   **Audit Focus:** Ensure that the application layer (FastAPI services) and the database schema (via ORM or raw SQL constraints) enforce append-only behavior for these critical records.
*   **Security (JWT via python-jose):**
    *   **Status:** Defined in `[STACK]`.
    *   **Audit Focus:**
        *   Verification of JWT issuance, validation, and refresh mechanisms.
        *   Ensuring all protected endpoints require valid JWTs.
        *   Proper handling of secrets (JWT keys) via environment variables.
        *   Role-based access control if different user types (e.g., admin) are introduced.

### 2.4. Testing (Pytest) - Status and Gaps

*   **Status:** `[ENG]` identity explicitly requires tests.
*   **Audit Focus:**
    *   **Unit Tests:** Verify presence and coverage for all core domain logic, services, and utility functions (e.g., anonymization, trend calculation).
    *   **Integration Tests:** Verify presence and coverage for API endpoints, database interactions, and authentication/authorization flows.
    *   **Test Data:** Ensure tests use isolated, reproducible test data (e.g., via `pytest-factoryboy`, Testcontainers for PostgreSQL).
    *   **Edge Cases:** Verify tests cover error conditions, invalid inputs, and boundary conditions.

### 2.5. Project Structure (FastAPI) - Status and Gaps

*   **Status:** `backend/` directory is defined in `Project Structure`.
*   **Audit Focus:**
    *   Verify a clear separation of concerns (e.g., `models/`, `schemas/`, `routers/`, `services/`, `dependencies/`, `database/`).
    *   Modularity for different functional areas (e.g., `consent/`, `scans/`, `audit/`).
    *   Adherence to FastAPI best practices.

---

## 3. Mobile App Integration (React Native / Expo) - from Backend Perspective

While the mobile app code is not directly auditable by `eng` in this context, its interaction with the backend is crucial.

### 3.1. API Consumption

*   **Status:** The mobile app will be the primary consumer of the backend API.
*   **Audit Focus (from backend perspective):**
    *   Ensure backend API responses are consistent, well-documented (e.g., with OpenAPI via `fastapi-users` or `APIRouter` tags), and easy for the mobile team to consume.
    *   Error messages from the backend should be clear and actionable for the mobile app to display to the user.

### 3.2. On-Device Processing & Quality Gates

*   **Status:** `[ARCHITECTURE]` and `[QUALITY_GATES]` confirm on-device processing and quality checks.
*   **Audit Focus (from backend perspective):**
    *   The backend should expect pre-processed, validated metrics.
    *   The `PUT /api/v1/scans/sessions/{id}/complete` endpoint must correctly handle `quality_status` and `rejection_reason` fields submitted by the mobile app.
    *   Backend should *not* attempt to re-validate biometric signal quality, only the format and completeness of the submitted metrics.

---

## 4. Compliance (India DPDP Act 2023) - Status and Gaps

The `[COMPLIANCE]` decision explicitly targets India DPDP Act 2023.

*   **Consent Management:**
    *   **Status:** Covered by `POST /api/v1/consent` and `POST /api/v1/consent/revoke`.
    *   **Audit Focus:** Verification of explicit, informed consent capture and the append-only history of consent records.
*   **Data Anonymization:**
    *   **Status:** Core to `[ARCHITECTURE]`.
    *   **Audit Focus:** **CRITICAL.** Verification of the anonymization strategy for biometric metrics (`anonymized_user_id`) to ensure no direct PII is stored with the metrics. This includes ensuring the *process* itself is robust and not easily reversible.
*   **Data Deletion:**
    *   **Status:** Covered by `POST /api/v1/consent/deletion-request`.
    *   **Audit Focus:** **CRITICAL.** Verification of the 30-day hold period and the actual data deletion process, ensuring it adheres to the legal requirements.

---

## 5. Summary of Gaps & Recommendations

### 5.1. Immediate Priorities for Verification/Implementation

1.  **Anonymization Strategy:** The specific implementation of how user IDs are anonymized for metric storage while allowing history retrieval is paramount. This needs a detailed design and rigorous testing.
2.  **Data Deletion with 30-day Hold:** The background process for handling deletion requests after the mandated 30-day hold is complex and critical for DPDP compliance. This requires careful implementation and testing.
3.  **Trend Delta Calculation:** The logic for `GET /api/v1/scans/history` to calculate week-over-week deltas is a core product feature and requires precise implementation.
4.  **Immutability Enforcement:** Ensure `ConsentRecord` and `AuditLog` tables and associated service methods strictly enforce append-only behavior.
5.  **Comprehensive Testing:** Given the privacy and health-related nature of the data, robust unit and integration tests for all core logic and API endpoints are non-negotiable.

### 5.2. Next Steps

1.  **Detailed Code Review:** An actual code review of the `pranascan-mvp` repository is required to verify the implementation details against the audit points raised in this report.
2.  **Documentation:** Ensure that the anonymization strategy, data deletion process, and trend calculation logic are thoroughly documented.
3.  **Security Audit:** A dedicated security audit focusing on JWT implementation, data access controls, and potential vulnerabilities should be conducted.
4.  **Performance Testing:** Once core features are implemented, performance testing of API endpoints (especially `/scans/history` and `/scans/sessions/{id}/complete`) should be conducted to meet the `< 15 seconds end-to-end` target.

This audit report provides a framework for evaluating the current state and guiding future development for the `pranascan` project.

---
