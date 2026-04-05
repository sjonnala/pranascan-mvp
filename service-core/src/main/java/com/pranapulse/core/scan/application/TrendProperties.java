package com.pranapulse.core.scan.application;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Min;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.trend")
public record TrendProperties(
        @Min(1) int lookbackDays,
        @DecimalMin("0.1") double alertThresholdPct,
        @Min(1) int minBaselineScans,
        @Min(1) int cooldownHours
) {
}
