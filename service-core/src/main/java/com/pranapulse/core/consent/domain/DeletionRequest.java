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
        name = "deletion_requests",
        indexes = {
                @Index(name = "idx_deletion_requests_user_id", columnList = "user_id"),
                @Index(name = "idx_deletion_requests_status", columnList = "status")
        }
)
public class DeletionRequest extends AuditableEntity {

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "user_id", nullable = false)
    private User user;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 32)
    private DeletionRequestStatus status = DeletionRequestStatus.PENDING;

    @Column(name = "purged_at")
    private Instant purgedAt;

    @Column(name = "failure_reason", length = 512)
    private String failureReason;

    protected DeletionRequest() {
    }

    public DeletionRequest(User user) {
        this.user = Objects.requireNonNull(user, "user must not be null");
    }

    public User getUser() {
        return user;
    }

    public DeletionRequestStatus getStatus() {
        return status;
    }

    public Instant getPurgedAt() {
        return purgedAt;
    }

    public String getFailureReason() {
        return failureReason;
    }
}
