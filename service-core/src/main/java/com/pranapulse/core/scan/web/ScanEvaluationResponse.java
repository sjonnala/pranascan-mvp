package com.pranapulse.core.scan.web;

import com.pranapulse.core.scan.application.ScanEvaluationOutcome;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import java.util.List;
import java.util.UUID;

@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record ScanEvaluationResponse(
        UUID userId,
        Double hrBpm,
        Double hrvMs,
        Double spo2,
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

    public static ScanEvaluationResponse from(UUID userId, ScanEvaluationOutcome outcome) {
        return new ScanEvaluationResponse(
                userId,
                outcome.hrBpm(),
                outcome.hrvMs(),
                outcome.spo2(),
                outcome.respiratoryRate(),
                outcome.voiceJitterPct(),
                outcome.voiceShimmerPct(),
                outcome.qualityScore(),
                outcome.lightingScore(),
                outcome.motionScore(),
                outcome.faceConfidence(),
                outcome.audioSnrDb(),
                outcome.flags(),
                outcome.warnings(),
                outcome.qualityGatePassed(),
                outcome.rejectionReason(),
                outcome.vascularAgeEstimate(),
                outcome.vascularAgeConfidence(),
                outcome.hbProxyScore(),
                outcome.anemiaWellnessLabel(),
                outcome.anemiaConfidence()
        );
    }
}
