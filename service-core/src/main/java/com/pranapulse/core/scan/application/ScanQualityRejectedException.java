package com.pranapulse.core.scan.application;

import java.util.List;

public class ScanQualityRejectedException extends RuntimeException {

    private final List<String> flags;
    private final String rejectionReason;

    public ScanQualityRejectedException(List<String> flags, String rejectionReason) {
        super("Scan quality was insufficient. Please retry in better conditions.");
        this.flags = List.copyOf(flags != null ? flags : List.of());
        this.rejectionReason = rejectionReason;
    }

    public List<String> getFlags() {
        return flags;
    }

    public String getRejectionReason() {
        return rejectionReason;
    }
}
