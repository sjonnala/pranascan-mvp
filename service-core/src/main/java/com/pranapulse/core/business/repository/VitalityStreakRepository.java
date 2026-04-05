package com.pranapulse.core.business.repository;

import com.pranapulse.core.business.domain.VitalityStreak;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface VitalityStreakRepository extends JpaRepository<VitalityStreak, UUID> {

    @Query("""
            select streak
            from VitalityStreak streak
            join fetch streak.user
            where streak.user.id = :userId
            """)
    Optional<VitalityStreak> findByUserId(@Param("userId") UUID userId);
}
