package com.pranapulse.core.scan.domain.contract;

/** Whether a pulse reading was taken. Persisted names match {@code ck_scan_results_hr_status}. */
public enum HeartRateStatus {
    MEASURED("Pulse reading captured."),
    ABSTAINED("Pulse reading skipped because the signal was not clear enough. Try again in steady, even light."),
    NOT_ATTEMPTED("Pulse reading was not part of this scan."),
    /** NULL column or rev-1 peer. Never treated as measured. */
    UNKNOWN("Pulse reading status is not available for this scan.");

    private final String userFacingSummary;

    HeartRateStatus(String userFacingSummary) {
        this.userFacingSummary = userFacingSummary;
    }

    public String userFacingSummary() {
        return userFacingSummary;
    }

    public static HeartRateStatus fromColumn(String column) {
        return ColumnEnums.fromColumn(HeartRateStatus.class, column, UNKNOWN);
    }

    public String toColumn() {
        return ColumnEnums.toColumn(this, UNKNOWN);
    }
}
