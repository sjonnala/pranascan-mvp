package com.pranapulse.core.feedback.repository;

import com.pranapulse.core.feedback.domain.ScanFeedback;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ScanFeedbackRepository extends JpaRepository<ScanFeedback, UUID> {

    Optional<ScanFeedback> findBySession_Id(UUID sessionId);
}
