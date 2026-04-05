package com.pranapulse.core.scan.domain;

public enum ScanSessionStatus {
    INITIATED("initiated"),
    COMPLETED("completed"),
    REJECTED("rejected"),
    FAILED("failed");

    private final String value;

    ScanSessionStatus(String value) {
        this.value = value;
    }

    public String value() {
        return value;
    }
}
