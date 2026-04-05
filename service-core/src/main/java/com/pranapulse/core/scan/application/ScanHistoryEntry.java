package com.pranapulse.core.scan.application;

import com.pranapulse.core.scan.domain.ScanResult;
import com.pranapulse.core.scan.domain.ScanSession;

public record ScanHistoryEntry(
        ScanSession session,
        ScanResult result,
        Double hrTrendDelta,
        Double hrvTrendDelta
) {
}
