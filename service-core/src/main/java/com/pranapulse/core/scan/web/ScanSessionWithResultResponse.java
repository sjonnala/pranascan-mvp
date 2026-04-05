package com.pranapulse.core.scan.web;

import com.pranapulse.core.scan.application.ScanSessionBundle;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;

@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record ScanSessionWithResultResponse(
        ScanSessionResponse session,
        ScanResultResponse result
) {

    public static ScanSessionWithResultResponse from(ScanSessionBundle bundle) {
        return new ScanSessionWithResultResponse(
                ScanSessionResponse.from(bundle.session()),
                bundle.result() != null ? ScanResultResponse.from(bundle.result()) : null
        );
    }
}
