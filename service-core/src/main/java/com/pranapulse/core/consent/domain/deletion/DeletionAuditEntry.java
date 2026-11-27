package com.pranapulse.core.consent.domain.deletion;

import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

/** One row of {@code core.deletion_audit} (V10). Carries no personal data: ids, counts and states only. */
public record DeletionAuditEntry(
        UUID deletionRequestId,
        Instant createdAt,
        DeletionState fromState,
        DeletionState toState,
        String store,
        Long rowsAffected,
        String actor,
        String note) {

    public DeletionAuditEntry {
        Objects.requireNonNull(deletionRequestId, "deletionRequestId");
        Objects.requireNonNull(createdAt, "createdAt");
        Objects.requireNonNull(toState, "toState");
        if (actor == null || actor.isBlank() || actor.length() > 128) {
            throw new IllegalArgumentException("actor is required (max 128 characters)");
        }
        if (store != null && store.length() > 48) {
            throw new IllegalArgumentException("store exceeds 48 characters");
        }
        if (note != null && note.length() > 512) {
            throw new IllegalArgumentException("note exceeds 512 characters");
        }
        if (rowsAffected != null && rowsAffected < 0) {
            throw new IllegalArgumentException("rowsAffected cannot be negative");
        }
    }
}
