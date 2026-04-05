package com.pranapulse.core.report.application;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;

import com.pranapulse.core.auth.domain.User;
import com.pranapulse.core.auth.repository.UserRepository;
import com.pranapulse.core.consent.application.ConsentService;
import com.pranapulse.core.report.domain.VitalityReport;
import com.pranapulse.core.scan.application.CreateScanSessionCommand;
import com.pranapulse.core.scan.application.ScanEvaluationCommand;
import com.pranapulse.core.scan.application.ScanEvaluationOutcome;
import com.pranapulse.core.scan.application.ScanEvaluationService;
import com.pranapulse.core.scan.application.ScanSessionService;
import com.pranapulse.core.scan.domain.ScanSession;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;

@SpringBootTest
class VitalityReportServiceIntegrationTest {

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private ConsentService consentService;

    @Autowired
    private ScanSessionService scanSessionService;

    @Autowired
    private VitalityReportService vitalityReportService;

    @MockBean
    private ScanEvaluationService scanEvaluationService;

    @Test
    void generatesPersistedWeeklyReportFromCoreScanHistory() {
        User user = userRepository.save(new User("oidc-report-1", "report-user@example.com", "Report User", null));
        consentService.grantConsent(user.getId(), "1.0", "wellness_screening", null, null);
        when(scanEvaluationService.evaluate(any())).thenReturn(reportOutcome(), reportOutcome(), reportOutcome());

        for (int index = 0; index < 3; index++) {
            ScanSession session = scanSessionService.createSession(
                    user.getId(),
                    new CreateScanSessionCommand("Pixel 9", "1.2.0")
            );
            scanSessionService.completeSession(user.getId(), session.getId(), sampleCommand());
        }

        VitalityReport report = vitalityReportService.generate(user.getId());

        assertEquals(3, report.getScanCount());
        assertEquals(72.0, report.getAvgHrBpm());
        assertTrue(report.getSummaryText().contains(VitalityReportService.DISCLAIMER));
        assertEquals(report.getId(), vitalityReportService.getLatest(user.getId()).getId());
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

    private static ScanEvaluationOutcome reportOutcome() {
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
