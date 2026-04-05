package com.pranapulse.core.scan.web;

import com.pranapulse.core.scan.application.ScanHistoryPage;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import java.util.List;

@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record ScanHistoryResponse(
        List<ScanHistoryItemResponse> items,
        int total,
        int page,
        int pageSize
) {

    public static ScanHistoryResponse from(ScanHistoryPage historyPage) {
        return new ScanHistoryResponse(
                historyPage.items().stream().map(ScanHistoryItemResponse::from).toList(),
                historyPage.total(),
                historyPage.page(),
                historyPage.pageSize()
        );
    }
}
