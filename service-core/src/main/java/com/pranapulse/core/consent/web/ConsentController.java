package com.pranapulse.core.consent.web;

import com.pranapulse.core.auth.application.AuthenticatedUserService;
import com.pranapulse.core.auth.domain.User;
import com.pranapulse.core.consent.application.ConsentService;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/consent")
public class ConsentController {

    private final AuthenticatedUserService authenticatedUserService;
    private final ConsentService consentService;

    public ConsentController(
            AuthenticatedUserService authenticatedUserService,
            ConsentService consentService
    ) {
        this.authenticatedUserService = authenticatedUserService;
        this.consentService = consentService;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public ConsentRecordResponse grantConsent(
            @AuthenticationPrincipal Jwt jwt,
            @Valid @RequestBody GrantConsentRequest request,
            HttpServletRequest httpRequest
    ) {
        User user = authenticatedUserService.getOrProvisionUser(jwt);
        return ConsentRecordResponse.from(consentService.grantConsent(
                user.getId(),
                request.consentVersion(),
                request.purpose(),
                firstNonBlank(request.ipAddress(), extractClientIp(httpRequest)),
                firstNonBlank(request.userAgent(), httpRequest.getHeader("User-Agent"))
        ));
    }

    @PostMapping("/revoke")
    @ResponseStatus(HttpStatus.CREATED)
    public ConsentRecordResponse revokeConsent(
            @AuthenticationPrincipal Jwt jwt,
            @Valid @RequestBody RevokeConsentRequest request,
            HttpServletRequest httpRequest
    ) {
        User user = authenticatedUserService.getOrProvisionUser(jwt);
        return ConsentRecordResponse.from(consentService.revokeConsent(
                user.getId(),
                extractClientIp(httpRequest),
                httpRequest.getHeader("User-Agent")
        ));
    }

    @PostMapping("/deletion-request")
    @ResponseStatus(HttpStatus.CREATED)
    public ConsentRecordResponse requestDeletion(
            @AuthenticationPrincipal Jwt jwt,
            @Valid @RequestBody RequestDeletionRequest request,
            HttpServletRequest httpRequest
    ) {
        User user = authenticatedUserService.getOrProvisionUser(jwt);
        return ConsentRecordResponse.from(consentService.requestDeletion(
                user.getId(),
                extractClientIp(httpRequest),
                httpRequest.getHeader("User-Agent")
        ));
    }

    @GetMapping("/status")
    public ConsentStatusResponse getConsentStatus(@AuthenticationPrincipal Jwt jwt) {
        User user = authenticatedUserService.getOrProvisionUser(jwt);
        return ConsentStatusResponse.from(consentService.getConsentStatus(user.getId()));
    }

    private static String extractClientIp(HttpServletRequest request) {
        String forwardedFor = request.getHeader("X-Forwarded-For");
        if (forwardedFor != null && !forwardedFor.isBlank()) {
            return forwardedFor.split(",")[0].trim();
        }
        return request.getRemoteAddr();
    }

    private static String firstNonBlank(String preferred, String fallback) {
        if (preferred != null && !preferred.isBlank()) {
            return preferred.trim();
        }
        return fallback != null && !fallback.isBlank() ? fallback.trim() : null;
    }
}
