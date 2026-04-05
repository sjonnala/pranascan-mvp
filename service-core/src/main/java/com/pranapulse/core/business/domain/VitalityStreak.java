package com.pranapulse.core.business.domain;

import com.pranapulse.core.auth.domain.User;
import com.pranapulse.core.shared.persistence.AuditableEntity;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.Index;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.OneToOne;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import java.time.LocalDate;
import java.util.Objects;

@Entity
@Table(
        schema = "core",
        name = "vitality_streaks",
        indexes = {
                @Index(name = "idx_vitality_streaks_status", columnList = "status")
        },
        uniqueConstraints = {
                @UniqueConstraint(name = "uk_vitality_streaks_user_id", columnNames = "user_id")
        }
)
public class VitalityStreak extends AuditableEntity {

    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "user_id", nullable = false)
    private User user;

    @Column(name = "current_streak_days", nullable = false)
    private int currentStreakDays;

    @Column(name = "longest_streak_days", nullable = false)
    private int longestStreakDays;

    @Column(name = "last_check_in_on")
    private LocalDate lastCheckInOn;

    @Column(name = "streak_started_on")
    private LocalDate streakStartedOn;

    @Column(name = "grace_window_ends_on")
    private LocalDate graceWindowEndsOn;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 32)
    private StreakStatus status = StreakStatus.ACTIVE;

    protected VitalityStreak() {
    }

    public VitalityStreak(User user) {
        this.user = Objects.requireNonNull(user, "user must not be null");
    }

    public User getUser() {
        return user;
    }

    public int getCurrentStreakDays() {
        return currentStreakDays;
    }

    public int getLongestStreakDays() {
        return longestStreakDays;
    }

    public LocalDate getLastCheckInOn() {
        return lastCheckInOn;
    }

    public LocalDate getStreakStartedOn() {
        return streakStartedOn;
    }

    public LocalDate getGraceWindowEndsOn() {
        return graceWindowEndsOn;
    }

    public StreakStatus getStatus() {
        return status;
    }

    public void registerCheckIn(LocalDate checkInDate) {
        Objects.requireNonNull(checkInDate, "checkInDate must not be null");

        if (lastCheckInOn != null && checkInDate.isBefore(lastCheckInOn)) {
            throw new IllegalArgumentException("checkInDate cannot move backwards");
        }

        if (lastCheckInOn == null) {
            currentStreakDays = 1;
            longestStreakDays = 1;
            streakStartedOn = checkInDate;
        } else if (checkInDate.equals(lastCheckInOn)) {
            status = StreakStatus.ACTIVE;
            graceWindowEndsOn = null;
            return;
        } else if (lastCheckInOn.plusDays(1).equals(checkInDate)) {
            currentStreakDays += 1;
            longestStreakDays = Math.max(longestStreakDays, currentStreakDays);
        } else {
            currentStreakDays = 1;
            streakStartedOn = checkInDate;
        }

        lastCheckInOn = checkInDate;
        status = StreakStatus.ACTIVE;
        graceWindowEndsOn = null;
    }

    public void markAtRisk(LocalDate graceWindowEndsOn) {
        this.graceWindowEndsOn = Objects.requireNonNull(
                graceWindowEndsOn,
                "graceWindowEndsOn must not be null"
        );
        this.status = StreakStatus.AT_RISK;
    }

    public void breakStreak() {
        currentStreakDays = 0;
        streakStartedOn = null;
        graceWindowEndsOn = null;
        status = StreakStatus.BROKEN;
    }
}
