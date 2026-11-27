package com.pranapulse.core.scan.domain.contract;

import java.util.List;
import java.util.Locale;

/**
 * Guard for user-facing text: PranaScan reports wellness indicators, never diagnoses.
 * Labels and summaries must not name, imply or rule out a medical condition.
 */
public final class WellnessWording {

    /** Lower-case fragments that make text read as a diagnosis or clinical claim. */
    public static final List<String> PROHIBITED_FRAGMENTS = List.of(
            "diagnos", "disease", "disorder", "anemic", "anaemic", "anemia", "anaemia",
            "arrhythmi", "atrial", "hypertens", "tachycardi", "bradycardi", "parkinson",
            "patholog", "symptom", "medical condition", "abnormal", "you have", "detected condition");

    private WellnessWording() {
    }

    public static boolean isNonDiagnostic(String text) {
        if (text == null) {
            return true;
        }
        String lower = text.toLowerCase(Locale.ROOT);
        return PROHIBITED_FRAGMENTS.stream().noneMatch(lower::contains);
    }

    public static String requireNonDiagnostic(String text) {
        if (!isNonDiagnostic(text)) {
            throw new IllegalArgumentException("user-facing text must stay a wellness indicator, not a diagnosis");
        }
        return text;
    }
}
