package com.pranapulse.core.consent.domain.deletion;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.pranapulse.core.consent.domain.DeletionRequestStatus;
import com.pranapulse.core.consent.domain.ProcessingPurpose;
import java.time.Instant;
import java.util.EnumSet;
import java.util.Set;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class DeletionLifecycleTest {

    private static final UUID ID = UUID.fromString("00000000-0000-0000-0000-0000000000d1");
    private static final Instant T0 = Instant.parse("2026-11-01T00:00:00Z");

    @Test
    void newRequestGetsRunbookTargetAndSla() {
        DeletionLifecycle lifecycle = DeletionLifecycle.received(ID, DeletionScope.ACCOUNT_ALL,
                DeletionTriggerSource.USER_REQUEST, T0);
        assertEquals(DeletionState.RECEIVED, lifecycle.state());
        assertEquals(Instant.parse("2026-12-01T00:00:00Z"), lifecycle.targetAt());
        assertEquals(Instant.parse("2027-01-30T00:00:00Z"), lifecycle.slaDueAt());
        assertEquals(DeletionRequestStatus.PENDING, lifecycle.legacyStatus());
    }

    @Test
    void legacyRowsMapExactlyLikeTheV10Backfill() {
        assertEquals(DeletionState.RECEIVED, DeletionState.fromLegacyStatus(DeletionRequestStatus.PENDING));
        assertEquals(DeletionState.COMPLETED, DeletionState.fromLegacyStatus(DeletionRequestStatus.COMPLETED));
        assertEquals(DeletionState.IN_PROGRESS, DeletionState.fromLegacyStatus(DeletionRequestStatus.FAILED));

        Instant purged = Instant.parse("2026-10-20T00:00:00Z");
        DeletionLifecycle completed = DeletionLifecycle.fromLegacyRow(ID, DeletionRequestStatus.COMPLETED, T0, purged);
        assertEquals(purged, completed.completedAt());
        assertEquals(DeletionScope.ACCOUNT_ALL, completed.scope());
        assertEquals(DeletionTriggerSource.USER_REQUEST, completed.triggerSource());

        DeletionLifecycle pending = DeletionLifecycle.fromLegacyRow(ID, DeletionRequestStatus.PENDING, T0, null);
        assertNull(pending.completedAt());
        assertEquals(DeletionRequestStatus.PENDING, pending.legacyStatus());
    }

    @Test
    void legacyStatusStaysPendingUntilCompleted() {
        for (DeletionState state : DeletionState.values()) {
            DeletionRequestStatus expected = state == DeletionState.COMPLETED
                    ? DeletionRequestStatus.COMPLETED : DeletionRequestStatus.PENDING;
            assertEquals(expected, state.toLegacyStatus(), state.name());
        }
    }

    @Test
    void happyPathWritesOneAuditEntryPerTransition() {
        DeletionLifecycle l = DeletionLifecycle.received(ID, DeletionScope.ACCOUNT_ALL, DeletionTriggerSource.USER_REQUEST, T0);
        DeletionState[] path = {DeletionState.VERIFIED, DeletionState.NOTICE_SENT, DeletionState.IN_PROGRESS,
                DeletionState.PRIMARY_PURGED, DeletionState.BACKUPS_EXPIRING, DeletionState.COMPLETED};
        Instant at = T0;
        for (DeletionState next : path) {
            at = at.plusSeconds(3600);
            DeletionLifecycle.Transition t = l.transitionTo(next, "system:test", null, at);
            assertEquals(l.state(), t.audit().fromState());
            assertEquals(next, t.audit().toState());
            assertEquals(ID, t.audit().deletionRequestId());
            l = t.lifecycle();
        }
        assertEquals(DeletionState.COMPLETED, l.state());
        assertEquals(at, l.completedAt());
        assertEquals("system:test", l.verifiedBy());
        assertEquals(DeletionRequestStatus.COMPLETED, l.legacyStatus());
        assertTrue(l.state().isTerminal());
    }

    @Test
    void illegalTransitionsAreRejected() {
        DeletionLifecycle l = DeletionLifecycle.received(ID, DeletionScope.ACCOUNT_ALL, DeletionTriggerSource.USER_REQUEST, T0);
        assertThrows(IllegalStateException.class, () -> l.transitionTo(DeletionState.COMPLETED, "a", null, T0));
        assertThrows(IllegalStateException.class, () -> l.transitionTo(DeletionState.PRIMARY_PURGED, "a", null, T0));
        assertThrows(IllegalArgumentException.class,
                () -> l.transitionTo(DeletionState.VERIFIED, "a", null, T0.minusSeconds(1)));
        assertThrows(IllegalArgumentException.class, () -> l.transitionTo(DeletionState.VERIFIED, " ", null, T0));
        assertFalse(DeletionState.COMPLETED.canTransitionTo(DeletionState.IN_PROGRESS));
        assertFalse(DeletionState.REJECTED.canTransitionTo(DeletionState.RECEIVED));
        assertEquals(Set.of(), DeletionState.COMPLETED.allowedNext());
    }

    @Test
    void legalHoldNeedsReasonAndResumesIntoInProgress() {
        DeletionLifecycle l = DeletionLifecycle.received(ID, DeletionScope.ACCOUNT_ALL, DeletionTriggerSource.USER_REQUEST, T0);
        assertThrows(IllegalArgumentException.class, () -> l.transitionTo(DeletionState.ON_HOLD_LEGAL, "ops", null, T0));

        DeletionLifecycle held = l.transitionTo(DeletionState.ON_HOLD_LEGAL, "ops", null, T0, "regulator query", null, null)
                .lifecycle();
        assertEquals("regulator query", held.legalHoldReason());
        assertEquals(EnumSet.of(DeletionState.IN_PROGRESS, DeletionState.REJECTED), EnumSet.copyOf(held.state().allowedNext()));

        DeletionLifecycle resumed = held.transitionTo(DeletionState.IN_PROGRESS, "ops", "hold lifted", T0.plusSeconds(60)).lifecycle();
        assertNull(resumed.legalHoldReason());
    }

    @Test
    void slaBreachIgnoresFinishedRequests() {
        DeletionLifecycle l = DeletionLifecycle.received(ID, DeletionScope.ACCOUNT_ALL, DeletionTriggerSource.USER_REQUEST, T0);
        Instant day91 = T0.plusSeconds(91L * 24 * 3600);
        assertTrue(l.isSlaBreached(day91));
        assertTrue(l.isPastTarget(T0.plusSeconds(31L * 24 * 3600)));
        DeletionLifecycle rejected = l.transitionTo(DeletionState.REJECTED, "ops", "identity not verified", T0).lifecycle();
        assertFalse(rejected.isSlaBreached(day91));
    }

    @Test
    void auditEntriesCarryNoFreeFormPersonalFieldsBeyondBoundedNotes() {
        DeletionAuditEntry entry = DeletionLifecycle.received(ID, DeletionScope.ACCOUNT_ALL,
                        DeletionTriggerSource.USER_REQUEST, T0)
                .transitionTo(DeletionState.VERIFIED, "system:verifier", "ok", T0).audit();
        assertNotNull(entry.createdAt());
        assertThrows(IllegalArgumentException.class, () -> new DeletionAuditEntry(ID, T0, null,
                DeletionState.VERIFIED, null, -1L, "a", null));
        assertThrows(IllegalArgumentException.class, () -> new DeletionAuditEntry(ID, T0, null,
                DeletionState.VERIFIED, null, null, "a", "x".repeat(513)));
    }

    @Test
    void legacyBundledConsentCoversScanAndTrendButNeverResearch() {
        assertEquals(ProcessingPurpose.LEGACY_BUNDLED, ProcessingPurpose.fromPurposeId(null));
        assertEquals(ProcessingPurpose.LEGACY_BUNDLED, ProcessingPurpose.fromPurposeId("legacy.bundled"));
        Set<ProcessingPurpose> legacy = ProcessingPurpose.LEGACY_BUNDLED.effectivePurposes();
        assertTrue(legacy.contains(ProcessingPurpose.SCAN_ONEOFF));
        assertTrue(legacy.contains(ProcessingPurpose.TREND_LONGITUDINAL));
        assertFalse(legacy.contains(ProcessingPurpose.RESEARCH_MODEL_TRAINING));
        assertThrows(IllegalArgumentException.class, () -> ProcessingPurpose.fromPurposeId("marketing.ads"));
    }
}
