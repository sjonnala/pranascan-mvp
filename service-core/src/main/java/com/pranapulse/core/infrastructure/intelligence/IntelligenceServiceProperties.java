package com.pranapulse.core.infrastructure.intelligence;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.intelligence")
public record IntelligenceServiceProperties(
        String internalToken,
        String grpcHost,
        int grpcPort) {

    public IntelligenceServiceProperties {
        if (internalToken == null || internalToken.isBlank()) {
            throw new IllegalArgumentException("internalToken must not be blank.");
        }
        internalToken = internalToken.trim();
        if (grpcHost == null || grpcHost.isBlank()) {
            throw new IllegalArgumentException("grpcHost must not be blank.");
        }
        grpcHost = grpcHost.trim();
        if (grpcPort <= 0) {
            throw new IllegalArgumentException("grpcPort must be positive.");
        }
    }
}
