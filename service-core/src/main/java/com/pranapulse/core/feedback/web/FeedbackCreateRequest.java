package com.pranapulse.core.feedback.web;

import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import java.util.UUID;

@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record FeedbackCreateRequest(
        @NotNull UUID sessionId,
        @NotNull
        @Pattern(regexp = "useful|needs_work", message = "useful_response must be 'useful' or 'needs_work'.")
        String usefulResponse,
        @Min(value = 0, message = "nps_score must be between 0 and 10.")
        @Max(value = 10, message = "nps_score must be between 0 and 10.")
        Integer npsScore,
        @Size(max = 500, message = "comment must not exceed 500 characters.")
        String comment
) {

    public FeedbackCreateRequest {
        usefulResponse = usefulResponse != null ? usefulResponse.trim() : null;
        comment = normalizeComment(comment);
    }

    private static String normalizeComment(String comment) {
        if (comment == null) {
            return null;
        }
        String trimmed = comment.trim();
        return trimmed.isEmpty() ? null : trimmed;
    }
}
