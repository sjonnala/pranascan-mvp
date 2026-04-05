package com.pranapulse.core.consent.application;

import java.time.Instant;
import java.util.UUID;

public record ConsentStatusSnapshot(
        UUID userId,
        boolean hasActiveConsent,
        String consentVersion,
        Instant grantedAt,
        Instant revokedAt,
        boolean deletionRequested,
        Instant deletionScheduledAt
) {
}
