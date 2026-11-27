package com.pranapulse.core.consent.application.purge;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.pranapulse.core.consent.domain.deletion.DeletionLifecycle;
import com.pranapulse.core.consent.domain.deletion.DeletionScope;
import com.pranapulse.core.consent.domain.deletion.DeletionState;
import com.pranapulse.core.consent.domain.deletion.DeletionTriggerSource;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class DeletionPurgeCoordinatorTest {

    private static final UUID REQUEST = UUID.fromString("00000000-0000-0000-0000-0000000000d1");
    private static final UUID USER = UUID.fromString("00000000-0000-0000-0000-000000000001");
    private static final Instant T0 = Instant.parse("2026-11-01T00:00:00Z");

    /** Idempotent fake: deletes rows on the first call, reports 0 rows (still complete) afterwards. */
    private static final class FakeStore implements PurgeStore {
        private final String id;
        private long remaining;
        private final boolean reachable;
        int calls;

        FakeStore(String id, long rows, boolean reachable) {
            this.id = id;
            this.remaining = rows;
            this.reachable = reachable;
        }

        @Override
        public String storeId() {
            return id;
        }

        @Override
        public PurgeStepResult purge(UUID deletionRequestId, UUID userId, DeletionScope scope) {
            calls++;
            if (!reachable) {
                return new PurgeStepResult(id, 0, false, "store unavailable");
            }
            long deleted = remaining;
            remaining = 0;
            return new PurgeStepResult(id, deleted, true, null);
        }
    }

    private static DeletionLifecycle inProgress() {
        DeletionLifecycle l = DeletionLifecycle.received(REQUEST, DeletionScope.ACCOUNT_ALL,
                DeletionTriggerSource.USER_REQUEST, T0);
        for (DeletionState s : List.of(DeletionState.VERIFIED, DeletionState.NOTICE_SENT, DeletionState.IN_PROGRESS)) {
            l = l.transitionTo(s, "system:test", null, T0).lifecycle();
        }
        return l;
    }

    @Test
    void purgesEveryStoreThenMovesToPrimaryPurged() {
        FakeStore core = new FakeStore("core", 12, true);
        FakeStore intelligence = new FakeStore("intelligence.public", 3, true);
        DeletionPurgeCoordinator worker = new DeletionPurgeCoordinator(List.of(core, intelligence), Duration.ofDays(35));

        List<DeletionLifecycle.Transition> steps = worker.advance(inProgress(), USER, T0.plusSeconds(60));

        assertEquals(3, steps.size());
        assertEquals("core", steps.get(0).audit().store());
        assertEquals(12L, steps.get(0).audit().rowsAffected());
        assertEquals("intelligence.public", steps.get(1).audit().store());
        assertEquals(DeletionState.PRIMARY_PURGED, steps.get(2).lifecycle().state());
        steps.forEach(t -> assertEquals(DeletionPurgeCoordinator.ACTOR, t.audit().actor()));
    }

    @Test
    void unreachableStoreKeepsRequestInProgressForRetry() {
        FakeStore core = new FakeStore("core", 12, true);
        FakeStore objects = new FakeStore("object-storage", 0, false);
        DeletionPurgeCoordinator worker = new DeletionPurgeCoordinator(List.of(core, objects), Duration.ofDays(35));

        List<DeletionLifecycle.Transition> first = worker.advance(inProgress(), USER, T0);
        assertEquals(2, first.size());
        assertEquals(DeletionState.IN_PROGRESS, first.get(1).lifecycle().state());

        // Retry is idempotent: core reports zero further rows.
        List<DeletionLifecycle.Transition> retry = worker.advance(first.get(1).lifecycle(), USER, T0.plusSeconds(3600));
        assertEquals(0L, retry.get(0).audit().rowsAffected());
        assertEquals(2, core.calls);
    }

    @Test
    void completesOnlyAfterBackupRetention() {
        DeletionPurgeCoordinator worker = new DeletionPurgeCoordinator(
                List.of(new FakeStore("core", 1, true)), Duration.ofDays(35));
        DeletionLifecycle purged = worker.advance(inProgress(), USER, T0).get(1).lifecycle();
        DeletionLifecycle expiring = worker.advance(purged, USER, T0).get(0).lifecycle();
        assertEquals(DeletionState.BACKUPS_EXPIRING, expiring.state());

        assertTrue(worker.advance(expiring, USER, T0.plus(Duration.ofDays(34)), T0).isEmpty());
        DeletionLifecycle done = worker.advance(expiring, USER, T0.plus(Duration.ofDays(35)), T0).get(0).lifecycle();
        assertEquals(DeletionState.COMPLETED, done.state());
        assertTrue(worker.advance(done, USER, T0.plus(Duration.ofDays(40))).isEmpty());
    }

    @Test
    void doesNothingBeforeVerificationOrDuringLegalHold() {
        DeletionPurgeCoordinator worker = new DeletionPurgeCoordinator(
                List.of(new FakeStore("core", 1, true)), Duration.ofDays(35));
        DeletionLifecycle received = DeletionLifecycle.received(REQUEST, DeletionScope.ACCOUNT_ALL,
                DeletionTriggerSource.USER_REQUEST, T0);
        assertTrue(worker.advance(received, USER, T0).isEmpty());
        DeletionLifecycle held = received.transitionTo(DeletionState.ON_HOLD_LEGAL, "ops", null, T0,
                "regulator query", null, null).lifecycle();
        assertTrue(worker.advance(held, USER, T0).isEmpty());
    }

    @Test
    void requiresAtLeastOneStore() {
        assertThrows(IllegalArgumentException.class, () -> new DeletionPurgeCoordinator(List.of(), Duration.ofDays(1)));
    }
}
