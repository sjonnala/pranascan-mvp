package com.pranapulse.core.consent.domain.deletion;

/** What a deletion request erases. V10 backfills existing requests as ACCOUNT_ALL. */
public enum DeletionScope {
    ACCOUNT_ALL,
    /** Only data processed under one withdrawn purpose (for example research.model_training). */
    SINGLE_PURPOSE
}
