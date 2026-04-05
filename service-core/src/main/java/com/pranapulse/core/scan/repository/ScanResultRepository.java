package com.pranapulse.core.scan.repository;

import com.pranapulse.core.scan.domain.ScanResult;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ScanResultRepository extends JpaRepository<ScanResult, UUID> {

    Optional<ScanResult> findBySessionId(UUID sessionId);

    List<ScanResult> findByUser_IdOrderByCreatedAtAsc(UUID userId);

    List<ScanResult> findByUser_IdOrderByCreatedAtDesc(UUID userId);
}
