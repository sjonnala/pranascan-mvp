package com.pranapulse.core.scan.repository;

import com.pranapulse.core.scan.domain.ScanSession;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ScanSessionRepository extends JpaRepository<ScanSession, UUID> {
}
