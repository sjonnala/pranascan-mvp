package com.pranapulse.core.scan.domain.contract;

import java.util.Objects;

/** Mobile vs spectral signal quality (proto {@code QualityBreakdown}, V8 columns). */
public record QualityBreakdown(
        Double mobileQualityScore,
        Double spectralQualityScore,
        Double spectralSnrDb,
        QualityScoreBasis basis) {

    public QualityBreakdown {
        requireUnitInterval(mobileQualityScore, "mobileQualityScore");
        requireUnitInterval(spectralQualityScore, "spectralQualityScore");
        basis = Objects.requireNonNullElse(basis, QualityScoreBasis.UNKNOWN);
    }

    /** A legacy (pre-V8) row: only the basis label from the V8 backfill is known. */
    public static QualityBreakdown legacy(String basisColumn) {
        return new QualityBreakdown(null, null, null, QualityScoreBasis.fromColumn(basisColumn));
    }

    static void requireUnitInterval(Double value, String name) {
        if (value != null && (value.isNaN() || value < 0.0 || value > 1.0)) {
            throw new IllegalArgumentException(name + " must be within [0, 1]: " + value);
        }
    }
}
