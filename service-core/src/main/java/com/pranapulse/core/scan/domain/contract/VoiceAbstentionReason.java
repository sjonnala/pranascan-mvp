package com.pranapulse.core.scan.domain.contract;

/** Why voice indicators were skipped (proto {@code VoiceAbstentionReason}). */
public enum VoiceAbstentionReason {
    INSUFFICIENT_SAMPLES,
    CLIPPING_DETECTED,
    NO_VOICE_DETECTED,
    INSUFFICIENT_VOICED_DURATION,
    HIGH_NOISE,
    INSUFFICIENT_GLOTTAL_CYCLES,
    UNSPECIFIED;

    public static VoiceAbstentionReason fromColumn(String column) {
        return ColumnEnums.fromColumn(VoiceAbstentionReason.class, column, UNSPECIFIED);
    }
}
