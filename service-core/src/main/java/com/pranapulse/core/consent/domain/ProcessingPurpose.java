package com.pranapulse.core.consent.domain;

import java.util.Arrays;
import java.util.EnumSet;
import java.util.Set;

/**
 * DPDP processing purposes (runbook; V9 {@code consent_records.purpose_id}). Mirrors proto
 * {@code ProcessingPurpose}. Legacy bundled grants cover one-off scans and trends only:
 * research use always needs a fresh, separate opt-in.
 */
public enum ProcessingPurpose {
    SCAN_ONEOFF("scan.oneoff"),
    TREND_LONGITUDINAL("trend.longitudinal"),
    RESEARCH_MODEL_TRAINING("research.model_training"),
    LEGACY_BUNDLED("legacy.bundled");

    private final String purposeId;

    ProcessingPurpose(String purposeId) {
        this.purposeId = purposeId;
    }

    public String purposeId() {
        return purposeId;
    }

    /** NULL is how V9 sees pre-V9 writes during a rolling deploy: treated as legacy bundled. */
    public static ProcessingPurpose fromPurposeId(String purposeId) {
        if (purposeId == null || purposeId.isBlank()) {
            return LEGACY_BUNDLED;
        }
        return Arrays.stream(values())
                .filter(p -> p.purposeId.equals(purposeId.trim()))
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException("unknown purpose_id: " + purposeId));
    }

    /** Concrete purposes this grant covers. */
    public Set<ProcessingPurpose> effectivePurposes() {
        return this == LEGACY_BUNDLED ? EnumSet.of(SCAN_ONEOFF, TREND_LONGITUDINAL) : EnumSet.of(this);
    }
}
