package com.pranapulse.core.consent.domain;

public enum DeletionRequestStatus {
    PENDING("pending"),
    COMPLETED("completed"),
    FAILED("failed");

    private final String value;

    DeletionRequestStatus(String value) {
        this.value = value;
    }

    public String value() {
        return value;
    }
}
