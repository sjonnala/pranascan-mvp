package com.pranapulse.core.scan.web;

import com.pranapulse.core.scan.application.ScanHistoryEntry;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;

@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record ScanHistoryItemResponse(
        ScanSessionResponse session,
        ScanResultResponse result,
        Double hrTrendDelta,
        Double hrvTrendDelta
) {

    public static ScanHistoryItemResponse from(ScanHistoryEntry entry) {
        return new ScanHistoryItemResponse(
                ScanSessionResponse.from(entry.session()),
                entry.result() != null ? ScanResultResponse.from(entry.result()) : null,
                entry.hrTrendDelta(),
                entry.hrvTrendDelta()
        );
    }
}
