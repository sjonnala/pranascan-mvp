package com.pranapulse.core.consent.repository;

import com.pranapulse.core.consent.domain.ConsentRecord;
import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ConsentRecordRepository extends JpaRepository<ConsentRecord, UUID> {

    List<ConsentRecord> findByUser_IdOrderByCreatedAtAscIdAsc(UUID userId);
}
