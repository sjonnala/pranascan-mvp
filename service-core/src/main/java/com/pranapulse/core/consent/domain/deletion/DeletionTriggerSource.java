package com.pranapulse.core.consent.domain.deletion;

/** Why the deletion started. V10 backfills existing requests as USER_REQUEST. */
public enum DeletionTriggerSource {
    USER_REQUEST,
    CONSENT_WITHDRAWAL,
    RETENTION_EXPIRY,
    OPERATOR
}
