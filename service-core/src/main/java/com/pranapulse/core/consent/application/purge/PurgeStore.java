package com.pranapulse.core.consent.application.purge;

import com.pranapulse.core.consent.domain.deletion.DeletionScope;
import java.util.UUID;

/**
 * One data store the purge must clear. Implementations must be idempotent: running a step twice
 * for the same request deletes nothing extra and reports {@code complete = true} again.
 */
public interface PurgeStore {

    /** Short, stable id written to {@code deletion_audit.store} (max 48 characters). */
    String storeId();

    PurgeStepResult purge(UUID deletionRequestId, UUID userId, DeletionScope scope);
}
