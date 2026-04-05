package com.pranapulse.core.audit.web;

import com.pranapulse.core.audit.application.AuditLogPage;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import java.util.List;

@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record AuditLogListResponse(
        List<AuditLogResponse> items,
        int total,
        int page,
        int pageSize
) {

    public static AuditLogListResponse from(AuditLogPage page) {
        return new AuditLogListResponse(
                page.items().stream().map(AuditLogResponse::from).toList(),
                page.total(),
                page.page(),
                page.pageSize()
        );
    }
}
