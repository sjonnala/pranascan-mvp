package com.pranapulse.core.feedback.application;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;

import com.pranapulse.core.auth.domain.User;
import com.pranapulse.core.auth.repository.UserRepository;
import com.pranapulse.core.consent.application.ConsentService;
import com.pranapulse.core.feedback.domain.ScanFeedback;
import com.pranapulse.core.scan.application.CreateScanSessionCommand;
import com.pranapulse.core.scan.application.ScanEvaluationCommand;
import com.pranapulse.core.scan.application.ScanEvaluationOutcome;
import com.pranapulse.core.scan.application.ScanEvaluationService;
import com.pranapulse.core.scan.application.ScanSessionService;
import com.pranapulse.core.scan.domain.ScanSession;
import com.pranapulse.core.shared.error.ConflictException;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;

@SpringBootTest
class FeedbackServiceIntegrationTest {

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private ConsentService consentService;

    @Autowired
    private ScanSessionService scanSessionService;

    @Autowired
    private FeedbackService feedbackService;

    @MockBean
    private ScanEvaluationService scanEvaluationService;

    @Test
    void createsAndFetchesFeedbackForCompletedCoreSession() {
        User user = userRepository.save(new User("oidc-feedback-1", "feedback-1@example.com", "Feedback User", null));
        consentService.grantConsent(user.getId(), "1.0", "wellness_screening", null, null);
        when(scanEvaluationService.evaluate(any())).thenReturn(outcome());

        ScanSession session = scanSessionService.createSession(
                user.getId(),
                new CreateScanSessionCommand("Pixel 9", "1.2.0")
        );
        scanSessionService.completeSession(user.getId(), session.getId(), sampleCommand());

        ScanFeedback created = feedbackService.create(
                user.getId(),
                session.getId(),
                "useful",
                9,
                "Fast and easy."
        );

        ScanFeedback loaded = feedbackService.getForSession(user.getId(), session.getId());

        assertEquals(created.getId(), loaded.getId());
        assertEquals("useful", loaded.getUsefulResponse());
        assertEquals(9, loaded.getNpsScore());
        assertEquals("Fast and easy.", loaded.getComment());
    }

    @Test
    void rejectsDuplicateFeedbackForTheSameSession() {
        User user = userRepository.save(new User("oidc-feedback-2", "feedback-2@example.com", "Feedback User 2", null));
        consentService.grantConsent(user.getId(), "1.0", "wellness_screening", null, null);
        when(scanEvaluationService.evaluate(any())).thenReturn(outcome());

        ScanSession session = scanSessionService.createSession(
                user.getId(),
                new CreateScanSessionCommand("Pixel 9", "1.2.0")
        );
        scanSessionService.completeSession(user.getId(), session.getId(), sampleCommand());

        feedbackService.create(user.getId(), session.getId(), "useful", null, null);

        ConflictException conflict = assertThrows(
                ConflictException.class,
                () -> feedbackService.create(user.getId(), session.getId(), "needs_work", 4, "Duplicate")
        );
        assertEquals("Feedback has already been recorded for this scan session.", conflict.getMessage());
    }

    private static ScanEvaluationCommand sampleCommand() {
        return new ScanEvaluationCommand(
                null,
                null,
                null,
                null,
                72.0,
                40.0,
                15.0,
                0.4,
                1.8,
                0.91,
                0.8,
                0.97,
                0.94,
                22.0,
                List.of(),
                100.0,
                110.0,
                90.0
        );
    }

    private static ScanEvaluationOutcome outcome() {
        return new ScanEvaluationOutcome(
                72.0,
                45.0,
                97.0,
                16.0,
                0.5,
                2.0,
                0.92,
                0.8,
                0.98,
                0.95,
                25.0,
                List.of(),
                List.of(),
                true,
                null,
                36.0,
                0.82,
                11.8,
                "monitor",
                0.71
        );
    }
}
