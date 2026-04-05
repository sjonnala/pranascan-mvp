package com.pranapulse.core.feedback.web;

import com.pranapulse.core.auth.application.AuthenticatedUserService;
import com.pranapulse.core.auth.domain.User;
import com.pranapulse.core.feedback.application.FeedbackService;
import jakarta.validation.Valid;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/feedback")
public class FeedbackController {

    private final AuthenticatedUserService authenticatedUserService;
    private final FeedbackService feedbackService;

    public FeedbackController(
            AuthenticatedUserService authenticatedUserService,
            FeedbackService feedbackService
    ) {
        this.authenticatedUserService = authenticatedUserService;
        this.feedbackService = feedbackService;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public FeedbackResponse createFeedback(
            @AuthenticationPrincipal Jwt jwt,
            @Valid @RequestBody FeedbackCreateRequest request
    ) {
        User user = authenticatedUserService.getOrProvisionUser(jwt);
        return FeedbackResponse.from(feedbackService.create(
                user.getId(),
                request.sessionId(),
                request.usefulResponse(),
                request.npsScore(),
                request.comment()
        ));
    }

    @GetMapping("/sessions/{sessionId}")
    public FeedbackResponse getFeedbackForSession(
            @AuthenticationPrincipal Jwt jwt,
            @PathVariable UUID sessionId
    ) {
        User user = authenticatedUserService.getOrProvisionUser(jwt);
        return FeedbackResponse.from(feedbackService.getForSession(user.getId(), sessionId));
    }
}
