package com.pranapulse.core.consent.application;

import com.pranapulse.core.auth.domain.User;
import com.pranapulse.core.auth.repository.UserRepository;
import com.pranapulse.core.consent.domain.ConsentAction;
import com.pranapulse.core.consent.domain.ConsentRecord;
import com.pranapulse.core.consent.domain.DeletionRequest;
import com.pranapulse.core.consent.repository.ConsentRecordRepository;
import com.pranapulse.core.consent.repository.DeletionRequestRepository;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.UUID;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ConsentService {

    private final UserRepository userRepository;
    private final ConsentRecordRepository consentRecordRepository;
    private final DeletionRequestRepository deletionRequestRepository;
    private final ConsentProperties consentProperties;

    public ConsentService(
            UserRepository userRepository,
            ConsentRecordRepository consentRecordRepository,
            DeletionRequestRepository deletionRequestRepository,
            ConsentProperties consentProperties
    ) {
        this.userRepository = userRepository;
        this.consentRecordRepository = consentRecordRepository;
        this.deletionRequestRepository = deletionRequestRepository;
        this.consentProperties = consentProperties;
    }

    @Transactional
    public ConsentRecord grantConsent(
            UUID userId,
            String consentVersion,
            String purpose,
            String ipAddress,
            String userAgent
    ) {
        User user = userRepository.getReferenceById(userId);
        return consentRecordRepository.save(
                new ConsentRecord(
                        user,
                        ConsentAction.GRANTED,
                        normalizeOrDefault(consentVersion, consentProperties.defaultVersion()),
                        normalizeOrDefault(purpose, "wellness_screening"),
                        ipAddress,
                        userAgent,
                        null
                )
        );
    }

    @Transactional
    public ConsentRecord revokeConsent(UUID userId, String ipAddress, String userAgent) {
        User user = userRepository.getReferenceById(userId);
        return consentRecordRepository.save(
                new ConsentRecord(
                        user,
                        ConsentAction.REVOKED,
                        consentProperties.defaultVersion(),
                        "consent_revocation",
                        ipAddress,
                        userAgent,
                        null
                )
        );
    }

    @Transactional
    public ConsentRecord requestDeletion(UUID userId, String ipAddress, String userAgent) {
        User user = userRepository.getReferenceById(userId);
        Instant deletionScheduledAt = Instant.now()
                .plus(consentProperties.deletionHoldDays(), ChronoUnit.DAYS);

        deletionRequestRepository.save(new DeletionRequest(user));
        return consentRecordRepository.save(
                new ConsentRecord(
                        user,
                        ConsentAction.DELETION_REQUESTED,
                        consentProperties.defaultVersion(),
                        "data_deletion_request",
                        ipAddress,
                        userAgent,
                        deletionScheduledAt
                )
        );
    }

    @Transactional(readOnly = true)
    public ConsentStatusSnapshot getConsentStatus(UUID userId) {
        List<ConsentRecord> records = consentRecordRepository.findByUser_IdOrderByCreatedAtAscIdAsc(userId);

        Instant grantedAt = null;
        Instant revokedAt = null;
        boolean deletionRequested = false;
        Instant deletionScheduledAt = null;
        String consentVersion = null;
        int lastGrantIndex = -1;
        int lastRevokeIndex = -1;

        for (int index = 0; index < records.size(); index++) {
            ConsentRecord record = records.get(index);
            if (record.getAction() == ConsentAction.GRANTED) {
                grantedAt = record.getCreatedAt();
                consentVersion = record.getConsentVersion();
                lastGrantIndex = index;
            } else if (record.getAction() == ConsentAction.REVOKED) {
                revokedAt = record.getCreatedAt();
                lastRevokeIndex = index;
            } else if (record.getAction() == ConsentAction.DELETION_REQUESTED) {
                deletionRequested = true;
                deletionScheduledAt = record.getDeletionScheduledAt();
            }
        }

        boolean hasActiveConsent = grantedAt != null
                && !deletionRequested
                && lastGrantIndex > lastRevokeIndex;

        return new ConsentStatusSnapshot(
                userId,
                hasActiveConsent,
                consentVersion,
                grantedAt,
                revokedAt,
                deletionRequested,
                deletionScheduledAt
        );
    }

    @Transactional(readOnly = true)
    public boolean hasActiveConsent(UUID userId) {
        return getConsentStatus(userId).hasActiveConsent();
    }

    public void requireActiveConsent(UUID userId) {
        if (!hasActiveConsent(userId)) {
            throw new AccessDeniedException(
                    "Active consent required to start a scan session. Please grant consent first."
            );
        }
    }

    private static String normalizeOrDefault(String value, String fallback) {
        if (value == null || value.isBlank()) {
            return fallback;
        }
        return value.trim();
    }
}
