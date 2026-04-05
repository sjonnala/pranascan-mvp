package com.pranapulse.core.scan.domain;

import com.pranapulse.core.auth.domain.User;
import com.pranapulse.core.shared.error.ConflictException;
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
import java.util.UUID;
import org.springframework.security.access.AccessDeniedException;

@Entity
@Table(
        schema = "core",
        name = "scan_sessions",
        indexes = {
                @Index(name = "idx_scan_sessions_user_id", columnList = "user_id"),
                @Index(name = "idx_scan_sessions_status", columnList = "status")
        }
)
public class ScanSession extends AuditableEntity {

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "user_id", nullable = false)
    private User user;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 32)
    private ScanSessionStatus status = ScanSessionStatus.INITIATED;

    @Column(name = "device_model", length = 128)
    private String deviceModel;

    @Column(name = "app_version", length = 32)
    private String appVersion;

    @Column(name = "completed_at")
    private Instant completedAt;

    protected ScanSession() {
    }

    public ScanSession(User user, String deviceModel, String appVersion) {
        this.user = Objects.requireNonNull(user, "user must not be null");
        this.deviceModel = normalize(deviceModel);
        this.appVersion = normalize(appVersion);
    }

    public User getUser() {
        return user;
    }

    public ScanSessionStatus getStatus() {
        return status;
    }

    public String getDeviceModel() {
        return deviceModel;
    }

    public String getAppVersion() {
        return appVersion;
    }

    public Instant getCompletedAt() {
        return completedAt;
    }

    public void ensureOwnedBy(UUID actingUserId) {
        if (!Objects.equals(user.getId(), actingUserId)) {
            throw new AccessDeniedException("Session not found.");
        }
    }

    public void ensureCompletable() {
        if (status != ScanSessionStatus.INITIATED) {
            throw new ConflictException("Session is already in status '" + status.value() + "'.");
        }
    }

    public void markCompleted(Instant completedAt) {
        ensureCompletable();
        this.status = ScanSessionStatus.COMPLETED;
        this.completedAt = Objects.requireNonNull(completedAt, "completedAt must not be null");
    }

    public void markRejected(Instant completedAt) {
        ensureCompletable();
        this.status = ScanSessionStatus.REJECTED;
        this.completedAt = Objects.requireNonNull(completedAt, "completedAt must not be null");
    }

    private static String normalize(String value) {
        if (value == null) {
            return null;
        }
        String trimmed = value.trim();
        return trimmed.isEmpty() ? null : trimmed;
    }
}
