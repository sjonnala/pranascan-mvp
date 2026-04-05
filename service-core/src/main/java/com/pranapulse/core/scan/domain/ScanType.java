package com.pranapulse.core.scan.domain;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonValue;

public enum ScanType {
    STANDARD("standard"),
    DEEP_DIVE("deep_dive");

    private final String value;

    ScanType(String value) {
        this.value = value;
    }

    @JsonValue
    public String value() {
        return value;
    }

    @JsonCreator
    public static ScanType fromValue(String value) {
        if (value == null || value.isBlank()) {
            return STANDARD;
        }

        return switch (value.trim().toLowerCase()) {
            case "standard" -> STANDARD;
            case "deep_dive" -> DEEP_DIVE;
            default -> throw new IllegalArgumentException("Unsupported scan type: " + value);
        };
    }

    public static ScanType defaultIfNull(ScanType scanType) {
        return scanType == null ? STANDARD : scanType;
    }
}
