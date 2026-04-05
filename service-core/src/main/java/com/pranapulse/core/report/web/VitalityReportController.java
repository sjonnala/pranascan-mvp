package com.pranapulse.core.report.web;

import com.pranapulse.core.auth.application.AuthenticatedUserService;
import com.pranapulse.core.auth.domain.User;
import com.pranapulse.core.report.application.VitalityReportService;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/reports")
public class VitalityReportController {

    private final AuthenticatedUserService authenticatedUserService;
    private final VitalityReportService vitalityReportService;

    public VitalityReportController(
            AuthenticatedUserService authenticatedUserService,
            VitalityReportService vitalityReportService
    ) {
        this.authenticatedUserService = authenticatedUserService;
        this.vitalityReportService = vitalityReportService;
    }

    @PostMapping("/generate")
    @ResponseStatus(HttpStatus.CREATED)
    public VitalityReportResponse generate(@AuthenticationPrincipal Jwt jwt) {
        User user = authenticatedUserService.getOrProvisionUser(jwt);
        return VitalityReportResponse.from(vitalityReportService.generate(user.getId()));
    }

    @GetMapping("/latest")
    public VitalityReportResponse latest(@AuthenticationPrincipal Jwt jwt) {
        User user = authenticatedUserService.getOrProvisionUser(jwt);
        return VitalityReportResponse.from(vitalityReportService.getLatest(user.getId()));
    }
}
