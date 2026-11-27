package com.pranapulse.core.scan.domain.contract;

import java.util.List;
import java.util.Objects;

/** Voice outcome (proto {@code VoiceAssessment}). */
public record VoiceAssessment(
        VoiceStatus status,
        List<VoiceAbstentionReason> abstentionReasons,
        boolean clientValuesCleared,
        Double clipFraction,
        boolean shimmerWithheldLowHnr) {

    public VoiceAssessment {
        status = Objects.requireNonNullElse(status, VoiceStatus.UNKNOWN);
        abstentionReasons = abstentionReasons == null ? List.of() : List.copyOf(abstentionReasons);
        if (status != VoiceStatus.ABSTAINED && !abstentionReasons.isEmpty()) {
            throw new IllegalArgumentException("voice abstention reasons require status ABSTAINED");
        }
        if (abstentionReasons.contains(VoiceAbstentionReason.UNSPECIFIED)) {
            throw new IllegalArgumentException("UNSPECIFIED is not a storable voice abstention reason");
        }
        QualityBreakdown.requireUnitInterval(clipFraction, "clipFraction");
    }

    public static VoiceAssessment abstained(List<VoiceAbstentionReason> reasons, boolean clientValuesCleared) {
        return new VoiceAssessment(VoiceStatus.ABSTAINED, reasons, clientValuesCleared, null, false);
    }
}
