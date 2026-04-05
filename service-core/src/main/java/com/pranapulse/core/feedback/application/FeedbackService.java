package com.pranapulse.core.feedback.application;

import com.pranapulse.core.feedback.domain.ScanFeedback;
import com.pranapulse.core.feedback.repository.ScanFeedbackRepository;
import com.pranapulse.core.scan.domain.ScanSession;
import com.pranapulse.core.scan.domain.ScanSessionStatus;
import com.pranapulse.core.scan.repository.ScanSessionRepository;
import com.pranapulse.core.shared.error.ConflictException;
import com.pranapulse.core.shared.error.NotFoundException;
import java.util.Objects;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class FeedbackService {

    private final ScanSessionRepository scanSessionRepository;
    private final ScanFeedbackRepository scanFeedbackRepository;

    public FeedbackService(
            ScanSessionRepository scanSessionRepository,
            ScanFeedbackRepository scanFeedbackRepository
    ) {
        this.scanSessionRepository = scanSessionRepository;
        this.scanFeedbackRepository = scanFeedbackRepository;
    }

    @Transactional
    public ScanFeedback create(
            UUID actingUserId,
            UUID sessionId,
            String usefulResponse,
            Integer npsScore,
            String comment
    ) {
        ScanSession session = getOwnedCompletedSession(actingUserId, sessionId);
        if (scanFeedbackRepository.findBySession_Id(sessionId).isPresent()) {
            throw new ConflictException("Feedback has already been recorded for this scan session.");
        }
        return scanFeedbackRepository.save(
                new ScanFeedback(session, session.getUser(), usefulResponse, npsScore, comment)
        );
    }

    @Transactional(readOnly = true)
    public ScanFeedback getForSession(UUID actingUserId, UUID sessionId) {
        getOwnedCompletedSession(actingUserId, sessionId);
        return scanFeedbackRepository.findBySession_Id(sessionId)
                .orElseThrow(() -> new NotFoundException("No feedback found for this scan session."));
    }

    private ScanSession getOwnedCompletedSession(UUID actingUserId, UUID sessionId) {
        ScanSession session = scanSessionRepository.findById(sessionId)
                .orElseThrow(() -> new NotFoundException("Session not found."));
        if (!Objects.equals(session.getUser().getId(), actingUserId)) {
            throw new NotFoundException("Session not found.");
        }
        if (session.getStatus() != ScanSessionStatus.COMPLETED) {
            throw new ConflictException("Feedback can only be recorded for completed scan sessions.");
        }
        return session;
    }
}
