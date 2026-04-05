package com.pranapulse.core.consent.web;

import com.pranapulse.core.consent.application.ConsentStatusSnapshot;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import java.time.Instant;
import java.util.UUID;

@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record ConsentStatusResponse(
        UUID userId,
        boolean hasActiveConsent,
        String consentVersion,
        Instant grantedAt,
        Instant revokedAt,
        boolean deletionRequested,
        Instant deletionScheduledAt
) {

    public static ConsentStatusResponse from(ConsentStatusSnapshot snapshot) {
        return new ConsentStatusResponse(
                snapshot.userId(),
                snapshot.hasActiveConsent(),
                snapshot.consentVersion(),
                snapshot.grantedAt(),
                snapshot.revokedAt(),
                snapshot.deletionRequested(),
                snapshot.deletionScheduledAt()
        );
    }
}
