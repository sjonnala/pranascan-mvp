package com.pranapulse.core.scan.web;

import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import java.time.Instant;
import java.util.List;

@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record ScanQualityRejectedResponse(
        Instant timestamp,
        int status,
        String error,
        String message,
        String path,
        List<String> flags,
        String rejectionReason
) {
}
