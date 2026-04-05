package com.pranapulse.core.business.domain;

import com.pranapulse.core.auth.domain.User;
import java.time.LocalDate;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class VitalityStreakTest {

    @Test
    void startsAStreakOnFirstCheckIn() {
        User user = new User("oidc-subject-1", "a@example.com", "Asha", null);
        VitalityStreak streak = new VitalityStreak(user);

        streak.registerCheckIn(LocalDate.of(2026, 4, 4));

        assertEquals(1, streak.getCurrentStreakDays());
        assertEquals(1, streak.getLongestStreakDays());
        assertEquals(LocalDate.of(2026, 4, 4), streak.getLastCheckInOn());
        assertEquals(StreakStatus.ACTIVE, streak.getStatus());
    }

    @Test
    void extendsTheStreakForConsecutiveDays() {
        User user = new User("oidc-subject-2", "b@example.com", "Bhavna", null);
        VitalityStreak streak = new VitalityStreak(user);

        streak.registerCheckIn(LocalDate.of(2026, 4, 4));
        streak.registerCheckIn(LocalDate.of(2026, 4, 5));

        assertEquals(2, streak.getCurrentStreakDays());
        assertEquals(2, streak.getLongestStreakDays());
    }

    @Test
    void resetsCurrentStreakAfterAGap() {
        User user = new User("oidc-subject-3", "c@example.com", "Charu", null);
        VitalityStreak streak = new VitalityStreak(user);

        streak.registerCheckIn(LocalDate.of(2026, 4, 1));
        streak.registerCheckIn(LocalDate.of(2026, 4, 2));
        streak.registerCheckIn(LocalDate.of(2026, 4, 5));

        assertEquals(1, streak.getCurrentStreakDays());
        assertEquals(2, streak.getLongestStreakDays());
        assertEquals(LocalDate.of(2026, 4, 5), streak.getStreakStartedOn());
    }
}
