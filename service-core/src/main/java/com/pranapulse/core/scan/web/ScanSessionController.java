package com.pranapulse.core.scan.web;

import com.pranapulse.core.auth.application.AuthenticatedUserService;
import com.pranapulse.core.auth.domain.User;
import com.pranapulse.core.scan.application.ScanSessionService;
import jakarta.validation.Valid;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/scans/sessions")
public class ScanSessionController {

    private final AuthenticatedUserService authenticatedUserService;
    private final ScanSessionService scanSessionService;

    public ScanSessionController(
            AuthenticatedUserService authenticatedUserService,
            ScanSessionService scanSessionService
    ) {
        this.authenticatedUserService = authenticatedUserService;
        this.scanSessionService = scanSessionService;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public ScanSessionResponse createSession(
            @AuthenticationPrincipal Jwt jwt,
            @Valid @RequestBody CreateScanSessionRequest request
    ) {
        User user = authenticatedUserService.getOrProvisionUser(jwt);
        return ScanSessionResponse.from(scanSessionService.createSession(user.getId(), request.toCommand()));
    }

    @PutMapping("/{sessionId}/complete")
    public ScanResultResponse completeSession(
            @AuthenticationPrincipal Jwt jwt,
            @PathVariable UUID sessionId,
            @Valid @RequestBody ScanEvaluationRequest request
    ) {
        User user = authenticatedUserService.getOrProvisionUser(jwt);
        return ScanResultResponse.from(
                scanSessionService.completeSession(user.getId(), sessionId, request.toCommand())
        );
    }

    @GetMapping("/{sessionId}")
    public ScanSessionWithResultResponse getSession(
            @AuthenticationPrincipal Jwt jwt,
            @PathVariable UUID sessionId
    ) {
        User user = authenticatedUserService.getOrProvisionUser(jwt);
        return ScanSessionWithResultResponse.from(scanSessionService.getSession(user.getId(), sessionId));
    }

    @GetMapping("/history")
    public ScanHistoryResponse getHistory(
            @AuthenticationPrincipal Jwt jwt,
            @RequestParam(name = "page", defaultValue = "1") int page,
            @RequestParam(name = "page_size", defaultValue = "20") int pageSize
    ) {
        User user = authenticatedUserService.getOrProvisionUser(jwt);
        return ScanHistoryResponse.from(scanSessionService.getHistory(user.getId(), page, pageSize));
    }
}
