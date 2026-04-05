package com.pranapulse.core.report.application;

import com.pranapulse.core.report.domain.VitalityReport;
import com.pranapulse.core.report.repository.VitalityReportRepository;
import com.pranapulse.core.scan.domain.ScanResult;
import com.pranapulse.core.scan.repository.ScanResultRepository;
import com.pranapulse.core.shared.error.NotFoundException;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.function.Function;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class VitalityReportService {

    public static final String DISCLAIMER =
            "This is a wellness summary, not a medical report. "
                    + "For health concerns, consult a qualified healthcare provider.";

    private final ScanResultRepository scanResultRepository;
    private final VitalityReportRepository vitalityReportRepository;

    public VitalityReportService(
            ScanResultRepository scanResultRepository,
            VitalityReportRepository vitalityReportRepository
    ) {
        this.scanResultRepository = scanResultRepository;
        this.vitalityReportRepository = vitalityReportRepository;
    }

    @Transactional
    public VitalityReport generate(UUID userId) {
        Instant now = Instant.now();
        Instant currentStart = now.minus(7, ChronoUnit.DAYS);
        Instant priorStart = now.minus(14, ChronoUnit.DAYS);

        List<ScanResult> allResults = scanResultRepository.findByUser_IdOrderByCreatedAtAsc(userId);
        List<ScanResult> currentResults = allResults.stream()
                .filter(result -> !result.getCreatedAt().isBefore(currentStart))
                .toList();
        List<ScanResult> priorResults = allResults.stream()
                .filter(result -> !result.getCreatedAt().isBefore(priorStart))
                .filter(result -> result.getCreatedAt().isBefore(currentStart))
                .toList();

        ScanResult latest = currentResults.isEmpty() ? null : currentResults.get(currentResults.size() - 1);
        int alertCount = (int) currentResults.stream().filter(result -> result.getTrendAlert() != null).count();

        VitalityReport report = new VitalityReport(
                userId,
                currentStart,
                now,
                currentResults.size(),
                alertCount,
                average(currentResults, ScanResult::getHrBpm),
                average(currentResults, ScanResult::getHrvMs),
                average(currentResults, ScanResult::getRespiratoryRate),
                average(currentResults, ScanResult::getVoiceJitterPct),
                average(currentResults, ScanResult::getVoiceShimmerPct),
                delta(currentResults, priorResults, ScanResult::getHrBpm),
                delta(currentResults, priorResults, ScanResult::getHrvMs),
                latest != null ? latest.getVascularAgeEstimate() : null,
                latest != null ? latest.getVascularAgeConfidence() : null,
                latest != null ? latest.getAnemiaWellnessLabel() : null,
                latest != null ? latest.getAnemiaConfidence() : null,
                renderSummary(currentStart, now, currentResults, priorResults, latest, alertCount)
        );
        return vitalityReportRepository.save(report);
    }

    @Transactional(readOnly = true)
    public VitalityReport getLatest(UUID userId) {
        return vitalityReportRepository.findFirstByUserIdOrderByGeneratedAtDesc(userId)
                .orElseThrow(() -> new NotFoundException(
                        "No vitality report found. Generate one first via POST /reports/generate."
                ));
    }

    private String renderSummary(
            Instant currentStart,
            Instant currentEnd,
            List<ScanResult> currentResults,
            List<ScanResult> priorResults,
            ScanResult latest,
            int alertCount
    ) {
        List<String> lines = new ArrayList<>();
        lines.add("PranaScan Weekly Wellness Summary");
        lines.add("====================================");
        lines.add("Period : " + currentStart.toString().substring(0, 10)
                + " to " + currentEnd.toString().substring(0, 10));
        lines.add("Scans  : " + currentResults.size());
        lines.add("");
        lines.add("-- Wellness Indicators --");
        lines.add(renderMetricLine("Heart Rate", "bpm", currentResults, priorResults, ScanResult::getHrBpm));
        lines.add(renderMetricLine("HRV (RMSSD)", "ms", currentResults, priorResults, ScanResult::getHrvMs));
        lines.add(renderMetricLine(
                "Respiratory Rate",
                "breaths/min",
                currentResults,
                priorResults,
                ScanResult::getRespiratoryRate
        ));
        lines.add(renderMetricLine("Voice Jitter", "%", currentResults, priorResults, ScanResult::getVoiceJitterPct));
        lines.add(renderMetricLine(
                "Voice Shimmer",
                "%",
                currentResults,
                priorResults,
                ScanResult::getVoiceShimmerPct
        ));
        lines.add("");
        lines.add("-- Supplementary Indicators --");
        lines.add(latest != null && latest.getVascularAgeEstimate() != null
                ? "  Vascular Age Estimate  "
                        + latest.getVascularAgeEstimate().intValue()
                        + " years (wellness indicator)"
                : "  Vascular Age Estimate  insufficient data");
        lines.add(latest != null && latest.getAnemiaWellnessLabel() != null
                ? "  Hemoglobin Proxy       " + latest.getAnemiaWellnessLabel().replace('_', ' ')
                : "  Hemoglobin Proxy       insufficient data");
        lines.add("");
        if (alertCount > 0) {
            lines.add("-- Wellness Alerts (" + alertCount + ") --");
            lines.add("  Consider scheduling a routine check-up based on recent trends.");
            lines.add("");
        }
        lines.add(DISCLAIMER);
        return String.join("\n", lines);
    }

    private String renderMetricLine(
            String label,
            String unit,
            List<ScanResult> currentResults,
            List<ScanResult> priorResults,
            Function<ScanResult, Double> extractor
    ) {
        Double currentAverage = average(currentResults, extractor);
        Double priorAverage = average(priorResults, extractor);
        if (currentAverage == null) {
            return "  " + label + "  insufficient data";
        }

        StringBuilder line = new StringBuilder("  ")
                .append(label)
                .append("  ")
                .append(currentAverage)
                .append(' ')
                .append(unit);
        if (priorAverage != null) {
            double delta = round(currentAverage - priorAverage);
            String direction = delta > 0 ? "up" : (delta < 0 ? "down" : "flat");
            line.append("  ").append(direction).append(' ').append(Math.abs(delta)).append(" vs prior week");
        }
        return line.toString();
    }

    private Double delta(
            List<ScanResult> currentResults,
            List<ScanResult> priorResults,
            Function<ScanResult, Double> extractor
    ) {
        Double currentAverage = average(currentResults, extractor);
        Double priorAverage = average(priorResults, extractor);
        return currentAverage != null && priorAverage != null ? round(currentAverage - priorAverage) : null;
    }

    private Double average(List<ScanResult> results, Function<ScanResult, Double> extractor) {
        List<Double> values = results.stream().map(extractor).filter(value -> value != null).toList();
        if (values.isEmpty()) {
            return null;
        }
        return round(values.stream().mapToDouble(Double::doubleValue).average().orElse(0.0));
    }

    private static double round(double value) {
        return Math.round(value * 10.0) / 10.0;
    }
}
