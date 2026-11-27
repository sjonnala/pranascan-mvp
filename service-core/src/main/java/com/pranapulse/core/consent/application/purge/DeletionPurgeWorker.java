package com.pranapulse.core.consent.application.purge;

import com.pranapulse.core.consent.domain.deletion.DeletionLifecycle;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

/**
 * Advances one deletion request by at most one lifecycle step per call. Callers persist every
 * returned transition (state columns + audit row) in one transaction, then call again later.
 */
public interface DeletionPurgeWorker {

    /**
     * @return the transitions taken (empty when the request is waiting: not yet in progress,
     *         on legal hold, waiting for backups to expire, or finished)
     */
    List<DeletionLifecycle.Transition> advance(DeletionLifecycle lifecycle, UUID userId, Instant now);
}
