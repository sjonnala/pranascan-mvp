package com.pranapulse.core.consent.application.purge;

import com.pranapulse.core.consent.domain.deletion.DeletionLifecycle;
import com.pranapulse.core.consent.domain.deletion.DeletionState;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.UUID;

/**
 * Reference {@link DeletionPurgeWorker}: IN_PROGRESS runs every store's idempotent step and moves
 * to PRIMARY_PURGED once all report complete; PRIMARY_PURGED moves to BACKUPS_EXPIRING; and
 * BACKUPS_EXPIRING completes once the backup retention window since the primary purge has passed.
 * Verification and notice steps stay with the consent service. Plain class, not a Spring bean.
 */
public class DeletionPurgeCoordinator implements DeletionPurgeWorker {

    public static final String ACTOR = "system:deletion-purge-worker";

    private final List<PurgeStore> stores;
    private final Duration backupRetention;

    public DeletionPurgeCoordinator(List<PurgeStore> stores, Duration backupRetention) {
        this.stores = List.copyOf(Objects.requireNonNull(stores, "stores"));
        this.backupRetention = Objects.requireNonNull(backupRetention, "backupRetention");
        if (this.stores.isEmpty()) {
            throw new IllegalArgumentException("at least one purge store is required");
        }
        if (backupRetention.isNegative()) {
            throw new IllegalArgumentException("backupRetention cannot be negative");
        }
    }

    /**
     * @param primaryPurgedAt when the request entered PRIMARY_PURGED (from {@code deletion_audit});
     *                        only read in BACKUPS_EXPIRING
     */
    public List<DeletionLifecycle.Transition> advance(DeletionLifecycle lifecycle, UUID userId, Instant now,
                                                      Instant primaryPurgedAt) {
        return switch (lifecycle.state()) {
            case IN_PROGRESS -> purgeStores(lifecycle, userId, now);
            case PRIMARY_PURGED -> List.of(lifecycle.transitionTo(DeletionState.BACKUPS_EXPIRING, ACTOR,
                    "primary stores purged; waiting for backup rotation", now));
            case BACKUPS_EXPIRING -> backupsExpired(primaryPurgedAt, now)
                    ? List.of(lifecycle.transitionTo(DeletionState.COMPLETED, ACTOR, "backup retention elapsed", now))
                    : List.of();
            default -> List.of();
        };
    }

    @Override
    public List<DeletionLifecycle.Transition> advance(DeletionLifecycle lifecycle, UUID userId, Instant now) {
        return advance(lifecycle, userId, now, null);
    }

    private List<DeletionLifecycle.Transition> purgeStores(DeletionLifecycle lifecycle, UUID userId, Instant now) {
        List<DeletionLifecycle.Transition> transitions = new ArrayList<>();
        DeletionLifecycle current = lifecycle;
        boolean allComplete = true;
        for (PurgeStore store : stores) {
            PurgeStepResult result = store.purge(lifecycle.requestId(), userId, lifecycle.scope());
            allComplete &= result.complete();
            DeletionLifecycle.Transition step = current.transitionTo(DeletionState.IN_PROGRESS, ACTOR,
                    result.complete() ? "store purged" : "store step incomplete; will retry",
                    now, null, store.storeId(), result.rowsAffected());
            transitions.add(step);
            current = step.lifecycle();
        }
        if (allComplete) {
            transitions.add(current.transitionTo(DeletionState.PRIMARY_PURGED, ACTOR, "all primary stores purged", now));
        }
        return List.copyOf(transitions);
    }

    private boolean backupsExpired(Instant primaryPurgedAt, Instant now) {
        return primaryPurgedAt != null && !now.isBefore(primaryPurgedAt.plus(backupRetention));
    }
}
