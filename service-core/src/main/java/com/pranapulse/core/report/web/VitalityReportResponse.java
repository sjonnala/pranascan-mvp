package com.pranapulse.core.report.web;

import com.pranapulse.core.report.domain.VitalityReport;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import java.time.Instant;
import java.util.UUID;

@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record VitalityReportResponse(
        UUID id,
        UUID userId,
        Instant periodStart,
        Instant periodEnd,
        int scanCount,
        int alertCount,
        Double avgHrBpm,
        Double avgHrvMs,
        Double avgRespiratoryRate,
        Double avgVoiceJitterPct,
        Double avgVoiceShimmerPct,
        Double deltaHrBpm,
        Double deltaHrvMs,
        Double latestVascularAgeEstimate,
        Double latestVascularAgeConfidence,
        String latestAnemiaLabel,
        Double latestAnemiaConfidence,
        String summaryText,
        Instant generatedAt
) {

    public static VitalityReportResponse from(VitalityReport report) {
        return new VitalityReportResponse(
                report.getId(),
                report.getUserId(),
                report.getPeriodStart(),
                report.getPeriodEnd(),
                report.getScanCount(),
                report.getAlertCount(),
                report.getAvgHrBpm(),
                report.getAvgHrvMs(),
                report.getAvgRespiratoryRate(),
                report.getAvgVoiceJitterPct(),
                report.getAvgVoiceShimmerPct(),
                report.getDeltaHrBpm(),
                report.getDeltaHrvMs(),
                report.getLatestVascularAgeEstimate(),
                report.getLatestVascularAgeConfidence(),
                report.getLatestAnemiaLabel(),
                report.getLatestAnemiaConfidence(),
                report.getSummaryText(),
                report.getGeneratedAt()
        );
    }
}
