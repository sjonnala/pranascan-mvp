package com.pranapulse.core.scan.domain.contract;

import java.util.Objects;

/**
 * Pulse outcome for one scan (proto {@code RppgAssessment}). Invariants mirror V8's
 * {@code ck_scan_results_hr_abstained_has_no_hr}: a skipped reading never carries a value.
 */
public record HeartRateAssessment(
        HeartRateStatus status,
        HrAbstentionReason abstentionReason,
        Double effectiveFps,
        boolean hrvWithheldLowFps,
        Double hrBpm,
        Double hrvMs) {

    public HeartRateAssessment {
        status = Objects.requireNonNullElse(status, HeartRateStatus.UNKNOWN);
        abstentionReason = Objects.requireNonNullElse(abstentionReason, HrAbstentionReason.UNSPECIFIED);
        if (status == HeartRateStatus.ABSTAINED && (hrBpm != null || hrvMs != null)) {
            throw new IllegalArgumentException("a skipped pulse reading cannot carry hr_bpm or hrv_ms");
        }
        if (status != HeartRateStatus.ABSTAINED && abstentionReason != HrAbstentionReason.UNSPECIFIED) {
            throw new IllegalArgumentException("abstention reason is only valid when status is ABSTAINED");
        }
        if (status == HeartRateStatus.MEASURED && hrBpm == null) {
            throw new IllegalArgumentException("a captured pulse reading needs hr_bpm");
        }
        if (hrvWithheldLowFps && hrvMs != null) {
            throw new IllegalArgumentException("hrv_ms must be empty when HRV was withheld for low fps");
        }
        if (effectiveFps != null && (effectiveFps.isNaN() || effectiveFps < 0.0)) {
            throw new IllegalArgumentException("effectiveFps cannot be negative: " + effectiveFps);
        }
    }

    public static HeartRateAssessment measured(double hrBpm, Double hrvMs, Double effectiveFps, boolean hrvWithheldLowFps) {
        return new HeartRateAssessment(HeartRateStatus.MEASURED, HrAbstentionReason.UNSPECIFIED,
                effectiveFps, hrvWithheldLowFps, hrBpm, hrvMs);
    }

    public static HeartRateAssessment abstained(HrAbstentionReason reason, Double effectiveFps) {
        return new HeartRateAssessment(HeartRateStatus.ABSTAINED, reason, effectiveFps, false, null, null);
    }

    /**
     * Rebuilds the assessment from V8 columns. Legacy rows have {@code hr_status = NULL}, which
     * reads as {@link HeartRateStatus#UNKNOWN} even when {@code hr_bpm} is present.
     */
    public static HeartRateAssessment fromColumns(String hrStatus, String abstentionReason, Double effectiveFps,
                                                  Boolean hrvWithheldLowFps, Double hrBpm, Double hrvMs) {
        return new HeartRateAssessment(HeartRateStatus.fromColumn(hrStatus),
                HrAbstentionReason.fromColumn(abstentionReason), effectiveFps,
                Boolean.TRUE.equals(hrvWithheldLowFps), hrBpm, hrvMs);
    }

    /** Only explicitly captured readings feed trends; unknown (legacy/rev-1) and skipped never do. */
    public boolean usableForTrends() {
        return status == HeartRateStatus.MEASURED;
    }
}
