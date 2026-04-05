package com.pranapulse.core.social.web;

import com.pranapulse.core.auth.application.AuthenticatedUserService;
import com.pranapulse.core.auth.domain.User;
import com.pranapulse.core.social.application.SocialConnectionService;
import jakarta.validation.Valid;
import java.util.List;
import java.util.UUID;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/social/connections")
public class SocialController {

    private final AuthenticatedUserService authenticatedUserService;
    private final SocialConnectionService socialConnectionService;

    public SocialController(
            AuthenticatedUserService authenticatedUserService,
            SocialConnectionService socialConnectionService
    ) {
        this.authenticatedUserService = authenticatedUserService;
        this.socialConnectionService = socialConnectionService;
    }

    @GetMapping
    public List<SocialConnectionResponse> listConnections(@AuthenticationPrincipal Jwt jwt) {
        User user = authenticatedUserService.getOrProvisionUser(jwt);
        return socialConnectionService.listConnections(user)
                .stream()
                .map(SocialConnectionResponse::from)
                .toList();
    }

    @PostMapping
    public SocialConnectionResponse createConnection(
            @AuthenticationPrincipal Jwt jwt,
            @Valid @RequestBody CreateSocialConnectionRequest request
    ) {
        User user = authenticatedUserService.getOrProvisionUser(jwt);
        return SocialConnectionResponse.from(
                socialConnectionService.createConnectionRequest(user, request.targetUserId())
        );
    }

    @PostMapping("/{connectionId}/accept")
    public SocialConnectionResponse acceptConnection(
            @AuthenticationPrincipal Jwt jwt,
            @PathVariable UUID connectionId
    ) {
        User user = authenticatedUserService.getOrProvisionUser(jwt);
        return SocialConnectionResponse.from(
                socialConnectionService.accept(user, connectionId)
        );
    }

    @PostMapping("/{connectionId}/decline")
    public SocialConnectionResponse declineConnection(
            @AuthenticationPrincipal Jwt jwt,
            @PathVariable UUID connectionId
    ) {
        User user = authenticatedUserService.getOrProvisionUser(jwt);
        return SocialConnectionResponse.from(
                socialConnectionService.decline(user, connectionId)
        );
    }
}
