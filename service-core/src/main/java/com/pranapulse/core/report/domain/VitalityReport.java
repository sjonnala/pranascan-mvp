package com.pranapulse.core.report.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Index;
import jakarta.persistence.PrePersist;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(
        schema = "core",
        name = "vitality_reports",
        indexes = {
                @Index(name = "idx_vitality_reports_user_id", columnList = "user_id"),
                @Index(name = "idx_vitality_reports_generated_at", columnList = "generated_at")
        }
)
public class VitalityReport {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(name = "user_id", nullable = false)
    private UUID userId;

    @Column(name = "period_start", nullable = false)
    private Instant periodStart;

    @Column(name = "period_end", nullable = false)
    private Instant periodEnd;

    @Column(name = "scan_count", nullable = false)
    private int scanCount;

    @Column(name = "alert_count", nullable = false)
    private int alertCount;

    @Column(name = "avg_hr_bpm")
    private Double avgHrBpm;

    @Column(name = "avg_hrv_ms")
    private Double avgHrvMs;

    @Column(name = "avg_respiratory_rate")
    private Double avgRespiratoryRate;

    @Column(name = "avg_voice_jitter_pct")
    private Double avgVoiceJitterPct;

    @Column(name = "avg_voice_shimmer_pct")
    private Double avgVoiceShimmerPct;

    @Column(name = "delta_hr_bpm")
    private Double deltaHrBpm;

    @Column(name = "delta_hrv_ms")
    private Double deltaHrvMs;

    @Column(name = "latest_vascular_age_estimate")
    private Double latestVascularAgeEstimate;

    @Column(name = "latest_vascular_age_confidence")
    private Double latestVascularAgeConfidence;

    @Column(name = "latest_anemia_label", length = 32)
    private String latestAnemiaLabel;

    @Column(name = "latest_anemia_confidence")
    private Double latestAnemiaConfidence;

    @Column(name = "summary_text", nullable = false, length = 4000)
    private String summaryText;

    @Column(name = "generated_at", nullable = false, updatable = false)
    private Instant generatedAt;

    protected VitalityReport() {
    }

    public VitalityReport(
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
            String summaryText
    ) {
        this.userId = userId;
        this.periodStart = periodStart;
        this.periodEnd = periodEnd;
        this.scanCount = scanCount;
        this.alertCount = alertCount;
        this.avgHrBpm = avgHrBpm;
        this.avgHrvMs = avgHrvMs;
        this.avgRespiratoryRate = avgRespiratoryRate;
        this.avgVoiceJitterPct = avgVoiceJitterPct;
        this.avgVoiceShimmerPct = avgVoiceShimmerPct;
        this.deltaHrBpm = deltaHrBpm;
        this.deltaHrvMs = deltaHrvMs;
        this.latestVascularAgeEstimate = latestVascularAgeEstimate;
        this.latestVascularAgeConfidence = latestVascularAgeConfidence;
        this.latestAnemiaLabel = latestAnemiaLabel;
        this.latestAnemiaConfidence = latestAnemiaConfidence;
        this.summaryText = summaryText;
    }

    @PrePersist
    void onCreate() {
        if (generatedAt == null) {
            generatedAt = Instant.now();
        }
    }

    public UUID getId() {
        return id;
    }

    public UUID getUserId() {
        return userId;
    }

    public Instant getPeriodStart() {
        return periodStart;
    }

    public Instant getPeriodEnd() {
        return periodEnd;
    }

    public int getScanCount() {
        return scanCount;
    }

    public int getAlertCount() {
        return alertCount;
    }

    public Double getAvgHrBpm() {
        return avgHrBpm;
    }

    public Double getAvgHrvMs() {
        return avgHrvMs;
    }

    public Double getAvgRespiratoryRate() {
        return avgRespiratoryRate;
    }

    public Double getAvgVoiceJitterPct() {
        return avgVoiceJitterPct;
    }

    public Double getAvgVoiceShimmerPct() {
        return avgVoiceShimmerPct;
    }

    public Double getDeltaHrBpm() {
        return deltaHrBpm;
    }

    public Double getDeltaHrvMs() {
        return deltaHrvMs;
    }

    public Double getLatestVascularAgeEstimate() {
        return latestVascularAgeEstimate;
    }

    public Double getLatestVascularAgeConfidence() {
        return latestVascularAgeConfidence;
    }

    public String getLatestAnemiaLabel() {
        return latestAnemiaLabel;
    }

    public Double getLatestAnemiaConfidence() {
        return latestAnemiaConfidence;
    }

    public String getSummaryText() {
        return summaryText;
    }

    public Instant getGeneratedAt() {
        return generatedAt;
    }
}
