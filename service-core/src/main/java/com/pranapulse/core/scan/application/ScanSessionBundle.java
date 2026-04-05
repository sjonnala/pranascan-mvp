package com.pranapulse.core.scan.application;

import com.pranapulse.core.scan.domain.ScanResult;
import com.pranapulse.core.scan.domain.ScanSession;

public record ScanSessionBundle(
        ScanSession session,
        ScanResult result
) {
}
