package com.pranapulse.core.auth.web;

import com.pranapulse.core.auth.application.AuthenticatedUserService;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/auth")
public class AuthController {

    private final AuthenticatedUserService authenticatedUserService;

    public AuthController(AuthenticatedUserService authenticatedUserService) {
        this.authenticatedUserService = authenticatedUserService;
    }

    @GetMapping("/me")
    public UserProfileResponse currentUser(@AuthenticationPrincipal Jwt jwt) {
        return UserProfileResponse.from(authenticatedUserService.getOrProvisionUser(jwt));
    }
}
