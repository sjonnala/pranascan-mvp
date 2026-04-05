package com.pranapulse.core.business.web;

import com.pranapulse.core.auth.application.AuthenticatedUserService;
import com.pranapulse.core.auth.domain.User;
import com.pranapulse.core.business.application.VitalityStreakService;
import jakarta.validation.Valid;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/business/vitality-streak")
public class VitalityStreakController {

    private final AuthenticatedUserService authenticatedUserService;
    private final VitalityStreakService vitalityStreakService;

    public VitalityStreakController(
            AuthenticatedUserService authenticatedUserService,
            VitalityStreakService vitalityStreakService
    ) {
        this.authenticatedUserService = authenticatedUserService;
        this.vitalityStreakService = vitalityStreakService;
    }

    @GetMapping
    public VitalityStreakResponse getCurrentStreak(@AuthenticationPrincipal Jwt jwt) {
        User user = authenticatedUserService.getOrProvisionUser(jwt);
        return VitalityStreakResponse.from(vitalityStreakService.getOrCreate(user));
    }

    @PostMapping("/check-ins")
    public VitalityStreakResponse registerCheckIn(
            @AuthenticationPrincipal Jwt jwt,
            @Valid @RequestBody(required = false) RegisterCheckInRequest request
    ) {
        User user = authenticatedUserService.getOrProvisionUser(jwt);
        return VitalityStreakResponse.from(
                vitalityStreakService.registerCheckIn(
                        user,
                        request != null ? request.checkInDate() : null
                )
        );
    }
}
