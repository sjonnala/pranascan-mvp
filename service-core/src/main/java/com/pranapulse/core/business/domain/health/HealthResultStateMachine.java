package com.pranapulse.core.business.domain.health;

import java.time.Instant;
import java.util.Objects;

public final class HealthResultStateMachine {

    public HealthResultState resolve(HealthResultSnapshot snapshot, Instant asOf) {
        Objects.requireNonNull(snapshot, "snapshot must not be null");
        Objects.requireNonNull(asOf, "asOf must not be null");

        if (snapshot.verifiedAt() != null) {
            return new ResultVerified(
                    snapshot.resultId(),
                    snapshot.userId(),
                    snapshot.recordedAt(),
                    snapshot.verifiedAt(),
                    snapshot.verifiedBy()
            );
        }

        ResultPending pending = new ResultPending(
                snapshot.resultId(),
                snapshot.userId(),
                snapshot.recordedAt(),
                snapshot.expiresAt()
        );

        if (!asOf.isBefore(snapshot.expiresAt())) {
            return pending.expire(asOf, "Verification window elapsed.");
        }

        return pending;
    }
}
