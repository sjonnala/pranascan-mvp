package com.pranapulse.core.scan.application;

import java.util.List;

public record ScanEvaluationOutcome(
        Double hrBpm,
        Double hrvMs,
        Double spo2,
        Double stiffnessIndex,
        Double respiratoryRate,
        Double voiceJitterPct,
        Double voiceShimmerPct,
        double qualityScore,
        Double lightingScore,
        Double motionScore,
        Double faceConfidence,
        Double audioSnrDb,
        List<String> flags,
        List<String> warnings,
        boolean qualityGatePassed,
        String rejectionReason,
        Double vascularAgeEstimate,
        Double vascularAgeConfidence,
        Double hbProxyScore,
        String anemiaWellnessLabel,
        Double anemiaConfidence
) {
}
