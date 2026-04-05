package com.pranapulse.core.business.domain.health;

import java.time.Instant;
import java.util.UUID;

public sealed interface HealthResultState permits ResultPending, ResultVerified, ResultExpired {

    UUID resultId();

    UUID userId();

    Instant recordedAt();

    Instant effectiveAt();

    HealthResultStatus status();

    boolean terminal();

    default ResultVerified verify(Instant verifiedAt, String verifiedBy) {
        throw new IllegalStateException("Only pending results can be verified.");
    }

    default ResultExpired expire(Instant expiredAt, String reason) {
        throw new IllegalStateException("Only pending results can expire.");
    }
}
