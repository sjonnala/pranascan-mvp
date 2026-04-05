package com.pranapulse.core.scan.application;

public record CreateScanSessionCommand(
        String deviceModel,
        String appVersion
) {
}
