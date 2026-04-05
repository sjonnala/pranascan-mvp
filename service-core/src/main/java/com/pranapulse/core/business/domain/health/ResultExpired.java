package com.pranapulse.core.business.domain.health;

import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

public record ResultExpired(
        UUID resultId,
        UUID userId,
        Instant recordedAt,
        Instant expiryDeadline,
        Instant expiredAt,
        String reason
) implements HealthResultState {

    public ResultExpired {
        Objects.requireNonNull(resultId, "resultId must not be null");
        Objects.requireNonNull(userId, "userId must not be null");
        Objects.requireNonNull(recordedAt, "recordedAt must not be null");
        Objects.requireNonNull(expiryDeadline, "expiryDeadline must not be null");
        Objects.requireNonNull(expiredAt, "expiredAt must not be null");
        if (!expiryDeadline.isAfter(recordedAt)) {
            throw new IllegalArgumentException("expiryDeadline must be after recordedAt.");
        }
        if (expiredAt.isBefore(expiryDeadline)) {
            throw new IllegalArgumentException("expiredAt must be on or after expiryDeadline.");
        }
        if (reason == null || reason.isBlank()) {
            throw new IllegalArgumentException("reason must not be blank.");
        }
        reason = reason.trim();
    }

    @Override
    public Instant effectiveAt() {
        return expiredAt;
    }

    @Override
    public HealthResultStatus status() {
        return HealthResultStatus.EXPIRED;
    }

    @Override
    public boolean terminal() {
        return true;
    }
}
