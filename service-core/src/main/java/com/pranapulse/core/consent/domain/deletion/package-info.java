/**
 * DPDP deletion lifecycle (T-401 §8, DPDP runbook; persisted by Flyway V10).
 *
 * <p>The runbook's state machine lives here as pure domain logic: legal transitions, the 30-day
 * target and 90-day SLA, and an audit entry for every transition. Legacy
 * {@link com.pranapulse.core.consent.domain.DeletionRequestStatus} stays the public status of the
 * current API and is derived from the state. Not wired into {@code ConsentService} yet, so the
 * existing endpoints behave exactly as before.
 */
package com.pranapulse.core.consent.domain.deletion;
