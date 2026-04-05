package com.pranapulse.core.consent.web;

import com.pranapulse.core.consent.domain.ConsentRecord;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import java.time.Instant;
import java.util.UUID;

@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record ConsentRecordResponse(
        UUID id,
        UUID userId,
        String action,
        String consentVersion,
        String purpose,
        Instant createdAt,
        Instant deletionScheduledAt
) {

    public static ConsentRecordResponse from(ConsentRecord record) {
        return new ConsentRecordResponse(
                record.getId(),
                record.getUser().getId(),
                record.getAction().value(),
                record.getConsentVersion(),
                record.getPurpose(),
                record.getCreatedAt(),
                record.getDeletionScheduledAt()
        );
    }
}
