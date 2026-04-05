package com.pranapulse.core.social.domain;

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
import jakarta.persistence.UniqueConstraint;
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;
import org.springframework.security.access.AccessDeniedException;

@Entity
@Table(
        schema = "core",
        name = "social_connections",
        indexes = {
                @Index(name = "idx_social_connections_requester_user_id", columnList = "requester_user_id"),
                @Index(name = "idx_social_connections_addressee_user_id", columnList = "addressee_user_id"),
                @Index(name = "idx_social_connections_status", columnList = "status")
        },
        uniqueConstraints = {
                @UniqueConstraint(
                        name = "uk_social_connections_pair",
                        columnNames = {"requester_user_id", "addressee_user_id"}
                )
        }
)
public class SocialConnection extends AuditableEntity {

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "requester_user_id", nullable = false)
    private User requesterUser;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "addressee_user_id", nullable = false)
    private User addresseeUser;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 32)
    private SocialConnectionStatus status = SocialConnectionStatus.PENDING;

    @Column(name = "responded_at")
    private Instant respondedAt;

    protected SocialConnection() {
    }

    public SocialConnection(User requesterUser, User addresseeUser) {
        this.requesterUser = Objects.requireNonNull(requesterUser, "requesterUser must not be null");
        this.addresseeUser = Objects.requireNonNull(addresseeUser, "addresseeUser must not be null");
        if (Objects.equals(requesterUser.getId(), addresseeUser.getId())) {
            throw new IllegalArgumentException("A user cannot connect to themselves.");
        }
    }

    public User getRequesterUser() {
        return requesterUser;
    }

    public User getAddresseeUser() {
        return addresseeUser;
    }

    public SocialConnectionStatus getStatus() {
        return status;
    }

    public Instant getRespondedAt() {
        return respondedAt;
    }

    public boolean involves(UUID userId) {
        return Objects.equals(requesterUser.getId(), userId)
                || Objects.equals(addresseeUser.getId(), userId);
    }

    public void accept(UUID actingUserId) {
        requireAddressee(actingUserId);
        requirePending();
        status = SocialConnectionStatus.ACCEPTED;
        respondedAt = Instant.now();
    }

    public void decline(UUID actingUserId) {
        requireAddressee(actingUserId);
        requirePending();
        status = SocialConnectionStatus.DECLINED;
        respondedAt = Instant.now();
    }

    private void requireAddressee(UUID actingUserId) {
        if (!Objects.equals(addresseeUser.getId(), actingUserId)) {
            throw new AccessDeniedException("Only the invited user can respond to the request.");
        }
    }

    private void requirePending() {
        if (status != SocialConnectionStatus.PENDING) {
            throw new IllegalArgumentException("Only pending requests can be updated.");
        }
    }
}
