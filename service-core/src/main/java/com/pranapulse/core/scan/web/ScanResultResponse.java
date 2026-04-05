package com.pranapulse.core.scan.web;

import com.pranapulse.core.scan.domain.ScanResult;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record ScanResultResponse(
        UUID id,
        UUID sessionId,
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
        String trendAlert,
        Double vascularAgeEstimate,
        Double vascularAgeConfidence,
        Double hbProxyScore,
        String anemiaWellnessLabel,
        Double anemiaConfidence,
        Instant createdAt
) {

    public static ScanResultResponse from(ScanResult scanResult) {
        return new ScanResultResponse(
                scanResult.getId(),
                scanResult.getSession().getId(),
                scanResult.getUser().getId(),
                scanResult.getHrBpm(),
                scanResult.getHrvMs(),
                scanResult.getSpo2(),
                scanResult.getRespiratoryRate(),
                scanResult.getVoiceJitterPct(),
                scanResult.getVoiceShimmerPct(),
                scanResult.getQualityScore(),
                scanResult.getLightingScore(),
                scanResult.getMotionScore(),
                scanResult.getFaceConfidence(),
                scanResult.getAudioSnrDb(),
                scanResult.getFlags(),
                scanResult.getWarnings(),
                scanResult.getTrendAlert(),
                scanResult.getVascularAgeEstimate(),
                scanResult.getVascularAgeConfidence(),
                scanResult.getHbProxyScore(),
                scanResult.getAnemiaWellnessLabel(),
                scanResult.getAnemiaConfidence(),
                scanResult.getCreatedAt()
        );
    }
}
