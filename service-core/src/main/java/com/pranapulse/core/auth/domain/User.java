package com.pranapulse.core.auth.domain;

import com.pranapulse.core.shared.persistence.AuditableEntity;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import java.time.Instant;
import java.util.Objects;

@Entity
@Table(
        schema = "core",
        name = "users",
        uniqueConstraints = {
                @UniqueConstraint(name = "uk_users_oidc_subject", columnNames = "oidc_subject"),
                @UniqueConstraint(name = "uk_users_email", columnNames = "email"),
                @UniqueConstraint(name = "uk_users_phone_e164", columnNames = "phone_e164")
        }
)
public class User extends AuditableEntity {

    @Column(name = "oidc_subject", nullable = false, length = 128)
    private String oidcSubject;

    @Column(name = "email", length = 320)
    private String email;

    @Column(name = "display_name", nullable = false, length = 120)
    private String displayName;

    @Column(name = "phone_e164", length = 20)
    private String phoneE164;

    @Column(name = "avatar_url", length = 512)
    private String avatarUrl;

    @Column(name = "is_active", nullable = false)
    private boolean active = true;

    @Column(name = "last_login_at")
    private Instant lastLoginAt;

    protected User() {
    }

    public User(String oidcSubject, String email, String displayName, String phoneE164) {
        this.oidcSubject = Objects.requireNonNull(oidcSubject, "oidcSubject must not be null");
        this.email = normalize(email);
        this.displayName = normalizeDisplayName(displayName, oidcSubject);
        this.phoneE164 = normalize(phoneE164);
    }

    public String getOidcSubject() {
        return oidcSubject;
    }

    public void setOidcSubject(String oidcSubject) {
        this.oidcSubject = Objects.requireNonNull(oidcSubject, "oidcSubject must not be null");
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = normalize(email);
    }

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = normalizeDisplayName(displayName, oidcSubject);
    }

    public String getPhoneE164() {
        return phoneE164;
    }

    public void setPhoneE164(String phoneE164) {
        this.phoneE164 = normalize(phoneE164);
    }

    public String getAvatarUrl() {
        return avatarUrl;
    }

    public void setAvatarUrl(String avatarUrl) {
        this.avatarUrl = normalize(avatarUrl);
    }

    public boolean isActive() {
        return active;
    }

    public void activate() {
        this.active = true;
    }

    public void deactivate() {
        this.active = false;
    }

    public Instant getLastLoginAt() {
        return lastLoginAt;
    }

    public void recordLogin(Instant loggedInAt) {
        this.lastLoginAt = Objects.requireNonNull(loggedInAt, "loggedInAt must not be null");
    }

    private static String normalize(String value) {
        if (value == null) {
            return null;
        }
        String trimmed = value.trim();
        return trimmed.isEmpty() ? null : trimmed;
    }

    private static String normalizeDisplayName(String displayName, String fallback) {
        String normalized = normalize(displayName);
        return normalized != null ? normalized : fallback;
    }
}
