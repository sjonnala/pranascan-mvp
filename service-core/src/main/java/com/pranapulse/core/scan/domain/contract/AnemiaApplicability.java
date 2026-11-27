package com.pranapulse.core.scan.domain.contract;

/** Whether the colour-based haemoglobin wellness indicator applied to this scan. */
public enum AnemiaApplicability {
    APPLICABLE,
    NOT_APPLICABLE,
    UNKNOWN;

    public static AnemiaApplicability fromColumn(String column) {
        return ColumnEnums.fromColumn(AnemiaApplicability.class, column, UNKNOWN);
    }

    public String toColumn() {
        return ColumnEnums.toColumn(this, UNKNOWN);
    }
}
