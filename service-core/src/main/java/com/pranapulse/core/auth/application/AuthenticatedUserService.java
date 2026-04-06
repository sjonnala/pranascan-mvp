package com.pranapulse.core.auth.application;

import com.pranapulse.core.auth.domain.User;
import com.pranapulse.core.auth.repository.UserRepository;
import com.pranapulse.core.shared.error.NotFoundException;
import java.time.Instant;
import java.util.Optional;
import java.util.UUID;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AuthenticatedUserService {

    private final UserRepository userRepository;

    public AuthenticatedUserService(UserRepository userRepository) {
        this.userRepository = userRepository;
    }

    @Transactional
    public User getOrProvisionUser(Jwt jwt) {
        String subject = require(jwt.getSubject(), "OIDC subject is required.");
        String email = normalize(jwt.getClaimAsString("email"));
        String displayName = firstNonBlank(
                jwt.getClaimAsString("name"),
                jwt.getClaimAsString("preferred_username"),
                email,
                subject
        );
        String phone = normalize(jwt.getClaimAsString("phone_number"));
        String avatarUrl = normalize(jwt.getClaimAsString("picture"));

        User user = userRepository.findByOidcSubject(subject).orElse(null);
        boolean dirty = false;

        if (user == null) {
            user = new User(subject, email, displayName, phone);
            dirty = true;
        }

        // User attributes might change in Keycloak
        if (!java.util.Objects.equals(user.getOidcSubject(), subject)) {
            user.setOidcSubject(subject);
            dirty = true;
        }
        if (!java.util.Objects.equals(user.getEmail(), email)) {
            user.setEmail(email);
            dirty = true;
        }
        if (!java.util.Objects.equals(user.getDisplayName(), displayName)) {
            user.setDisplayName(displayName);
            dirty = true;
        }
        if (!java.util.Objects.equals(user.getPhoneE164(), phone)) {
            user.setPhoneE164(phone);
            dirty = true;
        }
        if (!java.util.Objects.equals(user.getAvatarUrl(), avatarUrl)) {
            user.setAvatarUrl(avatarUrl);
            dirty = true;
        }
        if (!user.isActive()) {
            user.activate();
            dirty = true;
        }

        // Throttle lastLoginAt updates to once per hour to prevent constant db writes
        Instant now = Instant.now();
        if (user.getLastLoginAt() == null || user.getLastLoginAt().isBefore(now.minusSeconds(3600))) {
            user.recordLogin(now);
            dirty = true;
        }

        return dirty ? userRepository.save(user) : user;
    }

    @Transactional(readOnly = true)
    public User findRequiredUser(UUID userId) {
        return userRepository.findById(userId)
                .orElseThrow(() -> new NotFoundException("User not found: " + userId));
    }

    private static String firstNonBlank(String... candidates) {
        for (String candidate : candidates) {
            String normalized = normalize(candidate);
            if (normalized != null) {
                return normalized;
            }
        }
        return null;
    }

    private static String normalize(String value) {
        if (value == null) {
            return null;
        }
        String trimmed = value.trim();
        return trimmed.isEmpty() ? null : trimmed;
    }

    private static String require(String value, String message) {
        return Optional.ofNullable(normalize(value))
                .orElseThrow(() -> new IllegalArgumentException(message));
    }
}
