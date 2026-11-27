package com.pranapulse.core.scan.domain.contract;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import org.junit.jupiter.api.Test;

class ScanContractRev2ValueObjectsTest {

    @Test
    void legacyRowWithHeartRateButNoStatusReadsAsUnknownNotMeasured() {
        HeartRateAssessment legacy = HeartRateAssessment.fromColumns(null, null, null, null, 71.0, 42.0);

        assertEquals(HeartRateStatus.UNKNOWN, legacy.status());
        assertFalse(legacy.usableForTrends());
        assertNull(legacy.status().toColumn());
        assertEquals(71.0, legacy.hrBpm());
    }

    @Test
    void legacyRowQualityBasisComesFromV8Backfill() {
        QualityBreakdown legacy = QualityBreakdown.legacy("LEGACY_MAX_OF_MOBILE_AND_SPECTRAL");
        QualityBreakdown overlap = QualityBreakdown.legacy(null);

        assertEquals(QualityScoreBasis.LEGACY_MAX_OF_MOBILE_AND_SPECTRAL, legacy.basis());
        assertEquals(QualityScoreBasis.UNKNOWN, overlap.basis());
        assertFalse(legacy.basis().comparableWith(QualityScoreBasis.SPECTRAL));
        assertFalse(overlap.basis().comparableWith(QualityScoreBasis.UNKNOWN));
        assertTrue(QualityScoreBasis.SPECTRAL.comparableWith(QualityScoreBasis.SPECTRAL));
    }

    @Test
    void skippedPulseReadingCannotCarryValues() {
        assertThrows(IllegalArgumentException.class, () -> new HeartRateAssessment(
                HeartRateStatus.ABSTAINED, HrAbstentionReason.LOW_SPECTRAL_SNR, 30.0, false, 72.0, null));
        assertThrows(IllegalArgumentException.class, () -> new HeartRateAssessment(
                HeartRateStatus.MEASURED, HrAbstentionReason.FLAT_SIGNAL, 30.0, false, 72.0, null));
        assertThrows(IllegalArgumentException.class, () -> HeartRateAssessment.measured(72.0, 40.0, 12.0, true));

        HeartRateAssessment skipped = HeartRateAssessment.abstained(HrAbstentionReason.LOW_SPECTRAL_SNR, 14.9);
        assertEquals("ABSTAINED", skipped.status().toColumn());
        assertEquals("LOW_SPECTRAL_SNR", skipped.abstentionReason().toColumn());
        assertFalse(skipped.usableForTrends());
        assertTrue(HeartRateAssessment.measured(72.0, 41.0, 29.8, false).usableForTrends());
    }

    @Test
    void notApplicableAnemiaIndicatorCarriesNoLabelOrScore() {
        assertThrows(IllegalArgumentException.class, () -> new AnemiaAssessment(
                AnemiaApplicability.NOT_APPLICABLE, AnemiaNotApplicableReason.NO_CONJUNCTIVAL_ROI, "normal_range", null));
        AnemiaAssessment na = AnemiaAssessment.notApplicable(AnemiaNotApplicableReason.NO_CONJUNCTIVAL_ROI);
        assertEquals("NOT_APPLICABLE", na.applicability().toColumn());

        AnemiaAssessment legacy = AnemiaAssessment.fromColumns(null, null, "below_typical_range", 0.61);
        assertEquals(AnemiaApplicability.UNKNOWN, legacy.applicability());
    }

    @Test
    void voiceReasonsOnlyWhenAbstained() {
        assertThrows(IllegalArgumentException.class, () -> new VoiceAssessment(
                VoiceStatus.MEASURED, List.of(VoiceAbstentionReason.HIGH_NOISE), false, 0.01, false));
        assertThrows(IllegalArgumentException.class, () -> new VoiceAssessment(
                VoiceStatus.MEASURED, List.of(), false, 1.5, false));
        VoiceAssessment skipped = VoiceAssessment.abstained(List.of(VoiceAbstentionReason.HIGH_NOISE), true);
        assertEquals(List.of(VoiceAbstentionReason.HIGH_NOISE), skipped.abstentionReasons());
        assertEquals(VoiceStatus.UNKNOWN, new VoiceAssessment(null, null, false, null, false).status());
    }

    @Test
    void captureTimingAndDeviceProfileAcceptPr2AndLegacyShapes() {
        CaptureTiming timing = new CaptureTiming(29.7, 2.1, 33.7, FrameTimestampSource.fromRestValue("wall_clock"));
        assertEquals(FrameTimestampSource.WALL_CLOCK, timing.timestampSource());
        assertEquals(FrameTimestampSource.UNKNOWN, FrameTimestampSource.fromRestValue("gps"));
        assertThrows(IllegalArgumentException.class, () -> new CaptureTiming(-1.0, null, null, null));

        DeviceProfile legacy = DeviceProfile.legacy("Redmi 12", "1.4.0");
        assertEquals(DevicePlatform.UNKNOWN, legacy.platform());
        assertEquals(LockState.UNKNOWN, legacy.aeLock());
        assertNull(legacy.aeLock().toColumn());
    }

    @Test
    void contractRevisionTreatsAbsentAsRevOne() {
        assertEquals(ContractRevision.REV_1, ContractRevision.effective(0));
        assertEquals(ContractRevision.REV_2, ContractRevision.effective(2));
        assertFalse(ContractRevision.hasTypedAssessments(0));
        assertTrue(ContractRevision.hasTypedAssessments(2));
    }

    @Test
    void unknownColumnValuesNeverThrow() {
        assertEquals(HeartRateStatus.UNKNOWN, HeartRateStatus.fromColumn("maybe"));
        assertEquals(HrAbstentionReason.UNSPECIFIED, HrAbstentionReason.fromLegacyFlagValue("cosmic_rays"));
        assertEquals(VoiceStatus.UNKNOWN, VoiceStatus.fromColumn(" "));
    }
}
