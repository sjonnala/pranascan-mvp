package com.pranapulse.core.feedback.web;

import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import com.pranapulse.core.feedback.domain.ScanFeedback;
import java.time.Instant;
import java.util.UUID;

@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record FeedbackResponse(
        UUID id,
        UUID sessionId,
        UUID userId,
        String usefulResponse,
        Integer npsScore,
        String comment,
        Instant createdAt
) {

    public static FeedbackResponse from(ScanFeedback feedback) {
        return new FeedbackResponse(
                feedback.getId(),
                feedback.getSession().getId(),
                feedback.getUser().getId(),
                feedback.getUsefulResponse(),
                feedback.getNpsScore(),
                feedback.getComment(),
                feedback.getCreatedAt()
        );
    }
}
