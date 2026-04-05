package com.pranapulse.core.infrastructure.security;

import java.util.List;
import java.util.Objects;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;

final class AudienceValidator implements OAuth2TokenValidator<Jwt> {

    private final String requiredAudience;

    AudienceValidator(String requiredAudience) {
        this.requiredAudience = Objects.requireNonNull(
                requiredAudience,
                "requiredAudience must not be null"
        );
    }

    @Override
    public OAuth2TokenValidatorResult validate(Jwt token) {
        List<String> audience = token.getAudience();
        if (audience != null && audience.contains(requiredAudience)) {
            return OAuth2TokenValidatorResult.success();
        }

        OAuth2Error error = new OAuth2Error(
                "invalid_token",
                "The required audience is missing.",
                null
        );
        return OAuth2TokenValidatorResult.failure(error);
    }
}
