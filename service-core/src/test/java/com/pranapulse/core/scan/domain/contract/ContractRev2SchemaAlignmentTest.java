package com.pranapulse.core.scan.domain.contract;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.pranapulse.core.consent.domain.ProcessingPurpose;
import com.pranapulse.core.consent.domain.deletion.DeletionState;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;

/** Persisted enum names must be exactly the values the Flyway CHECK constraints accept. */
class ContractRev2SchemaAlignmentTest {

    private static String migration(String name) throws IOException {
        try (InputStream in = ContractRev2SchemaAlignmentTest.class.getResourceAsStream("/db/migration/" + name)) {
            assertNotNull(in, name + " must be on the classpath");
            return new String(in.readAllBytes(), StandardCharsets.UTF_8);
        }
    }

    private static void assertQuoted(String sql, Stream<String> values, String what) {
        values.forEach(v -> assertTrue(sql.contains("'" + v + "'"), what + " value " + v + " missing from SQL"));
    }

    @Test
    void v8ChecksAcceptEveryPersistedValue() throws IOException {
        String v8 = migration("V8__scan_contract_rev2.sql");
        assertQuoted(v8, Arrays.stream(HeartRateStatus.values()).map(HeartRateStatus::toColumn)
                .filter(java.util.Objects::nonNull), "hr_status");
        assertQuoted(v8, Arrays.stream(LockState.values()).map(LockState::toColumn)
                .filter(java.util.Objects::nonNull), "ae_lock/awb_lock");
        assertQuoted(v8, Arrays.stream(FrameTimestampSource.values()).map(FrameTimestampSource::toColumn)
                .filter(java.util.Objects::nonNull), "frame_timestamp_source");
        assertQuoted(v8, Stream.of(QualityScoreBasis.LEGACY_MAX_OF_MOBILE_AND_SPECTRAL.toColumn()), "backfill basis");
    }

    @Test
    void v9AndV10MatchConsentAndDeletionVocabulary() throws IOException {
        assertQuoted(migration("V9__consent_purposes.sql"),
                Stream.of(ProcessingPurpose.LEGACY_BUNDLED.purposeId()), "purpose_id backfill");
        assertQuoted(migration("V10__deletion_lifecycle.sql"),
                Arrays.stream(DeletionState.values()).map(Enum::name), "deletion state");
    }

    @Test
    void userFacingSummariesStayWellnessIndicators() {
        List<String> texts = Stream.of(
                        Arrays.stream(HeartRateStatus.values()).map(HeartRateStatus::userFacingSummary),
                        Arrays.stream(VoiceStatus.values()).map(VoiceStatus::userFacingSummary),
                        Arrays.stream(AnemiaNotApplicableReason.values()).map(AnemiaNotApplicableReason::userFacingSummary))
                .flatMap(s -> s)
                .toList();
        texts.forEach(t -> assertTrue(WellnessWording.isNonDiagnostic(t), "diagnostic wording: " + t));
        assertTrue(!WellnessWording.isNonDiagnostic("You have anemia"));
        // Current intelligence labels (anemia_screen.py) all pass the guard.
        Stream.of("normal_range", "below_typical_range", "consider_followup", "low_confidence_environment")
                .forEach(label -> assertTrue(WellnessWording.isNonDiagnostic(label), label));
    }
}
