/**
 * Contract for the DPDP purge worker (T-401 §8 gap). Interfaces and a pure coordinator only:
 * no {@code @Scheduled} job, no Spring bean and no store implementation is registered, so
 * nothing runs yet. A later PR adds per-store {@link com.pranapulse.core.consent.application.purge.PurgeStore}
 * implementations (core schema, intelligence {@code public} schema, object storage) and the schedule.
 */
package com.pranapulse.core.consent.application.purge;
