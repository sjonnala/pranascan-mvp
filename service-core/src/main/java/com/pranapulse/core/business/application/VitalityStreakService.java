package com.pranapulse.core.business.application;

import com.pranapulse.core.auth.domain.User;
import com.pranapulse.core.business.domain.VitalityStreak;
import com.pranapulse.core.business.repository.VitalityStreakRepository;
import java.time.LocalDate;
import java.time.ZoneOffset;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class VitalityStreakService {

    private final VitalityStreakRepository vitalityStreakRepository;

    public VitalityStreakService(VitalityStreakRepository vitalityStreakRepository) {
        this.vitalityStreakRepository = vitalityStreakRepository;
    }

    @Transactional
    public VitalityStreak getOrCreate(User user) {
        return vitalityStreakRepository.findByUserId(user.getId())
                .orElseGet(() -> vitalityStreakRepository.save(new VitalityStreak(user)));
    }

    @Transactional
    public VitalityStreak registerCheckIn(User user, LocalDate checkInDate) {
        LocalDate effectiveDate = checkInDate != null
                ? checkInDate
                : LocalDate.now(ZoneOffset.UTC);
        VitalityStreak streak = getOrCreate(user);
        streak.registerCheckIn(effectiveDate);
        return vitalityStreakRepository.save(streak);
    }
}
