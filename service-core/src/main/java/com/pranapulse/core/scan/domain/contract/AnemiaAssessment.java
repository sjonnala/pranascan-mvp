package com.pranapulse.core.scan.domain.contract;

import java.util.Objects;

/**
 * Haemoglobin wellness indicator outcome (proto {@code AnemiaAssessment}). Mirrors V8's
 * {@code ck_scan_results_anemia_na_has_no_label}: not applicable means no label and no score.
 */
public record AnemiaAssessment(
        AnemiaApplicability applicability,
        AnemiaNotApplicableReason notApplicableReason,
        String wellnessLabel,
        Double hbProxyScore) {

    public AnemiaAssessment {
        applicability = Objects.requireNonNullElse(applicability, AnemiaApplicability.UNKNOWN);
        notApplicableReason = Objects.requireNonNullElse(notApplicableReason, AnemiaNotApplicableReason.UNSPECIFIED);
        if (applicability == AnemiaApplicability.NOT_APPLICABLE && (wellnessLabel != null || hbProxyScore != null)) {
            throw new IllegalArgumentException("a not-applicable indicator cannot carry a label or score");
        }
        if (applicability != AnemiaApplicability.NOT_APPLICABLE
                && notApplicableReason != AnemiaNotApplicableReason.UNSPECIFIED) {
            throw new IllegalArgumentException("not-applicable reason requires applicability NOT_APPLICABLE");
        }
        if (wellnessLabel != null) {
            WellnessWording.requireNonDiagnostic(wellnessLabel);
        }
    }

    public static AnemiaAssessment notApplicable(AnemiaNotApplicableReason reason) {
        return new AnemiaAssessment(AnemiaApplicability.NOT_APPLICABLE, reason, null, null);
    }

    public static AnemiaAssessment fromColumns(String applicability, String reason, String label, Double hbProxy) {
        return new AnemiaAssessment(AnemiaApplicability.fromColumn(applicability),
                AnemiaNotApplicableReason.fromColumn(reason), label, hbProxy);
    }
}
