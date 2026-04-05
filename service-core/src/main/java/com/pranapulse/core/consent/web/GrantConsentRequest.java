package com.pranapulse.core.consent.web;

import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import jakarta.validation.constraints.Size;

@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record GrantConsentRequest(
        @Size(max = 16) String consentVersion,
        @Size(max = 256) String purpose,
        @Size(max = 64) String ipAddress,
        @Size(max = 512) String userAgent
) {
}
