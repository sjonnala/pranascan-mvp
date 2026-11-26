package com.pranapulse.core.scan.application;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.pranapulse.core.scan.domain.ScanResult;
import com.pranapulse.core.scan.repository.ScanResultRepository;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

/**
 * Unit tests for {@link TrendAnalysisService#computeTrendAlert}.
 *
 * <p>Phase 0 voice safety (bug B19): voice jitter / shimmer fluctuations must never raise
 * the {@code consider_lab_followup} "Trend Notice", while HR, HRV and respiratory-rate
 * deviations still do.
 */
class TrendAnalysisServiceTest {

    private static final String TREND_ALERT = "consider_lab_followup";
    private static final TrendProperties PROPERTIES = new TrendProperties(7, 15.0, 3, 48);

    private ScanResultRepository repository;
    private TrendAnalysisService service;
    private UUID userId;

    @BeforeEach
    void setUp() {
        repository = mock(ScanResultRepository.class);
        service = new TrendAnalysisService(repository, PROPERTIES);
        userId = UUID.randomUUID();
    }

    @Test
    void largeVoiceJitterJumpDoesNotRaiseTrendAlert() {
        givenBaseline(stableBaseline());

        // Jitter 0.5 % -> 1.5 % is a 200 % relative change: it used to raise the alert.
        String alert = service.computeTrendAlert(userId, outcome(72.0, 40.0, 15.0, 1.5, 3.0));

        assertNull(alert);
    }

    @Test
    void largeVoiceShimmerJumpDoesNotRaiseTrendAlert() {
        givenBaseline(stableBaseline());

        String alert = service.computeTrendAlert(userId, outcome(72.0, 40.0, 15.0, 0.5, 9.0));

        assertNull(alert);
    }

    @Test
    void voiceJitterAndShimmerDroppingSharplyDoNotRaiseTrendAlert() {
        givenBaseline(stableBaseline());

        String alert = service.computeTrendAlert(userId, outcome(72.0, 40.0, 15.0, 0.1, 0.5));

        assertNull(alert);
    }

    @Test
    void noisyVoiceBaselineWithStableVitalsDoesNotRaiseTrendAlert() {
        // Room-dependent voice values (quiet room vs fan vs traffic) with stable vitals.
        givenBaseline(List.of(
                priorResult(72.0, 40.0, 15.0, 0.4, 2.0, 3),
                priorResult(71.0, 41.0, 15.0, 13.0, 25.0, 2),
                priorResult(73.0, 39.0, 15.0, 46.0, 31.0, 1)
        ));

        String alert = service.computeTrendAlert(userId, outcome(72.0, 40.0, 15.0, 0.6, 2.2));

        assertNull(alert);
    }

    @Test
    void heartRateDeviationStillRaisesTrendAlert() {
        givenBaseline(stableBaseline());

        String alert = service.computeTrendAlert(userId, outcome(92.0, 40.0, 15.0, 0.5, 3.0));

        assertEquals(TREND_ALERT, alert);
    }

    @Test
    void hrvDeviationStillRaisesTrendAlert() {
        givenBaseline(stableBaseline());

        String alert = service.computeTrendAlert(userId, outcome(72.0, 22.0, 15.0, 0.5, 3.0));

        assertEquals(TREND_ALERT, alert);
    }

    @Test
    void respiratoryRateDeviationStillRaisesTrendAlert() {
        givenBaseline(stableBaseline());

        String alert = service.computeTrendAlert(userId, outcome(72.0, 40.0, 21.0, 0.5, 3.0));

        assertEquals(TREND_ALERT, alert);
    }

    @Test
    void stableVitalsWithMissingVoiceDoNotRaiseTrendAlert() {
        givenBaseline(stableBaseline());

        String alert = service.computeTrendAlert(userId, outcome(72.0, 40.0, 15.0, null, null));

        assertNull(alert);
    }

    private void givenBaseline(List<ScanResult> results) {
        when(repository.findByUser_IdAndCreatedAtGreaterThanEqualOrderByCreatedAtAsc(eq(userId), any(Instant.class)))
                .thenReturn(results);
    }

    private static List<ScanResult> stableBaseline() {
        return List.of(
                priorResult(72.0, 40.0, 15.0, 0.5, 3.0, 3),
                priorResult(72.0, 40.0, 15.0, 0.5, 3.0, 2),
                priorResult(72.0, 40.0, 15.0, 0.5, 3.0, 1)
        );
    }

    private static ScanResult priorResult(
            Double hr,
            Double hrv,
            Double respiratoryRate,
            Double jitter,
            Double shimmer,
            int daysAgo
    ) {
        ScanResult result = mock(ScanResult.class);
        when(result.getCreatedAt()).thenReturn(Instant.now().minus(daysAgo, ChronoUnit.DAYS));
        when(result.getTrendAlert()).thenReturn(null);
        when(result.getHrBpm()).thenReturn(hr);
        when(result.getHrvMs()).thenReturn(hrv);
        when(result.getRespiratoryRate()).thenReturn(respiratoryRate);
        when(result.getVoiceJitterPct()).thenReturn(jitter);
        when(result.getVoiceShimmerPct()).thenReturn(shimmer);
        return result;
    }

    private static ScanEvaluationOutcome outcome(
            Double hr,
            Double hrv,
            Double respiratoryRate,
            Double jitter,
            Double shimmer
    ) {
        return new ScanEvaluationOutcome(
                hr,
                hrv,
                97.0,
                null,
                respiratoryRate,
                jitter,
                shimmer,
                0.91,
                0.8,
                0.97,
                0.94,
                22.0,
                List.of(),
                List.of(),
                true,
                null,
                36.0,
                0.78,
                11.4,
                "monitor",
                0.66
        );
    }
}
