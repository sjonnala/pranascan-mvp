package com.pranapulse.core.scan.domain.contract;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

import java.util.List;
import org.junit.jupiter.api.Test;

class LegacyFlagParserTest {

    private static final List<String> REV1_ABSTAINED = List.of(
            "low_lighting", "hr_abstained", "no_reliable_pulse", "abstain_reason:low_spectral_snr",
            "mobile_quality_score:0.8312", "spectral_quality_score:0.1800", "spectral_snr_db:1.9",
            "anemia_not_applicable", "voice_clip_fraction:0.012", "voice_mains_hum_notched:2");

    @Test
    void readsAbstentionFromEncodedFlags() {
        HeartRateAssessment rppg = LegacyFlagParser.rppgFrom(REV1_ABSTAINED);
        assertEquals(HeartRateStatus.ABSTAINED, rppg.status());
        assertEquals(HrAbstentionReason.LOW_SPECTRAL_SNR, rppg.abstentionReason());
        assertNull(rppg.hrBpm());
    }

    @Test
    void noAbstentionFlagMeansUnknownNotMeasured() {
        assertEquals(HeartRateStatus.UNKNOWN, LegacyFlagParser.rppgFrom(List.of("low_lighting")).status());
        assertEquals(HeartRateStatus.UNKNOWN, LegacyFlagParser.rppgFrom(null).status());
    }

    @Test
    void readsQualityBreakdownAndIgnoresMalformedValues() {
        QualityBreakdown quality = LegacyFlagParser.qualityFrom(REV1_ABSTAINED);
        assertEquals(0.8312, quality.mobileQualityScore());
        assertEquals(0.18, quality.spectralQualityScore());
        assertEquals(1.9, quality.spectralSnrDb());
        assertEquals(QualityScoreBasis.SPECTRAL, quality.basis());

        QualityBreakdown junk = LegacyFlagParser.qualityFrom(List.of("mobile_quality_score:abc", "spectral_quality_score:7"));
        assertNull(junk.mobileQualityScore());
        assertNull(junk.spectralQualityScore());
        assertEquals(QualityScoreBasis.UNKNOWN, junk.basis());
    }

    @Test
    void stripsDiagnosticsSoScanNotesStayHumanReadable() {
        assertEquals(List.of("low_lighting"), LegacyFlagParser.stripEncoded(REV1_ABSTAINED));
        assertEquals(List.of("motion_detected", "low_lighting"),
                LegacyFlagParser.stripEncoded(List.of("motion_detected", "hrv_withheld_low_fps", "low_lighting")));
    }
}
