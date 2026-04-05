package com.pranapulse.core.business.web;

import com.pranapulse.core.business.domain.VitalityStreak;
import com.pranapulse.core.business.domain.StreakStatus;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

public record VitalityStreakResponse(
        UUID id,
        UUID userId,
        int currentStreakDays,
        int longestStreakDays,
        LocalDate lastCheckInOn,
        LocalDate streakStartedOn,
        LocalDate graceWindowEndsOn,
        StreakStatus status,
        Instant createdAt,
        Instant updatedAt
) {

    public static VitalityStreakResponse from(VitalityStreak streak) {
        return new VitalityStreakResponse(
                streak.getId(),
                streak.getUser().getId(),
                streak.getCurrentStreakDays(),
                streak.getLongestStreakDays(),
                streak.getLastCheckInOn(),
                streak.getStreakStartedOn(),
                streak.getGraceWindowEndsOn(),
                streak.getStatus(),
                streak.getCreatedAt(),
                streak.getUpdatedAt()
        );
    }
}
