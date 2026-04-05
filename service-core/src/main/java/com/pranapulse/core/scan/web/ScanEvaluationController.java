package com.pranapulse.core.scan.web;

import com.pranapulse.core.auth.application.AuthenticatedUserService;
import com.pranapulse.core.auth.domain.User;
import com.pranapulse.core.scan.application.ScanEvaluationService;
import jakarta.validation.Valid;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/scans")
public class ScanEvaluationController {

    private final AuthenticatedUserService authenticatedUserService;
    private final ScanEvaluationService scanEvaluationService;

    public ScanEvaluationController(
            AuthenticatedUserService authenticatedUserService,
            ScanEvaluationService scanEvaluationService
    ) {
        this.authenticatedUserService = authenticatedUserService;
        this.scanEvaluationService = scanEvaluationService;
    }

    @PostMapping("/evaluations")
    public ScanEvaluationResponse evaluateScan(
            @AuthenticationPrincipal Jwt jwt,
            @Valid @RequestBody ScanEvaluationRequest request
    ) {
        User user = authenticatedUserService.getOrProvisionUser(jwt);
        return ScanEvaluationResponse.from(
                user.getId(),
                scanEvaluationService.evaluate(request.toCommand())
        );
    }
}
