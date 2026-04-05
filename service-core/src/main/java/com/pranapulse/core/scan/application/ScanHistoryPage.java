package com.pranapulse.core.scan.application;

import java.util.List;

public record ScanHistoryPage(
        List<ScanHistoryEntry> items,
        int total,
        int page,
        int pageSize
) {
}
