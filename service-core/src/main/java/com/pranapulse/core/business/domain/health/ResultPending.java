package com.pranapulse.core.business.domain.health;

import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

public record ResultPending(
        UUID resultId,
        UUID userId,
        Instant recordedAt,
        Instant expiresAt
) implements HealthResultState {

    public ResultPending {
        Objects.requireNonNull(resultId, "resultId must not be null");
        Objects.requireNonNull(userId, "userId must not be null");
        Objects.requireNonNull(recordedAt, "recordedAt must not be null");
        Objects.requireNonNull(expiresAt, "expiresAt must not be null");
        if (!expiresAt.isAfter(recordedAt)) {
            throw new IllegalArgumentException("expiresAt must be after recordedAt.");
        }
    }

    @Override
    public Instant effectiveAt() {
        return recordedAt;
    }

    @Override
    public HealthResultStatus status() {
        return HealthResultStatus.PENDING;
    }

    @Override
    public boolean terminal() {
        return false;
    }

    @Override
    public ResultVerified verify(Instant verifiedAt, String verifiedBy) {
        Objects.requireNonNull(verifiedAt, "verifiedAt must not be null");
        if (verifiedAt.isBefore(recordedAt)) {
            throw new IllegalArgumentException("verifiedAt cannot be before recordedAt.");
        }
        if (!verifiedAt.isBefore(expiresAt)) {
            throw new IllegalStateException("Pending results can only be verified before expiresAt.");
        }

        String normalizedVerifier = normalize(verifiedBy, "verifiedBy");
        return new ResultVerified(resultId, userId, recordedAt, verifiedAt, normalizedVerifier);
    }

    @Override
    public ResultExpired expire(Instant expiredAt, String reason) {
        Objects.requireNonNull(expiredAt, "expiredAt must not be null");
        if (expiredAt.isBefore(expiresAt)) {
            throw new IllegalArgumentException("expiredAt must be on or after expiresAt.");
        }

        String normalizedReason = normalize(reason, "reason");
        return new ResultExpired(resultId, userId, recordedAt, expiresAt, expiredAt, normalizedReason);
    }

    private static String normalize(String value, String fieldName) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(fieldName + " must not be blank.");
        }
        return value.trim();
    }
}
