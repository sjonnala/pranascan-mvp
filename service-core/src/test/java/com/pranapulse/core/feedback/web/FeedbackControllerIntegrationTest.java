package com.pranapulse.core.feedback.web;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.pranapulse.core.auth.domain.User;
import com.pranapulse.core.auth.repository.UserRepository;
import com.pranapulse.core.consent.application.ConsentService;
import com.pranapulse.core.scan.application.CreateScanSessionCommand;
import com.pranapulse.core.scan.application.ScanEvaluationCommand;
import com.pranapulse.core.scan.application.ScanEvaluationOutcome;
import com.pranapulse.core.scan.application.ScanEvaluationService;
import com.pranapulse.core.scan.application.ScanSessionService;
import com.pranapulse.core.scan.domain.ScanSession;
import com.pranapulse.core.scan.domain.ScanType;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class FeedbackControllerIntegrationTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private ConsentService consentService;

    @Autowired
    private ScanSessionService scanSessionService;

    @MockBean
    private ScanEvaluationService scanEvaluationService;

    @Test
    void createAndReadFeedbackThroughHttpApi() throws Exception {
        User user = userRepository.save(new User(
                "oidc-feedback-http-1",
                "feedback-http-1@example.com",
                "Feedback HTTP User 1",
                null
        ));
        consentService.grantConsent(user.getId(), "1.0", "wellness_screening", null, null);
        when(scanEvaluationService.evaluate(any())).thenReturn(outcome());

        ScanSession session = scanSessionService.createSession(
                user.getId(),
                new CreateScanSessionCommand(ScanType.STANDARD, "Pixel 9", "1.2.0")
        );
        scanSessionService.completeSession(user.getId(), session.getId(), sampleCommand());

        mockMvc.perform(post("/api/v1/feedback")
                        .with(jwt().jwt(jwt -> jwt
                                .subject("oidc-feedback-http-1")
                                .claim("email", "feedback-http-1@example.com")
                                .claim("name", "Feedback HTTP User 1")))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "session_id": "%s",
                                  "useful_response": "needs_work",
                                  "nps_score": 7,
                                  "comment": "Voice step felt long."
                                }
                                """.formatted(session.getId())))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.session_id").value(session.getId().toString()))
                .andExpect(jsonPath("$.useful_response").value("needs_work"))
                .andExpect(jsonPath("$.nps_score").value(7))
                .andExpect(jsonPath("$.comment").value("Voice step felt long."));

        mockMvc.perform(get("/api/v1/feedback/sessions/{sessionId}", session.getId())
                        .with(jwt().jwt(jwt -> jwt
                                .subject("oidc-feedback-http-1")
                                .claim("email", "feedback-http-1@example.com")
                                .claim("name", "Feedback HTTP User 1"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.session_id").value(session.getId().toString()))
                .andExpect(jsonPath("$.useful_response").value("needs_work"));
    }

    private static ScanEvaluationCommand sampleCommand() {
        return new ScanEvaluationCommand(
                ScanType.STANDARD,
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
                null,
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
                null,
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
