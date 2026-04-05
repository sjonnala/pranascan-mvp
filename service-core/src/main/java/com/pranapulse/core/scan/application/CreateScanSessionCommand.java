package com.pranapulse.core.scan.application;

import com.pranapulse.core.scan.domain.ScanType;

public record CreateScanSessionCommand(
        ScanType scanType,
        String deviceModel,
        String appVersion
) {
}
