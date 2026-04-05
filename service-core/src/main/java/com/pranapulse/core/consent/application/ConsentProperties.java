package com.pranapulse.core.consent.application;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.consent")
public record ConsentProperties(
        @NotBlank String defaultVersion,
        @Min(1) int deletionHoldDays
) {
}
