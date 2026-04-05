package com.pranapulse.core.consent.application;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.pranapulse.core.auth.domain.User;
import com.pranapulse.core.auth.repository.UserRepository;
import com.pranapulse.core.consent.repository.DeletionRequestRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class ConsentServiceIntegrationTest {

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private ConsentService consentService;

    @Autowired
    private DeletionRequestRepository deletionRequestRepository;

    @Test
    void grantAndRevokeConsentUpdatesLedgerStatus() {
        User user = userRepository.save(new User("oidc-consent-1", "consent-1@example.com", "Consent User", null));

        consentService.grantConsent(user.getId(), "1.0", "wellness_screening", "127.0.0.1", "JUnit");
        ConsentStatusSnapshot granted = consentService.getConsentStatus(user.getId());
        assertTrue(granted.hasActiveConsent());
        assertEquals("1.0", granted.consentVersion());
        assertNotNull(granted.grantedAt());

        consentService.revokeConsent(user.getId(), "127.0.0.1", "JUnit");
        ConsentStatusSnapshot revoked = consentService.getConsentStatus(user.getId());
        assertFalse(revoked.hasActiveConsent());
        assertNotNull(revoked.revokedAt());
        assertFalse(revoked.deletionRequested());
    }

    @Test
    void deletionRequestDisablesConsentAndCreatesPrivacyWorkItem() {
        User user = userRepository.save(new User("oidc-consent-2", "consent-2@example.com", "Consent User 2", null));

        consentService.grantConsent(user.getId(), "1.0", "wellness_screening", null, null);
        consentService.requestDeletion(user.getId(), "127.0.0.1", "JUnit");

        ConsentStatusSnapshot status = consentService.getConsentStatus(user.getId());
        assertFalse(status.hasActiveConsent());
        assertTrue(status.deletionRequested());
        assertNotNull(status.deletionScheduledAt());
        assertEquals(1L, deletionRequestRepository.countByUser_Id(user.getId()));
    }
}
