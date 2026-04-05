package com.pranapulse.core.scan.application;

import com.pranapulse.core.auth.domain.User;
import com.pranapulse.core.auth.repository.UserRepository;
import com.pranapulse.core.consent.application.ConsentService;
import com.pranapulse.core.scan.domain.ScanResult;
import com.pranapulse.core.scan.domain.ScanSession;
import com.pranapulse.core.scan.repository.ScanResultRepository;
import com.pranapulse.core.scan.repository.ScanSessionRepository;
import com.pranapulse.core.shared.error.NotFoundException;
import java.time.Instant;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ScanSessionService {

    private final UserRepository userRepository;
    private final ScanSessionRepository scanSessionRepository;
    private final ScanResultRepository scanResultRepository;
    private final ScanEvaluationService scanEvaluationService;
    private final ConsentService consentService;
    private final TrendAnalysisService trendAnalysisService;

    public ScanSessionService(
            UserRepository userRepository,
            ScanSessionRepository scanSessionRepository,
            ScanResultRepository scanResultRepository,
            ScanEvaluationService scanEvaluationService,
            ConsentService consentService,
            TrendAnalysisService trendAnalysisService
    ) {
        this.userRepository = userRepository;
        this.scanSessionRepository = scanSessionRepository;
        this.scanResultRepository = scanResultRepository;
        this.scanEvaluationService = scanEvaluationService;
        this.consentService = consentService;
        this.trendAnalysisService = trendAnalysisService;
    }

    @Transactional
    public ScanSession createSession(UUID userId, CreateScanSessionCommand command) {
        consentService.requireActiveConsent(userId);
        User user = userRepository.getReferenceById(userId);
        ScanSession session = new ScanSession(user, command.deviceModel(), command.appVersion());
        return scanSessionRepository.save(session);
    }

    @Transactional(noRollbackFor = ScanQualityRejectedException.class)
    public ScanResult completeSession(UUID actingUserId, UUID sessionId, ScanEvaluationCommand command) {
        ScanSession session = scanSessionRepository.findById(sessionId)
                .orElseThrow(() -> new NotFoundException("Session not found: " + sessionId));

        session.ensureOwnedBy(actingUserId);
        session.ensureCompletable();

        ScanEvaluationOutcome outcome = scanEvaluationService.evaluate(command);
        Instant completedAt = Instant.now();

        if (!outcome.qualityGatePassed()) {
            session.markRejected(completedAt);
            throw new ScanQualityRejectedException(outcome.flags(), outcome.rejectionReason());
        }

        String trendAlert = trendAnalysisService.computeTrendAlert(actingUserId, outcome);
        ScanResult scanResult = new ScanResult(session, session.getUser(), outcome, trendAlert);
        session.markCompleted(completedAt);
        return scanResultRepository.save(scanResult);
    }

    @Transactional(readOnly = true)
    public ScanSessionBundle getSession(UUID actingUserId, UUID sessionId) {
        ScanSession session = scanSessionRepository.findById(sessionId)
                .orElseThrow(() -> new NotFoundException("Session not found: " + sessionId));
        session.ensureOwnedBy(actingUserId);
        return new ScanSessionBundle(
                session,
                scanResultRepository.findBySessionId(sessionId).orElse(null)
        );
    }

    @Transactional(readOnly = true)
    public ScanHistoryPage getHistory(UUID actingUserId, int page, int pageSize) {
        return trendAnalysisService.buildHistoryPage(actingUserId, page, pageSize);
    }
}
