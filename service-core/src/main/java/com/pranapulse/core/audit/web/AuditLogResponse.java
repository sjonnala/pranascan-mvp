package com.pranapulse.core.audit.web;

import com.pranapulse.core.audit.domain.AuditLog;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import java.time.Instant;
import java.util.UUID;

@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record AuditLogResponse(
        UUID id,
        UUID userId,
        String action,
        String resourceType,
        String resourceId,
        String httpMethod,
        String httpPath,
        Integer httpStatus,
        Integer durationMs,
        String ipAddress,
        String detail,
        Instant createdAt
) {

    public static AuditLogResponse from(AuditLog auditLog) {
        return new AuditLogResponse(
                auditLog.getId(),
                auditLog.getUserId(),
                auditLog.getAction(),
                auditLog.getResourceType(),
                auditLog.getResourceId(),
                auditLog.getHttpMethod(),
                auditLog.getHttpPath(),
                auditLog.getHttpStatus(),
                auditLog.getDurationMs(),
                auditLog.getIpAddress(),
                auditLog.getDetail(),
                auditLog.getCreatedAt()
        );
    }
}
