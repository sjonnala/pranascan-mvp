package com.pranapulse.core.business.domain.health;

import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

public record ResultVerified(
        UUID resultId,
        UUID userId,
        Instant recordedAt,
        Instant verifiedAt,
        String verifiedBy
) implements HealthResultState {

    public ResultVerified {
        Objects.requireNonNull(resultId, "resultId must not be null");
        Objects.requireNonNull(userId, "userId must not be null");
        Objects.requireNonNull(recordedAt, "recordedAt must not be null");
        Objects.requireNonNull(verifiedAt, "verifiedAt must not be null");
        if (verifiedAt.isBefore(recordedAt)) {
            throw new IllegalArgumentException("verifiedAt cannot be before recordedAt.");
        }

        if (verifiedBy == null || verifiedBy.isBlank()) {
            throw new IllegalArgumentException("verifiedBy must not be blank.");
        }
        verifiedBy = verifiedBy.trim();
    }

    @Override
    public Instant effectiveAt() {
        return verifiedAt;
    }

    @Override
    public HealthResultStatus status() {
        return HealthResultStatus.VERIFIED;
    }

    @Override
    public boolean terminal() {
        return true;
    }
}
