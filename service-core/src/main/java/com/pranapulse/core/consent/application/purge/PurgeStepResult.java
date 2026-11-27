package com.pranapulse.core.consent.application.purge;

import java.util.Objects;

/** Outcome of one store's purge step. {@code note} must not contain personal data. */
public record PurgeStepResult(String storeId, long rowsAffected, boolean complete, String note) {

    public PurgeStepResult {
        Objects.requireNonNull(storeId, "storeId");
        if (rowsAffected < 0) {
            throw new IllegalArgumentException("rowsAffected cannot be negative");
        }
    }
}
