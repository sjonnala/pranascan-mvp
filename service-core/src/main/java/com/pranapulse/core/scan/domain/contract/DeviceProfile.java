package com.pranapulse.core.scan.domain.contract;

import java.util.Objects;

/** Capture device profile (T-302); V2 + V8 scan_sessions columns. No user identifiers. */
public record DeviceProfile(
        String deviceModel,
        DevicePlatform platform,
        String osVersion,
        String appVersion,
        CapturePath capturePath,
        ColorRange colorRange,
        LockState aeLock,
        LockState awbLock) {

    public DeviceProfile {
        requireMaxLength(deviceModel, 128, "deviceModel");
        requireMaxLength(osVersion, 32, "osVersion");
        requireMaxLength(appVersion, 32, "appVersion");
        platform = Objects.requireNonNullElse(platform, DevicePlatform.UNKNOWN);
        capturePath = Objects.requireNonNullElse(capturePath, CapturePath.UNKNOWN);
        colorRange = Objects.requireNonNullElse(colorRange, ColorRange.UNKNOWN);
        aeLock = Objects.requireNonNullElse(aeLock, LockState.UNKNOWN);
        awbLock = Objects.requireNonNullElse(awbLock, LockState.UNKNOWN);
    }

    /** What a pre-V8 session row knows: model and app version only. */
    public static DeviceProfile legacy(String deviceModel, String appVersion) {
        return new DeviceProfile(deviceModel, null, null, appVersion, null, null, null, null);
    }

    private static void requireMaxLength(String value, int max, String name) {
        if (value != null && value.length() > max) {
            throw new IllegalArgumentException(name + " exceeds " + max + " characters");
        }
    }
}
