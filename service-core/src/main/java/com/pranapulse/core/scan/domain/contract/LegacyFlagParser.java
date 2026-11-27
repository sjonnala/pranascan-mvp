package com.pranapulse.core.scan.domain.contract;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/**
 * Tolerant reader for rev-1 intelligence, which encodes diagnostics into {@code flags}
 * ({@code hr_abstained}, {@code abstain_reason:<x>}, {@code mobile_quality_score:0.41}, ...).
 * Used only when a response has no typed sub-message; delete after rollout step 4 (T-401 §7).
 * Malformed or unknown values never throw.
 */
public final class LegacyFlagParser {

    /** Bare internal markers that must never reach users as "Scan notes". */
    static final Set<String> INTERNAL_MARKERS = Set.of(
            "hr_abstained", "no_reliable_pulse", "hrv_withheld_low_fps", "anemia_not_applicable");

    private LegacyFlagParser() {
    }

    public static HeartRateAssessment rppgFrom(List<String> flags) {
        List<String> safe = flags == null ? List.of() : flags;
        boolean abstained = safe.contains("hr_abstained") || safe.contains("no_reliable_pulse");
        if (!abstained) {
            return new HeartRateAssessment(HeartRateStatus.UNKNOWN, HrAbstentionReason.UNSPECIFIED,
                    null, safe.contains("hrv_withheld_low_fps"), null, null);
        }
        HrAbstentionReason reason = valueOf(safe, "abstain_reason")
                .map(HrAbstentionReason::fromLegacyFlagValue)
                .orElse(HrAbstentionReason.UNSPECIFIED);
        return HeartRateAssessment.abstained(reason, null);
    }

    public static QualityBreakdown qualityFrom(List<String> flags) {
        List<String> safe = flags == null ? List.of() : flags;
        Double mobile = unitScore(valueOf(safe, "mobile_quality_score").orElse(null));
        Double spectral = unitScore(valueOf(safe, "spectral_quality_score").orElse(null));
        Double snr = number(valueOf(safe, "spectral_snr_db").orElse(null));
        QualityScoreBasis basis = spectral != null ? QualityScoreBasis.SPECTRAL : QualityScoreBasis.UNKNOWN;
        return new QualityBreakdown(mobile, spectral, snr, basis);
    }

    /** Keeps human-meaningful quality flags; drops {@code key:value} diagnostics and internal markers. */
    public static List<String> stripEncoded(List<String> flags) {
        if (flags == null) {
            return List.of();
        }
        List<String> kept = new ArrayList<>();
        for (String flag : flags) {
            if (flag == null) {
                continue;
            }
            String normalized = flag.trim().toLowerCase(Locale.ROOT);
            if (normalized.contains(":") || normalized.startsWith("voice_") || INTERNAL_MARKERS.contains(normalized)) {
                continue;
            }
            kept.add(flag);
        }
        return List.copyOf(kept);
    }

    private static java.util.Optional<String> valueOf(List<String> flags, String key) {
        String prefix = key + ":";
        return flags.stream()
                .filter(f -> f != null && f.startsWith(prefix))
                .map(f -> f.substring(prefix.length()))
                .findFirst();
    }

    private static Double number(String raw) {
        if (raw == null) {
            return null;
        }
        try {
            double v = Double.parseDouble(raw.trim());
            return Double.isFinite(v) ? v : null;
        } catch (NumberFormatException ex) {
            return null;
        }
    }

    private static Double unitScore(String raw) {
        Double v = number(raw);
        return v != null && v >= 0.0 && v <= 1.0 ? v : null;
    }
}
