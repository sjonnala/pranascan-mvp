package com.pranapulse.core.scan.application;

import com.pranapulse.core.scan.domain.ScanResult;
import com.pranapulse.core.scan.repository.ScanResultRepository;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.UUID;
import java.util.function.Function;
import org.springframework.stereotype.Service;

@Service
public class TrendAnalysisService {

    private static final String TREND_ALERT = "consider_lab_followup";

    private final ScanResultRepository scanResultRepository;
    private final TrendProperties trendProperties;

    public TrendAnalysisService(
            ScanResultRepository scanResultRepository,
            TrendProperties trendProperties
    ) {
        this.scanResultRepository = scanResultRepository;
        this.trendProperties = trendProperties;
    }

    public String computeTrendAlert(UUID userId, ScanEvaluationOutcome outcome) {
        Instant now = Instant.now();
        Instant cooldownCutoff = now.minus(trendProperties.cooldownHours(), ChronoUnit.HOURS);
        Instant baselineCutoff = now.minus(trendProperties.lookbackDays(), ChronoUnit.DAYS);
        Instant queryCutoff = cooldownCutoff.isBefore(baselineCutoff) ? cooldownCutoff : baselineCutoff;

        List<ScanResult> allResults = scanResultRepository.findByUser_IdAndCreatedAtGreaterThanEqualOrderByCreatedAtAsc(userId, queryCutoff);

        boolean onCooldown = allResults.stream()
                .anyMatch(result -> result.getTrendAlert() != null && !result.getCreatedAt().isBefore(cooldownCutoff));
        if (onCooldown) {
            return null;
        }

        List<ScanResult> baselineWindow = allResults.stream()
                .filter(result -> !result.getCreatedAt().isBefore(baselineCutoff))
                .toList();

        if (deviates(outcome.hrBpm(), baselineWindow, ScanResult::getHrBpm)
                || deviates(outcome.hrvMs(), baselineWindow, ScanResult::getHrvMs)
                || deviates(outcome.respiratoryRate(), baselineWindow, ScanResult::getRespiratoryRate)
                || deviates(outcome.voiceJitterPct(), baselineWindow, ScanResult::getVoiceJitterPct)
                || deviates(outcome.voiceShimmerPct(), baselineWindow, ScanResult::getVoiceShimmerPct)) {
            return TREND_ALERT;
        }

        return null;
    }

    public ScanHistoryPage buildHistoryPage(UUID userId, int page, int pageSize) {
        List<ScanResult> resultsDesc = new ArrayList<>(scanResultRepository.findByUser_IdOrderByCreatedAtDesc(userId));
        List<ScanResult> resultsAsc = new ArrayList<>(resultsDesc);
        resultsAsc.sort(Comparator.comparing(ScanResult::getCreatedAt));

        int total = resultsDesc.size();
        int offset = Math.max(0, (page - 1) * pageSize);
        int toIndex = Math.min(total, offset + pageSize);

        List<ScanHistoryEntry> items = new ArrayList<>();
        if (offset < total) {
            for (ScanResult result : resultsDesc.subList(offset, toIndex)) {
                items.add(new ScanHistoryEntry(
                        result.getSession(),
                        result,
                        computeHistoryDelta(resultsAsc, result, ScanResult::getHrBpm),
                        computeHistoryDelta(resultsAsc, result, ScanResult::getHrvMs)
                ));
            }
        }

        return new ScanHistoryPage(items, total, page, pageSize);
    }

    private Double computeHistoryDelta(
            List<ScanResult> orderedResults,
            ScanResult current,
            Function<ScanResult, Double> extractor
    ) {
        Instant cutoff = current.getCreatedAt().minus(trendProperties.lookbackDays(), ChronoUnit.DAYS);
        List<Double> priorValues = orderedResults.stream()
                .filter(candidate -> candidate.getCreatedAt().isBefore(current.getCreatedAt()))
                .filter(candidate -> !candidate.getCreatedAt().isBefore(cutoff))
                .map(extractor)
                .filter(value -> value != null)
                .toList();

        Double currentValue = extractor.apply(current);
        if (currentValue == null || priorValues.size() < trendProperties.minBaselineScans()) {
            return null;
        }

        double baselineAverage = priorValues.stream()
                .mapToDouble(Double::doubleValue)
                .average()
                .orElse(Double.NaN);
        return Double.isNaN(baselineAverage)
                ? null
                : round(currentValue - baselineAverage);
    }

    private boolean deviates(
            Double currentValue,
            List<ScanResult> baselineWindow,
            Function<ScanResult, Double> extractor
    ) {
        if (currentValue == null) {
            return false;
        }

        List<Double> baselineValues = baselineWindow.stream()
                .map(extractor)
                .filter(value -> value != null)
                .toList();

        if (baselineValues.size() < trendProperties.minBaselineScans()) {
            return false;
        }

        double baselineAverage = baselineValues.stream()
                .mapToDouble(Double::doubleValue)
                .average()
                .orElse(0.0);
        if (baselineAverage == 0.0) {
            return false;
        }

        double deviationPct = Math.abs((currentValue - baselineAverage) / baselineAverage) * 100.0;
        return deviationPct >= trendProperties.alertThresholdPct();
    }

    private static Double round(double value) {
        return Math.round(value * 10.0) / 10.0;
    }
}
