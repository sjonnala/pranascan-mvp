package com.pranapulse.core.business.domain.health;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Instant;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class HealthResultStateMachineTest {

    private final HealthResultStateMachine stateMachine = new HealthResultStateMachine();

    @Test
    void pendingResultCanTransitionToVerified() {
        ResultPending pending = new ResultPending(
                UUID.randomUUID(),
                UUID.randomUUID(),
                Instant.parse("2026-04-04T12:00:00Z"),
                Instant.parse("2026-04-05T12:00:00Z")
        );

        ResultVerified verified = pending.verify(
                Instant.parse("2026-04-04T16:30:00Z"),
                "clinical-review-bot"
        );

        assertEquals(HealthResultStatus.VERIFIED, verified.status());
        assertEquals("clinical-review-bot", verified.verifiedBy());
        assertTrue(verified.terminal());
    }

    @Test
    void stateMachineResolvesExpiredResultAfterDeadline() {
        HealthResultSnapshot snapshot = new HealthResultSnapshot(
                UUID.randomUUID(),
                UUID.randomUUID(),
                Instant.parse("2026-04-04T12:00:00Z"),
                Instant.parse("2026-04-04T18:00:00Z"),
                null,
                null
        );

        HealthResultState resolved = stateMachine.resolve(
                snapshot,
                Instant.parse("2026-04-04T18:05:00Z")
        );

        ResultExpired expired = assertInstanceOf(ResultExpired.class, resolved);
        assertEquals(HealthResultStatus.EXPIRED, expired.status());
        assertEquals("Verification window elapsed.", expired.reason());
        assertTrue(expired.terminal());
    }

    @Test
    void stateMachineResolvesVerifiedSnapshot() {
        HealthResultSnapshot snapshot = new HealthResultSnapshot(
                UUID.randomUUID(),
                UUID.randomUUID(),
                Instant.parse("2026-04-04T12:00:00Z"),
                Instant.parse("2026-04-04T18:00:00Z"),
                Instant.parse("2026-04-04T13:00:00Z"),
                "reviewer-42"
        );

        HealthResultState resolved = stateMachine.resolve(
                snapshot,
                Instant.parse("2026-04-04T14:00:00Z")
        );

        ResultVerified verified = assertInstanceOf(ResultVerified.class, resolved);
        assertEquals("reviewer-42", verified.verifiedBy());
        assertEquals(HealthResultStatus.VERIFIED, verified.status());
    }
}
