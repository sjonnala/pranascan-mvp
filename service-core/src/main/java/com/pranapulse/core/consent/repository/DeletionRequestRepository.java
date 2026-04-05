package com.pranapulse.core.consent.repository;

import com.pranapulse.core.consent.domain.DeletionRequest;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface DeletionRequestRepository extends JpaRepository<DeletionRequest, UUID> {

    long countByUser_Id(UUID userId);
}
