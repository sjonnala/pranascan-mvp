package com.pranapulse.core.scan.web;

import com.pranapulse.core.scan.application.CreateScanSessionCommand;
import com.pranapulse.core.scan.domain.ScanType;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import jakarta.validation.constraints.Size;

@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record CreateScanSessionRequest(
        ScanType scanType,
        @Size(max = 128) String deviceModel,
        @Size(max = 32) String appVersion
) {

    public CreateScanSessionCommand toCommand() {
        return new CreateScanSessionCommand(ScanType.defaultIfNull(scanType), deviceModel, appVersion);
    }
}
