package com.pranapulse.core.audit.repository;

import com.pranapulse.core.audit.domain.AuditLog;
import java.util.UUID;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface AuditLogRepository extends JpaRepository<AuditLog, UUID> {

    Page<AuditLog> findByUserIdOrderByCreatedAtDesc(UUID userId, Pageable pageable);

    Page<AuditLog> findByUserIdAndActionStartingWithOrderByCreatedAtDesc(UUID userId, String action, Pageable pageable);
}
