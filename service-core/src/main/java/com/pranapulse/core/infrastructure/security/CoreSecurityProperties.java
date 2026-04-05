package com.pranapulse.core.infrastructure.security;

import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.security")
public record CoreSecurityProperties(
        @NotBlank String issuerUri,
        @NotBlank String jwkSetUri,
        @NotBlank String requiredAudience
) {
}
