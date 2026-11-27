package com.pranapulse.core.scan.domain.contract;

/** Whether voice wellness indicators were produced. */
public enum VoiceStatus {
    MEASURED("Voice indicators captured."),
    ABSTAINED("Voice indicators skipped because the recording was not clear enough. Try again somewhere quiet."),
    NOT_SUBMITTED("No voice recording was part of this scan."),
    UNKNOWN("Voice indicator status is not available for this scan.");

    private final String userFacingSummary;

    VoiceStatus(String userFacingSummary) {
        this.userFacingSummary = userFacingSummary;
    }

    public String userFacingSummary() {
        return userFacingSummary;
    }

    public static VoiceStatus fromColumn(String column) {
        return ColumnEnums.fromColumn(VoiceStatus.class, column, UNKNOWN);
    }

    public String toColumn() {
        return ColumnEnums.toColumn(this, UNKNOWN);
    }
}
