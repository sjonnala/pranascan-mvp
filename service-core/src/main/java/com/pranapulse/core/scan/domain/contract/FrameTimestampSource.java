package com.pranapulse.core.scan.domain.contract;

import java.util.Locale;

/** Clock behind capture frame timestamps. REST values are PR #2's snake_case strings. */
public enum FrameTimestampSource {
    HARDWARE,
    WALL_CLOCK,
    MIXED,
    UNKNOWN;

    /** Parses PR #2's {@code hardware|wall_clock|mixed}; anything else is UNKNOWN. */
    public static FrameTimestampSource fromRestValue(String value) {
        return ColumnEnums.fromColumn(FrameTimestampSource.class, value == null ? null : value.toUpperCase(Locale.ROOT), UNKNOWN);
    }

    public String toColumn() {
        return ColumnEnums.toColumn(this, UNKNOWN);
    }
}
