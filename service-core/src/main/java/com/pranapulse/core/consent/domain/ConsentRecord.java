package com.pranapulse.core.consent.domain;

import com.pranapulse.core.auth.domain.User;
import com.pranapulse.core.shared.persistence.AuditableEntity;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.Index;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.Objects;

@Entity
@Table(
        schema = "core",
        name = "consent_records",
        indexes = {
                @Index(name = "idx_consent_records_user_id", columnList = "user_id"),
                @Index(name = "idx_consent_records_action", columnList = "action")
        }
)
public class ConsentRecord extends AuditableEntity {

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "user_id", nullable = false)
    private User user;

    @Enumerated(EnumType.STRING)
    @Column(name = "action", nullable = false, length = 32)
    private ConsentAction action;

    @Column(name = "consent_version", nullable = false, length = 16)
    private String consentVersion;

    @Column(name = "purpose", nullable = false, length = 256)
    private String purpose;

    @Column(name = "ip_address", length = 64)
    private String ipAddress;

    @Column(name = "user_agent", length = 512)
    private String userAgent;

    @Column(name = "deletion_scheduled_at")
    private Instant deletionScheduledAt;

    protected ConsentRecord() {
    }

    public ConsentRecord(
            User user,
            ConsentAction action,
            String consentVersion,
            String purpose,
            String ipAddress,
            String userAgent,
            Instant deletionScheduledAt
    ) {
        this.user = Objects.requireNonNull(user, "user must not be null");
        this.action = Objects.requireNonNull(action, "action must not be null");
        this.consentVersion = require(consentVersion, "consentVersion");
        this.purpose = require(purpose, "purpose");
        this.ipAddress = normalize(ipAddress);
        this.userAgent = normalize(userAgent);
        this.deletionScheduledAt = deletionScheduledAt;
    }

    public User getUser() {
        return user;
    }

    public ConsentAction getAction() {
        return action;
    }

    public String getConsentVersion() {
        return consentVersion;
    }

    public String getPurpose() {
        return purpose;
    }

    public String getIpAddress() {
        return ipAddress;
    }

    public String getUserAgent() {
        return userAgent;
    }

    public Instant getDeletionScheduledAt() {
        return deletionScheduledAt;
    }

    private static String require(String value, String fieldName) {
        String normalized = normalize(value);
        if (normalized == null) {
            throw new IllegalArgumentException(fieldName + " must not be blank.");
        }
        return normalized;
    }

    private static String normalize(String value) {
        if (value == null) {
            return null;
        }
        String trimmed = value.trim();
        return trimmed.isEmpty() ? null : trimmed;
    }
}
