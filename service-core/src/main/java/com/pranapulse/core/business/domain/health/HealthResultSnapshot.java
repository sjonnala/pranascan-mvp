package com.pranapulse.core.business.domain.health;

import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

public record HealthResultSnapshot(
        UUID resultId,
        UUID userId,
        Instant recordedAt,
        Instant expiresAt,
        Instant verifiedAt,
        String verifiedBy
) {

    public HealthResultSnapshot {
        Objects.requireNonNull(resultId, "resultId must not be null");
        Objects.requireNonNull(userId, "userId must not be null");
        Objects.requireNonNull(recordedAt, "recordedAt must not be null");
        Objects.requireNonNull(expiresAt, "expiresAt must not be null");

        if (!expiresAt.isAfter(recordedAt)) {
            throw new IllegalArgumentException("expiresAt must be after recordedAt.");
        }

        verifiedBy = normalize(verifiedBy);
        if (verifiedAt == null && verifiedBy != null) {
            throw new IllegalArgumentException("verifiedBy requires verifiedAt.");
        }
        if (verifiedAt != null) {
            if (verifiedAt.isBefore(recordedAt)) {
                throw new IllegalArgumentException("verifiedAt cannot be before recordedAt.");
            }
            if (!verifiedAt.isBefore(expiresAt)) {
                throw new IllegalArgumentException("verifiedAt must be before expiresAt.");
            }
            if (verifiedBy == null) {
                throw new IllegalArgumentException("verifiedBy must be provided when verifiedAt is set.");
            }
        }
    }

    private static String normalize(String value) {
        if (value == null) {
            return null;
        }
        String trimmed = value.trim();
        return trimmed.isEmpty() ? null : trimmed;
    }
}
