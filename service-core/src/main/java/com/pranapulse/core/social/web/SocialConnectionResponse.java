package com.pranapulse.core.social.web;

import com.pranapulse.core.social.domain.SocialConnection;
import com.pranapulse.core.social.domain.SocialConnectionStatus;
import java.time.Instant;
import java.util.UUID;

public record SocialConnectionResponse(
        UUID id,
        UUID requesterUserId,
        String requesterDisplayName,
        UUID addresseeUserId,
        String addresseeDisplayName,
        SocialConnectionStatus status,
        Instant respondedAt,
        Instant createdAt,
        Instant updatedAt
) {

    public static SocialConnectionResponse from(SocialConnection connection) {
        return new SocialConnectionResponse(
                connection.getId(),
                connection.getRequesterUser().getId(),
                connection.getRequesterUser().getDisplayName(),
                connection.getAddresseeUser().getId(),
                connection.getAddresseeUser().getDisplayName(),
                connection.getStatus(),
                connection.getRespondedAt(),
                connection.getCreatedAt(),
                connection.getUpdatedAt()
        );
    }
}
