package com.pranapulse.core.scan.domain.contract;

import java.util.Objects;

/** Capture cadence reported by mobile (PR #2) at session completion; V8 scan_sessions columns. */
public record CaptureTiming(
        Double deliveredFps,
        Double fpsJitterMs,
        Double meanFrameIntervalMs,
        FrameTimestampSource timestampSource) {

    public CaptureTiming {
        requireNonNegative(deliveredFps, "deliveredFps");
        requireNonNegative(fpsJitterMs, "fpsJitterMs");
        requireNonNegative(meanFrameIntervalMs, "meanFrameIntervalMs");
        timestampSource = Objects.requireNonNullElse(timestampSource, FrameTimestampSource.UNKNOWN);
    }

    private static void requireNonNegative(Double value, String name) {
        if (value != null && (value.isNaN() || value < 0.0)) {
            throw new IllegalArgumentException(name + " cannot be negative: " + value);
        }
    }
}
