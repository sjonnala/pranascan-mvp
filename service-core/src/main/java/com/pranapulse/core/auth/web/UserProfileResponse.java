package com.pranapulse.core.auth.web;

import com.pranapulse.core.auth.domain.User;
import java.time.Instant;
import java.util.UUID;

public record UserProfileResponse(
        UUID id,
        String oidcSubject,
        String email,
        String displayName,
        String phoneE164,
        String avatarUrl,
        boolean active,
        Instant lastLoginAt,
        Instant createdAt,
        Instant updatedAt
) {

    public static UserProfileResponse from(User user) {
        return new UserProfileResponse(
                user.getId(),
                user.getOidcSubject(),
                user.getEmail(),
                user.getDisplayName(),
                user.getPhoneE164(),
                user.getAvatarUrl(),
                user.isActive(),
                user.getLastLoginAt(),
                user.getCreatedAt(),
                user.getUpdatedAt()
        );
    }
}
