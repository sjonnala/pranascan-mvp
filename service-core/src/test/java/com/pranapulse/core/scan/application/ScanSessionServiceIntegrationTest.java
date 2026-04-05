package com.pranapulse.core.scan.application;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;

import com.pranapulse.core.auth.domain.User;
import com.pranapulse.core.auth.repository.UserRepository;
import com.pranapulse.core.consent.application.ConsentService;
import com.pranapulse.core.scan.domain.ScanResult;
import com.pranapulse.core.scan.domain.ScanSession;
import com.pranapulse.core.scan.domain.ScanSessionStatus;
import com.pranapulse.core.scan.domain.ScanType;
import com.pranapulse.core.scan.repository.ScanResultRepository;
import com.pranapulse.core.scan.repository.ScanSessionRepository;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.security.access.AccessDeniedException;

@SpringBootTest
class ScanSessionServiceIntegrationTest {

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private ScanSessionService scanSessionService;

    @Autowired
    private ScanSessionRepository scanSessionRepository;

    @Autowired
    private ScanResultRepository scanResultRepository;

    @Autowired
    private ConsentService consentService;

    @MockBean
    private ScanEvaluationService scanEvaluationService;

    @Test
    void createSessionRequiresActiveConsent() {
        User user = userRepository.save(new User("oidc-subject-0", "scan-owner-0@example.com", "Scan Owner 0", null));

        AccessDeniedException exception = assertThrows(
                AccessDeniedException.class,
                () -> scanSessionService.createSession(
                        user.getId(),
                        new CreateScanSessionCommand(ScanType.STANDARD, "Pixel 9", "1.2.0")
                )
        );

        assertTrue(exception.getMessage().contains("Active consent required"));
    }

    @Test
    void persistsRejectedStatusWhenQualityGateFails() {
        User user = userRepository.save(new User("oidc-subject-1", "scan-owner@example.com", "Scan Owner", null));
        consentService.grantConsent(user.getId(), "1.0", "wellness_screening", null, null);
        ScanSession session = scanSessionService.createSession(
                user.getId(),
                new CreateScanSessionCommand(ScanType.STANDARD, "Pixel 9", "1.2.0")
        );
        when(scanEvaluationService.evaluate(any())).thenReturn(rejectedOutcome());

        ScanQualityRejectedException exception = assertThrows(
                ScanQualityRejectedException.class,
                () -> scanSessionService.completeSession(user.getId(), session.getId(), sampleCommand())
        );

        ScanSession persistedSession = scanSessionRepository.findById(session.getId()).orElseThrow();
        assertEquals(List.of("low_lighting"), exception.getFlags());
        assertEquals(ScanSessionStatus.REJECTED, persistedSession.getStatus());
        assertNotNull(persistedSession.getCompletedAt());
        assertTrue(scanResultRepository.findBySessionId(session.getId()).isEmpty());
    }

    @Test
    void persistsCompletedSessionAndResultWhenEvaluationPasses() {
        User user = userRepository.save(new User("oidc-subject-2", "scan-owner-2@example.com", "Scan Owner 2", null));
        consentService.grantConsent(user.getId(), "1.0", "wellness_screening", null, null);
        ScanSession session = scanSessionService.createSession(
                user.getId(),
                new CreateScanSessionCommand(ScanType.STANDARD, "iPhone 17", "1.2.0")
        );
        when(scanEvaluationService.evaluate(any())).thenReturn(successOutcome());

        ScanResult scanResult = scanSessionService.completeSession(user.getId(), session.getId(), sampleCommand());

        ScanSession persistedSession = scanSessionRepository.findById(session.getId()).orElseThrow();
        assertEquals(ScanSessionStatus.COMPLETED, persistedSession.getStatus());
        assertNotNull(persistedSession.getCompletedAt());
        assertEquals(List.of("borderline_noise"), scanResult.getFlags());
        assertEquals(List.of("borderline_noise"), scanResult.getWarnings());
        assertTrue(scanResultRepository.findBySessionId(session.getId()).isPresent());
    }

    @Test
    void raisesTrendAlertAfterThreePriorBaselineScans() {
        User user = userRepository.save(new User("oidc-subject-3", "scan-owner-3@example.com", "Scan Owner 3", null));
        consentService.grantConsent(user.getId(), "1.0", "wellness_screening", null, null);

        when(scanEvaluationService.evaluate(any())).thenReturn(
                successOutcome(),
                successOutcome(),
                successOutcome(),
                deviatingOutcome()
        );

        for (int index = 0; index < 3; index++) {
            ScanSession session = scanSessionService.createSession(
                    user.getId(),
                    new CreateScanSessionCommand(ScanType.STANDARD, "Pixel 9", "1.2.0")
            );
            scanSessionService.completeSession(user.getId(), session.getId(), sampleCommand());
        }

        ScanSession alertSession = scanSessionService.createSession(
                user.getId(),
                new CreateScanSessionCommand(ScanType.STANDARD, "Pixel 9", "1.2.0")
        );
        ScanResult alertedResult = scanSessionService.completeSession(
                user.getId(),
                alertSession.getId(),
                sampleCommand()
        );

        assertEquals("consider_lab_followup", alertedResult.getTrendAlert());
    }

    @Test
    void returnsPaginatedHistory() {
        User user = userRepository.save(new User("oidc-subject-4", "scan-owner-4@example.com", "Scan Owner 4", null));
        consentService.grantConsent(user.getId(), "1.0", "wellness_screening", null, null);
        when(scanEvaluationService.evaluate(any())).thenReturn(successOutcome(), successOutcome(), successOutcome());

        for (int index = 0; index < 3; index++) {
            ScanSession session = scanSessionService.createSession(
                    user.getId(),
                    new CreateScanSessionCommand(ScanType.STANDARD, "Pixel 9", "1.2.0")
            );
            scanSessionService.completeSession(user.getId(), session.getId(), sampleCommand());
        }

        ScanHistoryPage historyPage = scanSessionService.getHistory(user.getId(), 1, 2);

        assertEquals(3, historyPage.total());
        assertEquals(2, historyPage.items().size());
        assertEquals(1, historyPage.page());
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

    private static ScanEvaluationOutcome rejectedOutcome() {
        return new ScanEvaluationOutcome(
                72.0,
                40.0,
                96.0,
                null,
                15.0,
                0.4,
                1.8,
                0.72,
                0.2,
                0.97,
                0.94,
                22.0,
                List.of("low_lighting"),
                List.of(),
                false,
                "Lighting score 0.20 too low.",
                36.0,
                0.78,
                11.4,
                "monitor",
                0.66
        );
    }

    private static ScanEvaluationOutcome successOutcome() {
        return new ScanEvaluationOutcome(
                72.0,
                40.0,
                97.0,
                null,
                15.0,
                0.4,
                1.8,
                0.91,
                0.8,
                0.97,
                0.94,
                22.0,
                List.of("borderline_noise"),
                List.of("borderline_noise"),
                true,
                null,
                36.0,
                0.78,
                11.4,
                "monitor",
                0.66
        );
    }

    private static ScanEvaluationOutcome deviatingOutcome() {
        return new ScanEvaluationOutcome(
                92.0,
                22.0,
                95.0,
                null,
                21.0,
                1.1,
                4.5,
                0.91,
                0.8,
                0.97,
                0.94,
                22.0,
                List.of(),
                List.of(),
                true,
                null,
                41.0,
                0.78,
                11.4,
                "monitor",
                0.66
        );
    }
}
