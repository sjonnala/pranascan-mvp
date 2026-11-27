package com.pranapulse.core.scan.domain.contract;

/**
 * What {@code quality_score} was computed from. Rows written before PR #1 used max(mobile,
 * spectral); V8 labels them {@link #LEGACY_MAX_OF_MOBILE_AND_SPECTRAL}.
 */
public enum QualityScoreBasis {
    LEGACY_MAX_OF_MOBILE_AND_SPECTRAL,
    SPECTRAL,
    MOBILE_ONLY,
    /** NULL column or rev-1 peer: basis not known. */
    UNKNOWN;

    public static QualityScoreBasis fromColumn(String column) {
        return ColumnEnums.fromColumn(QualityScoreBasis.class, column, UNKNOWN);
    }

    public String toColumn() {
        return ColumnEnums.toColumn(this, UNKNOWN);
    }

    /** Trend analysis may only compare quality scores computed the same, known way. */
    public boolean comparableWith(QualityScoreBasis other) {
        return this != UNKNOWN && this == other;
    }
}
