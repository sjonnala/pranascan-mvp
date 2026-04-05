package com.pranapulse.core.audit.application;

import com.pranapulse.core.audit.domain.AuditLog;
import java.util.List;

public record AuditLogPage(
        List<AuditLog> items,
        int total,
        int page,
        int pageSize
) {
}
