package com.pranapulse.core.scan.web;

import com.pranapulse.core.scan.domain.ScanSession;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import java.time.Instant;
import java.util.UUID;

@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record ScanSessionResponse(
        UUID id,
        UUID userId,
        String status,
        String scanType,
        String deviceModel,
        String appVersion,
        Instant createdAt,
        Instant completedAt
) {

    public static ScanSessionResponse from(ScanSession session) {
        return new ScanSessionResponse(
                session.getId(),
                session.getUser().getId(),
                session.getStatus().value(),
                session.getScanType().value(),
                session.getDeviceModel(),
                session.getAppVersion(),
                session.getCreatedAt(),
                session.getCompletedAt()
        );
    }
}
