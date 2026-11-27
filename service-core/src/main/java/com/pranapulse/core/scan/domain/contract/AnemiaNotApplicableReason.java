package com.pranapulse.core.scan.domain.contract;

/** Why the haemoglobin wellness indicator did not apply. */
public enum AnemiaNotApplicableReason {
    NO_CONJUNCTIVAL_ROI("No inner-eyelid image was captured, so this indicator was not estimated."),
    SCAN_TYPE_NOT_SUPPORTED("This indicator is not part of this scan type."),
    UNSPECIFIED("This indicator was not estimated for this scan.");

    private final String userFacingSummary;

    AnemiaNotApplicableReason(String userFacingSummary) {
        this.userFacingSummary = userFacingSummary;
    }

    public String userFacingSummary() {
        return userFacingSummary;
    }

    public static AnemiaNotApplicableReason fromColumn(String column) {
        return ColumnEnums.fromColumn(AnemiaNotApplicableReason.class, column, UNSPECIFIED);
    }

    public String toColumn() {
        return ColumnEnums.toColumn(this, UNSPECIFIED);
    }
}
