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

        User user = userRepository.findByOidcSubject(subject)
                .orElseGet(() -> new User(subject, email, displayName, phone));

        user.setOidcSubject(subject);
        user.setEmail(email);
        user.setDisplayName(displayName);
        user.setPhoneE164(phone);
        user.setAvatarUrl(avatarUrl);
        user.activate();
        user.recordLogin(Instant.now());

        return userRepository.save(user);
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
