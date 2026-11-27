package com.pranapulse.core.consent.domain.deletion;

import com.pranapulse.core.consent.domain.DeletionRequestStatus;
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

/**
 * Immutable snapshot of one DPDP deletion request's lifecycle (V10 columns on
 * {@code core.deletion_requests}). Every change goes through {@link #transitionTo}, which returns
 * the next snapshot together with the audit entry that must be stored with it.
 */
public record DeletionLifecycle(
        UUID requestId,
        DeletionState state,
        DeletionScope scope,
        DeletionTriggerSource triggerSource,
        Instant createdAt,
        Instant targetAt,
        Instant slaDueAt,
        Instant completedAt,
        String legalHoldReason,
        String verifiedBy) {

    /** Runbook: aim to finish within 30 days of the request. */
    public static final Duration TARGET = Duration.ofDays(30);
    /** Runbook: hard SLA of 90 days from the request. */
    public static final Duration SLA = Duration.ofDays(90);

    public DeletionLifecycle {
        Objects.requireNonNull(requestId, "requestId");
        Objects.requireNonNull(state, "state");
        Objects.requireNonNull(scope, "scope");
        Objects.requireNonNull(triggerSource, "triggerSource");
        Objects.requireNonNull(createdAt, "createdAt");
        Objects.requireNonNull(targetAt, "targetAt");
        Objects.requireNonNull(slaDueAt, "slaDueAt");
        if (state == DeletionState.COMPLETED && completedAt == null) {
            throw new IllegalArgumentException("a completed deletion needs completedAt");
        }
        if (state != DeletionState.COMPLETED && completedAt != null) {
            throw new IllegalArgumentException("completedAt is only set once the deletion is completed");
        }
        if (state == DeletionState.ON_HOLD_LEGAL && (legalHoldReason == null || legalHoldReason.isBlank())) {
            throw new IllegalArgumentException("a legal hold needs a reason");
        }
        if (legalHoldReason != null && legalHoldReason.length() > 256) {
            throw new IllegalArgumentException("legalHoldReason exceeds 256 characters");
        }
    }

    /** A new request: RECEIVED, with the runbook's 30-day target and 90-day SLA. */
    public static DeletionLifecycle received(UUID requestId, DeletionScope scope,
                                             DeletionTriggerSource trigger, Instant createdAt) {
        return new DeletionLifecycle(requestId, DeletionState.RECEIVED, scope, trigger, createdAt,
                createdAt.plus(TARGET), createdAt.plus(SLA), null, null, null);
    }

    /** Reads a row written before V10 the same way V10's backfill does. */
    public static DeletionLifecycle fromLegacyRow(UUID requestId, DeletionRequestStatus status,
                                                  Instant createdAt, Instant purgedAt) {
        DeletionState state = DeletionState.fromLegacyStatus(status);
        Instant completed = state == DeletionState.COMPLETED ? Objects.requireNonNullElse(purgedAt, createdAt) : null;
        return new DeletionLifecycle(requestId, state, DeletionScope.ACCOUNT_ALL, DeletionTriggerSource.USER_REQUEST,
                createdAt, createdAt.plus(TARGET), createdAt.plus(SLA), completed, null, null);
    }

    public Transition transitionTo(DeletionState target, String actor, String note, Instant at) {
        return transitionTo(target, actor, note, at, null, null, null);
    }

    /**
     * Moves to {@code target} if the runbook allows it. {@code legalHoldReason} is required when
     * entering ON_HOLD_LEGAL; {@code store}/{@code rowsAffected} describe a purge step, if any.
     */
    public Transition transitionTo(DeletionState target, String actor, String note, Instant at,
                                   String legalHoldReasonForHold, String store, Long rowsAffected) {
        Objects.requireNonNull(at, "at");
        if (!state.canTransitionTo(target)) {
            throw new IllegalStateException("illegal deletion transition " + state + " -> " + target);
        }
        if (at.isBefore(createdAt)) {
            throw new IllegalArgumentException("transition time precedes the request");
        }
        String hold = target == DeletionState.ON_HOLD_LEGAL ? legalHoldReasonForHold : null;
        String verifier = target == DeletionState.VERIFIED ? actor : verifiedBy;
        Instant completed = target == DeletionState.COMPLETED ? at : null;
        DeletionLifecycle next = new DeletionLifecycle(requestId, target, scope, triggerSource, createdAt,
                targetAt, slaDueAt, completed, hold, verifier);
        DeletionAuditEntry audit = new DeletionAuditEntry(requestId, at, state, target, store, rowsAffected, actor, note);
        return new Transition(next, audit);
    }

    public DeletionRequestStatus legacyStatus() {
        return state.toLegacyStatus();
    }

    /** Past the 90-day SLA and still not finished (rejected requests are finished too). */
    public boolean isSlaBreached(Instant now) {
        return !state.isTerminal() && now.isAfter(slaDueAt);
    }

    public boolean isPastTarget(Instant now) {
        return !state.isTerminal() && now.isAfter(targetAt);
    }

    /** The next snapshot plus the audit row that must be written in the same transaction. */
    public record Transition(DeletionLifecycle lifecycle, DeletionAuditEntry audit) {
    }
}
