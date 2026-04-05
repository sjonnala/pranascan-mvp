package com.pranapulse.core.report.repository;

import com.pranapulse.core.report.domain.VitalityReport;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface VitalityReportRepository extends JpaRepository<VitalityReport, UUID> {

    Optional<VitalityReport> findFirstByUserIdOrderByGeneratedAtDesc(UUID userId);
}
