package com.pranapulse.core.scan.domain.contract;

import java.util.Locale;

/** Why the pulse reading was skipped (proto {@code HrAbstentionReason}). */
public enum HrAbstentionReason {
    LOW_SPECTRAL_QUALITY,
    LOW_SPECTRAL_SNR,
    FLAT_SIGNAL,
    INSUFFICIENT_PEAKS,
    UNSPECIFIED;

    public static HrAbstentionReason fromColumn(String column) {
        return ColumnEnums.fromColumn(HrAbstentionReason.class, column, UNSPECIFIED);
    }

    public String toColumn() {
        return ColumnEnums.toColumn(this, UNSPECIFIED);
    }

    /** Reads rev-1 {@code abstain_reason:<x>} values; unknown values map to UNSPECIFIED, never throw. */
    public static HrAbstentionReason fromLegacyFlagValue(String value) {
        if (value == null) {
            return UNSPECIFIED;
        }
        return fromColumn(value.trim().toUpperCase(Locale.ROOT));
    }
}
