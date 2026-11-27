package com.pranapulse.core.consent.domain.deletion;

import com.pranapulse.core.consent.domain.DeletionRequestStatus;
import java.util.EnumSet;
import java.util.Map;
import java.util.Set;

/**
 * Runbook deletion states. Main path:
 * RECEIVED → VERIFIED → NOTICE_SENT → IN_PROGRESS → PRIMARY_PURGED → BACKUPS_EXPIRING → COMPLETED,
 * with side exits REJECTED (terminal) and ON_HOLD_LEGAL (resumes into IN_PROGRESS). Names match
 * V10's {@code ck_deletion_requests_state}.
 */
public enum DeletionState {
    RECEIVED,
    VERIFIED,
    NOTICE_SENT,
    IN_PROGRESS,
    PRIMARY_PURGED,
    BACKUPS_EXPIRING,
    COMPLETED,
    REJECTED,
    ON_HOLD_LEGAL;

    private static final Map<DeletionState, Set<DeletionState>> NEXT = Map.of(
            RECEIVED, EnumSet.of(VERIFIED, REJECTED, ON_HOLD_LEGAL),
            VERIFIED, EnumSet.of(NOTICE_SENT, ON_HOLD_LEGAL),
            NOTICE_SENT, EnumSet.of(IN_PROGRESS, ON_HOLD_LEGAL),
            // IN_PROGRESS -> IN_PROGRESS records a retried store step.
            IN_PROGRESS, EnumSet.of(IN_PROGRESS, PRIMARY_PURGED, ON_HOLD_LEGAL),
            PRIMARY_PURGED, EnumSet.of(BACKUPS_EXPIRING),
            BACKUPS_EXPIRING, EnumSet.of(COMPLETED),
            ON_HOLD_LEGAL, EnumSet.of(IN_PROGRESS, REJECTED),
            COMPLETED, EnumSet.noneOf(DeletionState.class),
            REJECTED, EnumSet.noneOf(DeletionState.class));

    public boolean canTransitionTo(DeletionState target) {
        return target != null && NEXT.get(this).contains(target);
    }

    public Set<DeletionState> allowedNext() {
        Set<DeletionState> next = NEXT.get(this);
        return next.isEmpty() ? Set.of() : Set.copyOf(EnumSet.copyOf(next));
    }

    public boolean isTerminal() {
        return NEXT.get(this).isEmpty();
    }

    /** Status the current API keeps reporting: only COMPLETED is completed, everything else pending. */
    public DeletionRequestStatus toLegacyStatus() {
        return this == COMPLETED ? DeletionRequestStatus.COMPLETED : DeletionRequestStatus.PENDING;
    }

    /** Same mapping V10's backfill applies to existing rows. */
    public static DeletionState fromLegacyStatus(DeletionRequestStatus status) {
        if (status == null) {
            return RECEIVED;
        }
        return switch (status) {
            case COMPLETED -> COMPLETED;
            case FAILED -> IN_PROGRESS; // retryable; failure_reason is kept
            case PENDING -> RECEIVED;
        };
    }
}
