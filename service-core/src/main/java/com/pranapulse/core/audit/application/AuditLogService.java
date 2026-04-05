package com.pranapulse.core.audit.application;

import com.pranapulse.core.audit.domain.AuditLog;
import com.pranapulse.core.audit.repository.AuditLogRepository;
import java.util.UUID;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AuditLogService {

    private final AuditLogRepository auditLogRepository;

    public AuditLogService(AuditLogRepository auditLogRepository) {
        this.auditLogRepository = auditLogRepository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public AuditLog recordHttpEvent(
            UUID userId,
            String action,
            String httpMethod,
            String httpPath,
            Integer httpStatus,
            Integer durationMs,
            String ipAddress,
            String userAgent,
            String detail
    ) {
        return auditLogRepository.save(new AuditLog(
                userId,
                action,
                null,
                null,
                httpMethod,
                httpPath,
                httpStatus,
                durationMs,
                ipAddress,
                userAgent,
                detail
        ));
    }

    @Transactional(readOnly = true)
    public AuditLogPage list(UUID userId, String action, int page, int pageSize) {
        Pageable pageable = PageRequest.of(Math.max(page - 1, 0), pageSize);
        Page<AuditLog> result = action == null || action.isBlank()
                ? auditLogRepository.findByUserIdOrderByCreatedAtDesc(userId, pageable)
                : auditLogRepository.findByUserIdAndActionStartingWithOrderByCreatedAtDesc(userId, action, pageable);

        return new AuditLogPage(result.getContent(), (int) result.getTotalElements(), page, pageSize);
    }
}
